# loopmarket — User Guide

*A tutorial. You will publish offers, build a catalogue, watch a solver
find a loop nobody could see, settle it atomically, federate books across
makers, catch a forger, and put the whole thing on a live Swarm network.
Every snippet is runnable as written; run them in order in one Python
session (or adapt freely). For the API in full detail, see the
[Reference Manual](REFERENCE.md); for the design and its reasons,
[ARCHITECTURE.md](../ARCHITECTURE.md); for the vision,
[the loop-economy essay](loop-economy.md).*

## 0. The idea in five sentences

Every economic intention — I teach piano, I want a vegetable box — is one
uniform, content-addressed **offer**. Offers are priced on the maker's
**personal scale**: a private measuring unit that is bookkeeping, not
money — n gives and m wants need n+m prices instead of n×m exchange rates,
nobody ever holds anything, and the numbers cancel inside a loop. A shared
**catalogue** orders meanings by *fits-within*, so "piano-lesson"
satisfies someone who wants "music-lesson". **Solvers** hunt loops —
cycles of offers whose exchange-rate product exceeds 1, which is genuine
surplus. **Settlement** trusts no solver: it re-verifies every leg from
scratch and commits the whole loop atomically, or not at all.

## 1. Installation

```bash
git clone https://github.com/petfold/loopmarket
cd loopmarket
pip install -e ".[test]"        # (--break-system-packages, or use a venv)
python3 -m pytest tests/ -q    # everything green; two tests skip without a Bee node
```

Extras, when you need them:

| extra | gives you | needed for |
|---|---|---|
| `.[swarm]` | `recordstore[bee,feeds]` | running against a live Bee node (§11) |
| `.[sig]` | `eth-keys` | detached offer signatures (§8.4) |

The core has two dependencies — `ontodag` (the catalogue) and
`recordstore` (the book) — and works fully offline; Swarm is a persistence
backend chosen at the edges, never a requirement of the model.

## 2. Your first offer

An offer exchanges a **Thing** (what, when, where) against an amount on
the maker's personal scale. There are exactly two flavours:

```python
from loopmarket import Thing, TimeWindow, GeoDisc, give, want

NOW = 1_700_000_000                       # fix time; determinism is a feature
season   = TimeWindow(NOW, NOW + 90 * 86_400)     # when the service happens
standing = TimeWindow(NOW - 1, NOW + 30 * 86_400) # while the offer stands
here     = GeoDisc(46.05, 14.50, 5_000)           # 5 km around a point

# GIVE: "I give a thing, I want 100 on my own scale"
teach = give("amara", Thing(("piano-lesson",), unit="course"), 100,
            service=season, where=here, valid=standing)

# WANT: "I give 104 on my own scale, I want a thing"
eat = want("amara", Thing(("produce", "local", "weekly"), unit="course"), 104,
          service=season, where=here, valid=standing)
```

(Order-book readers: a *give* is the ask and a *want* is the bid —
`ask`/`bid` remain available as exact synonyms. The plain words won
because in everyday English "ask" reads as requesting, the opposite of
its trading sense.)

Things to notice:

- **The ratio is the information.** Amara priced the box at 104 against
  lessons at 100 — she values a season of boxes at 1.04 lessons. The
  absolute numbers mean nothing; only ratios on one scale do, and because
  every quote shares one denominator her quotes can never contradict each
  other (nobody can arbitrage Amara against her own rate matrix).
- **A `Thing` is a conjunction of catalogue categories** plus quantity,
  unit, and divisibility. `("produce", "local", "weekly")` means all
  three at once. Units must match exactly between a give and a want;
  quantities must be equal unless both sides are `divisible=True`.
- **Offers are immutable values with a content address**:

```python
teach.offer_id          # 64-hex SHA-256 of the canonical encoding
teach.kind              # "give"
teach.unit_price        # 100.0 — scale units per thing-unit
```

  Equal content means equal id, always — concept order doesn't matter,
  but every meaningful field does (a fresh intention gets a fresh `nonce`
  automatically, hence a fresh id).

## 3. The catalogue

Matching needs one question answered: *does the offered thing satisfy the
wanted description?* The catalogue is an OntoDAG ordered by fits-within:

