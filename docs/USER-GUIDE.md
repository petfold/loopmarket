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
| `.[swarm]` | `recordstore[bee,feeds]` | running against a live Bee node (§11); reading a feed's signed sequence of roots (§7.5) |
| `.[sig]` | `swarmfs[feeds]`, `coincurve`, `cryptography`, `eth-hash` | detached offer signatures (§8.4), a key as your identity |
| `.[chain]` | `web3` | the contracts on Gnosis: announcements, beats, the escrow (§7.2, §11.1) |
| `.[evm]` | `web3`, `py-solc-x`, `eth-tester` | compiling the contracts and running them on a local EVM (the contract tests) |

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
wanted description?* The catalogue is an OntoDAG ordered by fits-within.
It is what every maker shares, so this tutorial keeps it in a file of its
own, `market.od`, and builds it with `odag -f market.od put CHILD
PARENT...` (run everything from one directory, or give the full path):

```console
$ odag -f market.od prelude                 # the standard dimensions: geo, time, mass, ...
$ odag -f market.od put handover
$ odag -f market.od put geo handover        # where and when a thing changes hands
$ odag -f market.od put time handover
$ odag -f market.od put service
$ odag -f market.od put lesson service
$ odag -f market.od put music-lesson lesson
$ odag -f market.od put piano-lesson music-lesson
$ odag -f market.od put repair service
$ odag -f market.od put bicycle-repair repair
$ odag -f market.od put food
$ odag -f market.od put produce food
$ odag -f market.od put local
$ odag -f market.od put weekly
$ odag -f market.od put vegetable-box produce local weekly
$ loop set catalogue market.od
```

The two `handover` lines tell matching that a bare place or time in an
offer says where or when the thing changes hands, and that those match
when one side contains the other (§3). Everything else matches one way:
the give fits within the want. Ask the catalogue questions the way
matching will:

```console
$ odag -f market.od below piano-lesson music-lesson    # does piano fit within music?
true
$ odag -f market.od below music-lesson piano-lesson    # not the reverse!
false
$ odag -f market.od get produce weekly                 # everything that is both
vegetable-box
$ odag -f market.od get mystery-goods                  # nothing: no such category
```

Invariant **U7: vocabulary fails closed.** An unknown category never
matches — silent drift breaks loudly, by design — and `loop` refuses to
publish an offer that names one (`loop: unknown category: mystery-goods —
vocabulary fails closed (U7); `odag put mystery-goods PARENT` adds it to
the catalogue`).

A plain `.od` file has no root, so nothing can pin it: this is the
development mode, where every unpinned offer matches every other. For
anything beyond a toy the catalogue is a content-addressed record store
whose canonical root offers **pin**:

```console
$ odag -f rs:catalogue merge market.od
$ odag -f rs:catalogue status
store = rs:/home/you/catalogue
root = 989ae9d1d52108cf1583a3aae1f1749c77992666dc75c160d3b36b652d4e32de
...
$ loop set catalogue rs:catalogue
```

Offers written against it name its root, the dimension-registry version
and the contract version (`pins catalogue 989ae9d1d52108cf registry 4.2
contract 0.1` in the block of §3). **A pinned catalogue refuses unpinned
offers** during matching, and offers with mismatched pins never pair — the
semantic ground cannot move under a committed loop. The rest of this guide
uses the unpinned `market.od`.

Your own **places** are not in that file. `loop place` (§3) files them in
odag's active store — `~/.ontodag/store.od` by default, your *personal*
store — which nobody else reads. A name only you know cannot stand in a
public offer, so it is published as the cell it hangs under. A place
everyone shares (a shop, a city) belongs in the catalogue and stands as
spelled. (Without `set catalogue`, `loop` reads odag's active store as
both: fine for one person, but then your places are catalogue vocabulary.)

*The same in Python:*

```python
from loopmarket import Ontology

catalogue = Ontology().load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})
catalogue.declare_handover(["geo", "time"])             # where and when match either way
catalogue.declare_roles({"from": "geo", "to": "geo"})   # a route's two ends
catalogue.covers("music-lesson", "piano-lesson")               # True
catalogue.satisfies(("vegetable-box",), ("produce", "weekly"))  # True
catalogue.satisfies(("mystery-goods",), ("mystery-goods",))     # False (U7)

# persistent, hence pinnable:
from recordstore import MemoryBytesStore, RecordStore
pinned = Ontology.persistent(RecordStore(MemoryBytesStore()))
pinned.load({"service": [], "lesson": ["service"]}); pinned.commit()
pinned.pins   # {'ontology_root': '…', 'registry_version': '4.2', 'contract_version': '0.1'}
```

## 3. Your first offer

Tell `loop` who you are and where you are. A place is given by its
coordinates and a radius, and named from then on:

```console
$ loop set maker amara
$ loop place home 46.05,14.50,5km
$ loop set terms home
```

(`set` is durable: it writes `~/.loopmarket/config`. `loop set` alone
lists every setting in force; `loop set terms` shows one. `terms` are
added to every offer whose line does not already say where (or, for a
time in `terms`, when) — leave it unset and an offer is anywhere, any
time.) Now the offer.
There are exactly two verbs — **give** and **want** — and a bare number
last is the price, on your own scale:

```console
$ loop give piano-lesson 100
give     geo(u24) piano-lesson
  maker    amara
  quantity 1 unit — 1, indivisible
  price    100 (100/unit, on amara's scale)
  valid    2026-10-01T06:00:00Z .. 2026-10-31T06:00:00Z
           local 2026-10-01 08:00 CEST .. 2026-10-31 07:00 CET
  pins     catalogue -  registry 4.2  contract 0.1  v4
  terms    bond 0  oracle countersign  arbitrator -
  nonce    1790834400000
  offer_id b7d0e7661d218a5fe50456324e594a8f0c00706ca4e9e3e499a1b5f8705ac7a1
  note     default home
  note     home → geo(u24)
publish? [y/N] y
b7d0e7661d218a5fe50456324e594a8f0c00706ca4e9e3e499a1b5f8705ac7a1
```

**Nothing publishes unseen.** What you approve is the fully resolved
offer: every default expanded, relative times made absolute in UTC *and*
your local zone, your private `home` replaced by the public cell it hangs
under (`geo(u24)`; a stale `home` would be visible here), and the id it
will receive. `loop show ID` prints exactly this block later. The defaults
it filled in are settings: `terms` (here `home`; add a `time(...)` if you
mean a window — without one the offer is any time) and `valid` (how long
the offer stands, `30d`; `valid(2026-10-01..)` stands until withdrawn).
Say `y` and the id is printed: publishing is a commitment, and the id is
what `withdraw` needs. (In a script, with no terminal to ask at, `confirm
auto` publishes without asking — unless a price was reused, below.)

