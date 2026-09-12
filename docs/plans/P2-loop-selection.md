# loopmarket — loop selection

Status: design, 2026-08-07. Decided here: the complexity boundary
(divisible legs are a flow LP, indivisible legs a bounded-cycle packing
ILP); exact winner determination for small beats with the deterministic
greedy as fallback; a failure-aware expected-settled-surplus objective;
chains admitted receive-before-give only until the bond fabric exists;
pre-commit netting under maker-declared tolerances, one netting domain per
beat; lexicographic tie-breaking extending U6; composition on the want side only — one want, many unconditional gives, the buyer pays once and clearing splits (§10, 2026-09-07; declared parts first and a give-side *floor* instead of give-side parts, 2026-09-12); the cleared object is a value-conserving *circulation* in a generalized flow network with hyper-legs — cycles are its smallest case, clearing prices are its node potentials, cycle cancelling its classical solver (§11, 2026-09-07). Open here: chain atomicity
across beats; failure-prior cold start and its wash-loop interaction; the
mixed divisible/indivisible decomposition; tolerance semantics under U9.

This document names the optimization problem P0 deliberately dodged:
choosing *which set* of loops settles in a beat, not finding *a* loop.
Companions: `P2-batch-auction.md` (beat mechanics, sealed bids, scoring,
the reserve bid this document preconditions), `P2-clearing-pricing.md`
(rates inside the selected loops), `P3-guarantee-coupling.md` (the bonds
that unlock bridge donors), `P1-federated-book.md` (the per-maker books
whose merge feeds a beat), and `THREATS.md` (T1/T2/T3/T8 all touch
selection). ARCHITECTURE.md §7 records the arithmetic this builds on.

## 1. Selection is packing, not search

The baseline (`graph.py`) answers "does a profitable cycle exist?" —
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
  thickness argues the same way: a k-leg loop needs a k-way coincidence of
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
  for the product test, incomplete for feasibility. Cycles that would
  clear are silently invisible.
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
  balance — is an open problem owned by `P2-clearing-pricing.md`.
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
  is registered in `P2-clearing-pricing.md`.

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

## 10. Composition: one want, many gives (decided 2026-09-07)

Two examples set the problem. A traveller at midnight wants a toothbrush
at the hotel reception within thirty minutes; a petrol station 300 m away
sells one; a courier can carry it. Six people are needed to lift a heavy
object; the buyer wants the object lifted, not six separate labour
contracts. In both, **the want is one thing and it takes several gives to
satisfy it**, and the buyer should pay once, not once per give.

