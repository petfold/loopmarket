"""The federated book, end to end: publish → fold → solve → settle → follow.

Three makers publish per-maker books; a fourth (Mallory) tries to forge an
offer in Amara's name; one offer is withdrawn by tombstone. Two independent
aggregators fold everything in different orders and produce byte-identical
manifests; a solver settles the triangle against the fold; settlement bases
its *own* book on the fold (provably — the re-commit reproduces the fold's
root); both aggregators fold the settlement back in; a follower reads the
settled world from the manifest alone.

Run in memory (no network, no dependencies beyond the core):

    PYTHONPATH=src python3 examples/demo_federation.py

Run live against a Bee node (feeds, real addresses, network blobs):

    BEE_API=http://localhost:1633 BEE_BATCH=<postage batch id> \\
        PYTHONPATH=src python3 examples/demo_federation.py
"""

import os
import secrets
import time

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Aggregator, GeoDisc, MockSettlement, OfferRegistry, Ontology,
    SolverAgent, Thing, TimeWindow, give, want,
)
from loopmarket.federation import SETTLEMENT

BEE_API = os.environ.get("BEE_API")
BEE_BATCH = os.environ.get("BEE_BATCH")
LIVE = bool(BEE_API and BEE_BATCH)
TOPIC = f"loopfed-demo-{int(time.time())}"

if LIVE:
    from recordstore import BeeBytesStore, swarm_store

    from loopmarket import maker_address

    def fresh_store():
        """A store over the network's blob space, head kept locally."""
        return RecordStore(BeeBytesStore(BEE_API, BEE_BATCH))

    def feed_store(name, **kw):
        """A store whose head lives in a Swarm feed (owner- or signer-side)."""
        return swarm_store(f"{TOPIC}-{name}", api_url=BEE_API,
                           stamp=BEE_BATCH, **kw)
else:
    BLOBS = MemoryBytesStore()

    def fresh_store():
        return RecordStore(BLOBS)


def short(root):
    return f"{root[:16]}…" if root else "(none)"


print(f"\n=== the federated book — "
      f"{'LIVE on ' + BEE_API if LIVE else 'in memory'} ===\n")

# --- the shared catalogue (persistent, so offers can pin it) -----------------

catalogue = Ontology.persistent(
    feed_store("catalogue", signer=secrets.token_hex(32)) if LIVE
    else fresh_store())
catalogue.load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})
catalogue.commit()
pins = catalogue.pins
print(f"catalogue committed: root={short(catalogue.root)}")
print(f"offers will pin it: registry v{pins['registry_version']}, "
      f"contract v{pins['contract_version']}\n")

# --- three makers, three books (one feed each, when live) --------------------

now = int(time.time())
town = dict(service=TimeWindow(now, now + 120 * 86_400),
            valid=TimeWindow(now - 3_600, now + 30 * 86_400), **pins)
places = {"amara": GeoDisc(46.05, 14.50, 5_000),
          "bruno": GeoDisc(46.10, 14.55, 15_000),
          "chen": GeoDisc(46.06, 14.51, 4_000)}

books, name_of = {}, {}
for name in ("amara", "bruno", "chen"):
    if LIVE:
        key = secrets.token_hex(32)
        owner = maker_address(key)
        book = OfferRegistry(feed_store(f"book-{name}", signer=key))
    else:
        owner, book = name, OfferRegistry(fresh_store())
    books[owner], name_of[owner] = book, name

owners = {v: k for k, v in name_of.items()}
a, b, c = owners["amara"], owners["bruno"], owners["chen"]
books[a].publish_many([
    give(a, Thing(("piano-lesson",), unit="course"), 100,
        where=places["amara"], **town),
    want(a, Thing(("produce", "local", "weekly"), unit="course"), 104,
        where=places["amara"], **town),
])
books[b].publish_many([
    give(b, Thing(("vegetable-box",), unit="course"), 50,
        where=places["bruno"], **town),
    want(b, Thing(("bicycle-repair",), unit="course"), 52,
        where=places["bruno"], **town),
])
books[c].publish_many([
    give(c, Thing(("bicycle-repair",), unit="course"), 80,
        where=places["chen"], **town),
    want(c, Thing(("music-lesson",), unit="course"), 83,
        where=places["chen"], **town),
])

# Bruno posts a second box at a worse price, thinks better of it, and
# withdraws: the exit is a monotone tombstone, an *add* that survives merges.
regret = books[b].publish(
    give(b, Thing(("vegetable-box",), unit="course"), 90,
        where=places["bruno"], **town))
books[b].withdraw(regret)

