"""The distributed offer book: a RecordStore keyspace.

Layout (one book = one RecordStore, one root reference per version):

    offer/<offer_id>                 -> the offer record (immutable value)
    sig/<offer_id>                   -> detached maker signature (U8, off-feed)
    handoff/<loop_id>/<offer_id>     -> sealed settlement text (handoff.py)
    withdraw/<offer_id>              -> 1  (monotone tombstone: offer closed)
    fill/<offer_id>                  -> {"loop": <loop_id>}
    loop/<loop_id>                   -> the cleared loop record

There is no index in the book. The `idx/{c,t,g}` prefixes (per concept,
per touched day bucket, per geohash prefix) were written by maker books
until 2026-08-21, then only by aggregators as derived state, and read by
nothing throughout; they retired 2026-09-12 when ontodag #14 made the
`DimensionIndex` one query — ontodag is the one intersection engine, and
a second index of the same three dimensions never gets a query path
(`docs/plans/ontodag-coupling.md` §5). Derived query structures, if they
are ever published, get a manifest root of their own then (cone
summaries, `P1-federated-book.md` §2) — never book keys.

Everything the marketplace knows at a moment is one root reference:
`snapshot()` returns `(root, frozen_reader)`, and solvers work against that
frozen state — recordstore's snapshot isolation is what makes "solve against
a pinned book" free. Offers are immutable and content-addressed, so
publication is naturally an OR-set: concurrent publishers writing the same
offer write byte-identical records (canonical encoding), concurrent distinct
publications touch distinct keys, and `commit(reconcile=True)` three-way
merges the rest. The only genuinely racy key class is `fill/` — clearing
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

OFFER = "offer/"
SIG = "sig/"
WITHDRAW = "withdraw/"
FILL = "fill/"
LOOP = "loop/"
HANDOFF = "handoff/"   # handoff/<loop_id>/<offer_id> -> sealed text (see handoff.py)


class PartialLoopError(RuntimeError):
    """A book holds a loop missing some of its fills (planned invariant U11).

    Clearing is atomic per writer, so this can only arise from a merge in
    which two loops claimed one offer. There is no safe repair — evicting a
    cleared loop is a finality rollback — so the checker raises instead of
    resolving, by design (docs/plans/P1-federated-book.md §3).
    """


def or_set_resolver(key: str, base, ours, theirs):
    """Merge policy for concurrent book writers.

    Offers and indexes are add-only values of identical content — either
    side's copy is the value. A doubly-claimed offer keeps the
    lexicographically smaller loop id, deterministically on every replica
    (commutative, so 3+ writers stay order-independent).

    The per-key fill rule is convergence mechanics, not clearing policy:
    when two loops claim one offer, resolving fill-by-fill can strand the
    losing loop with its `loop/` record and its *other* fills — a cleared
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
    """Publish, enumerate and clear offers over a duck-typed RecordStore."""

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

        The clearing pattern (P1 §1): a clearing instance bases its
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

    def loop_of(self, offer_id: str) -> str | None:
        """The loop that filled `offer_id`, if any."""
        key = FILL + offer_id
        rec = self.store.get(key) if self.store.contains(key) else None
        return rec.get("loop") if isinstance(rec, dict) else None

    def attach_handoff(self, loop_id: str, offer_id: str, record: dict, *,
                       fold=None) -> None:
        """Store a sealed handoff beside a *filled* offer of this book's
        maker: `handoff/<loop_id>/<offer_id>` (docs/plans/P1-spacetime-terms.md
        §4; `handoff.seal` makes the record). A sidecar like `sig/` — never
        in identity, OR-set presence in merges, unread by aggregators. The
        fill is checked against `fold` when given (fills live in the
        clearing book, which a maker's own book need not contain), else
        against this book. Fail closed: no fill, no handoff."""
        book = fold if fold is not None else self
        if book.loop_of(offer_id) != loop_id:
            raise ValueError("handoff for an offer this loop did not fill")
        if not isinstance(record, dict) or "ct" not in record:
            raise ValueError("a handoff record is a sealed payload")
        self.store.put(f"{HANDOFF}{loop_id}/{offer_id}", record)

    def handoff(self, loop_id: str, offer_id: str) -> dict | None:
        key = f"{HANDOFF}{loop_id}/{offer_id}"
        return self.store.get(key) if self.store.contains(key) else None

    def handoffs(self) -> Iterator[tuple[str, str, dict]]:
        """Every (loop_id, offer_id, sealed record) in the book."""
        for key, rec in self.store.items(HANDOFF):
            loop_id, _, offer_id = key[len(HANDOFF):].partition("/")
            yield loop_id, offer_id, rec

    def mark_filled(self, offer_ids: Iterable[str], loop_id: str,
                    loop_record: dict) -> None:
        """Claim every offer for the loop; a pure function of the decision.

        No wall clock: the same logical clearing must produce
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
