# loopmarket — threat register (T1–T14)

Status: design, 2026-08-07; dated edit 2026-08-21 (T10–T13 imported from
the factbond mirror per the content-sync rule; T14 added at owner
direction with the agenda-#5 sign-off). Decided at 2026-08-07: the fixed IDs T1–T9 and their
primary owners; young-system ordering; the maintenance and content-sync
rules; the ten by-construction fee/bond rules; the wash-loop inequality as
U13's design-time check; initial tripwire thresholds, pre-registered,
changeable only by dated edit. Open here: threshold calibration, the
announcement-layer spam floor, k-cohort sybil costing, off-chain solver
side payments, off-protocol subsidies, semantic drift.

This is the cross-system register both repos gate on. Each entry records
the attack, its economics with researched numbers, the by-construction
defense with its invariant and owning document, the residual, the tripwire
that pages a human, and the owning work package. The mirror is
`factbond/docs/plans/THREATS.md`; defenses live in `P2-batch-auction.md`,
`P1-federated-book.md`, `P3-guarantee-coupling.md`,
`catalogue-bootstrap.md`, `P4-privacy.md`, and factbond's
`mechanism-design.md`, `insurance-products.md`, `evidence-policy.md`; the
adversary playbooks exercising every entry are
`factbond/docs/plans/phase0-simulation.md`.

## 0. Register discipline

**Why young-system ordering.** A mature marketplace fears capture and
drift; a young one dies of its own incentive budget — FCoin was insolvent
within 20 months of inventing fee-mining, and Ethereum NFT wash volume
peaked above 80% in January 2022 — the month LooksRare's fee-mining
launched. So the ranking is expected damage to a *young*
system as each surface goes live: T1–T3 attack the earliest surfaces
(fees, rewards, the book, the beat), T4–T6 attack the guarantee fabric
(factbond-primary), T7–T9 are chronic — present from day one, accruing
slowly. IDs were assigned in that 2026-08 ranking and are **frozen: never
renumber**; re-rankings re-sort presentation by dated edit.

**The structural fact shaping every defense.** Wash-trading detectors key
on self-financing cycles — trade subgraphs with ~zero net balance (Victor
& Weintraud, WWW'21). A legitimate loopmarket loop **is** a
self-financing cycle by design: personal tokens exist only for the
instant a loop passes through and cancels. Graph-shape wash detection
would flag the product itself, so it is unavailable here; every defense
is *by construction* — budget balance, cost floors, indemnity caps —
never shape policing.

**Maintenance rule.** The register is normative: **no phase goes green
while any entry lacks an owning work package or, once its surface is
live, an instrumented tripwire.** P2 blocks specifically on T1/T3
(the phase↔document map on the repo front page, `../../README.md`).

**Content-sync rule.** Mirrored entries name a primary owner: T1–T3, T7,
T8 and T14 here; T4–T6, T9 and T10–T13 in
`factbond/docs/plans/THREATS.md`. Secondary copies
carry every column's *substance* (wording may condense, content may not)
plus a cross-reference; edits land primary-first. The factbond-native
entries T10–T13 were imported below on 2026-08-21, per this rule's
next-dated-edit clause.

## T1 — Rebate/reward-farmed wash loops

**Attack.** A sybil ring posts matched ask/bid pairs; a ring-run solver
"finds" the loop; the ring farms any volume-linked subsidy, reward,
rebate, or airdrop score. The loop settles and consumed nothing.

**Economics.** LooksRare paid volume-proportional LOOKS against a 2% fee:
a measured **1.34% daily return** on wash capital ($6.2M rewards vs $3.7M
fees in one day), 98% of platform volume wash (hildobby/Dune). FCoin
refunded 100% of fees in its own token: $5.6B/day volume within weeks,
copycats at ~40% of reported global crypto volume, then **insolvency in
20 months**, $130M shortfall. Counter-datum: Chainalysis found only 110
*profitable* NFT wash traders while most lost money to gas — a real fee
floor does price attackers out.

**Defense (by construction).** U13 — "wash-loop budget-balance by
construction, fees external-asset only" — checked by the inequality
below; U12 — "reward/reputation statistics count settled fee-paid loops
only"; F9 — "no volume-linked emissions anywhere" — the same law on the
sister system. Mechanics in `P2-batch-auction.md` §7/§9 (decided 2026-08,
lands with P2): rewards = capped marginal contribution over the reserve,
cap = β × fees the solver's own settled loops generated, plus a small
fixed floor for young solvers with no fee history — the floor is the one
subsidy term *not* bounded by the solver's own fees, so it enters the
wash-loop inequality's subsidy side explicitly and must stay below the
per-identity fee floor a sybil ring pays; rebates
redistribute only the loop's own surplus (a wash ring rebates its own
money to itself, minus fees); reward-eligible surplus counts only
bonded/aged/fee-paying makers.

**Residual.** Off-protocol budgets — grants, third-party airdrop scores,
"active maker" stats — can re-fund wash loops from outside; fee-splitting
rings just under the cap; token-appreciation cross-subsidy if loopmarket
ever issues a token (it should not).

**Tripwire.** Per funding cluster (hildobby filter 4 common-funder
clustering — analytics only, never enforcement): Σ(rewards + rebates) /
Σ(external-asset fees). Pages at > 0.8 over 7 days, or one cluster > 10%
of settled volume (initial pre-registrations).

**Work package.** `P2-batch-auction.md` §9 + the self-dealing playbook in
`factbond/docs/plans/phase0-simulation.md`.

## T2 — Sybil offer spam & statistics pollution

**Attack.** Personal tokens are free identities: flood the book to
pollute indexes, price statistics, premium feeds, and (P4) privacy
cohorts; farm any per-offer benefit.

**Economics.** Marginal wallet ≈ gas + postage. Farming is industrial:
Arbitrum single funders ran 1,000+ eligible wallets (~$3.3M to top
clusters); LayerZero filtered **803,093 addresses**; Linea ~517k of 1.3M
claimants (**~40% sybils**). Detection is an arms race the defender loses
at the margin; what deterred farming was making the marginal wallet cost
more than its expected payoff. Proof-of-personhood does not help: rented
World IDs at ~$30–80 restore sybil capacity — World ID is a *rate
limiter*, never a trust root.

**Defense (by construction).** A cost curve, not detection
(`P1-federated-book.md` §6/§8): per-offer postage is the offer's rent and
the sybil floor; per-commit fees stack; no per-offer benefit may exceed
the per-offer cost floor. U8 — "two-layer offer authenticity (feed
ownership primary; detached signature for off-feed circulation; nothing
signed enters canonical bytes)" — makes maker forgery non-free (decided
2026-08; the sidecar primitives and fail-closed `sig/` storage landed
2026-08-20, the fold rule that completes U8 lands with the P1
aggregator). Damage is bounded by the Circles
property: a sybil cannot appear in a *settled* loop without a real
counterparty on every leg — the settled fee-paid ledger is the one thing
sybils cannot cheaply populate, so U12 routes every consequential
statistic through it and nothing else.

