"""The dimension-backed candidate generator (loopmarket.dimensions).

The load-bearing assertion is RECALL: over randomized books, the indexed
generator must yield exactly the matches of the exact give x want baseline —
this is the benchmark ARCHITECTURE.md §6 demands of smarter generators.
The second assertion is that it actually prunes (fewer exact checks than
the full product), so it cannot silently degenerate into the baseline."""

import random

import pytest

from loopmarket import GeoDisc, Ontology, Thing, TimeWindow, give, want
from loopmarket.dimensions import DimensionIndex, candidate_matches_indexed
from loopmarket.matching import candidate_matches, check_match

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
        # a v1/v2 window is a field, not a term: the exact check gates it
        assert a3.offer_id in cands
        assert check_match(a3, b, ontology, now=NOW) is None

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


# ------------------------------------------------------------- role terms
# Place and time are query terms like categories (Peter, 2026-09-12): the
# index files a give under whatever terms it carries and a want's candidates
# are the gives inside every wanted cone — one `get`, no set arithmetic.

ROLES = {"from": "geo", "to": "geo", "depart": "time"}
CELLS = ["u2e", "u2e4", "u2e4x", "u2e4xq", "u2e5", "u2f"]
# nodes a role term may name since ontodag #15: a place under a cell, a
# floor under the place, a region above two cells (a lower bound, §14)
PLACES = ["my_home", "my_home_4th", "ljubljana"]


def roles_ontology():
    ont = fresh_ontology()
    ont.declare_roles(ROLES)
    ont.dag.put("made_in", ["geo"])           # descriptive: containment
    ont.dag.put("my_home", ["geo(u2e4x)"])
    ont.dag.put("my_home_4th", ["my_home"])
    ont.dag.put("ljubljana", ["geo"])
    ont.dag.put("geo(u2e4)", ["ljubljana"])
    ont.dag.put("geo(u2e5)", ["ljubljana"])
    return ont


