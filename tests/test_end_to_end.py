"""The whole machine: publish -> snapshot-solve -> clearing, atomically."""

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    BookClearing, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)

NOW = 1_700_000_000
W = dict(valid=TimeWindow(NOW - 1, NOW + 30 * 86_400))

ONT = Ontology().load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})


def _book(chen_oracle="countersign"):
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    registry.publish_many([
        give("amara", Thing(("piano-lesson",), unit="course"), 100, **W),
        want("amara", Thing(("produce", "local", "weekly"), unit="course"), 104, **W),
        give("bruno", Thing(("vegetable-box",), unit="course"), 50, **W),
        want("bruno", Thing(("bicycle-repair",), unit="course"), 52, **W),
        give("chen", Thing(("bicycle-repair",), unit="course"), 80,
            oracle=chen_oracle, **W),
        want("chen", Thing(("music-lesson",), unit="course"), 83, **W),
    ])
    registry.commit()
    return registry


def test_triangle_clears_and_book_empties():
    registry = _book()
    agent = SolverAgent(registry, ONT, BookClearing(registry, ONT, clock=lambda: NOW))
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and receipts[0].accepted
    # the fills landed atomically under a new root
    assert list(registry.offers(now=NOW)) == []
    assert registry.store.contains(f"loop/{receipts[0].loop_id}")
    # a second solver pass finds nothing
    assert agent.step(now=NOW) == []


def test_clearing_rejects_double_spend():
    registry = _book()
    agent = SolverAgent(registry, ONT, BookClearing(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    assert len(loops) == 1
    from loopmarket import LoopProposal
    proposal = LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    clearing = BookClearing(registry, ONT, clock=lambda: NOW)
    assert clearing.submit(proposal).accepted
    second = clearing.submit(proposal)          # same loop again
    assert not second.accepted and "filled" in second.reason


def test_clearing_reverifies_against_ontology():
    registry = _book()
    agent = SolverAgent(registry, ONT, BookClearing(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    from loopmarket import LoopProposal
    # a clearing bound to a *different* catalogue must reject the loop
    hostile = Ontology().load({"unrelated": []})
    clearing = BookClearing(registry, hostile, clock=lambda: NOW)
    receipt = clearing.submit(
        LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    )
    assert not receipt.accepted and "re-verification" in receipt.reason


def test_clearing_refuses_pin_mismatch_and_absence():
    # U10's clearing rehearsal: the proposal's catalogue pin must equal
    # the clearing's own — a claimed root the verifier cannot confirm is
    # refused, and so is silence toward a pinned verifier
    registry = _book()
    agent = SolverAgent(registry, ONT, BookClearing(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    from loopmarket import LoopProposal
    clearing = BookClearing(registry, ONT, clock=lambda: NOW)
    claimed = clearing.submit(
        LoopProposal(loops[0], registry.store.root, "some-root", "s", NOW)
    )
    assert not claimed.accepted and "pin" in claimed.reason
    assert clearing.submit(
        LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    ).accepted


def test_clearing_refuses_unverifiable_oracle_types():
    # the P3 refusal gate, fabric-free: a leg naming a witness type this
    # clearing cannot verify fails closed, like U7 for vocabulary
    registry = _book(chen_oracle="photo")
    agent = SolverAgent(registry, ONT, BookClearing(registry, ONT, clock=lambda: NOW))
    _, loops = agent.find_loops(now=NOW)
    assert len(loops) == 1   # matching is oracle-blind; clearing is not
    from loopmarket import LoopProposal
    proposal = LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    strict = BookClearing(registry, ONT, clock=lambda: NOW)
    receipt = strict.submit(proposal)
    assert not receipt.accepted and "oracle" in receipt.reason
    lax = BookClearing(registry, ONT, clock=lambda: NOW,
                         verifiable_oracles={"countersign", "photo"})
    assert lax.submit(proposal).accepted


def test_snapshot_isolation():
    registry = _book()
    root, frozen = registry.snapshot()
    # new offers after the snapshot are invisible to the frozen view
    registry.publish(
        give("dora", Thing(("vegetable-box",), unit="course"), 1, **W)
    )
    registry.commit()
    assert len(list(frozen.offers(now=NOW))) == 6
    assert len(list(registry.offers(now=NOW))) == 7
