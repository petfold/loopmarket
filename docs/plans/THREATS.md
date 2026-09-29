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
that pages a human, and the owning work package. The other half is
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

**Content-sync rule.** Every entry names a primary owner: T1–T3, T7, T8,
T14–T16 and T18 here; T4–T6, T9–T13 and T17 in
`factbond/docs/plans/THREATS.md`. *(Revised 2026-09-28, to stop keeping two
full copies:)* an entry whose primary is factbond appears here as a short
stub — the attack in a sentence, loopmarket's own part of the defense,
tripwire and work package, and a link to the full entry — and is edited
there only. factbond's register does the same for the entries primary
here, so every entry has one full copy; a stub that contradicts its
primary blocks both registers' phase gates (factbond's G4).

## T1 — Rebate/reward-farmed wash loops

*(Update 2026-08-21 — agenda item 4 ratified no protocol fees and **no
protocol emissions at all**: nothing exists to farm, so this attack's
surface is deleted at the root — a stronger defense than the inequality.
The entry is retained as the gate: any future emission proposal must
re-open it and prove the inequality first. U12's ledger is now settled
cost-borne loops — postage + settlement gas — so the statistics-pollution
half of the motive shifts to T8's tripwires.)*

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

Buying the final rung of the dispute ladder when the reliance riding on
it exceeds its capture cost, or griefing with cheap disputes until honest
disputers give up. **Here:** a payout auto-funds the dispute on the edge
that lied (disputer-side funding against wear-down), and the four
adversarial fixtures of `P3-guarantee-coupling.md` §4 must reject or bound
their attacks by construction; per-edge cap utilization pages at 80%.
Work package here: `P3-guarantee-coupling.md`. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

## T5 — Insurance arson — primary: `factbond/docs/plans/THREATS.md`

Insure a fact, then make it wrong. **Here:** a clearing root proves
which cleared legs relied on the insured edge, so cover pays at most what
the insured provably had at stake, minus the premium (F3 exact); per-edge
caps fail closed. Outside clearing, factbond covers a fact someone controls
only by its controller's reserved deposit or a surety (2026-09-28). Work
package here: `P3-guarantee-coupling.md` §3. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

## T6 — Catalogue governance capture — primary: `factbond/docs/plans/THREATS.md`

Patient capture of assertion and adjudication power over hub edges,
bribe markets for edge disputes, re-meaning categories, stuffing offers for
the solver. **Here:** bonds scale with settlement-weighted centrality from
the witness feed, never static degree (`P3-guarantee-coupling.md` §2); the
governance norms are protocol rules in `catalogue-bootstrap.md` (schema
gated and bonded, never re-mean a category, don't tag for the solver);
tripwires: one principal's bonded share over the top decile of
settlement-weighted edges above 25%, offers whose categories their fills
never exercise, schema-merge review latency. Work package here:
`catalogue-bootstrap.md`. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

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
premium feed's inputs are attackable via T2 until volume exists. *Added
2026-09-18:* the defense above is solver-side; the **beat** — winner
determination, the fairness filter, the reserve bid (`P2-loop-selection.md`,
built that day) — scores nominal surplus, so the lemons leg at the best
rate wins the beat and sets every reference even when a bonded
alternative exists — **answered the same evening by admissibility by
declaration (Peter's ruling; `P2-loop-selection.md` §4a, the v5 record):
a maker states the bond floor and witness types it requires of any
counterparty and no leg below them is ever matched, so the lemons leg
reaches the beat only where every member let it**; and should bonds ever weigh in the objective, the
mirror vector is **bond-bought priority** — capital, not quality, buying
selection — not farmable as a statistic (U12/U13 stand) but a bias to be
chosen knowingly. Both registered as `P2-loop-selection.md` §4a.

**Tripwire.** Realized loss/dispute rate of cheapest-decile legs vs the
book median pages at > 3× (initial); acceptance-limit saturation
concentrated on new makers (measures the cold-start tax); once bonds are
enforced, the loss rate of *winning* legs against that of proposals the
beat rejected (does the beat select the lemons?), and the share of beats
won by the top bond decile (does capital buy priority?).

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

Basis risk, the uptake killer: a real loss on a technically true edge, or
a payout with nothing lost; policy ambiguity is its cheapest form.
**Here:** the fits-within half of every dispute is checked against the
pinned root (F8, `proof-fabric.md`); an offer's `oracle` field carries the
policy hash, so the policy is the contract (`P3-guarantee-coupling.md`
§4). Work package here: `P3-guarantee-coupling.md` §4. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

## T10 — Assertion-mining & assertion spam — primary: `factbond/docs/plans/THREATS.md`

Farming a reward for asserting, or spamming assertions. Closed by
factbond's F9 (nothing is ever paid for asserting); nothing on loopmarket's
side. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

## T11 — Self-dispute laundering — primary: `factbond/docs/plans/THREATS.md`

Disputing your own assertion from a second key to wash stake or history.
A loss on the fees alone, and surviving a dispute is never a positive
signal (factbond, 2026-09-28); loopmarket's wash-loop inequality (U13)
applied to disputes. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

## T12 — Correlated adjudicator failure as reserve shock — primary: `factbond/docs/plans/THREATS.md`

One final rung failing, or captured, poisons every exposure that ends at
it at once: a reserve shock. factbond's reserve and ladder; nothing on
loopmarket's side beyond T4's fixtures. Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

## T13 — Evidence-class rot — primary: `factbond/docs/plans/THREATS.md`

An evidence class decays (a camera fleet's certificates revoked): rulings
that relied on it must degrade, never certify garbage. factbond's evidence
policy owns the roster, demotion and reopening; loopmarket consumes the
roster (`P3-guarantee-coupling.md` §4). Full entry: [`factbond/docs/plans/THREATS.md`](https://github.com/petfold/factbond/blob/main/docs/plans/THREATS.md).

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
registry event on the EVM chain Swarm settles on — the one channel since 2026-09-14, GSOC dropped;
`P1-federated-book.md` §4), maker books are public
feeds, and recordstore absence proofs demonstrate "offer X is absent
from root R" mechanically while X sits on its maker's feed. Since
2026-08-21 the manifest carries `announcement_root` — a commitment to
the folded input set — so completeness is first-class and computable by
anyone: (announced set) − (makers under `book_root`) is a proof of
omission, which also makes **pay-to-be-indexed legible as censorship**
(the item-4 revenue ruling: aggregators charge for serving, never
inclusion). Fold
decisions and rejections are attributed speech acts in the aggregator's
own `provenance_root`. Entry is permissionless, and reading never
requires an aggregator: any solver can fold maker feeds directly — a
censored offer is uncaptured surplus a competitor collects. *(Landed
2026-09-04, in memory: `federation.audit_manifest` computes the
omission set — `offer/` and `withdraw/` records an announced maker book
holds that neither entered `book_root` nor earned a `reject/` — and
returns recordstore absence proofs per record; `tests/test_federation.py`
covers the silent drop and the eaten tombstone, and
`examples/demo_federation.py` runs the solver-self-fold recovery.)*
*(2026-09-14: the announced set is the chain's, so completeness is one
reader's computation — `audit_manifest(expected=channel.announced())`
reports a never-folded book as an omission with a proof — and comparing
aggregators with each other is no longer how they are trusted. The CLI's
`fold` recomputes the fold from the announced set under U8 by default,
manifests being caches. The live variant against a deployed contract is
still open.)*

**Residual.** Since 2026-09-14 auditability no longer depends on the
number of aggregators: any reader convicts an omission against the
chain's announced set alone. What plurality still buys is availability
and latency — the aggregator-economics open problem
(`P1-federated-book.md`; `adoption-and-thickness.md`) is about who runs
the always-on folders, not about trust. **Owner
directive (2026-08-21): distributed, permissionless and censorship-proof
is loopmarket's main value; several independent aggregators are the
deployment floor, a single-aggregator steady state is a failure
condition, and stronger decentralization of the read path is a mandated
investigation before P1 completes.** The P1 settlement-instance
chokepoint stands until P2's verifiable settlement; no aggregator remedy
touches it.

**Tripwire.** `audit_manifest` against the chain's announced set on every
manifest read — an omission pages. Manifest `book_root` divergence not
explained by input-set differences (a sanity check now, not the trust
basis). The count of independently-operated manifests, for availability.
A planted-offer probe:
publication-plus-announcement to manifest inclusion, measured across
every watched aggregator — any manifest that never includes the probe
pages.

**Work package.** `P1-federated-book.md` §2/§8 (fold, provenance,
admission-by-reference); `adoption-and-thickness.md` (aggregator
economics, section added 2026-08-21); the settlement half:
`P2-batch-auction.md`; the read-path decentralization investigation:
registered, pre-P1-completion.

## T15 — Register liveness as denial of service on its issuees (added 2026-09-25)

**Attack.** The counterparty gate (`counterparty-gate.md`) reads a
statement's status against pinned register roots and fails closed: a
register that goes silent past a requirer's `max_root_age` invalidates
every statement it issued, for every requirer that strict. Taking a
register offline, or outrunning its heartbeat with a network partition,
excludes all its issuees from every leg that requires them. Motives: a
competing issuer, a captured root, or plain outage.

**Economics.** The attack costs the register nothing if it is the
register's own act, and costs an outsider only the register's
availability. Its value scales with how many makers depend on one
register and how short requirers set their bounds.

**Defense (by construction).** Registers are transparency logs with a
declared cadence and consistency proofs between roots
(`credentials-cover-and-options.md` D7); mirrors are content-addressed
snapshots on Swarm that proposals pin, so a register's last root stays
readable after it stops; a requirer whose bound is shorter than a
register's cadence excludes it by its own choice; trust roots are the
requirer's, so a captured or silent root is routed around by naming
another; "two inconsistent roots signed by one register" is a specific,
refutable fact against the register's bond. The residual is the price of
hard-fail, accepted and named: a requirer who sets hours bears hours.

## T16 — Puppet third parties and ruling-count washing (added 2026-09-25)

**Attack.** Keys are free, so a giver names its own puppet as a leg's
resolver or inspector, or a would-be adjudicator manufactures a record of
"unreversed rulings" with puppet cases (a puppet asserts, a puppet
disputes, the adjudicator rules, nobody reverses) at the cost of the burn
slice per case. The same for inspection counts.

**Economics.** A puppet key costs nothing; a manufactured ruling costs
the burn slice plus a fee the washer pays to itself. Any acceptance
criterion that counts volume is bought at that price.

**Defense (by construction).** No acceptance criterion counts. A
requirement admits a resolver or an inspector by key, by an accrediting
root whose own collateral is at stake, by a deposit floor, or by the
absence of reversals within a look-back window
(`credentials-cover-and-options.md` D7 C4, D4 E2); the resolver is fixed
at clearing and must be within the requirer's acceptance; its deposit is
what a ruling puts at risk, and a reversal at the final rung forfeits it
and enters the calibration ledger; a puppet that slips through only
delays, and its deposit pays for the delay. The only positive entry the
ledger carries for an adjudicator is a ruling escalated at doubled stake
to the final rung and upheld there, which costs a real review. The cheap
formality stays: a resolver or inspector is never the key of a party to
the leg or of the deposit's maker. U12's rule, applied to judges.

## T17 — Defamation on a permanent store — primary: `factbond/docs/plans/THREATS.md` (added 2026-09-28)

*(Mirrored from factbond's entry; condensed.)* A contest that is a label
("K is a fraudster") instead of a refutable fact buys, for a stake, a
permanent public accusation no ruling can clear, against a person's key.
Defense: factbond's adjudicator path (F4, `factbond.procedure`) refuses a
contest that names no claim record its policy covers, in the accused's
favour; the `notice/` of rung zero passes between the parties and is
public only when a bonded act cites it after the cure deadline, so a
cured matter leaves nothing public (R6's gate here). Residual: the bonded
act itself stays public, marked by its refusal.

## T18 — Claim hijack at the escrow's consumer edge (added 2026-09-29)

**Attack.** A reservation whose resolver is factbond's `Assertions` is
held by whatever claim names it: `assert_` is open to anyone, and the
escrow's `hold` accepted every call from its resolver. factbond's
`retract` closes a claim with outcome 0, which the escrow read as a
refutation and refunded the giver. So anyone could assert and at once
retract a claim on any such reservation and void it: the giver's friend,
or the giver, escaping a reservation before its window for the assertion
fee, with the claim and the cancellation ladder bypassed. Two neighbours:
a claim above the reservation, which the escrow's `resolve` refused, so
it could never certify and its stakes waited on a refutation; and a
recipient whose address refuses payment, which blocked any settlement
paying it, a ruling included.

**Economics.** The void costs factbond's fee (0.001 xDAI on the Gnosis
deployment) against the whole reservation. The blocked payout costs the
refuser nothing and holds the wanter's payout and both factbond stakes.

**Defense (by construction; E1 of the 2026-09-25 development sequence,
built 2026-09-28).** The escrow reads the claim inside `hold` (factbond
writes it before calling, USER-GUIDE §6) and opens only the wanter's own,
naming the giver as `about` so the giver's watcher is told, with a payout
above 0 and within the reservation, and challenge and ruling windows no
shorter than the reservation's `minChallenge`/`minRuling`; one claim at a
time. A retraction reopens the reservation, since nobody ruled; a close
that arrives after the parties settled (a split, a countersign) is
acknowledged without moving anything, so the resolver's case always ends;
a settlement's payout that is refused (or that burns the forwarded gas)
is credited to `owed` for the recipient to `collect`. `assign` is refused
while a claim is open, so a claimant cannot sell a claim and then drop it.
Gates: `tests/test_escrow.py` (`test_the_escrow_opens_only_the_wanters_claim_and_a_retraction_reopens`,
`test_a_split_while_a_claim_is_open_lets_the_resolvers_case_end`,
`test_a_refused_payout_is_credited_and_never_blocks_the_ruling`).
**Live exposure:** the old Gnosis pair (escrow `0x299CE4…69Bf`, Assertions
`0xfa6f…BF99`) has the hole; its one factbond-resolved reservation settled
at the 2026-09-19 gate, and since 2026-09-29 the config names the
redeployed pair (`0xA49Cc9F9dab95aAB7093F138A084027ef66dD936` with `0x3c1B4C944398bcc30890d6A6c78f1F9AA2dFe270`), where the E3 gate showed
the giver's own claim refused and a retraction reopening the reservation
live. **Residual, factbond's:**
`Assertions` calls its consumer without isolating a revert, so a consumer
that reverts in `resolve` strands the case and both stakes, and one that
reverts only on 0 makes its claims unrefutable; the defense here makes
this escrow's `resolve` never revert on a claim it opened, and the
general fix is on factbond's side.

## The ten fee/bond rules (by construction)

*(Standing note, 2026-08-21: with agenda item 4 ratified there is no live
fee schedule — these rules bind today's real cost floors (postage,
settlement gas, bonds) and any future emission proposal, which must pass
them before existing.)*

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
- **Closed 2026-09-25** (`credentials-cover-and-options.md`): the item
  denial-of-sale attack (a cross-maker exclusivity rule on a derived
  `item(h)` blocked any item for free; the rule is per maker, exclusivity
  priced, D5); exit by silence (a held reservation could quiet-settle to a
  silent asserter; only a ruling releases it, D10 C1); and T5's indemnity
  rule now stated for cover (`min(limit, provable loss) − deductible`,
  net of the giver's reservation after assignment, D3).

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
