# loopmarket — Reference Manual

*The public API, record formats, keyspace, and invariants, precisely.
Tutorial: [USER-GUIDE.md](USER-GUIDE.md). Rationale:
[ARCHITECTURE.md](../ARCHITECTURE.md). Working rules and roadmap:
[CLAUDE.md](../CLAUDE.md).*

Floors: Python ≥ 3.11, `ontodag` ≥ 0.26.1, `recordstore` ≥ 0.21.0.
Extras: `[swarm]` = `recordstore[bee,feeds]` (Bee blobs + signed feeds),
`[sig]` = `eth-keys`, `eth-hash`, `coincurve`, `cryptography` (detached
signatures; sealed handoffs, notices and case records), `[chain]` = `web3`
(the contracts on Gnosis: announcements, beats, the escrow), `[evm]` =
`web3`, `py-solc-x`, `eth-tester` (compiling the contracts, a local EVM),
`[test]` = pytest.

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

### `TimeWindow(start: int, end: int | None = None)`
Frozen. A half-open interval `[start, end)` in unix seconds (UTC).
Raises `ValueError` unless `end > start`.

| member | meaning |
|---|---|
| `TimeWindow.from_iso(start, end)` | classmethod; ISO-8601 strings, naive = UTC |
| `.contains(other)` | fits-within: `other` entirely inside `self` |
| `.overlaps(other)` | non-empty intersection |
| `.intersection(other)` | `TimeWindow` or `None` |
| `.is_open_at(t)` | `start <= t < end`; `end=None` is open-ended — stands until withdrawn (v3 records only) |
| `.to_record()` | `[start, end]` (`end` may be `null`) |

### `GeoDisc(lat: float, lon: float, radius_m: float)`
Frozen. A disc on the sphere — **v1/v2 records only**: since the v3 record
(2026-09-12) a place is a cell or region term in the conjunction, and this
class exists to read and match old records among themselves; nothing
creates a new disc. Raises `ValueError` for out-of-range centre or
negative radius.

| member | meaning |
|---|---|
| `.contains(other)` | fits-within (haversine, 1e-9 m tolerance) |
| `.intersects(other)` | a handover point both parties can reach |
| `.to_record()` | `[lat, lon, radius_m]` |

`haversine_m(lat1, lon1, lat2, lon2) -> float` — great-circle metres.

### `q(x) -> Fraction` / `rat(x) -> str`
Exact numbers (invariant U9, the v4 record, 2026-09-14). `q` reads an int
or `Fraction` as is, a string as the decimal or `n/d` it spells, a float as
the shortest decimal that prints it (`99.99` is 9999/100); `rat` writes the
one v4 spelling, `n/d` reduced or `n` alone. Everything clearing
re-verifies goes through `q`; the solver's `-log` search may still float.

### `Thing(concepts, qty=1, unit="unit", divisible=None, step=None, min=0)`
Frozen. A conjunction of catalogue category names plus quantity.
`concepts` is normalized to a sorted, deduplicated tuple (order never
matters to identity); the spelling of each term is the caller's — the CLI
stores the catalogue's canonical spelling (`surface.elaborate`). Numbers
may be ints, `Fraction`s, floats or spelled strings; a string is read by
`q` at construction. `step` is the granularity a fill must be a multiple
of: `0` continuous, the whole `qty` indivisible (the default), `1` whole
apples out of a thousand, `25` for 25 kg sacks; `divisible` is the v1–v3
field and a shorthand (`True` is `step=0`, `False` `step=qty`) and is
derived from `step`. `min` is the give-side floor, the least one fill may
take (0: none), a multiple of `step`. `.takes(qty)` is the matching rule:
within `qty`, not below `min`, a positive multiple of `step`. Raises
`ValueError` on empty concepts, non-positive qty, a step or floor outside
`[0, qty]`, a floor off the step, or `divisible` disagreeing with `step`.
`.to_record(v)`: v1–v3 `{"concepts","qty","unit","divisible"}` with the
numbers as stored; v4 `{"concepts","qty","unit","step","min"}` with `rat`
strings.

### `Parts(parts: tuple[Thing, ...])`
Frozen. A composed want: at least two things wanted together, all or
nothing, one price for the lot (`P2-loop-selection.md` §10, `cli.md` §13;
v4). Want side only. Each part is served by its own give and the fill
names which.

### `Tokens(issuer: str, amount)`
Frozen. An amount on the maker's personal scale (int, `Fraction`, float or
spelled string). Raises `ValueError` unless `amount > 0`. `.to_record(v)`:
the stored number for v1–v3, a `rat` string for v4.

### `Offer(...)` — frozen; the one uniform intention

```
Offer(maker, gives, wants, valid, service=None, where=None,
      ontology_root="", bond=0.0, oracle="countersign", arbitrator="",
      requires=None, nonce=<auto: unix ms>, registry_version="", contract_version="",
      claim_max=0, underlying="", exercise=None, v=4)
```

v5 (2026-09-18/19, admissibility by declaration): `bond` is a `Bond(asset:
Thing, value, escrow)` — a deposit worth `value` on the giver's scale, held
by the escrow contract at `escrow`, reserved per fill as bond × taken /
quantity (`Bond.reserved`) — and `requires` a `Requires(point, ladder,
accepts, oracles, escrows)`: the neutral point on a no-show on the maker's
scale, the cancellation ladder `((lead_seconds, amount), ...)` descending
to 0 (`.at(lead)` linear), the `Acceptance(concepts, unit, price)` entries
naming the asset categories accepted as compensation each at the maker's
price per unit, the witness types and escrow kinds accepted. A requirement
or a deposit makes the offer v5; v4 re-encodes byte for byte.

v6 (2026-09-29, R1): `Requires` gains `counterparty` (a tuple of
`Credential(category, kinds, min_bond=0, roots=(), max_root_age=0)` — what
the other side must present, checked by the counterparty gate), `legs`
(`RequiredLeg(category, accept)`: an operator give under `category` from a
giver `accept` admits, composed with the thing — cover, an inspection),
`resolvers` (an `Accept(keys=(), roots=(), min_deposit=0, clean_for=0,
issuance=())`: the resolvers this offer accepts — by key, or since
2026-09-29 by property (`arbitrators.py`: every rung that can rule
accredited under a named root as an `arbitrator`, at least `min_deposit` on
the requirer's scale at stake on a reversed ruling, no reversal within
`clean_for` on a record at least that long; `issuance` not read yet), on
either side, the leg's resolver the first candidate both admit) and `claim_period` (seconds: the claim period a want asks of a
give's deposit); the offer gains `claim_max` (a give's longest claim
period), `underlying` and `exercise` (an option: the id of the plain offer
it holds and its `TimeWindow`, given together). Any of them makes the
offer v6; every requirement the build cannot check fails closed (U7), and
`tests/test_v6_record.py` pins a v4/v5 corpus's ids.

v7 (2026-09-29, C5): `Bond(asset, value, escrow, deductible=0)` — the
deductible an amount of the deposit's own asset for the give's whole
quantity (`deductible_share(taken, whole)`, `payable(taken, whole)` = the
reserved share less it), `0 <= deductible < asset.qty`; a ruled claim pays
at most the share less the deductible, and a deposit counts against a
wanter's point only up to `payable`. A deductible is the only v7 form.

### `Statement(subject, category, issuer, kind, as_of, until, evidence, path, paid_by, deposit=None, scheme="", issuance="", v=1)` — frozen

The one shape the counterparty gate reads (R1/R2): a claim about the key
`subject` in `category`, by `issuer`, of a `kind` in `STATEMENT_KINDS`
(`"self-bonded"`, `"attested"`, …), valid `as_of`..`until`, with its
`evidence` reference, the accreditation `path` from the issuer up to a
trust root, who paid (`PAID_BY`), and optionally the `(offer id, escrow)`
of a deposit that backs it. Content addressed: `.statement_id` is the
SHA-256 of `canonical_bytes()`. Presented in the subject's own book as
`cred/<subject>/<statement id>` (`OfferRegistry.present`).

Validation (`ValueError`): exactly one of `gives`/`wants` is a `Thing`
(or, on the want side of a v4 record, `Parts`) and one a `Tokens` whose
`issuer == maker` (invariant U1); `bond >= 0` (v<5) or a `Bond` (v5+); `v in {1, …, 7}`; an
option names both its `underlying` (a 64-hex id) and its `exercise`; v1
records carry no registry/contract pins; parts, a `step` other than 0 or
the whole quantity, and a floor are v4 forms.

| member | meaning |
|---|---|
| `.kind` | `"give"` (gives a Thing) or `"want"` (wants one); constants `GIVE`, `WANT` |
| `.thing` / `.tokens` | the respective side (`.thing` raises for a composed want) |
| `.composed` / `.parts` | a want of several parts; the things this offer is about — one for a give or a simple want, several for a composed want |
| `.amount` / `.unit_price` | the price of the lot, exact; scale units per thing-unit, exact (`Fraction`; not for a composed want) |
| `.to_record()` | dict, **in the offer's native version** (a v1 offer re-encodes as v1 — version is identity, U2) |
| `Offer.from_record(rec)` | classmethod; dispatches on `rec["v"]`, **raises `ValueError` on unknown versions** |
| `.canonical_bytes()` | recordstore canonical JSON of `to_record()` |
| `.offer_id` | SHA-256 hex of `canonical_bytes()` — the content address |

`bond`, `oracle`, `arbitrator` are carried in identity from day one; since
v5 a maker's *requirement* of them is enforced (`matching.meets`, the
contract's verifier), and since 2026-09-19 a deposit naming an escrow
counts only up to what the contract holds (`meets(held=)`).

### `give(maker, thing, amount, *, valid, service=None, where=None, **kw) -> Offer`
### `want(maker, thing_or_parts, amount, *, valid, service=None, where=None, **kw) -> Offer`
The current record by default — v4, or the version its fields need: a
`requires` or a `Bond` deposit v5, a v6 requirement field, `claim_max`
or an option v6, a deductible v7 — unless `v=` says otherwise; passing
`service`/`where` yields the v2 field form.
Convenience constructors; `**kw` passes through (`nonce=`, pins, etc.).
Splat `**Ontology.pins` to pin the catalogue.

Order-book synonyms, kept indefinitely: `ask = give`, `bid = want`
(functions), `ASK = GIVE`, `BID = WANT` (constants), and `Match.ask` /
`Match.bid` (properties aliasing `Match.give` / `Match.want`).

---

## 2. `loopmarket.spacetime` — geohash cells

The spelling of a place: input vocabulary only, the cell is the stored
name and ontodag's prefix kind orders it. (The day-bucket and cell-prefix
chains that fed the `idx/{t,g}` index retired with it, 2026-09-12.)

