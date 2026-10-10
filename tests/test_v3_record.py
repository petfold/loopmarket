"""The v3 offer record (docs/plans/P1-spacetime-terms.md §2, §5.5, decided
2026-09-12): where and when a thing changes hands are role terms in the
conjunction, `valid` may be open-ended, and no record holds a disc. The
v1/v2 offers that did are retired (tests/test_v1_v2_retired.py)."""

import random
from datetime import datetime, timezone

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    BookClearing, Offer, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)
from loopmarket.dimensions import candidate_matches_indexed
from loopmarket.matching import candidate_matches, check_match

NOW = 5_000
ROLES = {"from": "geo", "to": "geo"}
V = dict(valid=TimeWindow(0, 1_000_000))


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def time(a, b):
    return f"time({iso(a)}..{iso(b - 1)})"


SEASON = time(1_000, 100_000)


def catalogue():
    ont = Ontology(OntoDAG())
    ont.declare_roles(ROLES)
    ont.declare_handover(["geo", "time"])
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
    """v3 was the default record 2026-09-12 to 2026-09-14; since v4 it is
    asked for with `v=3` and re-encodes byte for byte (U2)."""
    assert give("a", Thing(("ride",)), 5, **V).v == 4
    o = give("a", Thing(("ride", "geo(u2e4)", SEASON)), 5, nonce=7, v=3, **V)
    assert o.v == 3 and o.service is None and o.where is None
    rec = o.to_record()
    assert "service" not in rec and "where" not in rec and rec["v"] == 3
    back = Offer.from_record(rec)
    assert back == o and back.offer_id == o.offer_id
    with pytest.raises(ValueError):                       # the fields are v1/v2
        give("a", Thing(("ride",)), 5, service=TimeWindow(1, 2), v=3, **V)


def test_v3_refuses_field_keys_and_unknown_versions():
    rec = give("a", Thing(("ride",)), 5, v=3, **V).to_record()
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, where=[46.0, 14.0, 10.0]))
    with pytest.raises(ValueError):
        Offer.from_record(dict(rec, v=5))
    with pytest.raises(ValueError):                       # a v3 thing is not a v4 one
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


# ------------------------------------------------------------------- matching

def test_v3_matches_through_the_conjunction():
    """Place and time are bare terms, and handover coordinates match when
    one contains the other: the ride serving all of `u2e` serves the want
    at `u2e4x`, and the ride at `u2e4x` serves a want anywhere in `u2e`."""
    ont = catalogue()
    broad = give("bruno", Thing(("ride", "geo(u2e)", SEASON)), 5, **V)
    near = want("amara", Thing(("ride", "geo(u2e4x)", SEASON)), 6, **V)
    assert check_match(broad, near, ont, now=NOW) is not None  # the give is wider
    assert check_match(give("bruno", Thing(("ride", "geo(u2e4x)", SEASON)), 5, **V),
                       want("amara", Thing(("ride", "geo(u2e)", SEASON)), 6, **V),
                       ont, now=NOW) is not None               # u2e4x lies inside u2e
    sibling = want("amara", Thing(("ride", "geo(u2e5)", SEASON)), 6, **V)
    assert check_match(give("bruno", Thing(("ride", "geo(u2e4)", SEASON)), 5, **V),
                       sibling, ont, now=NOW) is None          # siblings share no cell
    at_cell = give("bruno", Thing(("ride", "geo(u2e4x)", SEASON)), 5, **V)
    late = want("amara", Thing(("ride", "geo(u2e4x)", time(200_000, 300_000))), 6, **V)
    assert check_match(at_cell, late, ont, now=NOW) is None    # the season is not inside
    slot = give("bruno", Thing(("ride", "geo(u2e4x)", time(2_000, 3_000))), 5, **V)
    assert check_match(slot, near, ont, now=NOW) is not None   # a slot inside the season
    silent = give("bruno", Thing(("ride",)), 5, **V)
    assert check_match(silent, near, ont, now=NOW) is None     # says nothing about where/when
    dont_care = want("amara", Thing(("ride",)), 6, **V)
    assert check_match(at_cell, dont_care, ont, now=NOW) is not None
    expired = want("amara", Thing(("ride",)), 6, valid=TimeWindow(0, 100))
    assert check_match(silent, expired, ont, now=NOW) is None
    standing = want("amara", Thing(("ride",)), 6, valid=TimeWindow(0))
    forever = give("bruno", Thing(("ride",)), 5, valid=TimeWindow(0))
    assert check_match(forever, standing, ont, now=10**10) is not None
    assert check_match(silent, standing, ont, now=10**10) is None  # give expired


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
        if rng.random() < 0.8:
            terms.append(f"geo({rng.choice(CELLS)})")
        if rng.random() < 0.8:
            a = 1_000 + rng.randrange(0, 90_000)
            terms.append(time(a, a + rng.randrange(600, 60_000)))
        fields = dict(valid=TimeWindow(0) if rng.random() < 0.3 else TimeWindow(0, 1_000_000),
                      v=3 if rng.random() < 0.5 else 4)
        offers.append(side(f"maker-{i}", Thing(tuple(terms), qty=1),
                           10 + rng.randrange(90), **fields))
    return offers


def test_index_is_recall_exact_on_a_mixed_version_book():
    """v3 and v4 offers in one book: the index finds the baseline's
    matches, across the two versions too."""
    ont = catalogue()
    total = across = 0
    for seed in range(5):
        offers = _mixed_book(seed)
        version = {o.offer_id: o.v for o in offers}
        expected = {(m.give.offer_id, m.want.offer_id)
                    for m in candidate_matches(offers, ont, now=NOW)}
        got = {(m.give.offer_id, m.want.offer_id)
               for m in candidate_matches_indexed(offers, ont, now=NOW)}
        assert got == expected, f"drift at seed {seed}"
        total += len(got)
        across += sum(version[g] != version[w] for g, w in got)
    assert total > 20 and across > 0


def test_registry_files_v3_offers_and_nothing_else():
    store = RecordStore(MemoryBytesStore())
    book = OfferRegistry(store)
    o = give("a", Thing(("ride", "geo(u2e4)")), 5, valid=TimeWindow(100))
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
    town = dict(valid=TimeWindow(0), v=3)
    # each give hands over inside the cell the receiving want names: the
    # want is the wider cone (bruno takes his repair anywhere in u2e4)
    flat, shop, area = "geo(u2e4x)", "geo(u2e4x)", "geo(u2e4)"
    offers = [
        give("amara", Thing(("piano-lesson", flat, SEASON), unit="course"), 100, **town),
        want("amara", Thing(("produce", "local", "weekly", flat, SEASON), unit="course"), 104, **town),
        give("bruno", Thing(("vegetable-box", flat, SEASON), unit="course"), 50, **town),
        want("bruno", Thing(("bicycle-repair", area, SEASON), unit="course"), 52, **town),
        give("chen", Thing(("bicycle-repair", shop, SEASON), unit="course"), 80, **town),
        want("chen", Thing(("music-lesson", flat, SEASON), unit="course"), 83, **town),
    ]
    assert all(o.v == 3 for o in offers)
    registry.publish_many(offers)
    registry.commit()
    agent = SolverAgent(registry=registry, ontology=ont,
                        clearing=BookClearing(registry, ont, clock=lambda: NOW),
                        solver_id="t")
    receipts = agent.step()
    assert len(receipts) == 1 and receipts[0].accepted
    assert all(registry.is_filled(o.offer_id) for o in offers)
    assert agent.step() == []
