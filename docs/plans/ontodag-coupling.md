# loopmarket — the catalogue contract (ontodag coupling)

Status: design, 2026-08-07. Decided here: ontodag `CONTRACT.md` G1–G6 +
the as-of clause adopted as loopmarket's normative substrate, O1–O3 as
standing obligations; the spacetime migration completed on paper (exact
interval time terms, prefix-dimension cells, region nodes, three-valued
`get_overlapping` reports, fixed-UTC-offset elaboration); unit families
for quantities, prices and tokens — the U9 substrate — with personal
tokens as address-named unit families, bridged assets as distinct
families, and matching's gate 6 moved into the catalogue; the five-degree
match ladder with concept abduction, routed to solver speculation / maker
recruitment / catalogue demand signals and **never settlement**;
derived-index discipline (derived, local, never merged; the indexed
generator wired behind a measured threshold); the two-axis criterion as
the filter on what loopmarket pushes upstream (disjointness stays out);
`BINDING` §1's one-filler-per-role rule as schema validation; the tripwire
table, with the Merkle-cone-commitment wall fired formally at P2 start and
solver query-set logging on from day one. Open here: pin agility under
catalogue growth; abduction weights; the indexed-generator threshold;
shared tangent-plane frames; ordinal and cyclic encodings.

This is the treaty between loopmarket and its catalogue: what loopmarket
relies on upstream, what it must never build locally, and what evidence
obliges it to ask for more. The catalogue's *content* — seeds, imports,
governance — is `catalogue-bootstrap.md`; pins and certificates are
`proof-fabric.md`; the exact-rational settlement migration leaning on §3
is `P2-settlement-pricing.md` §8; the aggregator publishing §5's derived
`index_root` is `P1-federated-book.md` §2; §4's demand signals feed
`P3-guarantee-coupling.md`. Normative upstream: ontodag `docs/CONTRACT.md`,
`docs/DIMENSIONS.md`, `docs/UNITS.md` + `UNIT_TABLE.md`,
`docs/plans/BINDING.md`, `docs/plans/DATABASE_DIRECTION.md`.
ARCHITECTURE.md §3–§4 point here.

## 1. The substrate: G1–G6 and the as-of clause are load-bearing

