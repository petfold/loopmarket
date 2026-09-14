"""The v4 record (2026-09-14, decided with Peter): exact numbers as `n/d`
strings (U9), `step` and `min` on a thing in place of `divisible`, a want of
several `Parts`, fills that name every give with the quantity taken, and a
versioned loop record. v1–v3 records re-encode byte for byte (U2)."""

from fractions import Fraction

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Circulation, MockClearing, Offer, OfferRegistry, Ontology, Parts, SolverAgent,
    Thing, TimeWindow, check_match, check_parts, give, parts_legs, q, rat, want,
)
from loopmarket.matching import Leg, _gates

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def catalogue():
    cat = Ontology(OntoDAG())
    cat.load({"apple": [], "fruit": [], "sack": [], "flour": ["sack"],
              "ticket": [], "transport": [], "lesson": [], "repair": []})
    cat.dag.put("apple", ["fruit"])
    return cat


# ------------------------------------------------------------------ numbers

def test_exact_numbers_and_one_spelling():
    assert q(0.1) == Fraction(1, 10) and float(q(0.1)) == 0.1   # the decimal it prints as
    assert q("10.5") == Fraction(21, 2) == q(10.5)              # decimals are exact
    assert rat(10) == "10" and rat("10.5") == "21/2" and rat(Fraction(4, 2)) == "2"
    o = give("a", Thing(("apple",), "10.5", "kg", step="0.5"), "99.99", **V)
    rec = o.to_record()
    assert rec["v"] == 4 and rec["gives"]["qty"] == "21/2" and rec["gives"]["step"] == "1/2"
    assert rec["gives"]["min"] == "0" and rec["wants"]["amount"] == "9999/100"
    assert "divisible" not in rec["gives"]
    back = Offer.from_record(rec)
    assert back == o and back.offer_id == o.offer_id
    assert o.unit_price == Fraction(9999, 100) / Fraction(21, 2)   # exact, no float
    # the same offer typed with floats has the same id: U2 on values, not spellings
    assert give("a", Thing(("apple",), 10.5, "kg", step=0.5), 99.99, nonce=o.nonce, **V).offer_id == o.offer_id


def test_v1_to_v3_records_are_untouched():
    """A v3 offer typed today re-encodes as v3 with the same float fields —
    the same bytes, the same id (U2)."""
    o = give("a", Thing(("apple",), 2.0, "kg", divisible=True), 5, nonce=7, v=3, **V)
    rec = o.to_record()
    assert rec["v"] == 3 and rec["gives"]["qty"] == 2.0 and rec["gives"]["divisible"] is True
    assert "step" not in rec["gives"]
    assert Offer.from_record(rec).offer_id == o.offer_id
    assert o.thing.step == 0 and o.thing.takes(1) and not o.thing.takes(3)
    # a v3 form cannot say what v4 adds
    with pytest.raises(ValueError):
        give("a", Thing(("apple",), 10, step=1), 5, v=3, **V)
    with pytest.raises(ValueError):
        give("a", Thing(("apple",), 10, divisible=True, min=2), 5, v=3, **V)
    with pytest.raises(ValueError):
        want("a", Parts((Thing(("apple",)), Thing(("ticket",)))), 5, v=3, **V)


# ------------------------------------------------------------------ step, min

def test_step_replaces_the_boolean_and_matching_follows_it():
    cat = catalogue()
    apples = give("g", Thing(("apple",), 1000, step=1), 500, **V)        # whole apples
    sacks = give("g", Thing(("flour",), 100, "kg", step=25, min=50), 90, **V)   # 25 kg sacks, two at least
    whole = give("g", Thing(("ticket",), 4), 40, **V)                    # indivisible: all four
    assert apples.thing.divisible and not whole.thing.divisible
    for thing, ok, bad in ((apples, (1, 7, 1000), (Fraction(1, 2), 1001, 0)),
                           (sacks, (50, 75, 100), (25, 60, 125)),
                           (whole, (4,), (1, 2, 3, 5))):
        for n in ok:
            assert thing.thing.takes(n), (thing, n)
        for n in bad:
            assert not thing.thing.takes(n), (thing, n)
    assert check_match(apples, want("w", Thing(("fruit",), 7), 5, **V), cat, now=NOW)
    assert check_match(apples, want("w", Thing(("fruit",), "7.5"), 5, **V), cat, now=NOW) is None
    assert check_match(sacks, want("w", Thing(("sack",), 75, "kg"), 80, **V), cat, now=NOW)
    assert check_match(sacks, want("w", Thing(("sack",), 25, "kg"), 30, **V), cat, now=NOW) is None
    with pytest.raises(ValueError):
        Thing(("apple",), 10, step=3, min=4)        # the floor sits on the step
    with pytest.raises(ValueError):
        Thing(("apple",), 10, divisible=True, step=10)   # they disagree