The second flavour:

```console
$ loop want produce local weekly 104
want     geo(u24) local produce weekly
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
  gives three indivisible bicycles. Every term goes into the description.
  A bare place, cell or `time(...)` window says where and when the thing
  changes hands, and matches when one side contains the other: a give
  anywhere in a cell serves a want at a point in it, and the reverse.
  Only `valid(...)` is the offer's own field, how long it stands:

  ```console
  $ loop give piano-lesson 'time(2026-10-05..2026-12-20)' 'valid(2h)' 100
  give     geo(u24) piano-lesson time(2026-10-05T00:00:00Z..2026-12-20T23:59:59Z)
  ...
  ```

  A route has two ends of one kind, so they are *roles* of `geo`, declared
  once in the catalogue (`odag -f market.od put from geo`, and `put ride
  service` for the thing):

  ```console
  $ loop want ride 'from(home)' 'time(today..+7d)' 5
  want     from(u24) geo(u24) ride time(2026-10-01T00:00:00Z..2026-10-08T05:59:59Z)
  ...
    note     from(home) → from(u24)
    note     time(today..+7d) → time(2026-10-01T00:00:00Z..2026-10-08T05:59:59Z)
  publish? [y/N] n
  ```

  `home` hangs under its geo cell, so the published term is `from(u24)` —
  public vocabulary — and the approval block says so. Your private name
  never leaves your machine; its value does. (`home` was declared as 5 km
  around a point that lies near a cell edge, so its cell is the coarser
  one containing the whole radius: a cell is what the offer *says*.)
- **An omitted price is your last unit price** for the same side and the
  same bare categories, scaled by quantity, read from your own book, and
  marked in the block (`note price 100 reused: unit price 100/unit from
  offer 23e1d080a2ea (0m ago)`). No earlier offer means an error, never a
  guess; in a script a reused price refuses the line unless `confirm` is
  `off`, because nobody saw it.
- **Offers are immutable values with a content address.** Equal content
  means equal id, always — concept order doesn't matter, but every
  meaningful field does, and a fresh intention gets a fresh `nonce`
  automatically, hence a fresh id.

*The same in Python:*

```python
from loopmarket import Thing, TimeWindow, give, want

NOW = 1_790_834_400                       # 2026-10-01T06:00:00Z; determinism is a feature
here     = "geo(u24)"                     # the cell containing 5 km around the flat
standing = TimeWindow(NOW - 1)            # the offer stands until withdrawn

teach = give("amara", Thing(("piano-lesson", here)), 100, valid=standing)
eat = want("amara", Thing(("produce", "local", "weekly", here)), 104, valid=standing)
teach.offer_id, teach.kind, teach.unit_price      # '…64 hex…', 'give', Fraction(100, 1)
season = "time(2026-10-05T00:00:00Z..2026-12-20T23:59:59Z)"
later = give("amara", Thing(("piano-lesson", here, season)), 100,
             valid=TimeWindow(NOW, NOW + 7200))   # stands for two hours
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
id            side  maker  qty     thing                                                                   price  state
23e1d080a2ea  give  amara  1 unit  geo(u24) piano-lesson time(2026-10-05T00:00:00Z..2026-12-20T23:59:59Z)  100    open
a04ff4b6d207  want  amara  1 unit  geo(u24) local produce weekly                                           104    open
b7d0e7661d21  give  amara  1 unit  geo(u24) piano-lesson                                                   100    open
$ loop status
book = rs:/home/you/.loopmarket/book
book root = 0f427c97f954fa66a928cb651198e1fa091cc4679a2d9c8a0f4654194a8e9c15
offers = 3 (filled 0, withdrawn 0)
catalogue = /home/you/market.od
catalogue root = (unpinned)
categories = 34
...
maker = amara
terms = home
...
$ loop withdraw 23e1d080a2ea                # the two-hour lesson: changed my mind
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
registry.publish(teach); registry.publish(eat); registry.publish(later)
root = registry.commit()                 # one root names the whole book state
list(registry.offers(now=NOW))           # active offers (filters closed ones)
registry.get(teach.offer_id)             # any offer, by content address
registry.withdraw(later.offer_id)        # the tombstone
registry.commit()
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
$ loop --maker bruno give vegetable-box farm 50
$ loop --maker bruno want bicycle-repair farm 52
$ loop matches
bruno gives geo(u24) vegetable-box to amara (wants geo(u24) local produce weekly) rate 2.08  f6e70644bfac>a04ff4b6d207
```

Bruno's box is a `vegetable-box`; Amara wants `produce local weekly`; the
catalogue says the first fits within all three, the two places are the
same cell (handover terms, matched when one contains the other), the
units agree — a match, at rate 104/50 = 2.08 (the want's unit price over
the give's). `matches` exits 1 when there are none, so it reads as a
predicate in scripts.

*The same in Python:*

```python
from loopmarket import check_match, candidate_matches

grow = give("bruno", Thing(("vegetable-box", here)), 50, valid=standing)
m = check_match(grow, eat, catalogue, now=NOW)
m.rate, m.giver, m.receiver          # Fraction(52, 25), 'bruno', 'amara'
```

Rates are exact rationals (invariant U9): 52/25 is 2.08 exactly, and
everything clearing re-checks is computed without rounding.
`check_match` is exact and self-contained — cheap to re-run, which is what
lets clearing re-verify without trusting anyone. Its gates, in order:
kinds and distinct makers → one side of the v2/v3 record line → an
option's underlying and an item's id (§7.3, §7.4) → each side's
requirements met by the other's declarations (§7.2, §7.5) → validity
windows open at `now` → (v1/v2 only) service windows and discs intersect
→ quantity within what is left, on the step and above the floor, in the
same unit → **version pins** (mixed pinning refuses; pinned catalogues
refuse unpinned offers; major registry/contract skew refuses) → catalogue
subsumption. `candidate_matches(offers, catalogue, now=...)` runs it over
the full give × want product — fine in memory, and §10 shows the indexed
generator for bigger books.

## 6. Loops

Rates multiply around a cycle. If the product exceeds 1, the slack is
real, distributable surplus. Chen fixes bicycles, and her daughter wants
piano lessons:

```console
$ loop --maker chen place shop 46.06,14.51,4km
$ loop --maker chen give bicycle-repair shop 80
$ loop --maker chen want music-lesson shop 83
$ loop matches
amara gives geo(u24) piano-lesson to chen (wants geo(u24) music-lesson) rate 0.83  b7d0e7661d21>71a90da7111c
bruno gives geo(u24) vegetable-box to amara (wants geo(u24) local produce weekly) rate 2.08  f6e70644bfac>a04ff4b6d207
chen gives bicycle-repair geo(u24) to bruno (wants bicycle-repair geo(u24)) rate 0.65  a9665e2662c9>e784e7ae3e98
$ loop loops
loop ad562f631186fb01… surplus 12.22%
  chen gives bicycle-repair geo(u24) to bruno (rate 0.65)
  amara gives geo(u24) piano-lesson to chen (rate 0.83)
  bruno gives geo(u24) vegetable-box to amara (rate 2.08)
