"""Peter's vegetable-box example (2026-09-13): where an offer holds is a bare
geo term in its conjunction — a shop, a door, a city — and handover
coordinates match when one side contains the other.

Two cases. A seller who delivers anywhere in the city serves a want at a
door inside it: the give is the wider one, and it matches. A seller at a
shop does not serve a want at a door by itself — that leg is the shop's
give composed with the courier's `transport from(barcelona) to(barcelona)`
(the operator form of `docs/plans/P2-loop-selection.md` §10), which the
circulation hunt finds and clearing re-derives (built 2026-09-13, the
same day the example was put through)."""

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
    cat.declare_operator({"transport": ("from", "to")})
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


def test_the_shop_plus_courier_leg_clears_as_a_circulation():
    """The case the example was about: the shop's box and the courier's
    run together satisfy the want at the door — one composed leg, found by
    the circulation hunt and re-derived by clearing. The ring closes
    through the grocer's repair and two lessons from the buyer, so every
    maker both gives and receives; the buyer takes part through three
    offers (one want, two gives), each used once."""
    cat = city()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    standing = dict(valid=TimeWindow(0))
    book.publish_many([
        give("grocer", Thing(("vegetable-box", "shop")), 5, **standing),
        want("grocer", Thing(("bicycle-repair", "shop")), 6, **standing),
        give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, **standing),
        want("courier", Thing(("piano-lesson", "barcelona")), 5, **standing),
        want("buyer", Thing(("vegetable-box", "door")), 8, **standing),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=1, **standing),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=2, **standing),
        give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, **standing),
        want("mechanic", Thing(("piano-lesson", "barcelona")), 5, **standing),
    ])
    book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW),
                        solver_id="t")
    receipts = agent.step()
    assert len(receipts) == 1 and receipts[0].accepted, receipts
    rec = book.store.get(f"loop/{receipts[0].loop_id}")
    composed = [leg for leg in rec["legs"] if len(leg["gives"]) == 2]
    assert len(composed) == 1
    gives = {book.get(g).maker for g in composed[0]["gives"]}
    assert gives == {"grocer", "courier"} and book.get(composed[0]["want"]).maker == "buyer"
    assert set(rec["potentials"]) == {"grocer", "courier", "buyer", "mechanic"}
    assert all(book.is_filled(oid) for oid in
               [o for leg in rec["legs"] for o in (*leg["gives"], leg["want"])])
    book.verify_loop_atomicity()                     # U11 reads composed legs
    assert agent.step() == []


def test_without_the_courier_nothing_clears():
    cat = city()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    standing = dict(valid=TimeWindow(0))
    book.publish_many([
        give("grocer", Thing(("vegetable-box", "shop")), 5, **standing),
        want("grocer", Thing(("bicycle-repair", "shop")), 6, **standing),
        want("buyer", Thing(("vegetable-box", "door")), 8, **standing),
        give("buyer", Thing(("piano-lesson", "door")), 4, **standing),
        give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, **standing),
        want("mechanic", Thing(("piano-lesson", "barcelona")), 5, **standing),
    ])
    book.commit()
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    assert agent.step() == []                        # the box stays at the shop
