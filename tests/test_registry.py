"""The book under replication and merge: determinism, loop atomicity.

Memory-backed variants of the P1 federation gates
(docs/plans/P1-federated-book.md): equal settlements must produce equal
roots on every replica, and no partially-filled loop may survive a merge
(planned invariant U11).
"""

import pytest
from recordstore import MemoryBytesStore, MemoryPointer, RecordStore

from loopmarket import (
    GeoDisc, MockSettlement, OfferRegistry, Ontology, PartialLoopError,
    SolverAgent, Thing, TimeWindow, ask, bid,
)
from loopmarket.registry import or_set_resolver

NOW = 1_700_000_000
W = dict(
    service=TimeWindow(NOW, NOW + 90 * 86_400),
    valid=TimeWindow(NOW - 1, NOW + 30 * 86_400),
    where=GeoDisc(46.0, 14.0, 50_000),
)
ONT = Ontology().load({"g1": [], "g2": [], "g3": []})

# One shared offer list: replicas of a book hold the *same* offers
# (identical canonical bytes), so any root divergence is the fill path's.
OFFERS = [
    ask("a", Thing(("g1",)), 100, nonce=1, **W),
    bid("a", Thing(("g3",)), 104, nonce=2, **W),
    ask("b", Thing(("g2",)), 50, nonce=3, **W),
    bid("b", Thing(("g1",)), 52, nonce=4, **W),
    ask("c", Thing(("g3",)), 80, nonce=5, **W),
    bid("c", Thing(("g2",)), 83, nonce=6, **W),
]


def _settled_root() -> str:
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    registry.publish_many(OFFERS)
    registry.commit()
    agent = SolverAgent(
        registry, ONT, MockSettlement(registry, ONT, clock=lambda: NOW)
    )
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and receipts[0].accepted
    return registry.store.root


def test_fill_determinism_across_replicas():
    # the P1 gate: two replicas settling the same loop produce
    # byte-identical fill/ and loop/ records, hence equal roots
    assert _settled_root() == _settled_root()


# --------------------------------------------------------- U11 loop atomicity

def _loop_rec(legs):
    return {"legs": [{"ask": a, "bid": b} for a, b in legs]}


def _writer(blobs, base_root):
    return OfferRegistry(RecordStore(blobs, root=base_root))


def _base():
    blobs = MemoryBytesStore()
    base = RecordStore(blobs)
    base.put("offer/seed", {"v": 1})   # any content; the checker reads loops
    return blobs, base.commit()


def test_conflicting_loops_fail_the_merge_loudly():
    # two writers settle loops sharing offers o3, o4; per-key resolution
    # keeps the smaller loop id on the shared fills, stranding the loser
    # with its loop/ record and its other fills — exactly what U11 forbids
    blobs, base_root = _base()
    a, b = _writer(blobs, base_root), _writer(blobs, base_root)
    a.mark_filled(("o1", "o2", "o3", "o4"), "L1", _loop_rec([("o1", "o2"), ("o3", "o4")]))
    b.mark_filled(("o3", "o4", "o5", "o6"), "L2", _loop_rec([("o3", "o4"), ("o5", "o6")]))
    merged = RecordStore.merge(
        blobs, base_root, a.store.commit(), b.store.commit(),
        resolver=or_set_resolver,
    )
    reg = OfferRegistry(RecordStore(blobs, root=merged))
    with pytest.raises(PartialLoopError):
        reg.verify_loop_atomicity()


def test_disjoint_loops_merge_whole():
    blobs, base_root = _base()
    a, b = _writer(blobs, base_root), _writer(blobs, base_root)
    a.mark_filled(("o1", "o2"), "L1", _loop_rec([("o1", "o2")]))
    b.mark_filled(("o5", "o6"), "L2", _loop_rec([("o5", "o6")]))
    merged = RecordStore.merge(
        blobs, base_root, a.store.commit(), b.store.commit(),
        resolver=or_set_resolver,
    )
    reg = OfferRegistry(RecordStore(blobs, root=merged))
    reg.verify_loop_atomicity()   # both loops arrived whole
    assert reg.store.get("fill/o1") == {"loop": "L1"}
    assert reg.store.get("fill/o5") == {"loop": "L2"}


def test_reconciled_commit_runs_the_checker():
    # same conflict through the commit(reconcile=True) path: two writers
    # sharing one head pointer, the second commit folds and must raise
    blobs = MemoryBytesStore()
    head = MemoryPointer()
    a = OfferRegistry(RecordStore(blobs, pointer=head))
    b = OfferRegistry(RecordStore(blobs, pointer=head))
    a.mark_filled(("o1", "o2", "o3", "o4"), "L1", _loop_rec([("o1", "o2"), ("o3", "o4")]))
    a.commit()
    b.mark_filled(("o3", "o4", "o5", "o6"), "L2", _loop_rec([("o3", "o4"), ("o5", "o6")]))
    with pytest.raises(PartialLoopError):
        b.commit()
