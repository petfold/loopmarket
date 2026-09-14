"""Partial fills of a divisible give (2026-09-14, the v4 sequence's second
step): a fill takes exactly the want's quantity, the remainder stays open
for the next loop, the fills of one give are keyed per loop and may not sum
past its quantity (U11 checks it at the fold), a remainder below the floor
or the step is dust and exhausts the offer, and the CLI shows what is left.
The stepped clearing regime is therefore exact: no rounding, ever."""

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, PartialLoopError, SolverAgent, Thing,
    TimeWindow, check_match, give, q, want,
)

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def catalogue():
    return Ontology(OntoDAG()).load({"apple": [], "lesson": [], "repair": [], "ride": []})


def test_two_loops_share_one_divisible_give():
    """100 kg of apples, divisible: a 40 kg ring clears first, the 60 kg ring
    second, from what is left; the give is filled only when nothing
    takeable remains."""
    cat = catalogue()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    apples = give("farm", Thing(("apple",), 100, "kg", divisible=True), 200, **V)   # 2/kg
    ring1 = [want("b1", Thing(("apple",), 40, "kg"), 90, **V), give("b1", Thing(("lesson",)), 80, **V),
             want("farm", Thing(("lesson",)), 85, nonce=1, **V)]
    book.publish_many([apples, *ring1]); book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    lid1 = receipts[0].loop_id
    assert book.taken(apples.offer_id) == 40 and book.available(apples.offer_id) == 60
    assert not book.is_filled(apples.offer_id) and book.loops_of(apples.offer_id) == [lid1]
    assert book.store.get(f"fill/{apples.offer_id}/{lid1}") == {"loop": lid1, "qty": "40"}
    assert not book.store.contains(f"fill/{apples.offer_id}")
    rec = book.store.get(f"loop/{lid1}")
    assert [l["taken"] for l in rec["legs"] if l["give"] == apples.offer_id] == [["40"]]
    assert [o.offer_id for o in book.offers(now=NOW)] == [apples.offer_id]   # still open
    # the solver sees what is left: a 70 kg want cannot be served now
    too_much = want("b2", Thing(("apple",), 70, "kg"), 150, **V)
    assert check_match(apples, too_much, cat, now=NOW) is not None           # the whole offer would
    assert check_match(apples, too_much, cat, now=NOW, available=book.availability([apples])) is None
    ring2 = [want("b2", Thing(("apple",), 60, "kg"), 130, **V), give("b2", Thing(("repair",)), 100, **V),
             want("farm", Thing(("repair",)), 125, nonce=2, **V)]   # covers 60 kg at 2/kg
    book.publish_many(ring2); book.commit()
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    lid2 = receipts[0].loop_id
    assert book.taken(apples.offer_id) == 100 and book.available(apples.offer_id) == 0
    assert book.is_filled(apples.offer_id) and book.loops_of(apples.offer_id) == sorted([lid1, lid2])
    book.verify_loop_atomicity()
    assert agent.step(now=NOW) == []


def test_dust_exhausts_a_stepped_give_and_the_floor_holds():
    cat = catalogue()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    sacks = give("mill", Thing(("apple",), 100, "kg", step=25, min=50), 90, **V)
    offers = [sacks, want("b", Thing(("apple",), 75, "kg"), 80, **V),
              give("b", Thing(("lesson",)), 70, **V), want("mill", Thing(("lesson",)), 75, **V)]
    book.publish_many(offers); book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    assert [r.accepted for r in agent.step(now=NOW)] == [True]
    assert book.available(sacks.offer_id) == 25          # one sack left...
    assert book.is_filled(sacks.offer_id)                # ...below the 50 kg floor: dust
    assert sacks.offer_id not in {o.offer_id for o in book.offers(now=NOW)}
    # a remainder above the floor but not a full step is dust too
    loose = Thing(("apple",), 100, "kg", step=30)
    assert loose.exhausted(10) and not loose.exhausted(30) and loose.takes(30, 40) and not loose.takes(60, 40)


def test_oversold_and_double_filled_gives_are_caught_at_the_fold():
    cat = catalogue()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    apples = give("farm", Thing(("apple",), 100, "kg", divisible=True), 200, **V)
    book.publish(apples)
    book.mark_filled({f"{apples.offer_id}/L1": {"loop": "L1", "qty": "70"}, "w1": {"loop": "L1"}}, "L1",
                     {"legs": [{"give": apples.offer_id, "gives": [apples.offer_id], "want": "w1"}]})
    book.mark_filled({f"{apples.offer_id}/L2": {"loop": "L2", "qty": "40"}, "w2": {"loop": "L2"}}, "L2",
                     {"legs": [{"give": apples.offer_id, "gives": [apples.offer_id], "want": "w2"}]})
    with pytest.raises(PartialLoopError, match="oversold"):
        book.verify_loop_atomicity()
    other = OfferRegistry(RecordStore(MemoryBytesStore()))
    other.publish(apples)
    other.mark_filled({f"{apples.offer_id}/L1": {"loop": "L1", "qty": "70"}, "w1": {"loop": "L1"}}, "L1",
                      {"legs": [{"give": apples.offer_id, "gives": [apples.offer_id], "want": "w1"}]})
    other.mark_filled({apples.offer_id: {"loop": "L3", "qty": "100"}, "w3": {"loop": "L3"}}, "L3",
                      {"legs": [{"give": apples.offer_id, "gives": [apples.offer_id], "want": "w3"}]})
    with pytest.raises(PartialLoopError, match="whole and in part"):
        other.verify_loop_atomicity()
