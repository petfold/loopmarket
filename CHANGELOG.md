# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

Started 2026-09-11. Releases are tag-driven (`v*` tags run
`.github/workflows/publish.yml`, PyPI trusted publishing).

## [Unreleased]

### Added

- **The v4 record** (decided with Peter and built 2026-09-14; the plans'
  four items in one bump). Exact rationals on the clearing path — U9
  enters the invariants: `schema.q`/`rat`, `Fraction` rates, potentials
  and surplus, no epsilon in any gate, floats only in the `-log` search;
  a typed float is the decimal it prints as. `step` and `min` on a
  `Thing` in place of `divisible` (0 continuous, the whole quantity
  indivisible, 1 whole apples, 25 sacks; the floor is the chartered bus;
  `Thing.takes(qty)` the one rule, identical to the old one on old
  records). A want of `Parts` — several things, all or nothing, one price
  — publishes: `check_parts`, `parts_legs`, the CLI's `+` line and
  composed drafts now publish (the `not encodable until v4` refusal is
  gone), `show`/`offers` render parts, `line_for` round-trips with a
  trailing `valid(...)`. Fills name every give with the quantity taken
  (`LoopProposal.fills`; a want's fill lists `gives` with `qty`) and
  nothing else — no prices, per P4 §5 item 4, ruled conditional the same
  day (receipts arrive with sealed offers). The `loop/` record carries
  `"v": 1`, `taken` per give, exact numbers and the potentials (public
  for now, outside `loop_id`). v1–v3 records re-encode byte for byte;
  the 2026-08 fill shape still reads. Not yet: a CLI spelling for `step`
  and for the give floor (`10kg..` is still refused at publish), partial
  fills of divisible gives, and the stepped clearing regime.
  `tests/test_v4_record.py`.
- **The registry is deployed**: `LoopBookRegistry` at `0xD4379E494a488411D964BebDb210C0bf628d97af` on Gnosis
  (2026-09-14). `loop set registry chain:https://rpc.gnosischain.com@0xD4379E494a488411D964BebDb210C0bf628d97af`;
  `loop announce` from a `bee_signer` key sends the transaction as that
  key, and a session with only the registry setting reads the announced
  set back with `announced`; with the Bee node up, the same clean
  session read the maker's offer from the announced Swarm feed with
  `offers` and printed the fold's root with `fold` — the read-path gate,
  live, no peer configured anywhere. The contract header is a plain
  comment now (solc read `@OWNER` in the NatSpec text as a tag).

## [0.7.0] — 2026-09-14

The read path: a book becomes discoverable by one announcement on the
chain Swarm settles on, every reader folds the announced set under U8 as
each book's owner, and a manifest is a cache audited against that set.
GSOC and the aggregator-agreement check dropped; terms stored in the
catalogue's canonical spelling; two aliases kept "one release" removed.
Needs ontodag 0.26.1. The registry contract is written and tested against
a client with web3's face; deployment on chain follows.

### Added

- **The announcement channel, and the read path** (Peter, 2026-09-14:
  skip GSOC, go straight to the chain; the aggregator-agreement check
  goes with it). `announce.py`: a book becomes discoverable by one
  announcement — `Announcement(owner, book, role)`, latest per owner,
  retractions — on one of three backends chosen by spec:
  `chain:RPC_URL@CONTRACT` (the `LoopBookRegistry` contract,
  `contracts/LoopBookRegistry.sol`, its event log read with
  `eth_getLogs`, announcements sent as the maker's own transaction so
  `msg.sender` is the feed-signing owner; web3 behind the new `chain`
  extra, lazy), `file:PATH` (sessions on one machine), `memory:`; several
  comma-separated specs are one channel (`UnionAnnouncements`, per owner
  the last-listed wins, writes go to all) so a move to another EVM chain
  is a setting, not a change — nothing in contract or code names a chain;
  the deployment follows the chain Swarm settles postage on.
  `Aggregator.subscribe(channel, open_book)` folds exactly the announced
  set; `audit_manifest(expected=channel.announced())` reports a book
  announced and never folded as an omission with an absence proof, so
  completeness is one reader's computation and aggregators are no longer
  trusted by agreeing with each other. CLI: the `registry` setting and
  `announce [--role]`, `announced`, `fold`; with a registry set every
  fold is the announced set folded through `Aggregator` under U8 as each
  book's announced owner — the solver-self-fold as the default read
  path, manifests as caches. `scripts/deploy_registry.py` deploys the
  contract; not yet run against a deployed one. Plan: `P1-federated-book.md`
  §4 rewritten, T14 updated. Tests: `tests/test_announce.py`, the
  three-maker file-registry flow in `tests/test_cli.py`.

### Changed

- **Terms are stored in the catalogue's canonical spelling.** The CLI runs
  every known term through ontodag's `surface.elaborate` before it enters
  an offer — `weight(8000g)` → `weight(8kg)`, `time(2026-10)` → the
  month's full range (as a bare `2026-10` already was), `transport(weight(..8kg)
  small-item)` → `transport(small-item weight(..8kg))` — so one denotation
  is one offer id (U2). `schema.canonical_term`, the interim sort that
  only ordered an operator's constituents, is gone; `Thing` sorts
  concepts and nothing else.

### Removed

- `Ontology.declare_service_roles` (the 0.3.0 name, kept one release) and
  the `loopmarket.settlement` import alias (the pre-2026-09-07 name, kept
  one release). Both had outlived the release they were kept for.

## [0.6.0] — 2026-09-14

The operator's argument is its want: `transport(small-item weight(..8kg))`
on the courier's give is what the courier accepts, matched want-within-
give against the wanter's `transport(bicycle)`; the term is ontodag's graph
kind (0.26.1). Breaking: `declare_operator` takes the category and its two
ends. Needs ontodag 0.26.1.

### Added

- **An operator's argument is its want** (Peter, 2026-09-13 evening: *the
  parameter of the transport is a want from the transporter's side*).
  `give transport(small-item weight(..8kg)) from(barcelona) to(barcelona)`
  says what the courier accepts; `want transport(bicycle weight(5kg))
  from(flat) to(shop)` says what the wanter hands over; the argument is
  matched want-within-give, constraint by constraint (`bicycle ⊑
  small-item`; the 12 kg bicycle fails the 8 kg limit; a give constraint
  the want is silent on refuses), the operator category itself
  give-within-want. `transport(A B)` is the same term as `transport(A)
  transport(B)`; `schema.canonical_term` sorts the constituents so the
  spellings are one offer id (U2). The same argument is the payload check
  of a composed leg (`Ontology.accepts`): the small-item courier moves the
  box and not the piano — the gap 0.5.0's composition had. A direct
  transport want now matches the courier in `check_match`. New facade
  methods `operator_of`, `argument`, `ends`, `accepts`; the CLI rejoins a
  term's tokens while a parenthesis is open. The term is ontodag's
  **graph kind** (#19, asked and landed the same evening, ontodag
  0.26.1 — the pin moves): `declare_operator` puts the category under
  `graph-dimension` as well as `operator`, ontodag canonicalises the
  argument (sorted, deduplicated; a redundant constraint such as
  `transport(bicycle small-item)` refused, an unknown one failing closed)
  and orders two such terms by the graph, and a give whose argument the
  catalogue refuses matches nothing rather than "anything". Tests in
  `test_ontology.py`,
  `test_circulation.py`, `test_schema.py`, `test_cli.py`; the index recall
  book carries operator terms; `examples/delivery.loop`'s courier says
  `transport(small-item)`.

### Changed

- **`declare_operator` takes the category and its two ends** —
  `{"transport": ("from", "to")}` puts `transport` under the new `operator`
  marker and the roles under `operator-input`/`operator-output`; 0.5.0's
  `{base: (in, out)}` shape raises. `Ontology.operators()` is gone: a
  give's moves are read off the ends it names (`ends`), and an operator
  give is recognised by its operator term, not by carrying two role terms.
  The seeds (`triangle.od`, `delivery.od`, the demos) declare
  `graph-dimension dimension`, `transport graph-dimension operator`
  and `storage graph-dimension operator`. Pin `ontodag>=0.26.1`.

- **Composition search: only where needed, and up to two hops** (Peter's
  follow-up questions, 2026-09-13). `composed_legs` no longer composes an
  operator onto a give that already reaches the want (a lesson at the door
  already serves a want anywhere in the city), and chains up to two
  distinct operator gives for one thing — two couriers of the same packet,
  shop to hub, hub to door — proposing a chain only where a shorter one
  does not reach. `check_composition` always applied operators in
  sequence; clearing verifies chains of any length. Tests: two deliveries
  in one ring, two couriers of one packet (`tests/test_circulation.py`).

## [0.5.0] — 2026-09-13

The day after 0.4.0, from one worked example (a vegetable box, a shop, a
courier, a door): no `where`/`when` heads, handover coordinates matching
when one side contains the other, and a baseline solver that finds
circulations — a want met by several gives at once, cleared as one leg.
Needs ontodag 0.25.0.

### Added

- **The baseline solver finds circulations** (Peter, 2026-09-13: "the
  whole point of a solver is to find circulations"). A want may be met by
  several gives at once: `matching.Leg`, `check_composition(want, gives)`
  — the thing's give moved by an operator give the catalogue declares
  (`Ontology.declare_operator({"geo": ("from", "to"), "time": ("depart",
  "arrive")})`; the operator's input must be comparable with the thing's
  coordinate, its output replaces it) — and `composed_legs`, the cubic
  one-hop search. `graph.Circulation` is a set of legs in which every
  maker both gives and receives; feasibility is the existence of node
  potentials (a Bellman–Ford-shaped fixpoint; for a simple cycle exactly
  product > 1), `surplus` compounds the largest uniform per-leg gain and
  equals `Loop.surplus` on a cycle, `loop_id` agrees with `Loop` there.
  `find_circulations` is a deterministic depth-first hunt the agent runs
  after Bellman–Ford's simple cycles. Clearing re-derives composed legs
  with `check_composition` and checks the potentials; the `loop/` record's
  legs carry `gives` and a composed set its `potentials`; U11 reads them.
  `examples/delivery.loop` clears the grocer's box at the shop plus the
  courier's run to the door as one composed leg (with the ring closed by
  two lessons); the seeds declare the operators.

### Changed

- **No `where`/`when` heads; handover coordinates match either way**
  (Peter, 2026-09-13, from the vegetable-box example). Where an offer
  holds is a bare geo term in its conjunction — `give vegetable-box shop`,
  a cell, a region, a place node — and when it holds a bare time term; a
  head stays only for the two ends of a route or transport
  (`from`/`to`, `depart`/`arrive`) and for descriptive geo/time terms
  (`made_in`, `made`). A handover coordinate on a give answers the want's
  when it fits within it *or contains it*: the seller delivering anywhere
  in the city serves the want at the door, the shop serves the buyer who
  collects anywhere; partial overlap is not a match; categories and
  descriptive terms stay one-way. The seed marks the dimensions:
  `declare_handover(["geo", "time"])` (roles under them inherit),
  `declare_descriptive(["made_in"])`. `DimensionIndex.candidates` queries
  the one-way terms only and leaves place and time to `check_match`. The
  seeds, demos, `triangle.loop` (`give piano-lesson amara_flat 100`) and
  the CLI (`set terms home`, a bare `LAT,LON,R` or `today..+7d`) follow;
  `examples/delivery.loop` and `tests/test_handover.py` carry the example,
  including the leg the P0 solver cannot yet compose (the shop's box plus
  the courier's `from(barcelona) to(barcelona)` — P2's operator form).

## [0.4.0] — 2026-09-13

Needs ontodag 0.25.0 (role parameters naming nodes, `items_only`, the
dimension cache; released the same day). The night's design thread: one
relation, containment, for every term — the overlap rule of 0.3.0 was a
modelling error (Peter: a want is the wider cone, a give the narrower).

### Changed

- **One relation: containment, for every term** (Peter, 2026-09-12 night:
  "an overlap of everything with A is just A"; "a want is a wider cone and
  a give is a narrower cone" — the toothbrush wanted within five metres of
  the reception desk within thirty minutes is a narrow want, and the give
  that fits within it matches). Where and when a thing changes hands are
  terms like its categories: `Ontology.satisfies` is `is_below` term by
  term, a want's place and window are query terms, and a give must fit
  within them. The 0.3.0 overlap relation for "service roles" — heads
  under a `service-role` marker matched by "a handover point exists" — is
  gone with the marker: `declare_roles({head: base})` declares a role of a
  dimension (one edge, `odag put from geo`; `declare_service_roles` stays
  one release as an alias), and `is_service_role`/`split_roles`/`meet`
  left the facade. A give that says nothing about where it hands over does
  not satisfy a want that says where; a want that says nothing does not
  care. The example catalogues and `triangle.od` drop the marker.
- **`DimensionIndex.candidates` is one `get` of the want's own conjunction**
  (`get([line marker, *want.concepts], items_only=True)`): place and time
  prune like categories because they are terms like categories. No
  overlap queries, no set arithmetic on the answer, nothing filed but what
  a give says (the v1/v2 window and disc are fields the exact check gates).
  The day's detours — three queries intersected in Python, ontodag #14's
  `overlapping=` planner argument, a whole-space value for silence — are
  withdrawn with ontodag's overlap query mode. Suite 54 s → 11 s.

### Added

- **Names stand in role terms** (ontodag #15, 2026-09-12). A role head
  takes the base dimension's nodes as parameters, so a catalogue name in
  a role term is published as spelled — `where(ljubljana)` (a region above
  cells), `where(my_home_4th)` (a floor under a building), `from(my_home)`
  — and ontodag orders it by the graph. The CLI substitutes a value only
  for a *private* place (a name only the personal store holds, which the
  pinned root cannot carry): it publishes as its cell and the name stays
  private; a private region or floor is refused. A name outside the
  dimension is refused in ontodag's words, never read as a literal cell.
### Removed

- **The `idx/{c,t,g}` recordstore index** (`index_offers`,
  `OfferRegistry.ids_by_index`, `spacetime.cell_for`/`cell_chain`/
  `day_buckets`/`bucket_chain`, the `service-cell` index head): read by
  nothing since 2026-08-21, retired as decided 2026-09-07 now that the
  one-query generator exists. **`Manifest.index_root` is gone with it**
  (three roots: book, provenance, announcement); cone summaries get a
  root of their own if they ever come (`P1-federated-book.md` §2).

### Changed

- Live-checked 0.3.0 on the Bee 2.8.2 light node right after release:
  `loop -f swarm:TOPIC --catalogue examples/triangle.od < examples/triangle.loop`
  published six v3 offers, found and cleared the triangle (`loop_id`
  `2eab00cd3c84c475…`, the same id the in-memory G1 test produces — a
  fixed `now` makes the live book byte-reproducible) in 1m51s; a fresh
  session read the book root and six filled offers back in 11s.
- The federation demo live on the same node with ontodag's core pack, 4m25s:
  three per-maker feeds and a Swarm catalogue with v3 offers, two aggregators
  folding to byte-identical manifests, the censoring aggregator convicted by
  two absence proofs verified without a store, the forgery refused, the
  tombstone honoured, the triangle cleared at 12.22% on a book re-based on
  the fold, and a follower reading the loop and six fills from the manifest.

## [0.3.0] — 2026-09-12

The day's design thread, `docs/plans/P1-spacetime-terms.md`: place and
time leave the offer's fields for its conjunction (the v3 record), the
catalogue declares which heads match by overlap, cells are the geo truth,
and the address reaches the courier through the book.
The record that will carry composed-want parts, per-fill quantities and
D9 rationals — called "v3" in 0.2.0's notes — is now **v4**.

### Added

- **Sealed handoffs and `watch`** (`docs/plans/P1-spacetime-terms.md` §4,
  decided with Peter 2026-09-12): the address is settlement text on the
  place node (`loop place NAME LAT,LON,R [ADDRESS...]`), never vocabulary
  or record. After a loop clears, `loop watch` reports the maker's fills
  (the fill record is the notification), seals each remembered text to the
  leg counterparty's public key — recovered from the signature on their
  own offer, no registry — and writes it as `handoff/<loop>/<offer>` beside
  the maker's filled offer in their own book; the counterparty's `watch`
  opens it with `bee_signer`. `loop handoff ID TEXT` sets the text for one
  offer, `loop handoffs` lists what was sealed to you, the `interval`
  setting paces `watch`. New module `loopmarket.handoff` (ECIES over the
  makers' secp256k1 keys; the `sig` extra gains coincurve and
  cryptography), `sigs.recover_public_key`, registry
  `attach_handoff`/`handoff`/`handoffs`/`loop_of`, and fold admission of a
  maker's own handoffs only.
- **The v3 offer record** (`docs/plans/P1-spacetime-terms.md` step 5,
  decided with Peter 2026-09-12): no `service` window, no `where` disc —
  where and when a thing changes hands are role terms in the conjunction
  (`when(a..b)`, `where(cell)`, `from`/`to`, `depart`/`arrive`), matched by
  overlap through the catalogue; cells and region nodes are the exact geo
  truth, and no record holds a disc. `valid` may be open-ended (`[start,
  null]`: the offer stands until withdrawn). v1/v2 records still read and
  match among themselves, and the field form of `give`/`want` still
  yields a v2 record; `check_match` refuses pairs across the v2/v3 line.
  `spacetime.cell_for_coords` is the v3 spelling of `LAT,LON,R`: the
  finest cell containing that radius. The triangle clears in v3 form
  (`tests/test_v3_record.py`, both demos, `examples/triangle.loop`
  unchanged).
- **Service roles in the catalogue** (`docs/plans/P1-spacetime-terms.md`,
  decided with Peter 2026-09-12): `Ontology.satisfies` now walks one
  conjunction with two relations — containment for what a thing is,
  overlap for where and when it changes hands — and the *head* decides
  which, declared in the catalogue under the marker node `service-role`.
  The marker is the only name the core knows: which heads are roles
  (`from`/`to` over `geo`, `depart`/`arrive` over `time`) is seed
  vocabulary, written with `odag put from geo service-role` or
  `Ontology.declare_service_roles({...})`. A give from anywhere in `u2e`
  now serves a want at
  `u2e4x` and vice versa; `made_in(u2e4x)` still only satisfies
  `made_in(u2e)` one way. Absent role = unconstrained; same-head terms are
  their meet; an uninterpretable role term fails closed on either side.
  No record change: the `service`/`where` field gates still run beside it,
  and a catalogue that declares no roles behaves exactly as before. The
  fields leave at the v3 bump, the package's step 5.
- **Role terms in candidate generation** (step 4 of the same package):
  `DimensionIndex` files a give under its service-role terms and
  `candidates` asks overlap per role head the want names, plus the gives
  silent on that head — place prunes through cells for the first time.
  Recall-exact against the baseline over randomized books carrying
  `from`/`to`/`depart`/`made_in` terms. `Ontology.split_roles` and
  `Ontology.meet` are public. The example seeds (`triangle.od`, both
  demos) declare `from`/`to` over `geo` and `depart`/`arrive` over `time`
  under `service-role`; `triangle.od` carries ontodag's prelude for it.
- **Drafts and composed wants at the command line** (`docs/plans/cli.md`
  §13, `P2-loop-selection.md` §10 "Declared parts", decided with Peter
  2026-09-12): a theatre ticket with transport is one want with two parts,
  cleared together or not at all. `draft [NAME] want|give ...` stages a
  resolved offer or part (a price optional; a local file, never the book),
  `draft [NAME] A + B` composes drafts with the same `+` the one-line want
  uses, `drafts` lists them in canonical spelling with the typed spelling
  as notes, `offer NAME [PRICE]` turns a draft into an offer, `discard`
  drops them; `want PART + PART ... PRICE` is the one-line form. Simple
  drafts publish today; a composed want renders its full block and then
  **refuses** until the v3 record lets `wants` carry parts. Composition is
  want-side only: the give side gets a minimum fill (the chartered bus,
  the cow), never parts.
- **`clearing`** is the clearing-house command; `clear` (delete, on every
  terminal) stays a silent alias for one release.
- **The offer line as Python's literal**: `cli.offer_from_line` and
  `cli.line_for` round-trip an `Offer` and its canonical line.
- `where(LAT,LON,R)` as a literal place, the spelling `place` takes, so a
  canonical draft line re-parses to the same disc.
- Live-checked on a Bee 2.8.2 light node after the changes: both gated
  Swarm suites pass (5m38s), and the triangle script on a Swarm feed
  clears in 58s to the same `loop_id` and book root as before.

### Fixed

- A place name in a role term now takes its *most specific* cell: a place
  hangs under its own cell and, by computed containment, under every
  coarser one, and the first ancestor in set order was sometimes the
  coarse one.

### Changed

- **`loop` speaks only catalogue terms.** `when(...)` and `where(...)` pass
  through as role terms (the seed declares them; `triangle.od` carries
  ontodag's prelude for it); the one interpreted head is `valid(...)`,
  now accepting `valid(A..)`; `time(...)` terms are accepted; a
  `LAT,LON,R` parameter of any geo-kind head becomes the containing cell;
  the approval block shows terms and validity only; `place` writes the
  node under its cell and no disc metadata. The `where`/`when` settings
  and `--where`/`--when` flags are replaced by one `terms` setting
  (`--terms`): terms added to every offer whose line does not name that
  head; unset, an offer is anywhere, any time (Peter's ruling: optional).

## [0.2.0] — 2026-09-12

### Added

- **The command line, `loop`** (`src/loopmarket/cli.py`, `python -m
  loopmarket`; design record `docs/plans/cli.md`). Ontodag's grammar plus
  two conventions — a bare number first is the quantity, last is the price
  — every name a catalogue node (places via `loop place NAME LAT,LON,R`, a
  dated bridge), an omitted price the maker's last unit price for the same
  thing, the fully resolved offer shown and approved before anything is
  published, and `show ID` printing that same block later. Commands for
  the maker (`give`, `want`, `withdraw`, `mine`, `place`), the reader
  (`offers`, `show`, `matches`, `status`), the solver (`loops`) and the
  clearing house (`clear`), plus `set`, `export`, `import`. Settings share
  odag's format and precedence rule and inherit its Bee configuration; a
  bare `loop` at a terminal is a prompt, a pipe is a batch. Live-checked
  with the book on a Swarm feed the same day.
- **Role terms match.** `Ontology.known` accepts a parametric term of a
  declared dimension head (it asks the DAG to order the term against
  itself), so `from(u24m)` in an offer fits within `from(u2)` by ontodag's
  computed containment. At the command line a catalogue *name* in a term's
  parameter takes its public value (`from(home)` → `from(u24m)`), printed
  as a note; the published offer holds public vocabulary only.
- `examples/triangle.loop` + `examples/triangle.od`: the triangle demo as
  a fifteen-line script; `tests/test_cli.py` (gates G1–G6 and the rules
  around them).

### Changed

- The user guide is a command-line tutorial with the API alongside; the
  README leads with `loop`; the reference manual gains §17 (grammar,
  commands, settings) and the `LOOP_*` environment.
- Dependency floor: `ontodag>=0.23.0` (the CLI uses its store backends,
  prelude and surface layer).

### Rulings recorded (Peter, 2026-09-12)

- The binary is `loop`; `loopmarket` is the long alias.
- In a batch under `confirm auto`, a line whose price was *reused* refuses
  rather than publishing a number nobody saw.
- Ontodag interprets the *name* in `from(my_home)`; the CLI carries its
  value into the term.

### Known

- Quantity and time terms (`weight(...)`, `time(...)`) are accepted by the
  grammar and refused at publish until quantities and spacetime become
  catalogue terms (`ontodag-coupling.md` §2–3). `peers` is a trusted
  union; U8 admission arrives with the `fold` command. The schema has no
  numeric normalization (`1` ≠ `1.0` as records) — the CLI keeps the typed
  form; the fix is D9's in the v3 bump.

## [0.1.0] — 2026-09-11

First release on PyPI (the tag workflow succeeded on its third run, after
the `[sig]` extra gained its hashing backend).

A universal combinatorial marketplace: uniform offers over an OntoDAG
catalogue, a versioned offer book on recordstore/Swarm, and solver agents
hunting profitable loops.

### The model, as settled so far

- **The primitive is a circulation; the loop is its smallest case.** `loop`
  keeps its name and widens its meaning, with `cycle` reserved for where the
  reasoning goes round — settled by two vocabulary audits.
- **Composition: one want, many gives** — the buyer pays once.
- **Clearing is not settlement.** The commit fixes obligations; delivery
  settles them. Cleared loops count; delivery never adds credit (U12).
  `settlement` was renamed to `clearing` throughout, and
  `P2-settlement-pricing` became `P2-clearing-pricing`.
- **Who commits is not the solver.** Smarter solver species live outside this
  repo; the public repo names no particular solver.
- **Hyper-legs and hypergraphs**: the pallet as one hyper-leg, with the
  hypergraph defined where hyper-legs are used.

### Added

- **One intersection engine** — no set arithmetic in loopmarket itself, and
  `idx/` retires.
- Candidate generation issues one query rather than three.
- Plans: one clearing commit per beat, and publication of the anchored root.
- A live federation demo recorded on Bee, with commits retrying transient 5xx.

### Open before v3

- The integer granularity of a give in loop selection is a decision still
  outstanding.
