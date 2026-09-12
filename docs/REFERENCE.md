# loopmarket — Reference Manual

*The public API, record formats, keyspace, and invariants, precisely.
Tutorial: [USER-GUIDE.md](USER-GUIDE.md). Rationale:
[ARCHITECTURE.md](../ARCHITECTURE.md). Working rules and roadmap:
[CLAUDE.md](../CLAUDE.md).*

Floors: Python ≥ 3.11, `ontodag` ≥ 0.23.0, `recordstore` ≥ 0.16.0.
Extras: `[swarm]` = `recordstore[bee,feeds]` (Bee blobs + signed feeds),
`[sig]` = `eth-keys` (detached signatures), `[test]` = pytest.

## 0. Conventions

- **Names are identity at public boundaries.** Wherever the API takes a
  concept or maker, a plain string is accepted; catalogue queries take
  category names, not objects.
- **Stores are duck-typed.** `OfferRegistry` and `Aggregator` accept
  anything with the `RecordStore` surface (`put/get/contains/items/keys/
  commit/root/blobs`, classmethods `at`/`merge`); `recordstore.RecordStore`
  over any `BytesStore` is the reference implementation, `swarm_store`
  the network-backed one.
- **Determinism guarantees**: equal offer content ⇒ equal `offer_id`;
  equal book content ⇒ equal root; the same book yields the same loop on
  every replica (U6); aggregators that saw the same inputs produce
  byte-identical manifests in any fold order.
- **Fail closed**: unknown vocabulary never matches (U7); unknown record
  versions raise; unverifiable signatures, oracles, and pins refuse.
- **Vocabulary**: prose says *personal scale* (a personal numeraire); the
  record encoding calls it the maker's personal token (`Tokens`). Nothing
  is ever held or transferred; scale amounts exist to cancel in-loop.

---

## 1. `loopmarket.schema` — the offer form

### `TimeWindow(start: int, end: int)`
Frozen. A half-open interval `[start, end)` in unix seconds (UTC).
Raises `ValueError` unless `end > start`.

| member | meaning |
|---|---|
| `TimeWindow.from_iso(start, end)` | classmethod; ISO-8601 strings, naive = UTC |
| `.contains(other)` | fits-within: `other` entirely inside `self` |
| `.overlaps(other)` | non-empty intersection |
| `.intersection(other)` | `TimeWindow` or `None` |
| `.is_open_at(t)` | `start <= t < end` |
| `.to_record()` | `[start, end]` |

### `GeoDisc(lat: float, lon: float, radius_m: float)`
Frozen. A disc on the sphere. Raises `ValueError` for out-of-range
centre or negative radius.

| member | meaning |
|---|---|
| `.contains(other)` | fits-within (haversine, 1e-9 m tolerance) |
| `.intersects(other)` | a handover point both parties can reach |
| `.to_record()` | `[lat, lon, radius_m]` |

`haversine_m(lat1, lon1, lat2, lon2) -> float` — great-circle metres.

### `Thing(concepts, qty=1.0, unit="unit", divisible=False)`
Frozen. A conjunction of catalogue category names plus quantity.
`concepts` is normalized to a sorted, deduplicated tuple (order never
matters to identity). Raises `ValueError` on empty concepts or
non-positive qty. `divisible` marks partial-fillability; matching
requires `want.qty == give.qty` unless *both* sides are divisible, and
always `want.qty <= give.qty` and equal `unit` strings.

### `Tokens(issuer: str, amount: float)`
Frozen. An amount on the maker's personal scale. Raises `ValueError`
unless `amount > 0`.

### `Offer(...)` — frozen; the one uniform intention

```
Offer(maker, gives, wants, service, where, valid,
      ontology_root="", bond=0.0, oracle="countersign", arbitrator="",
      nonce=<auto: unix ms>, registry_version="", contract_version="", v=2)
```

Validation (`ValueError`): exactly one of `gives`/`wants` is a `Thing`
and one a `Tokens` whose `issuer == maker` (invariant U1); `bond >= 0`;
`v in {1, 2}`; v1 records carry no registry/contract pins.

| member | meaning |
|---|---|
| `.kind` | `"give"` (gives a Thing) or `"want"` (wants one); constants `GIVE`, `WANT` |
| `.thing` / `.tokens` | the respective side |
| `.unit_price` | scale units per thing-unit |
| `.to_record()` | dict, **in the offer's native version** (a v1 offer re-encodes as v1 — version is identity, U2) |
| `Offer.from_record(rec)` | classmethod; dispatches on `rec["v"]`, **raises `ValueError` on unknown versions** |
| `.canonical_bytes()` | recordstore canonical JSON of `to_record()` |
| `.offer_id` | SHA-256 hex of `canonical_bytes()` — the content address |