**Rejected: the transformer as a give plus a want.** The natural first
drawing makes the courier a maker who *wants* the brush on the forecourt
(bid 3) and *gives* the brush at the reception (ask 12), the 9 being the
carriage. Value-balances at every node, and it is how the talk first drew
it. It fails on the offer model: offers are unconditional standing
commitments, so the courier's want can be matched and cleared on its own,
in some other loop, leaving them holding a toothbrush at midnight. Making
the two offers clear together or not at all is a give-side bundle — the
combinatorial door this document keeps shut (open problems, "price and
capacity schedules": cross-offer conditional pricing excluded). Rejected
alongside it: the buyer posting n separate wants and paying n times — n
independent loops with no atomicity, so five lifters can clear and the
sixth not.

**Adopted: composition on the want side.** Gives stay what they are —
unconditional, one thing each, a plain service where the thing is work:
the station gives *brush at the forecourt* (3); the courier gives
*transport of a small item, forecourt cell → reception cell, 00:15 → 00:35*
(9); each lifter gives *one person-hour of lifting at place P, time T*.
The conjunction lives in the single want, which is one offer and
therefore one fill decision, so all-or-nothing is free: it is U1's "one
offer, one fill" doing its ordinary job. Two composition rules make a set
of gives satisfy a want:

- **By operator, along a dimension.** Transport shifts the place
  coordinate, storage shifts the time coordinate, exchange shifts the
  denomination. `brush@forecourt ⊗ transport(forecourt→reception,
  00:15→00:35) ⊑ brush@reception@00:35`. The operator's give names its
  input and output coordinates; matching checks that the input fits the
  other give and the output fits the want. This needs spacetime as
  dimension terms in the shared catalogue (P1's open item;
  `ontodag-coupling.md` §5) — the same terms one-query candidate
  generation needs, so it is one investment, not two.
- **By aggregation, along quantity.** Σ gives ⊑ want when the gives are
  the same category and quantities add: six person-hours of lifting. The
  want carries a minimum quantity (fill-or-kill at ≥ 6); each give is
  unconditional and indivisible at one. This is the flow LP of §2 with a
  lower bound on one want, nothing more.

**Paying once.** The buyer's give is money, and money is divisible, so
one give of "up to 12" (or "up to 60") is split across the fills at the
per-leg clearing prices `P2-clearing-pricing.md` already defines — 3 and 9
here; whatever the six asks and the equal log-surplus split produce there.
No new record on the buyer's side: partial fills of a divisible give are
the qty-as-flow-capacity mechanism of §2, and the settled-quantities v3
record (`P2-clearing-pricing.md` §8) already has to grow per-fill
quantities for it.

**Shape.** The result is not a cycle and does not decompose into cycles:
the buyer has one inflow (the composed thing) and k outflows (the split
payment), or k inflows and one outflow if you count the gives. It is a
balanced flow with a hub node. The principle the essay states as "the
numbers cancel in-loop" is exactly "the numbers cancel at every node, on
that node's own scale"; a simple cycle is the case where every maker has
one in and one out. §11 names the object: a circulation. §2's flow formulation already carries this; §1's
packing gains hyper-legs (one want variable bound to several give
variables), which is a constraint shape the ILP handles natively and the
P0 Bellman–Ford solver cannot see at all — a solver that composes is a
different species, and per U3 clearing re-verifies the composition
(operator input/output fit, quantity sum, per-node balance) exactly as it
re-verifies a leg.

**What changes where.** Matching: `check_match` stays the pairwise truth
for simple legs; a `check_composition(want, gives)` sits beside it,
re-run by clearing. Records: a `fill/` of a composed want must name every
give it consumed (today it names only the loop); a give's fill gains a
quantity. Catalogue: dimension operators as terms. Pricing: the surplus
split runs over k+1 nodes with the hub counted once. Settlement risk on
composed legs: with the service model nobody is merchant of record — the
station is paid for a brush on the forecourt, the courier for carriage —
so the buyer bears the courier's non-delivery, priced by P3's bonds like
any other leg; the reseller routing (courier buys, then sells delivered)
is the *maker's* choice to offer, and then the courier bears it. Both are
expressible; the protocol prefers neither.

**Declared parts (decided 2026-09-12).** A third example set the order
of work: a theatre ticket with transport to the theatre — no ticket
without a way there, no transport without a ticket. The theatre gives a
ticket, a bus company gives carriage of a person from one cell to
another in a window; neither cares about the bundle, only the buyer
does, so it is want-side composition exactly as above, with the person
as the thing being moved. What the case adds is *who names the parts*.
The operator rule above is the **discovered** form: the buyer states the
end state ("brush at the reception at 00:35") and the solver binds the
courier. The theatre case is the **declared** form: the buyer names the
parts — a ticket at the venue in the evening window, transport from home
to the venue arriving before it — and the solver only has to find one
give per part. Declared parts are the simpler species, need no operator
algebra and no spacetime terms in the shared catalogue, and are what a
person types (`cli.md` §13: `draft`, `drafts`, `compose`); they are the
first form to build, and the discovered form lands later on the same
record. Fixed by the same ruling:

- *Record (v3).* A want may carry **parts**: a list of two or more
  `Thing`s, canonically ordered by their canonical bytes so U2 holds; a
  `fill/` of a composed want names every give it consumed and the
  quantity taken from each (already listed under "what changes where").
  Gives are unchanged: one `Thing`.
- *Matching.* `check_composition(want, gives)`: exactly one give per
  part, each part covered by its give under `check_match`'s own gates
  (kinds, validity, window overlap, disc intersection, quantity and
  unit, pins, subsumption), the gives from any makers other than the
  buyer — two parts from one maker are fine — and the buyer's node
  balanced on its own scale under the clearing split. Clearing re-runs
  it (U3).
- *No prices on parts.* The buyer prices the composed thing once, "up
  to 60"; the split across the gives is clearing's
  (`P2-clearing-pricing.md`), never the buyer's guess.
- *No cross-part constraints in the protocol.* "Transport must arrive
  before curtain" is the buyer's spelling of the two windows —
  `cli.md` §6's rule, declare in the direction you know — not a
  constraint language. A part's terms may name catalogue names that
  resolve to values (`from(home)` → `from(u24m)`) exactly as a simple
  want's do.
- *Drafts are not records.* A staged part lives at the buyer's edge
  until composed; a "draft" in the book would be a conditional offer,
  the shape rejected above.

**The give side gets a floor, not parts (same ruling).** Every case
that looks like a composed give falls into one of three: (i) one maker,
one taker, several things that go together — the packed box, the
furniture lot, the bicycle-and-helmet kit — is *one indivisible give of
one thing*, the kit as a category, nothing to compose; (ii) one maker,
many interchangeable takers, all or none — the chartered bus that runs
only if thirty seats sell, the workshop with a minimum of eight, the
production run, the crowdfunding threshold, the cow that cannot be half
slaughtered — is the **mirror of aggregation**: one give carrying a
*minimum fill*, same category, quantities adding, a lower bound on one
edge of the flow (Hoffman's condition decides feasibility), which
`cli.md` §6 already spells as the minimum order quantity `30seat..` and
which rides the v3 bump with the integer-granularity decision below;
(iii) one maker, many takers, *different* things, all or none — sirloin
to one buyer and mince to another only if the whole animal sells — is
the tying door this document keeps shut, and the reseller who buys the
cow and sells cuts is the market's route. So composition stays
want-side only; the v3 bump carries want parts, fills naming gives with
per-give quantities, the give-side minimum, and the integer-granularity
decision (open problems).

**Open under this heading.** Operator algebra beyond one hop (container
then van: two place operators compose; the intermediate coordinate is a
free variable the solver binds); whether a want — now a *part* — may
name *alternative* compositions (any saw, or a jigsaw plus a blade) — an
OR on the want side that the cone intersection already gives for
categories but not for operators (left open 2026-09-12); and the recall
of composition search — candidate generation over sets is the
combinatorial part this document otherwise avoids, and it is the
solvers' problem to be good at, not clearing's.

## 11. The primitive is a circulation (reframed 2026-09-07)

§10 changed the object under this document without saying so. Said so:
**what loopmarket clears is not a loop but a circulation** — a flow on
the maker graph that is conserved at every node, where conservation is
of *value on that node's own scale* and some legs are hyper-legs (one
want composed from several gives, §10). A simple cycle is the smallest
non-trivial circulation; the P0 solver finds exactly those and nothing
else. "The numbers cancel in-loop" (the essay) is precisely "the numbers
cancel at every node". Nothing in U1–U7 or U11 changes; they were always
statements about nodes and legs, never about cycles.

**Hypergraphs, since the word is load-bearing.** A hypergraph is a graph
whose edges may join more than two nodes; in the directed form a
hyperedge has a set of tail nodes and a set of head nodes. An ordinary
leg is an edge from one giver to one wanter. A composed leg is a
hyperedge: the givers are its tails (six lifters; the station and the
courier) and the one wanting maker is its head. It is a hyperedge and not
k edges because it carries *one* flow variable — the composition rule
fixes how much of each tail's give it consumes (one person-hour from
each; one brush and one carriage) — so filling it fills every tail and
not filling it fills none. That is what "all or nothing" means here, not
an added constraint. The payment side is not a hyperedge: the buyer's one
divisible money give leaving along k ordinary edges is plain flow
splitting. Conservation on a hypergraph reads as on a graph once each
hyperedge's flow is weighted by its consumption of each incident node's
give or want at that node's own price. Flow on hypergraphs with this
structure is a linear program for divisible legs and an integer program
when a hyperedge is all-or-nothing, which is the §2 boundary again.

