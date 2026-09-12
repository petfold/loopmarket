# loopmarket — User Guide

*A tutorial. You will build a catalogue, publish offers, watch a solver
find a loop nobody could see, clear it atomically, federate books across
makers, catch a forger, and put the whole thing on a live Swarm network.
Most of it happens at the command line — `loop`, a sibling of ontodag's
`odag` — and each step also shows the Python call it stands for, so the
same tutorial reads as an API tour. Every snippet is runnable as written;
run them in order. For the API in full detail, see the
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
surplus. **Clearing** trusts no solver: it re-verifies every leg from
scratch and commits the whole loop atomically, or not at all.

## 1. Installation

```bash
pip install loopmarket             # gives you the `loop` command (and `odag`)
```

or, to work on it:

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
| `.[sig]` | `eth-keys` | detached offer signatures (§8.4), a key as your identity |

The core has two dependencies — `ontodag` (the catalogue) and
`recordstore` (the book) — and works fully offline; Swarm is a persistence
backend chosen at the edges, never a requirement of the model.

Two commands, one grammar. `odag` edits the catalogue; `loop` speaks
offers. Both keep a config file (`~/.ontodag/config`, `~/.loopmarket/config`)
with the same `key = value` format and the same precedence rule — flag,
then environment, then config, then default — and `loop` inherits from
`odag` what the two share: the Bee node settings, and odag's active store
as the default catalogue. Type `loop` alone at a terminal and you get a
prompt, exactly as with `odag`; pipe a file into it and it runs the lines
as a script (§8 does).

## 2. The catalogue

Matching needs one question answered: *does the offered thing satisfy the
wanted description?* The catalogue is an OntoDAG ordered by fits-within,
and you build it with `odag put CHILD PARENT...`:

```console
$ odag put service
$ odag put lesson service
$ odag put music-lesson lesson
$ odag put piano-lesson music-lesson
$ odag put repair service
$ odag put bicycle-repair repair
$ odag put food
$ odag put produce food
$ odag put local
$ odag put weekly
$ odag put vegetable-box produce local weekly
```

Ask it questions the way matching will:

```console
$ odag below piano-lesson music-lesson      # does piano fit within music?
true
$ odag below music-lesson piano-lesson      # not the reverse!
false
$ odag get produce weekly                   # everything that is both
vegetable-box
$ odag get mystery-goods                    # nothing: no such category
```

Invariant **U7: vocabulary fails closed.** An unknown category never
matches — silent drift breaks loudly, by design — and `loop` refuses to
publish an offer that names one (`loop: unknown category: mystery-goods —
vocabulary fails closed (U7)`).

Where does the catalogue live? In odag's **active store**: a plain `.od`
file by default, or — for anything beyond a toy — a content-addressed
record store with a canonical root that offers can **pin**:

```console
$ odag set store rs:~/.ontodag/catalogue     # versioned, with a root
$ odag status
store = rs:/home/you/.ontodag/catalogue
root = 7c1e…
```

`loop` reads that same store as its catalogue unless you point it
elsewhere (`loop set catalogue SPEC`, any odag store spec). Offers written
against a pinned catalogue name its root, the dimension-registry version
and the contract version; **a pinned catalogue refuses unpinned offers**
during matching, and offers with mismatched pins never pair — the
semantic ground cannot move under a committed loop. (An unpinned `.od`
catalogue is the development mode: everything unpinned matches, nothing is
demanded. The rest of this guide runs in that mode.)

*The same in Python:*

```python
from loopmarket import Ontology

catalogue = Ontology().load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})
catalogue.covers("music-lesson", "piano-lesson")               # True
catalogue.satisfies(("vegetable-box",), ("produce", "weekly"))  # True
catalogue.satisfies(("mystery-goods",), ("mystery-goods",))     # False (U7)

# persistent, hence pinnable:
from recordstore import MemoryBytesStore, RecordStore
catalogue = Ontology.persistent(RecordStore(MemoryBytesStore()))
catalogue.load({...}); catalogue.commit()
catalogue.pins   # {'ontology_root': '…', 'registry_version': '4.1', 'contract_version': '0.1'}
```

