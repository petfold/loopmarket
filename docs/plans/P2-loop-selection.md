# loopmarket — loop selection

Status: design, 2026-08-07. Decided here: the complexity boundary
(divisible legs are a flow LP, indivisible legs a bounded-cycle packing
ILP); exact winner determination for small beats with the deterministic
greedy as fallback; a failure-aware expected-settled-surplus objective;
chains admitted receive-before-give only until the bond fabric exists;
pre-commit netting under maker-declared tolerances, one netting domain per
beat; lexicographic tie-breaking extending U6. Open here: chain atomicity
across beats; failure-prior cold start and its wash-loop interaction; the
mixed divisible/indivisible decomposition; tolerance semantics under U9.

This document names the optimization problem P0 deliberately dodged:
choosing *which set* of loops settles in a beat, not finding *a* loop.
Companions: `P2-batch-auction.md` (beat mechanics, sealed bids, scoring,
the reserve bid this document preconditions), `P2-settlement-pricing.md`
(rates inside the selected loops), `P3-guarantee-coupling.md` (the bonds
that unlock bridge donors), `P1-federated-book.md` (the per-maker books
whose merge feeds a beat), and `THREATS.md` (T1/T2/T3/T8 all touch
selection). ARCHITECTURE.md §7 records the arithmetic this builds on.

## 1. Selection is packing, not search

The baseline (`graph.py`) answers "does a profitable loop exist?" —
Bellman–Ford, then greedy disjoint extraction. The P2 question is
different: given a beat's proposals — many loops, overlapping in offers —
pick the feasible subset that maximizes what actually settles. Greedy
extraction can strictly block better packings: one high-surplus loop can
consume the offer two smaller loops needed. The clearing literature is
unambiguous that this is a packing problem, and Anoma's resource model is
its formal validation from the intent side: each intent declares resources
consumed and produced, a valid match balances them, and their canonical
example is a three-party BTC/ETH/DOT loop with no common medium of
exchange (Anoma whitepaper). A loopmarket loop is exactly a balanced set
of consumed and produced offer-resources; a beat is a set of such sets,
disjoint in offers.

## 2. The complexity boundary: flow where divisible, packing where not

Divisibility is what buys polynomiality. The two regimes:

| legs                  | problem           | complexity | precedent    |
|-----------------------|-------------------|------------|--------------|
| divisible, same unit  | min-cost flow LP  | polynomial | MTCS/Cycles  |
| indivisible, cap L≥3  | cycle packing ILP | NP-hard    | kidney exch. |

