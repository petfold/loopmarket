# loopmarket — settlement pricing (P2)

Status: design, 2026-08-07. Decided here: the equal log-surplus split as the
pricing rule (architect-derived, provenance marked below); the precedence of
uniform directional clearing over the per-loop split; the exact-rational
migration (planned invariant **U9**); the divisible/indivisible boundary at
pricing time. Open here: the uniqueness proof for the split; the residual
tension between uniform clearing and the equal split; quantified shading
behaviour.

This document specifies how settlement chooses actual prices inside each
[ask, bid] interval and distributes loop surplus — the "real settlement
pricing" that `../../CLAUDE.md` known simplification #1 and
`../../ARCHITECTURE.md` §7 reserve for P2. Companions: `P2-batch-auction.md`
(the beat, the fairness floor, solver rewards, fees), `P2-loop-selection.md`
(which loops win, netting/compression), `proof-fabric.md` (what an on-chain
verifier re-checks), `THREATS.md` (register; T1 and T2 touch pricing),
`ontodag-coupling.md` (unit families), and
`factbond/docs/plans/phase0-simulation.md` (the shared harness where this
rule's incentive claims get tested).

## 1. The problem: Π > 1 proves surplus; prices realize it

`graph.py` proves a loop profitable when the product of its match rates
exceeds 1: around a cycle, Π rᵢ telescopes into Π (node's bid price / node's
own ask price) = S. That is an existence proof, not a settlement. To settle,
every node i must sell xᵢ units of its thing at some price uᵢ ≥ aᵢ (its ask,
in its own token) and buy xᵢ₋₁ units of the previous thing at some price
vᵢ ≤ bᵢ (its bid, in its own token), such that its personal-token inflow and
outflow cancel exactly: xᵢ·uᵢ = xᵢ₋₁·vᵢ. Tokens exist only for the instant
the loop passes through the maker (`../../ARCHITECTURE.md` §2); the
cancellation constraint is that fact written as arithmetic.

What pricing can and cannot choose is fixed by a conservation identity.
Define node i's surplus factor σᵢ = (uᵢ/aᵢ)·(bᵢ/vᵢ) — how much its settled
prices beat its stated bounds, dimensionless in its own token. Then

    Π σᵢ = Π (bᵢ/aᵢ) · Π (uᵢ/vᵢ) = S · Π (xᵢ₋₁/xᵢ) = S,

because the cancellation constraints make Π (uᵢ/vᵢ) telescope to 1. Total
log-surplus Σ log σᵢ = log S is conserved no matter what prices are chosen;
a pricing rule chooses only the *split*. Equivalently, the settled per-leg
exchange rates ρᵢ = vᵢ₊₁/uᵢ always satisfy Π ρᵢ = 1: settlement extracts the
entire negative cycle, and the settled book is arbitrage-free at its own
prices by construction. In −log terms, the rule distributes the cycle's
weight −log S across its participants. Everything distributed is drawn from
inside the loop that produced it — the self-funded property planned
invariant **U13** ("wash-loop budget-balance by construction, fees
external-asset only") demands, and the reason the T1 rebate-farming channel
has nothing external to farm (`THREATS.md` T1). Per-leg fees in an external
asset are charged alongside and are out of scope here; `P2-batch-auction.md`
owns them.

## 2. The rule: equal log-surplus split

**Every node in an n-loop receives the same surplus factor S^(1/n).** In leg
terms: each leg settles at its match rate deflated by the geometric mean of
the loop's rates, ρᵢ = rᵢ / S^(1/n), which makes Π ρᵢ = 1 automatically. In
−log terms: add the mean cycle weight (log S)/n to every edge, so the
settled cycle weighs exactly zero. The rule is closed-form, deterministic
(same accepted loops ⇒ same prices on every replica — U6's discipline
extended to prices), numeraire-free (planned invariant **U14**,
"numeraire-free scoring": every σᵢ is a ratio in one node's own token, so
re-denominating any personal token changes nothing), and strictly positive
throughout (U5 untouched).

**Provenance, marked.** This rule is architect-derived, not literature. The
closest running relatives price differently: CoW converts everything to a
native-token numeraire (which loopmarket refuses — see §4 of
`P2-batch-auction.md`); Cycles/MTCS (arXiv:2507.22309) clears divisible
obligations in a single denomination, where the split question does not
arise. **The uniqueness claim — that the equal split is the only rule that
is symmetric across nodes and invariant under re-denomination of personal
tokens — is stated here as to-be-proven, not proven.** The honest difficulty:
each node's own spread sᵢ = bᵢ/aᵢ is itself re-denomination-invariant, so
"keep your own spread" (σᵢ = sᵢ) passes both stated axioms too. The proof
must find the axiom that separates them — a candidate is independence of the
split from *stated* spreads given S (the Roth-safety direction, §7) — or the
axiom set must be revised. Gate G1 holds the rule at working-rule status
until then; accepting it as the working rule is discussion-agenda item #9 of
the approved plan.

**Rational realization** (decided 2026-08, lands with P2). S^(1/n) is
irrational for almost all rational S, and **U9** ("exact rationals in
everything settlement re-verifies") forbids settling on an irrational
target. The implemented rule therefore targets the equal split through a
deterministic fixed-precision integer n-th root: compute σ̂ ≤ S^(1/n) as a
reduced rational at a fixed power-of-two precision, assign σ̂ to n−1 nodes in
deterministic order, and give the residual factor S/σ̂ⁿ⁻¹ to the last node,
so conservation Π σᵢ = S holds *exactly* in rationals and the residual
node's advantage is bounded by the chosen precision. The rounding scheme is
part of the normative rule: settlement re-verification recomputes it
byte-for-byte, never checks "approximately equal".

## 3. Worked triangle, exact rationals

Three makers, three divisible things, capacity 1 each, prices in each
maker's own token. C posts zero spread on purpose.

| maker | sells | ask a | buys | bid b | spread s = b/a |
|-------|-------|-------|------|-------|----------------|
| A     | X     | 20 A  | Z    | 27 A  | 27/20          |
| B     | Y     | 25 B  | X    | 32 B  | 32/25          |
| C     | Z     | 40 C  | Y    | 40 C  | 1              |

Match rates: r₁ (X, A→B) = 32/20 = 8/5; r₂ (Y, B→C) = 40/25 = 8/5;
r₃ (Z, C→A) = 27/40. Product S = 216/125, so S^(1/3) = 6/5 exactly (the
example is engineered to need no rounding; §2's scheme covers the general
case). Settled leg rates ρᵢ = rᵢ·(5/6): 4/3, 4/3, 9/16 — product exactly 1.
Quantities follow from cancellation, xᵢ/xᵢ₋₁ = sᵢ/S^(1/n), normalized so the
largest fill hits capacity: A sells 15/16 X, B sells 1 Y, C sells 5/6 Z.
Bookkeeping under the sell-at-ask convention (uᵢ = aᵢ, vᵢ = bᵢ·5/6):

| node | sells        | inflow | buys              | outflow | factor |
|------|--------------|--------|-------------------|---------|--------|
| A    | 15/16 X @ 20 | 75/4 A | 5/6 Z @ 45/2      | 75/4 A  | 6/5    |
| B    | 1 Y @ 25     | 25 B   | 15/16 X @ 80/3    | 25 B    | 6/5    |
| C    | 5/6 Z @ 40   | 100/3 C| 1 Y @ 100/3       | 100/3 C | 6/5    |

Every token book cancels exactly; every number is a reduced rational; every
node's settled prices beat its stated bounds by exactly 6/5 — including C,
whose own spread contributed nothing. The redistribution is paid for by
partial fills (A fills 15/16, C fills 5/6): divisibility is the currency of
the equal split. Which side of a leg carries the gain in the recorded prices
(sell-at-ask above, or buy-at-bid symmetrically) is bookkeeping only — the
tokens cancel either way; the convention is fixed once so records are
canonical.

## 4. Rejected alternatives

- **Shapley-style division.** Distributing surplus by marginal contribution
  needs the coalition function's values in one comparable unit. Node
  surpluses are denominated in n different personal tokens whose only
  exchange rates are the ones this very rule is choosing — the construction
  is circular unless an external numeraire is imported, which loopmarket
  refuses (**U14**; CoW's native-price manipulation surface without CoW's
  liquid anchors, per the solver-auctions research). It is also not
  scale-invariant across personal numeraires and exponential in coalition
  enumeration. Rejected.
- **Ask-side-take-all** (settle every leg at the bid; symmetrically,
  bid-side-take-all). One side's stated bound is extracted in full: a maker
  who truthfully reveals its reservation pays or receives exactly it, and
  learns to shade next time. This is precisely the failure Roth's market-
  design safety criterion names (Roth, "What Have We Learned from Market
  Design?", Economic Journal 2008 / NBER w13530): a rule that extracts
  more surplus from more-truthful offers teaches makers to shade, thinning
  the market — the research note's gloss, not Roth's sentence. Roth-unsafe;
  rejected.
- **Keep-your-own-spread** (σᵢ = sᵢ; each node trades at one own-token
  price qᵢ ∈ [aᵢ, bᵢ]). Feasible only when every sᵢ ≥ 1 — it is
  `per_node_ok` promoted to a pricing rule, and it refuses exactly the
  loops divisibility is supposed to unlock (S > 1 with some node's own
  spread below 1). Kept as what indivisible legs force (§6), rejected as
  the general rule.

## 5. Precedence: uniform directional clearing binds

CoW's fair combinatorial auction (CIP-67, live June 2025) requires uniform
directional clearing prices — the same directed token pair settles at one
price within a winning outcome — because differential pricing of one pair
across batched orders is exactly the surplus-shifting CoW previously had to
police as a slashable offence ("local token conservation"). The loopmarket
analog, adopted here as the **precedence rule**: when the same directed
(ask, bid) pair is consumed by more than one winning loop in a beat
(divisible offers split across loops), that pair settles at **one rate** for
the whole beat. One offer, one directed counterparty, one price — the
structural block on shifting surplus between loops that share an offer, and
on a solver constructing sibling loops to move value toward its own legs
(T1-adjacent; see `THREATS.md`).

The equal split cannot always survive this: two loops sharing an edge
generally want two different deflators S₁^(1/n₁) ≠ S₂^(1/n₂). The rule of
precedence is: **uniform directional clearing binds; the equal log-surplus
split is the target that the netting/compression step approximates** —
`P2-loop-selection.md` §7 merges loops sharing offers into one netting
domain per beat, and the approximation objective this document imposes on
that step — choose the single rate per directed pair that minimizes
deviation from each loop's equal-split target, subject to every offer's
bounds and the fairness floor — is specified here and not yet designed in
detail. How large the residual deviation can get, and whether the
approximation objective itself is gameable, is a registered open problem
(below), not a solved corner.

## 6. Divisible and indivisible legs at pricing time

**Divisible legs scale to cancel exactly.** The quantity ratios
xᵢ/xᵢ₋₁ = sᵢ/S^(1/n) are forced by the split; normalization lifts the
largest fill to its capacity. A node whose own spread is below 1 still
settles at prices beating its bounds by S^(1/n); the quantities absorb the
difference. This is the regime where the equal split is fully realized.

**Indivisible legs are pinned.** With unit quantities, cancellation forces
uᵢ = vᵢ: node i trades at a single own-token price qᵢ, feasible iff
aᵢ ≤ qᵢ ≤ bᵢ, i.e. iff sᵢ ≥ 1 — `per_node_ok` *is* individual rationality
for indivisible loops, and each node's factor is pinned at its own sᵢ
regardless of q. No price choice can redistribute anything. Indivisible
legs therefore do not get the equal split; they must clear the **fairness
floor** of `P2-batch-auction.md` — each offer does at least as well as its
best standalone reference outcome — which subsumes `per_node_ok` as policy
while the arithmetic fact stays true (the plan's marking: kept as
arithmetic fact, superseded as policy). Mixed loops price their divisible
degrees of freedom toward the equal-split target under the indivisible
legs' pinned constraints.

One code-level alignment (lands with P2): `check_match` today consults only
the ask's divisibility while `Loop.all_divisible` requires both sides; a leg
is scalable at pricing time only if *both* sides are divisible, and the
gates must agree.

## 7. Incentive properties, honestly stated

Full strategy-proofness is unavailable: by the Myerson–Satterthwaite
impossibility, no bilateral-trade mechanism is simultaneously efficient,
budget-balanced, individually rational and incentive-compatible — and a
loop is a cycle of bilateral trades settled budget-balanced (§1's
conservation identity is budget balance). So this document claims only
**bounded manipulability, and that claim is an inference, not a theorem.**
The leg-local arithmetic behind the inference: a node that shades one bound
by factor φ (ask up, or bid down) shrinks S by φ, hence everyone's share by
φ^(1/n), while pocketing the wedge φ against its true bound — a net gain of
φ^((n−1)/n), *if* the loop still forms at the shaded bound, the match still
exists, and the fairness floor still passes. Shading is therefore never
free: it bears 1/n of its own damage, risks pricing the maker out of loop
formation entirely, and shrinks the maker's own reference outcome under the
floor. What the rule does guarantee: truthful bounds are never extracted in
full (the ask-side-take-all failure), settled prices always beat stated
bounds, and the fairness floor (`P2-batch-auction.md`) is the backstop — no
participant ever does worse than its standalone reference, whatever pricing
games others play. That is the Roth-safety posture: truth-telling is not
punished, even though it is not perfectly rewarded.

Quantifying the residual — equilibrium shading levels, thinning effects,
whether φ^((n−1)/n) survives loop-formation risk at realistic book densities
— is assigned to the shared agent-based harness of
`factbond/docs/plans/phase0-simulation.md`, which runs loopmarket
pricing-shading experiments alongside factbond's planted-error experiments
(gate G2). The efficiency cost of fairness — how much total surplus the
floor plus equal split forgo against an unconstrained max-surplus packing —
must be measured there too (gate G3); the empirical price-of-fairness line
that followed failure-aware kidney exchange (the Dickerson–Procaccia–
Sandholm Management Science 2019 lineage, via the clearing research) is the
methodological template, and we do not import its numbers. One further
pressure, registered rather than solved: the equal split hands out per-node
shares, so splitting one economic actor into two chained maker identities
claims two shares — a T2-shaped sybil pressure on n (see `THREATS.md` T2;
per-leg external-asset fees and U1's distinct-makers rule are the current
frictions).

## 8. Exact arithmetic — the U9 migration

Planned invariant **U9**: "exact rationals in everything settlement
re-verifies." Today everything is float — quantities, amounts,
`Match.rate`, `unit_price = tokens.amount / thing.qty`, surplus thresholds,
with 1e-9/1e-12/1e-15 epsilons scattered through the gates — which cannot
survive deterministic re-verification by a Gnosis contract or byte-identical
cross-replica audits (loopmarket-code research: the float debt is silent but
total). The migration (decided 2026-08, lands with P2):

- **Reduced rationals via ontodag unit families.** ontodag's D9 rational
  anchoring (registry v3, 2026-08-01) already stores canonical values as
  reduced rationals of the anchor unit and compares by cross-multiplication,
  no floats ever; the fiat pack renders `0.99USD` as `99/100USD`.
  Offer quantities and token amounts adopt the same representation;
  personal-token denominations ship as a loopmarket unit pack
  (`ontodag-coupling.md` owns the coupling, including the rule that bridged
  assets are edges with rates, never identities — BZZ vs xBZZ, USD vs
  USDC). The interpreter registry version participates in canonical
  comparison, which is one reason the pin tuple grows to planned invariant
  **U10** {book_root, ontology_root, REGISTRY_VERSION, CONTRACT_VERSION}
  (offer-side pins land with the v2 bump, enforcement with P2;
  `proof-fabric.md` §3).
- **Floats solver-side only.** Bellman–Ford's w = −log r stays floating
  point: the −log weights are a search heuristic that ranks candidates,
  never truth. Settlement re-verifies Π rᵢ > 1 by exact cross-multiplied
  integer comparison, the split by the §2 rounding scheme, cancellation by
  rational equality — no epsilon anywhere on the settlement path. A solver
  whose float search proposes a loop that exact arithmetic rejects simply
  loses the proposal; U3 already assumes solvers are wrong.
- **Records.** `Match.rate` becomes a reduced rational, and fill records
  grow settled quantities (today `fill/` holds only `{"loop"}` — the
  `at` field was dropped 2026-08-20 for fill determinism) — originally
  slated for the offer/record v2 bump so ids never churn twice (decided
  2026-08). **Update 2026-08-20: the v2 bump landed without these** —
  the quantities recorded are the *settled* ones, which presuppose the
  pricing rule this document proposes (discussion agenda #9), and the
  rational representation waits on the unit-family design (see
  `ontodag-coupling.md`'s dated note). They ride the v3 bump with U9,
  before P2. Settled *prices* follow
  `P4-privacy.md` §5's format-freeze ruling: the per-leg price vector goes
  into private per-participant receipt envelopes, never public fill
  records; the public beat record carries per-directed-pair aggregates —
  which is exactly what §9's reference-rate note needs, and all it gets. Geometric gates (haversine disc intersection) are a separate
  exactness question: they are re-run by settlement but are booleans, not
  arithmetic the contract recomputes; their exact-rational option (ontodag's
  planar tangent-plane discs) and what the on-chain verifier actually
  re-checks belong to `proof-fabric.md`.

## 9. Settled rates as future reference rates (a note, not a commitment)

Uniform directional clearing leaves each beat with an audited list of
settled rates per directed pair, under a pinned root. Renegade's dark pool
is tractable precisely because it imports an external midpoint price and
reduces private matching to a boolean cross test instead of price formation
(privacy research). Loopmarket has no external midpoint — but its own
settled clearing rates are the native candidate for that role: a future
private-matching tier (`P4-privacy.md`, Tier 3) could peg to trailing
settled rates per category pair the way Renegade pegs to Binance. Recorded
here so the P2 record format keeps settled rates queryable per directed
pair; nothing else is promised.

## Gates

- **G1 — uniqueness or revision.** The symmetric + re-denomination-
  invariance uniqueness claim for the equal split is proven, or the axiom
  set is revised and the rule re-derived. Unblocked by: a written proof
  reviewed in this repo, plus owner sign-off on plan discussion item #9.
  Until then the split is a working rule; no on-chain contract hardcodes it.
- **G2 — shading experiments green.** The shared harness
  (`factbond/docs/plans/phase0-simulation.md`) runs maker-shading agent
  populations against this rule; go if equilibrium shading stays within the
  φ^((n−1)/n) leg-local bound and no thinning spiral appears across the
  swept parameter region. Owner: the Phase-0 simulation work package.
- **G3 — price of fairness measured.** Total-surplus cost of (fairness
  floor + equal split + uniform clearing) vs unconstrained max-surplus
  packing, measured on simulated and replayed books; the acceptance
  threshold is fixed before the first run, in the pre-registration style
  Phase-0 mandates. No launch of P2 pricing without the number.
- **G4 — exact-rational pipeline lands.** Rational `Match.rate`,
  rational settled prices/quantities in v2 records, epsilon-free settlement
  path, CI test proving no float enters anything settlement re-verifies
  (**U9** enforced by test, at which point U9 graduates into
  `../../CLAUDE.md` per the marking convention).
- **G5 — precedence approximation bounded.** The netting step's deviation
  from per-loop equal-split targets is instrumented and bounded (worst-case
  and realized), or shared-edge splitting is restricted until it is.
  Owner: this document (the approximation objective), implemented by the
  netting step of `P2-loop-selection.md` §7.

## Open problems

- **Uniqueness of the equal split.** The stated axioms do not yet separate
  S^(1/n) from σᵢ = sᵢ (§2); the separating axiom — plausibly independence
  from stated spreads, which is also the Roth-safety intuition — must be
  found and the proof written, or the rule loses its "unique" billing and
  keeps only its pragmatic ones (closed-form, deterministic, numeraire-
  free). Work package: P2 design, gate G1.
- **Uniform clearing vs equal split — the residual tension.** One rate per
  directed pair per beat conflicts with per-loop deflators whenever loops
  share an edge; the approximation objective, its worst case, and its
  gameability are unresolved (§5). Registered per the approved plan. Work
  package: P2, jointly with `P2-loop-selection.md`.
- **Shading and node-splitting quantification.** The bounded-manipulability
  inference (§7) needs empirical teeth: equilibrium shading levels, the
  interaction with the fairness floor, and the T2-shaped incentive to split
  one actor into multiple loop positions for extra S^(1/n) shares. Work
  package: factbond Phase-0 shared harness; threat accounting in
  `THREATS.md` (T2).
- **Rounding-scheme parameters.** Precision of the integer n-th root, the
  deterministic order that picks the residual node, and the bound on the
  residual node's advantage are implementation-normative and must be fixed
  in the P2 spec before any contract freezes them. Work package: P2, with
  `proof-fabric.md` for what the verifier recomputes.
- **Reference-rate governance.** If P4 ever pegs private matching to
  trailing settled rates (§9), those rates become a manipulation target
  (settle small loops to move the peg); scoping whether and how they may be
  consumed belongs to `P4-privacy.md` before anything consumes them. Work
  package: P4.

## What this document does not promise

- **Settlement certifies re-verification, not delivery.** The settled
  prices prove every leg re-derived under the pinned roots and every token
  book cancelled exactly; whether the cello arrives is the guarantee
  fabric's business (`P3-guarantee-coupling.md`), and certified ≠ true on
  every surface (factbond invariant **F7**).
- **The split is fairness of stated surplus, not of welfare.** S^(1/n)
  equalizes gains measured against *stated* bounds in each maker's *own*
  token; it makes no interpersonal welfare comparison and no claim that
  equal factors are equal utilities. There is no common numeraire here to
  even state such a claim in (**U14**).
- **Bounded manipulability is an inference.** Myerson–Satterthwaite
  guarantees a manipulation surface exists; §7's bound is leg-local
  arithmetic plus a backstop, pending G2's experiments — not an equilibrium
  theorem.
- **Settled rates are prices, not probabilities or values.** A beat's
  clearing rates are outputs of this mechanism under its constraints; they
  estimate nothing, and consuming them as reference truth (§9) is a P4
  decision not made here.
- **No new surplus.** The rule splits what Π rᵢ > 1 already proves; nothing
  here creates value, subsidizes loops, or rebates anything not drawn from
  inside the loop itself (**U13**).
