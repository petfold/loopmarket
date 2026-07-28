"""The distributed offer book: a RecordStore keyspace with index prefixes.

Layout (one book = one RecordStore, one root reference per version):

    offer/<offer_id>                 -> the offer record (immutable value)
    fill/<offer_id>                  -> {"loop": <loop_id>, "at": t}
    loop/<loop_id>                   -> the settled loop record
    idx/c/<concept>/<offer_id>       -> 1     (per thing concept)
    idx/t/<day>/<offer_id>           -> 1     (per touched service day)
    idx/g/<cell-prefix>/<offer_id>   -> 1     (per geohash prefix of the cell)

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

import time as _time
from typing import Iterable, Iterator

from .schema import Offer
from .spacetime import bucket_chain, cell_chain, cell_for, day_buckets

OFFER = "offer/"
FILL = "fill/"
LOOP = "loop/"


def or_set_resolver(key: str, base, ours, theirs):
    """Merge policy for concurrent book writers.

    Offers and indexes are add-only values of identical content — either
    side's copy is the value. Fills are first-writer-wins: a doubly-claimed
    offer keeps the lexicographically smaller loop id, deterministically on
    every replica (commutative, so 3+ writers stay order-independent).
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
        for concept in offer.thing.concepts:
            self.store.put(f"idx/c/{concept}/{oid}", 1)
        for day in day_buckets(offer.service):
            for bucket in bucket_chain(day):
                self.store.put(f"idx/t/{bucket}/{oid}", 1)
        for prefix in cell_chain(cell_for(offer.where)):
            self.store.put(f"idx/g/{prefix}/{oid}", 1)
        return oid

    def publish_many(self, offers: Iterable[Offer]) -> list[str]:
        return [self.publish(o) for o in offers]

    def mark_filled(self, offer_ids: Iterable[str], loop_id: str,
                    loop_record: dict) -> None:
        now = int(_time.time())
        for oid in offer_ids:
            self.store.put(FILL + oid, {"loop": loop_id, "at": now})
        self.store.put(LOOP + loop_id, loop_record)

    def commit(self, *, reconcile: bool = True) -> str:
        """Land staged changes; with reconcile, converge with other writers."""
        try:
            return self.store.commit(reconcile=reconcile, resolver=or_set_resolver)
        except TypeError:  # store without multi-writer support (plain mock)
            return self.store.commit()

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
        """All offers, filtering fills and (given `now`) expired validity."""
        for key, rec in self.store.items(OFFER):
            oid = key[len(OFFER):]
            if not include_filled and self.is_filled(oid):
                continue
            offer = Offer.from_record(rec)
            if now is not None and not offer.valid.is_open_at(now):
                continue
            yield offer

    def ids_by_index(self, prefix: str) -> Iterator[str]:
        """Offer ids under an index prefix, e.g. 'idx/c/produce/'."""
        for key in self.store.keys(prefix):
            yield key.rsplit("/", 1)[-1]


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
