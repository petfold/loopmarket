"""The dimension-backed candidate generator (loopmarket.dimensions).

The load-bearing assertion is RECALL: over randomized books, the indexed
generator must yield exactly the matches of the exact give x want baseline —
this is the benchmark ARCHITECTURE.md §6 demands of smarter generators.
The second assertion is that it actually prunes (fewer exact checks than
the full product), so it cannot silently degenerate into the baseline."""

import random

from loopmarket import GeoDisc, Ontology, Thing, TimeWindow, give, want
from loopmarket.dimensions import (
    DimensionIndex, candidate_matches_indexed, time_term,
)
from loopmarket.matching import candidate_matches

NOW = 5_000
CATALOGUE = {
    "produce": [], "local": [], "weekly": [], "service": [],
    "vegetable-box": ["produce", "local", "weekly"],
    "fruit-box": ["produce", "local"],
    "piano-lesson": ["service"],
    "bike-repair": ["service", "local"],
}


def fresh_ontology():
    return Ontology().load(dict(CATALOGUE))


def wide(**kw):
    base = dict(service=TimeWindow(1_000, 100_000),
                where=GeoDisc(46.0, 14.0, 10_000),
                valid=TimeWindow(0, 1_000_000))
    base.update(kw)
    return base


class TestTimeTerm:
    def test_half_open_to_inclusive(self):
        term = time_term(TimeWindow(0, 86_400))
        assert term == "service-time(1970-01-01T00:00:00Z..1970-01-01T23:59:59Z)"


class TestCandidates:
    def test_courier_style_pruning(self):
        ontology = fresh_ontology()
        a1 = give("bruno", Thing(("vegetable-box",)), 50, **wide())
        a2 = give("chiara", Thing(("piano-lesson",)), 30, **wide())
        late = wide(service=TimeWindow(200_000, 300_000))
        a3 = give("dora", Thing(("vegetable-box",)), 40, **late)
        b = want("amara", Thing(("produce", "weekly")), 104, **wide())

        index = DimensionIndex(ontology)
        for a in (a1, a2, a3):
            assert index.file(a)
        cands = index.candidates(b)
        assert a1.offer_id in cands
        assert a2.offer_id not in cands          # wrong concept cone
        assert a3.offer_id not in cands          # disjoint service window

    def test_unknown_vocabulary_not_filed(self):
        index = DimensionIndex(fresh_ontology())
        stranger = give("x", Thing(("mystery-goods",)), 1, **wide())
        assert not index.file(stranger)
        assert stranger.offer_id not in index._filed

    def test_shared_catalogue_untouched(self):
        ontology = fresh_ontology()
        before = {(p.name, c.name) for p in ontology.dag.nodes.values()
                  for c in p.neighbors}
        index = DimensionIndex(ontology)
        index.file(give("bruno", Thing(("vegetable-box",)), 50, **wide()))
        after = {(p.name, c.name) for p in ontology.dag.nodes.values()
                 for c in p.neighbors}
        assert before == after   # derived index: pins stay stable


class TestRecallAgainstBaseline:
    def _random_book(self, seed, n=60):
        rng = random.Random(seed)
        concepts = ["vegetable-box", "fruit-box", "piano-lesson",
                    "bike-repair", "produce", "service", "local"]
        offers = []
        for i in range(n):
            maker = f"maker-{i}"
            thing = Thing(tuple(rng.sample(concepts, rng.randint(1, 2))),
                          qty=rng.choice([1, 2, 4]),
                          divisible=rng.random() < 0.5)
            start = rng.randrange(0, 150_000)
            window = dict(
                service=TimeWindow(start, start + rng.randrange(600, 90_000)),
                where=GeoDisc(45 + rng.random() * 2, 13 + rng.random() * 2,
                              rng.choice([2_000, 20_000, 80_000])),
                valid=TimeWindow(0, 1_000_000),
            )
            side = give if rng.random() < 0.5 else want
            offers.append(side(maker, thing, 10 + rng.randrange(90),
                               **window))
        return offers

    def test_exactly_the_baseline_matches(self):
        ontology = fresh_ontology()
        for seed in range(5):
            offers = self._random_book(seed)
            expected = {(m.give.offer_id, m.want.offer_id)
                        for m in candidate_matches(offers, ontology, now=NOW)}
            got = {(m.give.offer_id, m.want.offer_id)
                   for m in candidate_matches_indexed(
                       offers, ontology, now=NOW)}
            assert got == expected, f"recall/precision drift at seed {seed}"

    def test_it_actually_prunes(self):
        ontology = fresh_ontology()
        offers = self._random_book(1)
        gives = [o for o in offers if o.kind == "give"]
        wants = [o for o in offers if o.kind == "want"]
        index = DimensionIndex(ontology)
        filed = [a for a in gives if index.file(a)]
        checked = sum(len(index.candidates(b)) for b in wants)
        assert checked < len(filed) * len(wants) * 0.8, \
            "the index is not pruning against the full product"


