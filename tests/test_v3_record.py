"""The v3 offer record (docs/plans/P1-spacetime-terms.md §2, §5.5, decided
2026-09-12): where and when a thing changes hands are role terms in the
conjunction, `valid` may be open-ended, no record holds a disc, and pairs
across the v2/v3 line are refused at matching."""

import random
from datetime import datetime, timezone

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    GeoDisc, MockClearing, Offer, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)
from loopmarket.dimensions import candidate_matches_indexed
from loopmarket.matching import candidate_matches, check_match

NOW = 5_000
ROLES = {"when": "time", "where": "geo", "from": "geo", "to": "geo"}
V = dict(valid=TimeWindow(0, 1_000_000))
FIELDS = dict(service=TimeWindow(1_000, 100_000),
              where=GeoDisc(46.0, 14.0, 10_000), **V)


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def when(a, b):
    return f"when({iso(a)}..{iso(b - 1)})"


SEASON = when(1_000, 100_000)


def catalogue():
    ont = Ontology(OntoDAG())
    ont.declare_service_roles(ROLES)
    ont.load({
        "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
        "piano-lesson": ["music-lesson"], "repair": ["service"],
        "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
        "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
        "ride": [],
    })
    return ont


# ------------------------------------------------------------------ the record

def test_v3_is_the_default_record_and_carries_no_fields():
    o = give("a", Thing(("ride", "where(u2e4)", SEASON)), 5, nonce=7, **V)
    assert o.v == 3 and o.service is None and o.where is None
    rec = o.to_record()
    assert "service" not in rec and "where" not in rec and rec["v"] == 3
    back = Offer.from_record(rec)
    assert back == o and back.offer_id == o.offer_id
    with pytest.raises(ValueError):                       # the fields are v1/v2
        give("a", Thing(("ride",)), 5, service=TimeWindow(1, 2), v=3, **V)
    with pytest.raises(ValueError):                       # and v2 needs them
        give("a", Thing(("ride",)), 5, v=2, **V)
    # the field form still yields a v2 record, unchanged in every byte
    v2 = give("a", Thing(("ride",)), 5, nonce=7, **FIELDS)
    assert v2.v == 2 and Offer.from_record(v2.to_record()).offer_id == v2.offer_id


def test_v3_refuses_field_keys_and_unknown_versions():
    rec = give("a", Thing(("ride",)), 5, **V).to_record()
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, where=[46.0, 14.0, 10.0]))
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, v=4))


def test_open_ended_valid_is_a_v3_form():
    forever = TimeWindow(100)
    assert forever.open_ended and forever.is_open_at(10**12)
    assert not forever.is_open_at(99)
    assert forever.overlaps(TimeWindow(0, 101)) and not forever.overlaps(TimeWindow(0, 100))
    assert forever.contains(TimeWindow(200, 300)) and not TimeWindow(0, 500).contains(forever)
    assert forever.intersection(TimeWindow(50, 150)) == TimeWindow(100, 150)
    assert forever.intersection(TimeWindow(500)) == TimeWindow(500)
    with pytest.raises(ValueError):
        TimeWindow(5, 5)
    o = give("a", Thing(("ride",)), 5, valid=forever)
    assert o.to_record()["valid"] == [100, None]
    assert Offer.from_record(o.to_record()) == o
    with pytest.raises(ValueError):                       # v2 windows are finite
        give("a", Thing(("ride",)), 5, valid=forever,
             service=TimeWindow(1, 2), where=GeoDisc(46.0, 14.0, 10))


# ------------------------------------------------------------------- matching

def test_v3_matches_through_the_conjunction():
    ont = catalogue()
    broad = give("bruno", Thing(("ride", "where(u2e)", SEASON)), 5, **V)
    near = want("amara", Thing(("ride", "where(u2e4x)", SEASON)), 6, **V)
    assert check_match(broad, near, ont, now=NOW) is not None
    assert check_match(give("bruno", Thing(("ride", "where(u2e4x)", SEASON)), 5, **V),
                       want("amara", Thing(("ride", "where(u2e)", SEASON)), 6, **V),
                       ont, now=NOW) is not None
    assert check_match(broad, want("amara", Thing(("ride", "where(u2e5)", SEASON)), 6, **V),
                       ont, now=NOW) is not None           # u2e5 lies inside u2e
    sibling = want("amara", Thing(("ride", "where(u2e5)", SEASON)), 6, **V)
    assert check_match(give("bruno", Thing(("ride", "where(u2e4)", SEASON)), 5, **V),
                       sibling, ont, now=NOW) is None        # siblings share no cell
    late = want("amara", Thing(("ride", "where(u2e4x)", when(200_000, 300_000))), 6, **V)
    assert check_match(broad, late, ont, now=NOW) is None
    anywhere_anytime = give("bruno", Thing(("ride",)), 5, **V)
    assert check_match(anywhere_anytime, near, ont, now=NOW) is not None
    expired = want("amara", Thing(("ride",)), 6, valid=TimeWindow(0, 100))
    assert check_match(anywhere_anytime, expired, ont, now=NOW) is None
    standing = want("amara", Thing(("ride",)), 6, valid=TimeWindow(0))
    forever = give("bruno", Thing(("ride",)), 5, valid=TimeWindow(0))
    assert check_match(forever, standing, ont, now=10**10) is not None
    assert check_match(anywhere_anytime, standing, ont, now=10**10) is None  # give expired


