# loopmarket — the batch auction (P2)

Status: design, 2026-08-07. Decided here: fixed-cadence beats with a
cancellation cutoff pinning the book root; sealed proposals (Shutter on
Gnosis, commit-reveal fallback); numeraire-free scoring (U14); the CIP-67
fairness filter generalized from directed token pairs to cycles; exact-ILP
winner selection with a greedy fallback and a lexicographic tie-break
extending U6; marginal-contribution rewards capped by the solver's own
generated fees plus a weekly consistency pool; the deterministic baseline as
permanent reserve bid, *preconditioned* on the ExchangeGraph recall gap;
permissionless solver entry bonded through the factbond pool; per-leg
external-asset fees under the wash-loop inequality (U13). Open here: beat
length, fairness-filter gaming materiality, null-reference edge cases,
consistency-pool sybils, fee incidence. Everything below implies unbuilt
code (decided 2026-08, lands with P2); three moves await discussion-agenda
sign-off: `per_node_ok` superseded as policy (touches U3's checklist), the
baseline's promotion to reserve bid (changes U6's meaning), and introducing
fees at all.

This document specifies the **beat**: the per-interval sealed-proposal
auction replacing `MockSettlement`'s first-valid-wins — who may propose,
what a proposal is worth, who wins, what discovery earns, and why colluding
or self-dealing does not pay. It consumes two things it does not own:
`P2-loop-selection.md` owns the optimization inside winner selection
(packing, chains, failure-aware objective, the recall-gap defect gating §8);
`P2-settlement-pricing.md` owns what winning legs pay (equal log-surplus
split, uniform directional clearing). Threats T1/T3 live in full in
`THREATS.md`; solver-bond plumbing is `P3-guarantee-coupling.md` and
factbond's `../../../factbond/docs/plans/loopmarket-coupling.md`.

## 1. Why a beat at all

`MockSettlement` is first-valid-wins: whoever reaches settlement first with
a valid proposal takes the loop. That is Budish–Cramton–Shim's continuous
serial processing, whose equilibrium is known — a latency arms race, sniped
stale quotes, rents to speed rather than discovery; their remedy is
discrete-time uniform-price sealed-bid batch auctions at frequent intervals,
sealed bids essential (otherwise the batch recreates the race). Penumbra
runs the shape in production (per-block batches at a uniform clearing
price, identities shielded — its designed flow encryption is unshipped,
so amounts are revealed; `P4-privacy.md` §7); CoW Protocol is where the
incentive engineering got
tested at scale (~$3.7B/mo, arXiv:2408.12225), and this design adopts its
mechanism wherever loopmarket's structure permits.

The beat is explicitly *not* for thickness: dynamic-matching theory
(Ashlagi et al., arXiv:1301.3509; the Akbarpour–Li–Gharan JPE 2020 line)
finds batching gains modest unless the market is thin and agents patient —
thin verticals get deliberately longer pooled runs, an adoption decision
(`adoption-and-thickness.md`), not an auction one. Beats are short; they
exist for proposal competition, sealed submission, and deterministic
tie-breaking. The cutoff-calendar precedent is the clearing world: AJPES's
compulsory monthly multilateral set-off has run ~three decades on a fixed
cutoff-and-window discipline, and Cycles (arXiv:2507.22309) clears at
periodic epochs with a cancellation cutoff before the solve, mid-batch
intents rolling to the next epoch. Keep the discipline, shrink the period.

## 2. Beat mechanics

Four phases (decided 2026-08, lands with P2):

1. **Open.** Offers and withdrawal tombstones (`P1-federated-book.md`)
   accumulate as always.
2. **Cutoff.** The beat's book root is pinned. Every proposal must pin
   exactly the tuple of U10 — "load-bearing pins {book_root, ontology_root,
   REGISTRY_VERSION, CONTRACT_VERSION}, verifiers refuse on mismatch or
   absence." Offers and cancellations after cutoff roll to the next beat,
   Cycles-style; nothing cancels mid-solve, so a solver's snapshot (U4) and
   the verifier's book are the same object all beat.
3. **Solve.** Solvers submit sealed proposals (§3) until the deadline; the
   deterministic baseline's proposals are computed by every replica from
   the pinned root and enter the beat unconditionally.