```

Amara teaches piano but wants vegetables; Bruno grows vegetables but wants
bicycle repair; Chen fixes bicycles and her daughter wants piano lessons.
**No two of them can trade** — look at `matches`: three handoffs, each
useless alone — and the triangle clears at 0.83 × 0.65 × 2.08 = 1.1222,
a 12.22% surplus. `loops` searches a pinned snapshot of the book and
prints; it never clears. Under the hood the solver enumerates every
simple cycle up to a length cap and picks the best set of offer-disjoint
ones (Bellman–Ford, hunting negative cycles in −log(rate) weights, tops up
when the cap cut the search), always in sorted order, so **the same book
yields the same loop on every replica** (invariant U6 — determinism is
what later makes the baseline solver the auction's reserve bid). Exit
code 1 means nothing profitable, so `loop loops && loop clearing` reads
naturally.

*The same in Python:*

```python
from loopmarket import ExchangeGraph

wheels = want("bruno", Thing(("bicycle-repair", here)), 52, valid=standing)
fix    = give("chen", Thing(("bicycle-repair", here)), 80, valid=standing)
learn  = want("chen", Thing(("music-lesson", here)), 83, valid=standing)

everyone = [teach, eat, grow, wheels, fix, learn]
graph = ExchangeGraph.from_matches(candidate_matches(everyone, catalogue, now=NOW))
loop = graph.find_profitable_loop()
loop.nodes, loop.product, loop.loop_id   # ('amara', 'chen', 'bruno'), Fraction(14027, 12500), '…'
```

## 7. Clearing

Clearing's one non-negotiable: **trust no solver** (invariant U3). A
proposal names the roots it was solved against; clearing re-derives
every leg against the *current* book with its own catalogue, re-checks
pins, oracles, fills, tombstones and the arithmetic, and only then
commits — all fills and the loop record under one new root, atomically.
`loop clearing` runs that clearing house locally, over your book (not
`clear`: that means delete on every terminal, and publishing an offer does
not clear it):

```console
$ loop clearing
cleared ad562f631186fb01… surplus 12.22%
  chen gives bicycle-repair geo(u24) to bruno (rate 0.65)
  amara gives geo(u24) piano-lesson to chen (rate 0.83)
  bruno gives geo(u24) vegetable-box to amara (rate 2.08)
book root 749fd71e37488373b8890722448b5b8b855625ad353e8fcc385c9a4f92083798
$ loop loops; echo $?
1
$ loop show b7d0e7661d21 | tail -1
  state    filled
$ loop withdraw b7d0e7661d21
loop: b7d0e7661d21 is filled: a cleared leg is an obligation
```

Six fills and one loop record landed under one root; a second search
finds nothing; the filled legs are obligations now. Rejections print to
stderr with their reason — unknown, filled or withdrawn offers, legs that
fail re-verification, pins that don't equal clearing's own, oracle types
it cannot verify (the local clearing verifies `countersign` and the
door's `possession` and `photo-match`), surplus below threshold,
indivisible legs without per-node surplus — and `clearing` exits 1 when
nothing cleared.

*The same in Python:*

```python
from loopmarket import MockClearing, LoopProposal

for o in (grow, wheels, fix, learn):
    registry.publish(o)
registry.commit()
clearing = MockClearing(registry, catalogue, clock=lambda: NOW)
proposal = LoopProposal(loop, book_root=registry.store.root,
                        ontology_root=catalogue.root, solver="me", found_at=NOW)
receipt = clearing.submit(proposal)
receipt.accepted, receipt.book_root          # True, the new root
clearing.submit(proposal).reason             # 'already filled: …'
```

### 7.1 Getting the address to the courier

Matching runs on cells; a delivery needs a door. The door is *settlement*
text, never vocabulary: give it to the place, and it never enters an
offer, an id or the catalogue.

```console
$ loop place home 46.05,14.50,5km Trubarjeva 12, 4th floor, ring twice
$ loop want ride 'from(home)' 5
...
  note     handoff from(home): Trubarjeva 12, 4th floor, ring twice — sealed to the counterparty at clearing
