# loopmarket — adoption and thickness

Status: design, 2026-08-07. Decided here: vertical selection scored on oracle
cheapness × cycle density, with the ordered launch list (Swarm substrate as
nursery → digital services → supply-chain triads → physical niches on
locker+countersign oracles); bridge liquidity as budgeted launch
infrastructure — a solver species, never a protocol change; loop-length
discipline; pooled batch runs pulled forward for thin verticals; the broker
surface as software fed by the match-degree ladder; personal-token hygiene,
in-loop cancellation defended as the design's strongest economic property.
Open here: on-chain token representation (discussion-agenda item 7); bridge
funding under U13; pooled-run cadence and cold-start statistics; broker
compensation; ex-ante cycle-density estimation.

This document answers the question every mechanism doc in this corpus defers:
where do the first loops come from? Solver ecology, batch auction and
guarantee fabric are worth nothing over an empty book — solver sophistication
is strictly downstream of book thickness. Companions: `P2-batch-auction.md`
(the beats pooled runs anticipate; fees and rewards), `P2-loop-selection.md`
(the failure-aware objective that prices loop length; chains and bridge
donors), `P1-federated-book.md` (postage as the offer's rent and sybil
floor), `P3-guarantee-coupling.md` (the oracle roster the vertical ordering
follows), `ontodag-coupling.md` (the match-degree ladder the broker
consumes), `catalogue-bootstrap.md` (annotation incentives), `THREATS.md`
(T1, T2, T7, T8 all have adoption-phase surfaces). The conceptual ancestor is
the loop-economy essay's "The path in", turned here into scoring and gates.

## 1. Thickness is the binding constraint

Every civilian relative met the same constraint; outcomes rank by how each
bought thickness. **LETS died thin**: volunteer governance burden, dated
tooling, and above all a small stale offer set under which the
coincidence-of-wants problem re-emerges — turnover stayed trivial, members
churned; time banks added "equal time, equal value" pricing, suppressing
exactly the heterogeneous trades that thicken a market. **Sardex bought
thickness with human brokers**: B2B mutual credit at EUR-parity prices,
~€50M/yr volume by 2015 at ~3–4k SMEs (€212M cumulative by 2017), and the
load-bearing ingredient was the broker desk actively arranging trades and
steering positive balances toward spending — the volume was broker-made, and
growth stalled where broker labor did. **WIR institutionalized it**: Swiss
mutual credit since 1934, >60,000 members (~45,000 SMEs) at peak, CHF 1.6B
turnover in 2006, kept circulating by statute — CHW non-convertible, official
members obliged to accept ≥30% WIR (§7 returns to this pair). **AJPES
legislated it**: Slovenia's compulsory monthly multilateral set-off of
overdue inter-firm obligations, running ~three decades, ~€680M set off in
2012 in a two-million-person economy; compulsory registration solves book
thickness by law, and the 111-month study of its data (arXiv:2605.02436)
attributes an average 37.9% (range 31.8–47.2%) of cleared value to
trade-credit flow mechanisms.

The gradient — LETS fail at hundreds of members, Sardex sustains at thousands
with brokers, WIR institutionalizes at tens of thousands, AJPES clears the
most under compulsion — is the design brief. loopmarket has none of those
levers (no law, no broker payroll, no acceptance quota), so its thickness
must be *engineered*: chosen verticals (§2), injected liquidity (§3), short
loops (§4), pooled runs (§5), brokers as software (§6). Trustlines Network is
the standing warning for skipping this document: generic transitive-IOU
infrastructure, technically sound, essentially dormant — infrastructure
without a seeded economic loop gets no usage.

## 2. Vertical selection: oracle cheapness × cycle density