The reframing puts the project inside a body of theory with names for
everything it had been rediscovering.

**Circulations (network flow, 1956–).** A flow with no sources or sinks
is a circulation. Three classical results carry over directly.
*Decomposition:* on an ordinary graph every circulation is a sum of flows
around simple cycles, at most one cycle per edge — the precise sense in
which a cleared set is "a combination of loops"; hyper-legs break the
decomposition, which is why §10's shapes are not "two loops".
*Feasibility:* Hoffman's circulation theorem (1960) — with a lower and
upper bound on every edge, a circulation exists iff no cut is
over-demanded — is the test that a set of bounded offers can clear at
all, and a cheap infeasibility pruner for solvers. *Optimality:*
minimum-cost circulation is an LP with Klein's cycle-cancelling algorithm
(1967): while the residual network has a negative-cost cycle, push flow
round it; stop when none remains. Negative cycles are found by
Bellman–Ford. The P0 baseline is one iteration of that procedure.

**Generalized flows (flows with gains, 1960s; Goldberg–Plotkin–Tardos
1991).** Each edge multiplies what passes through it by a factor — here
the rate. Conservation is of value, not units; a cycle whose factors
multiply to more than one is a *flow-generating cycle* — the finance
word is arbitrage, ours is surplus — and under −log weights it is a
negative cycle, which is exactly `graph.py`. Generalized circulation is
still an LP with polynomial combinatorial algorithms. loopmarket's two
departures are §10's hyper-legs (a hypergraph flow: still an LP for
divisible legs, a coupling constraint the LP handles natively) and
indivisible legs (§2's ILP boundary, unchanged).

**Duality: clearing prices are node potentials.** The dual variables of
the circulation LP are one number per node — a potential — and an edge's
reduced cost is the difference of its endpoints' potentials less its
cost. Complementary slackness says flow runs only on edges of zero
reduced cost. Translated: at the clearing prices the log-rates round
every cycle sum to zero (Π ρ = 1, `P2-clearing-pricing.md` §1), the
potentials *are* the makers' personal scales (a scale is a node potential
by construction — that is why one maker's offers can never be arbitraged
against each other, §10 of the talk), and the equal log-surplus split is
one particular choice of potentials among those that make the field
conservative. The Kirchhoff correspondence, for the record: current law =
per-node conservation; voltage law = potentials exist ⇔ Π ρ = 1 on every
cycle; a profitable loop before clearing is a non-conservative field;
Tellegen's theorem (Σ voltage × current = 0 for any lawful pair) =
surplus exactly distributed, none created or lost, at clearing. Where the
analogy stops: one commodity and passive edges there; a gain at every
node, bounded offers as edges, and hyper-legs here.