```

Nothing is sent anywhere. Once a loop clears, `loop watch` (or `watch
--once` in a script) reports your fills — the fill record *is* the
notification — and seals each remembered text to the leg counterparty's
public key, recovered from the signature on their own offer, writing it
beside your filled offer in your own book. The courier's `loop watch`
reads the fold they already follow and opens it with their `bee_signer`:

```console
$ loop watch --once                    # the courier
filled   4f1c3a9b07d2 in loop 9a2e5c1f08b3d7e4…: 0x1563… gives ride to 0x19E7…
handoff  from 0x19E7… for loop 9a2e5c1f08b3d7e4…: from(home): Trubarjeva 12, 4th floor, ring twice
```

`loop handoff ID TEXT` replaces the text for one offer; `loop handoffs`
lists what was sealed to you. Both makers need the `sig` extra and a
`bee_signer`: the same key that owns a feed and signs offers is the key
things are sealed to, so there is no registry. Someone offering courier
service only to harvest addresses learns one per *cleared* obligation —
and can be bonded for it (§7.2) — and a maker who wants to disclose
nothing names a locker or a public pickup place instead
(`docs/plans/P1-spacetime-terms.md` §4).

### 7.2 Guarantees: a neutral point, a deposit, the escrow

Since 0.11.0 an offer can *require* something of any counterparty and
*declare* something about itself (the v5 record — admissibility by
declaration, `docs/plans/P3-release-and-reclearing.md` §5d). Both are on
your own scale; the protocol names no money:

```console
$ loop set default_asset 'xdai xDAI 1'   # MY price for the asset a bare amount means: 1 on my scale per xDAI (no default)
$ loop set require_point 20          # a no-show costs me 20 on my scale: any give I take must be backed by that much
$ loop set require_cancel 5          # a cancellation well ahead costs me 5 — the ladder in between is derived
$ loop set bond 5                    # every give I publish is backed by 5 on my scale, deposited as default_asset at my price
$ loop give vegetable-box farm 50    # → "bond 5xDAI xdai worth 5 …  requires point 20 …  v5"
```

A give whose deposit does not cover a wanter's point *at her price for
that asset* is never matched with her — fail closed, like vocabulary —
and the clearing contract checks the same declaration. Nothing is
converted after clearing: two conversions each inside one maker's scale,
one comparison in the asset's unit.

The deposit is held by the **escrow contract** (`contracts/LoopEscrow.sol`,
deployed on Gnosis): `loop set escrow chain:RPC@CONTRACT` names it in the
record, `loop deposit` funds every bonded give of yours in the chain's
gas token, and from then on the hunt and the checklist count a bond only
up to what the contract holds — a declared, unfunded bond matches nothing.
When a beat is finalized, `loop finalize BEAT` reserves the share of each
deposit its loop relies on (bond × taken / quantity) for that fill: the
wanter's key, the handover window, a claim period (`escrow_claim`, 7 d),
the wanter's ladder in the asset. Every undisputed case then settles
without anyone ruling: the reservation returns to the giver after a
quiet claim period (anyone may settle), or now on the wanter's
countersignature, and a giver who cancels pays the ladder's amount for
that lead. Only a *contested* claim needs a ruling.

**Who rules: by default, one arbitrator both sides accept.** Name an
arbitrator on your gives (`loop set arbitrator 0x…`): a key whose ruling
is final, chosen by reputation or accreditation, as in commercial
arbitration. Say which you accept with `set require_resolvers`, on your
wants and your gives alike — by key (`0x…`), or by property: `root:0x…`
admits every key a register you trust has accredited as an `arbitrator`
(its statement presented in its own book, the register among those you
read), so `loop set require_resolvers root:0xa5…` admits every accredited
arbitrator, new ones included, without naming any. A leg's resolver is
the give's `arbitrator` if both sides accept it, else the first key either
side names, in sorted order, that both accept, else the clearing's own
`resolver` when the give leaves the choice to it (the approval block says
so); a resolver is never a party to the leg, nor rules through one.

For higher stakes among strangers, factbond's `Assertions` is the option:
a bonded ladder — an adjudicator, an arbiter above it, deposits forfeited
on reversal — a stake standing in for the reputation a new pseudonymous key
does not have. Choose it by naming its address as a give's `arbitrator` or
as the clearing's `resolver`. Two more properties are read from such a
contract: `min:10` (at least 10 on your scale at stake on a reversed ruling,
priced by your acceptance of the chain's coin, so `default_asset` or
`require_accepts` must say your price) and `clean:365d` (no ruling reversed
within the year, on a record at least that long). A plain-key arbitrator
has no deposit and no appeal record, so `min:` and `clean:` admit none, and
`clean:365d` admits no contract whose record is under a year old. With
factbond as the resolver, the escrow opens only the wanter's own claim,
naming the giver, for at most the reservation, with windows no shorter than
`claim_min_challenge` and `claim_min_ruling`; a retracted claim reopens the
reservation. How such a claim runs (the claim, the giver's dispute or the
claim certifying, concession, the ruling and its appeal) is factbond's to
document: its
[User Guide](https://github.com/petfold/factbond/blob/main/docs/USER-GUIDE.md)
§2–§3, and §12 for this escrow as the consumer. **Test amounts only:** the
deployed `Assertions` (`0x3c1B4C944398bcc30890d6A6c78f1F9AA2dFe270`) has the
operator's own keys as its adjudicator and final rung — a stand-in until a
named, independent final rung exists (Peter, 2026-10-01) — so do not put
real money behind it.

**Before a claim, a notice.** A claim should start with a notice to the
giver: which fact is wrong and until when it may cure (deliver, refund at
the ladder, correct the statement). The book is the channel, sealed: `loop
notice OFFER --cure 3d` writes the notice into your book, readable only by
the giver (sealed to the key its offer's signature reveals, or its contact
card) beside a salted commitment, and keeps the opening a later claim would
cite in `~/.loopmarket/notices/`; `--fact STATEMENT` names a statement the
giver presented, the give itself otherwise. The cure period is yours to
state. The giver's `loop watch` opens it (`notice   from …: cure by …`), and
`loop cure OFFER [--evidence REF]` answers, sealed back; your `watch`
reports the cure. A cured matter leaves nothing readable in any book. An
arbitrator may refuse a claim the giver had no chance to cure.

**A case before the arbitrator** runs through the book, sealed the same
way. The arbitrator writes its contact card once (`loop contact-card`: a
card that carries nothing but its public key, signed), so it can be reached
without an offer of its own. The wanter claims (`loop claim OFFER 40%
--evidence REF --text "never came"`): the claim goes sealed to the
arbitrator and to the giver, who sees it in `watch` and answers (`loop
answer OFFER --text …`), sealed to the arbitrator and the claimant. The
arbitrator holds the reservation (`loop hold OFFER`, the quiet timeout
stops) and rules (`loop rule OFFER 0.004xDAI --reason "came late: half"`):
final; the escrow pays the ruling less any deductible and returns the
rest, and the reasons go sealed to both. A reservation whose resolver is a
contract — factbond's ladder — is claimed there, not with `loop claim`.

Choosing an arbitrator is a judgement of reputation, and the parties to a
ruling are no witnesses to it: the winner is always satisfied and the loser
almost never. `loop arbitrators` shows what you can see for yourself, from
the escrow's log: the arbitrators named on reservations where you, or a
maker you trust (`--trust KEYS`, or `set trust`), were a party; their
rulings; and the one signal a loser gives that nobody can fake for them —
who lost a ruling under an arbitrator and named it again in an offer
posted after the loss. Nothing outside your circle is counted, since counts
are what puppet trades manufacture. The accreditation an arbitrator
presents is listed beside it, with its state under the registers you read.

The **claim period** is matched per leg (v6): a give declares the longest
it carries (`set claim_max 60d`), a want asks for one (`set require_claim
30d`) and meets only gives that carry at least that; with no ask the
reservation takes `escrow_claim`, never beyond the give's `claim_max`.

**Ending a reservation by agreement.** The parties can end any reservation
themselves: each signs the same split and the second signature pays it
out; the wanter may assign the claim to anyone, and the giver may lengthen
the claim period (tail cover). Each act is a verb: `loop reservations`
lists what the escrow holds behind your legs; `loop countersign OFFER` (you
received it), `loop cancel OFFER` (you cannot deliver: the ladder's amount
at this lead goes to the wanter), `loop assign OFFER KEY`, `loop settle
OFFER 40%` (or `0.004xDAI`, or an amount on your scale at your
`default_asset` price — the other party signs the same and it pays out),
`loop settle OFFER` alone after a quiet claim period, `loop extend-claim
OFFER 30d`, and `loop collect` for a payout your address refused. OFFER is
the offer id's prefix; add `--loop LOOP` when several loops took from it. A
reservation behind a give under the catalogue's `insure` is cover: it is
never ended by a countersignature. The Gnosis escrow at
`0xddDB7276F705671673F0885aEf93B99b890Eb5A9` has all these acts, the
deductible and cover.

A deposit may carry a **deductible** (v7): `loop set deductible 2` — on
your scale, like `bond`, held in the deposit's asset at the price your
deposit states (its worth per unit), for the give's whole quantity like
the deposit (a fill takes its share). A ruled claim pays what it is, at
most the reservation, less the deductible: with factbond as the resolver a
claim at or below it is refused at `hold`, since it could pay nothing, and
under a key arbitrator a ruling at or below it pays nothing. A deposit
counts against a wanter's neutral point only up to what it can pay. For
cover — an `insure(car theft time(…))` give whose deposit is the limit — it
is the insurance deductible: the part of any loss the insured bears herself.

**Cover over a counterparty's deposit** (the taxi case). When cover is
composed with a thing whose give carries its own deposit — a driver's small
deposit, an insurer's cover above it — the cover *covers* that deposit's
reservation: before the cover pays, the insured assigns her claim on the
driver's reservation to the insurer (`loop assign DRIVERS-OFFER
INSURER-KEY`; the cover's claim is refused until she has), and the insurer
recovers the driver's deposit itself; or, if she has already collected from
the driver, the cover pays only the rest. She is paid once, the insurer's
cost is the loss less the driver's deposit, and the driver's own fault costs
him his deposit — nobody has to judge why the ride did not happen.

### 7.3 Options: holding an offer for someone

An **option** is a give of the right to take one of your offers later, at
the price that offer already names (the v6 record, released in
0.13.0; `docs/plans/options-and-cover.md`). You write it
on your own open offer; the premium is what the option itself costs, on
your scale (here in a catalogue with `flat` and a `ljubljana` place):

```console
$ loop give flat ljubljana 900                  # the offer: a flat, one and indivisible, at 900
$ loop option 4f2a --until 7d --premium 20      # an option on it: exercisable for a week, for 20
$ loop option 4f2a                              # or let the window and the premium be suggested (below)
$ loop holds                                    # every hold in the fold: offer, option, holder, until, left
```

**Without the numbers.** How long a hold may last and what it costs are
your judgement — what a hold costs you is the chance another buyer comes
while it blocks the offer and none after it lapses — so there is no
default in the protocol; the command line *suggests*, and you approve what
the block shows, as with the price memory:

- the window is `option_window` of the lead (default `1/4`: a quarter of
  the time to the offer's handover, or to its validity's end without one),
  closing before the handover so a lapsed hold leaves time to sell again;
  or a duration (`set option_window 3d`);
- the premium is `option_premium`: `suggest` (default) reads how many wants
  for a thing like yours appeared in the book over 30 days and prices the
  chance a buyer comes during the hold and none after it, the holder
  exercising half the time — cheap in a thick market, dear close to the
  handover in a thin one; with no demand in the book it says so and falls
  back to price × window/lead × ½. Or a percentage (`set option_premium
  5%`), or an amount. Never below 1% of the price: a hold is never free.

`set options on` writes the option with every plain give, both shown in one
approval block.

**When someone asks.** A buyer can want an option nobody has written yet —
`loop want 'option(apartment)' 30` — and that is a signal to sellers:
`loop show` on your offer and `loop watch` tell you someone would pay to
hold a thing like it, and `loop option ID --for WANT` writes the option
that meets that want. `show` on any offer also lists the options written
on it, so a buyer sees what may be held.

The option is an ordinary give of `option(flat ljubljana)`: a want of
`option(flat)` matches it by containment, and it clears in a loop like
anything else. When it clears the flat is **held** for the option's
holder until the window ends: nobody else's leg can take it, and it
needs no write to end — a hold is active while now is before its end, so
an expired option frees the flat by itself. The holder exercises while the
window is open by wanting the flat at a price of their own:

```console
$ loop exercise 9c1e 950        # as the holder: want the held flat at 950 on my scale
```

An exercise is a clearing like any other (it needs a loop that closes);
the hold only makes sure the holder is the one who can take the offer
meanwhile. Your way out while it is held is a priced cancellation of the
option leg — its deposit's ladder — never a free withdrawal.

**Several options at once** — a trip's flat, car and ferry held one by one
as you find them, then committed together:

```console
$ loop exercise 9c1e 4b07 77aa 2400   # one composed want of the three offers, all or nothing, at 2400
```

Several options become **one composed want** (§9, *Bundles*): a part per
held offer, one price, open until the first window closes. It clears as
one loop or not at all, like any composed want — the holds are what made
every part sure to be there when you commit, so the commitment can wait
until the last component is found. What the holds do not change is the
rest of a bundle's limits: the loop must still close (every component's
seller paid by something they want), and one composed leg must stay
small enough to verify on chain in one call (a few million gas a leg).

**On chain** (since 2026-09-29; `BeatClearing` at `0xC475…11d4` today): a beat
commits the holds its option legs write, the contract records them at
finalize, and the remainder a leg is checked against counts every active
hold but the taker's own — so a beat in which someone other than the
holder takes a held offer is convicted by a challenge, and the holder's
exercise uses the hold up.

### 7.4 Naming one particular thing: items

Most offers are about kinds of things — a vegetable box, an hour of
lessons. Some are about **one particular thing**: this car, this plot of
land, this watch. `item(h)` names it, `h` derived from the identifier the
thing already has, so the same car gets the same `h` however its VIN is
typed (`docs/plans/items-and-ownership.md`):

```python
from loopmarket.items import term, vin_id, land_register_id, serial_id
h = vin_id("1HGCM82633A004352")          # also land_register_id("si", "1234 5678"), serial_id("Omega", "abc123")
give("seller", Thing(("car", term(h)), 1, "car"), 50, valid=...)
```

A want naming `item(h)` takes only that car; a want of `car` takes it too.
An item term that is not a whole 64-character id matches nothing. **One
open claim per maker and item**: once a sale of the car clears, the same
maker's second offer of that car is refused until the first sale's claim
has run out (the handover window, an option's exercise window, or else
the give's validity). Two
*different* makers may both offer it — the owner and a broker — and both
may clear; whichever cannot deliver is a non-performance, which their
deposit covers. On chain the claims are committed and recorded with the
fills, and a beat whose claim races the same maker's claim through
another offer is cancelled at finalize.

**Registered goods: the register is the witness.** For land and
vehicles the title register's transfer is the delivery. A seller declares
it on the give (`loop set oracle 'registry-transfer(0xREGISTER)'`, on a
give naming the item, `car item(…)`), a buyer names the registers whose
transfer she accepts (`loop set require_transfer 0xREGISTER`), and the leg
is performed when that register shows the item held by her: her `watch`
reports `transfer … the register … shows it held by me`, and `loop
countersign` refuses until it does. A register operator records titles
with `loop -f SPEC register transfer ITEM KEY`.

### 7.5 Who you deal with: credentials

A want can require something of the maker on the other side — a licence,
a qualification, a membership — as a **credential entry**: a category, the
kinds of statement it accepts, the trust roots it relies on, how fresh
their registers must be, and a deposit floor (the v6 record's
`requires.counterparty`; `docs/plans/counterparty-gate.md`). The other side
answers with a **statement** about its key, presented in its own book
(`cred/`), issued by someone a trust root accredits and standing in the
issuer's **register** — a separately rooted book of statuses, revocations
and suspensions:

```python
from loopmarket import Credential, Requires, Statement
from loopmarket.register import Register