A launch vertical is scored on two factors — committed as the selection rule,
not a menu. **Oracle cheapness**: how close leg fulfillment comes to
parametric settlement off a canonical feed with no dispute layer (the
parametric-first doctrine, `P3-guarantee-coupling.md` §4; primary home
`factbond/docs/plans/evidence-policy.md`). **Cycle density**: how often the
vertical's wants already close into 2–3-leg cycles without recruitment. Both
are about spending nothing: cheap oracles mean the guarantee fabric is not a
launch dependency; dense cycles mean no waiting on a k-way coincidence.

| # | vertical | oracle | cycle density source |
|---|----------|--------|----------------------|
| 1 | the Swarm substrate itself | free and perfect | every node buys and sells the same services |
| 2 | digital services / agents | checksum, zkTLS, signed feeds | agents compose services into pipelines |
| 3 | supply-chain triads | countersign on invoice-shaped legs | cycles pre-exist in the invoice graph |
| 4 | campus/neighborhood niches | locker + countersign | geographic closure, recurring routes |

**1 — the nursery is the substrate (decided 2026-08, lands with P1).** The
storage network the book lives on is itself made of digitally verifiable
service commitments — storage, bandwidth, postage prepayment — and digital
legs come with free, perfect oracles: the network can *prove* a chunk is
stored (the redistribution game exists to do exactly that). The essay's
ouroboros is an engineering plan: the earliest profitable loops provision the
system that hosts them. P1's postage economics already open the door — stamp
top-up is permissionless, so "solvers subsidize the books that feed them
loops" (`P1-federated-book.md` §6) is a loop leg waiting for an offer form.
The dogfood book is where the stack meets reality on stakes no one cries
over.

**2 — digital services, agents first.** Anything whose performance is a
checksum or a web-visible record: compute jobs, data transfers, API credits,
hosting, indexing. zkTLS and signed feeds make fulfillment parametric or
nearly so, and the natural first customers are AI agents composing services
into pipelines — converging with factbond's agents-first wedge
(`factbond/docs/plans/insurance-products.md`) and the ontodag agents-first
decision. Watch item and potential collaborator: Solar Punk's Swarm AI Data
Exchange (April 2026 Swarm Accelerator Hackweek) — ACT-encrypted publication
with x402-gated paid access, the same substrate, explicitly agent-driven
commerce; its x402 pattern is also a candidate for paid book access or
solver-fee collection.

**3 — supply-chain triads.** Invoice-shaped obligations are where cycle
density is *measured*, not hoped for: pure cycles clear ~9.5% of debt on 1.28M
Italian invoices (arXiv:2507.22309, Fig. 10); obligation clearing freed ~25%
of net internal debt on real Sardex data (Fleischman & Dini, JRFM 13(12):295,
2020 — 24.6% of transaction value cleared via TETRIS on the May 2019
network); the Sardex network studies find short transaction cycles prevalent
(1,477 businesses, 48,170 transactions in the studied window). The
recruitment rule follows: **recruit pre-existing closed triads — a firm, its
supplier, its supplier's customer whose obligations already close — never
generic members.** One triad adds a settling loop; three unrelated firms add
three orphan offers.

**4 — physical niches, chosen for density and low stakes.** Campus parcel
relays, neighborhood grocery legs through locker banks: recurring routes in a
closed geography, stakes small enough that countersign (optimistic,
value-bounded, audited) plus the locker oracle (operator-signed deposit and
collection events, readable via zkTLS off tracking surfaces, no partnership
required — attesting handover, never contents) suffice. This is where the
guarantee fabric accumulates its actuarial tables before anyone ships a
piano. New verticals start as lemons country (T7, `THREATS.md`): per-maker
acceptance limits and wide premium priors (`P3-guarantee-coupling.md` §5) are
the quarantine.

One incentive note spanning all four (owner: `catalogue-bootstrap.md`): the
GoodRelations lesson is that annotation happens only when the annotator is
paid immediately — fail-closed matching supplies the payment, since an
unannotated offer is invisible. Adoption engineering invests in
authoring-cost reduction, never evangelism.

## 3. Bridge liquidity: the cheapest thickness multiplier

