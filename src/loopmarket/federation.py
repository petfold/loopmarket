"""The federated book: per-maker books folded into one solver-speed view.

The production multi-writer shape (ARCHITECTURE §5 shape 3, ratified
2026-08-21): every book is single-writer at the source — each maker
publishes `offer/`, `sig/` and `withdraw/` keys under their own feed and
signer, settlement publishes `fill/` and `loop/` under its own — and
conflicts exist only at the fold. An **aggregator** folds announced books
with three-way merge under the loop-aware resolver, applies the U8 fold
rules per offer, records its decisions as attributed provenance, rebuilds
the derived index, and publishes the **manifest tuple**
`{book_root, provenance_root, index_root, announcement_root}`
(docs/plans/P1-federated-book.md §2).

The fold is *pure*: deterministic admission rules plus commutative merge
mean aggregators that saw the same inputs produce byte-identical
`book_root`s in any fold order — divergence between manifests is evidence,
not opinion, and omission is provable against `announcement_root` and the
announcement ground truth (threat register T14). Aggregators charge for
serving, never inclusion; an aggregator that folds selectively is a
censoring aggregator and is caught as one.

One assumption rides throughout: all books share one blob space — Swarm's
in deployment, one `MemoryBytesStore` in tests — so a root is enough to
reach any book's bytes. In memory, "feed ownership" is the declared
`owner` of an announced book; on Swarm it becomes the feed's owner
address, which is what makes U8's primary layer real (P1 §1).
"""

from __future__ import annotations

from dataclasses import dataclass

from .registry import (
    FILL, LOOP, OFFER, SIG, WITHDRAW, OfferRegistry, index_offers,
    or_set_resolver,
)
from .schema import Offer

#: Roles an announced book may carry: makers speak offers, signatures and
#: tombstones; a settlement instance speaks fills and loops. Every other
#: key class in a book is outside its writer's authority and is refused.
MAKER = "maker"
SETTLEMENT = "settlement"


@dataclass(frozen=True, slots=True)
class Manifest:
    """What an aggregator publishes: four roots and its name.

    `book_root` is the pure fold (byte-identical across honest aggregators
    with the same inputs); `provenance_root` holds the aggregator's
    attributed speech acts (`origin/`, `reject/`); `index_root` is derived
    and regenerable (never merged); `announcement_root` commits to the
    exact input set this fold consumed — the completeness handle (T14).
    """

    aggregator: str
    book_root: str
    provenance_root: str
    index_root: str
    announcement_root: str