## 3. Your first offer

Tell `loop` who you are and where you are. A place is a **catalogue
node** — vocabulary, like everything else — created with its coordinates
and a radius, and named from then on:

```console
$ loop set maker amara
$ loop place home 46.05,14.50,5km
$ loop set where home
```

(`set` is durable: it writes `~/.loopmarket/config`. `loop set` alone
lists every setting in force; `loop set where` shows one.) Now the offer.
There are exactly two verbs — **give** and **want** — and a bare number
last is the price, on your own scale:

```console
$ loop give piano-lesson 100
give     piano-lesson
  maker    amara
  quantity 1 unit — 1, indivisible
  price    100 (100/unit, on amara's scale)
  service  2026-09-12T05:58:42Z .. 2026-12-11T05:58:42Z
           local 2026-09-12 07:58 CEST .. 2026-12-11 06:58 CET
  valid    2026-09-12T05:58:42Z .. 2026-10-12T05:58:42Z
           local 2026-09-12 07:58 CEST .. 2026-10-12 07:58 CEST
  where    46.05,14.5 radius 5000m
  pins     catalogue -  registry 4.1  contract 0.1  v2
  terms    bond 0  oracle countersign  arbitrator -
  nonce    1789192722000
  offer_id 8804427fa09d64a87cebb844b3d0d14dd6ea4590471e2dc70f299f312d342584
  note     place home
publish? [y/N] y
8804427fa09d64a87cebb844b3d0d14dd6ea4590471e2dc70f299f312d342584
```

**Nothing publishes unseen.** What you approved is the fully resolved
offer — every default expanded, relative times made absolute in UTC *and*
your local zone, the place's coordinates read back from the catalogue so
a stale `home` is visible, the id it will receive — and `loop show ID`
prints exactly this block later. The defaults it filled in are settings:
`when` (the service window, `..+90d` = from now for ninety days), `valid`
(how long the offer stands, `30d`), `where`. Say `y` and the id is printed:
publishing is a commitment, and the id is what `withdraw` needs.

The second flavour:

```console
$ loop want produce local weekly 104
want     local produce weekly
  maker    amara
  ...
  price    104 (104/unit, on amara's scale)
```

Things to notice:

- **The ratio is the information.** Amara priced the box at 104 against
  lessons at 100 — she values a season of boxes at 1.04 lessons. The
  absolute numbers mean nothing; only ratios on one scale do, and because
  every quote shares one denominator her quotes can never contradict each
  other (nobody can arbitrage Amara against her own rate matrix).
- **A thing is a conjunction of catalogue categories.** `produce local
  weekly` means all three at once, in any order (the record sorts them).
- **The grammar is ontodag's, plus two conventions.** A bare word is a
  category; `head(param)` is a term in ontodag's spelling (quote the
  parentheses in a shell); a bare number *first* is the quantity and a
  bare number *last* is the price. So `loop give 10kg apple 100` gives up
  to ten kilos, divisible, priced 100 the lot; `loop give 3 bicycle 900`
  gives three indivisible bicycles. Three heads are interpreted onto the
  offer's fields — `when(...)`, `where(...)`, `valid(...)` — and every
  other term goes into the description:

  ```console
  $ loop give piano-lesson 'when(2026-10-01..2026-12-20)' 'valid(2h)' 100
  $ odag pack prelude                        # the standard dimension heads
  $ odag put from prefix-dimension           # a role, as ontodag's guide does
  $ odag put ride service
  $ loop want ride 'from(home)' 'when(today..+7d)' 5
  want     from(u24m) ride
  ...
    note     from(home) → from(u24m)
  ```

  In the last line ontodag interprets the *name*: `home` hangs under its
  geo cell, so the published term is `from(u24m)` — public vocabulary
  that matches by prefix containment (`from(u24m)` fits within
  `from(u2)`), ontodag's London→Rome pattern — and the approval block
  says so. Your private name never leaves your machine; its value does.