The Cycles liquidity curve is the design basis, and it is dramatic: on the
1.28M-invoice dataset, zero external liquidity clears ~9.5% of debt; liquidity
worth 10% of total debt clears ~50%; 20% clears ~70%, plateauing near net
internal debt (arXiv:2507.22309, Fig. 10). A small external-asset overhang
converts the cycle-only regime into near-full clearing. loopmarket's
instrument already exists and needs no mechanism: a **bridge offer** — an
offer whose Thing is itself a currency (ARCHITECTURE.md §2, §10). One
stablecoin-collateralized participant posting symmetric ask/bid pairs (buys
the vertical's staples for stablecoin and sells stablecoin for them, at a
spread) is the cheapest thickness multiplier available: it turns every
almost-cycle failing only on a money leg into a settling loop.

Decided (2026-08, lands with the first vertical launch): the launch budget
includes one capitalized bridge maker per vertical, operated as ordinary
maker infrastructure — bridges are ordinary makers, no new mechanism; the
*decision* is budgeting one rather than waiting for a speculator to emerge.
Discipline, in order of sharpness:

- **A bridge is a maker, not a subsidy.** It earns its spread or it shrinks.
  Anything paying bridges beyond their spread is a rebate, and U13 — quoted
  exactly: **"wash-loop budget-balance by construction, fees external-asset
  only"** — must hold with the bridge inside the attacker's principal set: a
  wash ring that owns the bridge still pays more in fees than all subsidies
  it can reach (T1, `THREATS.md`; the Phase-0 self-dealing playbook runs
  this case, `factbond/docs/plans/phase0-simulation.md`).
- **The stablecoin leg is settlement cargo, not a scoring numeraire.** U14 —
  "numeraire-free scoring" — is untouched: the bridge's external asset
  prices its own legs, never anyone's score.
- **A bridge that gives before it receives is a bridge donor** and needs a
  bond once chains land — receive-before-give is the P2 rule, bonded donors
  are P3 (`P2-loop-selection.md` §5). Until then, bridge legs settle inside
  one atomic commit like everything else.
- **CRC is an optional bridge asset, not a dependency.** Where both
  counterparties are Circles users a leg can clear in CRC — same chain, and
  demurrage on bridge *inventory* aligns with tokens that should not be
  hoarded (§7). Optional means optional: no leg requires it.

## 4. Loop-length discipline

Thickness decays with loop length: a k-loop needs a k-way coincidence of
wants (Roth, "What Have We Learned from Market Design?", Economic Journal
2008), and Roth–Sönmez–Ünver (AER 2007) showed 2- and 3-cycles capture most
of the welfare in dense pools. Reliability argues the same direction with
kidney-exchange brutality — one dead leg kills its cycle, and whole-cycle
failure compounds per leg — which is why `P2-loop-selection.md`'s
failure-aware objective prefers short loops *endogenously*, with a length cap
as belt-and-braces. Two adoption-side consequences. The launch metrics
(Gates) track the share of surplus from ≤3-leg loops — if low, the book is
thin and papered over by fragile long cycles. And standing bridge offers are
the altruistic-donor analog: in kidney exchange, non-directed donors turned
fragile simultaneous cycles into robust chains; here, a standing
widely-acceptable bridge offer converts a fragile k-loop into two short ones
through the bridge. Long structures are chains when they land, never long
cycles (`P2-loop-selection.md` §5).

## 5. Pooled batch runs for thin verticals