```python
from loopmarket import Ontology

catalogue = Ontology().load({
    "service": [],
    "lesson": ["service"],
    "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"],
    "repair": ["service"],
    "bicycle-repair": ["repair"],
    "food": [],
    "produce": ["food"],
    "local": [], "weekly": [],
    "vegetable-box": ["produce", "local", "weekly"],
})

catalogue.covers("music-lesson", "piano-lesson")   # True: piano fits within
catalogue.covers("piano-lesson", "music-lesson")   # False: not the reverse!
catalogue.satisfies(("vegetable-box",), ("produce", "weekly"))  # True
catalogue.satisfies(("mystery-goods",), ("mystery-goods",))     # False!
```

That last line is invariant **U7: vocabulary fails closed**. An unknown
category never matches — silent drift breaks loudly, by design.

For anything beyond a toy, make the catalogue **persistent** so it has a
canonical root that offers can pin:

```python
from recordstore import MemoryBytesStore, RecordStore

catalogue = Ontology.persistent(RecordStore(MemoryBytesStore()))
catalogue.load({...})            # same dict as above
catalogue.commit()               # -> the catalogue's canonical root

catalogue.pins
# {'ontology_root': '…64 hex…', 'registry_version': '4.1', 'contract_version': '0.1'}
```

Splat `**catalogue.pins` into `give`/`want` and the offer names the exact
semantic ground it was written against. **A pinned catalogue refuses
unpinned offers** during matching, and offers with mismatched pins never
pair — the ground cannot move under a committed loop. (In-memory
catalogues with no root are the development mode: everything unpinned
matches, nothing is demanded.)

## 4. The book

The book is a versioned keyspace over a `RecordStore` — every committed
state is one root reference, and equal content means equal root:

```python
from loopmarket import OfferRegistry

registry = OfferRegistry(RecordStore(MemoryBytesStore()))
registry.publish(teach)
registry.publish(eat)
root = registry.commit()        # one root names the whole book state

list(registry.offers(now=NOW))          # active offers (filters closed ones)
registry.get(teach.offer_id)            # any offer, by content address
```

Three operations you'll want:

- **`snapshot()`** returns `(root, frozen_registry)` — a self-consistent
  view a solver can work against for as long as it likes, for free.
  Everything downstream (proposals, settlement receipts) pins such roots:
  reproducibility and auditability beat freshness (invariant U4).
- **`withdraw(offer_id)`** closes an offer forever — as a *tombstone*, an
  add rather than a delete, so the exit survives merges with peers who
  haven't heard yet. Re-publishing identical content does not resurrect
  it; a fresh intention is a fresh offer.
- **`commit(reconcile=True)`** (the default) converges with concurrent
  writers by three-way merge and then verifies that no settled loop lost
  a leg in the merge (invariant U11 — it raises `PartialLoopError` rather
  than let that damage propagate).

## 5. Matching

A `Match` is one feasible handoff: this give satisfies that want.

```python
from loopmarket import check_match, candidate_matches

grow = give("bruno", Thing(("vegetable-box",), unit="course"), 50,
           service=season, where=GeoDisc(46.10, 14.55, 15_000), valid=standing)

m = check_match(grow, eat, catalogue, now=NOW)
m.rate            # 104/50 = 2.08 — want unit price over give unit price
m.giver, m.receiver   # 'bruno', 'amara'
```

`check_match` is exact and self-contained — cheap to re-run, which is what
lets settlement re-verify without trusting anyone. Its gates, in order:
kinds and distinct makers → validity windows open at `now` → service
windows intersect → service discs intersect (a handover point exists) →
quantity/divisibility/unit → **version pins** (mixed pinning refuses;
pinned catalogues refuse unpinned offers; major registry/contract skew
refuses) → catalogue subsumption. `candidate_matches(offers, catalogue,
now=...)` runs it over the full give × want product — fine in memory, and
§10 shows the indexed generator for bigger books.

## 6. Loops

Rates multiply around a cycle. If the product exceeds 1, the slack is
real, distributable surplus:

```python
from loopmarket import ExchangeGraph

fix   = give("chen", Thing(("bicycle-repair",), unit="course"), 80,
            service=season, where=GeoDisc(46.06, 14.51, 4_000), valid=standing)
learn = want("chen", Thing(("music-lesson",), unit="course"), 83,
            service=season, where=GeoDisc(46.06, 14.51, 4_000), valid=standing)
wheels = want("bruno", Thing(("bicycle-repair",), unit="course"), 52,
             service=season, where=GeoDisc(46.10, 14.55, 15_000), valid=standing)

everyone = [teach, eat, grow, wheels, fix, learn]
graph = ExchangeGraph.from_matches(candidate_matches(everyone, catalogue, now=NOW))
loop = graph.find_profitable_loop()

loop.nodes      # ('amara', 'chen', 'bruno') — no pair of whom could trade!
loop.product    # 1.1222…  -> 12.22% surplus
loop.surplus    # 0.1222…
loop.loop_id    # content address of the settlement decision (the leg cycle)
```

