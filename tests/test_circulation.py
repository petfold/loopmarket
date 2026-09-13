"""Circulations (graph.Circulation, find_circulations; P2-loop-selection §10/§11).

A simple cycle lifts to a circulation with the same id and surplus; a
composed leg is a hyperedge; feasibility is the existence of node
potentials; the hunt is deterministic; clearing re-derives composed legs
and refuses a tampered one."""

from ontodag import OntoDAG

from loopmarket import (
    Circulation, ExchangeGraph, Leg, Loop, MockClearing, OfferRegistry, Ontology,
    Thing, TimeWindow, check_composition, find_circulations, give, want,
)
from loopmarket.clearing import LoopProposal
from loopmarket.matching import candidate_matches, composed_legs
from recordstore import MemoryBytesStore, RecordStore

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def city():
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo"})
    cat.declare_handover(["geo", "time"])
    cat.declare_operator({"geo": ("from", "to")})
    cat.load({"vegetable-box": [], "transport": [], "bicycle-repair": [],
              "piano-lesson": [], "g1": [], "g2": [], "g3": []})
    cat.dag.put("barcelona", ["geo"])
    cat.dag.put("geo(sp3e)", ["barcelona"]); cat.dag.put("geo(sp3g)", ["barcelona"])
    cat.dag.put("shop", ["geo(sp3e3)"]); cat.dag.put("door", ["geo(sp3g7)"])
    return cat


def triangle():
    return [
        give("a", Thing(("g1",)), 100, **V), want("a", Thing(("g3",)), 104, **V),
        give("b", Thing(("g2",)), 50, **V), want("b", Thing(("g1",)), 52, **V),
        give("c", Thing(("g3",)), 80, **V), want("c", Thing(("g2",)), 83, **V),
    ]


def delivery_book():
    s = dict(valid=TimeWindow(0))
    return [
        give("grocer", Thing(("vegetable-box", "shop")), 5, **s),
        want("grocer", Thing(("bicycle-repair", "shop")), 6, **s),
        give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **s),
        want("courier", Thing(("piano-lesson", "barcelona")), 5, **s),
        want("buyer", Thing(("vegetable-box", "door")), 8, **s),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=1, **s),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=2, **s),
        give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, **s),
        want("mechanic", Thing(("piano-lesson", "barcelona")), 5, **s),
    ]


def test_a_cycle_lifts_to_a_circulation_with_the_same_id_and_surplus():
    cat = city()
    matches = list(candidate_matches(triangle(), cat, now=NOW))
    loop = ExchangeGraph.from_matches(matches).find_profitable_loop()
    circ = Circulation.from_loop(loop)
    assert circ.loop_id == loop.loop_id and circ.surplus == loop.surplus
    assert circ.as_loop() is not None and circ.simple and circ.per_node_ok
    assert circ.potentials() is not None
    # the same cycle found by the circulation hunt over the same legs
    found = find_circulations([Leg.from_match(m) for m in matches])
    assert len(found) == 1 and found[0].loop_id == loop.loop_id
    assert abs(found[0].surplus - loop.surplus) < 1e-9


def test_check_composition_moves_the_thing_along_the_operator():
    cat = city()
    box = give("grocer", Thing(("vegetable-box", "shop")), 5, **V)
    run = give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **V)
    at_door = want("buyer", Thing(("vegetable-box", "door")), 8, **V)
    leg = check_composition(at_door, (box, run), cat, now=NOW)
    assert leg is not None and leg.tails == ("grocer", "courier") and not leg.simple
    # the operator must be able to pick the thing up where it is...
    far = give("courier", Thing(("transport", "from(u2e)", "to(barcelona)")), 2, **V)
    assert check_composition(at_door, (box, far), cat, now=NOW) is None
    # ...and put it down where the want is
    short = give("courier", Thing(("transport", "from(barcelona)", "to(geo(sp3e))")), 2, **V)
    assert check_composition(at_door, (box, short), cat, now=NOW) is None
    # a give that moves nothing is not an operator; the thing alone does not reach
    assert check_composition(at_door, (box, give("x", Thing(("transport",)), 2, **V)), cat, now=NOW) is None
    assert check_composition(at_door, (box,), cat, now=NOW) is None
    # the buyer's own give cannot be a part
    assert check_composition(at_door, (box, give("buyer", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **V)), cat, now=NOW) is None
    assert [leg.key for leg in composed_legs([box, run, at_door], cat, now=NOW)] == [leg.key]


