"""The book under replication and merge: determinism, loop atomicity.

Memory-backed variants of the P1 federation gates
(docs/plans/P1-federated-book.md): equal settlements must produce equal
roots on every replica, and no partially-filled loop may survive a merge
(planned invariant U11).
"""

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    GeoDisc, MockSettlement, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, ask, bid,
)

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