Amara teaches piano but wants vegetables; Bruno grows vegetables but wants
bicycle repair; Chen fixes bicycles and her daughter wants piano lessons.
No two of them can trade — the triangle clears. Under the hood this is
Bellman–Ford hunting negative cycles in −log(rate) weights, iterated in
sorted order so **the same book yields the same loop on every replica**
(invariant U6 — determinism is what later makes the baseline solver the
auction's reserve bid).

## 7. Settlement

Settlement's one non-negotiable: **trust no solver** (invariant U3). A
proposal names the roots it was solved against; settlement re-derives
every leg against the *current* book with its own catalogue, re-checks
pins, oracles, fills, tombstones and the arithmetic, and only then
commits — all fills and the loop record under one new root, atomically.

```python
from loopmarket import MockSettlement, LoopProposal

settlement = MockSettlement(registry, catalogue, clock=lambda: NOW)
# (registry must hold all six offers; publish grow/wheels/fix/learn + commit)

proposal = LoopProposal(loop, book_root=registry.store.root,
                        ontology_root=catalogue.root, solver="me", found_at=NOW)
receipt = settlement.submit(proposal)
receipt.accepted        # True
receipt.book_root       # the new root, with 6 fills + 1 loop record inside
settlement.submit(proposal).accepted    # False: "already filled" — no double spend
```

Rejections come back as `Receipt(accepted=False, reason=...)`: unknown or
filled or withdrawn offers, legs that fail re-verification, pins that
don't equal settlement's own, oracle types outside
`settlement.verifiable_oracles` (the default `MockSettlement` verifies
only `"countersign"`), surplus below threshold, or indivisible legs
without per-node surplus.

## 8. The solver agent — and then federation

Everything above, as one loop of one method:

```python
from loopmarket import SolverAgent

agent = SolverAgent(registry, catalogue, settlement)
receipts = agent.step(now=NOW)   # snapshot → match → graph → hunt → propose
```

That's the whole P0 pipeline (it's `examples/demo_triangle.py`). Now the
part that makes it a *marketplace* rather than a database: nobody shares
a book.

### 8.1 One book per maker

Each maker publishes their own book — own store, and on Swarm their own
feed and signing key, so **feed ownership is the authenticity** of their
offers. All books share one blob space:

```python
blobs = MemoryBytesStore()
amara_book = OfferRegistry(RecordStore(blobs)); amara_book.publish_many([teach, eat]);   amara_book.commit()
bruno_book = OfferRegistry(RecordStore(blobs)); bruno_book.publish_many([grow, wheels]); bruno_book.commit()
chen_book  = OfferRegistry(RecordStore(blobs)); chen_book.publish_many([fix, learn]);    chen_book.commit()
```

### 8.2 The aggregator

Solvers don't poll makers; they read an **aggregator** — anyone who folds
announced books into one view and publishes a four-root **manifest**:

```python
from loopmarket import Aggregator

agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="agg-0")
agg.announce("amara", amara_book.store)
agg.announce("bruno", bruno_book.store)
agg.announce("chen",  chen_book.store)
manifest = agg.fold()

manifest.book_root          # the pure fold — the book a solver reads
manifest.provenance_root    # who said what, and what was rejected and why
manifest.index_root         # derived idx/{concept,time,geo} query structures
manifest.announcement_root  # commitment to the exact input set folded
```

The fold is **pure**: any aggregator that saw the same inputs produces
byte-identical roots, in any order. That's the neutrality mechanism —
run two, compare, and omission (including "pay me to be listed") is a
provable act, not a suspicion. Anyone can be an aggregator; aggregators
sell *serving* (speed, indexes), never *inclusion*.

### 8.3 The fold rules

Announced books are sanitized per record before entering the fold,
fail-closed: an offer's content address is re-derived; an offer whose
maker isn't the book's owner needs a valid detached signature or dies;
tombstones are admitted only from the book that owns the offer;
`fill/`/`loop/` keys are believed only from settlement-role books. Try
the forgery yourself:

```python
mallory = OfferRegistry(RecordStore(blobs))
mallory.publish(give("amara", Thing(("piano-lesson",), unit="course"), 1,
                    service=season, where=here, valid=standing))  # "amara", says mallory
mallory.commit()
agg.announce("mallory", mallory.store)
m2 = agg.fold()

prov = RecordStore.at(m2.provenance_root, blobs)
# reject/mallory/offer/<id> -> {"reason": "foreign maker without valid signature"}
```