patient = want(P, Thing(("dentistry", f"time({window})"), 1, "visit"), 40, valid=...,
               requires=Requires(counterparty=(Credential("dentist-licensed", ("attested",),
                                                          min_bond=20, roots=(CHAMBER,),
                                                          max_root_age=86_400),)))
statement = Statement(subject=D, category="dentist-licensed", issuer=ATTESTER, kind="attested",
                      as_of=..., until=..., evidence=..., path=(ATTESTER, CHAMBER), paid_by="subject")
book.present(statement)
attester = Register(store); attester.issue(statement.statement_id, t); attester.heartbeat(t); attester.commit()
```

The **counterparty gate** checks each entry in seven steps — category and
kind; a path of accreditations to a named trust root, every register on
it pinned by the proposal; not revoked; every register's root no older
than the entry allows; valid through the handover window; the deposit's
free share covering the floor; not suspended — and a refusal lists every
step that failed, so one re-presentation cures them all. No gate, no pass:
a credential requirement meets nothing where nobody reads the registers.

A register's roots form a **checked sequence** (since 2026-09-29): each
root names the one before it, a root that drops a revocation its
predecessor held is refused, and a clearing that reads the register's feed
refuses what a newer root says — a revocation or suspension published
since the pinned root — so a stale pin cannot hide a revocation. The proof
that a root keeps every earlier revocation is recordstore's extension
proof (0.21.0), checkable by anyone with no store.

**Credentials from the command line.** A want can require the giver to
present a statement — a licence, an accreditation — before the leg is
matched: `loop set require_credentials 'dentist-licensed attested
root:0xCHAMBER age:1d'` (a statement of a category under
`dentist-licensed`, attested, reaching the chamber's register through
registers no older than a day; `min:20` adds that its deposit's free share
covers 20 on your scale). The giver presents what an issuer gave it:
`loop cred present statement.json`, and `loop cred` lists what is
presented about you (or `loop cred 0xKEY` about anyone), with each
statement's state under the registers you read. An issuer runs its
register as a book of its own — `loop -f rs:~/chamber register issue
0xDENTIST dentist-licensed --until 365d --evidence HASH --paid-by subject`
prints the statement to hand over; `register revoke|suspend|reinstate
ID`, `register accredit 0xATTESTER licence --until 365d`, `register
heartbeat` (at the cadence it declares) and `register status` maintain it,
and `loop announce --role register` makes it discoverable.

