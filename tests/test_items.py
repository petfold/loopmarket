"""Items (I1–I2, 2026-09-29; `docs/plans/items-and-ownership.md` §1–§2).
I1: `item(h)` with h derived from a natural identifier — the same VIN
yields the same h however it is spelled — or a tagger's record; a want
naming an item takes only that item, and an item term that is not a whole
id matches nothing (the prefix-kind stopgap's guard). I2: the per-item rule,
per maker (plan D5): one open claim per (maker, item) — the second of two
offers by one maker on one item is refused while the first is open and
admissible after; two makers on one item both clear, whoever cannot deliver
being a non-performance."""

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.items import land_register_id, serial_id, tagged_id, term, vin_id, well_formed
from loopmarket.matching import check_match

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_item_heads()
    cat.load({"car": [], "vehicle": [], "lesson": [], "painting": []})
    return cat


def test_the_same_identifier_yields_the_same_item_and_only_that_item_matches():
    h = vin_id("1HGCM82633A004352")
    assert vin_id("1hg-cm826 33a004352") == h and len(h) == 64
    with pytest.raises(ValueError):
        vin_id("1HGCM82633A00435O")                  # an O is not a VIN character
    assert land_register_id("si", "1234 5678") == land_register_id("SI", "12345678")
    assert serial_id("Omega", "abc123") == serial_id("omega ", "ABC123")
    assert tagged_id("fp", "tagger-1") != tagged_id("fp", "tagger-2")         # an attested identity
    cat = _cat()
    other = vin_id("1HGCM82633A004353")
    car = give("s", Thing(("car", term(h)), 1, "car"), 50, **V)
    assert check_match(car, want("b", Thing(("car", term(h)), 1, "car"), 100, **V), cat, now=NOW) is not None
    assert check_match(car, want("b", Thing(("car", term(other)), 1, "car"), 100, **V), cat, now=NOW) is None
    assert check_match(car, want("b", Thing(("car",), 1, "car"), 100, **V), cat, now=NOW) is not None
    assert check_match(give("s", Thing(("car",), 1, "car"), 50, **V),
                       want("b", Thing(("car", term(h)), 1, "car"), 100, **V), cat, now=NOW) is None
    # a shortened id matches nothing: refused as malformed, and on the
    # identifier kind (K1) the catalogue itself puts no other item below it
    short = f"item({h[:8]})"
    assert not well_formed(("car", short)) and well_formed(("car", term(h)))
    assert check_match(car, want("b", Thing(("car", short), 1, "car"), 100, **V), cat, now=NOW) is None
    from ontodag import dimensions as dims
    if hasattr(dims, "KIND_IDENTIFIER"):
        assert cat.head_kind("item") == dims.KIND_IDENTIFIER
        assert not cat.dag.is_below(term(h), short) and cat.dag.is_below(term(h), term(h))


def _loop(book, seller, buyer, h, nonce, price=50, valid=V):
    """A two-maker cycle selling the car for a lesson."""
    offers = [give(seller, Thing(("car", term(h)), 1, "car"), price, **valid, nonce=nonce),
              want(buyer, Thing(("car", term(h)), 1, "car"), 100, **V, nonce=nonce + 1),
              give(buyer, Thing(("lesson",), 1, "hour"), 5, **V, nonce=nonce + 2),
              want(seller, Thing(("lesson",), 1, "hour"), 80, **V, nonce=nonce + 3)]
    book.publish_many(offers)
    book.commit()
    return offers


def _step(book, now):
    cat = _cat()
    return SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: now), solver_id="t").step(now=now)


def test_one_open_claim_per_maker_and_item():
    h = vin_id("1HGCM82633A004352")
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    first = _loop(book, "seller", "b1", h, 1, valid=dict(valid=TimeWindow(0, NOW + 100)))
    (r,) = _step(book, NOW)
    assert r.accepted
    [(loop, claim)] = book.item_claims(h, "seller")
    assert loop == r.loop_id and claim == {"offer": first[0].offer_id, "until": NOW + 100}
    # the same seller offers the same car again: refused while the first sale is open
    second = _loop(book, "seller", "b2", h, 10)
    assert _step(book, NOW + 50) == []
    # and admissible once the first claim has run out
    (r2,) = _step(book, NOW + 101)
    assert r2.accepted and book.is_filled(second[0].offer_id)
    book.verify_loop_atomicity()


def test_two_makers_on_one_item_both_clear():
    """The owner and a broker both offer the car; the rule is per maker, so
    both sales clear, and whichever cannot deliver is a non-performance
    covered by its deposit (plan D5: a rule across makers was a free
    denial-of-sale attack)."""
    h = vin_id("1HGCM82633A004352")
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    _loop(book, "owner", "b1", h, 1)
    _loop(book, "broker", "b2", h, 10)
    receipts = _step(book, NOW)
    assert [r.accepted for r in receipts] == [True, True]
    assert book.item_claims(h, "owner") and book.item_claims(h, "broker")


def test_an_option_on_an_item_claims_it_until_the_window_ends():
    """The option is the maker's open claim on the car (plan D5: one active
    option record or open fill per maker and item): its hold writes the
    claim until the exercise window ends, and the seller's second offer of
    the same car is refused meanwhile."""
    h = vin_id("1HGCM82633A004352")
    cat = _cat()
    cat.declare_graph_heads(["option"])
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    p = give("seller", Thing(("car", term(h)), 1, "car"), 50, **V, nonce=1)
    o = give("seller", Thing((f"option(car {term(h)})",), 1, "car"), 5, **V, nonce=2, underlying=p.offer_id,
             exercise=TimeWindow(NOW + 10, NOW + 500))
    book.publish_many([p, o, want("holder", Thing(("option(car)",), 1, "car"), 12, **V, nonce=3),
                       give("holder", Thing(("lesson",), 1, "hour"), 5, **V, nonce=4),
                       want("seller", Thing(("lesson",), 1, "hour"), 80, **V, nonce=5)])
    book.commit()
    (r,) = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t").step(now=NOW)
    assert r.accepted
    assert book.item_claims(h, "seller") == [(r.loop_id, {"offer": p.offer_id, "until": NOW + 500})]
    again = give("seller", Thing(("car", term(h)), 1, "car"), 40, **V, nonce=6)
    book.publish(again)
    book.commit()
    from loopmarket.gate import CounterpartyGate
    gate = CounterpartyGate.over(book, {}, now=NOW + 20)
    assert gate.item_fault(again).startswith("seller already holds an open claim on item")
    assert CounterpartyGate.over(book, {}, now=NOW + 501).item_fault(again) == ""
