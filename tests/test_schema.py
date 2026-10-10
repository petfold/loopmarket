"""Offer form invariants: uniformity, canonicity, content addressing."""

import pytest

from loopmarket.schema import Offer, Thing, TimeWindow, Tokens, give, want

W = dict(valid=TimeWindow(0, 10_000))


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
    a = give("a", Thing(("x",), qty=4, divisible=True), 100, **W)
    b = want("b", Thing(("x",), qty=2, divisible=True), 60, **W)
    assert a.kind == "give" and b.kind == "want"
    assert a.unit_price == 25 and b.unit_price == 30


def test_content_address_is_canonical_and_sensitive():
    a1 = give("a", Thing(("y", "x")), 10, nonce=7, **W)   # concept order...
    a2 = give("a", Thing(("x", "y")), 10, nonce=7, **W)   # ...never matters
    assert a1.offer_id == a2.offer_id
    a3 = give("a", Thing(("x", "y")), 11, nonce=7, **W)   # content always does
    assert a3.offer_id != a1.offer_id


def test_record_roundtrip():
    o = want("m", Thing(("p", "q"), qty=3, unit="kg", divisible=True), 42,
            bond=5.0, oracle="photo", arbitrator="arb-1", nonce=99,
            registry_version="4.1", contract_version="0.1", **W)
    assert Offer.from_record(o.to_record()) == o
    assert Offer.from_record(o.to_record()).offer_id == o.offer_id


def test_version_dispatch_fails_closed():
    o = give("a", Thing(("x",)), 10, nonce=7, **W)
    rec = o.to_record()
    assert rec["v"] == 4
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, v=8))        # unknown future version
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, v=5))        # a v5 record carries requires
    with pytest.raises(ValueError):
        Offer.from_record({k: v for k, v in rec.items() if k != "v"})
    with pytest.raises(ValueError):              # a field this version does not define
        Offer.from_record(dict(rec, service=[1_000, 2_000]))


def test_v1_records_re_encode_as_v1(golden):
    # an offer read from an old book must reproduce its original id (U2):
    # version is identity, never silently upgraded on the way through
    rec = next(r for k, r in golden.items() if k.startswith("offer/") and r["v"] == 1)
    assert "registry_version" not in rec
    v1 = Offer.from_record(rec)
    assert v1.v == 1 and v1.to_record() == rec
    v2 = Offer.from_record(dict(rec, v=2, registry_version="", contract_version=""))
    assert v2.offer_id != v1.offer_id            # the bump is part of identity


def test_time_windows_fit_within():
    assert TimeWindow(0, 100).contains(TimeWindow(10, 90))
    assert not TimeWindow(0, 100).contains(TimeWindow(10, 101))
    assert TimeWindow(0, 100).overlaps(TimeWindow(99, 200))
    assert not TimeWindow(0, 100).overlaps(TimeWindow(100, 200))



def test_a_record_number_can_neither_stall_nor_crash_the_reader():
    """Records are untrusted input. `q` read `"1e10000000"` by computing
    10**10000000 (12 s, and each further digit of the exponent costs at
    least ten times more), and let `"1/0"` escape as ZeroDivisionError,
    which the fold's admission rules do not catch (both found 2026-10-09
    by fuzzing `Offer.from_record`). The bomb here is finite, so that a
    regression fails the timing check rather than hanging the suite."""
    import time
    from fractions import Fraction

    from loopmarket.schema import q
    for text in ("1/0", "1e10000000", "1e-10000000"):
        started = time.perf_counter()
        with pytest.raises(ValueError):
            q(text)
        assert time.perf_counter() - started < 1
    assert q("1e3") == 1000 and q("21/2") == Fraction(21, 2) and q("10.5") == Fraction(21, 2)


def test_no_mutated_record_escapes_the_admission_errors(golden):
    """The fold rejects a single record when reading it raises ValueError,
    KeyError, TypeError or AttributeError; anything else rejects the whole
    book. A seeded mutator of real records found two escapes on
    2026-10-09, both numbers (`"1/0"`, `"1e10000000"`); this keeps the
    count at none. A v2 record is among them: old records are read for
    good."""
    import copy
    import random

    now = 1_700_000_000
    valid = TimeWindow(now - 1, now + 86_400)
    records = [next(r for k, r in golden.items() if k.startswith("offer/") and r["v"] == 2)] + \
        [o.to_record() for o in (
            give("amara", Thing(("piano-lesson", "time(2026-10)"), unit="course"), 100,
                 nonce=2, valid=valid),
            want("bruno", Thing(("vegetable-box",), unit="course"), 52, nonce=4, valid=valid))]
    garbage = [None, 0, -1, 10**40, 1.5, float("nan"), "", "xxx", [], {}, [1, 2],
               {"a": 1}, True, "1/0", "-5", "1e10000000", "1e-10000000", "9" * 5000]

    def paths(value, prefix=()):
        items = value.items() if isinstance(value, dict) else \
            enumerate(value) if isinstance(value, list) else ()
        for key, child in items:
            yield prefix + (key,)
            yield from paths(child, prefix + (key,))

    rng = random.Random(1)
    for _ in range(3000):
        rec = copy.deepcopy(rng.choice(records))
        for _ in range(rng.choice((1, 1, 2))):
            path = rng.choice(list(paths(rec)))
            parent = rec
            for key in path[:-1]:
                parent = parent[key]
            if rng.random() < 0.2 and isinstance(parent, dict):
                del parent[path[-1]]
            else:
                parent[path[-1]] = copy.deepcopy(rng.choice(garbage))
        try:
            offer = Offer.from_record(rec)
            offer.offer_id, offer.unit_price
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