# ------------------------------------------------------------------ parts

def test_a_composed_want_clears_as_one_leg_with_quantities_in_the_fills():
    """The theatre ticket and the transport to it: one want, two gives, one
    fill decision; the fills name which give served which part and how
    much was taken; the ring closes through lessons and a repair."""
    cat = catalogue()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    evening = want("buyer", Parts((Thing(("ticket",), 2), Thing(("transport",), 1))), 60, **V)
    offers = [
        evening,
        give("theatre", Thing(("ticket",), 10, step=1), 200, **V),      # 20 a ticket
        give("driver", Thing(("transport",)), 15, **V),
        give("buyer", Thing(("lesson",)), 30, nonce=1, **V),
        give("buyer", Thing(("lesson",)), 30, nonce=2, **V),
        want("theatre", Thing(("lesson",)), 42, **V),           # covers the two tickets (40)
        want("driver", Thing(("lesson",)), 31, **V),
    ]
    legs = list(parts_legs(offers, cat, now=NOW))
    assert len(legs) == 1 and legs[0].tails == ("theatre", "driver") and legs[0].parts
    assert legs[0].taken(0) == 2 and legs[0].taken(1) == 1
    assert legs[0].value_given(0) == 40 and legs[0].value_given(1) == 15
    assert check_match(offers[1], evening, cat, now=NOW) is None      # one give never serves parts
    assert check_parts(evening, (offers[2], offers[1]), cat, now=NOW) is None   # order is the parts'
    book.publish_many(offers); book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    rec = book.store.get(f"loop/{receipts[0].loop_id}")
    assert rec["v"] == 1 and set(rec["potentials"]) == {"buyer", "theatre", "driver"}
    composed = [l for l in rec["legs"] if len(l["gives"]) == 2][0]
    assert composed["taken"] == ["2", "1"] and "rate" not in composed
    assert all(isinstance(l.get("rate", "1"), str) for l in rec["legs"]) and isinstance(rec["surplus"], str)
    fill = book.store.get(f"fill/{evening.offer_id}")
    assert fill == {"loop": receipts[0].loop_id,
                    "gives": [{"offer": offers[1].offer_id, "qty": "2"},
                              {"offer": offers[2].offer_id, "qty": "1"}]}
    assert book.store.get(f"fill/{offers[1].offer_id}") == {"loop": receipts[0].loop_id, "qty": "2"}
    assert "price" not in str(fill) and "rate" not in str(fill)    # P4 §5 item 4: no prices in fills
    book.verify_loop_atomicity()
    assert agent.step() == []


def test_the_old_fill_shape_and_ids_alone_still_read():
    """A book written before v4 holds fills of `{"loop"}` alone; U11 and the
    registry read them, and `mark_filled` still takes bare ids."""
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    a = give("a", Thing(("x",)), 1, **V); b = want("b", Thing(("x",)), 2, **V)
    book.publish_many([a, b])
    book.mark_filled((a.offer_id, b.offer_id), "L1",
                     {"legs": [{"give": a.offer_id, "want": b.offer_id, "rate": 2.0}]})
    book.commit()
    assert book.is_filled(a.offer_id) and book.store.get(f"fill/{a.offer_id}") == {"loop": "L1"}
    book.verify_loop_atomicity()


def test_potentials_are_exact_and_agree_with_the_cycle():
    from loopmarket.matching import candidate_matches
    from loopmarket import ExchangeGraph
    cat = catalogue()
    offers = [
        give("a", Thing(("apple",), 3, step=1), 10, **V), want("a", Thing(("ticket",)), "10.4", **V),
        give("b", Thing(("ticket",)), 5, **V), want("b", Thing(("lesson",)), "5.2", **V),
        give("c", Thing(("lesson",)), 8, **V), want("c", Thing(("fruit",), 3), "8.3", **V),
    ]
    matches = list(candidate_matches(offers, cat, now=NOW))
    loop = ExchangeGraph.from_matches(matches).find_profitable_loop()
    assert isinstance(loop.surplus, Fraction) and loop.surplus == Fraction(104, 100) * Fraction(52, 50) * Fraction(83, 80) - 1
    circ = Circulation.from_loop(loop)
    e = circ.potentials()
    assert all(isinstance(x, Fraction) for x in e.values()) and circ.surplus == loop.surplus
