"""Peter's vegetable-box example (2026-09-13): where an offer holds is a bare
geo term in its conjunction — a shop, a door, a city — and handover
coordinates match when one side contains the other.

Two cases. A seller who delivers anywhere in the city serves a want at a
door inside it: the give is the wider one, and it matches. A seller at a
shop does not serve a want at a door — that leg needs the courier who says
`transport from(barcelona) to(barcelona)`, and composing the shop's give
with the courier's into one leg is the solver-side operator form of
`docs/plans/P2-loop-selection.md` §10, not built: today's solver hunts
simple cycles of single gives, so the case yields no loop and is pinned
here as the gap."""

from ontodag import OntoDAG

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow,
    give, want,
)
from loopmarket.matching import check_match
from recordstore import MemoryBytesStore, RecordStore

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def city():
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo"})
    cat.declare_handover(["geo", "time"])
    cat.load({"vegetable-box": [], "transport": [], "bicycle-repair": [],
              "piano-lesson": []})
    cat.dag.put("barcelona", ["geo"])                # a region above its cells
    cat.dag.put("geo(sp3e)", ["barcelona"])
    cat.dag.put("geo(sp3g)", ["barcelona"])
    cat.dag.put("shop", ["geo(sp3e3)"])              # places under cells
    cat.dag.put("door", ["geo(sp3g7)"])
    return cat


def test_a_city_wide_seller_serves_a_want_at_the_door():
    cat = city()
    delivers = give("grocer", Thing(("vegetable-box", "barcelona")), 5, **V)
    at_door = want("buyer", Thing(("vegetable-box", "door")), 6, **V)
    assert check_match(delivers, at_door, cat, now=NOW) is not None
    # ...and a seller at a fixed shop serves a buyer who collects anywhere
    at_shop = give("grocer", Thing(("vegetable-box", "shop")), 5, **V)
    collects = want("buyer", Thing(("vegetable-box", "barcelona")), 6, **V)
    assert check_match(at_shop, collects, cat, now=NOW) is not None
    # but the shop does not come to the door
    assert check_match(at_shop, at_door, cat, now=NOW) is None
    # and a give that says nothing about place does not serve a placed want
    nowhere = give("grocer", Thing(("vegetable-box",)), 5, **V)
    assert check_match(nowhere, at_door, cat, now=NOW) is None
    assert check_match(at_shop, want("buyer", Thing(("vegetable-box",)), 6, **V),
                       cat, now=NOW) is not None      # a want silent on place


def test_the_courier_matches_a_transport_want_either_way():
    cat = city()
    courier = give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **V)
    run = want("buyer", Thing(("transport", "from(shop)", "to(door)")), 3, **V)
    assert check_match(courier, run, cat, now=NOW) is not None     # the give is wider
    fixed = give("courier", Thing(("transport", "from(shop)", "to(door)")), 2, **V)
    any_run = want("buyer", Thing(("transport", "from(barcelona)", "to(barcelona)")), 3, **V)
    assert check_match(fixed, any_run, cat, now=NOW) is not None   # the want is wider
    elsewhere = want("buyer", Thing(("transport", "from(shop)", "to(u2e4)")), 3, **V)
    assert check_match(courier, elsewhere, cat, now=NOW) is None   # u2e4 is not in the city
    # roles are never confused: a `to` answers a `to`
    assert check_match(give("c", Thing(("transport", "from(barcelona)")), 2, **V),
                       want("b", Thing(("transport", "to(door)")), 3, **V), cat, now=NOW) is None


def test_the_shop_plus_courier_leg_is_not_composed_yet():
    """The gap this example pins: the shop's box and the courier's run
    together satisfy the want at the door, but the P0 solver matches one
    give to one want and finds no loop. Solver-side composition is P2."""
    cat = city()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    standing = dict(valid=TimeWindow(0))
    book.publish_many([
        give("grocer", Thing(("vegetable-box", "shop")), 5, **standing),
        want("grocer", Thing(("bicycle-repair", "shop")), 6, **standing),
        give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **standing),
        want("courier", Thing(("piano-lesson", "barcelona")), 3, **standing),
        give("buyer", Thing(("piano-lesson", "door")), 4, **standing),
        want("buyer", Thing(("vegetable-box", "door")), 7, **standing),
        give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, **standing),
        want("mechanic", Thing(("transport", "from(barcelona)", "to(barcelona)")), 8, **standing),
    ])
    book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW),
                        solver_id="t")
    assert agent.step() == []                        # no simple cycle: the box is at the shop
    # the city-wide seller closes it: the same book with one more give
    book.publish(give("grocer2", Thing(("vegetable-box", "barcelona")), 5, **standing))
    book.publish(want("grocer2", Thing(("bicycle-repair", "barcelona")), 6, **standing))
    book.commit()
    receipts = agent.step()
    assert len(receipts) == 1 and receipts[0].accepted