class Aggregator:
    """Folds announced books into one book a solver can read at speed.

    `store_factory` returns a fresh writable RecordStore over the shared
    blob space (in tests: ``lambda: RecordStore(blobs)``; on Swarm, a
    store under the aggregator's own feed). Admission is by reference:
    the aggregator folds the books it was told about and can un-announce
    a flooder — there is no store-side rate limiting to game (P1 §8).
    """

    def __init__(self, store_factory, *, aggregator_id: str = "agg-0"):
        self._new_store = store_factory
        self.id = aggregator_id
        self._announced: dict[str, tuple[str, object]] = {}

    # -- inputs ----------------------------------------------------------------

    def announce(self, owner: str, store, *, role: str = MAKER) -> None:
        """Register a book: "`owner`'s book is `store`" (one per owner).

        In deployment the announcement arrives over GSOC or the registry
        events and names (owner address, topic); here the store stands in
        for the resolved feed. Re-announcing an owner replaces the entry;
        un-announcing (admission-by-reference's teeth) is `retract`.
        """
        if role not in (MAKER, SETTLEMENT):
            raise ValueError(f"unknown book role: {role!r}")
        self._announced[owner] = (role, store)

    def retract(self, owner: str) -> None:
        """Stop folding an owner's book (takes effect at the next fold)."""
        self._announced.pop(owner, None)

    # -- the fold ----------------------------------------------------------------

    def fold(self) -> Manifest:
        """Sanitize every announced book, merge, re-derive, publish.

        Every step is deterministic in the announced (owner, root) set, so
        the whole manifest — not just `book_root` — reproduces across
        aggregators that saw the same inputs.
        """
        provenance = self._new_store()
        announcement = self._new_store()

        staged_roots: list[str] = []
        blobs = None
        store_type = None
        for owner in sorted(self._announced):
            role, store = self._announced[owner]
            root = store.root
            announcement.put(f"announce/{owner}",
                             {"role": role, "root": root or ""})
            if not root:
                continue
            blobs, store_type = store.blobs, type(store)
            source = store_type.at(root, blobs)
            staged = self._sanitize(owner, role, root, source, provenance)
            staged_root = staged.commit()
            if staged_root:
                staged_roots.append(staged_root)

        book_root = None
        for staged_root in staged_roots:
            book_root = staged_root if book_root is None else \
                store_type.merge(blobs, None, book_root, staged_root,
                                 resolver=or_set_resolver)
        book_root = book_root or ""

        index = self._new_store()
        if book_root:
            folded = OfferRegistry(store_type.at(book_root, blobs))
            folded.verify_loop_atomicity()   # U11, on every fold
            index_offers(index, folded.offers())

        return Manifest(
            aggregator=self.id,
            book_root=book_root,
            provenance_root=provenance.commit() or "",
            index_root=index.commit() or "",
            announcement_root=announcement.commit() or "",
        )

    # -- admission (the U8 fold rules) -------------------------------------------

    def _sanitize(self, owner: str, role: str, root: str, source,
                  provenance) -> object:
        """One book's admissible speech, copied into a staging store.

        Fail closed in U7's spirit: a record outside its writer's
        authority, an unreadable or mis-keyed offer, a forged maker
        without a valid detached signature — none of it enters the fold,
        and every rejection is an attributed provenance record.
        """
        staged = self._new_store()

        def reject(key: str, reason: str) -> None:
            provenance.put(f"reject/{owner}/{key}",
                           {"owner": owner, "reason": reason})

        offers: dict[str, Offer] = {}
        records = dict(source.items())
        for key in sorted(records):
            rec = records[key]
            if key.startswith(OFFER):
                if role != MAKER:
                    continue    # settlement books carry folded offers; not theirs to assert
                oid = key[len(OFFER):]
                try:
                    offer = Offer.from_record(rec)
                except (ValueError, KeyError, TypeError):
                    reject(key, "unreadable offer record")
                    continue
                if offer.offer_id != oid:
                    reject(key, "content address mismatch")
                    continue
                if offer.maker != owner:
                    sig = records.get(SIG + oid)
                    if not self._sig_recovers(oid, sig, offer.maker):
                        reject(key, "foreign maker without valid signature")
                        continue
                    staged.put(SIG + oid, sig)
                offers[oid] = offer
                staged.put(key, rec)
                provenance.put(f"origin/{oid}", {"owner": owner, "root": root})
            elif key.startswith(WITHDRAW):
                if role != MAKER:
                    reject(key, "tombstone outside a maker book")
                    continue
                oid = key[len(WITHDRAW):]
                offer = offers.get(oid)   # offer/ sorts before withdraw/
                if offer is None or offer.maker != owner:
                    reject(key, "tombstone for an offer this book cannot close")
                    continue
                staged.put(key, rec)
            elif key.startswith(SIG):
                oid = key[len(SIG):]
                offer = offers.get(oid)   # offer/ sorts before sig/
                if offer is None:
                    reject(key, "signature without an admitted offer")
                elif offer.maker != owner:
                    pass   # verified and staged alongside its foreign offer
                elif self._sig_recovers(oid, rec, owner):
                    staged.put(key, rec)
                # else: an own-maker signature that does not verify here
                # (bad, or no crypto library) is dropped, not folded — feed
                # ownership already authenticates the offer itself.
            elif key.startswith(FILL) or key.startswith(LOOP):
                if role != SETTLEMENT:
                    reject(key, "settlement keys in a maker book")
                    continue
                staged.put(key, rec)
            else:
                reject(key, "unknown keyspace")
        return staged

    @staticmethod
    def _sig_recovers(offer_id: str, sig, maker: str) -> bool:
        """Fail closed: no signature, no crypto library, no entry."""
        if not isinstance(sig, str):
            return False
        try:
            from .sigs import recover_maker
            return recover_maker(offer_id, sig) == maker
        except Exception:
            return False
