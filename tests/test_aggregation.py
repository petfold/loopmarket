"""Aggregation by quantity (P2-loop-selection.md §10, the six lifters;
built 2026-09-14): one want of one thing met by several gives of it whose
shares add up — each share within what the give may give (its step, floor
and remainder), the fill naming every give with its share, clearing
re-deriving the split exactly."""

from fractions import Fraction

from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Circulation, Leg, MockClearing, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, aggregate_legs, check_aggregate, give, want,
)
from loopmarket.clearing import LoopProposal

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def catalogue():
    return Ontology(OntoDAG()).load({"lifting": [], "lesson": [], "repair": []})


def test_six_lifters_from_three_gives():
    cat = catalogue()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    piano = want("mover", Thing(("lifting",), 6), 160, **V)              # six lifters
    gives = [give("a", Thing(("lifting",), 2), 30, **V),                  # two, indivisible
             give("b", Thing(("lifting",), 3), 45, **V),                  # three, indivisible
             give("c", Thing(("lifting",), 4, step=1), 60, **V)]          # up to four, by the person
    offers = [piano, *gives,
              give("mover", Thing(("lesson",)), 50, nonce=1, **V),
              give("mover", Thing(("lesson",)), 50, nonce=2, **V),
              give("mover", Thing(("lesson",)), 50, nonce=3, **V),
              want("a", Thing(("lesson",)), 31, **V), want("b", Thing(("lesson",)), 46, **V),
              want("c", Thing(("lesson",)), 61, **V)]                    # covers all four at 15
    legs = list(aggregate_legs(offers, cat, now=NOW))
    assert len(legs) == 1
    leg = legs[0]
    # a valid split, whichever the id order yields: shares within each give, six in all
    assert leg.quantities is not None and sum(leg.quantities) == 6 and len(leg.gives) >= 2
    for i, g in enumerate(leg.gives):
        assert g.thing.takes(leg.taken(i)) and leg.value_given(i) == g.unit_price * leg.taken(i)
    assert "@" in leg.key
    # the same search twice, and over a shuffled book, is the same leg (U6)
    assert [l.key for l in aggregate_legs(list(reversed(offers)), cat, now=NOW)] == [leg.key]
    # the split is the decision: another split is another check
    assert check_aggregate(piano, gives, (2, 3, 1), cat, now=NOW) is not None
    assert check_aggregate(piano, gives, (2, 2, 2), cat, now=NOW) is None        # b gives three or none
    assert check_aggregate(piano, gives, (2, 3, 2), cat, now=NOW) is None        # seven is not six
    assert check_aggregate(piano, gives[:2], (3, 3), cat, now=NOW) is None       # a has two
    book.publish_many(offers); book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    lid = receipts[0].loop_id
    rec = book.store.get(f"loop/{lid}")
    agg = [l for l in rec["legs"] if len(l["gives"]) >= 2][0]
    assert sum(Fraction(x) for x in agg["taken"]) == 6
    fill = book.store.get(f"fill/{piano.offer_id}")
    assert [g["offer"] for g in fill["gives"]] == agg["gives"] and \
        [g["qty"] for g in fill["gives"]] == agg["taken"]
    for gid, taken in zip(agg["gives"], agg["taken"]):
        g = book.get(gid)
        if Fraction(taken) == g.thing.qty:
            assert book.is_filled(gid) and book.store.get(f"fill/{gid}") == {"loop": lid, "qty": taken}
        else:
            assert book.store.get(f"fill/{gid}/{lid}") == {"loop": lid, "qty": taken}
            assert book.available(gid) == g.thing.qty - Fraction(taken)
    book.verify_loop_atomicity()
    # clearing refuses a tampered split
    circ = Circulation(tuple(Leg(l.want, l.gives, tuple(x + 1 for x in l.quantities)) if l.quantities else l
                             for l in _legs_of(book, rec)))                 # shares that do not add up
    receipt = MockClearing(book, cat, clock=lambda: NOW).submit(
        LoopProposal(circ, book.store.root, "", "t", NOW))
    assert not receipt.accepted


def _legs_of(book, rec):
    for l in rec["legs"]:
        gives = tuple(book.get(g) for g in l["gives"])
        quantities = tuple(Fraction(x) for x in l["taken"]) if len(gives) > 1 else None
        yield Leg(book.get(l["want"]), gives, quantities)


def test_no_aggregation_where_one_give_reaches_and_none_where_shares_cannot_add_up():
    cat = catalogue()
    one = give("a", Thing(("lifting",), 6), 90, **V)
    two = give("b", Thing(("lifting",), 4), 60, **V)
    piano = want("mover", Thing(("lifting",), 6), 120, **V)
    assert list(aggregate_legs([one, two, piano], cat, now=NOW)) == []        # `one` serves alone
    assert list(aggregate_legs([two, give("c", Thing(("lifting",), 4), 60, **V), piano], cat, now=NOW)) == []
    # a floor that cannot be met within the need
    picky = give("d", Thing(("lifting",), 10, step=1, min=5), 100, **V)
    assert list(aggregate_legs([two, picky, piano], cat, now=NOW)) == []        # 4 + (needs ≥5 of 2) fails
    found = [l for l in aggregate_legs([two, give("e", Thing(("lifting",), 3, step=1), 45, **V), piano], cat, now=NOW)]
    assert len(found) == 1 and sorted(found[0].quantities) == [2, 4]     # `two` whole, `e` makes up the six