# ------------------------------------------------------------- service roles
# Step 4 of docs/plans/P1-spacetime-terms.md: the index files a give under
# whatever role terms it carries and asks overlap per role head the want
# names — so place prunes, through cells, the truth for role terms.

ROLES = {"from": "geo", "to": "geo", "depart": "time"}
CELLS = ["u2e", "u2e4", "u2e4x", "u2e4xq", "u2e5", "u2f"]


def roles_ontology():
    ont = fresh_ontology()
    ont.declare_service_roles(ROLES)
    ont.dag.put("made_in", ["geo"])           # descriptive: containment
    return ont


class TestRoleTerms:
    def _random_book(self, seed, n=80):
        rng = random.Random(seed)
        concepts = ["vegetable-box", "fruit-box", "piano-lesson",
                    "bike-repair", "produce", "service", "local"]

        def cal(t):
            return _iso(t)

        offers = []
        for i in range(n):
            terms = list(rng.sample(concepts, rng.randint(1, 2)))
            for head in ("from", "to"):
                if rng.random() < 0.7:
                    terms.append(f"{head}({rng.choice(CELLS)})")
                    if rng.random() < 0.15:          # two same-head terms
                        terms.append(f"{head}({rng.choice(CELLS)})")
            if rng.random() < 0.5:
                a = 1_800_000_000 + rng.randrange(0, 3600)
                terms.append(f"depart({cal(a)}..{cal(a + rng.randrange(60, 3600))})")
            if rng.random() < 0.3:
                terms.append(f"made_in({rng.choice(CELLS)})")
            thing = Thing(tuple(terms), qty=rng.choice([1, 2]),
                          divisible=rng.random() < 0.5)
            side = give if rng.random() < 0.5 else want
            offers.append(side(f"maker-{i}", thing, 10 + rng.randrange(90),
                               **wide()))
        return offers

    def test_exactly_the_baseline_matches_with_role_terms(self):
        ontology = roles_ontology()
        seen_matches = 0
        for seed in range(6):
            offers = self._random_book(seed)
            expected = {(m.give.offer_id, m.want.offer_id)
                        for m in candidate_matches(offers, ontology, now=NOW)}
            got = {(m.give.offer_id, m.want.offer_id)
                   for m in candidate_matches_indexed(offers, ontology, now=NOW)}
            assert got == expected, f"recall/precision drift at seed {seed}"
            seen_matches += len(expected)
        assert seen_matches > 20                    # the books are not trivial

    def test_place_prunes_and_silence_is_unconstrained(self):
        ontology = roles_ontology()
        near = give("bruno", Thing(("vegetable-box", "from(u2e4)")), 50, **wide())
        far = give("chiara", Thing(("vegetable-box", "from(u2f)")), 50, **wide())
        anywhere = give("dora", Thing(("vegetable-box",)), 50, **wide())
        b = want("amara", Thing(("produce", "from(u2e4x)")), 104, **wide())
        index = DimensionIndex(ontology)
        for a in (near, far, anywhere):
            assert index.file(a)
        cands = index.candidates(b)
        assert near.offer_id in cands and anywhere.offer_id in cands
        assert far.offer_id not in cands            # sibling cell: pruned
        # a want silent on `from` takes every give
        assert len(index.candidates(
            want("amara", Thing(("produce",)), 104, **wide()))) == 3
        # a provably empty want, or an uninterpretable one, matches nothing
        assert index.candidates(want("amara", Thing(
            ("produce", "from(u2e4)", "from(u2e5)")), 104, **wide())) == set()
        assert index.candidates(want("amara", Thing(
            ("produce", "depart(garbage)")), 104, **wide())) == set()
        assert not index.file(give("e", Thing(("produce", "depart(garbage)")), 1, **wide()))


def _iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