**Residual.** Pollution of anything not settlement-weighted; the
announcement layer is floored only by sub-cent registry events and GSOC
mining, far below the storage floor (`P1-federated-book.md`, registered
open problem); **k-cohort poisoning** — P4's adaptive k-anonymity
generalizes until ≥ k live offers share a cell/bucket, so a sybil that
populates the cohort fakes k and strips the privacy; sybil-costing the k
computation is `P4-privacy.md`'s open problem.

**Tripwire.** Never-settled offer share per funding cluster: pages when
any cluster exceeds 10% of the live book or any `idx/` prefix (initial);
announcement-loss and batch top-up anomalies ride with
`P1-federated-book.md`'s TTL monitor.

**Work package.** `P1-federated-book.md` §8; k-cohort interaction:
`P4-privacy.md`.

## T3 — Solver collusion in batch auctions

**Attack.** A ring rotates lowball wins, shifts surplus between orders it
controls, or games the fairness filter — the vectors named by the CIP-67
theory (Cramton et al., arXiv:2408.12225): **overbid a standalone order
to disqualify a rival's batch as unfair**, and **underbid batches
expecting weak competition**. Losing-bid information front-runs the next
beat.

**Economics.** Ring profit = withheld surplus, stable when wins are
observable and punishable within the ring (on-chain, they are). CoW's
record says strategy is prevented by mechanism shape, not punishment: its
only real slashes were operational negligence cured at exact damages —
**$166,182.97** (CIP-22, Barter solver hack) and **$76,783** (CIP-55,
GlueX allowance bug) — with a 72-hour cure window.

**Defense (by construction).** The deterministic baseline as **permanent
reserve bid** — a ring can never win with less surplus than the free
replica-computable solution, rewards pay only capped verified improvement
over it (`P2-batch-auction.md` §8; preconditioned on the ExchangeGraph
recall gap, `P2-loop-selection.md` — a reserve with silent recall gaps
weakens this exact defense). Sealed proposals (Shutter) kill copying; the
fairness filter keeps the baseline in every reference set so references
cannot be collectively deflated; first-price flavor deters rings
(Marshall & Marx: the designated winner's deviation is profitable and
invisible); U14 — "numeraire-free scoring" — leaves no reference price to
nudge; the consistency pool funds an ecology, not a monoculture; entry
stays permissionless-with-bond.

**Residual.** Off-chain side payments are invisible and, per the
transaction-fee-mechanism impossibility results (arXiv 2402.08564),
cannot be designed away — resistance, priced and monitored, not proof.
Fairness-filter gaming materiality is unknown until real books exist
(CoW judges it negligible at ~94% of batches ≤3 orders).

**Tripwire.** Median (winning − reserve) margin per beat: pages when
< 5% of reserve score for 100 consecutive beats (initial); win-share
Herfindahl and rotation autocorrelation; winners isomorphic to a prior
beat's revealed losers.