def test_the_hunt_finds_the_composed_circulation_deterministically():
    cat = city()
    offers = delivery_book()
    legs = [Leg.from_match(m) for m in candidate_matches(offers, cat, now=NOW)] + \
        list(composed_legs(offers, cat, now=NOW))
    first = find_circulations(legs)
    second = find_circulations(list(reversed(legs)))
    assert len(first) == 1 and first[0].loop_id == second[0].loop_id
    circ = first[0]
    assert not circ.simple and circ.as_loop() is None
    assert set(circ.nodes) == {"grocer", "courier", "buyer", "mechanic"}
    assert circ.feasible and circ.surplus > 0 and circ.per_node_ok
    e = circ.potentials()
    for leg in circ.legs:                             # the potentials do balance every leg
        assert leg.want.unit_price * e[leg.head] >= \
            sum(g.unit_price * e[g.maker] for g in leg.gives) - 1e-9
    assert min(e.values()) == 1.0


def test_infeasible_prices_have_no_potentials():
    """The buyer offers less than the box and the run cost together: the
    hunt finds nothing, and the balanced set built by hand has no node
    potentials and a negative surplus."""
    cat = city()
    s = dict(valid=TimeWindow(0))
    offers = delivery_book()
    offers[4] = want("buyer", Thing(("vegetable-box", "door")), 3, **s)
    legs = [Leg.from_match(m) for m in candidate_matches(offers, cat, now=NOW)] + \
        list(composed_legs(offers, cat, now=NOW))
    assert find_circulations(legs) == []
    by = {(l.head, tuple(l.tails)): l for l in legs}
    circ = Circulation((
        by[("buyer", ("grocer", "courier"))],
        by[("grocer", ("mechanic",))],
        next(l for l in legs if l.head == "courier"),
        next(l for l in legs if l.head == "mechanic"
             and l.gives[0].offer_id != next(x for x in legs if x.head == "courier").gives[0].offer_id),
    ))
    assert circ.potentials() is None and circ.surplus < 0


def test_clearing_re_derives_a_composed_leg():
    cat = city()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = delivery_book()
    book.publish_many(offers); book.commit()
    legs = [Leg.from_match(m) for m in candidate_matches(offers, cat, now=NOW)] + \
        list(composed_legs(offers, cat, now=NOW))
    circ = find_circulations(legs)[0]
    clearing = MockClearing(book, cat, clock=lambda: NOW)
    # a tampered composed leg: the solver claims the courier moved the box
    # but names a courier who only runs elsewhere — refused on re-derivation
    elsewhere = give("courier", Thing(("transport", "from(u2e)", "to(u2e)")), 2, valid=TimeWindow(0))
    book.publish(elsewhere); book.commit()
    bad_legs = tuple(Leg(l.want, (l.gives[0], elsewhere)) if not l.simple else l for l in circ.legs)
    receipt = clearing.submit(LoopProposal(Circulation(bad_legs), book.store.root, "", "t", NOW))
    assert not receipt.accepted and "re-verification" in receipt.reason
    good = clearing.submit(LoopProposal(circ, book.store.root, "", "t", NOW))
    assert good.accepted
    rec = book.store.get(f"loop/{good.loop_id}")
    assert "potentials" in rec and any(len(l["gives"]) == 2 for l in rec["legs"])
    book.verify_loop_atomicity()
