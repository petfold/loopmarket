"""The distributed offer book: a RecordStore keyspace with index prefixes.

Layout (one book = one RecordStore, one root reference per version):

    offer/<offer_id>                 -> the offer record (immutable value)
    sig/<offer_id>                   -> detached maker signature (U8, off-feed)
    withdraw/<offer_id>              -> 1  (monotone tombstone: offer closed)
    fill/<offer_id>                  -> {"loop": <loop_id>}
    loop/<loop_id>                   -> the settled loop record
    idx/c/<concept>/<offer_id>       -> 1     (per thing concept)
    idx/t/<day>/<offer_id>           -> 1     (per touched service day)
    idx/g/<cell-prefix>/<offer_id>   -> 1     (per geohash prefix of the cell)

The `idx/` keys are *derived* state and live only in an aggregator's
derived-index store (P1, 2026-08-21) — maker books never write them: they
were read by nothing at the source, each publish would pay ~10+ chunk
writes of postage waste on Swarm, and derived values never merge (they
are re-derived after every fold instead — `index_offers`).

Everything the marketplace knows at a moment is one root reference:
`snapshot()` returns `(root, frozen_reader)`, and solvers work against that
frozen state — recordstore's snapshot isolation is what makes "solve against
a pinned book" free. Offers are immutable and content-addressed, so
publication is naturally an OR-set: concurrent publishers writing the same
offer write byte-identical records (canonical encoding), concurrent distinct
publications touch distinct keys, and `commit(reconcile=True)` three-way
merges the rest. The only genuinely racy key class is `fill/` — settlement
claims — resolved first-writer-wins by `or_set_resolver`.

Deployment shapes (see ARCHITECTURE.md §5):
- local/dev: RecordStore over MemoryBytesStore/DirBytesStore.
- shared book on Swarm: `swarm_offer_book(topic, signer=...)` — blobs via
  BeeBytesStore, the mutable head via a signed SwarmFeedPointer.
- fully peer-to-peer: one book *per maker* (each maker signs their own feed);
  an aggregator folds maker roots with `RecordStore.merge`, which the
  canonical trie makes O(divergence). The key layout is identical either way.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from .schema import Offer
from .spacetime import bucket_chain, cell_chain, cell_for, day_buckets

OFFER = "offer/"
SIG = "sig/"
WITHDRAW = "withdraw/"
FILL = "fill/"
LOOP = "loop/"


class PartialLoopError(RuntimeError):
    """A book holds a loop missing some of its fills (planned invariant U11).

    Settlement is atomic per writer, so this can only arise from a merge in
    which two loops claimed one offer. There is no safe repair — evicting a
    settled loop is a finality rollback — so the checker raises instead of
    resolving, by design (docs/plans/P1-federated-book.md §3).
    """


def or_set_resolver(key: str, base, ours, theirs):
    """Merge policy for concurrent book writers.

    Offers and indexes are add-only values of identical content — either
    side's copy is the value. A doubly-claimed offer keeps the
    lexicographically smaller loop id, deterministically on every replica
    (commutative, so 3+ writers stay order-independent).

    The per-key fill rule is convergence mechanics, not settlement policy:
    when two loops claim one offer, resolving fill-by-fill can strand the
    losing loop with its `loop/` record and its *other* fills — a settled
    loop missing a leg, which nothing repairs. Until the deterministic
    loop-granularity resolver exists (registered open problem,
    docs/plans/P1-federated-book.md §3), `verify_loop_atomicity` checks the
    merged book and fails loudly (planned invariant U11).
    """
    if ours == theirs:
        return ours
    if key.startswith(FILL):
        candidates = [v for v in (ours, theirs) if isinstance(v, dict)]
        return min(candidates, key=lambda v: v.get("loop", "")) if candidates else ours
    # add-only keyspace: prefer presence over absence
    return ours if ours is not None else theirs


class OfferRegistry:
    """Publish, enumerate and settle offers over a duck-typed RecordStore."""

    def __init__(self, store):
        self.store = store

    # -- writing ---------------------------------------------------------------

    def publish(self, offer: Offer) -> str:
        oid = offer.offer_id
        self.store.put(OFFER + oid, offer.to_record())
        return oid

    def publish_many(self, offers: Iterable[Offer]) -> list[str]:
        return [self.publish(o) for o in offers]

    def absorb(self, other: "OfferRegistry") -> None:
        """Re-assert another book's entire content as this writer's base.

        The settlement pattern (P1 §1): a settlement instance bases its
        *own feed* on an aggregator's fold by re-asserting the folded
        records and committing. Canonical encoding makes the re-commit
        reproduce the source root byte-for-byte — equal content, equal
        root — so anyone can verify the claimed base is exactly the fold
        (ontodag's clone-verification pattern). O(book); incremental
        re-basing via `diff` is the production upgrade.
        """
        for key, rec in other.store.items(""):
            self.store.put(key, rec)

    def withdraw(self, offer_id: str) -> None:
        """Close an offer forever: a monotone tombstone (lands with P1, §5).

        An *add*, never a delete — a removal is lossy and does not commute
        with a concurrent addition, so it cannot survive a grow-only merge;
        the tombstone merges as ordinary OR-set presence and fails closed
        the moment it is visible at fold time. Re-publishing the identical
        offer does not un-withdraw it (same content, same id, same
        tombstone): a fresh intention is a fresh offer, fresh nonce,
        fresh id.
        """
        if not self.store.contains(OFFER + offer_id):
            raise KeyError(offer_id)
        self.store.put(WITHDRAW + offer_id, 1)

    def is_withdrawn(self, offer_id: str) -> bool:
        return self.store.contains(WITHDRAW + offer_id)

    def attach_signature(self, offer_id: str, sig_hex: str) -> None:
        """Store a detached maker signature beside its offer (planned U8).

        The secondary authenticity layer, for offers circulating outside
        their home feed; feed ownership stays primary. Fail closed: a
        signature that does not recover to the offer's maker is refused,
        so the book never holds a sidecar that lies about who is speaking.
        Needs the `sig` extra (eth-keys).
        """
        from .sigs import recover_maker

        offer = self.get(offer_id)
        if recover_maker(offer_id, sig_hex) != offer.maker:
            raise ValueError("signature does not recover to the offer's maker")
        self.store.put(SIG + offer_id, sig_hex)

    def signature(self, offer_id: str) -> str | None:
        """The offer's detached signature, if one has been attached."""
        key = SIG + offer_id
        return self.store.get(key) if self.store.contains(key) else None

    def mark_filled(self, offer_ids: Iterable[str], loop_id: str,
                    loop_record: dict) -> None:
        """Claim every offer for the loop; a pure function of the decision.

        No wall clock: the same logical settlement must produce
        byte-identical records on every replica ("equal content ⇒ equal
        root"). Timestamps that matter are attributed provenance, and
        trustworthy time is *anchored* time — a feed index or an on-chain
        anchor — which is factbond's to build, never a field smuggled into
        the fill (docs/plans/P1-federated-book.md §3).
        """
        for oid in offer_ids:
            self.store.put(FILL + oid, {"loop": loop_id})
        self.store.put(LOOP + loop_id, loop_record)

    def commit(self, *, reconcile: bool = True) -> str:
        """Land staged changes; with reconcile, converge with other writers.

        Every reconciled commit re-checks loop atomicity (U11): a scan of
        `loop/` and `fill/`, the stopgap price of per-key fill resolution.
        """
        try:
            root = self.store.commit(reconcile=reconcile, resolver=or_set_resolver)
        except TypeError:  # store without multi-writer support (plain mock)
            return self.store.commit()
        if reconcile:
            self.verify_loop_atomicity()
        return root

    def verify_loop_atomicity(self) -> None:
        """Raise PartialLoopError unless every loop in the book is whole.

        The U11 invariant, checked rather than resolved: every present
        `loop/` record holds the fill of every leg it names, and every
        `fill/` points at a present loop. Run after every fold (reconciled
        commits do it automatically; aggregators folding with
        `RecordStore.merge` must call it themselves).
        """
        for key, rec in self.store.items(LOOP):
            lid = key[len(LOOP):]
            for leg in rec.get("legs", []):
                for oid in (leg["give"], leg["want"]):
                    claim = (self.store.get(FILL + oid)
                             if self.store.contains(FILL + oid) else None)
                    winner = claim.get("loop") if isinstance(claim, dict) else None
                    if winner != lid:
                        raise PartialLoopError(
                            f"loop {lid[:12]} lost offer {oid[:12]} to "
                            f"{winner[:12] if winner else 'nothing'}"
                        )
        for key, rec in self.store.items(FILL):
            lid = rec.get("loop", "") if isinstance(rec, dict) else ""
            if not self.store.contains(LOOP + lid):
                raise PartialLoopError(
                    f"fill on {key[len(FILL):][:12]} points at absent loop"
                )

    # -- reading ---------------------------------------------------------------

    def snapshot(self):
        """(root, frozen registry) — the unit a solver works against."""
        root = self.store.root
        frozen = type(self.store).at(root, self.store.blobs)
        return root, OfferRegistry(frozen)

    def get(self, offer_id: str) -> Offer:
        return Offer.from_record(self.store.get(OFFER + offer_id))

    def is_filled(self, offer_id: str) -> bool:
        return self.store.contains(FILL + offer_id)

    def offers(self, *, now: int | None = None,
               include_filled: bool = False) -> Iterator[Offer]:
        """Active offers: fills, tombstones and (given `now`) expiry filtered.

        `include_filled=True` disables all liveness filtering — the
        full-book scan a follower or auditor wants.
        """
        for key, rec in self.store.items(OFFER):
            oid = key[len(OFFER):]
            if not include_filled and (self.is_filled(oid)
                                       or self.is_withdrawn(oid)):
                continue
            offer = Offer.from_record(rec)
            if now is not None and not offer.valid.is_open_at(now):
                continue
            yield offer

    def ids_by_index(self, prefix: str) -> Iterator[str]:
        """Offer ids under an index prefix, e.g. 'idx/c/produce/'.

        Meaningful only on a store carrying a derived index (an
        aggregator's, built by `index_offers`) — maker books hold none.
        """
        for key in self.store.keys(prefix):
            yield key.rsplit("/", 1)[-1]


def index_offers(store, offers: Iterable[Offer]) -> None:
    """File offers under the idx/{c,t,g} prefixes of a *derived* store.

    Hints, never truth (cells index disc centres only; exact geometry is
    `check_match`'s): regenerable from any book root, so an aggregator
    rebuilds this store after every fold and nothing ever merges it —
    the derived-values-never-merge rule ontodag learned from counts.
    """
    for offer in offers:
        oid = offer.offer_id
        for concept in offer.thing.concepts:
            store.put(f"idx/c/{concept}/{oid}", 1)
        for day in day_buckets(offer.service):
            for bucket in bucket_chain(day):
                store.put(f"idx/t/{bucket}/{oid}", 1)
        for prefix in cell_chain(cell_for(offer.where)):
            store.put(f"idx/g/{prefix}/{oid}", 1)


# ------------------------------------------------------------------ Swarm wiring

def swarm_offer_book(topic: str, *, signer=None, owner=None, **kw) -> OfferRegistry:
    """A shared offer book on Swarm: BeeBytesStore blobs + signed feed head.

    Exactly recordstore's `swarm_store` — pass `signer` to publish (your
    book / a shared book you hold the key for) or `owner` to follow someone
    else's. Requires `recordstore[bee,feeds]` and a Bee node with a usable
    postage batch (see the swarm extra in pyproject.toml).
    """
    from recordstore import swarm_store

    return OfferRegistry(swarm_store(topic, signer=signer, owner=owner, **kw))