- **An omitted price is your last unit price** for the same side and the
  same bare categories, scaled by quantity, read from your own book, and
  marked in the block (`note price 100 reused: unit price 100/unit from
  offer 8804427fa09d (3d ago)`). No earlier offer means an error, never a
  guess.
- **Offers are immutable values with a content address.** Equal content
  means equal id, always — concept order doesn't matter, but every
  meaningful field does, and a fresh intention gets a fresh `nonce`
  automatically, hence a fresh id.

*The same in Python:*

```python
from loopmarket import Thing, TimeWindow, GeoDisc, give, want

NOW = 1_700_000_000                       # fix time; determinism is a feature
season   = TimeWindow(NOW, NOW + 90 * 86_400)     # when the service happens
standing = TimeWindow(NOW - 1, NOW + 30 * 86_400) # while the offer stands
here     = GeoDisc(46.05, 14.50, 5_000)           # 5 km around a point

teach = give("amara", Thing(("piano-lesson",)), 100,
            service=season, where=here, valid=standing)
eat = want("amara", Thing(("produce", "local", "weekly")), 104,
          service=season, where=here, valid=standing)
teach.offer_id, teach.kind, teach.unit_price      # '…64 hex…', 'give', 100.0
```

(Order-book readers: a *give* is the ask and a *want* is the bid —
`ask`/`bid` remain available as exact synonyms.)

## 4. The book

Your offers went into your **book**: a versioned keyspace over a record
store — every committed state is one root reference, and equal content
means equal root. By default it is `rs:~/.loopmarket/book`; `loop set
book SPEC` (or `-f SPEC` for one run) moves it, and §11 puts it on Swarm.

```console
$ loop mine
id            side  maker  qty     thing                 price  state
8804427fa09d  give  amara  1 unit  piano-lesson          100    open
f069ede6a44c  want  amara  1 unit  local produce weekly  104    open
$ loop status
book = rs:/home/you/.loopmarket/book
book root = eb461dcb528a4e8f374a9cb49f80cc9faf1e399039d664905be7947810f303a7
offers = 2 (filled 0, withdrawn 0)
catalogue = /home/you/.ontodag/store.od
catalogue root = (unpinned)
categories = 33
peers = (none)
maker = amara
...
```

Three operations you'll want:

- **`loop show ID`** — any offer, by content address or a unique prefix,
  as the same block you approved, plus its state (open, filled,
  withdrawn, expired). At a terminal `mine` and `offers` print tables; in
  a pipe, tab-separated lines (`loop mine | cut -f1`), and `--raw` /
  `--render` force either.
- **`loop withdraw ID`** closes an offer forever — as a *tombstone*, an
  add rather than a delete, so the exit survives merges with peers who
  haven't heard yet. Re-publishing identical content does not resurrect
  it; a fresh intention is a fresh offer. A filled offer cannot be
  withdrawn: a cleared leg is an obligation.
- **`loop export` / `loop import [FILE]`** move offers as JSON lines of
  their canonical records; ids survive the trip, because the record *is*
  the identity.

*The same in Python:*

```python
from loopmarket import OfferRegistry

registry = OfferRegistry(RecordStore(MemoryBytesStore()))
registry.publish(teach); registry.publish(eat)
root = registry.commit()                 # one root names the whole book state
list(registry.offers(now=NOW))           # active offers (filters closed ones)
registry.get(teach.offer_id)             # any offer, by content address
registry.withdraw(eat.offer_id)          # the tombstone
root, frozen = registry.snapshot()       # a self-consistent view a solver works on
```

`snapshot()` is what every solver reads: everything downstream
(proposals, receipts) pins such roots — reproducibility and auditability
beat freshness (invariant U4). `commit()` converges with concurrent
writers by three-way merge and then verifies that no cleared loop lost a
leg in the merge (invariant U11; `PartialLoopError` rather than damage).

## 5. Matching