Your `watch` also re-checks what your legs relied on: when a want of
yours required a credential (a licence, `requires.counterparty`) and the
issuer's register has since revoked or suspended the giver's statement,
`watch` says so once — `lapsed   dentist-licensed of 0x… (ID), relied
on in loop …: revoked` — with the notice to send. The registers are those you
read: `loop set registers 'ID=rs:PATH ID2=swarm:TOPIC@OWNER'`, and with a
`registry` every book announced under the `register` role. The same
registers let your solver and clearing check credentials and resolvers
accepted by `root:`, each pinned in the loops you clear.

**At the door.** A want can require that the person handing over proves
they hold the key: `loop set require_door possession` — a fresh challenge
signed with their key, which proves control and reveals nothing else. A
giver declares what it settles against with `loop set oracle possession`.
`photo` (the attester's photo of the key's holder, checked at the door)
must be asked for explicitly: a photo resolves to a legal identity almost
anywhere now, so it hands the counterparty a provable link from a face to
a key and its whole history (THREATS T19), and the approval block of
either side says so. Ask for it only where the stakes need it. The record
lists the witness types the level accepts (`photo-match possession` for
`possession`, `photo-match` for `photo`), since that is what the clearing
contract compares; the approval block says "door at least possession".

**On chain**: a beat pins the register roots, each leg's commitment
carries its statements, and `StatementVerifier` checks that each is
presented under the book root and neither revoked nor suspended under its
issuer's pinned register root — a beat pinning a root after the
revocation is convicted by a challenge. Which statement meets which entry
(category, path, validity) stays the optimistic half's.

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
give piano-lesson amara_flat 100
want produce local weekly amara_flat 104
set maker bruno
give vegetable-box bruno_farm 50
want bicycle-repair bruno_farm 52
set maker chen
give bicycle-repair chen_shop 80
want music-lesson chen_shop 83
loops
clearing
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
receipts = agent.step(now=NOW)   # snapshot → match → candidates → select → propose
# [] here: §7 already cleared the triangle, and a filled offer is spent
```

Now the part that makes it a *marketplace* rather than a database: nobody
shares a book. Each maker has their own — on Swarm their own feed and
signing key, so **feed ownership is the authenticity** of their offers —
and readers **fold** the books they know about. At the command line that
is the `registry` setting, the announcement channel on Gnosis: `loop set
registry chain:https://rpc.gnosischain.com@0xD4379E494a488411D964BebDb210C0bf628d97af`,
and every session folds the books announced there (`loop announce` says
"my book is here", `loop announced` lists them, `loop fold` prints the
root), each read as its owner's under the fold rules below. `peers`
(`loop set peers rs:/path/to/bruno,swarm:chen-book@0x…`) are books you
trust by spec, a plain union. `examples/demo_federation.py` runs this whole
section through the API as one narrated script.

### 8.1 One book per maker

```python
blobs = MemoryBytesStore()
amara_book = OfferRegistry(RecordStore(blobs)); amara_book.publish_many([teach, eat]);   amara_book.commit()
bruno_book = OfferRegistry(RecordStore(blobs)); bruno_book.publish_many([grow, wheels]); bruno_book.commit()
chen_book  = OfferRegistry(RecordStore(blobs)); chen_book.publish_many([fix, learn]);    chen_book.commit()
```

