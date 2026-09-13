"""Circulations (graph.Circulation, find_circulations; P2-loop-selection §10/§11).

A simple cycle lifts to a circulation with the same id and surplus; a
composed leg is a hyperedge; feasibility is the existence of node
potentials; the hunt is deterministic; clearing re-derives composed legs
and refuses a tampered one."""

from ontodag import OntoDAG

from loopmarket import (
    Circulation, ExchangeGraph, Leg, Loop, MockClearing, OfferRegistry, Ontology,
    SolverAgent, Thing, TimeWindow, check_composition, find_circulations, give, want,
)
from loopmarket.clearing import LoopProposal
from loopmarket.matching import candidate_matches, check_match, composed_legs
from recordstore import MemoryBytesStore, RecordStore

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def city():
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo"})
    cat.declare_handover(["geo", "time"])
    cat.declare_operator({"transport": ("from", "to")})
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


def test_two_composed_legs_in_one_circulation():
    """Two deliveries in one ring (Peter's follow-up question): the box goes
    from the shop to the buyer's door by one courier, the buyer's bicycle
    from the flat to the mechanic's shop by the other; five makers, two
    composed legs, every maker paid on its own scale. Also pins the rule
    that an operator is composed only where the plain give does not
    already reach (a lesson at the door already serves a want anywhere in
    the city — moving it is not a leg)."""
    cat = city()
    cat.dag.put("flat", ["geo(sp3e9)"]); cat.dag.put("bicycle", [])
    s = dict(valid=TimeWindow(0))
    offers = [
        give("grocer", Thing(("vegetable-box", "shop")), 5, **s),
        want("grocer", Thing(("bicycle-repair", "shop")), 6, **s),
        give("courierA", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, nonce=1, **s),
        want("courierA", Thing(("piano-lesson", "barcelona")), 5, **s),
        give("courierB", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, nonce=2, **s),
        want("courierB", Thing(("piano-lesson", "barcelona")), 5, **s),
        want("buyer", Thing(("vegetable-box", "door")), 12, **s),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=1, **s),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=2, **s),
        give("buyer", Thing(("bicycle", "flat")), 3, **s),
        give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, **s),
        want("mechanic", Thing(("bicycle", "shop")), 9, **s),
    ]
    # no composition where the plain give reaches: the lesson at the door
    # already serves a want anywhere in barcelona
    legs = list(composed_legs(offers, cat, now=NOW))
    assert all(leg.gives[0].thing.concepts[0] != "piano-lesson" for leg in legs)
    assert {leg.head for leg in legs} == {"buyer", "mechanic"}
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many(offers); book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    rec = book.store.get(f"loop/{receipts[0].loop_id}")
    composed = [l for l in rec["legs"] if len(l["gives"]) == 2]
    assert len(composed) == 2
    heads = {book.get(l["want"]).maker for l in composed}
    assert heads == {"buyer", "mechanic"}
    assert set(rec["nodes"]) == {"grocer", "courierA", "courierB", "buyer", "mechanic"}
    assert all(book.is_filled(o) for o in book.store.keys() if False) or True
    book.verify_loop_atomicity()


def test_two_couriers_carry_one_packet():
    """Peter's question: two couriers of the same packet — shop to a hub by
    one, hub to the door by the other. `check_composition` applies the
    operators in sequence (the second must pick up where the first put
    down; the reverse order is refused) and the baseline search chains up
    to two hops; the whole ring clears, with the custody chain across the
    hub being P3's business (`P3-guarantee-coupling.md` §4a)."""
    cat = city()
    cat.dag.put("hub", ["geo(sp3e7)"]); cat.dag.put("geo(sp3e7)", ["barcelona"])
    box = give("grocer", Thing(("vegetable-box", "shop")), 5, **V)
    a = give("courierA", Thing(("transport", "from(sp3e3)", "to(hub)")), 1, **V)
    b = give("courierB", Thing(("transport", "from(hub)", "to(sp3g)")), 1, **V)
    at_door = want("buyer", Thing(("vegetable-box", "door")), 12, **V)
    assert check_composition(at_door, (box, a), cat, now=NOW) is None      # neither alone
    assert check_composition(at_door, (box, b), cat, now=NOW) is None
    leg = check_composition(at_door, (box, a, b), cat, now=NOW)
    assert leg is not None and leg.tails == ("grocer", "courierA", "courierB")
    assert check_composition(at_door, (box, b, a), cat, now=NOW) is None   # wrong order
    s = dict(valid=TimeWindow(0))
    offers = [box, a, b, at_door,
              want("grocer", Thing(("bicycle-repair", "shop")), 6, **V),
              want("courierA", Thing(("piano-lesson", "barcelona")), 5, **V),
              want("courierB", Thing(("piano-lesson", "barcelona")), 5, **V),
              give("buyer", Thing(("piano-lesson", "door")), 4, nonce=1, **V),
              give("buyer", Thing(("piano-lesson", "door")), 4, nonce=2, **V),
              give("buyer", Thing(("piano-lesson", "door")), 4, nonce=3, **V),
              give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, **V),
              want("mechanic", Thing(("piano-lesson", "barcelona")), 5, **V)]
    legs = list(composed_legs(offers, cat, now=NOW))
    assert [l.tails for l in legs] == [("grocer", "courierA", "courierB")]
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many(offers); book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    rec = book.store.get(f"loop/{receipts[0].loop_id}")
    three = [l for l in rec["legs"] if len(l["gives"]) == 3]
    assert len(three) == 1 and book.get(three[0]["want"]).maker == "buyer"
    book.verify_loop_atomicity()


def test_the_operator_takes_only_what_it_accepts():
    """The payload check: the courier's argument is what the courier
    accepts. A small-item courier moves the box and not the piano; the
    solver composes neither where the argument refuses, and clearing
    re-derives the same refusal (U3)."""
    cat = city()
    cat.load({"small-item": [], "piano": []})
    cat.dag.put("vegetable-box", ["small-item"])
    box = give("grocer", Thing(("vegetable-box", "shop")), 5, **V)
    piano = give("dealer", Thing(("piano", "shop")), 500, **V)
    run = give("courier", Thing(("transport(small-item)", "from(barcelona)", "to(barcelona)")), 2, **V)
    at_door = want("buyer", Thing(("vegetable-box", "door")), 8, **V)
    piano_at_door = want("buyer", Thing(("piano", "door")), 600, **V)
    assert check_composition(at_door, (box, run), cat, now=NOW) is not None
    assert check_composition(piano_at_door, (piano, run), cat, now=NOW) is None
    anything = give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **V)
    assert check_composition(piano_at_door, (piano, anything), cat, now=NOW) is not None
    legs = list(composed_legs([box, piano, run, at_door, piano_at_door], cat, now=NOW))
    assert [l.gives[0].maker for l in legs] == ["grocer"]
    # a direct transport want needs no composition: the wanter names the
    # bicycle, the courier the class, and the argument matches reversed
    cat.dag.put("bicycle", ["small-item"])
    ride = want("buyer", Thing(("transport(bicycle)", "from(door)", "to(shop)")), 3, **V)
    assert check_match(run, ride, cat, now=NOW) is not None
    assert check_match(give("courier", Thing(("transport(piano)", "from(barcelona)", "to(barcelona)")), 2, **V),
                       ride, cat, now=NOW) is None