class TestRoleTerms:
    def _random_book(self, seed, n=80, places=()):
        rng = random.Random(seed)
        concepts = ["vegetable-box", "fruit-box", "piano-lesson",
                    "bike-repair", "produce", "service", "local"]
        params = CELLS + list(places)

        def cal(t):
            return _iso(t)

        offers = []
        for i in range(n):
            terms = list(rng.sample(concepts, rng.randint(1, 2)))
            for head in ("from", "to"):
                if rng.random() < 0.7:
                    terms.append(f"{head}({rng.choice(params)})")
                    if rng.random() < 0.15:          # two same-head terms
                        terms.append(f"{head}({rng.choice(params)})")
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
        for seed in range(4):
            offers = self._random_book(seed, n=60)
            expected = {(m.give.offer_id, m.want.offer_id)
                        for m in candidate_matches(offers, ontology, now=NOW)}
            got = {(m.give.offer_id, m.want.offer_id)
                   for m in candidate_matches_indexed(offers, ontology, now=NOW)}
            assert got == expected, f"recall/precision drift at seed {seed}"
            seen_matches += len(expected)
        assert seen_matches > 20                    # the books are not trivial

    def test_exactly_the_baseline_matches_with_names(self):
        """Places, a floor and a region as role parameters (ontodag #15),
        decided by the graph on both paths. One smaller book: every
        overlap decision that meets the whole-space region walks its
        covering, so a names book files and queries in seconds, not
        milliseconds (the cost note in `ontodag-coupling.md` §7)."""
        ontology = roles_ontology()
        offers = self._random_book(7, n=50, places=PLACES)
        baseline = list(candidate_matches(offers, ontology, now=NOW))
        expected = {(m.give.offer_id, m.want.offer_id) for m in baseline}
        got = {(m.give.offer_id, m.want.offer_id)
               for m in candidate_matches_indexed(offers, ontology, now=NOW)}
        assert got == expected
        assert any("my_home" in c or "ljubljana" in c for m in baseline
                   for c in m.give.thing.concepts + m.want.thing.concepts)

    def test_place_prunes_by_containment(self):
        ontology = roles_ontology()
        inside = give("bruno", Thing(("vegetable-box", "from(u2e4x)")), 50, **wide())
        wider = give("chiara", Thing(("vegetable-box", "from(u2e)")), 50, **wide())
        far = give("dora", Thing(("vegetable-box", "from(u2f)")), 50, **wide())
        silent = give("erin", Thing(("vegetable-box",)), 50, **wide())
        index = DimensionIndex(ontology)
        for a in (inside, wider, far, silent):
            assert index.file(a)
        b = want("amara", Thing(("produce", "from(u2e4)")), 104, **wide())
        assert index.candidates(b) == {inside.offer_id}    # the narrower give
        # a want silent on `from` takes every give
        assert len(index.candidates(
            want("amara", Thing(("produce",)), 104, **wide()))) == 4
        # a provably empty want, or an uninterpretable one, matches nothing
        assert index.candidates(want("amara", Thing(
            ("produce", "from(u2e4)", "from(u2e5)")), 104, **wide())) == set()
        assert index.candidates(want("amara", Thing(
            ("produce", "depart(garbage)")), 104, **wide())) == set()
        assert not index.file(give("e", Thing(("produce", "depart(garbage)")), 1, **wide()))
        assert not index.file(give("f", Thing(("produce", "from(u2e4)", "from(u2e5)")), 1, **wide()))

    def test_every_wanted_head_must_be_answered(self):
        """A give silent on `to` is in no `to` cone: a want naming `to`
        does not see it, however well its `from` fits."""
        ontology = roles_ontology()
        half = give("bruno", Thing(("vegetable-box", "from(u2e4x)")), 50, **wide())
        both = give("chiara", Thing(("vegetable-box", "from(u2e4x)", "to(u2f1)")), 50, **wide())
        index = DimensionIndex(ontology)
        for a in (half, both):
            assert index.file(a)
        b = want("amara", Thing(("produce", "from(u2e4)", "to(u2f)")), 104, **wide())
        assert index.candidates(b) == {both.offer_id}
        b = want("amara", Thing(("produce", "from(u2e4)")), 104, **wide())
        assert index.candidates(b) == {half.offer_id, both.offer_id}

    def test_names_in_role_terms_prune_through_the_graph(self):
        """ontodag #15: `from(my_home_4th)`, `from(ljubljana)` are filed as
        spelled and the cone query decides them by the graph."""
        ontology = roles_ontology()
        floor = give("chiara", Thing(("vegetable-box", "from(my_home_4th)")), 50, **wide())
        region = give("bruno", Thing(("vegetable-box", "from(ljubljana)")), 50, **wide())
        far = give("dora", Thing(("vegetable-box", "from(u2f)")), 50, **wide())
        index = DimensionIndex(ontology)
        for a in (floor, region, far):
            assert index.file(a)
        for wanted in ("from(my_home)", "from(u2e4)", "from(u2e)", "from(ljubljana)"):
            cands = index.candidates(want("amara", Thing(("produce", wanted)), 104, **wide()))
            assert floor.offer_id in cands and far.offer_id not in cands, wanted
        # the region is wider than a cell inside it, and its covering is a
        # lower bound: it fits within nothing but itself
        assert region.offer_id in index.candidates(
            want("amara", Thing(("produce", "from(ljubljana)")), 104, **wide()))
        assert region.offer_id not in index.candidates(
            want("amara", Thing(("produce", "from(u2)")), 104, **wide()))

    def test_candidates_is_exactly_one_get(self, monkeypatch):
        """One `get` per want, the want's own terms as the query, `items_only`,
        no set arithmetic on the answer."""
        ontology = roles_ontology()
        index = DimensionIndex(ontology)
        v3 = dict(valid=TimeWindow(0, 1_000_000))
        for a in (give("bruno", Thing(("vegetable-box", "from(u2e4x)")), 50, **v3),
                  give("dora", Thing(("vegetable-box",)), 50, **v3)):
            assert index.file(a)
        calls = []
        real_get = index._dag.get
        monkeypatch.setattr(index._dag, "get",
                            lambda *a, **kw: calls.append((a, kw)) or real_get(*a, **kw))
        monkeypatch.setattr(index._dag, "get_overlapping",
                            lambda *a, **kw: pytest.fail("get_overlapping called"))
        b = want("amara", Thing(("produce", "from(u2e4)", "from(u2e)")), 104, **v3)
        assert len(index.candidates(b)) == 1
        assert len(calls) == 1
        (terms,), kw = calls[0]
        assert {"produce", "from(u2e4)", "from(u2e)"} <= set(terms)
        assert kw == {"items_only": True}


def _iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