**Algorithms this suggests.** In order of how soon they pay.

1. **Cycle cancelling as the second species.** Repeated Bellman–Ford on
   the residual generalized network, pushing flow round each negative
   cycle, builds a whole circulation from many loops and handles
   divisible quantities natively — the natural successor to
   `find_profitable_loops`' greedy extraction, and it is *the* classical
   algorithm rather than a heuristic. Deterministic variant for U6:
   **minimum-mean-cycle cancelling** (Goldberg–Tarjan 1989) — strongly
   polynomial, and the cycle chosen at each step is canonical, so the same
   book yields the same circulation on every replica. Candidate for the
   reserve bid's upgrade once the recorded best-rate-per-pair defect (§6)
   is fixed; gate: recall-exact against the LP on the benchmark book.
2. **Verification by potentials (U3 in linear time).** A solver submits
   its circulation *and* the potentials that certify it. Clearing checks
   conservation at each node, each leg inside its [ask, bid] bounds, and
   zero reduced cost on every used leg — all O(legs), no search — and the
   duality gap between the submitted primal and dual is a proof of how
   good the proposal is. That is exactly what the fairness floor and
   winner scoring (`P2-batch-auction.md` §5–6) want to check without
   re-solving: "beats the reserve bid" becomes a certificate, not a
   recomputation. The on-chain verifier of P2 checks a potential vector,
   never runs Bellman–Ford — the same posture U9 takes on −log weights.