def test_pairs_across_the_v2_v3_line_are_refused():
    ont = catalogue()
    v2_give = give("bruno", Thing(("ride",)), 5, **FIELDS)
    v3_want = want("amara", Thing(("ride",)), 6, **V)
    assert check_match(v2_give, v3_want, ont, now=NOW) is None
    assert check_match(give("bruno", Thing(("ride",)), 5, **V),
                       want("amara", Thing(("ride",)), 6, **FIELDS), ont, now=NOW) is None
    # each side still matches its own kind
    assert check_match(v2_give, want("amara", Thing(("ride",)), 6, **FIELDS), ont, now=NOW)
    assert check_match(give("bruno", Thing(("ride",)), 5, **V), v3_want, ont, now=NOW)


# --------------------------------------------------------- index and registry

CELLS = ["u2e", "u2e4", "u2e4x", "u2e5", "u2f"]


def _mixed_book(seed, n=80):
    rng = random.Random(seed)
    concepts = ["vegetable-box", "piano-lesson", "bicycle-repair", "produce",
                "service", "local", "ride"]
    offers = []
    for i in range(n):
        terms = list(rng.sample(concepts, rng.randint(1, 2)))
        side = give if rng.random() < 0.5 else want
        if rng.random() < 0.5:                       # a v3 offer: terms
            if rng.random() < 0.8:
                terms.append(f"where({rng.choice(CELLS)})")
            if rng.random() < 0.8:
                a = 1_000 + rng.randrange(0, 90_000)
                terms.append(when(a, a + rng.randrange(600, 60_000)))
            fields = dict(valid=TimeWindow(0) if rng.random() < 0.3
                          else TimeWindow(0, 1_000_000))
        else:                                        # a v2 offer: fields
            start = rng.randrange(0, 150_000)
            fields = dict(
                service=TimeWindow(start, start + rng.randrange(600, 90_000)),
                where=GeoDisc(45 + rng.random() * 2, 13 + rng.random() * 2,
                              rng.choice([2_000, 20_000, 80_000])),
                valid=TimeWindow(0, 1_000_000))
        offers.append(side(f"maker-{i}", Thing(tuple(terms), qty=1),
                           10 + rng.randrange(90), **fields))
    return offers


def test_index_is_recall_exact_on_a_mixed_version_book():
    ont = catalogue()
    total = 0
    for seed in range(5):
        offers = _mixed_book(seed)
        expected = {(m.give.offer_id, m.want.offer_id)
                    for m in candidate_matches(offers, ont, now=NOW)}
        got = {(m.give.offer_id, m.want.offer_id)
               for m in candidate_matches_indexed(offers, ont, now=NOW)}
        assert got == expected, f"drift at seed {seed}"
        assert all(  # never across the line
            (next(o for o in offers if o.offer_id == g).v >= 3)
            == (next(o for o in offers if o.offer_id == w).v >= 3)
            for g, w in got)
        total += len(got)
    assert total > 20


def test_registry_files_v3_offers_and_nothing_else():
    store = RecordStore(MemoryBytesStore())
    book = OfferRegistry(store)
    o = give("a", Thing(("ride", "where(u2e4)")), 5, valid=TimeWindow(100))
    book.publish(o)
    book.commit()
    assert [x.offer_id for x in book.offers(now=10**9)] == [o.offer_id]
    assert list(book.offers(now=50)) == []
    # no index in the book: the idx/{c,t,g} prefixes retired 2026-09-12
    assert list(store.keys()) == [f"offer/{o.offer_id}"]


# ------------------------------------------------------------------ the loop

def test_the_v3_triangle_clears():
    """The demo's triangle in the v3 form: places as cells in the
    conjunction, the season as `when`, offers standing until withdrawn."""
    ont = catalogue()
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    town = dict(valid=TimeWindow(0))
    flat, farm, shop = "where(u2e4x)", "where(u2e4)", "where(u2e4x)"
    offers = [
        give("amara", Thing(("piano-lesson", flat, SEASON), unit="course"), 100, **town),
        want("amara", Thing(("produce", "local", "weekly", flat, SEASON), unit="course"), 104, **town),
        give("bruno", Thing(("vegetable-box", farm, SEASON), unit="course"), 50, **town),
        want("bruno", Thing(("bicycle-repair", farm, SEASON), unit="course"), 52, **town),
        give("chen", Thing(("bicycle-repair", shop, SEASON), unit="course"), 80, **town),
        want("chen", Thing(("music-lesson", shop, SEASON), unit="course"), 83, **town),
    ]
    assert all(o.v == 3 for o in offers)
    registry.publish_many(offers)
    registry.commit()
    agent = SolverAgent(registry=registry, ontology=ont,
                        clearing=MockClearing(registry, ont, clock=lambda: NOW),
                        solver_id="t")
    receipts = agent.step()
    assert len(receipts) == 1 and receipts[0].accepted
    assert all(registry.is_filled(o.offer_id) for o in offers)
    assert agent.step() == []