loopmarket's invariants are theorems over ontodag's guarantees, so the
guarantee set is adopted as normative and pinned (`ontodag.CONTRACT_VERSION`,
0.1, conformance-tested — part of the U10 tuple, quoted: "load-bearing pins
{book_root, ontology_root, REGISTRY_VERSION, CONTRACT_VERSION}, verifiers
refuse on mismatch or absence"). What each guarantee carries here:

- **G1 canonical root** (equal knowledge ⇒ equal root) is why an
  `ontology_root` pin means anything: a fingerprint of knowledge, not
  phrasing. Every "which catalogue said the cello fits the crate" rests
  on it.
- **G2 monotonicity** (true `is_below` answers stay true under merge;
  cones only grow) is why catalogue growth cannot invalidate pinned
  matches — and the only honest basis for ever relaxing the
  refuse-on-different-roots rule (open problem: pin agility).
- **G3 determinism** and **G4 `is_below` fail-closed** ("true only when
  the graph plus dimension arithmetic *witness* it") are U6's and U7's
  upstream twins. G4 makes `satisfies` verifier-shaped: re-derivation and
  certificate verification answer the same question by construction
  (`proof-fabric.md` §4).
- **G5 convergence** is the P1 aggregator's precedent: writers folding
  each other's roots land byte-identical.
- **G6 `get_overlapping`** ("complete for possibility, silent on
  satisfaction") ratifies an existing dependency by name (CONTRACT §8.3):
  loopmarket's candidate generation is exactly this — cones and overlap
  for recall, `check_match` for truth.
- **The as-of clause** (CONTRACT §4): monotone questions may be asked of
  the living store; non-monotone questions must name a root. U4 restated
  from the other side, and the source of the planned-invariant tail
  "non-monotone claims (offer absent, no better loop) always name a root"
  (`proof-fabric.md` §5).

The obligations run the other way and are adopted as standing rules:
**O1** derived closures stay local and regenerable (§5); **O2** every
non-monotone answer cites (query, root, registry version) — "an uncited
non-monotone answer is not a fact, it is a snapshot of one"; **O3**
write-back is monotone attributed claims only — no weights, probabilities
or reputations in identity, ever (§6). loopmarket's own agent surfaces
(offer entry, the broker of `adoption-and-thickness.md`) reuse ontodag's
envelope conventions rather than inventing any: answers carry `root` +
contract version + a namespaced `annotations` map, truncation is opt-in
and self-declaring, elaboration goes through `ontodag.surface` with
canonical echo as the confirm step — and **pre-elaboration spellings are
never stored in offers** (they would enter `canonical_bytes()` and churn
`offer_id`).

## 2. Spacetime becomes dimension terms (decided 2026-08, lands with P1)

`spacetime.py`'s day buckets and cell chains are subsumed (ontodag
`DIMENSIONS.md` §10, explicit). The completed shape:

- **Time windows are exact linear-interval terms** — `time(a..b)` over
  fixed ISO-8601 UTC; half-bounded ends free; point = degenerate interval.
  The day-bucket decomposition loses precision the interval term doesn't;
  generated bucket nodes drop out, surviving only as derived indexes.
  Calendar-period literals (`2026-08`) ride the `calendar-dimension` head.
  Time cells are exact — no boundary layer, so time needs no prefix kind.
- **Timezones elaborate at creation.** tzdata/DST is an upstream wall —
  political zones are legislation, not arithmetic — so offer entry snaps
  local times to concrete UTC offsets at input; the stored term is fixed
  UTC. Wall-clock *recurrence* ("Saturdays 9–17 local") is not one stored
  term today: see the cyclic row of §7.
- **Geo cells are `prefix-dimension` terms** — containment computed from
  the name, only used cells materialize, cell-scheme-agnostic (S2 later,
  "no design change"). **Service regions are region nodes above their
  interior cells** — any shape, holes, disconnected regions, adaptive
  precision all free; coverage queries are ancestor walks. The rule with
  teeth: **never multi-parent an offer under several cells** —
  `put(X, [A, B])` asserts the (near-empty) intersection, not the union —
  and ontodag enforces it: `put` under provably-disjoint same-dimension
  parents raises `ValueError`, a cheap exact lint for the
  union-vs-intersection footgun.
- **`get_overlapping` is the gate's native shape** (shipped v0.4.0,
  2026-07-30, built because loopmarket's time/geo gates are
  overlap-shaped; overlap is not transitive, so it is a query op, never
  stored). Match reports become three-valued: *guaranteed* (containment
  witnessed), *possible* (overlap candidate — the exact check decides),
  *impossible* (provably disjoint — pruned with no recall loss).
- **`GeoDisc.intersects` stays the exact truth.** Upstream's determinism
  doctrine permanently excludes transcendental arithmetic from the
  canonical order, so haversine discs never enter the DAG; cells and cones
  are recall-safe hints and `check_match` stays self-contained (U3's
  requirement, unchanged). The deferred upgrade is noted for what it is:
  planar tangent-plane discs are doctrine-admissible today
  (disc₁ ⊆ disc₂ ⇔ r₁ ≤ r₂ ∧ dist² ≤ (r₂−r₁)², exact over rationals;
  error ~(d/R)², centimeters at service scale) *if* a shared projection
  frame enters the vocabulary like a unit — moving "within 10 km" into
  recall-exact candidate generation. Per-pair halfway frames stay
  application-side forever: containment must be a function of stored names.

None of this moves the truth, and the derived rehearsal already ran: the
`DimensionIndex` (2026-07-30) files asks under exactly these terms in a
derived deepcopy, proven recall-exact against the baseline product
(`tests/test_dimensions.py`). What lands with P1 is the *shared* catalogue
carrying the terms, under a pinned root and registry version.

## 3. Unit families: quantities, prices, tokens (the U9 substrate)

U9, quoted: "exact rationals in everything settlement re-verifies."
ontodag's D9 rational anchoring (registry v3, 2026-08-01) supplies the
representation: canonical values are reduced rationals of the anchor unit,
comparisons cross-multiply, no floats anywhere — 247 built-in suffixes,
446 spellings with packs, decimals parsed exact (`0.99USD` → `99/100USD`).
`P2-settlement-pricing.md` §8 owns the settlement migration; this section
owns the catalogue side:

- **Quantities and token amounts become unit-family rationals.**
  `Thing.qty` and `Tokens.amount` adopt D9 representation (decided
  2026-08, lands with the v2 bump; the epsilon-free settlement path with
  P2). Indivisible quantities take the `count` dimension — whole-number
  floor of 1, `count(0)` refused as an absence claim in an open-world
  store — the same fail-closed philosophy as U5 and U7: absence is never
  encoded as a magnitude. `count(1..)` ≡ absent coordinate, so
  unannotated offers cost nothing.
- **Personal tokens are unit families named by the maker's address.** A
  unit declaration is graph data (`unit-family(NAME)` under
  `unit-declaration`) that travels inside the store — a fresh reader
  parses with nothing installed; declarations extend vocabulary without
  touching stored spellings or the registry. Naming each family by the
  maker's feed-owner address (the identity U8 and P1 standardize) makes
  declarations collision-free by construction — the Mercury
  same-name-merge hazard (`catalogue-bootstrap.md`) cannot arise between
  tokens. No personal token ever hard-claims a suffix.
- **Bridged and pegged assets are distinct families, never identities.**
  Upstream's crypto-core pack states the principle (BZZ vs xBZZ: "a
  bridge's nominal 1:1 costs a fee, takes time, and can fail, so it is a
  relation between distinct assets, never an identity"; DAI vs xDAI
  likewise; a peg is a promise, not arithmetic — USD vs USDC refuses).
  This is not a constraint loopmarket tolerates; it *is* loopmarket's
  model: cross-family comparison refusing at the catalogue layer is the
  same fact as bridged assets being edges with rates in the
  `ExchangeGraph`. A whole class of unit-confusion bugs becomes
  unrepresentable.