`bond`, `oracle`, `arbitrator` are carried in identity from day one but
only `oracle` is enforced today (clearing's refusal gate).

### `give(maker, thing, amount, *, service, where, valid, **kw) -> Offer`
### `want(maker, thing, amount, *, service, where, valid, **kw) -> Offer`
Convenience constructors; `**kw` passes through (`nonce=`, pins, etc.).
Splat `**Ontology.pins` to pin the catalogue.

Order-book synonyms, kept indefinitely: `ask = give`, `bid = want`
(functions), `ASK = GIVE`, `BID = WANT` (constants), and `Match.ask` /
`Match.bid` (properties aliasing `Match.give` / `Match.want`).

---

## 2. `loopmarket.spacetime` — discretised space and time

Index-name helpers; hints only, never a correctness dependency.

| function | meaning |
|---|---|
| `geohash(lat, lon, precision=6)` | plain geohash, no dependencies |
| `cell_for(disc, max_precision=6)` | finest cell not smaller than the disc (centre only — boundary discs touch neighbours) |
| `cell_chain(cell)` | all prefixes, coarsest first |
| `day_buckets(window, max_buckets=400)` | UTC day names the window touches |
| `bucket_chain(day)` | `['2026', '2026-08', '2026-08-14']` |

---

## 3. `loopmarket.ontology` — the catalogue facade

### `Ontology(dag: OntoDAG | None = None)`

| member | meaning |
|---|---|
| `.assert_edge(sub, supers, *, bond=0.0)` | assert fits-within; missing supers created under the root; `bond` recorded intent (P3) |
| `.load({sub: [supers, ...]})` | bulk, order-independent declaration; returns self |
| `.known(concept)` | vocabulary membership |
| `.covers(wanted, offered)` | `offered` fits within `wanted` (equal or descendant); **False for unknown names** (U7) |
| `.satisfies(offered, wanted)` | every wanted category covered by some offered concept |
| `.root` | canonical root of the last committed state, `''` if in-memory/uncommitted |
| `.pins` | `{"ontology_root", "registry_version", "contract_version"}` — splat into `give`/`want` (U10) |
| `Ontology.persistent(record_store)` | classmethod; an `EagerOntoDAG`-backed catalogue with committable roots |
| `.commit()` | commit, return the root; `TypeError` on in-memory catalogues |

---

## 4. `loopmarket.registry` — the book

Key prefixes (module constants): `OFFER="offer/"`, `SIG="sig/"`,
`WITHDRAW="withdraw/"`, `FILL="fill/"`, `LOOP="loop/"`.

### `OfferRegistry(store)`

Writing:

| member | meaning |
|---|---|
| `.publish(offer) -> offer_id` | store the offer record (nothing else — `idx/` is aggregator-derived) |
| `.publish_many(offers) -> [ids]` | |
| `.withdraw(offer_id)` | monotone tombstone; survives merges; `KeyError` if the offer isn't in this book; re-publishing identical content does not un-withdraw |
| `.absorb(other)` | re-assert another book's entire content as this writer's base; canonical addressing makes the re-commit reproduce the source root (clone verification). O(book) |
| `.attach_signature(offer_id, sig_hex)` | store a detached signature; `ValueError` unless it recovers to the offer's maker; needs `[sig]` |
| `.mark_filled(offer_ids, loop_id, loop_record)` | clearing's stroke: fills + loop record; **no wall clock** — a pure function of the decision |
| `.commit(*, reconcile=True) -> root` | land staged changes; reconciled commits three-way-merge with concurrent writers under `or_set_resolver`, then run `verify_loop_atomicity` |

Reading:

| member | meaning |
|---|---|
| `.snapshot() -> (root, frozen OfferRegistry)` | the unit a solver works against (U4) |
| `.get(offer_id) -> Offer` | `KeyError` if absent |
| `.is_filled(offer_id)` / `.is_withdrawn(offer_id)` | |
| `.signature(offer_id) -> str | None` | |
| `.offers(*, now=None, include_filled=False)` | active offers: fills and tombstones filtered, expiry filtered when `now` given; `include_filled=True` disables all filtering (full-book scan) |
| `.ids_by_index(prefix)` | offer ids under an `idx/` prefix — meaningful only on an aggregator's derived-index store |
| `.verify_loop_atomicity()` | raises `PartialLoopError` unless every `loop/` record holds all its fills and every fill points at a present loop (U11) |

### `or_set_resolver(key, base, ours, theirs)`
Merge policy for concurrent writers: add-only presence everywhere; a
doubly-claimed `fill/` keeps the lexicographically smaller loop id
(deterministic, commutative). Convergence mechanics, not clearing
policy — `verify_loop_atomicity` is the guard (see its docstring).

### `PartialLoopError(RuntimeError)`
A book holds a loop missing some of its fills. Raised, never repaired —
evicting a cleared loop would be a finality rollback.

### `index_offers(store, offers)`
File offers under `idx/c/<concept>/`, `idx/t/<bucket>/`,
`idx/g/<cell-prefix>/` in a *derived* store. Regenerable; never merged.

### `swarm_offer_book(topic, *, signer=None, owner=None, **kw) -> OfferRegistry`
A book on Swarm: `recordstore.swarm_store` underneath (Bee blobs, signed
feed head). `signer` (32-byte hex key) to publish; `owner` (address) to
follow. Needs `[swarm]`, a Bee node, and a purchased postage batch.

---

## 5. `loopmarket.matching` — the exact pairwise check

### `Match(give: Offer, want: Offer)` — frozen

| member | meaning |
|---|---|
| `.rate` | `want.unit_price / give.unit_price` — always positive (U5) |
| `.giver` / `.receiver` | give.maker / want.maker |
| `.qty` | the want's quantity |

### `check_match(give, want, ontology, *, now) -> Match | None`
Exact, self-contained, re-runnable by clearing. Gates, in order:

1. kinds: give is `GIVE`, want is `WANT`, distinct makers
2. validity: both offers open at `now`
3. time: service windows intersect
4. space: service discs intersect
5. quantity: `want.qty <= give.qty`; equal unless both divisible; equal units
6. **pins**: if the verifying catalogue is pinned (`ontology.root`), both
   offers must carry all three pins; mixed pinning (one side declares,
   the other silent) always refuses; equal `ontology_root` when both
   pin; registry/contract versions refuse on **major** skew (minor is
   vocabulary-additive and interoperates)
7. meaning: `ontology.satisfies(give concepts, want concepts)`

### `candidate_matches(offers, ontology, *, now) -> Iterator[Match]`
The exact check over the full give × want product. The recall baseline.

---

## 6. `loopmarket.dimensions` — indexed candidate generation

Needs ontodag ≥ 0.4.0 parametric dimensions. Recall-exact against the
baseline (enforced by test).

| member | meaning |
|---|---|
| `time_term(window)` | the window as one inclusive `service-time(a..b)` value |
| `cell_term(offer)` | the centre cell as one `service-cell(...)` prefix value |
| `DimensionIndex(ontology)` | files gives into a **deepcopy** of the catalogue (derived, per-solver, never merged/persisted) |
| `.file(offer) -> bool` | index a give; `False` for non-gives and unknown vocabulary (U7's outcome) |
| `.candidates(want) -> set[str]` | give ids inside every wanted cone with overlapping windows |
| `candidate_matches_indexed(offers, ontology, *, now, index=None)` | drop-in for `candidate_matches` |

Geo deliberately stays with the exact check: sibling cells share no
prefix, so a cell filter would lose recall.

---

## 7. `loopmarket.graph` — loops

### `Loop(matches: tuple[Match, ...])` — frozen
Raises `ValueError` unless ≥ 2 legs chaining into a cycle
(`matches[i].receiver == matches[i+1].giver`, wrapping).

| member | meaning |
|---|---|
| `.nodes` | givers, in cycle order |
| `.product` | Π rate — > 1 means surplus |
| `.surplus` | `product - 1` |
| `.per_node_ok` | every node's incoming want price ≥ its outgoing give price (exact cancellation feasible with unit legs) |
| `.all_divisible` | every leg divisible on both sides |
| `.offer_ids` | all 2k offer ids, leg order |
| `.loop_id` | SHA-256 of the **leg cycle** under its minimal rotation — rotation-invariant, pairing-sensitive (two pairings of the same offers get distinct ids) |

### `ExchangeGraph(edges: dict[(giver, receiver), Match])`

| member | meaning |
|---|---|
| `ExchangeGraph.from_matches(matches)` | best-rate reduction: one edge per ordered pair (a known recall gap for feasibility — see `docs/plans/P2-loop-selection.md` §6) |
| `.nodes` | sorted node list |
| `.find_profitable_loop(*, min_surplus=0.0)` | Bellman–Ford over −log(rate); deterministic (sorted iteration, U6); one `Loop` or `None` |
| `.find_profitable_loops(*, min_surplus=0.0, limit=10)` | greedy disjoint extraction (each offer used once) |

---

## 8. `loopmarket.clearing` — trust nothing, commit atomically

### `LoopProposal(loop, book_root, ontology_root, solver, found_at)` — frozen
`.to_record()` → the `loop/` record (see §13).

### `Receipt(accepted, loop_id, reason="", book_root="")` — frozen
`book_root` is the post-clearing root when accepted.

### `Clearing` (Protocol)
`submit(proposal) -> Receipt`.

### `MockClearing(registry, ontology, *, min_surplus=0.0, require_per_node=True, clock=time.time, verifiable_oracles=VERIFIABLE_ORACLES)`
`VERIFIABLE_ORACLES = frozenset({"countersign"})`. The checklist of
`submit`, in order (U3 — any future backend keeps this shape):

0. **pins**: `proposal.ontology_root` must *equal* the clearing's own
   `ontology.root` (absence and mismatch both refuse; `'' == ''` keeps
   the in-memory flow working)
1. every offer exists in the *current* book, is unfilled, is not
   tombstoned, is used once, and names an oracle type in
   `verifiable_oracles`
2. every leg re-derived with `check_match` against the current book and
   the clearing's own catalogue
3. arithmetic: `surplus >= min_surplus`; indivisible loops additionally
   need `per_node_ok` (while `require_per_node`, the pre-P2 policy)
4. one atomic commit: all fills + the loop record under one new root

---

## 9. `loopmarket.solver.agent` — the baseline species

### `SolverAgent(registry, ontology, clearing, solver_id="solver-0", min_surplus=0.005, max_loops_per_step=10)`

| member | meaning |
|---|---|
| `.find_loops(*, now=None) -> (book_root, [Loop])` | snapshot → offers → matches → graph → disjoint loops |
| `.step(*, now=None) -> [Receipt]` | find, then propose each loop (pinning the snapshot root and `ontology.root`); appends to `.receipts` |
| `.run(*, interval_s=5.0, max_steps=None)` | poll loop for live operation |

Deterministic and exact by design — the species smarter solvers must
beat, and (P2) the auction's reserve bid.

---

## 10. `loopmarket.sigs` — detached signatures (U8's off-feed layer)

All functions lazily import `eth-keys` (`[sig]`); without it they raise
`RuntimeError` (except `verify_offer_sig`, which returns `False` —
verification failing closed).

| function | meaning |
|---|---|
| `maker_address(private_key_hex) -> str` | the Ethereum-style address this key signs as — use as `maker` |
| `sign_offer(offer, private_key_hex) -> str` | recoverable 65-byte signature (hex) over the 32-byte offer id |
| `recover_maker(offer_id, sig_hex) -> str` | the address that signed |
| `verify_offer_sig(offer, sig_hex) -> bool` | recovers to `offer.maker`? malformed input → `False` |

Signatures live *beside* offers (`sig/` keys), never inside
`canonical_bytes()` — ids stay stable, roots stay pure.

---

## 11. `loopmarket.federation` — the aggregator

Constants: `MAKER = "maker"`, `CLEARING = "clearing"` (book roles).

### `Manifest(aggregator, book_root, provenance_root, index_root, announcement_root)` — frozen
What an aggregator publishes. `book_root` is the pure fold;
`provenance_root` its attributed decisions; `index_root` derived and
regenerable; `announcement_root` the input-set commitment (completeness
handle, threat T14).

### `Aggregator(store_factory, *, aggregator_id="agg-0")`
`store_factory() -> store` must return fresh writable stores over the
**shared blob space** (all books one blob space — Swarm's, or one
`MemoryBytesStore`).

| member | meaning |
|---|---|
| `.announce(owner, store, *, role=MAKER)` | register "owner's book is store"; one per owner; re-announce replaces; `ValueError` on unknown role |
| `.retract(owner)` | admission-by-reference's teeth: stop folding an owner |
| `.fold() -> Manifest` | sanitize every announced book, merge under `or_set_resolver`, U11-check, rebuild the derived index, commit all four roots. Deterministic in the announced (owner, root) set: same inputs ⇒ byte-identical manifest, any order |

Admission rules per record (fail closed; every rejection is an
attributed `reject/` record):

| key class | maker book | clearing book |
|---|---|---|
| `offer/` | content address re-derived; readable version; `maker == owner` **or** valid detached `sig/` in the same book | silently skipped (contains its base fold; not its speech) |
| `withdraw/` | only for an offer this book holds with `maker == owner` | silently skipped |
| `sig/` | staged when it verifies; foreign-offer sigs stage with their offer | silently skipped |
| `fill/`, `loop/` | **rejected** ("clearing keys in a maker book") | staged |
| anything else | rejected ("unknown keyspace") | silently skipped |

### `Omission(owner, key, announced_root, proof)` — frozen
One record an announced maker book holds at `announced_root` that is
absent from `book_root` and has no `reject/` in `provenance_root`.
`proof` is recordstore's absence proof for `key` against `book_root`
(`verify_proof(proof, book_root) is ABSENT`, no store access); `None`
when `book_root` is empty.

### `audit_manifest(manifest, blobs, *, store_type=RecordStore) -> list[Omission]`
The T14 cross-audit from the manifest alone: (announced set) − (speech
under `book_root`) over `offer/` and `withdraw/` keys of every
`MAKER`-role announcement, sorted by owner then key. Empty for an honest
fold. Not audited: `sig/` (dropped-without-rejection by design) and
clearing books (U11 covers them).

---

## 12. The keyspace

One book = one recordstore keyspace = one root per version:

```
offer/<offer_id>        the immutable offer record (v1 or v2)
sig/<offer_id>          detached maker signature, hex (never in identity)
withdraw/<offer_id>     1 — monotone tombstone: the offer is closed
fill/<offer_id>         {"loop": <loop_id>} — pure function of the decision
loop/<loop_id>          the cleared proposal record
idx/c/<concept>/<id>    1 — aggregator-derived only
idx/t/<bucket>/<id>     1 —      "
idx/g/<prefix>/<id>     1 —      "
origin/<offer_id>       {"owner", "root"}        (provenance store)
reject/<owner>/<key>    {"owner", "reason"}      (provenance store)
announce/<owner>        {"role", "root"}         (announcement store)
```

Maker books write `offer/`, `sig/`, `withdraw/` only; clearing books
add `fill/` and `loop/`; `idx/` exists only in derived index stores;
`origin/`, `reject/`, `announce/` only in an aggregator's provenance and
announcement stores.

## 13. Record formats

**Offer, v2** (v1 lacks `registry_version`/`contract_version` and says
`"v": 1`; a v1 offer re-encodes as v1 forever — U2):

```json
{"v": 2, "maker": "amara",
 "gives": {"type": "thing", "concepts": ["piano-lesson"], "qty": 1.0,
           "unit": "course", "divisible": false},
 "wants": {"type": "tokens", "issuer": "amara", "amount": 100},
 "service": [1700000000, 1707776000], "where": [46.05, 14.5, 5000],
 "valid": [1699999999, 1702592000],
 "ontology_root": "…64 hex…", "registry_version": "4.1",
 "contract_version": "0.1",
 "bond": 0.0, "oracle": "countersign", "arbitrator": "", "nonce": 1}
```

**Loop** (`LoopProposal.to_record()`):

```json
{"loop_id": "…", "solver": "demo-solver", "found_at": 1700000000,
 "book_root": "…", "ontology_root": "…", "surplus": 0.1222,
 "nodes": ["amara", "chen", "bruno"],
 "legs": [{"give": "<offer_id>", "want": "<offer_id>", "rate": 0.83}, …]}
```

**Fill**: `{"loop": "<loop_id>"}` — deliberately nothing else (no wall
clock: equal clearings must produce equal roots on every replica).

## 14. Invariants (binding; tests enforce them)

| id | statement |
|---|---|
| **B1** | the core imports and works with no network, no Bee node, no optional dependency |
| **B2** | dependencies point one way: loopmarket → ontodag → recordstore → (Swarm, lazily) |
| **U1** | exactly one side of every offer is a Thing, one is Tokens, and the token issuer is the maker |
| **U2** | offers are immutable canonical values; `from_record` dispatches on `"v"` and raises on unknown versions; offers re-encode in their native version |
| **U3** | clearing trusts no solver: pin equality, per-leg re-derivation against the current book, full re-checks, one atomic commit |
| **U4** | solvers work on snapshots and pin roots in proposals |
| **U5** | rates are positive; no signed prices anywhere |
| **U6** | the baseline solver is deterministic: same book, same loop, every replica |
| **U7** | vocabulary fails closed: unknown categories never match |
| **U11** | no partially-filled loop survives a merge unnoticed: `verify_loop_atomicity` on every reconciled commit and every fold, raising rather than repairing |

Planned invariants **U8–U14** (offer authenticity, exact rationals,
load-bearing pins, cost-borne statistics, no protocol emissions,
numeraire-free scoring) are specified in `docs/plans/` and enter the
binding set as their enforcing code lands — U8's fold rules and U10's
matching half are already running (§11, §5).

## 15. Environment

| variable | used by | meaning |
|---|---|---|
| `BEE_API` | live tests, `demo_federation.py` | Bee node API, e.g. `http://localhost:1633` (a light node suffices) |
| `BEE_BATCH` | " | a purchased postage batch id (never auto-buys; prefer mutable for feed-heavy work) |
| `BEE_SIGNER` | gated tests | throwaway 32-byte hex key for the shared-catalogue/book feeds |
| `LOOP_CORE` | `demo_federation.py` | `0` skips adopting ontodag's `core` pack (needs ontodag>=0.19) and uses the eleven-category toy catalogue |
| `LOOP_HOME` | `loop` | the CLI's home (`~/.loopmarket`): `config`, the default book `book/` |
| `LOOP_BOOK`, `LOOP_CATALOGUE`, `LOOP_PEERS`, `LOOP_MAKER`, `LOOP_WHERE`, `LOOP_WHEN`, `LOOP_VALID`, `LOOP_NOW`, `LOOP_CONFIRM`, `LOOP_RENDER`, `LOOP_LIMIT` | `loop` | the environment layer of the settings table (§17); `BEE_*` is shared with odag |
| `ONTODAG_HOME`, `ONTODAG_STORE` | `loop`, via odag | where the inherited odag config and active store (the default catalogue and the personal names layer) live |

Live test suites: `tests/test_swarm_book.py` (the P0 triangle on a live
book), `tests/test_swarm_federation.py` (per-maker feeds, two
aggregators, clearing feed, follower). Both skip without the
variables; both use timestamped topics so reruns inherit nothing.

## 16. Exceptions

| exception | raised by | meaning |
|---|---|---|
| `ValueError` | constructors, `from_record`, `attach_signature`, `announce` | malformed values, unknown record versions, non-recovering signatures, unknown roles |
| `KeyError` | `get`, `withdraw` | no such offer in this book |
| `PartialLoopError` | `verify_loop_atomicity` (reconciled commits, folds) | a merge stranded a partially-filled loop (U11) |
| `RuntimeError` | `sigs.*` without `[sig]`; `Ontology.persistent` without `EagerOntoDAG` | missing optional machinery |
| `TypeError` | `Ontology.commit` on in-memory catalogues | nothing to commit to |

## 17. `loopmarket.cli` — the `loop` command line

Console scripts `loop` and `loopmarket` (alias); `python -m loopmarket`
without installing. Design record: `docs/plans/cli.md`. Tooling, not
protocol: it encodes only what the schema holds, refuses the rest loudly,
and never scales, rounds or tolerates a quantity.

### Invocation

```
loop [GLOBAL-FLAGS] COMMAND [ARGS]     one command
loop [GLOBAL-FLAGS] < script            a batch: one command per line, # comments
loop                                     a prompt on a terminal (quit/exit to leave)
```

Global flags precede the command and are the flag layer of the settings
table: `-f SPEC`, `--catalogue SPEC`, `--peer SPECS`, `--maker NAME`,
`--where NAME`, `--when WINDOW`, `--valid DURATION`, `--now TIME`,
`--confirm MODE`, `-n N`, `--raw`/`--render`, `--bee-api URL`,
`--bee-batch ID`, `--bee-signer KEY`; `--version`, `--help`. Read commands
also take `-o FILE` (the prompt has no shell redirect), `-n N` and
`--raw`/`--render` after the command. Exit codes: 0 success, 1 error or a
false predicate (`loops`, `matches`, `clearing` with nothing to report;
`give`/`want` not published), 2 usage. Errors go to stderr as
`loop: ...`; commands are silent on success except `give`/`want`, which
print the new id.

### Grammar (ontodag's, plus two conventions)

A token after `give`/`want` is one of:

| token | meaning |
|---|---|
| bare word | a category (nothing bare is reserved; unknown fails closed, U7) |
| `head(param)` | an ontodag term in ontodag's spelling; quote the parentheses in a shell, bare at the prompt and in scripts |
| bare number **first** (`10kg`, `3`, `2.5l`) | the quantity: a unit suffix ⇒ `qty`, `unit`, divisible; a bare count ⇒ indivisible, unit `unit`; omitted ⇒ the schema default |
| bare number **last** (`100`, `12.5`) | the price, on the maker's scale; omitted ⇒ the maker's last unit price for the same side and bare categories, × quantity, marked in the block; no earlier offer ⇒ error |
| `+` between parts (`want` only) | a **composed want**: each part reads as a want line without its price (a bare number first is that part's quantity, no `valid(...)`), the last bare number of the line prices the whole; refused in a `give` |

Whole numbers encode as integers, decimals as floats (canonical JSON tells
`1` from `1.0`; the API's own encoding is matched byte for byte).

**Interpreted heads** (mapped onto offer fields until spacetime terms land,
`ontodag-coupling.md` §2): `when(WINDOW)` → `service`; `where(NAME)` →
`where` (the disc read from the place node; `where(LAT,LON,R)` is the
literal, the spelling `place` takes); `valid(DURATION | WINDOW)` →
`valid`. A startup check refuses a catalogue that declares one of these
as a dimension head.

**Other terms** pass into the description. A term of a declared *prefix*
or *dominance* head (`from(...)`, `to(...)`, `geo(...)`, `size(...)`) is
kept and matched by ontodag's computed containment; if its parameter is a
catalogue *name*, the name's value in that kind of dimension is
substituted (`from(home)` → `from(u24m)`, from `home ⊑ geo(u24m)`) and
printed as a note — a name with no such value is refused, never read as a
literal. A term of a *linear*, *count* or *calendar* head
(`weight(...)`, `count(...)`, `time(...)`) is accepted by the parser and
**refused at publish** with the coupling plan named: quantities and time
are fields today. Band spellings in quantity position (`9kg..11kg`,
`10kg..`, `..11kg`) likewise parse and refuse, naming the point spelling.

**Time** (input vocabulary, stored absolute UTC): `now`, `today`,
`tomorrow`, `+90d`/`-2h` (units `s m h d w`), any ontodag time literal
(`2026-10`, `2026-10-01`, `2026-10-01T10:00:00Z`), and ranges `A..B`,
`..B` (from now), `A..` (refused: a window needs an end). A name whose
node hangs under a `time(...)` term is a window too (`when(evenings)`).
Durations: `30d`, `2h`, `90m`, or ontodag's (`155min`). Radii: `5km`,
`500m`, bare metres.

### Commands

| role | command | does |
|---|---|---|
| maker | `give [QTY] CAT\|TERM... [PRICE]` | resolve, show the block, confirm, publish, commit, print the id |
| | `want [QTY] CAT\|TERM... [PRICE]` | the other side |
| | `withdraw ID` | tombstone one of my open offers (id or unique prefix); filled refuses |
| | `mine` | my offers, all states |
| | `place NAME LAT,LON,RADIUS` | a place node under its `geo(cell)` with `{"disc": [lat, lon, r]}` in metadata, written to odag's active store (temporary bridge; adopts the prelude there if absent) |
| | `want PART + PART... PRICE` | a composed want on one line: resolves every part, renders the composed block, **refuses** until the v3 record carries parts (exit 1, nothing published) |
| | `draft [NAME] want\|give ...` | stage one resolved offer (price optional) or part in `$LOOP_HOME/drafts` (a file, never the book; no id); re-drafting a name replaces it; numbers name the unnamed |
| | `draft [NAME] A + B ...` | compose drafts (want side only, flattening, a priced part refused); a single name copies |
| | `drafts` | every draft in canonical spelling — the line `offer` will speak — with the typed spelling and notes beneath (exit 1: none) |
| | `offer NAME [PRICE]` | a draft becomes an offer: its own price, the given one, or the price memory; block, question, publish, draft removed; a composed draft renders and refuses until v3 |
| | `discard [NAME\|N ...]` | drop drafts; alone, empty the list |
| reader | `offers [CATEGORY...]` | open offers in the fold, filtered through `satisfies` |
| | `show ID` | one offer as the approval block, plus `state` |
| | `matches` | every feasible handoff in the fold (exit 1: none) |
| | `status` | book and catalogue specs and roots, counts, settings in force |
| solver | `loops` | profitable loops on a pinned snapshot; prints, never clears (exit 1: none) |
| clearing | `clearing` | `MockClearing` over the fold; with `peers`, my book first absorbs the fold; fills committed to my book (exit 1: nothing cleared). `clear` is a one-release alias |
| plumbing | `set [KEY [VALUE]]` | list / show / durably change a setting; unknown keys are errors; values validated at set time |
| | `export` | every offer of my book as JSON lines of canonical records |
| | `import [FILE]` | publish records from FILE or stdin; ids survive |
| | `help`, `--version` | |

Not yet at the command line: `propose`, `fold`, `audit` (after the
federation demo). Composed wants (`docs/plans/cli.md` §13) draft, compose,
resolve and render today; publishing one waits for the v3 record (`wants`
carrying parts, fills naming every give consumed).

### The approval block

`give`/`want` print the fully resolved offer through the same renderer
`show` uses — byte-identical for the same offer (gate G4): side and
concepts, maker, quantity with its *reading* ("up to 10 kg, divisible";
"3, indivisible"; a want's point with the note that a floor is not
encodable yet), price and unit price on the maker's scale, service and
validity windows in UTC and local time, the disc, the pins, bond /
oracle / arbitrator, nonce, `offer_id`. Below the block, `note` lines:
the place name, a reused price with its source offer and age, and every
name→value substitution. The nonce is `now` in milliseconds plus the
maker's offer count in the book, so a fixed `now` still gives identical
lines distinct ids.

**Confirmation** (`confirm`): `auto` asks `publish? [y/N]` at a terminal
(default no) and proceeds in a batch — except that a line whose price
was reused **refuses** (fail closed; type the price or `set confirm
off`); `on` always asks, via `/dev/tty` when stdin is the script; `off`
never asks.

### Settings

One rule: **flag > `$LOOP_*`/`$BEE_*` > `~/.loopmarket/config` >
`~/.ontodag/config` (for the shared keys) > default.** `set` writes the
loop config (owner-readable, 0600); secrets print masked.

| setting | env | default | meaning |
|---|---|---|---|
| `book` | `LOOP_BOOK` | `rs:~/.loopmarket/book` | my writable book: `rs:PATH` (odag's on-disk layout) or `swarm:TOPIC` (signed with `bee_signer`) |
| `catalogue` | `LOOP_CATALOGUE` | odag's active store | the store offers pin (any odag spec: `.od` file, `rs:PATH`, `swarm:NAME`) |
| `peers` | `LOOP_PEERS` | none | read-only books folded into every answer: `rs:PATH`, `swarm:TOPIC@OWNER`; comma-separated. A trusted OR-set union today (U8 admission needs owners: the `fold` command) |
| `maker` | `LOOP_MAKER` | none | my identity; unset with `bee_signer` set and `[sig]` installed ⇒ the key's address, and offers get detached signatures |
| `where` | `LOOP_WHERE` | none | default place (a node with coordinates) |
| `when` | `LOOP_WHEN` | `..+90d` | default service window |
| `valid` | `LOOP_VALID` | `30d` | how long offers stand |
| `now` | `LOOP_NOW` | wall clock | the clock: unix seconds or an ISO-8601 literal |
| `confirm` | `LOOP_CONFIRM` | `auto` | `auto` / `on` / `off` |
| `render`, `limit` | `LOOP_RENDER`, `LOOP_LIMIT` | `auto` | as odag: tables and 50 rows at a terminal, raw and unlimited in a pipe |
| `bee_api`, `bee_batch`, `bee_signer` | `BEE_*` | inherited from odag | the Bee node; `bee_signer` is secret |

Names resolve through the **view** — the catalogue merged with odag's
active store and odag's overlays — while matching runs against the
`catalogue` store alone and only its root is pinned; a private place
never moves a root offers pin. When `catalogue` is unset the two stores
coincide (development), so `place` a location before publishing against
it.

### Programmatic use

`loopmarket.cli.dispatch(argv, session, out=None, err=None) -> int` runs
one command with captured streams; `Session()` opens stores lazily;
`run_stream(session, stream, interactive)` runs a batch. **The line as
Python's literal:** `offer_from_line(line, session=None) -> Offer` resolves
an offer line under the session's settings without publishing (a composed
line raises until v3); `line_for(offer) -> str` renders an `Offer` to its
canonical line, `want 2kg apple when(A..B) where(LAT,LON,Rm) valid(A..B) 9`,
and the two round-trip. `parse_offer_tokens`, `parse_want_line`, `window`,
`duration_s`, `radius_m`, `render_offer` are the pure pieces.
Gates G1–G6 (`docs/plans/cli.md`) are `tests/test_cli.py`.
