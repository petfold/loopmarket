# loopmarket — Reference Manual

*The public API, record formats, keyspace, and invariants, precisely.
Tutorial: [USER-GUIDE.md](USER-GUIDE.md). Rationale:
[ARCHITECTURE.md](../ARCHITECTURE.md). Working rules and roadmap:
[CLAUDE.md](../CLAUDE.md).*

Floors: Python ≥ 3.11, `ontodag` ≥ 0.13.0, `recordstore` ≥ 0.16.0.
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
only `oracle` is enforced today (settlement's refusal gate).

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
| `.mark_filled(offer_ids, loop_id, loop_record)` | settlement's stroke: fills + loop record; **no wall clock** — a pure function of the decision |
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
(deterministic, commutative). Convergence mechanics, not settlement
policy — `verify_loop_atomicity` is the guard (see its docstring).

### `PartialLoopError(RuntimeError)`
A book holds a loop missing some of its fills. Raised, never repaired —
evicting a settled loop would be a finality rollback.

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
Exact, self-contained, re-runnable by settlement. Gates, in order:

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

## 8. `loopmarket.settlement` — trust nothing, commit atomically

### `LoopProposal(loop, book_root, ontology_root, solver, found_at)` — frozen
`.to_record()` → the `loop/` record (see §13).

### `Receipt(accepted, loop_id, reason="", book_root="")` — frozen
`book_root` is the post-settlement root when accepted.

### `Settlement` (Protocol)
`submit(proposal) -> Receipt`.

### `MockSettlement(registry, ontology, *, min_surplus=0.0, require_per_node=True, clock=time.time, verifiable_oracles=VERIFIABLE_ORACLES)`
`VERIFIABLE_ORACLES = frozenset({"countersign"})`. The checklist of
`submit`, in order (U3 — any future backend keeps this shape):

0. **pins**: `proposal.ontology_root` must *equal* the settlement's own
   `ontology.root` (absence and mismatch both refuse; `'' == ''` keeps
   the in-memory flow working)
1. every offer exists in the *current* book, is unfilled, is not
   tombstoned, is used once, and names an oracle type in
   `verifiable_oracles`
2. every leg re-derived with `check_match` against the current book and
   the settlement's own catalogue
3. arithmetic: `surplus >= min_surplus`; indivisible loops additionally
   need `per_node_ok` (while `require_per_node`, the pre-P2 policy)
4. one atomic commit: all fills + the loop record under one new root

---

## 9. `loopmarket.solver.agent` — the baseline species

### `SolverAgent(registry, ontology, settlement, solver_id="solver-0", min_surplus=0.005, max_loops_per_step=10)`

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

Constants: `MAKER = "maker"`, `SETTLEMENT = "settlement"` (book roles).

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

| key class | maker book | settlement book |
|---|---|---|
| `offer/` | content address re-derived; readable version; `maker == owner` **or** valid detached `sig/` in the same book | silently skipped (contains its base fold; not its speech) |
| `withdraw/` | only for an offer this book holds with `maker == owner` | silently skipped |
| `sig/` | staged when it verifies; foreign-offer sigs stage with their offer | silently skipped |
| `fill/`, `loop/` | **rejected** ("settlement keys in a maker book") | staged |
| anything else | rejected ("unknown keyspace") | silently skipped |

---

## 12. The keyspace

One book = one recordstore keyspace = one root per version:

```
offer/<offer_id>        the immutable offer record (v1 or v2)
sig/<offer_id>          detached maker signature, hex (never in identity)
withdraw/<offer_id>     1 — monotone tombstone: the offer is closed
fill/<offer_id>         {"loop": <loop_id>} — pure function of the decision
loop/<loop_id>          the settled proposal record
idx/c/<concept>/<id>    1 — aggregator-derived only
idx/t/<bucket>/<id>     1 —      "
idx/g/<prefix>/<id>     1 —      "
origin/<offer_id>       {"owner", "root"}        (provenance store)
reject/<owner>/<key>    {"owner", "reason"}      (provenance store)
announce/<owner>        {"role", "root"}         (announcement store)
```

Maker books write `offer/`, `sig/`, `withdraw/` only; settlement books
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
clock: equal settlements must produce equal roots on every replica).

## 14. Invariants (binding; tests enforce them)

| id | statement |
|---|---|
| **B1** | the core imports and works with no network, no Bee node, no optional dependency |
| **B2** | dependencies point one way: loopmarket → ontodag → recordstore → (Swarm, lazily) |
| **U1** | exactly one side of every offer is a Thing, one is Tokens, and the token issuer is the maker |
| **U2** | offers are immutable canonical values; `from_record` dispatches on `"v"` and raises on unknown versions; offers re-encode in their native version |
| **U3** | settlement trusts no solver: pin equality, per-leg re-derivation against the current book, full re-checks, one atomic commit |
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

Live test suites: `tests/test_swarm_book.py` (the P0 triangle on a live
book), `tests/test_swarm_federation.py` (per-maker feeds, two
aggregators, settlement feed, follower). Both skip without the
variables; both use timestamped topics so reruns inherit nothing.

## 16. Exceptions

| exception | raised by | meaning |
|---|---|---|
| `ValueError` | constructors, `from_record`, `attach_signature`, `announce` | malformed values, unknown record versions, non-recovering signatures, unknown roles |
| `KeyError` | `get`, `withdraw` | no such offer in this book |
| `PartialLoopError` | `verify_loop_atomicity` (reconciled commits, folds) | a merge stranded a partially-filled loop (U11) |
| `RuntimeError` | `sigs.*` without `[sig]`; `Ontology.persistent` without `EagerOntoDAG` | missing optional machinery |
| `TypeError` | `Ontology.commit` on in-memory catalogues | nothing to commit to |
