"""The dimension-backed candidate generator (loopmarket.dimensions).

The load-bearing assertion is RECALL: over randomized books, the indexed
generator must yield exactly the matches of the exact ask x bid baseline —
this is the benchmark ARCHITECTURE.md §6 demands of smarter generators.
The second assertion is that it actually prunes (fewer exact checks than
the full product), so it cannot silently degenerate into the baseline."""

import random

from loopmarket import GeoDisc, Ontology, Thing, TimeWindow, ask, bid
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
        a1 = ask("bruno", Thing(("vegetable-box",)), 50, **wide())
        a2 = ask("chiara", Thing(("piano-lesson",)), 30, **wide())
        late = wide(service=TimeWindow(200_000, 300_000))
        a3 = ask("dora", Thing(("vegetable-box",)), 40, **late)
        b = bid("amara", Thing(("produce", "weekly")), 104, **wide())

        index = DimensionIndex(ontology)
        for a in (a1, a2, a3):
            assert index.file(a)
        cands = index.candidates(b)
        assert a1.offer_id in cands
        assert a2.offer_id not in cands          # wrong concept cone
        assert a3.offer_id not in cands          # disjoint service window

    def test_unknown_vocabulary_not_filed(self):
        index = DimensionIndex(fresh_ontology())
        stranger = ask("x", Thing(("mystery-goods",)), 1, **wide())
        assert not index.file(stranger)
        assert stranger.offer_id not in index._filed

    def test_shared_catalogue_untouched(self):
        ontology = fresh_ontology()
        before = {(p.name, c.name) for p in ontology.dag.nodes.values()
                  for c in p.neighbors}
        index = DimensionIndex(ontology)
        index.file(ask("bruno", Thing(("vegetable-box",)), 50, **wide()))
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
            side = ask if rng.random() < 0.5 else bid
            offers.append(side(maker, thing, 10 + rng.randrange(90),
                               **window))
        return offers

    def test_exactly_the_baseline_matches(self):
        ontology = fresh_ontology()
        for seed in range(5):
            offers = self._random_book(seed)
            expected = {(m.ask.offer_id, m.bid.offer_id)
                        for m in candidate_matches(offers, ontology, now=NOW)}
            got = {(m.ask.offer_id, m.bid.offer_id)
                   for m in candidate_matches_indexed(
                       offers, ontology, now=NOW)}
            assert got == expected, f"recall/precision drift at seed {seed}"

    def test_it_actually_prunes(self):
        ontology = fresh_ontology()
        offers = self._random_book(1)
        asks = [o for o in offers if o.kind == "ask"]
        bids = [o for o in offers if o.kind == "bid"]
        index = DimensionIndex(ontology)
        filed = [a for a in asks if index.file(a)]
        checked = sum(len(index.candidates(b)) for b in bids)
        assert checked < len(filed) * len(bids) * 0.8, \
            "the index is not pruning against the full product"