### 8.4 Offers travelling outside their home book

For gossip and relays there's the second authenticity layer: a detached
secp256k1 signature over the offer id, stored *beside* the offer (never
inside it — ids stay stable). Needs `.[sig]`:

```python
from loopmarket import maker_address, sign_offer

key = "11" * 32                          # throwaway private key
me = maker_address(key)                  # use this as your maker identity
offer = give(me, Thing(("food",)), 5, service=season, where=here, valid=standing)
relay = OfferRegistry(RecordStore(blobs))
relay.publish(offer)
relay.attach_signature(offer.offer_id, sign_offer(offer, key))
relay.commit()
# announced as "relay-9"'s book, the offer still enters the fold: the
# signature recovers to its maker
```

### 8.5 Settlement as its own writer

Settlement, too, owns a book (on Swarm: its own feed). It *bases* that
book on a fold — and canonical addressing proves the base is honest,
because re-committing the same content must reproduce the same root:

```python
folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
settle = OfferRegistry(RecordStore(blobs))
settle.absorb(folded)
assert settle.commit() == manifest.book_root      # clone-verified

agent = SolverAgent(settle, catalogue, MockSettlement(settle, catalogue, clock=lambda: NOW))
agent.step(now=NOW)                               # settles the triangle

from loopmarket.federation import SETTLEMENT
agg.announce("settlement-0", settle.store, role=SETTLEMENT)
final = agg.fold()                                # fills fold back in
```

A **follower** needs nothing but the manifest and the blob space to read
the settled world — the settled loop, every fill, and a book on which a
second solver pass finds nothing. `examples/demo_federation.py` runs this
entire section as one narrated script; read it next.

## 9. Patterns: booking, capacity, routes

The offer form is deliberately small. Real-world shapes — appointment
books, limited seats, moving couriers — are *patterns over it*, usually
run by a **maker agent**: a bit of software at the maker's edge that
turns their calendar, stock or route into offers and tombstones.

### Booking: one offer per slot

Amara teaches one lesson at a time. She posts one offer per bookable
hour — the service window *is* the slot, and no two overlap:

```python
hour = 3_600
slots = [give("amara", Thing(("piano-lesson",), unit="lesson"), 100,
             service=TimeWindow(NOW + h * hour, NOW + (h + 1) * hour),
             where=here, valid=standing)
         for h in (9, 10, 11)]          # Monday 9–10, 10–11, 11–12
```

A settled loop marks the slot's offer filled **atomically** — that fill
*is* the booking, and any second loop wanting the same hour is rejected
with "already filled". There is no separate reservation step to race.
Taking Wednesday off is `withdraw()` on Wednesday's slots: the tombstone
survives federation folds, so the closure reaches everyone.

### Capacity: one offer per seat

A gym class holds three. Post three seat-offers with the same window —
**giving each its own `nonce`**, because equal content means equal id
(without the nonces, these three would collapse into *one* offer):

```python
seats = [give("gym", Thing(("spin-class",), unit="seat"), 10, nonce=i,
             service=tuesday_class, where=gym, valid=standing)
         for i in range(3)]
```

Three different bidders can each win a seat in one beat; the fourth finds
the class full. The same pattern is 30 box-offers for a van. The schema
can already *say* this more compactly — `Thing(("spin-class",), qty=15,
unit="seat", divisible=True)` — but settlement today fills an offer
whole; **partial fills are P2**: the clearing LP treats quantities as
flow capacities natively, and fill records grow settled quantities at the
next record bump. Until then, unit offers are the strict, working form.

### Routes: state as offers

A bicycle courier's feasibility depends on where he *is* — crossing town
takes time and costs him. The protocol never models his position; his
agent publishes it as **spacetime tubes**: several (window, disc) pairs
along the planned route, priced accordingly —

```python
pickup_a = give(courier, parcel_run, 5,             # near the station, cheap
               service=TimeWindow(NOW, NOW + hour),
               where=GeoDisc(46.05, 14.50, 2_000), valid=standing)
pickup_b = give(courier, parcel_run, 8,             # across town, later, dearer
               service=TimeWindow(NOW + 2 * hour, NOW + 3 * hour),
               where=GeoDisc(46.02, 14.55, 2_000), valid=standing)
```