- **Matching's gate 6 moves into the catalogue** (decided 2026-08, lands
  with the U9 migration, before P2). Today the unit check is raw string
  equality — "course" vs "unit" never match and nothing relates them.
  Upgraded: units resolve through the merged declaration context; same
  family ⇒ exact rational conversion; different families ⇒ refuse, which
  is the truth. Unknown units already refuse upstream with teaching
  errors — gate 6 inherits U7's fail-closed shape for free.
- **Does-it-fit is native.** The `dominance` dimension
  (`size(390x230x190mm)`, components canonically sorted, componentwise
  intervals) makes "the cello fits the crate" a stored-name containment
  question — the same `is_below` settlement re-verifies and factbond's
  certificate rung adjudicates. The `pct`/`bp` suffixes are ready-made
  for P3 rate premia.

Cross-dimension *computation* stays walled upstream (`price × quantity` —
DATABASE_DIRECTION's exact-arithmetic tripwire was fired by loopmarket
2026-07-30 and resolved as parametric dimensions, with that explicit
residual). Loop arithmetic — products, surpluses, splits — stays
application-side forever; the catalogue supplies exact operands, never
economics.

## 4. Match degrees: the ladder above the Boolean

`satisfies` is and remains Boolean, exact, fail-closed. Above it, the
description-logic matchmaking school (Paolucci–Kawamura–Payne–Sycara,
ISWC 2002; refined by Di Noia, Di Sciascio, Donini, Mongiello, WWW2003,
and "Semantic Matchmaking as Non-Monotonic Reasoning", JAIR 2007) defines
a degree ladder that loopmarket's one-relation fragment computes almost
for free with existing `is_below`:

1. **exact** — mutual coverage;
2. **full** (subsumption) — offer ⊑ demand: today's `satisfies`, the only
   degree that settles;
3. **plug-in** — demand ⊑ offer: the offer is *too general* — unmatchable
   under strict `satisfies`, but one refinement away;
4. **potential** (intersection) — cones intersect without subsumption:
   something is *missing*, not wrong;
5. **fail-unknown** — vocabulary not in the catalogue: hard-closed, U7;
   no ladder position softens it.

**Concept abduction** (Colucci et al., DL-2003) degenerates in this
fragment to a cone diff: H = the wanted atoms whose descendant cones the
offer's concepts don't reach — the shopping list of what the offer lacks,
ranked by weighted |H| with per-dimension weights (a concept shortfall, a
window miss and a geo miss price differently). One correctness criterion
is adopted from Di Noia et al. as binding on any scorer: **monotonicity
over subsumption — adding detail to an offer never worsens its rank.**
Full contraction ("what *conflicts*") needs disjointness, which the
concept layer doesn't have; within a dimension disjointness is decidable
(`intersect()` empty), so time/geo/quantity conflicts can honestly report
*conflict* while concept-side conflict collapses into *potential* (§7).