A **match** is one feasible handoff: this give satisfies that want. Bruno
grows vegetables and wants his delivery bikes fixed. He is another maker,
so for this tutorial we speak as him with a flag (in life he has his own
book, own machine, own key — §8):

```console
$ loop --maker bruno place farm 46.10,14.55,15km
$ loop --maker bruno give vegetable-box 'where(farm)' 50
$ loop --maker bruno want bicycle-repair 'where(farm)' 52
$ loop matches
bruno gives vegetable-box to amara (wants local produce weekly) rate 2.08  04264773e2f4>f069ede6a44c
```

Bruno's box is a `vegetable-box`; Amara wants `produce local weekly`; the
catalogue says the first fits within all three, the discs intersect, the
windows overlap, the units agree — a match, at rate 104/50 = 2.08 (the
want's unit price over the give's). `matches` exits 1 when there are
none, so it reads as a predicate in scripts.

*The same in Python:*

```python
from loopmarket import check_match, candidate_matches

grow = give("bruno", Thing(("vegetable-box",)), 50,
           service=season, where=GeoDisc(46.10, 14.55, 15_000), valid=standing)
m = check_match(grow, eat, catalogue, now=NOW)
m.rate, m.giver, m.receiver          # 2.08, 'bruno', 'amara'
```

`check_match` is exact and self-contained — cheap to re-run, which is what
lets clearing re-verify without trusting anyone. Its gates, in order:
kinds and distinct makers → validity windows open at `now` → service
windows intersect → service discs intersect (a handover point exists) →
quantity/divisibility/unit → **version pins** (mixed pinning refuses;
pinned catalogues refuse unpinned offers; major registry/contract skew
refuses) → catalogue subsumption. `candidate_matches(offers, catalogue,
now=...)` runs it over the full give × want product — fine in memory, and
§10 shows the indexed generator for bigger books.

## 6. Loops

Rates multiply around a cycle. If the product exceeds 1, the slack is
real, distributable surplus. Chen fixes bicycles, and her daughter wants
piano lessons:

```console
$ loop --maker chen place shop 46.06,14.51,4km
$ loop --maker chen give bicycle-repair 'where(shop)' 80
$ loop --maker chen want music-lesson 'where(shop)' 83
$ loop matches
amara gives piano-lesson to chen (wants music-lesson) rate 0.83  8804427fa09d>c2a5b1cc6fa2
bruno gives vegetable-box to amara (wants local produce weekly) rate 2.08  04264773e2f4>f069ede6a44c
chen gives bicycle-repair to bruno (wants bicycle-repair) rate 0.65  16d64f611fe1>52c3336cda86
$ loop loops
loop 62067f2d29397be8… surplus 12.22%
  amara gives piano-lesson to chen (rate 0.83)
  chen gives bicycle-repair to bruno (rate 0.65)
  bruno gives vegetable-box to amara (rate 2.08)
```

Amara teaches piano but wants vegetables; Bruno grows vegetables but wants
bicycle repair; Chen fixes bicycles and her daughter wants piano lessons.
**No two of them can trade** — look at `matches`: three handoffs, each
useless alone — and the triangle clears at 0.83 × 0.65 × 2.08 = 1.1222,
a 12.22% surplus. `loops` searches a pinned snapshot of the book and
prints; it never clears. Under the hood this is Bellman–Ford hunting
negative cycles in −log(rate) weights, iterated in sorted order so **the
same book yields the same loop on every replica** (invariant U6 —
determinism is what later makes the baseline solver the auction's reserve
bid). Exit code 1 means nothing profitable, so `loop loops && loop clear`
reads naturally.

*The same in Python:*