### 8.2 The aggregator

A solver folds the announced books itself — the default at the command
line — or reads an **aggregator**: anyone who folds announced books into one
view and publishes a three-root **manifest**, a cache to check, never an
authority:

```python
from loopmarket import Aggregator

agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="agg-0")
agg.announce("amara", amara_book.store)
agg.announce("bruno", bruno_book.store)
agg.announce("chen",  chen_book.store)
manifest = agg.fold()

manifest.book_root          # the pure fold — the book a solver reads
manifest.provenance_root    # who said what, and what was rejected and why
manifest.announcement_root  # commitment to the exact input set folded
```

The fold is **pure**: any aggregator that saw the same inputs produces
byte-identical roots, in any order. That's the neutrality mechanism:
omission (including "pay me to be listed") is a provable act, not a
suspicion. Anyone can be an aggregator; aggregators
sell *serving* (speed, indexes), never *inclusion*.

One reader convicts an aggregator alone. Its `announcement_root` is its
own claim about which books, at which roots, it folded; whatever one of
those books holds that neither entered `book_root` nor earned a `reject/`
record was dropped silently — and with `expected=channel.announced()` a
book it never folded at all is an omission too:

```python
from loopmarket import audit_manifest
from loopmarket.announce import open_announcements
from recordstore import ABSENT, verify_proof

channel = open_announcements("memory:")     # in deployment "chain:RPC@CONTRACT", §8's registry
for who in ("amara", "bruno", "chen"):
    channel.announce(f"rs:/books/{who}", owner=who)

for o in audit_manifest(manifest, blobs, expected=channel.announced()):   # [] for an honest fold
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
mallory.publish(give("amara", Thing(("piano-lesson", here, season)), 1,
                    valid=standing))                       # "amara", says mallory
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
offer = give(me, Thing(("food", here, season)), 5, valid=standing)
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
`loop clearing` with `peers` set does exactly this first ("book re-based
on the fold"):

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
hour — the window *is* the slot, and no two overlap (a `time(a..b)`
includes both ends, so an hour ends at :59:59):

```console
$ odag -f market.od put spin-class service      # vocabulary for this section
$ odag -f market.od put parcel-run service
$ loop give piano-lesson 'time(2026-10-05T09:00:00Z..2026-10-05T09:59:59Z)' 100
$ loop give piano-lesson 'time(2026-10-05T10:00:00Z..2026-10-05T10:59:59Z)'
$ loop give piano-lesson 'time(2026-10-05T11:00:00Z..2026-10-05T11:59:59Z)'
```

(The second and third reuse the first's price — the block says so.) A
cleared loop marks the slot's offer filled **atomically** — that fill
*is* the booking, and any second loop wanting the same hour is rejected
with "already filled". There is no separate reservation step to race.
Taking Wednesday off is `loop withdraw` on Wednesday's slots: the
tombstone survives federation folds, so the closure reaches everyone.

### Capacity: seats

A gym class holds fifteen. One offer says so — a quantity with a step:

```console
$ loop --maker gym place gym 46.05,14.52,1km
$ loop --maker gym give 15seat:1 spin-class gym 'time(2026-10-07T18:00:00Z..2026-10-07T18:59:59Z)' 150
give     geo(u24) spin-class time(2026-10-07T18:00:00Z..2026-10-07T18:59:59Z)
  quantity 15 seat — up to 15 seat, in steps of 1 seat
  ...