**The routing rule (committal).** Degrees 1–2 are the only input
settlement ever sees; degrees 3–4 route to exactly three consumers and
nothing else (decided 2026-08, lands with the broker surface —
`adoption-and-thickness.md`): (a) **solver speculation** — almost-loops
held against future offers; (b) **maker recruitment** — "add X and this
loop closes", the hint plug-in matches exist for; (c) **catalogue demand
signals** — recurring abduced H's are demand for missing vocabulary or
edges, priced as factbond assertion opportunities
(`P3-guarantee-coupling.md`, `catalogue-bootstrap.md`; signals are
statistics, so U12's settled-fee-paid-only discipline guards what they
may ever earn — T2's pollution surface, `THREATS.md`). The rejected
alternative is named: score-thresholded fuzzy matching into settlement —
it trades U3/U7 determinism for recall exactly where money moves, and
G4's verifier shape (witnessed or false) cannot express "0.83 similar".
Near-miss scores are advisory in every phase, forever.

## 5. Derived-index discipline

O1 is the rule; the `DimensionIndex` is the sanctioned shape (a derived
deepcopy — never the shared catalogue, which would churn every pinned
root); ontodag's descendant counts are the cautionary tale (derived state
conflicts on every concurrent write). Stated once for every index this
system will ever have:

