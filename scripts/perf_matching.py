"""Gate G3's measurement (docs/plans/ontodag-coupling.md §5): the give x
want product against the ontodag index, matching alone and a whole solver
step, on three kinds of book and growing sizes.

Run from the repository root: ``python3 scripts/perf_matching.py``. The
catalogues are a random tree of 300 categories (`tree`) and ontodag's
core pack (`core`: the prelude and the `core` pack, about 5,000
categories). A book holds n gives and n wants, v4 offers that say nothing
of where or when, so the categories alone decide the matches: a give of
any category, a want of one of a hundred from the broad end (the first
third of the tree, the core pack's hundred categories with the most below
them). Fifty makers, prices from 10 to 99, every quantity 1. The `places`
books are the tree's with geo and time declared: every give hands over in
one of eight cells within a window of a few hours, half the wants name
one of the two parent cells and a third a window of days.

Matching is `candidate_matches` (the index, what the solver runs) against
the product the tests keep as their oracle (`tests/oracle.py`), checked to
find the same matches in the same order. The step is one
`SolverAgent.find_loops` over a book of those offers, as it runs and with
its four searches swapped for the oracle's (and no index built). Every
measurement runs in a fresh interpreter, once with the product first and
once with the index first, each variant once and timed; `--repeat` runs
the pair of interpreters that many times and reports the median, and
`--raw FILE` keeps every interpreter's numbers. The index's fixed cost,
building it (a copy of the catalogue), is measured alone.

Numbers are wall-clock times on whatever machine runs this; check the
load first (`uptime`). The table in ontodag-coupling.md says where and
when its numbers were taken.
"""
import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]

NOW = 5_000
MAKERS = 50


def catalogue(kind):
    """(Ontology, give categories, want categories)."""
    from loopmarket import Ontology
    if kind in ("tree", "places"):
        rng = random.Random(1)
        tree, names = {"goods": []}, ["goods"]
        for i in range(300):
            name = f"g{i}"
            tree[name] = [rng.choice(names)]
            names.append(name)
        cat = Ontology().load(tree)
        if kind == "places":
            cat.declare_handover(["geo", "time"])
        return cat, names[1:], names[: len(names) // 3]
    from ontodag import packs, prelude
    from ontodag import dimensions as dims
    cat = Ontology()
    prelude.apply(cat.dag)
    cat.dag.merge(packs.adoption_dag(cat.dag, "core"))
    plain = sorted(n for n in cat.dag.nodes if "(" not in n and n != "*" and not dims.is_kind_node(n)
                   and cat.head_kind(n) is None)
    broad = sorted(plain, key=lambda n: (-cat.dag.nodes[n].descendant_count, n))
    return cat, plain, broad[:100]


def _where_and_when(rng, wanted):
    """For the `places` books: a give hands over in one of eight cells in a
    window of a few hours; a want names one of their two parent cells half
    the time and a window of days a third of the time."""
    terms = []
    if not wanted:
        terms.append(f"geo(u2{rng.choice('ef')}{rng.choice('4567')})")
        day, hour = rng.randrange(10, 20), rng.randrange(6, 18)
        terms.append(f"time(2026-10-{day}T{hour:02d}:00:00Z..2026-10-{day}T{hour + rng.randrange(2, 6):02d}:00:00Z)")
    else:
        if rng.random() < 0.5:
            terms.append(f"geo(u2{rng.choice('ef')})")
        if rng.random() < 0.33:
            day = rng.randrange(10, 17)
            terms.append(f"time(2026-10-{day}..2026-10-{day + 3})")
    return terms


def book(kind, gives, wants, n, seed=2):
    from loopmarket import Thing, TimeWindow, give, want
    rng = random.Random(seed)
    valid = TimeWindow(0, 10_000)
    offers = []
    for i in range(n):
        g = (rng.choice(gives), *(_where_and_when(rng, False) if kind == "places" else ()))
        offers.append(give(f"m{i % MAKERS}", Thing(g), 10 + rng.randrange(90), nonce=i, valid=valid))
        w = (rng.choice(wants), *(_where_and_when(rng, True) if kind == "places" else ()))
        offers.append(want(f"m{(i + 7) % MAKERS}", Thing(w), 10 + rng.randrange(90),
                           nonce=10_000 + i, valid=valid))
    return offers


def _key(matches):
    return [(m.give.offer_id, m.want.offer_id) for m in matches]


def matching(variant, cat, offers):
    import oracle
    from loopmarket.matching import candidate_matches
    search = oracle.candidate_matches if variant == "product" else candidate_matches
    t = time.perf_counter()
    found = list(search(offers, cat, now=NOW))
    return time.perf_counter() - t, _key(found)


def step(variant, cat, offers):
    """One `find_loops` over a fresh book of `offers`; the product variant
    runs the oracle's four searches and builds no index."""
    import oracle
    from recordstore import MemoryBytesStore, RecordStore
    from loopmarket import BookClearing, OfferRegistry
    from loopmarket.solver import agent
    saved = {name: getattr(agent, name) for name in
             ("DimensionIndex", "candidate_matches", "aggregate_legs", "parts_legs", "composed_legs")}
    if variant == "product":
        def drop_index(search):
            return lambda *a, index=None, **kw: search(*a, **kw)
        agent.DimensionIndex = lambda ontology: None
        for name in ("candidate_matches", "aggregate_legs", "parts_legs", "composed_legs"):
            setattr(agent, name, drop_index(getattr(oracle, name)))
    try:
        registry = OfferRegistry(RecordStore(MemoryBytesStore()))
        registry.publish_many(offers)
        registry.commit()
        solver = agent.SolverAgent(registry, cat, BookClearing(registry, cat))
        t = time.perf_counter()
        _, loops = solver.find_loops(now=NOW)
        return time.perf_counter() - t, sorted(loop.loop_id for loop in loops)
    finally:
        for name, value in saved.items():
            setattr(agent, name, value)


def child(kind, n, what, first):
    """Runs in a fresh interpreter: both variants, `first` first, each on
    fresh offer objects (an offer caches its id and unit price)."""
    cat, gives, wants = catalogue(kind)
    if what == "build":
        from loopmarket import DimensionIndex
        t = time.perf_counter()
        DimensionIndex(cat)
        return {"build": time.perf_counter() - t, "categories": len(cat.dag.nodes)}
    run = matching if what == "match" else step
    order = [first, "index" if first == "product" else "product"]
    out = {}
    for variant in order:
        out[variant], out[variant + "_found"] = run(variant, cat, book(kind, gives, wants, n))
    out["identical"] = out["product_found"] == out["index_found"]
    out["found"] = len(out["index_found"])
    del out["product_found"], out["index_found"]
    return out


RAW = []


def measure(kind, n, what, first):
    cmd = [sys.executable, os.path.abspath(__file__), "--child", kind, str(n), what, first]
    done = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=True)
    out = json.loads(done.stdout.strip().splitlines()[-1])
    RAW.append({"catalogue": kind, "n": n, "what": what, "first": first,
                "load": os.getloadavg()[0], **out})
    return out


