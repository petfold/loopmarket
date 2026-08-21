"""The whole machine: publish -> snapshot-solve -> settle, atomically."""

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    GeoDisc, MockSettlement, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)

NOW = 1_700_000_000
W = dict(
    service=TimeWindow(NOW, NOW + 90 * 86_400),
    valid=TimeWindow(NOW - 1, NOW + 30 * 86_400),
)

ONT = Ontology().load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})


def _book(chen_oracle="countersign"):
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    a_flat = GeoDisc(46.05, 14.50, 5_000)
    b_farm = GeoDisc(46.10, 14.55, 15_000)
    c_shop = GeoDisc(46.06, 14.51, 4_000)
    registry.publish_many([
        give("amara", Thing(("piano-lesson",), unit="course"), 100, where=a_flat, **W),
        want("amara", Thing(("produce", "local", "weekly"), unit="course"), 104,
            where=a_flat, **W),
        give("bruno", Thing(("vegetable-box",), unit="course"), 50, where=b_farm, **W),
        want("bruno", Thing(("bicycle-repair",), unit="course"), 52, where=b_farm, **W),
        give("chen", Thing(("bicycle-repair",), unit="course"), 80, where=c_shop,
            oracle=chen_oracle, **W),
        want("chen", Thing(("music-lesson",), unit="course"), 83, where=c_shop, **W),
    ])
    registry.commit()
    return registry


def test_triangle_settles_and_book_empties():
    registry = _book()
    agent = SolverAgent(registry, ONT, MockSettlement(registry, ONT, clock=lambda: NOW))
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and receipts[0].accepted
    # the fills landed atomically under a new root
    assert list(registry.offers(now=NOW)) == []
    assert registry.store.contains(f"loop/{receipts[0].loop_id}")
    # a second solver pass finds nothing
    assert agent.step(now=NOW) == []


def test_settlement_rejects_double_spend():
    registry = _book()
    agent = SolverAgent(registry, ONT, MockSettlement(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    assert len(loops) == 1
    from loopmarket import LoopProposal
    proposal = LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    settlement = MockSettlement(registry, ONT, clock=lambda: NOW)
    assert settlement.submit(proposal).accepted
    second = settlement.submit(proposal)          # same loop again
    assert not second.accepted and "filled" in second.reason


def test_settlement_reverifies_against_ontology():
    registry = _book()
    agent = SolverAgent(registry, ONT, MockSettlement(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    from loopmarket import LoopProposal
    # a settlement bound to a *different* catalogue must reject the loop
    hostile = Ontology().load({"unrelated": []})
    settlement = MockSettlement(registry, hostile, clock=lambda: NOW)
    receipt = settlement.submit(
        LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    )
    assert not receipt.accepted and "re-verification" in receipt.reason


def test_settlement_refuses_pin_mismatch_and_absence():
    # U10's settlement rehearsal: the proposal's catalogue pin must equal
    # the settlement's own — a claimed root the verifier cannot confirm is
    # refused, and so is silence toward a pinned verifier
    registry = _book()
    agent = SolverAgent(registry, ONT, MockSettlement(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    from loopmarket import LoopProposal
    settlement = MockSettlement(registry, ONT, clock=lambda: NOW)
    claimed = settlement.submit(
        LoopProposal(loops[0], registry.store.root, "some-root", "s", NOW)
    )
    assert not claimed.accepted and "pin" in claimed.reason
    assert settlement.submit(
        LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    ).accepted


def test_settlement_refuses_unverifiable_oracle_types():
    # the P3 refusal gate, fabric-free: a leg naming a witness type this
    # settlement cannot verify fails closed, like U7 for vocabulary
    registry = _book(chen_oracle="photo")
    agent = SolverAgent(registry, ONT, MockSettlement(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    assert len(loops) == 1   # matching is oracle-blind; settlement is not
    from loopmarket import LoopProposal
    proposal = LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    strict = MockSettlement(registry, ONT, clock=lambda: NOW)
    receipt = strict.submit(proposal)
    assert not receipt.accepted and "oracle" in receipt.reason
    lax = MockSettlement(registry, ONT, clock=lambda: NOW,
                         verifiable_oracles={"countersign", "photo"})
    assert lax.submit(proposal).accepted


def test_snapshot_isolation():
    registry = _book()
    root, frozen = registry.snapshot()
    # new offers after the snapshot are invisible to the frozen view
    registry.publish(
        give("dora", Thing(("vegetable-box",), unit="course"), 1,
            where=GeoDisc(46.0, 14.0, 1_000), **W)
    )
    registry.commit()
    assert len(list(frozen.offers(now=NOW))) == 6
    assert len(list(registry.offers(now=NOW))) == 7