Dynamic-matching theory says batching gains are modest *unless the market is
thin and agents patient* (Ashlagi et al., arXiv:1301.3509; the
Akbarpour–Li–Gharan JPE 2020 line) — which is exactly a launch vertical.
Kidney exchange answered thinness with periodic match runs over a pooled
database, not continuous matching. Decided (2026-08, lands with the first
thin vertical — a deliberate pull-forward of part of P2): thin verticals run
on a published cadence — offers accumulate, a scheduled solve packs the
pooled book, everything settles in one run — instead of P0's first-valid-wins
racing. This is an adoption decision, not an auction one
(`P2-batch-auction.md` §1 records the division): beats are short and exist
for proposal competition; pooled runs are long and exist for coincidence
accumulation. A vertical graduates to standard beats via gate G4. The cadence
is published in advance — AJPES's cutoff-calendar discipline, monthly for
three decades — because a predictable solve is what lets makers leave offers
standing. Statistics discipline from day one: U12 — quoted exactly:
**"reward/reputation statistics count settled fee-paid loops only"** — since
the thin period is precisely when prior-farming and statistics pollution are
cheapest (T2, T8, `THREATS.md`; the cold-start interaction is registered in
`P2-loop-selection.md`'s open problems).

## 6. The broker surface: the Sardex desk as software

Sardex's volume was broker-made, and the broker's job decomposes into exactly
what the match machinery computes. Decided (2026-08, lands with P1 as solver
tooling — a solver species, not a schema or protocol change): the
**almost-loop API** — given a book snapshot, return ranked hypotheses of the
form *"this book needs offer X (concept set, window, region, price band) to
close N loops worth S total log-surplus."* It is powered by the match-degree
ladder (owner: `ontodag-coupling.md`): five degrees — exact;
full/subsumption (today's `satisfies`); plug-in (offer too general, one
refinement away); potential (cones intersect; concept abduction yields H =
the missing atoms, ranked by weighted |H|); fail-unknown (U7, hard-closed) —
preserving Di Noia's monotonicity criterion: adding detail to an offer never
worsens its rank (Di Noia, Di Sciascio, Donini, Mongiello, WWW2003; JAIR
2007). Degrees 3–4 are the broker's raw material.

Near-misses have **three consumers and only three** — never settlement:

1. **Solver speculation.** The essay's speculator species: a solver that
   finds an almost-loop can post the missing leg itself, becoming market
   maker of last resort. If posting it means giving before receiving, it is
   a bridge donor and waits for P3 bonds (§3).
2. **Maker recruitment.** "Your café shelf would close three loops this
   week" is the Sardex broker call, generated instead of salaried — and the
   recruitment instrument for §2's triads: the API names which third party
   completes a two-firm almost-cycle.
3. **Catalogue demand signals.** Recurring abduced atoms in no offer are
   demand for missing catalogue structure — routed to
   `catalogue-bootstrap.md`'s pipeline and priced as factbond assertion
   opportunities.

Settlement never sees any of this: `check_match` remains the exact boolean
truth, near-misses never enter it, U7 stays strict. If broker software ever
becomes a quoting tier, the CIP-72 rule is pre-committed
(`P2-batch-auction.md` §7): a quote is reward-eligible only if the quoter
later proposed an execution at least as good — brokers eat their own hints.

## 7. Personal-token hygiene

loopmarket's personal token is stronger than every deployed relative on one
axis, and this section exists to keep it that way: **tokens exist only long
enough for a loop to pass through the maker and cancel** (ARCHITECTURE.md
§2). No balance, therefore no cash-out surface, therefore no fiat gravity.
Circles v1 is the counterfactual run at scale: in the Berlin pilot, ~90% of
CRC earned by participating businesses was cashed out to EUR via the subsidy
program; no closed B2B loop formed (a Bali deployment reportedly fared better
precisely because a real closed exchange loop existed). WIR survived nine
decades by buying the same property with statute — non-convertibility plus
the ≥30% acceptance quota. In-loop cancellation buys it with arithmetic. It
is the strongest economic property in the design; features are judged against
it, not the reverse.

The rule (decided 2026-08, binding on all future design docs): **any feature
that lets token balances persist across settlement — standing bridge
inventory, partial fills, cross-beat chains, credit extension (Cycles'
assignment/overdraft modes, when analogues land) — ships with demurrage,
expiry, or acceptance-quota countermeasures from day one.** The working
precedents are WIR's statute pair and Circles v2's 7%/yr demurrage;
retrofitting hygiene after fiat gravity appears is what Circles v1's
post-mortem proves impossible. The fungibility fallback, named now so nobody
reinvents it: if personal-token illiquidity ever blocks a needed feature,
Circles v2's group currencies — personal tokens wrapped 1:1 into a
community-fungible ERC-1155 group token — are the adoption path.

**The on-chain representation question (open; discussion-agenda item 7).**
When P2's settlement contract lands, do personal tokens materialize on-chain
at all — and if so, as Circles v2 avatars (live on Gnosis since May 2025:
ERC-1155, 1 CRC/hour issuance, 7%/yr demurrage, binary trust edges with
expiry, ~10,000 active users as of Nov 2025, and a Pathfinder routing service
that is the loop solver's architectural sibling) or as minimal native tokens
minted and burned inside the settlement transaction? The tension: demurrage
prices *holding*, and strict in-loop cancellation leaves nothing held —
demurrage is coherent for the bridge-asset role (§3) and group-currency
balances, arguably meaningless for a token that lives one commit. Adopting
Circles buys audited contracts, an existing trust graph, interoperability;
minimal native tokens buy exact fit and no imported governance. Flagged for
discussion, not decided here.

## 8. Positioning and the competitive read

The pitch to a cash-strapped SME is liquidity-saving, not ideology, and the
numbers are other people's production history: obligation clearing alone
frees ~25% of net internal debt, ~50% with mutual credit, on real Sardex data
(Fleischman & Dini 2020); a 10%-of-debt liquidity injection clears ~50%
(Cycles, Fig. 10); an entire small economy set off ~€680M in one year by
monthly rhythm (AJPES 2012). The macro positioning is WIR's:
countercyclicality — WIR turnover and velocity rise when bank credit tightens
(Stodder, JEBO 2009; Stodder & Lietaer, Comparative Economic Studies 2016) —
a marketplace whose value peaks exactly when its members' alternatives fail.

**Cycles is the competitor to watch, and the read is specific.** Same
mathematical family (MTCS min-cost flow over obligation graphs;
`P2-loop-selection.md` §2 adopts the complexity split), now commercial: $6.4M
raised May 2026 to build "the open clearing network for on-chain finance",
Cycles Prime piloting with Lynq and FalconX, a Cycles Pay stablecoin tied to
the clearing engine. Their trajectory targets financial obligations —
invoices, trade credit, prime brokerage. loopmarket's differentiators, stated
once: (1) **the ontology-typed Thing side** — the graph contains offers that
never were invoices (a café shelf, a truck-day, a compute job), so the
clearable set is categorically larger than any obligation graph; (2)
**permissionless competing solvers** — Cycles runs the solve as the protocol
(TEE + ZK sidecar), loopmarket lets anyone solve and trusts no one who does;
(3) **trust-nothing re-verification** — U3 makes solver output worthless to
forge, which is what makes (2) safe. Where Cycles wins — legally-shaped
invoice netting with institutional counterparties — loopmarket should not
fight; where typed goods, services and spacetime enter the cycle, Cycles'
form cannot follow.

## Gates

- **G1 — metrics pinned before any launch.** Four thickness metrics defined,
  instrumented, abandonment thresholds pre-registered per vertical *before*
  its first offer (the Phase-0 pre-registration discipline): median
  time-to-first-settled-loop for a new maker; settled loops per active offer
  per week; share of settled surplus from ≤3-leg loops; bridge subsidy
  (spread income minus cost, when negative) per unit of settled surplus.
- **G2 — the nursery settles.** A loop provisioning the substrate itself
  (storage/bandwidth/postage legs) settles end-to-end on the federated P1
  stack with parametric verification, repeatably, across ≥3 independent
  makers. Blocks: extending to vertical 2.
- **G3 — bridge budget-balance.** The launch bridge's parameters survive the
  Phase-0 self-dealing playbook with the bridge inside the attacker's
  principal set — U13's inequality strictly negative for the wash ring.
  Blocks: capitalizing any bridge.
- **G4 — pooled-run graduation and abandonment.** A vertical graduates to
  standard beats when settled loops per run exceed its pinned graduation
  threshold for k consecutive runs; abandoned when below its pinned floor
  for k consecutive runs. Both thresholds set at launch under G1, never
  after.
- **G5 — broker conversion.** Almost-loop hints demonstrably convert: a
  pinned fraction of recruitment hints leads to a posted offer, and a pinned
  fraction of those closes a settled loop within one run. Blocks: any
  reward-bearing quoting tier (which also waits on `P2-batch-auction.md`'s
  CIP-72 rule).

## Open problems

- **On-chain personal-token representation** (work package: P2 settlement
  backend, this document with `P2-batch-auction.md`; discussion-agenda item
  7). Circles v2 avatars versus minimal native tokens, including whether
  demurrage is compatible with strict in-loop cancellation or belongs only
  to the bridge-asset and group-currency roles. §7 states the tension; the
  decision needs the settlement contract's shape.
- **Bridge funding under U13** (work package: `P2-batch-auction.md` §9 +
  `THREATS.md` T1; entangled with discussion-agenda item 4 on fees). Who
  capitalizes launch bridges, in what asset, and how a bridge running at a
  loss during bootstrap differs auditably from a rebate channel — the
  wash-loop inequality must hold with the bridge endogenous, and G1's
  subsidy-per-surplus is a tripwire metric, not a budget.
- **Pooled-run cadence and cold-start statistics** (work package:
  `P2-batch-auction.md` + `THREATS.md` T2/T8). How long a run should be per
  vertical, how the cadence shortens toward beats, and how statistics
  accumulate during the thin period when U12-compliant data is scarcest and
  pollution cheapest — jointly with the failure-prior cold-start problem
  registered in `P2-loop-selection.md`.
- **Broker compensation** (work package: `P2-batch-auction.md` §7). An
  almost-loop hint is free to copy once acted on — the free-riding shape
  sealed proposals solve for full loops, unsolved for hints. The CIP-72
  quoting tier is the placeholder; whether hint-making can be paid at all
  without inviting hint spam (T8) is open.
- **Ex-ante cycle-density estimation** (work package: this document +
  `factbond/docs/plans/phase0-simulation.md`). §2's scoring needs cycle
  density *before* a vertical is on the book. Invoice datasets exist for
  triads (the Italian and Sardex data); for digital services and physical
  niches there is no equivalent, and the estimation method — survey, scraped
  complementarity graphs, simulation on synthetic wants — is unchosen.

## What this document does not promise

- **The historical numbers do not transplant.** AJPES had legal compulsion,
  Sardex a broker payroll, WIR a statutory acceptance quota; loopmarket has
  none. The €680M, €50M/yr and ~25%/~50% figures bound what thickness
  engineering can be worth, not what it will deliver here.
- **Bridges multiply clearing; they do not create demand.** The Cycles curve
  operates on obligations that already exist. A bridge over an empty book
  clears nothing, at full capital cost.
- **Countercyclicality is positioning, not a property.** Stodder's finding
  is about WIR at tens of thousands of members over decades; nothing here
  demonstrates loopmarket reaches the scale at which the effect exists.
- **The Cycles read is a snapshot** — mid-2026 facts about a fast-moving
  competitor; the differentiators are structural, the trajectory claim is
  not.
- **Broker hints are hypotheses.** An almost-loop is a near-miss under the
  ladder, never a promise a loop settles — settlement re-verifies everything
  (U3), including everything a broker ever suggested.
- **Nothing here is built.** The nursery, bridges, pooled runs and the
  broker API are decided designs with dated markers; every vertical can fail
  its gates and be abandoned — G1 and G4 exist so abandonment is a
  pre-registered outcome, not an embarrassment.
