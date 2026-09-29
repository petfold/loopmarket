"""Argument-only operators and `requires.legs` (D4, 2026-09-29; the full
plan's D4, `options-and-cover.md` §4.1): `insure` and `inspect` are
operators declared by their argument alone — they attach to a thing and
move nothing — and a want that requires such legs is met only by a leg
composing the thing's give with an operator give under each named category,
whose argument accepts the thing, from a giver the entry accepts, never a
party to the leg. The gate: an inspection and cover compose with the car;
an unaccepted inspector, a missing leg, cover that does not take the thing,
or an inspector who is the seller each refuse; the solver composes it and
the circulation clears."""

from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Accept, MockClearing, OfferRegistry, Ontology, RequiredLeg, Requires, SolverAgent, Thing, TimeWindow, give,
    want,
)
from loopmarket.escrow import cover_predicate
from loopmarket.matching import check_composition, check_match, composed_legs

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
BUYER, SELLER, INSPECTOR, INSURER = "buyer", "seller", "inspector", "insurer"


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_argument_operator(["insure", "inspect"])
    cat.load({"vehicle": [], "car": ["vehicle"], "bicycle": ["vehicle"], "lesson": [], "painting": [], "photo": []})
    return cat


def _offers(inspector=INSPECTOR, cover="insure(car)"):
    buyer_wants = want(BUYER, Thing(("car",), 1, "car"), 100, **V, nonce=1, requires=Requires(legs=(
        RequiredLeg("inspect", Accept(keys=(INSPECTOR,))), RequiredLeg("insure", Accept(keys=(INSURER,))))))
    return {
        "want": buyer_wants,
        "car": give(SELLER, Thing(("car",), 1, "car"), 50, **V, nonce=2),
        "inspect": give(inspector, Thing(("inspect(vehicle)",), 1, "report"), 10, **V, nonce=3),
        "insure": give(INSURER, Thing((cover,), 1, "policy"), 10, **V, nonce=4),
    }


def test_an_inspection_and_cover_compose_with_the_thing():
    cat = _cat()
    o = _offers()
    leg = check_composition(o["want"], (o["car"], o["inspect"], o["insure"]), cat, now=NOW)
    assert leg is not None and [g.maker for g in leg.gives] == [SELLER, INSPECTOR, INSURER]
    assert check_match(o["car"], o["want"], cat, now=NOW) is None                    # the car alone is not enough
    assert check_composition(o["want"], (o["car"], o["inspect"]), cat, now=NOW) is None  # no cover leg
    assert cat.argument_only("insure") and not cat.argument_only("car")
    assert cover_predicate(cat)(o["insure"]) and not cover_predicate(cat)(o["car"])


def test_an_unaccepted_or_partial_inspector_and_unfit_cover_refuse():
    cat = _cat()
    stranger = _offers(inspector="someone")
    assert check_composition(stranger["want"], (stranger["car"], stranger["inspect"], stranger["insure"]),
                             cat, now=NOW) is None
    bikes_only = _offers(cover="insure(bicycle)")
    assert check_composition(bikes_only["want"], (bikes_only["car"], bikes_only["inspect"], bikes_only["insure"]),
                             cat, now=NOW) is None
    # the seller inspecting its own car: a party, whatever the acceptance says
    o = _offers()
    self_inspecting = give(SELLER, Thing(("inspect(vehicle)",), 1, "report"), 10, **V, nonce=5)
    picky = want(BUYER, Thing(("car",), 1, "car"), 100, **V, nonce=6, requires=Requires(legs=(
        RequiredLeg("inspect", Accept(keys=(SELLER,))),)))
    assert check_composition(picky, (o["car"], self_inspecting), cat, now=NOW) is None


def test_the_solver_composes_the_legs_and_the_circulation_clears():
    cat = _cat()
    o = _offers()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    returns = [give(BUYER, Thing(("lesson",), 1, "hour"), 5, **V, nonce=10),
               want(SELLER, Thing(("lesson",), 1, "hour"), 60, **V, nonce=11),
               give(BUYER, Thing(("painting",), 1, "piece"), 5, **V, nonce=12),
               want(INSPECTOR, Thing(("painting",), 1, "piece"), 12, **V, nonce=13),
               give(BUYER, Thing(("photo",), 1, "print"), 5, **V, nonce=14),
               want(INSURER, Thing(("photo",), 1, "print"), 12, **V, nonce=15)]
    book.publish_many([*o.values(), *returns])
    book.commit()
    legs = list(composed_legs(book.offers(), cat, now=NOW))
    assert any([g.maker for g in leg.gives] == [SELLER, INSPECTOR, INSURER] for leg in legs)
    receipts = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t").step(now=NOW)
    assert [r.accepted for r in receipts] == [True]
    for key in ("want", "car", "inspect", "insure"):
        assert book.is_filled(o[key].offer_id)


def test_an_inspector_is_no_party_to_the_item_anywhere_in_the_loop():
    """E2 (2026-09-29 night): an inspection give is admissible only if its
    giver is neither maker nor wanter on any leg of the loop naming the
    item it inspects — its own leg's included. A dealer chain: A sells car
    h to B, B sells it on to C with an inspection; A inspecting is refused
    (a previous owner of the very car), a stranger passes, and a leg on
    another item does not taint the inspector."""
    from loopmarket.items import vin_id
    from loopmarket.matching import Leg, independence_faults
    cat = _cat()
    cat.declare_item_heads()
    h = vin_id("WVWZZZ1JZXW000001")
    other = vin_id("WVWZZZ1JZXW000002")
    car = lambda maker, n, item=h: give(maker, Thing(("car", f"item({item})"), 1, "car"), 50, **V, nonce=n)
    wants = lambda maker, n, item=h: want(maker, Thing(("car", f"item({item})"), 1, "car"), 90, **V, nonce=n)
    inspection = lambda maker, n: give(maker, Thing(("inspect(vehicle)",), 1, "report"), 10, **V, nonce=n)
    first = Leg(wants("B", 1), (car("A", 2),))                                # A sells h to B
    by_a = Leg(wants("C", 3), (car("B", 4), inspection("A", 5)))              # B sells it on, A inspects
    assert independence_faults((first, by_a), cat) == [f"the inspector A is a party to a leg on item {h[:12]}"]
    by_stranger = Leg(wants("C", 3), (car("B", 4), inspection("X", 6)))
    assert independence_faults((first, by_stranger), cat) == []
    elsewhere = Leg(wants("B", 7, other), (car("A", 8, other),))            # A's trade in another car
    assert independence_faults((elsewhere, by_a), cat) == []
    # the own leg: the seller, or the buyer, inspecting
    assert "its own leg" in independence_faults((Leg(wants("C", 3), (car("B", 4), inspection("B", 9))),), cat)[0]
    assert "its own leg" in independence_faults((Leg(wants("C", 3), (car("B", 4), inspection("C", 9))),), cat)[0]
    # a catalogue with no `inspect` has no inspections to check
    plain = Ontology(OntoDAG()).load({"car": [], "vehicle": []})
    assert independence_faults((first, by_a), plain) == []