def ms(seconds):
    return f"{seconds * 1000:,.0f}" if seconds >= 0.01 else f"{seconds * 1000:.1f}"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--child", nargs=4, metavar=("KIND", "N", "WHAT", "FIRST"), help=argparse.SUPPRESS)
    p.add_argument("--catalogues", default="tree,core,places")
    p.add_argument("--match-sizes", default="10,25,50,100,200,400")
    p.add_argument("--step-sizes", default="10,25,50,100,200")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--raw", help="also write every interpreter's numbers to this file, one JSON line each")
    a = p.parse_args()
    if a.child:
        kind, n, what, first = a.child
        print(json.dumps(child(kind, int(n), what, first)))
        return
    print(f"# {time.strftime('%Y-%m-%d %H:%M')}, load average {os.getloadavg()[0]:.2f}, "
          f"{a.repeat} pair(s) of interpreters per row, medians in ms")
    for kind in a.catalogues.split(","):
        builds = [measure(kind, 0, "build", "index") for _ in range(a.repeat)]
        print(f"\n{kind}: {builds[0]['categories']} nodes, building the index "
              f"{ms(statistics.median(b['build'] for b in builds))} ms")
        for what, sizes in (("match", a.match_sizes), ("step", a.step_sizes)):
            print(f"\n| {what} | n a side | found | product first: product / index | "
                  f"index first: index / product | identical |")
            print("|---|---:|---:|---:|---:|---|")
            for n in (int(s) for s in sizes.split(",") if s):
                rows = {first: [measure(kind, n, what, first) for _ in range(a.repeat)]
                        for first in ("product", "index")}

                def med(first, variant):
                    return statistics.median(r[variant] for r in rows[first])
                same = all(r["identical"] for rs in rows.values() for r in rs)
                print(f"| {what} | {n} | {rows['index'][0]['found']} | "
                      f"{ms(med('product', 'product'))} / {ms(med('product', 'index'))} | "
                      f"{ms(med('index', 'index'))} / {ms(med('index', 'product'))} | {same} |", flush=True)
                if a.raw:
                    with open(a.raw, "w") as fh:
                        fh.writelines(json.dumps(r) + "\n" for r in RAW)


if __name__ == "__main__":
    main()