**Work package.** `P2-batch-auction.md` §8/§10, gates G2/G4.

## T4 — Adjudication capture & dispute griefing — primary: `factbond/docs/plans/THREATS.md`

**Attack.** Buy the dispute ladder's final rung when downstream reliance
exceeds its capture cost; or grief — spam cheap disputes to freeze
settlement and wear down honest disputers. p+ε bribery (Buterin 2015)
makes vote-buying free on success: pay bribed voters only if the attack
loses.

**Economics.** Polymarket/UMA, March 2025: one whale with **~25% of DVM
voting power** (5M UMA across 3 accounts) flipped a **$7M** market whose
proposer bond was **$750** — notional/bond ≈ 10⁴, the profit sitting in
the market position outside the oracle game. The Zelenskyy-suit market
($160–237M volume) resolved NO twice against the photographic record,
slashing honest disputers both times — dispute, lose bond, learn to stop.
UMA's patch (UMIP-189, whitelisted proposers) is a retreat to partial
permissioning with the DVM rung still capturable.

**Defense (by construction).** factbond's revised bond doctrine: the
final rung's integrity cost scales with **aggregate open reliance**, and
F4 — "reliance-bounded adjudication + fail-closed caps" — stops selling
exposure as it approaches that cost (Nexus Mutual's stake > 5× claim
quorum is the production precedent). F5 — "tribunal independence +
soulbound stake": the top rung is an *independent* arbitrator (the
reality.eth → Kleros composition), never a same-token DVM; escalation
enlarges the juror base faster than p+ε liability; disputer bonds cover
delay externalities, pricing out dispute spam; conduct and removal rules
precede the first dispute; rulings reopen on new evidence. loopmarket's
side: payouts **auto-fund the dispute** on the edge that lied —
institutionalized disputer-side funding against wear-down — and the four
adversarial fixtures of `P3-guarantee-coupling.md` §4 must reject or
bound by construction.

**Residual.** The correlated bad-ruling tail — a captured rung poisons
every downstream statistic at once; reserves and reopenability mitigate
(`factbond/docs/plans/netting-and-reserves.md`). Any proposer whitelist
is itself a new capture target.

**Tripwire.** Top-principal share of final-rung power vs aggregate open
reliance per subject; per-claim (per-edge in the coupling) cap
utilization pages at 80%; honest-disputer attrition (repeat disputers who
lose and exit) trending up.

**Work package.** `factbond/docs/plans/mechanism-design.md` (the
adjudication constitution); here: `P3-guarantee-coupling.md`.

## T5 — Insurance arson — primary: `factbond/docs/plans/THREATS.md`

**Attack.** Buy insurance on a catalogue edge, then make it wrong or
corrupt its adjudication — the assassination-politics generalization: a
market paying on an adverse event is a purse for causing it.

**Economics.** Profit = payout − premium − corruption cost; unbounded
whenever payout is unlinked to real loss. Insurance law's answer is the
indemnity principle: payout ≤ demonstrable insurable interest.

**Defense (by construction).** F3 — "indemnity (payout ≤ provable
reliance; payout-cap proxy where unprovable)". loopmarket is the one
deployment where reliance is provable for free: settlement roots pin
which settled legs walked the insured edge (`P3-guarantee-coupling.md`
§2–3), so breaking an edge you insured pays at most what you provably had
at stake, minus premium. Outside settlement (the agents-first wedge) the
proxy is micro-scale payout caps sized so arson cannot pay even on wholly
fabricated reliance (`factbond/docs/plans/insurance-products.md`). F4's
per-edge aggregate caps fail closed; a buyer-controls-source exclusion
bars insuring facts the buyer can cheaply falsify.

**Residual.** Reliance inflation via colluding loops — real settlements
run through the edge to raise the ceiling; a T1 fixture in a different
mask, bounded by the same arithmetic (inflating reliance costs real fees,
U13; only settled fee-paid loops count, U12). Many small policies across
sybils still press on the per-edge caps.

**Tripwire.** Per-edge open-insurance / final-rung-integrity-cost ratio
pages at 80% utilization, before the fail-closed stop; payouts where the
buyer's funding cluster intersects the edge's asserter/disputer cluster;
pre-launch: the Phase-0 arson-ROI surface must stay negative.

**Work package.** `factbond/docs/plans/insurance-products.md` +
`phase0-simulation.md`; here: `P3-guarantee-coupling.md` §3.

## T6 — Catalogue governance capture — primary: `factbond/docs/plans/THREATS.md`

**Attack.** Patient accumulation of assertion/adjudication power over hub
edges; bribe markets for edge disputes; re-meaning categories under
settled offers; category-stuffing to game solvers.