The Cycles protocol ("Cycles Protocol: A Peer-to-Peer Electronic Clearing
System", arXiv:2507.22309) clears obligation graphs with Multilateral
Trade Credit Set-off: a min-cost max-flow, polynomial precisely because
obligations are divisible flows in one denomination; the cleared quantity
is bounded by Net Internal Debt, and the paper concedes the optimum is
not unique (tie-breaking left to governance — we do not punt; §8). Kidney
exchange is the other side: maximum-weight vertex-disjoint cycle packing,
NP-hard for cycle cap L≥3 (Abraham, Blum & Sandholm, EC'07, "Clearing
algorithms for barter exchange markets"), whose cycle formulation — one
binary variable per feasible cycle, solved by branch-and-price / column
generation — cleared ~10,000-pair instances on 2007 hardware.

loopmarket's books are mixed: divisible legs (grain, compute, currency)
and indivisible ones (a cello, a truck-day). Decision (decided 2026-08,
lands with P2): route each beat's divisible-only subgraph through the
flow LP and legs touching any indivisible offer through the packing ILP;
the exact decomposition is a registered open problem below. Cycles'
intent taxonomy is the reserved vocabulary for partial fills: of its four
settlement modes (set-off, assignment, overdraft, assumption), loopmarket
has only the set-off analogue; assignment and overdraft are the named
partial-fill and credit-extension hooks — and an overdraft is a bridge
donor by another name (§5).

## 3. Two runs of one formulation, at two trust levels

The protocol never needs to solve an NP-hard problem; solvers do. The
same packing formulation runs twice per beat. Solver-side (private,
unrestricted): each solver packs its candidates however it likes — ILP,
heuristics, learned generators; nothing it does is trusted, so nothing is
restricted (U3). Beat-side (normative, deterministic): winner
determination scores the *submitted* packings — feasibility, fairness
filter (`P2-batch-auction.md`), objective value, deterministic selection.
Scoring a submitted solution is polynomial; only finding the optimum is
hard.

Exactness is affordable where it matters: ~94% of CoW's production
batches have ≤3 orders (arXiv:2408.12225) — combinatorial interaction is
sparse. So the beat also runs the exact packing itself when the instance
is small (decided 2026-08, lands with P2): below a pinned instance-size
threshold N\*, winner determination solves the ILP exactly; above it, it
falls back to the deterministic greedy (the baseline's disjoint
extraction over the failure-aware objective). The fallback trigger is a
function of instance size, **never wall-clock** — a timeout diverges
across replicas and breaks U6's replication story. The baseline's output
is also the beat's reserve bid; §6 preconditions that promotion.

## 4. The failure-aware objective

Committed matches die between commitment and execution. The kidney
numbers are brutal: in UNOS 2010–2012 data, 93% of algorithmically
selected transplants did not proceed — 44% direct failures cascading into
the other 49% because one dead leg kills its whole cycle (Dickerson,
Procaccia & Sandholm, EC'13 / Management Science 2019; modeled
edge-failure probability ~70%). Their fix — maximize *expected*
transplants under per-edge failure priors — transfers directly:
loopmarket's stale-snapshot → settle-time re-verification gap has the
same structure. An offer can be filled by an earlier beat, expire
mid-flight, be withdrawn by tombstone (`P1-federated-book.md`), or fail
re-verification after a root moves. The objective (decided 2026-08, lands
with P2):

    score(S) = Σ_{L ∈ S}  q(L) · log Π_{legs of L} r,
    q(L) = Π_{offers o ∈ L} (1 − p_o)

where p_o is offer o's failure-to-settle prior. Both factors are
dimensionless — log-surplus is a product of ratios, priors are unitless —
so the score honors U14 ("numeraire-free scoring") by construction; no
token amount or external price enters. Three consequences:

- **Short loops win endogenously.** q(L) decays geometrically in length,
  reproducing kidney exchange's short-cycle preference without a hard
  cap. Kidney caps cycles at 3 for *simultaneity logistics* (a 3-cycle is
  six simultaneous operating rooms), not computation; Roth–Sönmez–Ünver
  (AER 2007) showed 2- and 3-cycles capture most of the welfare. A length
  cap is kept as belt-and-braces — it also bounds cycle enumeration — and
  thickness argues the same way: a k-loop needs a k-way coincidence of
  wants (Roth, "What Have We Learned from Market Design?", Economic
  Journal 2008).
- **Priors obey U12** ("reward/reputation statistics count settled
  fee-paid loops only"). Failure priors are statistics, and priors
  learned from free or unsettled activity are a wash-loop pollution
  surface (T1, T2, T8): sybils could farm clean histories to bias
  selection toward their offers. Until U12-compliant data exists, the
  prior is uninformative and the objective degrades to length-penalized
  log-surplus (gate G3).
- **Priors rank; settlement re-verifies.** p_o never enters U3's checks.
  And p_o prices failure to *settle*, not failure to *perform* —
  performance risk is P3's risk-priced routing
  (`P3-guarantee-coupling.md`).

## 5. Chains alongside cycles, and who may give first

Chains break the length ceiling reliability imposes on cycles. NEAD
chains (Rees et al., NEJM 2009; Ashlagi et al., AJT 2011) execute
non-simultaneously with every pair *receiving before it gives*: a
reneging bridge donor merely truncates the chain — nobody who already
gave is left unpaid — so chains run to 30+ transplants, and long chains
add many matches in sensitized pools (Ashlagi–Gamarnik–Rees–Roth, "The
Need for (Long) Chains in Kidney Exchange", NBER w18202; Anderson–
Ashlagi–Gamarnik–Roth, PNAS 2015, prize-collecting TSP).

The formulation to adopt when chains land is **PICEF** — the
position-indexed chain-edge formulation (Dickerson, Manlove, Plaut,
Sandholm & Trimble, EC'16, arXiv:1606.01623). Naming discipline: PICEF is
not the cycle-packing ILP — that is Abraham–Blum–Sandholm's cycle
formulation. PICEF keeps cycles as exponentially many binary variables
(column generation) and adds chains as *polynomially many*
position-indexed edge variables — chains are the cheap part of the ILP.

Why chains at all: liquidity. In the Cycles data (1.28M Italian invoices,
760k firms, Dec 2020), pure cycles clear ~9.5% of debt; external
liquidity worth 10% of total debt clears ~50%; 20% clears ~70%
(arXiv:2507.22309, Fig. 10). A chain is how a liquidity injection (a
Cycles Tender; a bridge offer, `adoption-and-thickness.md`) propagates
through makers whose wants don't close into a cycle.

The rule (decided 2026-08; receive-before-give chains land with P2,
bonded bridge donors with P3): **a chain leg is admissible only if its
maker receives before giving.** Any leg giving value ahead of its
counterleg — the chain head extending real goods, services or external
assets first — is a **bridge donor** and requires a factbond bond sized
per factbond's doctrine (adjudication-cost floor plus reliance term —
`P3-guarantee-coupling.md`, `factbond/docs/plans/loopmarket-coupling.md`).
Kidney chains run unbonded because the altruistic head expects nothing
back; a loopmarket head expects compensation, so renege against it is
theft, not truncation. Until P3, chains are confined to what one commit
settles atomically — head's give and its compensation under one root —
which collapses them into cycles-with-a-liquidity-leg, expressible today.

The genuinely unresolved part is **chain atomicity across beats**: a
receive-before-give chain executes segments in different commits, and the
book's atomicity guarantee — all fills of a loop under one root, and
U11's "no partially-filled loop survives a merge" — has no chain analogue
yet. A chain record type with per-segment atomic fills and sanctioned
truncation is the likely shape; a registered open problem, not a decision.

## 6. The recall-gap defect: fix or document, required

Two defects in the baseline (`graph.py`) become load-bearing the moment
it is promoted to the beat's permanent reserve bid
(`P2-batch-auction.md`): a reserve bid with silent recall gaps weakens
the collusion defense it exists to provide (T3) — colluding solvers can
withhold exactly the loops the reserve provably cannot see.

- **Best-rate reduction loses feasible loops.**
  `ExchangeGraph.from_matches` keeps one edge per (giver, receiver) — the
  highest rate. A discarded lower-rate parallel edge can pair a
  *different* ask/bid of the same nodes whose unit prices pass the
  per-node feasibility floor where the best-rate pairing fails: complete
  for the product test, incomplete for feasibility. Loops that would
  settle are silently invisible.
- **Post-hoc `min_surplus` masks qualifying cycles.**
  `find_profitable_loop` tests the threshold only on the one cycle
  Bellman–Ford happened to certify; a below-threshold negative cycle
  returns `None` while an above-threshold one exists in the same graph —
  and the greedy extractor stops at the first `None`, terminating the
  whole extraction. (A stale in-code comment about folding `min_surplus`
  into edge weights was never implemented.)

Requirement (gate G1): **fix or document before the reserve-bid
promotion.** Candidate fixes, none yet chosen: keep the k best parallel
edges per pair (multigraph Bellman–Ford); partition parallel edges into
feasibility classes and search per class; iterate past sub-threshold
cycles by removing certified-cycle edges instead of returning `None`. The
document-only fallback — exact characterization of the book shapes where
the baseline is recall-complete, enforced by a property test — still
leaves the reserve weaker, so fixing is the default. **Owner ruling at
the item-3 sign-off (2026-08-21): the fix is the requirement — the
document-only fallback is withdrawn as a path to the promotion.
Recall-characterization property tests remain valuable as evidence the
fix worked; they do not substitute for it.**

## 7. Pre-commit compression: netting the accepted set

A beat's accepted loops form an obligation multigraph over (maker,
personal-token) pairs, and overlapping loops carry offsetting legs.
D'Errico & Roukny ("Compressing Over-the-Counter Markets",
arXiv:1705.07155, Operations Research 2021): excess = gross notional
minus the minimum gross supporting all net positions; excess is exactly
the flow circulating on cycles; conservative compression (reduce existing
bilateral legs only) is a network-flow computation; non-conservative
compression attains the minimum gross ½·Σ|net positions|. The production
evidence is triReduce (TriOptima/OSTTRA): >$750T cumulative notional
eliminated, and the operative trick is that **participants declare
tolerances** — tiny permitted net drift unlocks far more elimination than
exact-net preservation. Adopted (decided 2026-08, lands with P2):

- **Compress after verification, before commit.** U3 re-derives every leg
  of every accepted loop from the gross structure; compression is then a
  pure, deterministic transform of the accepted set — offsetting legs
  between the same parties cancel, fills are written net, and any
  verifier recomputes the compressed fill set byte-identically (gate G5).
  It saves fill records, Swarm writes and postage, and shrinks the
  arithmetic surface settlement gates; it creates no surplus.
- **Maker-declared tolerances, explicit dust.** Residual imbalance within
  a maker's declared per-beat tolerance is recorded explicitly in the
  fill record, never implicit. The exact semantics — Thing-side vs
  token-side drift, and where dust goes without violating U9 ("exact
  rationals in everything settlement re-verifies") or U13's budget
  balance — is an open problem owned by `P2-settlement-pricing.md`.
- **One netting domain per beat.** Duffie & Zhu (Rev. Asset Pricing
  Studies 2011): fragmenting clearing across domains destroys netting —
  every domain that cannot net against the others costs collateral. When
  per-maker books land (`P1-federated-book.md`), the *books* federate but
  the *beat* does not: all loops settling in a beat net in one merged
  domain and commit under one root. One-commit atomicity already provides
  the mechanism; the batch auction must exploit it deliberately.
- **Precedence.** Uniform directional clearing binds: the same (ask, bid)
  pair in multiple winning loops settles at one rate, and compression
  approximates the equal log-surplus split target — the residual tension
  is registered in `P2-settlement-pricing.md`.

## 8. Determinism: lexicographic tie-breaks, extending U6

MTCS leaves optimum non-uniqueness "to governance"; loopmarket does not.
U6's discipline — same book, same loop, every replica — extends to
beat-side selection (decided 2026-08, lands with P2): among feasible
solutions of equal score, the winner is chosen by a total lexicographic
order: (1) higher score; (2) fewer total legs; (3) smaller sorted tuple
of loop identifiers; (4) smaller canonical encoding of the full leg
sequence. Rule (4) exists because `loop_id` today hashes the sorted
offer-id set and is pairing-insensitive — two distinct leg-pairings of
the same offers collide (the loop_id leg-pairing question,
ARCHITECTURE.md §2 update note); the tie-break keys on the actual leg
sequence until that is resolved. Every input derives from the beat's
pinned roots (U10), so any replica reproduces the winner from the sealed
proposals alone — which also makes the reserve bid auditable for free,
where CoW needed an off-chain EBBO monitoring apparatus.

## 9. Per-participant inclusion proofs as legal artifacts

Cycles attaches per-party cryptographic inclusion proofs to its atomic
set-off records for legal purposes (arXiv:2507.22309) — an obligation
discharged in a batch must be provable by the party alone. loopmarket
adopts the same discipline (decided 2026-08, lands with P2): each
participant of a settled loop can extract, from the settled root, an
inclusion proof of their `fill/` record plus the `loop/` record and the
pin tuple per U10 ("load-bearing pins {book_root, ontology_root,
REGISTRY_VERSION, CONTRACT_VERSION}, verifiers refuse on mismatch or
absence"). The proof machinery is `proof-fabric.md`'s — the same
canonical-trie inclusion/absence proofs as the on-chain settlement path;
selection merely guarantees the artifact exists per participant.

## Gates

- **G1 — recall gap resolved.** Fixes for best-rate reduction and
  `min_surplus` masking land, or recall-complete book shapes are exactly
  characterized; either way a property test compares baseline extraction
  against exhaustive small-instance packing over randomized books, with
  zero silent losses (or losses only outside the characterized shapes).
  Blocks: the reserve-bid promotion in `P2-batch-auction.md`.
- **G2 — exact-selection threshold pinned.** N\* measured on the shared
  simulation harness (`factbond/docs/plans/phase0-simulation.md`): the
  largest instance where exact winner determination completes within 10%
  of the beat budget at the 99th percentile. Fallback triggers on
  instance size, never wall-clock. Blocks: exact selection going
  normative.
- **G3 — failure priors go live.** p_o computed only from U12-compliant
  statistics (settled fee-paid loops), above a pinned minimum sample
  count per offer class; below it the uninformative prior applies.
  Blocks: any prior-weighted selection. Unblocked by fees landing
  (`P2-batch-auction.md`) plus the statistics pipeline.
- **G4 — chains beyond one commit.** Ship only after (a) factbond
  Phase-0 green, (b) bridge-donor bonds exist
  (`P3-guarantee-coupling.md`), (c) a chain record type extending U11 to
  sanctioned truncation is designed and reviewed.
- **G5 — compression is a replayable transform.** Property test: the
  compressed fill set is a deterministic pure function of the accepted
  loop set; independent verifiers recompute it byte-identically; every
  maker's net drift ≤ declared tolerance; dust explicit in fill records.
  Blocks: netting entering the settlement path.

## Open problems

**Chain atomicity across beats.** One-commit atomicity and U11 have no
chain analogue; a chain record with per-segment atomic fills and
sanctioned truncation must ensure a merge never yields a half-executed
segment and a truncated chain is distinguishable from a broken one. Work
package: P2/P3 boundary, this document with `P3-guarantee-coupling.md`.

**Failure-prior cold start and wash-loop interaction.** Before loss data
exists the prior is uninformative, and the data-gathering period is
exactly when prior-farming (T1, T2, T8) is cheapest; the interaction of
prior updates with U12 needs an explicit update rule with an adversarial
analysis. Work package: `P2-batch-auction.md` with `THREATS.md`.

**The mixed divisible/indivisible decomposition.** Routing divisible legs
to the flow LP and indivisible legs to the packing ILP is decided; how
the two share offers appearing in both regimes — and whether the combined
solution stays within the fairness filter — is not worked out. Work
package: P2, this document.

**Tolerance semantics under U9/U13.** What a net-drift tolerance means on
a Thing leg vs a token leg, in exact rationals, and where forgiven dust
goes without opening a wash-loop subsidy channel. Work package:
`P2-settlement-pricing.md`.

**Compression vs uniform directional clearing.** Netting perturbs the
per-leg quantities the equal log-surplus split priced; the precedence
rule is decided, the residual gap unquantified. Work package:
`P2-settlement-pricing.md`; named here because compression is this
document's mechanism.

- **Price schedules in offers** (far roadmap — owner-added 2026-08-21;
  lands, if ever, with a post-P4 record bump). Today an offer quotes one
  price; the generalization is a *static, immutable schedule*: over
  quantity ("1 box at 50, up to 5 at 45 each" — a supply curve, most of
  what auction theory wants from a bidder), and/or over validity time
  (price as a function of beat index — a pre-committed Dutch or English
  auction inside one offer, which cannot double-fill the way a ladder of
  short-validity offers can). Both stay U2-compatible values solved
  against pinned roots; for divisible legs the flow LP extends to
  piecewise-linear convex edge costs and stays polynomial; indivisible
  legs plus curves is genuine combinatorial-auction territory, gated on
  thin verticals demonstrating that point-quotes leave surplus
  undiscovered. The doctrine that frames all of this, decided in the
  2026-08-21 discussion: **dynamic pricing quantizes to the beat** —
  repricing across beats (tombstone + repost, or a maker agent running
  any adaptive strategy) is free today; *continuous* in-protocol price
  dynamics stay rejected, because static edge weights are what
  Bellman–Ford and settlement re-verification stand on, and discrete
  batches exist precisely to convert speed races into price competition
  (Budish–Cramton–Shim; the sealed-proposal design would also leak to
  probing if quotes reacted live).

## What this document does not promise

- **Selection optimizes a model, not the world.** The failure-aware score
  maximizes expected *settled* surplus under priors; settlement certifies
  re-verification, not delivery, and p_o says nothing about whether a
  cello actually arrives. Failure priors are weights in an objective —
  prices, not probabilities of real-world performance.
- **Exactness is per-beat.** The exact ILP claims optimality only within
  one beat's sealed proposals; above N\* the greedy fallback claims only
  feasibility, determinism, and the reserve-bid floor.
- **Compression creates no surplus.** Netting saves writes, postage and
  arithmetic surface; every economic quantity it touches was already
  verified gross.
- **Chains bound harm, not disappointment.** Receive-before-give
  guarantees nobody gives unpaid; a truncated chain's tail still receives
  nothing it hoped for, and no bond changes that before P3.
- **The reserve bid is only as honest as G1.** Until the recall gap is
  fixed or exactly characterized, "the reserve saw no better solution" is
  a statement about the baseline's blind spots, not about the book.
