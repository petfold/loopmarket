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
            bond=5.0, oracle="photo", arbitrator="arb-1", nonce=99,
            registry_version="4.1", contract_version="0.1", **W)
    assert Offer.from_record(o.to_record()) == o
    assert Offer.from_record(o.to_record()).offer_id == o.offer_id


def test_version_dispatch_fails_closed():
    o = ask("a", Thing(("x",)), 10, nonce=7, **W)
    rec = o.to_record()
    assert rec["v"] == 2
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, v=3))        # unknown future version
    with pytest.raises(ValueError):
        Offer.from_record({k: v for k, v in rec.items() if k != "v"})
    with pytest.raises(ValueError):
        ask("a", Thing(("x",)), 10, v=1, registry_version="4.1", **W)


def test_v1_records_re_encode_as_v1():
    # an offer read from an old book must reproduce its original id (U2):
    # version is identity, never silently upgraded on the way through
    v1 = ask("a", Thing(("x",)), 10, nonce=7, v=1, **W)
    rec = v1.to_record()
    assert rec["v"] == 1 and "registry_version" not in rec
    back = Offer.from_record(rec)
    assert back == v1 and back.offer_id == v1.offer_id
    v2 = ask("a", Thing(("x",)), 10, nonce=7, **W)
    assert v2.offer_id != v1.offer_id            # the bump is part of identity


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