3. **Reduced-cost pruning in candidate generation.** With the potentials
   of the previous beat in hand, a new offer's legs have reduced costs
   computable in O(1) each; a leg with positive reduced cost against every
   current potential cannot lie on any improving cycle. Streaming
   candidate generation: most offers are rejected on arrival without a
   graph search. Composes with the indexed generator (`dimensions.py`).
4. **Composition as column generation.** §10's hyper-legs enter the
   packing ILP as columns (a hyper-leg with its consumption vector), the
   way PICEF (§5) adds chains as position-indexed variables; the pricing
   subproblem that finds an improving column is again a shortest-path /
   negative-cycle search over the residual network, so solvers that are
   good at (1) are good at this. Gate: the flow LP with hyper-legs, then
   branch-and-price for the indivisible case, on the §6 benchmark.
5. **Hoffman cuts as infeasibility proofs.** When a beat cannot clear a
   want (six lifters, five offered), the over-demanded cut is a compact,
   checkable explanation — the same shape as T14's absence proofs, on the
   selection side. Publishable beside the beat's result.
6. **A conservation audit for followers.** Tellegen's sum over a cleared
   circulation is zero at the clearing prices; any follower with the
   fills and prices checks it in one pass, with no ontology and no
   matching — a cheap tripwire that a clearing instance's arithmetic is
   honest, weaker than U3's re-derivation and far cheaper.

**Consequences for records and vocabulary.** `loop/` records name a
cycle of legs and `loop_id` is the content address of that cycle
(`graph.py`); the general object is a *multiset of legs with quantities*
conserved at every node — the settled-quantities v3 record
(`P2-clearing-pricing.md` §8) and §10's multi-give fills already push in
this direction, and the id should become the content address of the leg
multiset, of which a cycle is the special case (ids of today's loops are
unchanged by construction). The words (decided 2026-09-07):
**keep the names, widen the meaning.** *Loop* means any cleared
circulation — the essay's word, the brand, `Loop`, `LoopProposal`,
`loop/`, `loop_id`, "the solver proposes a loop" all stay and all become
exactly right under that reading; *cycle* (or *simple loop*) is the strict
circle, which is what P0's code can find and the only thing today's `Loop`
can hold; *circulation* is the technical name when the theory is being
invoked; *leg* and *hyper-leg* are the parts. Renaming the identifiers
now would make code promise what it cannot yet deliver, and `loop/` is a
persisted keyspace whose rename is a record-format bump (U2). When the
v3 record lets a `Loop` hold a leg multiset, the class simply grows into
its name. `P2-clearing-pricing.md` §10 records the
potentials view from the pricing side.

**What does not change.** U3's posture (clearing verifies, never
searches) gets stronger, not weaker: verification by potentials is
*cheaper* than re-running Bellman–Ford. U4/U6 determinism holds for
min-mean-cycle cancelling as for Bellman–Ford. U5 is the requirement that
gains be positive so that logs exist. Solvers remain outside the
protocol; the theory tells them which algorithms are classical, not
which they must use.

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
`P2-clearing-pricing.md`. *Not this problem (2026-09-11):* tolerance on a
**good's quantity** — "is 10.1 kg 10 kg?" — is a settlement norm per leg
and category, decided in `docs/plans/cli.md` §6 and
`ontodag-coupling.md` §3 (declare in the direction you know; no tolerance
parameter anywhere). Net-drift tolerance here is a clearing-side rational
bound and stays open as stated.

**Compression vs uniform directional clearing.** Netting perturbs the
per-leg quantities the equal log-surplus split priced; the precedence
rule is decided, the residual gap unquantified. Work package:
`P2-clearing-pricing.md`; named here because compression is this
document's mechanism.