```python
from loopmarket import ExchangeGraph

fix   = give("chen", Thing(("bicycle-repair",)), 80,
            service=season, where=GeoDisc(46.06, 14.51, 4_000), valid=standing)
learn = want("chen", Thing(("music-lesson",)), 83,
            service=season, where=GeoDisc(46.06, 14.51, 4_000), valid=standing)
wheels = want("bruno", Thing(("bicycle-repair",)), 52,
             service=season, where=GeoDisc(46.10, 14.55, 15_000), valid=standing)

everyone = [teach, eat, grow, wheels, fix, learn]
graph = ExchangeGraph.from_matches(candidate_matches(everyone, catalogue, now=NOW))
loop = graph.find_profitable_loop()
loop.nodes, loop.product, loop.loop_id   # ('amara','chen','bruno'), 1.1222…, '…'
```

## 7. Clearing

Clearing's one non-negotiable: **trust no solver** (invariant U3). A
proposal names the roots it was solved against; clearing re-derives
every leg against the *current* book with its own catalogue, re-checks
pins, oracles, fills, tombstones and the arithmetic, and only then
commits — all fills and the loop record under one new root, atomically.
`loop clear` runs that clearing house locally, over your book:

```console
$ loop clear
cleared 62067f2d29397be8… surplus 12.22%
  amara gives piano-lesson to chen (rate 0.83)
  chen gives bicycle-repair to bruno (rate 0.65)
  bruno gives vegetable-box to amara (rate 2.08)
book root 9b49b3ea8983b3cd91aa67ff26c84124f9642cd8eaafc2d1e5ce2310b460ec89
$ loop loops; echo $?
1
$ loop show 8804427fa09d | tail -1
  state    filled
$ loop withdraw 8804427fa09d
loop: 8804427fa09d is filled: a cleared leg is an obligation
```

Six fills and one loop record landed under one root; a second search
finds nothing; the filled legs are obligations now. Rejections print to
stderr with their reason — unknown, filled or withdrawn offers, legs that
fail re-verification, pins that don't equal clearing's own, oracle types
it cannot verify (the mock verifies only `countersign`), surplus below
threshold, indivisible legs without per-node surplus — and `clear` exits
1 when nothing cleared.

*The same in Python:*

```python
from loopmarket import MockClearing, LoopProposal

clearing = MockClearing(registry, catalogue, clock=lambda: NOW)
# (registry must hold all six offers; publish grow/wheels/fix/learn + commit)
proposal = LoopProposal(loop, book_root=registry.store.root,
                        ontology_root=catalogue.root, solver="me", found_at=NOW)
receipt = clearing.submit(proposal)
receipt.accepted, receipt.book_root          # True, the new root
clearing.submit(proposal).accepted           # False: "already filled"
```

## 8. The solver agent — and then federation

Everything above, as one loop of one method — and as one script. The
whole tutorial so far is `examples/triangle.loop`, run in a scratch home
so its `set` lines don't touch yours:

```bash
LOOP_HOME=$(mktemp -d) loop --catalogue examples/triangle.od < examples/triangle.loop
```

```
set confirm off
set now 2026-09-12T00:00:00Z
place amara_flat 46.05,14.50,5km
place bruno_farm 46.10,14.55,15km
place chen_shop 46.06,14.51,4km
set maker amara
give piano-lesson where(amara_flat) 100
want produce local weekly where(amara_flat) 104
set maker bruno
give vegetable-box where(bruno_farm) 50
want bicycle-repair where(bruno_farm) 52
set maker chen
give bicycle-repair where(chen_shop) 80
want music-lesson where(chen_shop) 83
loops
clear
```

Two things about scripts. Parentheses need no quoting inside a `loop`
script or at the `loop` prompt — only a shell wants them quoted. And
`confirm auto` (the default) asks at a terminal but proceeds in a batch,
*except* that a line whose price was **reused** refuses: a script that
omits a price would publish a number nobody saw, so it fails closed and
names the way out (type the price, or `set confirm off` when you mean
it). `set now` fixes the clock, so the script produces the same ids and
the same `loop_id` on every run — the Python demo, `examples/demo_triangle.py`,
is the same triangle through the API:

```python
from loopmarket import SolverAgent

agent = SolverAgent(registry, catalogue, clearing)
receipts = agent.step(now=NOW)   # snapshot → match → graph → hunt → propose
```

