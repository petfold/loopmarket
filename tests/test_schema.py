"""Offer form invariants: uniformity, canonicity, content addressing."""

import pytest

from loopmarket.schema import GeoDisc, Offer, Thing, TimeWindow, Tokens, ask, bid

W = dict(
    service=TimeWindow(1_000, 2_000),
    where=GeoDisc(46.0, 14.0, 1_000),
    valid=TimeWindow(0, 10_000),
)


def test_uniform_form_enforced():
    # two Thing sides
    with pytest.raises(ValueError):
        Offer(maker="a", gives=Thing(("x",)), wants=Thing(("y",)), **W)
    # two Tokens sides
    with pytest.raises(ValueError):
        Offer(maker="a", gives=Tokens("a", 1), wants=Tokens("a", 2), **W)
    # token side must be the maker's own token
    with pytest.raises(ValueError):
        Offer(maker="a", gives=Thing(("x",)), wants=Tokens("b", 1), **W)


def test_kind_and_unit_price():
    a = ask("a", Thing(("x",), qty=4, divisible=True), 100, **W)
    b = bid("b", Thing(("x",), qty=2, divisible=True), 60, **W)
    assert a.kind == "ask" and b.kind == "bid"
    assert a.unit_price == 25 and b.unit_price == 30


def test_content_address_is_canonical_and_sensitive():
    a1 = ask("a", Thing(("y", "x")), 10, nonce=7, **W)   # concept order...
    a2 = ask("a", Thing(("x", "y")), 10, nonce=7, **W)   # ...never matters
    assert a1.offer_id == a2.offer_id
    a3 = ask("a", Thing(("x", "y")), 11, nonce=7, **W)   # content always does
    assert a3.offer_id != a1.offer_id


def test_record_roundtrip():
    o = bid("m", Thing(("p", "q"), qty=3, unit="kg", divisible=True), 42,
            bond=5.0, oracle="photo", arbitrator="arb-1", nonce=99, **W)
    assert Offer.from_record(o.to_record()) == o
    assert Offer.from_record(o.to_record()).offer_id == o.offer_id


def test_time_and_geo_fits_within():
    assert TimeWindow(0, 100).contains(TimeWindow(10, 90))
    assert not TimeWindow(0, 100).contains(TimeWindow(10, 101))
    assert TimeWindow(0, 100).overlaps(TimeWindow(99, 200))
    assert not TimeWindow(0, 100).overlaps(TimeWindow(100, 200))
    big, small = GeoDisc(46.0, 14.0, 10_000), GeoDisc(46.01, 14.01, 500)
    assert big.contains(small) and not small.contains(big)
    assert big.intersects(small)
    far = GeoDisc(48.0, 16.0, 1_000)
    assert not big.intersects(far)