**Integer granularity of a give — DECISION REQUIRED before the v3 record
bump** (raised 2026-09-10). `Thing.divisible` is a boolean: off means
all-or-nothing, on means continuously divisible, and nothing in between
is representable. That leaves out the common case of one maker with a
large whole-unit quantity — 1,000 apples sold by the apple, grain in
25 kg sacks, 400 seats — which today needs either n one-unit offers
(book bloat, n matches, n fills) or a continuous give that clearing may
fill at 12.7 apples. §2's qty-as-flow-capacity partial fills remove the
n-offers cost but keep the continuity; §10's aggregation puts
integrality on the *want* (fill-or-kill ≥ 6) and still uses one offer
per unit on the give side; the capacity/slot schedules below are far
roadmap and about distinct slots, not fungible whole units. No document
specifies a step. The question cannot be deferred past the v3 bump:
under U2 a new record field changes every offer id, and v3 is already
scheduled to carry per-fill quantities (`P2-clearing-pricing.md` §8) and
U9's rational amounts, so the step must ride the same bump or wait for
another.

  Options on the table:
  1. **`step` replaces the boolean.** A quantity in the Thing's unit:
     `step == qty` is today's indivisible, `step == 0` today's continuous,
     `step == 1` whole apples, `step == 25 kg` sacks. Matching requires
     the want's quantity to be a positive multiple of the give's step;
     clearing constrains each fill to a multiple. Exact under U9 (a
     rational), one field, `from_record` maps v2's boolean to the two
     degenerate values. Recommended representation.
  2. **Keep the boolean, add `min_qty`.** Cheaper to read, but a minimum
     is not a granularity (it forbids 3 of 1,000, not 12.7) and leaves
     the fractional-fill problem in place. Included for completeness;
     not recommended.
  3. **Do nothing; one offer per unit stays the convention.** Zero code,
     and the P1 book already tolerates it; but the announcement, postage
     and matching costs scale with n, and a 400-seat bus posting 400
     offers is the case the owner flagged as the reason to decide.

  The clearing consequence is the real content of the decision: a
  stepped leg is not a continuous flow, and the rates on edges break the
  integrality that plain network flow enjoys, so stepped legs either
  (a) join the indivisible legs on the ILP side of §2 — exact, but every
  stepped bulk offer drags its beat out of the polynomial regime — or
  (b) stay in the LP and are rounded *down* to the step inside the
  equal log-surplus split, the remainder left unfilled and the rounding
  loss booked as the U13 dust rule already has to book it — polynomial,
  but the fairness filter must be shown to survive the rounding. (a) is
  the natural default for large steps relative to the quantity, (b) for
  small ones (whole apples out of 1,000); a threshold between them is a
  parameter nobody has chosen. Decide: representation (1 vs 2 vs 3),
  clearing regime ((a), (b), or a threshold), and whether the v3 bump
  waits for it. Owner: P2 kickoff, alongside the U9 migration; the
  matching change is one line in `check_match`, the record change rides
  v3, the clearing change is this document's §2.

- **Price and capacity schedules in offers** (far roadmap — owner-added
  2026-08-21;
  lands, if ever, with a post-P4 record bump). Today an offer quotes one
  price; the generalization is a *static, immutable schedule*: over
  quantity ("1 box at 50, up to 5 at 45 each" — a supply curve, most of
  what auction theory wants from a bidder), and/or over validity time
  (price as a function of beat index — a pre-committed Dutch or English
  auction inside one offer, which cannot double-fill the way a ladder of
  short-validity offers can). The same record family covers **capacity
  and slot schedules** (15 gym seats; one lesson per non-overlapping
  hour of a 9-to-5 window): fills become slot/quantity-parameterized —
  the settled-quantities v3 work extended to a settled *sub-window*.
  Until any of this lands, the strict working forms are
  one-offer-per-slot/seat (atomic fill = booking, today) and this
  document's flow LP, whose qty-as-capacity handles divisible pools at
  P2. Cross-offer conditional pricing ("both parcels cheaper together")
  stays excluded — bundles are the combinatorial door that stays shut;
  routing synergy is the solvers' to discover and be paid for. Both stay U2-compatible values solved
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