- **Derived, local, never merged.** `idx/{c,t,g}`, the `DimensionIndex`,
  the aggregator's `index_root`, cone summaries, future semantic-code
  bitmaps: own store or own memory, regenerable from a pinned root,
  short-TTL stamped when published, **re-derived after every merge, never
  merged** (`P1-federated-book.md` §3 applies this; the dead maker-book
  `idx/` writes die there, reborn as the aggregator's derived index).
- **A stale index is ignored, never wrong.** The cone-summary manifest
  pattern — `{data_root, index_root, format, policy}`, a cache with exact
  fallback that "changes time, never meaning" — is adopted for every
  published index. Thin solvers get affordability from it: LazyOntoDAG
  plus published summaries measured 375 → 3 record + 3 index fetches on
  broad-term queries (live on Swarm: 1 + 2 vs 71).
- **The meet-node hazard: prune-only.** `put(X, [A, B])` creates a
  *sibling* of the meet, never the meet, so
  cone(AB) ≠ cone(A) ∩ cone(B) (SEMANTIC_CODES §10; CONTRACT O4). A
  materialized intermediate category may *prune* candidates, never
  *generate* them — a generator enumerating a meet node's cone silently
  loses recall. Standing rule for every candidate generator.
- **Wiring the indexed generator** (decided 2026-08, lands with P1):
  `candidate_matches_indexed` is proven recall-exact against the baseline
  (equality over randomized books; candidate count < 0.8× the full
  product) but deliberately not the default. It becomes the solver's
  generator **behind a measured book-size threshold**: below N* the
  O(asks×bids) baseline with constant-time gates wins and stays the
  recall benchmark; above N* the index pays. N* is measured, not guessed
  (gate G3); the recall-equality suite runs at the switch point. Geo
  deliberately stays with the exact check (sibling geohash cells share no
  prefix — a cell filter loses recall) until region-node coverage queries
  change that arithmetic.
- **Feed the parked machinery, don't pre-build it.** Semantic codes /
  bitmap cone indexes are parked upstream behind explicit gates (hot
  query workload, RAM-exceeding graphs, thin clients), the admission
  policy waiting on workload evidence — and a large offer book with hot
  solver queries is precisely that workload. Decided 2026-08, lands with
  P1: **solvers log their query category-sets from day one** (the
  upstream query counter exists; loopmarket contributes the workload
  trace), so when the gates open, materialization runs on real
  distributions instead of guesses.

## 6. What loopmarket may push into the catalogue

The two-axis criterion (CONTRACT §5) filters every push: a thing enters
the shared catalogue only if **monotone** (merge-as-union survives) *and*
**cheaply semantically canonicalizable** (equal knowledge ⇒ equal root
stays decidable) — both necessary, together insufficient; tripwires decide
warrant. Applied:

- **In:** category edges, parametric dimension values, unit and
  unit-family declarations, region nodes, §2's spacetime terms — monotone
  claims with canonical names. (Content admission — who asserts what,
  bonded how — is `catalogue-bootstrap.md`'s governance and T6's surface:
  catalogue governance capture, primary: factbond `THREATS.md`.)
- **Out: offers.** Filing offers into the shared catalogue churns every
  pinned root; the derived-index path (§5) exists so this never happens.
- **Out: disjointness and negative constraints as global axioms.**
  Disjointness assertions would merge like any claim, but enforcement is
  local policy, never a merge precondition — "`get(Cat, Dog)` being
  non-empty *is* the consistency check." The decidable island loopmarket
  already has is within-dimension disjointness (§2's lint, §4's conflict
  reports). The economic form of concept-level disjointness is factbond's
  local bonded sibling partitions
  (`factbond/docs/plans/netting-and-reserves.md` §5), not a logic upgrade.
- **Out: weights, confidence, reputation, guarantee status** (O3; F6,
  quoted: "factbond state never enters canonical knowledge"). Two books
  with identical offers and different bonding must keep identical roots,
  or agreement-by-fingerprint dies. Guarantee status surfaces only in the
  reserved **`annotations.factbond`** namespace of answer envelopes —
  reserved upstream from day one, shipping empty; schema v1 owned by
  factbond (`factbond/docs/plans/records-and-anchoring.md` §8:
  `{v, status, confidence, capital, basis, policy_ref}`). loopmarket
  consumers ignore unknown namespaces, treat every field as a
  recomputable cache (F1), and never render `Certified` as "true" (F7).

**BINDING scope rules enter schema validation** (decided 2026-08, lands
with the v2 bump). ontodag `BINDING` §1: flat roles are sound for exactly
one filler per role per item — `transport, from(London), to(Rome)` works
today; two `from`s on one offer silently asserts an intersection nobody
means, so `Offer` validation refuses a second filler of any role.
Grouping (§2) breaks flat sets, and the sanctioned pattern (§3) is
already loopmarket's architecture — *legs are the items; journeys are
query-layer joins* ("loopmarket's entire job is finding chains and cycles
of compatible offers" is BINDING's own citation). So: **composite offers
are separate legs joined by the solver, never bundles.** Ground bundles
(§4) are a proposed amendment, unaccepted — nothing here may assume them;
a mixed bouquet today is one item per part-line (the `count` head
shipped; bundles did not), joined at query time.

## 7. The tripwire table

Each wall stays a wall until named consumer evidence fires it; every
"meanwhile" must be livable indefinitely. A fired tripwire obliges
loopmarket to *ask upstream*, never to build locally — a local fork of
`is_below`, subsumption proofs or dimension arithmetic is a second
implementation with its own bugs and no treaty.

| Upstream wall / tripwire      | Fires on (loopmarket evidence)        | Meanwhile / status |
|-------------------------------|---------------------------------------|--------------------|
| Exact arithmetic in terms     | fired 2026-07-30, by loopmarket       | **Resolved**: parametric dimensions. Residual wall: cross-dimension math (§3). |
| Merkle cone commitments       | P2 on-chain ⊑ verification            | **Fired at P2 start** — ask for a *derived* commitment index (`proof-fabric.md` §7). Meanwhile: `is_below` certificates. |
| Query-argument subsumption    | parametric terms in offer concepts (§2) | Ask when §2 lands; if built: intensional-only, no sup-side disjunction. Now: per-pair `is_below` in `satisfies`. |
| Meet nodes as generators (O4) | never — standing hazard               | Rule: prune, never generate (§5). |
| BINDING ground bundles        | within-offer filler pairing that matters | One item per part-line; solver joins legs; role validation (§6). Upstream §6 fork noted: bundle subsumption may be root-dependent. |
| Ordinal dimension kind        | condition grades / ratings in a vertical | Grade chains as plain categories; **never fake linear ranks** — invented magnitudes enter identity and lie. |
| Cyclic dimension kind         | recurring service windows (`hours(22..06)`) | Bounded-horizon generated nodes (validity bounds the horizon); fixed-offset elaboration. |
| Disjointness / negation       | concept-level "conflict" reporting demand | Within-dimension only (decidable, enforced); factbond bonded sibling partitions (§6). |
| ZK proofs over private stores | "loopmarket-shaped counterparty" — P4 by name | Nothing built; `P4-privacy.md` owns the firing. Noted: exact rationals + one primitive = circuit-friendly. |
| Semantic codes / bitmaps      | logged hot solver query-sets          | **Logging on from day one** (§5); cone summaries + `DimensionIndex` meanwhile. |
| Chunk layout / leaf-packing   | hydration cost breaching P1 latency gate | Hydrate-once + `get_many` batching; published summaries. |

## Gates

- **G1 — spacetime terms live.** The triangle settles with service
  windows and cells as shared-catalogue dimension terms under a pinned
  {root, REGISTRY_VERSION}; the recall-equality suite proves the
  term-driven generator exact against the baseline; the disjoint-parents
  lint demonstrably rejects a multi-parented offer. Owner: P1.
- **G2 — unit families in matching.** Gate 6 resolves via merged
  declarations: same-family different-suffix offers match with exact
  conversion; cross-family refuses; a personal-token family declared in
  one store parses in a scorched-earth reader. Shared with
  `P2-settlement-pricing.md` G4. Owner: the v2 bump → P2.
- **G3 — the threshold is a measurement.** N* pinned by benchmark
  (baseline vs indexed generator over growing randomized books, both
  recall-exact by test); `SolverAgent` switches at N* with the equality
  suite green at the switch point. Owner: P1.
- **G4 — the ladder is advisory by construction.** Degree computation
  ships with a property test for Di Noia monotonicity (adding a concept
  to an offer never lowers its degree) and a settlement test proving
  degrees 3–4 cannot reach `submit` through any code path. Owner: the
  broker surface (`adoption-and-thickness.md`).
- **G5 — tripwire hygiene (procedural).** The cone-commitment ask is
  filed upstream at P2 start (mirrors `proof-fabric.md` G5); query-set
  logging is on from the first federated solver; each fired row of §7
  gets its upstream answer recorded here. Owner: P1 / P2 kickoff.
- **G6 — BINDING validation.** Schema refuses a second filler per role;
  the v2 id-stability suite passes across the bump (U2). Owner: the v2
  bump.

## Open problems

- **Pin agility under catalogue growth.** Matching refuses offers pinned
  to different roots, and §3 makes every new maker's token-family
  declaration move the root — strict refusal would fragment the book by
  publication date. G2 monotonicity is the honest way out (`satisfies`
  true at R stays true at any root folding R in), but "R' folds R in" is
  a lineage claim needing verification (diff against ancestry, or an
  aggregator-published root chain). Undesigned; strict refusal is the
  behavior until it is. Work package: P1, with `catalogue-bootstrap.md`'s
  release pipeline.
- **Abduction penalty weights.** Weighted |H| needs weights; monotonicity
  (§4) is the only adopted constraint. Whether weights are solver-local
  policy, broker configuration, or learned from settled-loop statistics
  (U12-guarded) is open. Work package: `adoption-and-thickness.md`.
- **The indexed-generator threshold.** N* is unmeasured; the 0.8×
  candidate-count bound is a test-fixture fact, not a benchmark. Work
  package: P1 (gate G3).
- **Shared tangent-plane frames.** Recall-exact geo needs frame
  vocabulary — who declares frames, at what granularity, governed like
  units. Nobody's tripwire yet. Work package: post-P1, with
  `catalogue-bootstrap.md`.
- **Ordinal and cyclic encodings.** The grade-chain and bounded-horizon
  stopgaps (§7) degrade at scale: fine recurrence × long validity blows
  up generated nodes; deep grade chains invite fake-linear shortcuts.
  Both wait on upstream kinds loopmarket must *ask for* with vertical
  evidence, not simulate. Work package: adoption verticals → upstream
  asks.

## What this document does not promise

The catalogue certifies asserted structure, never world-truth (ontodag
L1; factbond F7 — "certified ≠ true" on every surface): `satisfies` at
root R says the catalogue at R relates the names, not that the crate
holds the cello. Recall-exactness is a property of *proven generators*,
not of the catalogue — cells, cones and summaries are hints, `check_match`
remains the exact, self-contained truth, and nothing in this treaty
weakens U3 or U7. Match degrees 3–4 are advisory in every phase; no
roadmap item upgrades them into settlement, and no fuzzy score will ever
be an input to money movement. Nothing here governs catalogue *content* —
seeds, imports, edge economics and capture resistance are
`catalogue-bootstrap.md` and T6's register. And upstream ships on its own
schedule: a fired tripwire is an obligation on loopmarket to ask with
evidence, never a commitment by ontodag to build — which is why every
"meanwhile" in §7 must be livable indefinitely, and this document must
stay honest if one of them becomes the permanent answer.
