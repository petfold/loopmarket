"""The matching probes behind ontodag's docs/plans/REVIEW_2026-10.md §6.

Run from the repository root: ``python3 scripts/perf_matching.py``. A
catalogue of 300 random categories, books of n gives and n wants with
random concepts, then: candidate generation by the give x want product
(what `SolverAgent` runs) against the ontodag index
(`candidate_matches_indexed`), checked to find the same matches; the cost
of building a `DimensionIndex`; and one `SolverAgent.find_loops`.

Numbers are wall-clock times on whatever machine runs this; the review's
were taken on an i7-3612QM laptop with 8 GB.
"""
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from recordstore import MemoryBytesStore, RecordStore  # noqa: E402

from loopmarket import (GeoDisc, BookClearing, Ontology, OfferRegistry,  # noqa: E402
                        SolverAgent, Thing, TimeWindow, give, want)
from loopmarket.dimensions import DimensionIndex, candidate_matches_indexed  # noqa: E402
from loopmarket.matching import candidate_matches  # noqa: E402

NOW = 5_000


def catalogue(size=300, seed=1):
    rng = random.Random(seed)
    tree = {"goods": []}
    names = ["goods"]
    for i in range(size):
        name = f"g{i}"
        tree[name] = [rng.choice(names)]
        names.append(name)
    return Ontology().load(tree), names


def book(names, n, seed=2):
    rng = random.Random(seed)
    w = dict(service=TimeWindow(1_000, 2_000), where=GeoDisc(46.0, 14.0, 1_000),
             valid=TimeWindow(0, 10_000))
    offers = []
    for i in range(n):
        offers.append(give(f"m{i % 50}", Thing((rng.choice(names[1:]),)),
                           10 + rng.randrange(90), nonce=i, **w))
        offers.append(want(f"m{(i + 7) % 50}", Thing((rng.choice(names[: len(names) // 3]),)),
                           10 + rng.randrange(90), nonce=10_000 + i, **w))
    return offers


def timed(label, fn):
    t = time.perf_counter()
    out = fn()
    print(f"{label:62} {(time.perf_counter() - t) * 1000:9.1f} ms")
    return out


def main():
    ontology, names = catalogue()
    for n in (100, 400, 800):
        offers = book(names, n)
        prod = timed(f"n={n:5}: candidate_matches (product, the solver's path)",
                     lambda: list(candidate_matches(offers, ontology, now=NOW)))
        idx = timed(f"n={n:5}: candidate_matches_indexed (ontodag query)",
                    lambda: list(candidate_matches_indexed(offers, ontology, now=NOW)))

        def key(m):
            return (m.give.offer_id, m.want.offer_id)
        same = sorted(map(key, prod)) == sorted(map(key, idx))
        print(f"{'':62} matches: {len(prod)} vs {len(idx)}, identical: {same}")
    timed("DimensionIndex over the 300-category catalogue",
          lambda: DimensionIndex(ontology))
    from ontodag import packs, prelude
    core = Ontology()
    prelude.apply(core.dag)
    core.dag.merge(packs.adoption_dag(core.dag, "core"))
    timed(f"DimensionIndex over the core pack ({len(core.dag.nodes)} nodes)",
          lambda: DimensionIndex(core))
    for n in (100, 400):
        offers = book(names, n)
        registry = OfferRegistry(RecordStore(MemoryBytesStore()))
        registry.publish_many(offers)
        registry.commit()
        agent = SolverAgent(registry, ontology, BookClearing(registry, ontology))
        timed(f"n={n:5}: SolverAgent.find_loops", lambda: agent.find_loops(now=NOW))
    timed("loop help (CLI start-up)", lambda: subprocess.run(
        [sys.executable, "-m", "loopmarket", "help"], capture_output=True))


if __name__ == "__main__":
    main()