4. **Reveal, filter, select, settle.** Proposals decrypt; the fairness
   filter (§5) discards; winner selection (§6) packs; settlement re-derives
   every winning leg from scratch (U3, unchanged) and commits all fills
   under one root. A hard settlement deadline follows CoW's convention
   (3 blocks on Gnosis in CoW's auctions); winning and missing it is §7's
   `missingScore` event and decays the solver's successRate standing.

## 3. Sealed proposals

A loop proposal is fully specified by offer ids and rates: once visible it
is free to copy, while discovering it cost real search — the free-riding
problem Paradigm's intent-risks analysis names for permissionless intent
pools (executors are disincentivized to gossip intents onward; "intents
disappear into the dark forest"). Production answers: CoW keeps bids
private to a trusted autopilot until close; UniswapX grants the winning
quoter a brief exclusive fill window; Penumbra shields identities (its
full flow encryption remains unshipped). Loopmarket has no
autopilot and wants none — one verifier, many solvers, no privileged
observer — so the answer is encryption. **Primary: Shutter threshold
encryption** — live on Gnosis since July 2024 (shutterized mempool), with
the Shutter API (March 2025) exposing encrypt-to-the-future as a service;
proposals encrypt to the beat's decryption epoch, nobody reads them before
the deadline, and decryption needs no per-solver reveal action.
**Fallback: commit-reveal** — hash-commit before the deadline, reveal
after, non-reveal penalized against bond and successRate; strictly worse (a
withheld reveal is a free option on others' reveals), kept only for
environments without a keyper set.

Rejected: a trusted auctioneer (CoW's autopilot shape) — it works, but is a
censorship point the rest of the architecture exists to avoid; and
exclusivity windows alone — they protect the quoter, not the beat, and
reintroduce latency competition. Sealed submission composes with
`P4-privacy.md` Tier 1, which uses the same Shutter machinery for offer
bodies; this document requires it only for proposals.

One further decision rides on the proposal format (the ERC-7683 lesson —
intent systems interoperate on the order struct and compete on
execution): the `LoopProposal` and fill record structs, once frozen
(v2 bump + this beat design), are published as the open interface
third-party solvers and future books build against — solvers compete on
discovery, never on private knowledge of the struct.

## 4. Scoring without a numeraire (U14)

CoW scores in a common numeraire — surplus converted to ETH via "native
prices," COW payouts converted at 24-hour-averaged Dune prices specifically
to blunt reference-price manipulation. That works because deep external ETH
markets anchor the reference. Loopmarket has no anchor *by construction*:
personal tokens price only inside their loop, and no external market for
them exists or should. Importing "convert to a reference asset" imports
CoW's native-price manipulation surface without CoW's liquid anchors — a
solver who can nudge any leg denomination's reference price can mint score.
Hence U14, quoted exactly: **"numeraire-free scoring."**

The score of a candidate outcome (a set of offer-disjoint winning loops) is
its total log surplus: Σ over winning loops of log Π(rates) — dimensionless
and invariant under re-denomination of any personal token, since each
maker's unit appears once above and once below the line within its own loop
and cancels. Per-offer shares of that headroom (as the equal log-surplus
split of `P2-settlement-pricing.md` distributes them) are what §5's
fairness floor compares. Failure-aware weighting (expected settled surplus)
belongs to the objective in `P2-loop-selection.md`.

## 5. The fairness filter, generalized to cycles

CoW's CIP-67 fair combinatorial auction (live June 20 2025) exists because
single-winner batching caused surplus shifting and cross-subsidization, and
policing it ex post via EBBO was "significant operational overhead and a
centralization factor." Its rules: per directed token pair, a **reference
outcome** = the best single-pair bid; any batched bid delivering some pair
less than its reference is discarded before winner selection — batching
happens only if every group benefits. The theory (Cramton et al.,
arXiv:2408.12225) frames this as cooperative-game fairness against an
*endogenous* reference and proves the trade-off: "stronger fairness
guarantees come at the expense of the market value of the assets
delivered." Loopmarket generalizes from pairs to cycles (decided 2026-08,
lands with P2):

- **Per-offer reference outcome** = the best standalone proposal through
  that offer among the beat's submissions — its best 2-cycle (direct
  barter) or best simple loop — *always including the deterministic
  baseline's proposals*. Including the baseline is load-bearing: it stops
  solvers collectively withholding standalone bids to deflate references,
  because the free replica-computable solution is always in the reference
  set. An offer no submission reaches standalone has reference = no-trade.
- **Filter**: any proposal whose settlement would give some participating
  offer a worse outcome than its reference is discarded before selection.
  A k-loop wins only if every member does at least as well as going alone.

Two consequences. First, `per_node_ok` is **kept as arithmetic fact,
superseded as policy**: the arithmetic stays (a loop whose indivisible legs
cannot cancel is infeasible; U3's re-verification refuses it forever), but
as the *fairness* story it is subsumed — per-node adequacy is the
degenerate case of "no offer does worse than its reference," since a maker
left net-negative does worse than not trading. This touches U3's checklist
(step 3 of `MockSettlement.submit`) and is discussion-agenda item 3; until
sign-off, settlement enforces both. Second, ex-post best-execution policing
is not built at all: CoW needed a whole EBBO apparatus (reference routes
for 2–3k orders in under a second, penalties for slippage solvers don't
control, a 72-hour reimburse window) because fairness lived outside winner
selection. The deterministic baseline is loopmarket's free EBBO oracle —
every replica computes the canonical reference score from the pinned root,
so "did the winners beat the obvious solution" is verifiable by anyone.

## 6. Winner selection

Selection consumes the packing problem of `P2-loop-selection.md`
(offer-disjoint cycle packing; chains when they land). The regime split
follows CoW's empirical fact that ~94% of batches have ≤3 orders — real
combinatorial interaction is sparse, so exactness is affordable where it
matters: **exact ILP for small beats, greedy over surviving offer-disjoint
proposals** for large ones. Greedy selection is approximate, which makes a
winner's marginal contribution (§7) possibly negative; adopt CoW's patch
verbatim — referenceScore_i = min(winning score, counterfactual score),
and if the reward is still negative, re-run selection without solver i.

Determinism: ties break lexicographically by loop_id, then proposal hash,
extending U6 from single-solver replay to batch settlement — same beat
inputs (pinned tuple + revealed proposals) ⇒ same winners on every replica.
Deliberately ahead of Cycles, whose min-cost-flow optimum "is not unique"
with tie-breaking punted to governance (arXiv:2507.22309); loopmarket's
audits need byte-identical replay, not a committee.

## 7. Solver rewards

Adopted from CoW's CIP-38/CIP-67 lineage (decided 2026-08, lands with P2):

- **Performance reward** = cap(totalScore − referenceScore_i −
  missingScore_i): solver i's marginal contribution to the beat
  (second-price-like) minus score promised by winning-but-unsettled
  proposals. cap(x) = max(−c_l, min(c_u, x)); rewards can go negative — a
  solver that wins and fails to settle owes the protocol. Upper cap
  c_u = β × settlement fees the solver's own settled loops generated (CoW:
  β = 50% Ethereum/Arbitrum/Base, 100% elsewhere; loopmarket starts
  conservative) plus a small fixed floor so young solvers with no fee
  history can earn. The cap is U13's budget discipline: rewards can never
  exceed revenue the solver's own settlements produced.
- **Consistency pool**, weekly, budget = β × fees − performance rewards
  paid: consistencyMetric_i = successRate_i × Σ_o surplus_i(o)/Σ_j
  surplus_j(o) — pays *losing but competitive* solvers proportional to
  proposed surplus, weighted by settle-in-time success rate. Deliberately
  funds a solver ecology, not a monoculture; monoculture is a collusion
  precondition (§8).
- **successRate standing** decays repeated win-without-settle; it gates the
  consistency pool and any future quoting tier.
- **CIP-72 rule, pre-committed**: if a quoting tier ever exists (broker
  software quoting almost-loops — `adoption-and-thickness.md`), a quote is
  reward-eligible only if the quoter later proposed an execution at least
  as good and it survived the fairness filter — CoW's fix after solvers
  baited users with quotes they never solved, worst on cheap L2s.
- **Considered, not adopted**: a UniswapX-style exclusivity window for the
  first-committed discoverer, as search compensation — right where bids are
  public; under sealed submission it buys little and reintroduces a race
  for the window. Revisit only if reveal-time copying (§10) proves real.

Per U12, quoted exactly: **"reward/reputation statistics count settled
fee-paid loops only."** Proposed surplus enters consistencyMetric only over
reward-eligible offers (§9); nothing unsettled or unpaid enters standing.

## 8. Collusion resistance and the reserve bid

The single cheapest anti-collusion device available to loopmarket is
already written: the deterministic baseline runs in every beat as a
**permanent reserve bid**. A ring can never win with less surplus than the
free in-protocol solution every replica computes; rewards pay only capped,
verified improvement over it. First-price flavor deters ring formation
(Marshall & Marx: a ring must trust its designated winner to shade;
deviation is profitable and invisible), and the transaction-fee-mechanism
impossibility results (arXiv 2402.08564) mean the goal is resistance,
priced and monitored — not proof.

**Precondition (unresolved).** `ExchangeGraph` keeps only the best rate per
ordered pair; a lower-rate parallel edge can satisfy per-node feasibility
where the best-rate edge fails. A reserve bid with silent recall gaps
weakens the collusion defense exactly where it matters — a ring profits in
the regions the reserve cannot see. The baseline's promotion from "species
to beat" (ARCHITECTURE.md §7) to normative reserve is therefore **gated on
the recall-gap fix-or-document in `P2-loop-selection.md`**, and it changes
U6's meaning (replay determinism → normative floor): discussion item 3.

**Solver entry** is permissionless-with-bond. Rejected: the 1inch Fusion
shape — a resolver whitelist capped at 10 with stake ≥5% of total Unicorn
Power, an oligopoly its own governance later tried to unwind. Bonds are
sized to damages and adjudication, never notional: CoW's only two real
slashes were operational negligence cured at exact damages ($166,182.97,
CIP-22 Barter hack; $76,783, CIP-55 GlueX allowance bug, reimbursed in full
next day), with a 72-hour cure window the norm — strategic manipulation is
prevented by mechanism shape, not punishment. Loopmarket's bonds target the
residual channels: win-without-settle, submission spam, wash-loop score
inflation. Registration bonds route through the factbond shared pool — the
pool's second customer after assertion bonds (`P3-guarantee-coupling.md`;
factbond side: `../../../factbond/docs/plans/loopmarket-coupling.md`) — so
solver misbehavior adjudicates on the same escalation ladder as everything
else.

## 9. Fees and the wash-loop inequality

Whether loopmarket charges fees at all — who pays, in what asset, against
the "makers never need gas" ambition — is discussion-agenda item 4, not
decided here. What is decided is the shape any fee system must have: §7's
rewards are insolvent without one and lethal with the wrong one.

- **Per-leg settlement fees in an external asset** (xDAI or BZZ), burned or
  to treasury — never personal tokens, never rebated in an asset whose
  price the rebated volume pumps. FCoin refunded 100% of fees in its own
  token: $5.6B/day wash volume within weeks, insolvency Feb 2020, $130M
  shortfall. LooksRare paid volume-proportional LOOKS against a 2% fee: a
  measured 1.34% daily return on wash capital, 98% of platform volume wash.
  Per U13, quoted exactly: **"wash-loop budget-balance by construction,
  fees external-asset only"**; factbond's F9 ("no volume-linked emissions
  anywhere") is the same law on the sister system.
- **The wash-loop inequality.** A legitimate loop *is* a self-financing
  cycle — every wash-trading detector keys on exactly that shape (Victor &
  Weintraud, WWW'21), so graph detection cannot tell wash loops from real
  ones here. The defense is arithmetic: for any loop an attacker can run
  entirely among principals it controls, Σ(subsidies + rewards reachable)
  < Σ(fees paid). A design-time budget-balance check over the fee schedule
  and reward caps — in CI once the schedule is code (decided 2026-08, lands
  with P2), and run against the adversary playbooks in the shared Phase-0
  harness (`../../../factbond/docs/plans/phase0-simulation.md`).
- **Rebates are self-funded only**: anything rebated redistributes the
  loop's own surplus among its own participants — a wash ring rebates its
  own money to itself, minus fees, automatically unprofitable. External
  top-ups of "surplus" recreate LooksRare.
- **Reward-eligible surplus** counts only offers from bonded, aged, or
  fee-paying makers — CoW's "surplus counts only over vetted tokens"
  translated to makers — and per U12 only settled fee-paid loops enter any
  statistic feeding rewards, reputation, or premia.

## 10. Gaming vectors and tripwires

Full register entries: `THREATS.md` T1 (rebate/reward-farmed wash loops),
T3 (solver collusion in batch auctions); T8 (reputation gaming) governs the
standing metrics.

| Vector | Answer | Tripwire |
|---|---|---|
| Overbid standalone to disqualify rival loops (arXiv:2408.12225) | baseline in reference set; missingScore | standalone bids settling below quote |
| Underbid packings expecting weak rivals | reserve bid floors the score | winning−reserve gap trending to 0 |
| Surplus shifting across a maker's offers (CoW "local token conservation") | fairness floor + uniform clearing | per-offer surplus dispersion in winners |
| Ring rotation among top solvers | reserve caps extraction; consistency pool | win Herfindahl; rotation autocorrelation |
| Copying revealed losers next beat | sealed proposals | winners isomorphic to prior beat's losers |
| Win-without-settle (free option) | negative rewards; successRate decay | successRate distribution tail |
| Wash-loop reward farming (T1) | U13 inequality; U12 statistics | common-funder clustering (hildobby filter 4), analytics only |

## Gates

- **G1 — sealed submission works.** A Shutter-encrypted proposal round-trip
  (encrypt → cutoff → decrypt → verify pins) on Gnosis testnet within a
  target beat time, or commit-reveal with measured non-reveal cost.
  Unblocks P2 implementation.
- **G2 — reserve-bid precondition.** The ExchangeGraph recall gap fixed or
  its bound documented (`P2-loop-selection.md`'s gate). Until it passes,
  the baseline stays a benchmark and the reserve-bid collusion argument may
  not be cited as a defense.
- **G3 — wash-loop inequality holds.** The candidate fee schedule + reward
  caps survive the self-dealing adversary playbook in the Phase-0 harness
  with strictly negative attacker EV. No fee schedule ships without it.
- **G4 — determinism replay.** Same pinned tuple + same revealed proposals
  ⇒ byte-identical winner set on independent replicas; the U6 test suite
  extends to the beat.
- **G5 — sign-off.** Discussion-agenda items 3 (`per_node_ok` supersession
  + reserve promotion) and 4 (fees at all) decided by the owner. This
  document proceeds on its stated defaults until then.

## Open problems

- **Beat length calibration** (P2 implementation + simulation). Gnosis
  blocks are ~5s; solve time, Shutter epoch granularity, and offer
  freshness pull apart. Kidney-exchange batch-timing says thickness gains
  from longer batches are modest — start short, lengthen only on measured
  proposal-competition failure.
- **Fairness-filter gaming materiality** (P2 + Phase-0 harness). CoW judges
  the overbid/underbid wrinkles negligible because 94% of batches have ≤3
  orders and exact optimization covers them; loopmarket's sparsity profile
  is unknown until real books exist. The harness should search for book
  shapes where filter gaming pays.
- **Null-reference edge cases** (P2 design follow-up). Reference = no-trade
  for offers nobody reaches standalone lets any non-negative inclusion
  pass — is that right for offers only ever reachable inside long loops?
  And should a reference computed only from the baseline's loops bind
  competing solvers while the baseline itself is gated by G2?
- **Consistency-pool sybil surface** (P2 + THREATS.md T8). A solver split
  into many identities farms the proportional payout; successRate weighting
  and per-identity bond carry are the cost floor, but the equilibrium
  identity count needs simulating before β is set.
- **Fee incidence** (successor to discussion item 4). Who ultimately pays
  the per-leg fee — winners' surplus, makers at settlement, solvers out of
  rewards — and how that coexists with "makers never need gas."
- **Off-chain side payments** (permanent residual, THREATS.md T3). Solvers
  can settle collusion out of band, invisibly; the impossibility results
  say this cannot be designed away. Monitor the tripwires, keep entry
  permissionless so rings face entrants, accept the residual.

## What this document does not promise

- **Settlement certifies re-verification, not delivery.** The beat ranks
  proposals and commits fills; whether the cello ever reaches the crate is
  the guarantee fabric's business (`P3-guarantee-coupling.md`).
- **The fairness floor is endogenous.** "No offer does worse than its
  reference" quantifies over *this beat's submissions plus the baseline* —
  not a best-execution claim against the world; by U14's own refusal there
  is no world price to compare against.
- **Collusion resistance, not collusion-proofness.** The reserve bid caps
  what a ring can extract; it does not make rings irrational, and off-chain
  side payments stay invisible.
- **Rewards are prices for discovery under caps, not measures of solver
  quality**; consistency standing is a payment rule, not a reputation the
  rest of the system may import.
- **Scores compare packings within a beat** — log-surplus totals are not
  welfare measures across beats, participants, or books.
- **Nothing here is built.** Every mechanism lands with P2; the fee system
  additionally awaits discussion item 4, and two invariant changes (U3's
  checklist, U6's meaning) await item 3.
