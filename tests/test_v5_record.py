"""The v5 record: admissibility by declaration (decided by Peter 2026-09-18,
`docs/plans/P2-loop-selection.md` §4a). A maker declares what it requires
of any counterparty — a bond floor, the witness types it accepts — and
matching refuses a leg that does not meet it, fail closed (U7); the
maker's own `bond` becomes an exact rational (U9). v4 records re-encode
byte for byte; a requirement is a v5 form."""

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, Offer, OfferRegistry, Ontology, Requires, SolverAgent, Thing, TimeWindow, give, want,
)
from loopmarket.clearing import LoopProposal
from loopmarket.graph import Loop
from loopmarket.matching import Match, candidate_matches, check_aggregate, check_match, check_parts

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def _cat():
    return Ontology(OntoDAG()).load({"apple": [], "lesson": [], "repair": [], "ticket": [], "transport": []})


def test_the_v5_record_round_trips_and_a_requirement_is_a_v5_form():
    o = give("a", Thing(("apple",), 3), 9, **V, bond="3/4",
             requires=Requires(bond="1/2", oracles=("locker", "countersign")))
    assert o.v == 5 and o.bond == 3 / 4 and o.requires.oracles == ("countersign", "locker")
    rec = o.to_record()
    assert rec["v"] == 5 and rec["bond"] == "3/4"
    assert rec["requires"] == {"bond": "1/2", "oracles": ["countersign", "locker"]}
    back = Offer.from_record(rec)
    assert back == o and back.offer_id == o.offer_id
    # a v5 offer without a stated requirement carries an empty one, so the record is complete
    plain5 = give("a", Thing(("apple",), 3), 9, **V, v=5)
    assert plain5.requires == Requires() and plain5.requires.empty and plain5.to_record()["bond"] == "0"
    # v4 is untouched: no requires key, the float bond, the same bytes as before
    o4 = give("a", Thing(("apple",), 3), 9, **V, nonce=7)
    assert o4.v == 4 and "requires" not in o4.to_record() and o4.to_record()["bond"] == 0.0
    assert Offer.from_record(o4.to_record()).offer_id == o4.offer_id
    with pytest.raises(ValueError, match="v5 form"):
        give("a", Thing(("apple",), 3), 9, **V, requires=Requires(bond=1), v=4)
    with pytest.raises(ValueError, match="v5 form"):
        Offer.from_record(dict(o4.to_record(), requires={"bond": "0", "oracles": []}))
    with pytest.raises(ValueError, match="carries requires"):
        Offer.from_record({k: v for k, v in rec.items() if k != "requires"})
    with pytest.raises(ValueError, match="unknown offer record version"):
        Offer.from_record(dict(rec, v=6))
    with pytest.raises(ValueError, match="non-negative"):
        Requires(bond=-1)


def test_matching_refuses_a_leg_that_fails_either_sides_requirement():
    cat = _cat()
    demanding = want("b", Thing(("apple",), 3), 12, **V, requires=Requires(bond=1))
    poor = give("a", Thing(("apple",), 3), 9, **V, bond="1/2", v=5)
    rich = give("a", Thing(("apple",), 3), 9, **V, bond=2, v=5)
    legacy = give("a", Thing(("apple",), 3), 9, **V)                    # v4: no rational bond, so none
    assert check_match(poor, demanding, cat, now=NOW) is None
    assert check_match(legacy, demanding, cat, now=NOW) is None
    assert check_match(rich, demanding, cat, now=NOW) is not None
    # the give may require too; the want's declaration is what it is judged by
    fussy = give("a", Thing(("apple",), 3), 9, **V, bond=2, requires=Requires(oracles=("locker",)))
    assert check_match(fussy, demanding, cat, now=NOW) is None           # the want settles by countersign
    lockered = want("b", Thing(("apple",), 3), 12, **V, oracle="locker", bond=1, requires=Requires(bond=1))
    assert check_match(fussy, lockered, cat, now=NOW) is not None
    # an empty requirement accepts anyone; a v5 offer against v4 offers matches as before
    assert check_match(legacy, want("b", Thing(("apple",), 3), 12, **V, v=5), cat, now=NOW) is not None
    # composed wants and aggregated legs are gated give by give
    evening = want("b", Thing(("ticket",), 2), 60, **V, requires=Requires(bond=1))
    assert check_aggregate(evening, [give("t1", Thing(("ticket",), 1), 20, **V, bond=1, v=5),
                                     give("t2", Thing(("ticket",), 1), 20, **V, bond=0, v=5)],
                           [1, 1], cat, now=NOW) is None
    assert check_aggregate(evening, [give("t1", Thing(("ticket",), 1), 20, **V, bond=1, v=5),
                                     give("t2", Thing(("ticket",), 1), 20, **V, bond=1, v=5)],
                           [1, 1], cat, now=NOW) is not None
    from loopmarket import Parts
    night = want("b", Parts((Thing(("ticket",), 2), Thing(("transport",), 1, "run"))), 60, **V,
                 requires=Requires(bond=1))
    theatre = give("th", Thing(("ticket",), 10, step=1), 200, **V, bond=1, v=5)
    driver = give("dr", Thing(("transport",), 1, "run"), 15, **V, bond="1/4", v=5)
    assert check_parts(night, (theatre, driver), cat, now=NOW) is None
    assert check_parts(night, (theatre, give("dr", Thing(("transport",), 1, "run"), 15, **V, bond=1, v=5)),
                       cat, now=NOW) is not None


def test_the_solver_never_proposes_an_inadmissible_loop_and_clearing_refuses_one():
    """b requires a bond of 1 from whoever serves it. The richer loop runs
    through an under-bonded seller: it is not a candidate at all; the bonded
    seller's loop clears. A proposal built by hand through the under-bonded
    seller is refused by the checklist."""
    cat = _cat()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [want("b", Thing(("apple",), 3), 15, **V, bond=1, requires=Requires(bond=1)),
              give("cheap", Thing(("apple",), 3), 9, **V, bond=0, v=5),           # rate 1.67, unbonded
              give("bonded", Thing(("apple",), 3), 12, **V, bond=1, v=5),         # rate 1.25
              give("b", Thing(("lesson",)), 10, **V, bond=1, v=5),
              want("cheap", Thing(("lesson",)), 11, **V, v=5),
              want("bonded", Thing(("lesson",)), 13, **V, v=5)]              # covers the 12 it is owed
    book.publish_many(offers); book.commit()
    matches = list(candidate_matches(offers, cat, now=NOW))
    assert not any(m.give.maker == "cheap" and m.want.maker == "b" for m in matches)
    agent = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True]
    assert book.is_filled(offers[2].offer_id) and not book.is_filled(offers[1].offer_id)
    forged = Loop((Match(give=offers[1], want=offers[0]), Match(give=offers[3], want=offers[4])))
    verdict = MockClearing(book, cat, clock=lambda: NOW).rehearse(
        LoopProposal(forged, book.store.root, cat.root, "t", NOW))
    assert not verdict.accepted and "already filled" in verdict.reason or "fails re-verification" in verdict.reason