Now the part that makes it a *marketplace* rather than a database: nobody
shares a book. Each maker has their own — on Swarm their own feed and
signing key, so **feed ownership is the authenticity** of their offers —
and readers **fold** the books they know about. At the command line that
is the `peers` setting: `loop set peers rs:/path/to/bruno,swarm:chen-book@0x…`
and every `offers`, `matches`, `loops` and `clear` answers over the union
of your book and theirs. (Today that union trusts its peers; the admission
rules below arrive at the command line with the `fold` command, since
they need each book's owner.) The federation proper is the API's, for
now — `examples/demo_federation.py` runs this whole section as one
narrated script.

### 8.1 One book per maker

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

You don't even need the second aggregator to convict the first. Its
`announcement_root` is its own claim about which books, at which roots,
it folded; whatever one of those books holds that neither entered
`book_root` nor earned a `reject/` record was dropped silently:

```python
from loopmarket import audit_manifest
from recordstore import ABSENT, verify_proof

for o in audit_manifest(manifest, blobs):       # [] for an honest fold
    print(o.owner, o.key)                        # whose speech went missing
    assert verify_proof(o.proof, manifest.book_root) is ABSENT   # no store needed
```

Each omission carries a recordstore absence proof, so the accusation
travels as bytes. Tombstones are audited too — an aggregator that folds
an offer but eats its withdrawal has resurrected it. And a solver that
trusts no manifest can fold the announced books itself (the
announcement names them) and lands on the honest `book_root`; manifests
are caches, never authority. `examples/demo_federation.py` runs the whole
scene with a censoring aggregator called Cain.

### 8.3 The fold rules

Announced books are sanitized per record before entering the fold,
fail-closed: an offer's content address is re-derived; an offer whose
maker isn't the book's owner needs a valid detached signature or dies;
tombstones are admitted only from the book that owns the offer;
`fill/`/`loop/` keys are believed only from clearing-role books. Try
the forgery yourself:

```python
mallory = OfferRegistry(RecordStore(blobs))
mallory.publish(give("amara", Thing(("piano-lesson",)), 1,
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
inside it — ids stay stable). Needs `.[sig]`. At the command line this is
automatic: set `bee_signer` (the same key that owns your Swarm feed), and
with `maker` unset your identity *is* that key's address, and every
`give`/`want` attaches its signature.

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

### 8.5 Clearing as its own writer

Clearing, too, owns a book (on Swarm: its own feed). It *bases* that
book on a fold — and canonical addressing proves the base is honest,
because re-committing the same content must reproduce the same root.
`loop clear` with `peers` set does exactly this first ("book re-based on
the fold"):

```python
folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
clear = OfferRegistry(RecordStore(blobs))
clear.absorb(folded)
assert clear.commit() == manifest.book_root      # clone-verified

agent = SolverAgent(clear, catalogue, MockClearing(clear, catalogue, clock=lambda: NOW))
agent.step(now=NOW)                               # clears the triangle

from loopmarket.federation import CLEARING
agg.announce("clearing-0", clear.store, role=CLEARING)
final = agg.fold()                                # fills fold back in
```

A **follower** needs nothing but the manifest and the blob space to read
the cleared world — the cleared loop, every fill, and a book on which a
second solver pass finds nothing.

## 9. Patterns: booking, capacity, routes

The offer form is deliberately small. Real-world shapes — appointment
books, limited seats, moving couriers — are *patterns over it*, usually
run by a **maker agent**: a bit of software at the maker's edge that
turns their calendar, stock or route into `loop` lines and tombstones.

### Booking: one offer per slot

Amara teaches one lesson at a time. She posts one offer per bookable
hour — the service window *is* the slot, and no two overlap:

```console
$ odag put spin-class service; odag put parcel-run service   # vocabulary for this section
$ loop give piano-lesson 'when(2026-10-05T09:00:00Z..2026-10-05T10:00:00Z)' 100
$ loop give piano-lesson 'when(2026-10-05T10:00:00Z..2026-10-05T11:00:00Z)'
$ loop give piano-lesson 'when(2026-10-05T11:00:00Z..2026-10-05T12:00:00Z)'
```

(The second and third reuse the first's price — the block says so.) A
cleared loop marks the slot's offer filled **atomically** — that fill
*is* the booking, and any second loop wanting the same hour is rejected
with "already filled". There is no separate reservation step to race.
Taking Wednesday off is `loop withdraw` on Wednesday's slots: the
tombstone survives federation folds, so the closure reaches everyone.

### Capacity: one offer per seat

A gym class holds three. Post three seat-offers with the same window —
the same line three times. Equal content means equal id, but `loop` gives
every offer a fresh nonce, so the three stay three:

```console
$ loop --maker gym place gym 46.05,14.52,1km
$ loop --maker gym give spin-class 'where(gym)' 'when(2026-10-07T18:00:00Z..2026-10-07T19:00:00Z)' 10
$ loop --maker gym give spin-class 'where(gym)' 'when(2026-10-07T18:00:00Z..2026-10-07T19:00:00Z)'
$ loop --maker gym give spin-class 'where(gym)' 'when(2026-10-07T18:00:00Z..2026-10-07T19:00:00Z)'
```

(In Python the same needs an explicit `nonce=i` per seat.) Three
different bidders can each win a seat in one beat; the fourth finds the
class full. The same pattern is 30 box-offers for a van. The schema can
already *say* this more compactly — `loop give 15seat spin-class 150`,
a divisible quantity — but clearing today fills an offer whole;
**partial fills are P2**: the clearing LP treats quantities as flow
capacities natively, and fill records grow cleared quantities at the
next record bump. Until then, unit offers are the strict, working form.

### Routes: state as offers

A bicycle courier's feasibility depends on where he *is* — crossing town
takes time and costs him. The protocol never models his position; his
agent publishes it as **spacetime tubes**: several (window, place) pairs
along the planned route, priced accordingly —

```console
$ loop --maker courier place station 46.05,14.50,2km
$ loop --maker courier place eastside 46.02,14.55,2km
$ loop --maker courier give parcel-run 'where(station)'  'when(now..+1h)'  5   # near the station, cheap
$ loop --maker courier give parcel-run 'where(eastside)' 'when(+2h..+3h)'  8   # across town, later, dearer
```

— and as legs clear and his plan changes, the agent withdraws and
reposts between beats. Dynamic state quantizes to the beat; the book a
solver sees is always static and pinned.

### Bundles: a composed want

A theatre ticket is worthless if you cannot get there, and the ride is
worthless without the ticket. Neither the theatre nor the bus company
cares; only you do, so the coupling lives in *your* want, as **parts**
that clear together or not at all. Stage the parts, look at them, compose:

```console
$ loop draft want theatre-ticket hamlet 'when(2026-10-05T19:00:00Z..2026-10-05T22:00:00Z)' 'where(venue)'
1  want hamlet theatre-ticket when(2026-10-05T19:00:00Z..2026-10-05T22:00:00Z) where(46.051,14.506,100m)
$ loop draft want transport person 'from(home)' 'to(venue)' 'when(2026-10-05T17:00:00Z..2026-10-05T19:00:00Z)'
2  want from(u24m) person to(u24mfp) transport when(2026-10-05T17:00:00Z..2026-10-05T19:00:00Z) where(46.05,14.5,5000m)
$ loop drafts                # canonical lines, your spelling as notes beneath
$ loop compose 60            # all drafts, one price for the lot; `compose 1 2 60` picks
```

Or on one line, for scripts and assistants — `+` between parts, one price
last:

```console
$ loop want theatre-ticket hamlet 'when(...)' 'where(venue)' + transport person 'from(home)' 'to(venue)' 'when(...)' 60
```

Drafts live in a local file, never in the book: a draft is not an offer,
has no price and no id, and nobody can match it. Parts carry no prices —
you price the bundle once and clearing splits it across the gives — and
there is no cross-part constraint language: the ride arriving before
curtain is you spelling the two windows. Today `compose` and the `+` line
render the whole composed block and then **refuse**: the record cannot
carry parts until the v3 bump (`docs/plans/cli.md` §13). Composition is
want-side only. A kit that ships in one box is one indivisible give; a
class that only runs if eight enrol is a *minimum fill* on one give, also
v3; and "sirloin to one buyer, mince to another, only if the whole animal
sells" is the door the design keeps shut — that is a butcher's job.

### Where the sophistication lives (a design boundary)

Notice what these patterns have in common: loopmarket provides the basic
mechanisms and the means to express intentions — offers, atomic fills,
tombstones, pinned snapshots — and leaves the hard optimization to the
**solvers**. The solver behind `loop loops` is a deliberately simple
baseline, mainly for demonstration (and, later, the auction's reserve
want); professional solvers are expected to grow quickly *outside* the
loopmarket software — routing planners, statistical models, traditional
AI, LLMs, whatever wins. Their internals are not loopmarket's concern,
and they may well be kept secret for competitive edge: that is by
design, and healthy. The protocol's only demand is the one clearing
enforces — whatever a solver proposes gets re-verified from scratch, so
cleverness can be trusted *because* it is never trusted. The same
boundary holds above the command line: an assistant that drafts offers
for you produces the same `loop` lines a person would, and the approval
block is identical whichever typed them.

One honesty note for all three patterns: "blocked immediately" is as
strong as clearing's atomicity — airtight within one clearing
instance (P1's model). Global serialization across independent
clearing instances is what P2's verifiable clearing brings.

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
changes. You need a Bee node (a **light node suffices** for all of this)
and a **postage batch** — prefer a *mutable* one for feed-heavy work
(immutable batches reject writes once a bucket fills). Configure the node
once, in odag; `loop` inherits it:

```console
$ curl -s http://localhost:1633/stamps        # find a usable batch id
$ odag set bee_api http://localhost:1633
$ odag set bee_batch <batch id>
$ odag set bee_signer generate                 # your key: feed owner AND maker identity
$ odag set store swarm:catalogue               # the catalogue, on your feed
$ loop set book swarm:my-book                  # your book, on your feed
$ loop set maker                               # (unset: your identity is the key's address)
$ loop give piano-lesson 100
```

Each `give` is now a feed update — a couple of seconds on a light node —
and the book is readable by anyone who knows your address and topic:

```console
$ loop set peers swarm:my-book@0xYourAddress    # on another machine
$ loop offers
```

Identity convention on Swarm: a maker's identity is their feed's owner
address — one key authenticates the feed, recovers from detached
signatures (attached automatically), and (in P2) faces the clearing
contract. The triangle script runs live unchanged, `loop -f swarm:TOPIC
--catalogue examples/triangle.od < examples/triangle.loop` — about two
minutes for seven commits, and a fresh session on the same topic reads
the six fills back.

*The same in Python:*

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

Try the whole federation live, and the gated test suites:

```bash
BEE_API=… BEE_BATCH=… PYTHONPATH=src python3 examples/demo_federation.py
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

- **`loop help`** — every command and setting on one screen; the design
  record with its reasons is [`docs/plans/cli.md`](plans/cli.md).
- **[REFERENCE.md](REFERENCE.md)** — every public class, function, record
  format and invariant, precisely, and the command line's grammar and
  settings tables.
- **[ARCHITECTURE.md](../ARCHITECTURE.md)** — why each piece is shaped the
  way it is, and what the architecture does not promise.
- **The plan corpus** (`docs/plans/`, indexed in the
  [README](../README.md)) — where the marketplace is going: batch
  auctions, verifiable clearing, the guarantee fabric, privacy.
- **The demos** — `examples/triangle.loop` (P0 as a script),
  `examples/demo_triangle.py` (the same through the API),
  `examples/demo_federation.py` (P1 in one file, memory or live).