**Economics.** Croatian Wikipedia: **~10 admins held the project for 9
years**; the comparative CSCW study (TeBlunthuis et al., CSCW 2024)
attributes capture to missing *rules about rulers* — no admin-conduct or
removal pages — not to content rules. Curve wars: a liquid governance
token spawned an industrial bribe market (Votium; Convex > ⅓ of veCRV),
and the Mochi attack was stopped only by an ad hoc Emergency DAO. A hub
edge (`organic-food ⊑ food`) underwrites vastly more settlement value
than a leaf; capture there buys everything routed through it.

**Defense (by construction).** Bonds scale with **settlement-weighted
centrality** — realized reliance from the witness feed, never static
degree, which attackers farm cheaply (`P3-guarantee-coupling.md` §2). F5
keeps adjudication stake soulbound: no transferable token for a Votium to
price. Governance norms are protocol rules in `catalogue-bootstrap.md`:
schema gated and bonded, offers permissionless; "never re-mean a
category" (content addressing enforces it); "don't tag for the solver"
(OSM's don't-tag-for-the-renderer, instrumented below). Arbitrator
conduct and removal rules precede the first dispute — the Wikipedia
lesson verbatim — and the emergency brake is constituted with removal
rules, not improvised Curve-style. Per-edge loss experience is the
standing reliability audit.

**Residual.** Slow semantic drift inside accepted vocabulary that never
trips a dispute; the emergency brake itself; cultural capture of the
import pipeline's seed choices.

**Tripwire.** Single-principal bonded share over the top decile of
settlement-weighted edges pages at > 25% (initial); stuffing metric —
offers whose concept sets include high-traffic categories their fills
never exercise; schema-merge review latency.

**Work package.** `catalogue-bootstrap.md` (norms, import pipeline) +
`factbond/docs/plans/mechanism-design.md` (anti-capture economics).

## T7 — Lemons routing

**Attack.** No attacker required: the solver maximizes the rate product,
so it selects the cheapest leg that type-checks — under asymmetric
information, the lemons leg (the worst `plumbing-service` that still
satisfies the category). The catalogue guarantees type conformance, never
quality; the optimizer amplifies the gap because bad legs quote the best
rates.

**Economics.** The junk maker's margin is the price of the quality signal
it does not deliver. Credit-network precedent: Ripple's "Mind Your
Credit" (WWW'18) found **~$13M at risk** from misconfigured rippling
flags — path optimization silently loading counterparty risk onto whoever
priced it cheapest — and a topology where **as few as 10 highly connected
gateway wallets could financially isolate much of the user base**.
loopmarket avoids the hub half *structurally*: loops cancel at the maker,
no transitive trust exists to concentrate — a property to defend, not
dilute. The lemons half remains.

**Defense (by construction).** Risk-priced routing
(`P3-guarantee-coupling.md` §5; decided 2026-08, lands with P3): solver
edge weight = rate × (1 − expected-loss premium) from the pool's
per-edge/per-maker loss experience — strictly solver-side, so U3 and U5
are untouched; per-maker acceptance limits (Circles/Trustlines trust
lines) cap loop value through unproven makers — quarantine, not ban; a
per-beat concentration fee, the analog of Trustlines' **0.1% imbalance
fee**, charges loops for piling exposure onto one maker, under U13's fee
discipline.

**Residual.** Cold start: no loss data, so wide priors tax honest
newcomers exactly as hard as lemons — the broker surface and bridge
species are the sanctioned on-ramp (`adoption-and-thickness.md`); the
premium feed's inputs are attackable via T2 until volume exists.

**Tripwire.** Realized loss/dispute rate of cheapest-decile legs vs the
book median pages at > 3× (initial); acceptance-limit saturation
concentrated on new makers (measures the cold-start tax).

**Work package.** `P3-guarantee-coupling.md` §5; fee mechanics with
`P2-batch-auction.md`.

## T8 — Reputation gaming

