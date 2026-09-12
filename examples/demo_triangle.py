"""The smallest nontrivial loop, end to end.

Amara teaches piano and wants a weekly vegetable box. Bruno grows vegetables
and wants his delivery bikes repaired. Chen fixes bicycles and her daughter
wants piano lessons. No pair can trade; the triangle clears.

Run:  python3 examples/demo_triangle.py

Everything is in memory (MemoryBytesStore); swap `RecordStore(MemoryBytesStore())`
for `recordstore.swarm_store("offers", signer=...)` and the same code runs
against a Bee node with the book on Swarm.
"""

import logging
import time
from datetime import datetime, timezone

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

from loopmarket.spacetime import cell_for_coords


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- the shared catalogue ----------------------------------------------------

ontology = Ontology().load({
    "service": [],
    "lesson": ["service"],
    "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"],
    "repair": ["service"],
    "bicycle-repair": ["repair"],
    "food": [],
    "produce": ["food"],
    "local": [],
    "weekly": [],
    "vegetable-box": ["produce", "local", "weekly"],
})

# Service roles (docs/plans/P1-spacetime-terms.md §3, 2026-09-12): heads
# under the marker `service-role` match by overlap — a route's `from`/`to`
# over geo cells, a transport's `depart`/`arrive` windows over time. Seed
# vocabulary, one value space per head; the core knows only the marker.
SERVICE_ROLES = {"when": "time", "where": "geo",           # the handover
                 "from": "geo", "to": "geo",                # a route
                 "depart": "time", "arrive": "time"}         # a transport
ontology.declare_service_roles(SERVICE_ROLES)

# --- the book ------------------------------------------------------------------

registry = OfferRegistry(RecordStore(MemoryBytesStore()))

now = int(time.time())
# The v3 record (2026-09-12): where and when are terms in the conjunction.
# The season is one inclusive `when(a..b)`; a place is the cell containing
# the radius the maker names — all three here sit within their radius of a
# cell edge, so each honestly names the coarser cell `u24` (the exact
# covering would be a region node above the few cells that matter — role
# heads take nodes since ontodag #15 landed 2026-09-12; this demo keeps
# the plain cells). Offers stand until withdrawn.
season = f"when({iso(now)}..{iso(now + 120 * 86_400 - 1)})"   # four months
standing = TimeWindow(now - 3_600)                          # until withdrawn

town = dict(valid=standing)
amara_flat = f"where({cell_for_coords(46.05, 14.50, 5_000)})"
bruno_farm = f"where({cell_for_coords(46.10, 14.55, 15_000)})"  # covers the town
chen_shop = f"where({cell_for_coords(46.06, 14.51, 4_000)})"

offers = [
    # Amara: piano for amara-tokens; amara-tokens for a vegetable box
    give("amara", Thing(("piano-lesson", amara_flat, season), unit="course"), 100, **town),
    want("amara", Thing(("produce", "local", "weekly", amara_flat, season), unit="course"), 104, **town),
    # Bruno: vegetable boxes for bruno-tokens; bruno-tokens for bike repair
    give("bruno", Thing(("vegetable-box", bruno_farm, season), unit="course"), 50, **town),
    want("bruno", Thing(("bicycle-repair", bruno_farm, season), unit="course"), 52, **town),
    # Chen: bicycle repair for chen-tokens; chen-tokens for piano lessons
    give("chen", Thing(("bicycle-repair", chen_shop, season), unit="course"), 80, **town),
    want("chen", Thing(("music-lesson", chen_shop, season), unit="course"), 83, **town),
]

registry.publish_many(offers)
root = registry.commit()
print(f"\nbook committed: root={root[:16]}…  ({len(offers)} offers)\n")

# --- the solver ------------------------------------------------------------------

agent = SolverAgent(
    registry=registry,
    ontology=ontology,
    clearing=MockClearing(registry, ontology),
    solver_id="demo-solver",
)

receipts = agent.step()

print()
for r in receipts:
    status = "CLEARED" if r.accepted else f"rejected: {r.reason}"
    print(f"loop {r.loop_id[:16]}… -> {status}")
    if r.accepted:
        loop_rec = registry.store.get(f"loop/{r.loop_id}")
        print(f"  surplus: {100 * loop_rec['surplus']:.2f}%")
        for leg in loop_rec["legs"]:
            a = registry.get(leg["give"])
            b = registry.get(leg["want"])
            print(
                f"  {a.maker:>6} gives {', '.join(a.thing.concepts):<28}"
                f" to {b.maker:<6} (rate {leg['rate']:.3f})"
            )
        print(f"  new book root: {r.book_root[:16]}…")

# A second pass finds nothing: the offers are filled, atomically, in the book.
print("\nsecond pass (book now cleared):")
agent.step()