| function | meaning |
|---|---|
| `geohash(lat, lon, precision=6)` | plain geohash, no dependencies |
| `cell_bounds(cell)` | `(lat_lo, lat_hi, lon_lo, lon_hi)` — the bit interleaving run backwards |
| `cell_for_coords(lat, lon, radius_m, max_precision=6)` | the finest cell that **contains** the whole radius — what a bare `LAT,LON,R` (or `loop place NAME LAT,LON,R`) becomes |

---

## 3. `loopmarket.ontology` — the catalogue facade

### `Ontology(dag: OntoDAG | None = None)`

| member | meaning |
|---|---|
| `.assert_edge(sub, supers, *, bond=0.0)` | assert fits-within; missing supers created under the root; `bond` recorded intent (P3) |
| `.load({sub: [supers, ...]})` | bulk, order-independent declaration; returns self |
| `.known(concept)` | vocabulary membership: a node, or a parametric term of a declared head the DAG can order — incl. a role term naming a place, region or floor node (ontodag #15); a name outside the head's dimension fails closed |
| `.covers(wanted, offered)` | `offered` fits within `wanted` (equal or descendant); **False for unknown names** (U7) |
| `.satisfies(offered, wanted)` | every wanted term answered: a category or descriptive term by an offered concept that fits within it (the want is the wider cone); a **handover coordinate** — a bare geo/time term or a term of a role under a marked dimension — by an offered coordinate of the same head that fits within it *or contains it*; an **operator term** (`transport(bicycle)`, a category under `operator`) by an offered operator term whose category fits within it and whose argument — the operator's own want — contains the wanted argument constraint by constraint (`bicycle ⊑ small-item`; an offered constraint the want does not answer refuses); a head the want does not name constrains nothing; a conjunction with provably disjoint same-head terms describes nothing, on either side |
| `.declare_roles({head: base})` | seed convenience: put each head under its base dimension head — a role of that dimension, whose parameters may name its nodes (ontodag #15); a catalogue write. |
| `.declare_handover(heads)` | mark base dimension heads (`geo`, `time`) as handover coordinates under the `handover` marker; roles under them inherit it; prelude adopted on demand |
| `.declare_descriptive(heads)` | opt a geo/time head out (`made_in`, `made`) under the `descriptive` marker: its terms describe the thing and match one-way |
| `.handover_class(concept)` / `.handover_heads()` | the head whose coordinate a term states (`None` for categories and descriptive terms; a bare place node states `geo`'s); the marked base heads |
| `.declare_operator({category: (input_head, output_head)})` | `{"transport": ("from", "to"), "storage": ("depart", "arrive")}`: the category under the `operator` marker (created if absent), the two ends — roles of one dimension — under `operator-input`/`operator-output`; a give naming the category and both ends moves a thing along that dimension (composition, `P2-loop-selection.md` §10); the category's parenthesised argument is what it accepts. 0.5.0's `{base: (in, out)}` shape raises |
| `.operator_of(term)` / `.argument(term)` | the operator category a term names (`transport(bicycle)` and bare `transport` → `transport`; None otherwise); the constraints of its argument in ontodag's canonical spelling (`transport(small-item mass(..8000g))` → `("mass(..8kg)", "small-item")`; bare → `()`; a term the catalogue refuses → `()`, and `known` is False) — the term is ontodag's graph kind (#19, 0.26.1) |
| `.ends(concepts)` / `.accepts(concepts, operator_terms)` | the moves an operator give states, `[(base, input_term, output_term)]`; whether a thing fits every constraint of the operator terms' arguments (the payload check of `check_composition`) |
| `.base_head(head)` / `.coordinate(concepts, base)` / `.bare(term)` | a role's base head; the bare coordinate of `base` a conjunction states; a role term respelled as the bare coordinate it denotes (`to(u2e4)` → `geo(u2e4)`, `from(shop)` → `shop`) |
| `.head_kind(head)` | the registry kind a declared head orders values by, else `None` |
| `.root` | canonical root of the last committed state, `''` if in-memory/uncommitted |
| `.pins` | `{"ontology_root", "registry_version", "contract_version"}` — splat into `give`/`want` (U10) |
| `Ontology.persistent(record_store)` | classmethod; an `EagerOntoDAG`-backed catalogue with committable roots |
| `.commit()` | commit, return the root; `TypeError` on in-memory catalogues |

---

## 4. `loopmarket.registry` — the book

Key prefixes (module constants): `OFFER="offer/"`, `SIG="sig/"`,
`WITHDRAW="withdraw/"`, `FILL="fill/"`, `LOOP="loop/"`, and the sidecars
`HANDOFF`, `CRED`, `NOTICE`, `CURE`, `OPTION`, `EXERCISE`, `ITEM`, `KEY`,
`CASE` (§12).

### `OfferRegistry(store)`

Writing:

| member | meaning |
|---|---|
| `.publish(offer) -> offer_id` | store the offer record (nothing else — there is no index in the book) |
| `.publish_many(offers) -> [ids]` | |
| `.withdraw(offer_id)` | monotone tombstone; survives merges; `KeyError` if the offer isn't in this book; re-publishing identical content does not un-withdraw |
| `.absorb(other)` | re-assert another book's entire content as this writer's base; canonical addressing makes the re-commit reproduce the source root (clone verification). O(book) |
| `.attach_signature(offer_id, sig_hex)` | store a detached signature; `ValueError` unless it recovers to the offer's maker; needs `[sig]` |
| `.mark_filled(fills, loop_id, loop_record, extra=None)` | clearing's stroke: fills (whole, or per loop for a divisible give taken in part) + the loop record + `extra` records (holds, exercises, item claims) under one commit; **no wall clock** — a pure function of the decision |
| `.publish_contact_card(address, sig_hex)` | `key/<address>`: a signature over sha256(`b"loopmarket contact card\n"` + address) from which anyone recovers the key's public key (`sigs.sign_contact_card`) — how a key with no signed offer, an arbitrator, is sealed to |
| `.write_case(loop_id, offer_id, kind, side) -> key` | a sealed claim, answer or ruling (`case.sealed`) at `case/<loop>/<offer>/<kind>/<to>`; the fold admits it only as its writer's speech |
| `.commit(*, reconcile=True) -> root` | land staged changes; reconciled commits three-way-merge with concurrent writers under `or_set_resolver`, then run `verify_loop_atomicity` |

Reading:

| member | meaning |
|---|---|
| `.snapshot() -> (root, frozen OfferRegistry)` | the unit a solver works against (U4) |
| `.get(offer_id) -> Offer` | `KeyError` if absent |
| `.is_filled(offer_id)` / `.is_withdrawn(offer_id)` | |
| `.signature(offer_id) -> str | None` | |
| `.loop_of(offer_id) -> str | None` / `.loops_of(offer_id)` | the loop that filled the offer whole; every loop with a fill on it (a divisible give taken in part) |
| `.taken(offer_id)` / `.availability(offers, now=None)` | what the fills have taken; `{offer id: available}` for many — what the solver passes as `available=` |
| `.contact_card(address)` / `.case_record(loop_id, offer_id, kind, to)` / `.cases()` | read the `key/` and `case/` sidecars; `cases()` yields `(loop, offer, kind, record)` |
| `.notice(loop_id, offer_id)` / `.cure(loop_id, offer_id)` | read the notice and the cure |
| `.exercise_records(offer_id, holder, taken, now, loop_id)` | the records an exercise writes with its fill: what it took of the holder's holds |
| `.attach_handoff(loop_id, offer_id, record, *, fold=None)` | store a sealed handoff (`handoff.seal` + `from`/`to`) beside my *filled* offer, `handoff/<loop_id>/<offer_id>`; the fill is checked against `fold` (the clearing book) when given; `ValueError` otherwise |
| `.handoff(loop_id, offer_id) -> dict | None`, `.handoffs()` | read the sidecars |
| `.present(statement, presentation=None) -> statement_id` | a statement about a key, `cred/<subject>/<id>` (R2); the fold admits it only in its subject's own book |
| `.statements(subject=None)` | `(Statement, presentation)` pairs presented here |
| `.send_notice(loop_id, offer_id, side)` / `.send_cure(...)` | a sealed notice to the giver, `notice/<loop>/<offer>`, and the giver's cure, `cure/<loop>/<offer>` (R6, `notice.sealed`) |
| `.holds(offer_id)` | `(option loop, hold record)` pairs on an offer, key order (C2): `{option, holder, until, qty}` |
| `.held(offer_id, now)` / `.held_by(offer_id, holder, now)` / `.exercisable(offer_id, now)` / `.hold_left(offer_id, option_loop)` | what active holds keep (a function of time: expiry needs no write); what a holder may take now (its window open); what all holders may; what exercises left of one hold |
| `.available(offer_id, now=None)` | what a fill may still take: the quantity less fills and, given `now`, less active holds |
| `.item_claims(h, maker)` / `.item_claimed(h, maker, now, *, offer_id="")` | the maker's `item/<h>/<maker>/<loop>` claims; whether one is active through another offer (I2) |
| `.offers(*, now=None, include_filled=False)` | active offers: fills and tombstones filtered, expiry filtered when `now` given; `include_filled=True` disables all filtering (full-book scan) |
| `.verify_loop_atomicity()` | raises `PartialLoopError` unless every `loop/` record holds all its fills and every fill points at a present loop, and every `option/`, `exercise/` and `item/` record names a present loop (U11) |

### `or_set_resolver(key, base, ours, theirs)`
Merge policy for concurrent writers: add-only presence everywhere; a
doubly-claimed `fill/` keeps the lexicographically smaller loop id
(deterministic, commutative). Convergence mechanics, not clearing
policy — `verify_loop_atomicity` is the guard (see its docstring).

### `PartialLoopError(RuntimeError)`
A book holds a loop missing some of its fills. Raised, never repaired —
evicting a cleared loop would be a finality rollback.

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

### `check_match(give, want, ontology, *, now, available=None, held=None, gate=None) -> Match | None`
Exact, self-contained, re-runnable by clearing. `available` is `{offer id:
what is left}` (`OfferRegistry.availability`; absent = the whole
quantity), `held` `{offer id: what the escrow holds}` (a deposit naming an
escrow counts only up to it), `gate` the `CounterpartyGate` (§8f) over the
snapshot — no gate, and every requirement that needs one fails closed. A
composed want returns `None` (its legs are `check_parts`'). Gates, in
order:

1. kinds: give is `GIVE`, want is `WANT`, distinct makers
2. the record line: both v1/v2 or both v3+ (a disc is not a cell)
3. an option give's underlying (`gate.option_fault`, §8f), an item term's
   whole id and the maker's one open claim per item (`gate.item_fault`, §8h)
4. **requirements**: each side's `requires` met by the other side's
   declaration (`meets`, below)
5. validity: both offers open at `now`
6. (v1/v2 only) service windows and discs intersect
7. quantity: `give.thing.takes(want.qty, left)` — within what is left
   (plus the holder's own hold), not below the floor, on the step — and
   equal units
8. **pins**: if the verifying catalogue is pinned (`ontology.root`), both
   offers must carry all three pins; mixed pinning (one side declares,
   the other silent) always refuses; equal `ontology_root` when both
   pin; registry/contract versions refuse on **major** skew (minor is
   additive and interoperates: ontodag's CONTRACT.md G7 promises a newer
   minor never takes an answer away). The on-chain verifier applies the
   same rule: a beat pins the majors (`"4"`, `"0"`) and admits every offer
   pinned within them
9. meaning: `ontology.satisfies(give concepts, want concepts)`

### `meets(mine, other, ontology, *, taken=None, whole=None, held=None, gate=None, legs_checked=False) -> bool`
Is `mine`'s `requires` met by `other`'s declarations (v5+, admissibility
by declaration)? The witness type and escrow kind accepted; a neutral
point covered by the share of `other`'s deposit reserved for this fill
(`taken` of `whole`), its category under an accepted one through the
catalogue, at the acceptance's price, counted up to `held` and to
`Bond.payable`; each `counterparty` credential through `gate.faults`; an
`Accept` of resolvers through `arbitrators.admits`; a want's `legs` left to
the composed leg when `legs_checked` (`legs_faults(want, gives, ontology,
*, gate=None)` lists what a composed leg's operator gives fail of them).
No requirement: `True`; a requirement nothing can check: `False` (U7).

### `candidate_matches(offers, ontology, *, now, available=None, held=None, gate=None) -> Iterator[Match]`
The exact check over the full give × want product. The recall baseline.

### `check_parts(want, gives, ontology, *, now, available=None, held=None, gate=None) -> Leg | None`
The exact check of a composed want's leg (v4): give `i` serves part `i` —
the gates against that part (quantity on the give's step and floor, units,
pins) and `satisfies` — every give distinct, all or nothing. Re-run by
clearing (U3). `parts_legs(offers, ontology, *, now, limit=64)` is the
baseline search: per part the gives that serve it, every combination of
distinct gives checked exactly, deterministic order.

### `check_aggregate(want, gives, quantities, ontology, *, now, available=None, held=None, gate=None) -> Leg | None`
The exact check of an aggregated leg (the six lifters, 2026-09-14): one
want of one thing met by several gives of it, each contributing a share it
may give (`Thing.takes`, within what is left of it), the shares summing to
the want's quantity. `aggregate_legs(offers, ontology, *, now,
available=None, max_gives=6, max_alternatives=8)` is the deterministic
depth-first baseline search, largest shares first.

### `Leg(want: Offer, gives: tuple[Offer, ...], quantities=None)` — frozen
One want met by one or more gives — the hyperedge of `P2-loop-selection.md`
§10/§11. `Leg.from_match(m)`; `.head` (the buyer), `.tails` (the givers),
`.offer_ids`, `.simple` (one give), `.key` (`give+give>want`, the sort key),
`.parts` (a composed want's leg), `.quantities` (an aggregated leg's shares;
they enter `.key`, so another split is another decision), `.taken(i)` (the
quantity taken from give `i`: its share, the part's, the want's, or an
operator's whole run), `.value_given(i)` (its unit price times that
quantity — what the giver is owed).

### `check_composition(want, gives, ontology, *, now, available=None, held=None, gate=None) -> Leg | None`
The exact check of a composed leg (2026-09-13): the first give is the
thing, every further give an operator — a give naming a category under
`operator` and the two ends of a dimension (`transport(small-item)
from(barcelona) to(barcelona)`). The thing must fit the operator's
argument (`Ontology.accepts`: the payload check — the box goes, the piano
does not); each operator's input coordinate must be comparable with the
thing's coordinate as it stands (one contains the other) and its output
replaces it; the thing so moved must satisfy the want; every give passes
`check_match`'s gates against the want (the operator without the quantity
gate). An argument-only operator (`insure(...)`, `inspect(...)`, declared
by `Ontology.declare_argument_operator`) attaches to the thing when its
argument accepts it and moves nothing; a want's `requires.legs` are
checked here (`legs_faults`). Re-run by clearing (U3).

### `composed_legs(offers, ontology, *, now, max_hops=2, available=None, held=None, gate=None) -> Iterator[Leg]`
Baseline composition search: every want × thing give that does not already
match it × every chain of up to `max_hops` operator gives, checked exactly;
a chain only where a shorter one does not reach; deterministic order.

---

## 6. `loopmarket.dimensions` — indexed candidate generation

Recall-exact against the baseline (enforced by test); **one `get` per
want**, the want's own conjunction as the query, no set arithmetic on the
answer.

| member | meaning |
|---|---|
| `DimensionIndex(ontology)` | files gives into a **deepcopy** of the catalogue (derived, per-solver, never merged/persisted) under exactly the terms they carry, plus a record-line marker |
| `.file(offer) -> bool` | index a give under its concepts and its line marker; `False` for non-gives, unknown vocabulary (U7's outcome) and a conjunction ontodag refuses |
| `.candidates(want) -> set[str]` | one `get([line marker, *one-way terms], items_only=True)`: the gives inside every wanted category cone; handover coordinates are left to `check_match` (a give that *contains* the want's place sits above it, not in its cone) |
| `candidate_matches_indexed(offers, ontology, *, now, index=None)` | drop-in for `candidate_matches` |

The v1/v2 window and disc are fields the exact check gates, not terms;
they are not filed. ontodag's `items_only` (#14), role parameters naming
nodes (#15) and the dimension cache (#18) are all in the 0.26.1 floor.

---

## 7. `loopmarket.graph` — loops and circulations

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

### `enumerate_cycles(matches, *, max_legs=5, limit=2000, min_surplus=0) -> (list[Loop], complete)`
Every simple cycle over the whole match multigraph (not the best-rate
reduction) up to `max_legs` legs, each judged on its own surplus and
per-node feasibility, in canonical order; `complete` is `False` when
`limit` cut the enumeration (the agent then tops up with Bellman–Ford).
The candidates `selection.pack` chooses among (§8d) — the 2026-09-18 fix
of the recall gap above.

### `Circulation(legs: tuple[Leg, ...])` — frozen
A set of legs, some possibly composed, in which every maker both gives and
receives; each offer once, a maker may take part through several offers.
Raises `ValueError` otherwise. `Circulation.from_loop(loop)` lifts a cycle,
and `loop_id`/`surplus` agree with the `Loop` there.

| member | meaning |
|---|---|
| `.nodes` / `.offer_ids` / `.simple` | sorted makers; every offer id; all legs single-give |
| `.as_loop()` | the `Loop`, when every leg is simple, each maker takes part once each way and the legs chain; else `None` |
| `.potentials(gain=1.0)` | the least node potentials `e ≥ 1` with `want.price·e[buyer] ≥ gain·Σ give.price·e[giver]` on every leg — the clearing prices as the dual of §11 — or `None` when none exist; a Bellman–Ford-shaped fixpoint over the legs in sorted order (U6) |
| `.feasible` | potentials exist at gain 1 |
| `.surplus` | `(1+t)^k − 1` for the largest uniform per-leg gain `t` with potentials (bisection); for a simple cycle exactly `Loop.surplus`; negative when infeasible |
| `.per_node_ok` | each maker's wants cover its gives on its own scale — `Loop.per_node_ok` over any shape |
| `.loop_id` | a simple cycle's `Loop.loop_id`; else SHA-256 of the sorted leg keys |

### `find_circulations(legs, *, min_surplus=0.0, limit=10, max_legs=6, budget=50_000) -> list[Circulation]`
The baseline hunt: depth-first from each leg in sorted order, always
extending at the smallest unbalanced maker, so the set stays connected and
balances; the first set with surplus ≥ `min_surplus` is taken and its
offers retired. Deterministic (U6); bounded by `max_legs` and a node
budget. Simple cycles are found first by `ExchangeGraph` in the agent.

---

## 8. `loopmarket.clearing` — trust nothing, commit atomically

### `LoopProposal(loop, book_root, ontology_root, solver, found_at, register_roots=())` — frozen
`loop` is a `Loop` or a `Circulation` (`.circulation` lifts either).
`register_roots` pins every register a leg's requirement names as a trust
root, `((register id, root), ...)` (R3a; `register.named_registers`).
`.to_record()` → the `loop/` record: every leg names `want`, `gives` (all
of them) and `give` (the first — the 2026-08 shape's key, kept for
readers); a simple leg carries its `rate`; a composed set carries the
node `potentials`. A simple cycle's record is byte-identical to before.

### `Receipt(accepted, loop_id, reason="", book_root="")` — frozen
`book_root` is the post-clearing root when accepted.

### `Clearing` (Protocol)
`submit(proposal) -> Receipt`.

### `MockClearing(registry, ontology, *, min_surplus=0.0, require_per_node=True, clock=time.time, verifiable_oracles=VERIFIABLE_ORACLES, chain_fills=None, escrow_held=None, register_at=None, span=None, register_latest=None, resolver_profile=None)`
`VERIFIABLE_ORACLES = frozenset({"countersign", "possession",
"photo-match"})` — the countersign and the door's two witness types
(`witness.py`). `chain_fills(offer_id)` is what the chain has recorded as
taken (`BeatClearing.filled`: the chain is the fill authority), and
`escrow_held(offer_ids)` what the escrow holds behind each deposit;
`register_at(register_id, root)` opens a pinned register, `register_latest`
its newest root (R5), `span` reads a `time(...)` term's window and
`resolver_profile(key)` a resolver's chain record — together the
`CounterpartyGate` clearing builds itself (`.gate(register_roots, *,
now)`). The checklist of `submit`, in order (U3 — any future backend
keeps this shape):

0. **pins**: `proposal.ontology_root` must *equal* the clearing's own
   `ontology.root` (absence and mismatch both refuse; `'' == ''` keeps
   the in-memory flow working), and every register a leg names as a
   trust root is pinned in `register_roots`
1. every offer exists in the *current* book, is unfilled (in the book and
   on chain), is not tombstoned, is used once, and names an oracle type
   in `verifiable_oracles`
2. every leg re-derived against the current book, what fills have left of
   each give and the clearing's own catalogue and gate (`.verify_leg(leg,
   *, now, available, held=None, gate=None) -> reason | None`):
   `check_match` for a simple leg, `check_composition`, `check_parts` or
   `check_aggregate` for the others; across legs, an inspector is no
   party to the item it inspects
3. arithmetic: node potentials exist (a simple cycle: product > 1),
   `surplus >= min_surplus`; indivisible legs additionally need
   `per_node_ok` (while `require_per_node`)
4. one atomic commit: all fills, the loop record, and the holds,
   exercises and item claims its legs write (`.hold_records`) under one
   new root

`.rehearse(proposal)` runs the checklist without committing — what the
challenger uses.

### `ChainClearing(registry, ontology, *, beat_client, snapshot_of=None, **kw)`
`MockClearing`'s checklist, then the beat: each accepted loop is asked of
the contract's verifier (`beat.BeatClient.verdict`) and only then posted
as one optimistic beat on `BeatClearing` with its bond; `chain_fills`
defaults to the contract's `filled`. The receipt's reason names the beat
(§8b).

---

## 8b. `loopmarket.beat` — the beat on chain (P2, 2026-09-15)

| name | one line |
|---|---|
| `submission(proposal, snapshot, *, potentials=None, records=None, gate=None, ontology=None) -> Submission` | pure: every leg as `LoopVerifier.Leg` (value blobs and trie paths under the snapshot's root, quantities taken as `n/d`, each option give's underlying record), `leg_hashes` = keccak of each leg's and its statements' ABI encoding, `fills` (with each give's taker), `holds` and `claims` (C4, I3: an item claim's end from the clearing's `item/` `records`), `registers` (the pinned register roots), `statements` (R3b: the ones `gate.chosen` accepts over the snapshot, with their proofs), `makers`/`potentials`, `pins` (book root, catalogue root, the registry and contract *majors* of the first want, addressing); refuses a snapshot that is not the proposal's book root, and a leg whose evidence it cannot build |
| `commitment(sub) -> (legs, potentials, registers)` | the three hashes `BeatClearing.submit` stores — what a rebuilt submission must equal |
| `find_evidence(state, books, *, ontology=None, register_at=None, span=None)` | the `loop/` record behind a beat whose rebuilt submission hashes to its commitments |
| `BeatClient(rpc_url, address, *, key=None, client=None)` | `.bond()`, `.submit(sub) -> (beat, receipt)`, `.challenge(beat, index, sub) -> reason`, `.finalize(beat)`, `.filled(offer_id) -> Fraction`, `.beat(beat) -> dict`, `.pending_holds/pending_claims(beat)`, `.held_against(offer_id, taker, at)`, `.item_claim(item, maker)`, `.verdict_of(sub, index, ...)`; web3 lazy (`chain` extra) |
| `abi()` | the compiled `BeatClearing` (ABI, bytecode) from `loopmarket/contracts/BeatClearing.json` (inside the package); `LegVerifier.json` and, since 2026-09-29, `StatementVerifier.json` beside it, all three deployed by `deploy(...)` |
| `clearing.ChainClearing(registry, ontology, *, beat_client, ...)` | `MockClearing`'s checklist, then the beat posted; the receipt's `reason` is `beat N` |

## 8c. `loopmarket.auction` — the sealed-proposal beat (P2, 2026-09-18)

| name | one line |
|---|---|
| `bundle_bytes(proposals)` / `seal(bytes, salt)` | a proposal is a bundle of loop records pinning one root; sealed as keccak(bytes ‖ salt) |
| `outcome(beat, revealed, snapshot, ontology, *, now, chain_fills=None, baseline=...)` | re-derive every revealed loop (U3), add the baseline's loops as the reserve bid, the fairness filter, select the set worth most under the offers' capacities (`selection.pack`), ties by loop_id then bundle hash |
| `SealedBeatClient` / `MemorySealedBeat` (`open_sealed(spec)`) | commit, reveal, read a beat's phase and reveals, record the outcome; `SealedBeat.sol` |

## 8d. `loopmarket.selection` — loop selection (P2, 2026-09-18)

| name | one line |
|---|---|
| `Item(key, takes, legs, gain, payload=None)` | a candidate loop: what it takes from each offer (`{offer id: quantity}` — a want whole, a give by the leg's quantity), its leg count and uniform gain, the loop itself as `payload` |
| `pack(items, capacity, *, prior=0, factor=None, exact_up_to=24, budget=200_000) -> Packing` | the set worth most under per-offer capacities (`{offer id: what is left}`): exact branch and bound up to `exact_up_to` items within a node `budget`, greedy beyond, `order_key`'s total order (U6); `Packing(chosen, exact, infeasible)` |
| `weight(item, prior=0, factor=None)` | the objective per loop: Π(1+gain) exactly, or (1−p)^legs·ln(1+gain) in fixed-precision decimal with a failure prior; `factor` the risk-weight hook nobody sets |

## 8e. `loopmarket.escrow` — the crypto escrow (P3 §5a/§5e, 2026-09-19)

| name | one line |
|---|---|
| `EscrowClient(rpc_url, address, *, key=None, client=None)` | `.deposit(offer_id, amount, token=None)`, `.reserve(offer_id, loop_id, wanter, resolver, amount, *, window, claim_seconds, ladder=(), claim_only=False, min_challenge=0, min_ruling=0, deductible=0)`, `.cancel`, `.countersign`, `.cover_of(offer_id, loop_id)` (what a cover covers, what a reservation paid its wanter), `.settle(offer_id, loop_id, to_wanter=None)` (no split: the quiet path after the claim period; a split: this party's signature, the second pays it out), `.assign(offer_id, loop_id, to)` (the wanter's), `.extend_claim(offer_id, loop_id, seconds)` (the giver's), `.hold`, `.resolve(offer_id, loop_id, to_wanter)`, `.collect(token=None)` (a refused payout credited to `owed`), `.notice`, `.withdraw`; reads `.held`, `.free`, `.reservation`, `.owed(to, token=None)`, `.subject(offer_id, loop_id)` (the reservation's key, factbond's subject), `.ladder_at`, `.deposit_of`, `.events(name, from_block=0)` (the contract's `Reserved`, `Settled`, `Deposited`, … log, what `reputation.view` reads); web3 lazy (`chain` extra) |
| `to_wei(qty, decimals=18)` / `floor_wei` | an exact quantity as the asset's smallest unit — refused when not representable (U9) / rounded down (the ladder) |
| `held_units(client)` | offer id → what the escrow holds, in the asset's unit: the `escrow_held` the agent and the clearing take |
| `reservations_for(proposal, *, escrow, resolver, claim_seconds, now, span=None, decimals=18, claim_only=None, min_challenge=0, min_ruling=0)` | pure: one reservation per give whose bond names `escrow` — the share in smallest units, the wanter's key, the give's `arbitrator` or `resolver` (never a party, and one the want's `resolvers` admit), the want's `time(...)` term as the window (through `span`), the claim period per leg (the want's `claim_period`, else `claim_seconds`, never past the give's `claim_max`), the ladder converted at the wanter's acceptance price; `claim_only` for cover (`cover_predicate`) |
| `cover_predicate(ontology, head="insure")` | recognises a give of cover: an `insure(...)` term, whose reservation is never countersigned |
| `abi()` | the compiled `LoopEscrow` from `loopmarket/contracts/LoopEscrow.json` |

`LoopEscrow.sol`: deposit behind the offer id (native coin or ERC-20), the
clearing's key reserves per fill, undisputed cases settle by themselves
(`settle` after the claim period, `countersign`, `cancel` at `ladderAt`),
the resolver fixed at clearing makes two calls (`hold`, `resolve`), the
giver withdraws what no fill holds after a notice period. Since E1
(2026-09-28) a held reservation is released only by a ruling or by both
parties: `hold` opens only the wanter's own claim (naming the giver, within
the reservation, windows at least `minChallenge`/`minRuling`), a retraction
reopens it, and a payout the recipient refuses waits in `owed`. Deployed on
Gnosis at `0xddDB7276F705671673F0885aEf93B99b890Eb5A9` (2026-09-29 night, with assignment and netting; the
earlier `0x7bee…c55F`, `0x299C…69Bf`, `0xA49C…D936` and `0x3936…F3f2` keep their reservations), factbond's
`Assertions` at `0x3c1B4C944398bcc30890d6A6c78f1F9AA2dFe270` as resolver.

## 8f. `loopmarket.gate` — the counterparty gate (R4, 2026-09-29)

### `CounterpartyGate(statements, registers, now, span, offer, held, held_by, capacity, withdrawn, item_claimed, latest, profile)`

Built with `CounterpartyGate.over(book, registers, *, now, span=None, held=None, capacity=None, latest=None, profile=None)`:
the statements presented in `book`'s `cred/`, `registers` (register id →
`Register` at its pinned root), the clock, a `time(...)` span reader, the
escrow's holdings, — R5 — `latest(register id)`, the register at its
feed's newest root, and `profile(key)`, a resolver's chain record
(`arbitrators.chain_profile`). `meets`, every `check_*` and candidate
generator take `gate=`; no gate, no pass (U7).

| member | meaning |
|---|---|
| `.faults(requirer, counterparty, ontology, *, window, taken=None, whole=None) -> [str]` | every failing step of `requirer`'s credential entries against `counterparty`'s statements, one line per entry, the closest statement's steps listed (plan E4); `[]` when every entry is met |
| `.chosen(entry, requirer, counterparty, ontology, *, window, ...) -> Statement | None` | the statement that meets `entry` — what a beat's leg carries on chain (R3b) |
| `.statement_faults(entry, statement, ...)` | the seven steps: 1 category and kind; 2 a path of accreditations to a named trust root, every register on it pinned; 3 not revoked (and a status); 4 every register fresh — its heartbeat within `max_root_age`, its root extending its predecessor on `revoked/`, and no newer root published by the clock that revokes, suspends or drops a revocation (R5); 5 valid through the window; 6 a deposit's free share covering `min_bond`; 7 not suspended |
| `.option_fault(option) -> str` | why an option cannot clear now: its underlying present, a give by the same maker, not withdrawn, valid through the window, in its unit, with the option's quantity free (C2) |
| `.item_fault(give) -> str` | why a give naming `item(h)` cannot clear: its maker holds an active claim on h through another offer (I2) |
| `.window(want) -> (start, end)` | the handover window: the want's first `time(...)` term through `span`, else the clock's instant |
| `.accredited(subject, category, roots, ontology, window) -> [str]` | why `subject` is not accredited for `category` under one of `roots`: a signed or attested statement in its own book, steps 1–5 and 7, the registers read at their newest roots (what an `Accept` by `root:` reads) |

## 8j. `loopmarket.arbitrators` — resolvers accepted by property (2026-09-29)

| name | meaning |
|---|---|
| `accept_faults(accept, key, *, parties=(), requirer=None, ontology=None, gate=None, category="arbitrator", window=None) -> [str]` | why `key` fails an `Accept`: not one of its `keys` and not accredited as `category` under one of its `roots` (`gate.accredited`), less than `min_deposit` on the requirer's scale at stake on a reversed ruling, a reversal within `clean_for` or a record shorter than it, a party to the leg |
| `admits(accept, key, **reads) -> bool` | `accept_faults(...) == []` |
| `resolver_of(want, give, *, default="", gate=None, ontology=None, window=None) -> str | None` | a leg's resolver: the give's `arbitrator`, then the keys either side names in sorted order, the clearing's default last — the first both sides admit (the gate and `escrow.reservations_for` alike) |
| `constrained(want, give) -> bool` | whether either side names resolvers at all |
| `Profile(rulers, deposit=None, asset=None, reversals=None, since=None)` / `chain_profile(address, *, rpc=None, client=None, asset=(("xdai",), "xDAI"), decimals=18, from_block=0)` | a resolver's chain record: the keys that rule (factbond's adjudicator and arbiter, or a plain key itself), the deposit at stake (`min(deposits, depositWei)` with an arbiter, else none), the `Reversed` events; read through `CounterpartyGate(profile=)` |

## 8k. `loopmarket.case` and `loopmarket.reputation` — the default arbitrator (2026-10-01)

The default form: one arbitrator both sides accept, whose ruling is final
(`counterparty-gate.md` §7a). The escrow gives it its two acts (`hold`,
`resolve` on a reservation naming it as resolver); the book carries the
case, sealed like a notice to each recipient beside a salted commitment.

| name | meaning |
|---|---|
| `case.claim_record(claimant, accused, offer, loop, amount, *, sent_at, evidence_ref="", notice_ref="", text="")` | the wanter's claim: `amount` of the reservation in its smallest units, the notice it follows |
| `case.answer_record(author, claim_ref, *, time, evidence_ref="", text="")` | the giver's answer, naming the claim by its reference |
| `case.ruling_record(arbitrator, claim_ref, to_wanter, *, time, reason)` | the arbitrator's reasons; the money moves by the escrow's `resolve` |
| `case.sealed(record, *, sender, recipient, recipient_public_key) -> (side, opening)` / `case.read(side, private_key_hex)` | seal to one recipient (the claim to the arbitrator and the giver, the answer to the arbitrator and the claimant, the ruling to both parties); open |
| `case.key(loop_id, offer_id, kind, to)` / `case.fault(owner, key, rec)` / `KINDS` | `case/<loop>/<offer>/<kind>/<to>`; why a record is not `owner`'s speech (the fold's admission); `("claim", "answer", "ruling")` |
| `reputation.view(reserved, settled, deposited, *, me, trusted=(), posted=None) -> [Arbitrator]` | from the escrow's `Reserved`, `Settled` and `Deposited` events (`EscrowClient.events(name, from_block=0)`): every arbitrator named on a reservation where I or a trusted maker was a party — its legs, its rulings, and who of us lost a ruling under it and chose it again on an offer *posted* after the loss (`posted(maker, offer, loop)`); sorted by key (U6). Never a score the protocol reads |
| `reputation.Arbitrator(key, legs, rulings, chosen_again)` | one row of the view |

## 8g. `loopmarket.register` — registers (R3a, R5, 2026-09-29)

### `Register(store)`

A register's own recordstore keyspace — `status/<id>`, `revoked/<id>`
(monotone: a revocation stands forever), `suspended/<id>`,
`accredit/<issuer>/<category>`, `heartbeat`, `chain` — announced under the
`register` role and never folded into the offer book.

| member | meaning |
|---|---|
| `.issue(id, at)` / `.suspend(id, at)` / `.reinstate(id, at)` / `.revoke(id, at)` | a statement's status; a revoked one stays revoked (`ValueError`) |
| `.accredit(issuer, category, *, by, since, until, scheme="")` / `.accreditation(issuer, category)` / `.accreditations(issuer)` | who may issue what, until when, by which check scheme |
| `.heartbeat(at)` / `.as_of` | the root's publication time: what `max_root_age` bounds |
| `.commit() -> root` | commits what is staged, writing `chain` → {prev, seq}: every root names the one it supersedes (R5) |
| `.predecessor` / `.seq` / `.root` | the superseded root, this root's number in the sequence, the committed root |
| `.extends(base) -> bool | None` / `.extends_predecessor()` | recordstore's extension check on `MONOTONE` (`revoked/`): does this root keep every revocation `base` held; None when it cannot be checked, which the gate reads as failing |
| `.extension_proof() -> dict | None` | the self-contained proof (recordstore's `verify_extension` checks it with no store) |
| `.status(id)` / `.revoked(id)` / `.suspended(id)` / `.prove(key)` | reads; `prove` is recordstore's inclusion-or-absence proof — "not revoked" as a proof |

| function | meaning |
|---|---|
| `named_registers(offers) -> set[str]` | the trust roots the offers' requirements name: what a proposal must pin |
| `newest_reader(pointer_for, blobs)` | the gate's `latest` over registers' feed tips: `pointer_for(register id)` → its feed pointer |

## 8h. `loopmarket.items` — item identity (I1–I2, 2026-09-29)

| function | meaning |
|---|---|
| `vin_id(vin)`, `land_register_id(country, number)`, `serial_id(maker, serial)`, `natural_id(scheme, identifier)` | h from a natural identifier: the same identifier however spelled, the same h (`ValueError` on a malformed VIN) |
| `tagged_id(fingerprint, tagger, binding_evidence="")` | h from a tagger's record: an attested identity |
| `term(h, head="item") -> "item(<h>)"` | the concept naming the item |
| `ids(concepts)` / `well_formed(concepts)` | the item ids a concepts tuple names; whether every item term is a whole 64-hex id (the matching gates refuse the rest) |

`Ontology.declare_item_heads()` puts `item` on ontodag's prefix kind. The
per-item rule: one open claim per maker and item (`item/<h>/<maker>/<loop>`,
written with the fill or an option's hold); across makers nothing is
refused.

## 8i. `loopmarket.witness` and `loopmarket.notice` — the door and the notice (R6–R7, 2026-09-29)

| name | meaning |
|---|---|
| `witness.respond(challenge, bound_id, private_key_hex)` / `witness.signer(challenge, bound_id, response)` / `DoorCheck()` | the `possession` witness: a fresh challenge signed with the bound id; `DoorCheck` spends a challenge on its first response |
| `witness.photo_commitment(photo, salt)` / `photo_opens(commitment, photo, salt)` | the `photo-match` witness: the attester's salted commitment opened at the door |
| `witness.accepted_types(names)` / `DOOR_LEVELS` | a door level as a cumulative category; the CLI writes the types a level stands for into the record (the chain compares exact names), and `accepted_types` still reads a level's name |
| `witness.countersign_ready(give, *, possession=False, photo_confirmed=False) -> str` | why a countersign is not yet due, or `""` |
| `notice.notice_record(...)` / `cure_record(...)` / `sealed(record, *, sender, recipient, recipient_public_key)` / `read(side, private_key_hex)` / `opens(side, opening)` | a notice before a claim and its cure, factbond's shape, sealed to the other party beside a salted commitment anyone checks once opened |
| `notice.lapsed(gives, statements_of, registers)` / `gives_of(loop_record, book)` | the relied-on statements revoked or suspended since clearing — the watch's re-check |

## 9. `loopmarket.solver.agent` — the baseline species

### `SolverAgent(registry, ontology, clearing, solver_id="solver-0", min_surplus=0.005, max_loops_per_step=10, chain_fills=None, escrow_held=None, max_legs=5, cycle_limit=2000, exact_up_to=24, pack_budget=200_000, failure_prior=0, registers={}, span=None, register_latest=None, resolver_profile=None)`

| member | meaning |
|---|---|
| `.find_loops(*, now=None) -> (book_root, [Loop \| Circulation])` | snapshot → offers (the chain's fills and the escrow's holdings subtracted) → matches → every simple cycle (`enumerate_cycles`) plus the composed legs → `selection.pack` |
| `.step(*, now=None) -> [Receipt]` | find, then propose each loop (pinning the snapshot root and `ontology.root`); appends to `.receipts` |
| `.run(*, interval_s=5.0, max_steps=None)` | poll loop for live operation |

`registers` (register id → `Register`), `span`, `register_latest` and
`resolver_profile` build the `CounterpartyGate` over each snapshot, and
every register a requirement names is pinned in the proposal.
Deterministic and exact by design — the species smarter solvers must
beat, and the sealed beat's reserve bid.

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
| `recover_public_key(offer_id, sig_hex) -> bytes` | the signer's public key — what handoffs, notices and cases are sealed to |
| `sign_contact_card(private_key_hex) -> (address, sig)` / `contact_card_public_key(address, sig) -> bytes` | a contact card: a signature over sha256(`CONTACT_CARD_DOMAIN` + address), `CONTACT_CARD_DOMAIN = b"loopmarket contact card\n"` — the public key of a key with no signed offer |

Signatures live *beside* offers (`sig/` keys), never inside
`canonical_bytes()` — ids stay stable, roots stay pure.

---

## 10b. `loopmarket.handoff` — sealed handoffs (the address reaches the courier)

Settlement text — the door, the gate code — sealed to the leg counterparty's
public key and written into the place-owner's own book after clearing
(`docs/plans/P1-spacetime-terms.md` §4). ECIES over the makers' secp256k1
keys: ephemeral key, ECDH, HKDF-SHA256, AES-256-GCM. Needs the `sig` extra
(coincurve, cryptography); imports lazily.

| function | meaning |
|---|---|
| `seal(text, recipient_public_key) -> dict` | `{"v": 1, "epk", "nonce", "ct"}` (hex); a fresh ephemeral key each call |
| `open_(record, private_key_hex) -> str` | raises on a wrong key or a tampered record |
| `public_key_of(private_key_hex) -> bytes` | compressed SEC1 |
| `sigs.recover_public_key(offer_id, sig_hex) -> bytes` | the signer's public key from a detached signature — no key registry |
| `sigs.sign_contact_card(private_key_hex) -> (address, sig)` / `contact_card_public_key(address, sig) -> bytes` | a contact card: a signature over a fixed message naming the address, so anyone may seal to a key with no signed offer (stored as `key/<address>`, admitted only in its owner's book) |

## 11. `loopmarket.federation` — the aggregator

Constants: `MAKER = "maker"`, `CLEARING = "clearing"` (book roles; a
`register` book is announced but never folded).

### `Manifest(aggregator, book_root, provenance_root, announcement_root)` — frozen
What an aggregator publishes. `book_root` is the pure fold;
`provenance_root` its attributed decisions; `announcement_root` the
input-set commitment (completeness handle, threat T14). No derived root
since 2026-09-12 (the `idx/` index it named is gone).

### `Aggregator(store_factory, *, aggregator_id="agg-0")`
`store_factory() -> store` must return fresh writable stores over the
**shared blob space** (all books one blob space — Swarm's, or one
`MemoryBytesStore`).

| member | meaning |
|---|---|
| `.announce(owner, store, *, role=MAKER)` | register "owner's book is store"; one per owner; re-announce replaces; `ValueError` on unknown role |
| `.retract(owner)` | admission-by-reference's teeth: stop folding an owner |
| `.fold() -> Manifest` | sanitize every announced book, merge under `or_set_resolver`, U11-check, commit all three roots. Deterministic in the announced (owner, root) set: same inputs ⇒ byte-identical manifest, any order |

Admission rules per record (fail closed; every rejection is an
attributed `reject/` record):

| key class | maker book | clearing book |
|---|---|---|
| `offer/` | content address re-derived; readable version; `maker == owner` **or** valid detached `sig/` in the same book | silently skipped (contains its base fold; not its speech) |
| `withdraw/` | only for an offer this book holds with `maker == owner` | silently skipped |
| `sig/` | staged when it verifies; foreign-offer sigs stage with their offer | silently skipped |
| `fill/`, `loop/`, `option/`, `exercise/`, `item/` | **rejected** ("clearing keys in a maker book") | staged |
| `handoff/` | only beside an offer the owner made, `from` the owner | silently skipped |
| `cred/` | only in its subject's own book, under its own content address (R2) | silently skipped |
| `notice/`, `cure/`, `case/` | only as the writer's sealed speech (`from` the owner, a readable sealed record and commitment) | silently skipped |
| `key/` | only the owner's own contact card, recovering to the owner | silently skipped |
| anything else | rejected ("unknown keyspace") | silently skipped |

### `Omission(owner, key, announced_root, proof)` — frozen
One record an announced maker book holds at `announced_root` that is
absent from `book_root` and has no `reject/` in `provenance_root`.
`proof` is recordstore's absence proof for `key` against `book_root`
(`verify_proof(proof, book_root) is ABSENT`, no store access); `None`
when `book_root` is empty.

### `audit_manifest(manifest, blobs, *, store_type=RecordStore, expected=()) -> list[Omission]`
The T14 cross-audit from the manifest alone: (announced set) − (speech
under `book_root`) over `offer/` and `withdraw/` keys of every
`MAKER`-role announcement, sorted by owner then key. With
`expected=channel.announced()` (§11b) a maker book announced on the
channel and absent from the manifest's announcement set is an omitted
book too (`announce/<owner>`, proven absent under `announcement_root`).
Empty for an honest fold. Not audited: `sig/` (dropped-without-rejection
by design) and clearing books (U11 covers them).

## 11b. `loopmarket.announce` — the announcement channel (2026-09-14)

How a book becomes discoverable: `Announcement(owner, book, role="maker",
seq=0)` — the owner's book spec and role (`maker`, `clearing`,
`register`), latest per owner, retractions applied. Every backend has
`.announced() -> [Announcement]` (sorted by owner), `.announce(book,
role="maker", *, owner=None)` and `.retract(*, owner=None)`.

| name | meaning |
|---|---|
| `open_announcements(spec, *, key=None)` | `chain:RPC_URL@CONTRACT` (`ChainAnnouncements`: the `LoopBookRegistry` event log, `msg.sender` the owner — the announcement authenticates the book, U8; web3 lazy, `chain` extra), `file:PATH`, `memory:` (`MemoryAnnouncements`); several comma-separated are one channel (`UnionAnnouncements`, the later member winning) |

`LoopBookRegistry` is deployed on Gnosis at
`0xD4379E494a488411D964BebDb210C0bf628d97af`.

---

## 12. The keyspace

One book = one recordstore keyspace = one root per version:

```
offer/<offer_id>        the immutable offer record (v1–v7)
sig/<offer_id>          detached maker signature, hex (never in identity)
withdraw/<offer_id>     1 — monotone tombstone: the offer is closed
fill/<offer_id>         {"loop": <loop_id>} — pure function of the decision (a give taken in part: fill/<offer_id>/<loop_id>)
loop/<loop_id>          the cleared proposal record (v2 since 2026-09-29 with its register_roots)
handoff/<loop_id>/<offer_id>  sealed settlement text, the place-owner's own filled offer (maker books; folded only for the owner)
cred/<subject>/<statement_id>  {"statement", "presentation"} — a statement about a key, in its subject's own book (R2)
notice/<loop_id>/<offer_id>    a sealed notice to the giver, the claimant's own speech (R6)
cure/<loop_id>/<offer_id>      the giver's sealed cure (R6)
option/<offer_id>/<loop_id>    {"option", "holder", "until", "qty"} — a hold written with an option's fill (C2; clearing books)
exercise/<offer_id>/<option_loop>/<loop_id>  {"qty"} — what an exercise took of a hold (clearing books)
item/<h>/<maker>/<loop_id>     {"offer", "until"} — a maker's claim on an item (I2; clearing books)
key/<address>                  a contact card: the signature its public key is recovered from (the owner's own book)
case/<loop_id>/<offer_id>/<kind>/<to>  a sealed claim, answer or ruling to one recipient (kind: claim | answer | ruling; the writer's own book)
auction/<beat>                 {"beat", "book_root", "revealed_set", "winners"} — a sealed beat's recorded outcome (the clearing's own book; not folded)
origin/<offer_id>       {"owner", "root"}        (provenance store)
reject/<owner>/<key>    {"owner", "reason"}      (provenance store)
announce/<owner>        {"role", "root"}         (announcement store)
```

Maker books write `offer/`, `sig/`, `withdraw/` (and the sidecars
`handoff/`, `cred/`, `notice/`, `cure/`, `key/`, `case/`); clearing books
add `fill/`, `loop/`, `option/`, `exercise/` and `item/`; a register is
its own store (`status/`, `revoked/`, `suspended/`, `accredit/`,
`title/<h>` — a land or vehicle register's holder of an item, I4 —
`heartbeat`, `chain`, §8g), never folded; there is no index in any book (the `idx/{c,t,g}`
prefixes retired 2026-09-12, and the manifest's `index_root` with them);
`origin/`, `reject/`, `announce/` only in an aggregator's provenance and
announcement stores.

## 13. Record formats

**Offer, v3** (2026-09-12, `docs/plans/P1-spacetime-terms.md`): no
`service`/`where` — where and when the thing changes hands are terms in
`concepts`: a bare geo or time term (`geo(u24)`, a place node, a region, a
window `time(a..b)`, a named time) and, for a route or a transport, the
two ends `from`/`to`, `depart`/`arrive`. Handover coordinates match when
one side contains the other (the seller delivering anywhere in the city
serves the want at the door; the buyer collecting anywhere is served by the
shop); a want that names none does not care. `valid` may have a `null` end
(stands until withdrawn). A v3 record carrying `service` or `where` is
refused on read.
v2 and v3 offers never match each other (`check_match`):

```json
{"v": 3, "maker": "amara",
 "gives": {"type": "thing",
           "concepts": ["geo(u24)", "piano-lesson",
                        "time(2026-10-01T00:00:00Z..2026-12-31T23:59:59Z)"],
           "qty": 1.0, "unit": "course", "divisible": false},
 "wants": {"type": "tokens", "issuer": "amara", "amount": 100},
 "valid": [1699999999, null],
 "ontology_root": "…64 hex…", "registry_version": "4.1",
 "contract_version": "0.1",
 "bond": 0.0, "oracle": "countersign", "arbitrator": "", "nonce": 1}
```

**Offer, v2** (read and matched among v2 offers forever — U2; v1 lacks
`registry_version`/`contract_version` and says `"v": 1`):

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

**Offer, v4** (2026-09-14): every number a `rat` string; `step` and `min`
in place of `divisible`; a want may be `{"type": "parts", "parts": [...]}`:

```json
{"v": 4, "maker": "buyer",
 "gives": {"type": "tokens", "issuer": "buyer", "amount": "60"},
 "wants": {"type": "parts", "parts": [
     {"concepts": ["ticket"], "qty": "2", "unit": "unit", "step": "2", "min": "0"},
     {"concepts": ["transport"], "qty": "1", "unit": "unit", "step": "1", "min": "0"}]},
 "valid": [1699999999, null],
 "ontology_root": "…", "registry_version": "4.2", "contract_version": "0.1",
 "bond": 0.0, "oracle": "countersign", "arbitrator": "", "nonce": 1}
```

**Offers, v5–v7** add `requires`, a `Bond` deposit (v5), the counterparty,
legs, resolver and claim-period requirements, `claim_max` and an option's
`underlying`/`exercise` (v6), and a deposit's `deductible` (v7) — §1's
`Offer` entry; each re-encodes in its own version, so earlier ids never
move (`tests/test_v5_record.py`, `tests/test_v6_record.py`).

**Loop, record version 1** (`LoopProposal.to_record()`, 2026-09-14; version
2 since 2026-09-29 when it pins `register_roots`):
legs in sorted `key` order, each naming its want, its gives and the
quantity `taken` from each; a simple leg's exact `rate`; the node
`potentials` (the clearing prices, public while offers are plaintext — P4
§5 item 4; outside `loop_id`, which hashes the legs alone); all numbers
`rat` strings. Readers of the 2026-08 shape find `give` (the first give).

```json
{"v": 1, "loop_id": "…", "solver": "loop-cli", "found_at": 1700000000,
 "book_root": "…", "ontology_root": "…", "surplus": "611/5000",
 "nodes": ["amara", "bruno", "chen"],
 "legs": [{"give": "<id>", "gives": ["<id>"], "taken": ["1"], "want": "<id>", "rate": "104/50"}, …],
 "potentials": {"amara": "1", "bruno": "26/25", "chen": "…"}}
```

**Fill** (`LoopProposal.fills()`): a want's, at `fill/<offer>`,
`{"loop": "<loop_id>", "gives": [{"offer": "<id>", "qty": "<taken>"}]}`; a
give taken whole, at `fill/<offer>`, `{"loop": "<loop_id>", "qty": "<taken>"}`;
a divisible give taken in part, at `fill/<offer>/<loop_id>`, the same
record — several loops each take their share, the remainder stays open
(`OfferRegistry.available`), and the fills of one give may not sum past
its quantity (U11 raises "oversold"). Nothing else, ever: no wall clock
(fill determinism), no prices (P4 §5 item 4). The 2026-08 fill was
`{"loop"}` alone and still reads.

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
| **U9** | exact rationals in everything clearing re-verifies: quantities, amounts, rates, potentials and surplus are `Fraction`s, records spell them `n/d`, no epsilon in a gate (the solver's `-log` search may float) |
| **U11** | no partially-filled loop survives a merge unnoticed: `verify_loop_atomicity` on every reconciled commit and every fold, raising rather than repairing — every loop holds a fill for each leg, every fill (and every `option/`, `exercise/` and `item/` record) names a present loop, and the partial fills of one give never sum past its quantity |

The other planned invariants of **U8–U14** (offer authenticity,
load-bearing pins, cost-borne statistics, no protocol emissions,
numeraire-free scoring) are specified in `docs/plans/` and enter the
binding set as their enforcing code lands — U8's fold rules and U10's
matching half are already running (§11, §5).

## 15. Environment

| variable | used by | meaning |
|---|---|---|
| `BEE_API` | live tests, `demo_federation.py` | Bee node API, e.g. `http://localhost:1633` (a light node suffices) |
| `BEE_BATCH` | " | a purchased postage batch id (never auto-buys; prefer mutable for feed-heavy work) |
| `BEE_SIGNER` | gated tests, `loop` | throwaway 32-byte hex key for the shared-catalogue/book feeds; at the CLI, the maker's key |
| `LOOP_CORE` | `demo_federation.py` | `0` skips adopting ontodag's `core` pack (needs ontodag>=0.19) and uses the eleven-category toy catalogue |
| `LOOP_HOME` | `loop` | the CLI's home (`~/.loopmarket`): `config`, the default book `book/` |
| `LOOP_<SETTING>` — `LOOP_BOOK`, `LOOP_CATALOGUE`, `LOOP_PEERS`, `LOOP_MAKER`, `LOOP_TERMS`, `LOOP_VALID`, `LOOP_NOW`, `LOOP_CONFIRM`, `LOOP_RENDER`, `LOOP_LIMIT`, `LOOP_REGISTRY`, `LOOP_BEAT`, `LOOP_ESCROW`, … | `loop` | the environment layer of the settings table (§17): every setting `KEY` reads `LOOP_KEY`; `BEE_*` is shared with odag |
| `LOOP_CHAIN_RPC`, `LOOP_CHAIN_KEY` | `scripts/gate_*.py`, `scripts/deploy_*.py` | the chain's RPC and the deploying or clearing key for the live gates (never printed) |
| `ONTODAG_HOME`, `ONTODAG_STORE` | `loop`, via odag | where the inherited odag config and active store (the default catalogue and the personal names layer) live |

Live test suites: `tests/test_swarm_book.py` (the P0 triangle on a live
book), `tests/test_swarm_federation.py` (per-maker feeds, two
aggregators, clearing feed, follower), `tests/test_swarm_register.py` (a
register on a Swarm feed read at its tip, a stale pin refused after a
revocation). All skip without the variables; all use timestamped topics
so reruns inherit nothing.

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
table: `-f SPEC` (or `--book SPEC`), `--catalogue SPEC`, `--peer SPECS`, `--maker NAME`,
`--terms 'TERM ...'`, `--valid DURATION`, `--now TIME`,
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
| bare number **first**, `[MIN..]QTY[UNIT][:STEP]` (`10kg`, `3`, `1000:1`, `50kg..100kg:25`) | the quantity: a unit suffix ⇒ `qty`, `unit`, continuous (step 0); a bare count ⇒ indivisible, unit `unit`; `:STEP` the granularity a fill must be a multiple of; `MIN..` before it the give-side floor, the least one fill may take; omitted ⇒ the schema default. A step or floor on a want refuses (the give's step and floor decide the fill) |
| bare number **last** (`100`, `12.5`) | the price, on the maker's scale; omitted ⇒ the maker's last unit price for the same side and bare categories, × quantity, marked in the block; no earlier offer ⇒ error |
| `+` between parts (`want` only) | a **composed want**: each part reads as a want line without its price (a bare number first is that part's quantity, no `valid(...)`), the last bare number of the line prices the whole; refused in a `give` |

Numbers are exact (U9): a decimal as typed is the rational it spells
(`99.99` is 9999/100), and the v4+ record stores every number as a
reduced `n/d` string, so the CLI and the API encode the same offer byte
for byte.

**The one interpreted head** is `valid(DURATION | A..B | A..)` → the
offer's `valid` window (`A..` stands until withdrawn). A startup check
refuses a catalogue that declares `valid` as a dimension head. Everything
else is a catalogue term. Where and when the offer holds are **bare**
terms (2026-09-13: no `where`/`when` head): a place name, a cell, a
window — `give vegetable-box shop 5`, `want vegetable-box door 6`. Omit
them on a want and it does not care; omit them on a give and it says
nothing about where or when. A route's ends keep their heads,
`from(...)`/`to(...)`. The `terms` setting adds default terms to every
line that does not already state that coordinate (`set terms home`).

**Terms** pass into the description, elaborated by *kind*, never by head
(the CLI names no head). A *catalogue* name stands as spelled (`shop`,
`ljubljana`, `my_home_4th`, `autumn`): ontodag orders it. A *private*
name — one only the personal store holds, which the pinned root cannot
carry — publishes as the dimension term it hangs under (`home` →
`geo(u24)`) and is printed as a note; a private name with no such term is
refused, never read as a literal. A bare `LAT,LON,R` becomes the finest
cell containing that radius around the point (the spelling `place` takes;
a place near a cell edge names the coarser cell) under the prefix head the
catalogue marks as a handover coordinate; a bare relative time
(`today..+7d`) is elaborated to fixed UTC under the calendar one. A term of a *linear* or
*count* head (`mass(...)`, `count(...)`) is accepted by the parser and
**refused at publish** with the coupling plan named: quantities are
fields today. A floor alone or a ceiling alone in quantity position
(`10kg..`, `..11kg`) parses and refuses, naming the spelling that says how
much.

**Time** (input vocabulary, stored absolute UTC): `now`, `today`,
`tomorrow`, `+90d`/`-2h` (units `s m h d w`), any ontodag time literal
(`2026-10`, `2026-10-01`, `2026-10-01T10:00:00Z`), and ranges `A..B`,
`..B` (from now), `A..` (open-ended: for `valid`, until withdrawn). A name
whose node hangs under a `time(...)` term is a window too (`evenings`).
Durations: `30d`, `2h`, `90m`, or ontodag's (`155min`). Radii: `5km`,
`500m`, bare metres.

### Commands

| role | command | does |
|---|---|---|
| maker | `give [QTY] CAT\|TERM... [PRICE]` | resolve, show the block, confirm, publish, commit, print the id |
| | `want [QTY] CAT\|TERM... [PRICE]` | the other side |
| | `withdraw ID` | tombstone one of my open offers (id or unique prefix); filled refuses |
| | `option ID [--until T] [--premium X] [--for WANT]` | write an option on my open give: a give of `option(<its concepts>)` naming it as `underlying`, exercisable from now until T (a duration or an instant), priced at the premium; left out, the window is `option_window` of the lead and the premium `option_premium`'s (suggested from the book's demand by default), both shown with their reasons; `--for WANT` answers a want of an option on a thing like mine (checked to meet it); v6, its hold recorded on chain since the 2026-09-29 clearing contracts |
| | `exercise OPTION... PRICE` | as the options' holder, want their offers (the quantities held) at PRICE while the windows are open; anyone else is refused; several options: one composed want of their offers, all or nothing, open until the first window closes (2026-09-29) |
| | `holds` | every hold in the fold: offer, option, holder, until, what is left, active (named `options` until 2026-09-29) |
| | `mine` | my offers, all states |
| | `place NAME LAT,LON,RADIUS [ADDRESS...]` | a place node under the cell containing that radius, written to odag's active store (temporary bridge; adopts the prelude there if absent); the address is settlement text on the node, shown in the block of an offer naming the place and sealed to the cleared counterparty |
| | `handoff ID TEXT...` | what my offer's cleared counterparty may read (replaces the place text for this offer); kept in `$LOOP_HOME/handoffs`, sealed by `watch` once filled |
| | `watch [--once]` | poll the fold every `interval`: report my fills, seal pending handoffs to the counterparty's key (from the signature on their offer), open incoming ones with `bee_signer`; `--once` is one pass, exit 1 when nothing new |
| | `handoffs` | every handoff sealed to me, opened (exit 1: none) |
| | `want PART + PART... PRICE` | a composed want on one line: every part resolved, one price for the lot, published as one v4 offer — all the parts or nothing |
| | `draft [NAME] want\|give ...` | stage one resolved offer (price optional) or part in `$LOOP_HOME/drafts` (a file, never the book; no id); re-drafting a name replaces it; numbers name the unnamed |
| | `draft [NAME] A + B ...` | compose drafts (want side only, flattening, a priced part refused); a single name copies |
| | `drafts` | every draft in canonical spelling — the line `offer` will speak — with the typed spelling and notes beneath (exit 1: none) |
| | `offer NAME [PRICE]` | a draft becomes an offer: its own price, the given one, or the price memory; block, question, publish, draft removed; a composed draft publishes as one v4 offer |
| | `discard [NAME\|N ...]` | drop drafts; alone, empty the list |
| reader | `offers [CATEGORY...]` | open offers in the fold, filtered through `satisfies` |
| | `show ID` | one offer as the approval block, plus `state` |
| | `matches` | every feasible handoff in the fold (exit 1: none) |
| | `status` | book and catalogue specs and roots, counts, settings in force |
| solver | `loops` | profitable loops on a pinned snapshot; prints, never clears (exit 1: none) |
| clearing | `clearing` | `MockClearing` over the fold; with `peers`, my book first absorbs the fold; fills committed to my book (exit 1: nothing cleared). `clear` is an alias |
| plumbing | `set [KEY [VALUE]]` | list / show / durably change a setting; unknown keys are errors; values validated at set time |
| | `export` | every offer of my book as JSON lines of canonical records |
| | `import [FILE]` | publish records from FILE or stdin; ids survive |
| | `help`, `--version` | |
| chain | `propose` | clear locally as `clearing` does and post each loop as one beat on `beat` (the contract's verdict asked first; the bee_signer key pays the bond) |
| | `beats [--open]` | every beat on the contract: submitter, root, fills, state |
| | `challenge BEAT [LEG] [--check] [--book SPEC]` | find the record behind a beat, re-derive every leg off chain and by the verifier for free, send only what convicts (exit 2: no record anywhere) |
| | `finalize BEAT` | after the window: fills recorded on chain; with `escrow` set, each bonded give's share reserved per fill |
| | `commit` / `reveal [BEAT]` / `outcome [BEAT] [--check]` / `sealed [BEAT]` | the sealed beat on `auction`: seal my loops, open them, derive a closed beat's winners and post them, read a beat |
| | `deposit [ID] [--check]` | fund my gives' declared bonds on the `escrow` contract in the gas token |
| | `reservations [--all]` | the escrow's reservations behind my legs (bonded gives, my filled wants' gives): amount, wanter, resolver, claim period, state |
| | `countersign OFFER` / `cancel OFFER` | the wanter's receipt (the reservation returns; never on cover) / the giver's cancellation (the ladder's amount at this lead to the wanter) |
| | `assign OFFER KEY` | the wanter assigns the claim on the reservation to KEY (not while a claim is open) |
| | `settle OFFER [SPLIT]` | quiet after the claim period; with SPLIT — `all`, `N%`, `NxDAI` or an amount on my scale at my `default_asset` price — my signature of a split, the second settling it |
| | `extend-claim OFFER DURATION` | the giver lengthens the claim period (tail cover) |
| | `collect [--check]` | payouts my address refused, waiting in the escrow's `owed` |
| | `cred [SUBJECT]` / `cred present FILE [--presentation FILE]` | the statements presented about SUBJECT (me) with their state under the registers I read / present a statement about me in my book (R2) |
| | `register issue SUBJECT CATEGORY --until T --evidence HASH --paid-by subject\|relier [--kind K] [--path ROOT]... [--deposit OFFER@ESCROW] [--scheme HASH]` | run a register in this session's book (`-f SPEC`, announced with `announce --role register`): issue a statement, its record printed for the subject; `revoke`/`suspend`/`reinstate STATEMENT`, `accredit ISSUER CATEGORY --until T`, `transfer ITEM KEY` (a title register's holder, I4), `heartbeat`, `status` — each write heartbeats and commits a root naming its predecessor |
| | `contact-card` | write my contact card into my book, so anyone may seal to me (a claim to me as arbitrator, a notice when I have no signed offer) |
| | `claim OFFER AMOUNT [--evidence R] [--text T]` | as a reservation's wanter, when its resolver is one named arbitrator (a key): the claim — `all`, `N%`, `NxDAI` or on my scale — sealed to the arbitrator and the giver |
| | `answer OFFER [--evidence R] [--text T]` | as the giver: answer the claim, sealed to the arbitrator and the claimant |
| | `hold OFFER` / `rule OFFER AMOUNT --reason TEXT` | as the arbitrator: the escrow's `hold` (the timeout stops), and the final ruling — the escrow pays it less any deductible, the reasons sealed to both parties |
| | `cases` | the claims, answers and rulings involving me |
| | `arbitrators [--trust KEYS]` | a personal view, never a gate: the arbitrators named on escrow reservations where I or a maker I trust was a party, their rulings, who among us lost under one and chose it again with an offer posted after the loss, and the accreditation each presents |
| | `notice OFFER --cure DURATION [--fact STATEMENT]` | as the wanter of a cleared leg: factbond's `Notice` to the giver, sealed to its key beside a commitment, in my book; the opening kept locally for a claim |
| | `cure OFFER [--evidence REF]` | as the giver: answer a notice on my give, sealed back to the claimant |
| discovery | `announce [--role maker\|clearing\|register]` / `announced` / `fold` | say "my book is here" on `registry` (role `maker` by default; a clearing book says `clearing`, a register `register`); the standing set; fold the announced books myself |

The escrow verbs name a reservation by its offer's id prefix and, when the
book knows more than one loop that took from it, `--loop LOOP` (a prefix,
or the whole id of a loop the book does not know); they act under the
`bee_signer` key, and the contract decides who may.

### The approval block

`give`/`want` print the fully resolved offer through the same renderer
`show` uses — byte-identical for the same offer (gate G4): side and
concepts, maker, quantity with its *reading* ("up to 10 kg, divisible";
"3, indivisible"; "up to 15 seat, in steps of 1 seat, at least 8 seat"),
price and unit price on the maker's scale, the validity window in UTC
and local time ("until withdrawn" when open), the pins, bond / oracle /
arbitrator, nonce, `offer_id`. Below the block, `note` lines: every
name→value and spelling→term substitution, the defaults added from
`terms`, a reused price with its source offer and age, and the handoff
texts that will be sealed to the counterparty. The nonce is `now` in milliseconds plus the
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
| `terms` | `LOOP_TERMS` | none | terms added to every offer whose line does not already state that coordinate, e.g. `home ..+90d`; unset ⇒ anywhere, any time |
| `valid` | `LOOP_VALID` | `30d` | how long offers stand (`A..` until withdrawn) |
| `interval` | `LOOP_INTERVAL` | `30s` | how often `watch` polls |
| `now` | `LOOP_NOW` | wall clock | the clock: unix seconds or an ISO-8601 literal |
| `confirm` | `LOOP_CONFIRM` | `auto` | `auto` / `on` / `off` |
| `render`, `limit` | `LOOP_RENDER`, `LOOP_LIMIT` | `auto` | as odag: tables and 50 rows at a terminal, raw and unlimited in a pipe |
| `bee_api`, `bee_batch`, `bee_signer` | `BEE_*` | inherited from odag | the Bee node; `bee_signer` is secret |
| `registry` | `LOOP_REGISTRY` | none | the announcement channel: `chain:RPC@CONTRACT` (LoopBookRegistry), `file:PATH`, `memory:`; comma-separated are one channel |
| `beat` | `LOOP_BEAT` | none | the clearing contract `chain:RPC@CONTRACT` (BeatClearing): `propose`, `beats`, `challenge`, `finalize` |
| `auction` | `LOOP_AUCTION` | none | the sealed-proposal beat `chain:RPC@CONTRACT` (SealedBeat) or `memory:`: `commit`, `reveal`, `outcome`, `sealed` |
| `escrow` | `LOOP_ESCROW` | none | the escrow contract `chain:RPC@CONTRACT` (LoopEscrow); the record names the address; `deposit` funds, `finalize` reserves |
| `resolver` | `LOOP_RESOLVER` | none | who resolves a contested claim on the deposits `finalize` reserves (factbond's `Assertions`; a give's `arbitrator` wins; empty: my key) |
| `escrow_claim` | `LOOP_ESCROW_CLAIM` | `7d` | how long after a leg's window a claim on its deposit may be opened, when the want asks none; never beyond the give's `claim_max` |
| `claim_min_challenge`, `claim_min_ruling` | `LOOP_CLAIM_MIN_*` | none | the least dispute and ruling windows a claim on the reservations `finalize` makes must name (the escrow refuses shorter at `hold`) |
| `arbitrator` | `LOOP_ARBITRATOR` | none | the resolver my gives name for claims on their deposit (never my own key); a want requiring resolvers matches only a give naming one it accepts |
| `claim_max` | `LOOP_CLAIM_MAX` | none | the longest claim period my gives' deposits carry (v6) |
| `deductible` | `LOOP_DEDUCTIBLE` | none | what a ruled claim on my deposit leaves with me, on my scale like `bond`, held in the deposit's asset at the price the deposit states; for the give's whole quantity (v7) |
| `options` | `LOOP_OPTIONS` | `off` | `on`: every plain give I publish also writes its option, both in one approval block |
| `option_window` | `LOOP_OPTION_WINDOW` | `1/4` | an option's window: a fraction in (0, 1) of the lead to the offer's handover time (its validity's end without one), or a duration; it closes before the handover |
| `option_premium` | `LOOP_OPTION_PREMIUM` | `suggest` | an option's premium on my scale: `suggest` (price × ½ × the chance a buyer comes during the hold and none after it, the rate read from the book's wants for the thing over 30 days; with none, price × window/lead × ½, flagged as a guess), `N%` of the price, or an amount; never below 1% of the price |
| `require_claim`, `require_resolvers` | `LOOP_REQUIRE_*` | none | the claim period I ask of a giver's deposit; the resolvers I accept on my wants and gives — keys, `root:ID`, `min:AMOUNT` (on my scale), `clean:DURATION` (v6, §7a) |
| `trust` | `LOOP_TRUST` | none | makers whose choices of arbitrators `arbitrators` counts beside mine (a personal view) |
| `require_transfer` | `LOOP_REQUIRE_TRANSFER` | none | title registers whose transfer of the item my wants accept as the witness: gives declaring `oracle registry-transfer(ID)` for one of them (I4) |
| `require_credentials` | `LOOP_REQUIRE_CREDENTIALS` | none | what my wants require the giver to present: `;`-separated `CATEGORY KIND[,KIND...] [root:ID]... [age:DURATION] [min:AMOUNT]` (v6, R4) |
| `registers` | `LOOP_REGISTERS` | none | registers I read beyond those announced under the `register` role: `ID=SPEC` pairs; read at their heads, pinned in my proposals, consulted for credentials, `root:` resolvers and `watch`'s lapsed statements |
| `bond` | `LOOP_BOND` | none | my deposit on every give: an amount on my scale (deposited as `default_asset` at my price) or `QTY[UNIT] CATEGORY... VALUE` (v5) |
| `default_asset` | `LOOP_DEFAULT_ASSET` | none | the asset a bare `bond` deposits and a bare `require_point` accepts, with MY price per unit on my scale (`xdai xDAI 1.2`); no default price — unset, a bare amount is refused |
| `require_point`, `require_cancel`, `ladder` | `LOOP_REQUIRE_*`, `LOOP_LADDER` | none, none, `linear` | my neutral point on a no-show and on a far cancellation, on my scale; the ladder's shape over the lead at posting (`linear`, `late`, `early`, `flat`) |
| `require_accepts`, `require_escrows` | `LOOP_REQUIRE_*` | none | `CATEGORY... UNIT PRICE; ...` — the assets I accept as compensation at my prices; the escrow kinds I accept |
| `require_door` | `LOOP_REQUIRE_DOOR` | none | the door witness my wants require: `possession` (control of the key, the default meaning) or `photo` (possession plus the attested photo, which links the counterparty's face to their key — THREATS T19) |
| `oracle` | `LOOP_ORACLE` | `countersign` | the witness my gives settle against: `countersign`, `possession`, `photo-match` (the approval block says what the photo reveals), or, for a registered item, `registry-transfer(ID)` — the title register's transfer (I4) |

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
line is one v4 want); `line_for(offer) -> str` renders an `Offer` to its
canonical line, `want 2kg apple geo(CELL) time(A..B) valid(A..B) 9`,
and the two round-trip. `parse_offer_tokens`, `parse_want_line`, `window`,
`duration_s`, `radius_m`, `render_offer` are the pure pieces.
Gates G1–G6 (`docs/plans/cli.md`) are `tests/test_cli.py`.