— and as legs settle and his plan changes, the agent withdraws and
reposts between beats. Dynamic state quantizes to the beat; the book a
solver sees is always static and pinned.

### Where the sophistication lives (a design boundary)

Notice what these patterns have in common: loopmarket provides the basic
mechanisms and the means to express intentions — offers, atomic fills,
tombstones, pinned snapshots — and leaves the hard optimization to the
**solvers**. The solver in this repository is a deliberately simple
baseline, mainly for demonstration (and, later, the auction's reserve
want); professional solvers are expected to grow quickly *outside* the
loopmarket software — routing planners, statistical models, traditional
AI, LLMs, whatever wins. Their internals are not loopmarket's concern,
and they may well be kept secret for competitive edge: that is by
design, and healthy. The protocol's only demand is the one settlement
enforces — whatever a solver proposes gets re-verified from scratch, so
cleverness can be trusted *because* it is never trusted.

One honesty note for all three patterns: "blocked immediately" is as
strong as settlement's atomicity — airtight within one settlement
instance (P1's model). Global serialization across independent
settlement instances is what P2's verifiable settlement brings.

## 10. Bigger books: indexed candidate generation

The exhaustive give × want product is fine in memory. When it isn't,
`candidate_matches_indexed` prunes through the catalogue itself — gives are
filed under their concepts, exact service window and centre cell as
parametric dimension terms, and a want's candidates come from native
catalogue queries. It is **recall-exact**: provably the same matches as
the baseline (a test enforces set-equality), just fewer exact checks.

```python
from loopmarket import candidate_matches_indexed
matches = list(candidate_matches_indexed(everyone, catalogue, now=NOW))
```

The index is a derived, per-solver deepcopy of the catalogue — filing
offers never touches the shared catalogue or its pinned roots.

## 11. Going live on Swarm

Everything above runs unchanged against a real network; only the store
construction changes. You need a Bee node (a **light node suffices** for
all of this) and a **postage batch** — prefer a *mutable* one for
feed-heavy work (immutable batches reject writes once a bucket fills):

```bash
curl -s http://localhost:1633/stamps        # find a usable batch id
export BEE_API=http://localhost:1633
export BEE_BATCH=<batch id>
export BEE_SIGNER=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

The pieces:

```python
from loopmarket import swarm_offer_book               # a book on a feed
book = swarm_offer_book("my-book", api_url=BEE_API, stamp=BEE_BATCH,
                        signer=BEE_SIGNER)            # yours: pass signer
theirs = swarm_offer_book("my-book", api_url=BEE_API, stamp=BEE_BATCH,
                          owner="0x…")                # anyone else's: owner

from recordstore import swarm_store, BeeBytesStore, RecordStore
catalogue = Ontology.persistent(swarm_store("catalogue", api_url=BEE_API,
                                            stamp=BEE_BATCH, signer=BEE_SIGNER))
agg = Aggregator(lambda: RecordStore(BeeBytesStore(BEE_API, BEE_BATCH)))
```

Identity convention on Swarm: a maker's identity is their feed's owner
address — derive it with `maker_address(private_key_hex)` and use it as
the `maker` of every offer, so one key authenticates the feed, recovers
from detached signatures, and (in P2) faces the settlement contract.

Try it:

```bash
# the whole federation, live (also runs in memory without the env vars):
BEE_API=… BEE_BATCH=… PYTHONPATH=src python3 examples/demo_federation.py

# the gated live test suites:
BEE_API=… BEE_BATCH=… BEE_SIGNER=… python3 -m pytest \
    tests/test_swarm_book.py tests/test_swarm_federation.py -v
```

Operational honesty, from the P1 plan: postage TTL is the offer's *real*
lifetime (expired batch = silent, permanent loss — publication refuses
validity windows outstripping the batch, and you should watch
`batch_status()`); durability on a ~4,000-node network is a well-hedged
bet, not a custody arrangement; and one feed has one signer — sharing a
feed key is sharing your identity.

## 12. Where to go next

- **[REFERENCE.md](REFERENCE.md)** — every public class, function, record
  format and invariant, precisely.
- **[ARCHITECTURE.md](../ARCHITECTURE.md)** — why each piece is shaped the
  way it is, and what the architecture does not promise.
- **The plan corpus** (`docs/plans/`, indexed in the
  [README](../README.md)) — where the marketplace is going: batch
  auctions, verifiable settlement, the guarantee fabric, privacy.
- **The demos** — `examples/demo_triangle.py` (P0 in one file),
  `examples/demo_federation.py` (P1 in one file, memory or live).
