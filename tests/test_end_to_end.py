"""The whole machine: publish -> snapshot-solve -> clearing, atomically."""

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    GeoDisc, BookClearing, OfferRegistry, Ontology, SolverAgent, Thing,
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


def _book(chen_oracle="countersign", pins=None):
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    a_flat = GeoDisc(46.05, 14.50, 5_000)
    b_farm = GeoDisc(46.10, 14.55, 15_000)
    c_shop = GeoDisc(46.06, 14.51, 4_000)
    P = pins or {}
    registry.publish_many([
        give("amara", Thing(("piano-lesson",), unit="course"), 100, where=a_flat, **W, **P),
        want("amara", Thing(("produce", "local", "weekly"), unit="course"), 104,
            where=a_flat, **W, **P),
        give("bruno", Thing(("vegetable-box",), unit="course"), 50, where=b_farm, **W, **P),
        want("bruno", Thing(("bicycle-repair",), unit="course"), 52, where=b_farm, **W, **P),
        give("chen", Thing(("bicycle-repair",), unit="course"), 80, where=c_shop,
            oracle=chen_oracle, **W, **P),
        want("chen", Thing(("music-lesson",), unit="course"), 83, where=c_shop, **W, **P),
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


@pytest.mark.parametrize("which", ["registry", "contract"])
def test_an_upgraded_node_refuses_offers_pinned_to_the_old_major(which, monkeypatch):
    """Review item 4 (decided by Peter 2026-10-10): clearing's step 0
    refuses an offer whose registry or contract major differs from the
    ontodag it runs on, as matching does, and the refusal names both
    majors and says to re-post. Here the offers pin the installed versions,
    a loop is found, and then the node upgrades to the next major: the loop
    is refused, nothing is filled, the six offers still sit in their book,
    and the upgraded node's own solver pairs none of them."""
    import ontodag
    from ontodag import dimensions
    from loopmarket import LoopProposal
    from loopmarket.matching import major
    pins = dict(ontology_root="", registry_version=dimensions.REGISTRY_VERSION,
                contract_version=ontodag.CONTRACT_VERSION)
    registry = _book(pins=pins)
    _, loops = SolverAgent(registry, ONT, None).find_loops(now=NOW)
    assert len(loops) == 1
    proposal = LoopProposal(loops[0], registry.store.root, "", "s", NOW)
    module, attr = (dimensions, "REGISTRY_VERSION") if which == "registry" else (ontodag, "CONTRACT_VERSION")
    old = int(major(getattr(module, attr)))
    monkeypatch.setattr(module, attr, f"{old + 1}.0")
    receipt = BookClearing(registry, ONT, clock=lambda: NOW).submit(proposal)
    assert not receipt.accepted
    assert f"{which} major {old}" in receipt.reason and f"major {old + 1}" in receipt.reason
    assert "re-post" in receipt.reason
    assert len(list(registry.offers(now=NOW))) == 6
    assert SolverAgent(registry, ONT, None).find_loops(now=NOW)[1] == []


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
