"""The federated book, end to end: publish → fold → solve → clear → follow.

The catalogue is ontodag's shipped `core` pack (4,000+ consensus categories)
plus a small local services layer, committed to a pinned root every offer
names. Three makers publish per-maker books; a fourth (Mallory) tries to
forge an offer in Amara's name; one offer is withdrawn by tombstone. Two
independent aggregators fold everything in different orders and produce
byte-identical manifests. A third aggregator (Cain) censors Chen: it
announces her book and folds nothing of it — the audit turns that into
absence proofs from Cain's own manifest, and a solver that folds the
announced maker books itself recovers the honest fold byte for byte (T14).
A solver clears the triangle against the fold; clearing bases its *own*
book on the fold (provably — the re-commit reproduces the fold's root);
both honest aggregators fold the clearing back in; a follower reads the
cleared world from the manifest alone.

`LOOP_CORE=0` skips the core pack (an eleven-category toy catalogue instead;
faster on a slow node).

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
    Aggregator, GeoDisc, MockClearing, OfferRegistry, Ontology,
    SolverAgent, Thing, TimeWindow, audit_manifest, give, want,
)
from loopmarket.federation import CLEARING

BEE_API = os.environ.get("BEE_API")
BEE_BATCH = os.environ.get("BEE_BATCH")
LIVE = bool(BEE_API and BEE_BATCH)
CORE = os.environ.get("LOOP_CORE", "1") != "0"
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


def committed(writer, attempts=8, pause=20):
    """`writer.commit()`, retrying transient Bee 5xx when live.

    A light node's feed probe asks the network for a chunk that does not
    exist yet; when peers time out Bee answers 500 ("read chunk failed")
    rather than 404, and recordstore re-raises 5xx on purpose — the retry
    belongs to the caller, who knows how long a demo may wait.
    """
    for attempt in range(attempts):
        try:
            return writer.commit()
        except Exception as e:                      # noqa: BLE001
            status = getattr(e, "status", None)
            if not LIVE or status is None or status < 500 \
                    or attempt == attempts - 1:
                raise
            print(f"        (node answered {status}; retrying the commit in "
                  f"{pause}s, attempt {attempt + 2}/{attempts})")
            time.sleep(pause)


print(f"\n=== the federated book — "
      f"{'LIVE on ' + BEE_API if LIVE else 'in memory'} ===\n")

# --- the shared catalogue (persistent, so offers can pin it) -----------------

catalogue = Ontology.persistent(
    feed_store("catalogue", signer=secrets.token_hex(32)) if LIVE
    else fresh_store())
if CORE:
    # ontodag's upper ontology, built by consensus over WordNet, SUMO,
    # OpenCyc and Wikidata; its v6 goods layer exists because loopmarket
    # asked whether traded things could be named precisely. Adoption is a
    # merge, so every adopter lands on the same root — the pack is a
    # fingerprint, not a download. Services are still thin in core (its
    # `service` is the financial sense), so a local layer hangs the
    # town's trades from core's hinges: `lesson ⊑ teaching`, `work`,
    # `produce`.
    from ontodag import packs
    t0 = time.time()
    packs.apply(catalogue.dag, "core")
    print(f"adopted ontodag's core pack: {len(catalogue.dag.nodes)} "
          f"categories in {time.time() - t0:.1f}s")
    catalogue.load({
        "repair": ["work"], "bicycle-repair": ["repair"],
        "music-lesson": ["lesson"], "piano-lesson": ["music-lesson"],
        "local": [], "weekly": [],
        "vegetable-box": ["produce", "local", "weekly"],
    })
else:
    catalogue.load({
        "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
        "piano-lesson": ["music-lesson"], "repair": ["service"],
        "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
        "local": [], "weekly": [],
        "vegetable-box": ["produce", "local", "weekly"],
    })
t0 = time.time()
committed(catalogue)
pins = catalogue.pins
print(f"catalogue committed in {time.time() - t0:.1f}s: "
      f"root={short(catalogue.root)}")


def lineage(name):
    """The longest path from a category up to a top-level node."""
    parents = sorted(p.name for p in catalogue.dag.nodes[name].parents
                     if p.name != "*")
    chains = [lineage(p) for p in parents]
    return [name] + (max(chains, key=len) if chains else [])


print("an offer names its kind; matching is fits-within along the catalogue:")
print("   " + " ⊑ ".join(lineage("piano-lesson")))
print("   " + " ⊑ ".join(lineage("vegetable-box")))
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
    committed(book)
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
committed(mallory)
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

# --- Cain censors Chen; the manifest convicts him -------------------------------


class CensoringAggregator(Aggregator):
    """Announces a maker and silently folds nothing of theirs (T14). It
    lives in the demo: the library has no honest use for it."""

    def _sanitize(self, owner, role, root, source, provenance):
        if owner == c:
            return self._new_store()   # announced, never folded, never rejected
        return super()._sanitize(owner, role, root, source, provenance)


cain = CensoringAggregator(fresh_store, aggregator_id="agg-cain")
for owner in announce_a:
    cain.announce(owner, (books.get(owner) or mallory).store)
m_c = cain.fold()
print(f"\naggregator Cain folded, quietly dropping chen: "
      f"book={short(m_c.book_root)}")
print(f"same announcement_root as A ({m_c.announcement_root == m_a.announcement_root}), "
      f"different book_root ({m_c.book_root != m_a.book_root}): "
      f"the fold is pure, so this alone is evidence")
omitted = audit_manifest(m_c, BLOB_SPACE)
print(f"the audit reads Cain's manifest and finds {len(omitted)} omissions, "
      f"all by {sorted({name_of[o.owner] for o in omitted})}:")
from recordstore import ABSENT, verify_proof  # noqa: E402 — the stranger's check
for o in omitted:
    verdict = verify_proof(o.proof, m_c.book_root) is ABSENT
    print(f"   {o.key[:22]}… absent from Cain's book — proof verifies "
          f"with no store access: {verdict}")
print(f"honest aggregator A audits clean: {audit_manifest(m_a, BLOB_SPACE) == []}")

censored_view = OfferRegistry(RecordStore.at(m_c.book_root, BLOB_SPACE))
lost = SolverAgent(censored_view, catalogue,
                   MockClearing(censored_view, catalogue), solver_id="trusting")
print(f"a solver trusting Cain's manifest finds "
      f"{len(lost.find_loops(now=now)[1])} loops (the triangle needs chen)")

# A solver that trusts no manifest folds the maker books itself. Cain's
# own announcement names them — announcements, not manifests, are the
# ground truth (on Swarm: registry events, maker feeds by (owner, topic)).
announced = RecordStore.at(m_c.announcement_root, BLOB_SPACE)
own = Aggregator(fresh_store, aggregator_id="solver-self")
for key in announced.keys("announce/"):
    rec = announced.get(key)
    own.announce(key[len("announce/"):], RecordStore.at(rec["root"], BLOB_SPACE))
m_own = own.fold()
print(f"a solver folding the announced maker books itself lands on A's "
      f"book_root: {m_own.book_root == m_a.book_root} — "
      f"manifests are caches, never authority\n")

folded = OfferRegistry(RecordStore.at(m_a.book_root, BLOB_SPACE))
active = list(folded.offers(now=now))
prov = RecordStore.at(m_a.provenance_root, BLOB_SPACE)
reason = prov.get(f"reject/{mallory_owner}/offer/{forged.offer_id}")["reason"]
print(f"active offers in the fold: {len(active)} "
      f"(6 triangle + mallory's honest one)")
print(f"the forgery was refused: \"{reason}\"")
print(f"bruno's tombstone closed his regretted offer: "
      f"{folded.is_withdrawn(regret)}\n")

# --- clearing is its own writer, provably based on the fold -----------------

clearing = OfferRegistry(
    feed_store("clearing", signer=secrets.token_hex(32)) if LIVE
    else fresh_store())
clearing.absorb(folded)
base = committed(clearing)
print(f"clearing based its own book on the fold — re-commit "
      f"reproduces the root: {base == m_a.book_root}")

agent = SolverAgent(clearing, catalogue, MockClearing(clearing, catalogue),
                    solver_id="demo-solver")
receipts = [r for r in agent.step(now=now) if r.accepted]
loop_rec = clearing.store.get(f"loop/{receipts[0].loop_id}")
print(f"the solver cleared 1 loop, surplus {100 * loop_rec['surplus']:.2f}%:")
for leg in loop_rec["legs"]:
    giver = name_of.get(clearing.get(leg["give"]).maker, "?")
    taker = name_of.get(clearing.get(leg["want"]).maker, "?")
    print(f"   {giver:>7} → {taker:<7} rate {leg['rate']:.3f}")

# --- both aggregators fold clearing back in; a follower reads it all --------

for agg in (agg_a, agg_b):
    agg.announce("clearing-0", clearing.store, role=CLEARING)
m_a2, m_b2 = agg_a.fold(), agg_b.fold()
print(f"\nre-fold with the clearing book: identical again: "
      f"{m_a2.book_root == m_b2.book_root}")

follower = OfferRegistry(RecordStore.at(m_a2.book_root, BLOB_SPACE))
fills = list(follower.store.keys("fill/"))
print(f"a follower, given only the manifest, reads the loop and "
      f"{len(fills)} atomic fills")
second = SolverAgent(follower, catalogue,
                     MockClearing(follower, catalogue), solver_id="second")
print(f"second solver pass over the cleared fold finds: "
      f"{len([r for r in second.step(now=now) if r.accepted])} loops\n")
print("=== done ===\n")
