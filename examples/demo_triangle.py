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

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    GeoDisc, MockSettlement, OfferRegistry, Ontology, SolverAgent, Thing,
    TimeWindow, give, want,
)

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

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

# --- the book ------------------------------------------------------------------

registry = OfferRegistry(RecordStore(MemoryBytesStore()))

now = int(time.time())
season = TimeWindow(now, now + 120 * 86_400)          # the next four months
standing = TimeWindow(now - 3_600, now + 30 * 86_400)  # offers stand a month

town = dict(service=season, valid=standing)
amara_flat = GeoDisc(46.05, 14.50, 5_000)
bruno_farm = GeoDisc(46.10, 14.55, 15_000)   # delivery radius covers the town
chen_shop = GeoDisc(46.06, 14.51, 4_000)

offers = [
    # Amara: piano for amara-tokens; amara-tokens for a vegetable box
    give("amara", Thing(("piano-lesson",), unit="course"), 100,
        where=amara_flat, **town),
    want("amara", Thing(("produce", "local", "weekly"), unit="course"), 104,
        where=amara_flat, **town),
    # Bruno: vegetable boxes for bruno-tokens; bruno-tokens for bike repair
    give("bruno", Thing(("vegetable-box",), unit="course"), 50,
        where=bruno_farm, **town),
    want("bruno", Thing(("bicycle-repair",), unit="course"), 52,
        where=bruno_farm, **town),
    # Chen: bicycle repair for chen-tokens; chen-tokens for piano lessons
    give("chen", Thing(("bicycle-repair",), unit="course"), 80,
        where=chen_shop, **town),
    want("chen", Thing(("music-lesson",), unit="course"), 83,
        where=chen_shop, **town),
]

registry.publish_many(offers)
root = registry.commit()
print(f"\nbook committed: root={root[:16]}…  ({len(offers)} offers)\n")

# --- the solver ------------------------------------------------------------------

agent = SolverAgent(
    registry=registry,
    ontology=ontology,
    settlement=MockSettlement(registry, ontology),
    solver_id="demo-solver",
)

receipts = agent.step()

print()
for r in receipts:
    status = "SETTLED" if r.accepted else f"rejected: {r.reason}"
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
print("\nsecond pass (book now settled):")
agent.step()