```

Each loop through it takes exactly what its want asks (`1seat`, or
`2seat` for a couple), the fill is recorded per loop, and the rest stays
open; the fills of one give never sum past its quantity (invariant U11),
and a remainder below one step exhausts the offer. A class that only runs
if eight enrol puts a **floor** under one fill: `8seat..15seat:1` is up to
fifteen, at least eight in any one loop (the chartered bus). The older
form still works and is sometimes what you mean — the same line three
times is three separate one-seat offers, because `loop` gives every offer
a fresh nonce (in Python pass `nonce=` per seat: the default is the
millisecond clock). The same patterns cover 30 boxes in a van.

### Routes: state as offers

A bicycle courier's feasibility depends on where he *is* — crossing town
takes time and costs him. The protocol never models his position; his
agent publishes it as **spacetime tubes**: several (window, place) pairs
along the planned route, priced accordingly —

```console
$ loop --maker courier place station 46.05,14.50,2km
$ loop --maker courier place eastside 46.02,14.55,2km
$ loop --maker courier give parcel-run station  'time(now..+1h)'  5   # near the station, cheap
$ loop --maker courier give parcel-run eastside 'time(+2h..+3h)'  8   # across town, later, dearer
```

— and as legs clear and his plan changes, the agent withdraws and
reposts between beats. Dynamic state quantizes to the beat; the book a
solver sees is always static and pinned. (A courier can also offer the
move itself — `transport(small-item)` with a `from` and a `to` — and the
solver composes it with the grocer's box at the shop to serve a want at
the door: `examples/delivery.loop`.)

### Bundles: drafts and a composed want

A theatre ticket is worthless if you cannot get there, and the ride is
worthless without the ticket. Neither the theatre nor the bus company
cares; only you do, so the coupling lives in *your* want, as **parts**
that clear together or not at all. Drafts are the tool: a draft is a
resolved but unpublished offer or part, named, kept in a local file that
is never the book.

```console
$ odag -f market.od put to geo; odag -f market.od put theatre-ticket; odag -f market.od put hamlet
$ loop place venue 46.051,14.506,200m
$ loop draft ticket want theatre-ticket hamlet 'time(2026-10-05T19:00:00Z..2026-10-05T21:59:59Z)' venue
ticket  want geo(u24mfp) hamlet theatre-ticket time(2026-10-05T19:00:00Z..2026-10-05T21:59:59Z)
$ loop draft ride want ride 'from(home)' 'to(venue)' 'time(2026-10-05T17:00:00Z..2026-10-05T18:59:59Z)'
ride  want from(u24) geo(u24) ride time(2026-10-05T17:00:00Z..2026-10-05T18:59:59Z) to(u24mfp)
$ loop draft evening ticket + ride       # compose: the same + as on a one-line want
$ loop drafts                             # canonical lines; what you typed as notes beneath
$ loop offer evening 60                   # the draft becomes an offer, one price for the lot
want     hamlet theatre-ticket + ride
  maker    amara
  part 1   geo(u24mfp) hamlet theatre-ticket time(2026-10-05T19:00:00Z..2026-10-05T21:59:59Z)
           quantity 1 unit — 1, indivisible
  part 2   from(u24) geo(u24) ride time(2026-10-05T17:00:00Z..2026-10-05T18:59:59Z) to(u24mfp)
           quantity 1 unit — 1, indivisible
  price    60 (the lot, on amara's scale; split across the parts at clearing)
  ...
```

Or on one line, for scripts and assistants — `+` between parts, one price
last:

```console
$ loop want theatre-ticket hamlet 'time(...)' venue + ride 'from(home)' 'to(venue)' 'time(...)' 60
```

A draft may carry a price (`loop draft want apple 5`, then `loop offer 1`
publishes it as is); a *part* may not — you price the bundle once and
clearing splits it across the gives — and there is no cross-part
constraint language: the ride arriving before curtain is you spelling the
two windows. Draft names are your working memory, never vocabulary; they
cannot appear in an offer. The composed want is one v4 offer, and the
fill names which give served which part. Composition is want-side only.
A kit that ships in one box is one indivisible give; a class that only
runs if eight enrol is a floor on one give (above); and "sirloin to one
buyer, mince to another, only if the whole animal sells" is the door the
design keeps shut — that is a butcher's job.

For anything a person would want to *compute* — one offer per slot for a
month, a theatre visit parameterised by the evening — the language is
Python, and the pipeline is the macro pass: a script prints offer lines,
`loop` reads them as a batch, and `--confirm on` makes the batch ask on
your terminal. `loopmarket.cli.offer_from_line` and `line_for` turn a line
into an `Offer` and back, so a program can work in objects or in text and
end at the same approval block either way.

### Where the sophistication lives (a design boundary)

Notice what these patterns have in common: loopmarket provides the basic
mechanisms and the means to express intentions — offers, atomic fills,
tombstones, pinned snapshots — and leaves the hard optimization to the
**solvers**. The solver behind `loop loops` is a deliberately simple
baseline, mainly for demonstration (and the sealed auction's reserve
bid); professional solvers are expected to grow quickly *outside* the
loopmarket software — routing planners, statistical models, traditional
AI, LLMs, whatever wins. Their internals are not loopmarket's concern,
and they may well be kept secret for competitive edge: that is by
design, and healthy. The protocol's only demand is the one clearing
enforces — whatever a solver proposes gets re-verified from scratch, so
cleverness can be trusted *because* it is never trusted. The same
boundary holds above the command line: an assistant that drafts offers
for you produces the same `loop` lines a person would, and the approval
block is identical whichever typed them.

One honesty note for all these patterns: "blocked immediately" is as
strong as clearing's atomicity — airtight within one clearing instance.
Across independent clearing instances the chain serializes it (§11.1):
`BeatClearing` records the fills, and of two beats that would together
overfill an offer the second is cancelled at finalization and its bond
returned.

## 10. Bigger books: indexed candidate generation

The exhaustive give × want product is fine in memory. When it isn't,
`candidate_matches_indexed` prunes through the catalogue itself — gives are
filed under exactly the terms they carry, and a want's candidates are one
catalogue query: the gives inside every one of its categories' cones,
ontodag's intersection. Where and when are left to the exact check (a give
that *contains* the want's place sits above it, not in its cone). It is
**recall-exact**: the same matches as the baseline (a test enforces
set-equality), just fewer exact checks.

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
$ odag -f swarm:catalogue merge market.od      # the catalogue, on your feed
$ loop set catalogue swarm:catalogue
$ loop set book swarm:my-book                  # your book, on your feed
$ loop set maker ''                            # unset: your identity is the key's address
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
signatures (attached automatically), and faces the contracts of §11.1. The triangle script runs live unchanged, `loop -f swarm:TOPIC
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
    tests/test_swarm_book.py tests/test_swarm_federation.py tests/test_swarm_register.py -v
```

Operational honesty, from the P1 plan: postage TTL is the offer's *real*
lifetime (an expired batch is silent, permanent loss, and nothing in
`loop` yet refuses a validity window that outlasts the batch — watch the
batch's TTL in Bee's `/stamps`, or with `odag swarm`, and top it up;
recordstore refuses to write through a batch with less than a day left);
durability on a ~4,000-node network is a well-hedged
bet, not a custody arrangement; and one feed has one signer — sharing a
feed key is sharing your identity.

### 11.1 Clearing on chain

The contracts live on the EVM chain Swarm settles on (Gnosis today) and
every session with the settings sees the same beats:

```console
$ loop set beat chain:https://rpc.gnosischain.com@0x4A35ee6e86C266de94134BaD5523A8D7C8fA5cF4      # BeatClearing
$ loop set auction chain:https://rpc.gnosischain.com@0xfC5519dD267c8C398Cd29Fa1B9748078A180B5cE   # SealedBeat
$ loop set escrow chain:https://rpc.gnosischain.com@0xddDB7276F705671673F0885aEf93B99b890Eb5A9    # LoopEscrow
$ loop set resolver 0x3c1B4C944398bcc30890d6A6c78f1F9AA2dFe270                                       # factbond's Assertions (test amounts only: its rungs are the operator's keys)
$ loop propose                       # clear locally, post each loop as one beat (a bond, a challenge window)
$ loop beats --open                  # what stands
$ loop challenge 1 --check           # rebuild the record from the submitter's book, ask the verifier, send only what convicts
$ loop finalize 1                    # after the window: fills recorded on chain, deposits reserved on the escrow
$ loop commit; loop reveal; loop outcome   # the sealed beat: seal my loops, open them, derive a closed beat's winners
```

The chain is the authority on what is filled and on what is held: a
fold that never saw a clearing's fills still proposes nothing through a
spent offer, and a bond counts only as far as the escrow holds it. Since
2026-09-29 it is the authority on holds and item claims too (§7.3, §7.4),
and it checks a leg's statements against the register roots the beat pins
(§7.5); the leg verification is two contracts deployed beside
`BeatClearing` (`LegVerifier`, `StatementVerifier`). A contract names its
predecessors, so offers filled under an earlier one stay filled, and a
retired one takes no new beat.
`docs/plans/proof-fabric.md`, `P2-batch-auction.md` and
`P3-release-and-reclearing.md` §5a–§5e are the design records.

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
- **factbond** (`github.com/petfold/factbond`) — where a contested claim
  on a deposit is adjudicated: custody here, adjudication there. Its
  [User Guide](https://github.com/petfold/factbond/blob/main/docs/USER-GUIDE.md)
  and [Roadmap](https://github.com/petfold/factbond/blob/main/ROADMAP.md)
  cover that side.
- **The demos** — `examples/triangle.loop` (P0 as a script),
  `examples/demo_triangle.py` (the same through the API),
  `examples/demo_federation.py` (P1 in one file, memory or live).