**Attack.** Inflate delivered history via wash loops; suppress complaints
via retaliation or complaint cost; split identities to farm standing
(the consistency pool's sybil surface, `P2-batch-auction.md`).

**Economics.** eBay: only **0.3% of transactions rated negative** while
P(negative | partner rated negative) > **37%** — retaliation suppressed
truthful feedback until eBay went one-sided in 2007 (Resnick &
Zeckhauser; "Reputation Inflation", Filippas–Horton–Golden EC'18: cheap
ratings inflate toward uselessness). EigenTrust's pre-trusted peers are a
centrality target; it survives in papers, not production.

**Defense (by construction).** U12, quoted exactly: "reward/reputation
statistics count settled fee-paid loops only" — history inflation costs
real external-asset fees (U13), so reputation is bought at fee price,
never minted. Loss experience comes only from **bonded, adjudicated
events** — costly signals resist inflation as cheap ratings never did.
Disclosure is one-sided and aggregated (the eBay fix). Silence is
uninformative: a young bonded system shows the eBay pathology in mirror
image — near-zero recorded losses mean *thin data*, not safe edges — so
premiums start wide and narrow only on settled history
(`P3-guarantee-coupling.md` §5); an undisputed edge is priced unknown,
never good.

**Residual.** Collusion among real people (identity doesn't help);
thin-data cleanliness misread by consumers of the statistics; history
farmed at fee price is still history — the schedule must keep that price
above the standing it buys (rule 10).

**Tripwire.** Per-maker history growth per unit fee paid; pages when a
maker's standing-relevant history is > 50% common-funder counterparties
(hildobby filter 4, analytics only; initial); feedback-silence share per
vertical.

**Work package.** `P3-guarantee-coupling.md` §5 + `P2-batch-auction.md`
§7 (standing, consistency pool).

## T9 — Basis-risk disputes — primary: `factbond/docs/plans/THREATS.md`

**Attack.** An erosion, not an attacker: the insured loss is real but the
edge is technically "true", or the trigger pays when nothing was lost.
The index-insurance literature is unambiguous that **basis risk, not
fraud, is the #1 uptake killer**; parametric products show near-zero
measured claims fraud, displacing failure into trigger–loss mismatch.
Every deployed dispute system pays the same tax through wording: Augur's
chronic invalid-market problem, Proof-of-Humanity's photo-angle
pedantry, the Zelenskyy "wearing a suit" market — policy ambiguity is the
cheapest attack surface of all.

**Economics.** Each publicly wrong-feeling resolution burns trust in the
whole product class; the Zelenskyy market burned $160–237M of volume's
credibility and taught honest disputers to exit (T4's wear-down arriving
through wording rather than capture).

**Defense (by construction).** F8 — "structural claims settle by
certificate only": the fits-within half of every dispute is
machine-checkable against the pinned root (`proof-fabric.md`) — genuinely
lower basis risk than any weather index. The worldly half is fought at
wording time: hash-pinned adjudication policies (decided 2026-08, lands
with the v2 bump; `P3-guarantee-coupling.md` §4) — rulings converge on
the letter of the referenced policy, so the policy hash *is* the
contract; parametric-first wherever a canonical digital feed exists (the
Etherisc FlightDelay pattern); the oracle roster scoped per category
under F7 — "'certified ≠ true' on every surface".

**Residual.** Semantic edges ("suitable-for-X") retain irreducible
interpretive basis risk; no wording closes it, only pricing it and
saying so.

**Tripwire.** Per policy hash: share of disputes ending "policy
technically satisfied, consumer claims loss" (or the inverse) pages at
> 10% over a rolling quarter (initial) and forces a policy rewrite with a
version bump, never an in-place edit.

**Work package.** `factbond/docs/plans/evidence-policy.md`; here:
`P3-guarantee-coupling.md` §4.

## T10 — Assertion-mining & assertion spam — primary: `factbond/docs/plans/THREATS.md`

*(Imported 2026-08-21 per the content-sync rule; condensed, substance
complete.)*

**Attack & economics.** Farm any reward proportional to assertion volume
by asserting garbage at scale; failing that, spam assertions to
manufacture a calibration track record from certified-by-timeout claims
nobody watched, or to bury the claims that matter. Terminal precedents:
FCoin's trans-fee mining reached (with copycats) ~40% of global reported
exchange volume before insolvency inside 20 months; LooksRare's
volume-linked emissions returned a measured 1.34%/day on wash capital.
Assertion-mining would be the FCoin of facts, and the farm's statistics
would poison the very dataset the system exists to produce.

**Defense (by construction).** F9 — no volume-linked emissions anywhere:
an asserter's income paths are exactly yield on pool stake, a share of
assertion fees as an LP, slash winnings, and the underwriting business
(factbond `mechanism-design.md` §3; fees land with Phase 1). Assertions
cost a fee accruing to the pool — the spam price. The calibration ledger
counts only resolutions that carried consumption or survived a real
dispute (the U12 shape applied to reputation), so a manufactured record
buys nothing.

**Residual.** Off-protocol subsidies re-fund the farm from outside —
T1's residual wearing factbond's mask; a future token would add the
reflexive surface factbond `DESIGN.md` §9 refuses, revisitable only
after modelling the FCoin scenario.

**Tripwire & work package.** Assertions per principal never touching
consumption or dispute; certified-by-timeout share per asserter funding
cluster; the G-M6 audit finding any volume-proportional path pages
immediately, no threshold. factbond `mechanism-design.md` §3 (Phase 1) +
`phase0-simulation.md` §5 (the F9 check, kept forever).

## T11 — Self-dispute laundering — primary: `factbond/docs/plans/THREATS.md`

*(Imported 2026-08-21; condensed, substance complete.)*

**Attack & economics.** Dispute your own assertion from a second
identity and wash stake through the winner's share — manufacturing
dispute history, farming the calibration ledger's dispute-survival gate,
or laundering through a dispute-triggered market. Without a burn, one
principal on both sides recycles its capital at ~zero cost while
printing fake track record and fake loss experience — corrupting T7's
feed and T8's ledger at once.

**Defense (by construction).** The slash-split's burned slice (factbond
`DESIGN.md` §8; decided 2026-08, lands with Phase 1) makes the launder
loop strictly negative — loopmarket's wash-loop inequality applied to
disputes. **The burn is load-bearing**: any future split change must
re-verify the inequality. Dispute-market size caps bound the channel's
throughput; the ledger's consumption gate keeps even a paid-for history
thin.

**Residual.** The general asserter–challenger collusion form is open
(factbond `mechanism-design.md` §8 q4); the burn size is a parameter,
not a law — UMA burns half the loser's bond; the right slice is a
Phase-0 output.

**Tripwire & work package.** Asserter/challenger funding-cluster
intersection on resolved disputes (analytics only, never enforcement);
dispute-win share within common-funder clusters; the scripted Phase-0
laundering playbook stays strictly negative across the grid. factbond
`mechanism-design.md` §3/§8 + `phase0-simulation.md` §7.

## T12 — Correlated adjudicator failure as reserve shock — primary: `factbond/docs/plans/THREATS.md`

*(Imported 2026-08-21; condensed, substance complete.)*

**Attack & economics.** Not an actor but the tail T4 leaves: every claim
whose escalation path ends at the same final rung fails together if that
rung is captured or conformist — a failure that respects no DAG
structure, so the min-cut cluster term cannot see it. The reserve's
Lundberg arm (u = max(worst correlated claim cluster, ln(1/ε)/R)) dies
under correlation, and heavy tails void the bound unless per-fact
notional caps force a finite MGF. Nexus Mutual's collapsed model is the
production shape: MCR = active cover / 4.8 at Solvency II's 99.5%
one-year survival, ~20% concentration cap per listing.

**Defense (by construction).** The shock enters the reserve as an
explicit cluster — all open exposure sharing a final rung — with its own
loading (factbond `netting-and-reserves.md` §7; reserve v0 lands with
Phase 2). Per-fact notional caps enforce the model's assumptions; they
are F4's per-claim arm — at the cap the pool stops selling, never
re-prices and carries on. F4's final-rung condition caps what any single
rung is asked to defend; reopenability plus retroactive refunds make a
reversed capture recoverable. The go/no-go demands ≥99.5% solvency under
scripted cluster shocks.

**Residual.** The loading's size is the registered open problem: if it
dominates at realistic ladder concentration, adjudicator *diversity*
becomes a capital requirement, not a governance nicety. A captured rung
also poisons the loss tables — no reserve line item restores a corrupted
dataset.

**Tripwire & work package.** Share of open exposure terminating at any
single final rung; ruin runs re-run at every reserve or ladder change;
a loss-table divergence review forced after any final-rung reversal.
factbond `netting-and-reserves.md` §7 (Phase 2) + `mechanism-design.md`
+ `phase0-simulation.md` §7.

## T13 — Evidence-class rot — primary: `factbond/docs/plans/THREATS.md`

*(Imported 2026-08-21; condensed, substance complete.)*

**Attack & economics.** The fabrication cost of an admissible evidence
class decays — continuously under generative media, discontinuously on a
per-model exploit that is expensive to find and ~zero to reuse until
revoked. Design precedent: September 2025, an AI-generated image
injected via multiple-exposure mode into a validly signed Nikon Z6III
NEF; Nikon revoked all Z6III certificates and suspended its Authenticity
Service — one exploit, a fleet's evidentiary standing gone, and until
demotion lands every open claim admitting the class is simultaneously
attackable: a correlated evidence shock, T5's cheapest input. A $100
payout is a $100 bounty on fabricating one admissible artifact; bare
C2PA fabrication is near zero and falling. **Revocation latency is the
binding parameter.**

**Defense (by construction).** Admissibility is data, not code (factbond
`evidence-policy.md` §1; classes land with Phase 1): a demotion is a
signed catalogue edit binding every ruling not yet issued the moment it
publishes — demote fast, promote slow, fail closed. Policies pin rules
naming live inputs ("valid and unrevoked at ruling time"), so a claim
pinned to policy v1 stops admitting the rotted class without its hash
changing. Closed rulings never rebind (F1), but a fleet revocation is
evidence that did not exist at ruling time, so the reopening path
applies. The reserve treats a demotion as a correlated shock — the
affected cluster caps immediately (F4 at fleet scale). The
fabrication-bound gate (Phase 2) keeps every sole-evidence class's
sourced, dated fabrication-cost estimate above its payout cap or drops
it to corroboration-only.

**Residual.** Revocation latency itself; the demotion authority is a
T6-adjacent capture vector; the fabrication-cost curve E(t) has no
defensible empirical anchor — the sim sweeps it and treats fragility as
a gate, but the arms race is carried, not closed.

**Tripwire & work package.** Revocation-to-demotion propagation time
across open adjudications; per-class realized loss vs the class's dated
fabrication-cost estimate (paying out above it pages); red-team bounty
claim rate per class; the Phase-0 mass-revocation drill must show the
ladder degrading, never certifying garbage. factbond `evidence-policy.md`
§4/§5 + `phase0-simulation.md` §7; reopening: `mechanism-design.md` §4.

## T14 — Aggregator omission & centralization (added 2026-08-21)

**Attack.** An aggregator silently omits — or systematically delays —
makers or offers from its fold. Its manifest is the book most solvers
read, so omission is market exclusion; motives: a vertically-integrated
solver-aggregator suppressing rival order flow, pay-to-be-indexed
extortion, or external pressure. The enabling condition is
centralization, not code: admission-by-reference (T2's spam defense) *is*
censorship capability — the same discretionary power, mirrored — and with
only one aggregator worth reading it becomes unilateral market shaping.
Escalation: at P1 the settlement instance's own fold (a single trusted
writer) decides what can settle through it — a chokepoint no aggregator
competition reaches.

**Economics.** Omission is free at the margin (fold nothing, pay nothing)
and produces a perfectly valid `book_root`; its value scales with the
censor's share of solver attention. The counter-force is capital-light in
protocol but heavy in operations: a competing aggregator needs a full
pinning Bee node, so the market concentrates by default even with no
attacker — centralization is the *equilibrium* to defend against, not
just the attack.

**Defense (by construction).** The fold is pure and commutative
(`P1-federated-book.md` §2): aggregators that saw the same inputs produce
byte-identical `book_root`s in any fold order, so divergence between
manifests is evidence, not opinion. Omission is provable, never merely
suspected: announcements have a censorship-resistant ground truth (the
*permanent* Gnosis registry-event fallback), maker books are public
feeds, and recordstore absence proofs demonstrate "offer X is absent
from root R" mechanically while X sits on its maker's feed. Fold
decisions and rejections are attributed speech acts in the aggregator's
own `provenance_root`. Entry is permissionless, and reading never
requires an aggregator: any solver can fold maker feeds directly — a
censored offer is uncaptured surplus a competitor collects.

**Residual.** Neutrality-by-auditability is only as real as the number of
independent aggregators actually running — the aggregator-economics open
problem (`P1-federated-book.md`; `adoption-and-thickness.md`). **Owner
directive (2026-08-21): distributed, permissionless and censorship-proof
is loopmarket's main value; several independent aggregators are the
deployment floor, a single-aggregator steady state is a failure
condition, and stronger decentralization of the read path is a mandated
investigation before P1 completes.** The P1 settlement-instance
chokepoint stands until P2's verifiable settlement; no aggregator remedy
touches it.

**Tripwire.** The count of independently-operated manifests: pages when
it falls below two. Manifest `book_root` divergence not explained by
input-set differences (the cross-audit). A planted-offer probe:
publication-plus-announcement to manifest inclusion, measured across
every watched aggregator — any manifest that never includes the probe
pages.

**Work package.** `P1-federated-book.md` §2/§8 (fold, provenance,
admission-by-reference); `adoption-and-thickness.md` (aggregator
economics, section added 2026-08-21); the settlement half:
`P2-batch-auction.md`; the read-path decentralization investigation:
registered, pre-P1-completion.

## The ten fee/bond rules (by construction)

The compressed design law under T1/T2/T5/T8; each rule is load-bearing
somewhere above.

1. **The wash-loop inequality** (below): every self-dealable loop is
   strictly negative-EV, checked at design time.
2. **Fees exit the loop economy**: per-leg fees in an external asset
   (xDAI/BZZ), burned or to treasury — never personal tokens, never
   rebatable in an asset the rebated volume pumps (FCoin's fatal flaw).
3. **No volume-proportional emissions, ever** (F9); growth incentives
   capped per settlement and per identity-cluster per epoch, scored on
   verified improvement over the reserve (LooksRare vs Blur).
4. **Surplus rebates are self-funded only**: the loop's own surplus to
   its own participants; external top-ups recreate LooksRare.
5. **Baseline solver = reserve price**: solver pay is a capped function
   of (winning − baseline) surplus; collusion can never earn more than
   the cap nor win below the free solution.
6. **Payment on realized outcomes with clawback**: weekly netted
   settlement-verified results; negative deviations are debts;
   registration bonds ≥ max weekly exposure (CoW's slippage accounting).
7. **Indemnity cap on information insurance** (F3): payout ≤ value of
   the settled legs that pinned the insured edge.
8. **Two-part bond sizing**: bond = max(adjudication-cost floor, k ×
   settlement-weighted centrality); the final rung additionally requires
   integrity budget ≥ aggregate open reliance, else selling stops — the
   cap fails closed (F4).
9. **Adjudication stake is soulbound** (F5): non-transferable,
   time-locked, retroactively slashable; no liquid token for bribe
   markets to price.
10. **Every offer costs something to exist**: postage + per-commit fees
    set the sybil floor above any per-offer benefit; every statistic
    that matters counts settled, fee-paid loops only (U12).

## The wash-loop inequality — U13's design-time check

Let A be a principal and C(A) the identities A controls — makers,
solvers, LPs, announcement identities. For every loop L with legs l₁…lₙ
settleable entirely within C(A), the fee schedule Φ and reward/rebate
schedule must satisfy, strictly and for all n:

    Σ_{s ∈ S(L, C(A))} value(s)  <  Σ_{i=1..n} Φ(l_i)

where S(L, C(A)) is every subsidy, reward, rebate, emission or
statistic-derived benefit any identity in C(A) can reach as a consequence
of L settling. Valuation discipline: every term of S must be
**cap-bounded in the external fee asset at schedule time** — U14 means no
spot price exists to value anything else, and a benefit that cannot be so
bounded is forbidden outright (which is why F9 bans volume-linked
emissions: they admit no such bound). Self-funded rebates satisfy their
term automatically — the ring rebates its own money to itself. The check
runs over the closed form of the schedules at design time, in CI once
they are code (decided 2026-08, lands with P2), and against the Phase-0
self-dealing playbooks.

## Gates

- **G1 — full assignment.** Every entry has an owning work package and,
  for every live surface, an instrumented tripwire with a pre-registered
  threshold recorded here by dated edit. No phase gate passes without
  it; P2 blocks on T1/T3.
- **G2 — U13 holds.** The candidate fee schedule + reward caps survive
  the inequality in CI and the Phase-0 self-dealing playbook with
  strictly negative attacker EV (shared with `P2-batch-auction.md` G3).
- **G3 — tripwires are U12-clean.** Every tripwire is computable from
  the settled fee-paid ledger and pinned roots alone — a tripwire fed by
  pollutable statistics is itself a T2 target.
- **G4 — mirror sync.** Diff against `factbond/docs/plans/THREATS.md`
  empty modulo primary/secondary marking and wording-level condensation of
  secondary copies (column substance must match), checked at every phase
  gate; edits landed primary-first; factbond's T10–T13 appendix
  propagates here per the content-sync rule.
- **G5 — re-ranking cadence.** The damage ordering is reviewed at every
  phase gate and after any tripwire page; re-rankings are dated edits
  that re-sort presentation without renumbering.

## Open problems

- **Threshold calibration** (this register + Phase-0). Every threshold
  above is an initial pre-registration — honestly, a guess; the harness
  and first real books recalibrate. A threshold that becomes a target
  invites Goodharting, so recalibration is by dated edit under G5, never
  silent.
- **The announcement-layer spam floor** (T2; `P1-federated-book.md`).
  Discovery spam is orders of magnitude cheaper than storage spam; what
  floors it — stake, fees, settled-history priority — is unresolved.
- **k-cohort sybil costing** (T2 × P4; `P4-privacy.md`). Adaptive
  k-anonymity is theater if cohort membership is free to fake; pricing
  cohort participation without re-identifying participants is open.
- **Off-chain solver side payments** (T3; `P2-batch-auction.md`).
  Impossibility results say this cannot be designed away; monitor the
  tripwires, keep entry permissionless, accept and name the residual.
- **Off-protocol subsidies** (T1; this register). The inequality
  quantifies over the design's own schedules; external grants and
  airdrops can re-fund wash loops from outside. The register can only
  enumerate known external budgets and page on cluster anomalies.
- **Reliance denomination under U14** (T5; `P3-guarantee-coupling.md` +
  `factbond/docs/plans/insurance-products.md`). Indemnity needs a value
  for legs priced in personal tokens; declared-at-purchase coverage plus
  caps is the v1 proxy, its incentive-compatibility unproven.
- **Semantic drift inside accepted vocabulary** (T6;
  `catalogue-bootstrap.md`). Capture that never trips a dispute leaves
  no loss experience to audit; the standing signal is silent exactly
  here.

## What this document does not promise

- **The register is not exhaustive.** T1–T9 are the attacks with
  researched precedent; new entries get new IDs. It governs what is
  listed, not what exists.
- **Tripwires detect; they do not prevent.** Prevention is by
  construction in the owning documents; a page is a human's problem
  arriving late, by design.
- **The researched numbers are other systems' history** — LooksRare's
  1.34%/day, the $750/$7M ratio, Linea's ~40% — cited exactly, never
  forecasts of loopmarket's own attack surface.
- **What green does not mean, per subsystem:** settlement ≠ delivery (U3
  certifies re-verification under pinned roots); certified ≠ true (F7,
  verbatim, on every surface); premium ≠ probability (a price under
  capital constraints and attack); postage ≠ permanence (stamp TTL is
  the offer's real lifetime); k-anonymity ≠ unlinkability (a
  pseudonymous offer history is a mobility trace); a green Phase-0 ≠ a
  safe mechanism (model risk is not simulated away).
- **The ordering is a 2026-08 judgment**, not a law; G5 exists because
  it will be wrong in some direction. Only the IDs are promised stable.