for owner, book in books.items():
    book.commit()
    print(f"{name_of[owner]:>7} published "
          f"{len(list(book.offers(include_filled=True)))} offers "
          f"under their own book ({owner[:14]}…)"
          if LIVE else
          f"{name_of[owner]:>7} published their own book "
          f"({len(list(book.offers(include_filled=True)))} offers)")
print(f"        bruno withdrew one offer again (tombstone {regret[:12]}…)")

# --- Mallory forges; the fold is where forgery goes to die --------------------

if LIVE:
    mallory_key = secrets.token_hex(32)
    mallory_owner = maker_address(mallory_key)
    mallory = OfferRegistry(feed_store("book-mallory", signer=mallory_key))
else:
    mallory_owner = "mallory"
    mallory = OfferRegistry(fresh_store())
forged = give(a, Thing(("piano-lesson",), unit="course"), 1,
             where=places["amara"], **town)     # "amara sells cheap" — Mallory
honest = give(mallory_owner, Thing(("food",), unit="course"), 60,
             where=places["bruno"], **town)
mallory.publish_many([forged, honest])
mallory.commit()
name_of[mallory_owner] = "mallory"
print("mallory published a forged offer in amara's name\n")

# --- two independent aggregators fold, in different orders --------------------

announce_a = [a, b, c, mallory_owner]
agg_a = Aggregator(fresh_store, aggregator_id="agg-a")
agg_b = Aggregator(fresh_store, aggregator_id="agg-b")
for owner in announce_a:
    agg_a.announce(owner, (books.get(owner) or mallory).store)
for owner in reversed(announce_a):
    agg_b.announce(owner, (books.get(owner) or mallory).store)

m_a, m_b = agg_a.fold(), agg_b.fold()
identical = (m_a.book_root, m_a.provenance_root, m_a.index_root,
             m_a.announcement_root) == \
            (m_b.book_root, m_b.provenance_root, m_b.index_root,
             m_b.announcement_root)
print(f"aggregator A folded: book={short(m_a.book_root)}")
print(f"aggregator B folded (reverse order): book={short(m_b.book_root)}")
print(f"all four manifest roots byte-identical: {identical}")

BLOB_SPACE = books[a].store.blobs

folded = OfferRegistry(RecordStore.at(m_a.book_root, BLOB_SPACE))
active = list(folded.offers(now=now))
prov = RecordStore.at(m_a.provenance_root, BLOB_SPACE)
reason = prov.get(f"reject/{mallory_owner}/offer/{forged.offer_id}")["reason"]
print(f"active offers in the fold: {len(active)} "
      f"(6 triangle + mallory's honest one)")
print(f"the forgery was refused: \"{reason}\"")
print(f"bruno's tombstone closed his regretted offer: "
      f"{folded.is_withdrawn(regret)}\n")

# --- settlement is its own writer, provably based on the fold -----------------

settle = OfferRegistry(
    feed_store("settlement", signer=secrets.token_hex(32)) if LIVE
    else fresh_store())
settle.absorb(folded)
base = settle.commit()
print(f"settlement based its own book on the fold — re-commit "
      f"reproduces the root: {base == m_a.book_root}")

agent = SolverAgent(settle, catalogue, MockSettlement(settle, catalogue),
                    solver_id="demo-solver")
receipts = [r for r in agent.step(now=now) if r.accepted]
loop_rec = settle.store.get(f"loop/{receipts[0].loop_id}")
print(f"the solver settled 1 loop, surplus {100 * loop_rec['surplus']:.2f}%:")
for leg in loop_rec["legs"]:
    giver = name_of.get(settle.get(leg["give"]).maker, "?")
    taker = name_of.get(settle.get(leg["want"]).maker, "?")
    print(f"   {giver:>7} → {taker:<7} rate {leg['rate']:.3f}")

# --- both aggregators fold settlement back in; a follower reads it all --------

for agg in (agg_a, agg_b):
    agg.announce("settlement-0", settle.store, role=SETTLEMENT)
m_a2, m_b2 = agg_a.fold(), agg_b.fold()
print(f"\nre-fold with the settlement book: identical again: "
      f"{m_a2.book_root == m_b2.book_root}")

follower = OfferRegistry(RecordStore.at(m_a2.book_root, BLOB_SPACE))
fills = list(follower.store.keys("fill/"))
print(f"a follower, given only the manifest, reads the loop and "
      f"{len(fills)} atomic fills")
second = SolverAgent(follower, catalogue,
                     MockSettlement(follower, catalogue), solver_id="second")
print(f"second solver pass over the settled fold finds: "
      f"{len([r for r in second.step(now=now) if r.accepted])} loops\n")
print("=== done ===\n")
