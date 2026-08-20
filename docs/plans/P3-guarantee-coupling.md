# loopmarket — guarantee coupling (P3)

Status: design, 2026-08-07. Decided here: witness-edge emission as derived
telemetry at settlement re-verification; settlement-attached insurance under
the indemnity principle (F3's loopmarket instantiation); the leg-oracle
roster consumed in enforcement order, with fail-closed refusal and
hash-pinned adjudication policies; risk-priced routing (rate × (1 − premium),
per-maker acceptance limits, per-beat concentration fee); solver registration
bonds as the bond pool's second customer; the no-fabric boundary; the
shipping gate mirrored with `factbond/docs/plans/loopmarket-coupling.md`.
Open here: leg valuation under U14, the countersign at-risk bound for service
legs, premium cold start, witness-telemetry privacy.

This is loopmarket's half of the guarantee fabric: how settlement, solvers
and the catalogue *consume* factbond without ever depending on it. The
mechanism design — bond sizing, odds-weighted disputes, the adjudication
constitution — lives in `factbond/docs/plans/mechanism-design.md` and is
adopted, not redesigned (ARCHITECTURE.md §4). The mirror document is
`factbond/docs/plans/loopmarket-coupling.md`; the oracle roster's primary
home is `factbond/docs/plans/evidence-policy.md`; threats referenced by ID
(T1–T9) live in `THREATS.md` here and in `factbond/docs/plans/THREATS.md`;
fee and auction machinery leaned on below is `P2-batch-auction.md`.

## 1. Two claim surfaces, one pool

A settled loop rests on exactly two kinds of fact: **catalogue ⊑ edges**
("the catalogue at root R says the offered concept fits the wanted one") and
**leg fulfillment** ("and the crate really held the cello"). The first is
structural and cheap — F8 (*structural claims settle by certificate only*):
an `is_below` witness path or a trie inclusion/absence proof (ontodag
`CONTRACT.md` §7, `proof-fabric.md`) settles the matches-source half of any
dispute at the price of a hash computation. The second is worldly and
expensive — where oracles, countersigning and arbitrators earn their cost
(§4). The split is the coupling's central economy: every dispute decomposes
into a free structural half and a priced worldly half, and only the second
touches the adjudication ladder. Both are underwritten by one factbond bond
pool — catalogue-edge hedges (§3) and solver registration bonds (§6) are
its first and second customers.

## 2. Witness-edge instrumentation: the insurable surface

`MockSettlement.submit` step 2 re-derives every leg with `check_match`;
inside that, `Ontology.satisfies` answers each (offered, wanted) pair with
ontodag's Boolean `is_below` — an upward walk whose successful path is a
concrete list of ⊑ edges. Those edges are what the loop *relied on*: the
facts whose falsity costs the participants money, i.e. insurable facts with
natural consumers (factbond `docs/INTEGRATION.md` §8). The instrumentation
(decided 2026-08, lands ahead of the §8 gate — pure telemetry, no factbond
dependency): `covers`/`is_below` gain a witness mode, and settlement emits,
per settled loop, the deduplicated edge list its *own* re-verification
walked, keyed by `(loop_id, ontology_root)`. It must be the verifier's walk,
not the solver's — U3 trusts no solver, and a reliance proof built from an
untrusted walk would be no proof. Three committed properties:

- **Derived, never canonical.** The list is recomputable by anyone from the
  pinned `{book_root, ontology_root}` (U10 makes the replay exact), so it is
  emitted as a signed telemetry record *beside* the book — the
  provenance-store pattern — never inside the `loop/` record. Storing
  recomputable data in canonical records buys nothing and churns roots; F6
  (*factbond state never enters canonical knowledge*) forbids the
  neighborhood anyway.
- **It is the demand stream.** Which edges factbond's pool should
  auto-assert, at what confidence, is read off real reliance: the witness
  feed aggregated as settlement-weighted edge traffic. Static graph degree
  was rejected as the centrality measure — attackers farm cheap degree (the
  Curve-wars lesson, `factbond/docs/plans/mechanism-design.md`);
  settlement-weighted reliance is farmable only by paying real fees (U12).
- **Bonds attach to subjects, not edges.** F2 (*bonds attach to claim
  subjects*): ontodag's canonical reduction re-routes edges, so an
  edge-attached bond could be orphaned by an innocent catalogue commit. The
  witness list is edge-shaped; the claims it feeds are subject-shaped; the
  translation is factbond's (`factbond/docs/plans/records-and-anchoring.md`).

## 3. Settlement-attached insurance and reliance accounting

The coupling's payoff (decided 2026-08, lands with P3, gated in §8):
settlement offers each participant a hedge on the witness edges its loop
relied on, priced by the pool off stated confidence plus its own loss
tables. A payout **auto-funds and auto-files a dispute** on the edge that
lied (factbond `DESIGN.md` §7) — loop participants become the shared
catalogue's verification workforce without ever thinking about it, and
disputer-side funding counters the worn-down-disputer failure the
Polymarket/UMA record shows (honest disputers slashed twice on the
Zelenskyy-suit market, taught to stop disputing).

Reliance accounting makes this safe to sell. F3: *indemnity (payout ≤
provable reliance; payout-cap proxy where unprovable)*. loopmarket is the
one deployment where reliance is provable for free: the settlement root pins
exactly which settled legs walked the insured edge, so "payout ≤ value of
the settled legs that pinned the edge" is enforceable natively. That kills
insurance arson (T5, primary: `factbond/docs/plans/THREATS.md`) — breaking
an edge you insured pays at most what you provably had at stake, minus
premium. The structural half of the cap (which legs, which edges) is free;
the monetary half is not: legs are priced in personal tokens, and U14
(*numeraire-free scoring*) means no external price exists to read off. The
v1 rule is declared-at-purchase coverage in the pool's external asset,
capped per leg and per edge, premium proportional to coverage — overstating
reliance costs premium on the overstatement, and the caps bound the damage.
The honest denomination of reliance is a registered open problem (below).

Aggregate exposure fails closed. F4: *reliance-bounded adjudication +
fail-closed caps* — when open insurance on an edge approaches the integrity
cost of its dispute ladder's final rung, the pool stops selling on that
edge. This is the $750-bond-versus-$7M-market lesson (Polymarket/UMA, March
2025: one whale with ~25% of the DVM vote flipped the Ukraine-minerals
resolution): adjudication-cost bonds are safe only while downstream reliance
is capped, and a cap that fails open is not a cap. Nexus Mutual's quorum
rule (assessment stake > 5× the claim) is the same principle in production.
The pool's per-edge loss experience flows back as §5's premium feed — the
P3 "aggregated risk markets feeding rate premia" line item, made concrete.

## 4. The leg-oracle roster (consumed here, owned there)

Primary home: `factbond/docs/plans/evidence-policy.md` — admissibility
weights, revocation, per-domain policies. Here: the roster, its enforcement
order, and settlement's behavior toward it.

| oracle        | attests                      | trust root                  |
|---------------|------------------------------|-----------------------------|
| countersign   | both parties say it happened | counterparties' own stakes  |
| locker        | deposit/pickup at a machine  | operator-signed events      |
| digital-proof | a web-visible record         | zkTLS transport             |
| attested-photo| physical state at capture    | Truepic-class attestation   |
| location      | presence at a place          | none person-grade in 2026   |

**Countersign is the default**, with optimistic semantics: mutual silence
past the liveness window confirms the leg; disagreement — not a vote — opens
the dispute path. It is the optimistic-assertion pattern in miniature and
needs zero infrastructure. Its structural bound: a countersigned leg never
unlocks more value than both parties have at risk, so collusive
countersigning (both legs of a fake handover attesting happily) is capped by
the colluders' own escrow; pool-funded random audits price the residual.
**Locker** is the first infrastructure oracle: parcel networks (InPost
ShipX-class) emit timestamped, operator-signed deposit and QR-code-collection
events — a disinterested machine witness for exactly the handover legs the
triangle demo has — readable via zkTLS off the operator's tracking surface,
no partnership required; it attests handover, never contents or quality.
**Digital-proof (zkTLS)** covers every leg whose fulfillment leaves a
web-visible trace, with mature 2026 SDKs (Reclaim, zkPass, TLSNotary); it
proves what a website said and inherits the website's truthfulness — hence
the **parametric-first doctrine**: wherever a canonical digital feed exists,
settle parametrically with no dispute layer at all and spend all scrutiny on
feed selection (the Etherisc FlightDelay pattern — parametric payouts in
USDC on Gnosis Chain, loopmarket's own chain). **Attested-photo** requires
Truepic-class hardware-attested capture with revocation checks; bare C2PA is
corroboration only — it strips on re-encode, and one device exploit (Nikon
Z6III, Sept 2025) revoked a fleet's certificates; post-genAI, an unattested
photo is dispute *input* for a staked tribunal, never an oracle.
**Location is carried, not implemented** — the carried-in-the-encoding
discipline of `bond`/`oracle`/`arbitrator` today: no 2026 network offers
person-grade presence (Witness Chain: server-grade confidence regions; FOAM:
~a dozen zones; GEODNET: positioning correction, not presence). Naming the
slot keeps offer ids stable when one matures.

Two enforcement rules bind settlement, both the U7 shape — unknown fails
closed, drift breaks loudly:

1. **Refusal gate** (decided 2026-08, landed 2026-08-20 — the first
   enforcement step, needing no fabric at all): every settlement backend
   declares the oracle types it can verify and refuses any loop whose legs
   name a type outside that set. MockSettlement declares exactly the P0
   countersign semantics (`verifiable_oracles`); nothing else settles
   through it.
2. **Hash-pinned policies** (decided 2026-08, lands with the v2 bump): an
   offer's `oracle` field stops being a bare string and references a
   hash-pinned adjudication policy document. Policy ambiguity is the
   cheapest attack in every deployed dispute system — Augur's chronic
   "invalid market" tax, Proof-of-Humanity's photo-angle pedantry, the
   Zelenskyy suit — and rulings converge on the letter of the referenced
   policy, so the policy hash *is* the contract. Basis-risk disputes (T9,
   primary: `factbond/docs/plans/THREATS.md`) are fought here, at wording
   time.

U3's trust-nothing discipline extends to oracle inputs with permanent
adversarial fixtures (decided 2026-08, lands with the §8 coupling): a
whale-captured tribunal ruling, a collusive countersign pair, an
ambiguous-policy leg, and a revoked-certificate photo must each be rejected
or bounded by construction, the way `tests/test_boundaries.py` pins B1/B2.

## 5. Risk-priced routing: the lemons defense

The solver maximizes the rate product, so it routes through the cheapest leg
that type-checks — under asymmetric information, the lemons leg (T7,
primary: `THREATS.md`). The catalogue guarantees type conformance, never
quality; Ripple's credit network learned this as "rippling" (path
optimization silently loading risk onto whoever priced it cheapest). The
defense (decided 2026-08, lands with P3, gated in §8), all three parts with
credit-network precedent:

- **Premium-weighted edges.** Solver-side edge weight becomes
  `rate × (1 − expected-loss premium)`, the premium read per edge and per
  maker from the pool's loss experience. This lives strictly in solver
  graph weights: `Match.rate` and everything settlement re-verifies stay
  premium-free, so U3's checklist is untouched and U5 holds trivially
  (premiums lie in [0, 1); weighted rates stay positive).
- **Per-maker acceptance limits.** A trust line in the Circles/Trustlines
  sense — "I accept loops through maker M up to value V" — caps the loop
  value routable through unproven makers until they accumulate delivered
  history. Junk makers stay routable, at small size: quarantine, not ban.
- **Per-beat concentration fee.** Loops that pile exposure onto one maker
  within a settlement beat pay for the concentration — the analog of
  Trustlines' 0.1% imbalance fee for pushing a trustline further from
  balance. Fee mechanics land with `P2-batch-auction.md` and obey U13
  (*wash-loop budget-balance by construction, fees external-asset only*).

Two statistical disciplines guard the feed itself. First, U12
(*reward/reputation statistics count settled fee-paid loops only*): a wash
loop is graph-indistinguishable from a real one — every legitimate loop *is*
a self-financing cycle (Victor & Weintraud, WWW'21) — so shape detection
cannot work and only fee-paid settlement may count (T1, T8, primary:
`THREATS.md`). Second, **silence is uninformative**: eBay's record (0.3%
negative ratings while P(negative | partner rated negative) > 37% — Resnick
& Zeckhauser; "Reputation Inflation", Filippas–Horton–Golden EC'18) shows
costless feedback inflates toward uselessness, and a young bonded system
shows the mirror pathology — near-zero recorded losses meaning thin data,
not safe edges. Premiums start from wide priors and narrow only on real
settled history; an undisputed edge is priced as unknown, never as good.

## 6. Solver bonds: the pool's second customer

P2's batch auction requires solver registration bonds; they route through
the factbond bond pool rather than a bespoke escrow (decided 2026-08, lands
with P2's auction) — one pool, one LP interface, one loss ledger for both
customer classes. Sizing follows CoW's production record, the doctrine
factbond already holds: bonds sized to damage and adjudication, never to
notional volume. CoW's full bonding pool is $500,000 in yield-bearing
stables + 1,500,000 COW, and both real slashes in its history were
operational negligence cured at exact damages — $166,182.97 (CIP-22, hacked
solver infrastructure) and $76,783 (CIP-55, bad token allowances, drained
over 67 txs, detected in ~1 minute) — with a 72-hour cure window before
slashing. Strategic manipulation is handled by mechanism shape
(marginal-contribution rewards, the fairness filter, the reserve bid), not
punishment; settlement already trusts no solver (U3), so the bond targets
the residual channels: winning and failing to settle, proposal spam, and
wash-loop score inflation (T3, T1 — `THREATS.md`). The 1inch Fusion shape —
a whitelist of ten resolvers staking ≥5% of governance power — was rejected:
it buys the same safety by constructing an oligopoly, which the
solver-ecology premise exists to avoid.

## 7. The boundary: no fabric present

The coupling is consumption, never dependency — B1 extended to P3.
`import loopmarket` and the whole model run with no factbond installed, no
pool, no premium feed: fabric absent means raw rates, unlimited acceptance,
P0 settlement semantics — bit-for-bit today's behavior (§5's wide priors are
the policy when the fabric is present but *thin*; absence is not thinness).
F6: *factbond state never enters canonical knowledge* — hedges, premiums,
confidence and status live beside the book, and two books with identical
offers and different bonding must keep identical roots, or
agreement-by-fingerprint dies. Guarantee status surfaces only in the
reserved `annotations.factbond` namespace, whose schema factbond owns
(`factbond/docs/plans/records-and-anchoring.md` §8); nothing agent-facing
claims bond status before that schema exists, and F1 (*status derived never
merged*) means status is always recomputed from signed records plus a clock.
Composition is one-directional: loopmarket consumes factbond's records and
read APIs; factbond never imports loopmarket; neither imports the other at
module load (the B2 shape).

## 8. Sequencing

Mirrored, verbatim in substance, with
`factbond/docs/plans/loopmarket-coupling.md` §5: **the coupling ships only
after factbond Phase-0 is green AND loopmarket's P2 record formats are
frozen.** Phase-0 green means all four pre-registered panels of
`factbond/docs/plans/phase0-simulation.md` §1 pass — half-life first among
them — a fabric
that cannot make honest verification profitable would let settlement sell
hedges that certify nothing. The P2 freeze matters because the reliance
proof consumes P2's inclusion artifacts (`proof-fabric.md`'s pin table and
proofs) and the policy-hash field needs the v2 offer record; coupling to a
moving format would churn every hash-pinned policy reference. One piece
deliberately jumps the gate: §2's witness instrumentation — pure telemetry
with no factbond dependency, whose accumulated feed lets premiums start
from data rather than priors on day one.

## Gates

- **G1 — witness telemetry (no external gate).** Go when: replaying any
  settled loop from its pinned `{book_root, ontology_root}` reproduces the
  emitted edge list byte-for-byte on every replica, and roots are unchanged
  with instrumentation on/off. Unblocked by: the test suite alone.
- **G2 — refusal gate + policy hashes.** Go when: the v2 record bump lands
  with version-dispatched `from_record`; the full suite is green with all
  P0 offers on default countersign; the four §4 adversarial fixtures
  reject or bound their attacks. Unblocked by: the v2 bump (owner:
  loopmarket).
- **G3 — the coupling proper (hedges, auto-disputes, premium feed).** Go
  when *both*: factbond Phase-0 reports all four pre-registered panels
  passed (`phase0-simulation.md` §1; owner: factbond), and the P2
  record-format freeze is declared (owner: loopmarket, `proof-fabric.md` +
  `P2-batch-auction.md`).
  Either failing blocks; Peter signs off against the mirrored gate in
  `factbond/docs/plans/loopmarket-coupling.md`.
- **G4 — risk-priced routing on by default.** Go when: the premium feed is
  derived exclusively from settled fee-paid loops (U12, checkable from the
  ledger), and the recall benchmark shows the premium-weighted solver
  finds every loop the baseline finds when all premiums are zero (a
  B1-style regression: fabric off must reproduce today's solver).

## Open problems

- **Leg valuation under U14** (work package: `P2-settlement-pricing.md` +
  `factbond/docs/plans/insurance-products.md`). Reliance is structurally
  provable but personal-token legs have no external price, so indemnity
  caps rest on declared coverage plus per-leg/per-edge ceilings. Declared
  coverage is honest only while premium pricing makes overstatement a
  losing trade; a principled external-asset denomination of a leg's value —
  or a proof the declared-coverage proxy is incentive-compatible at
  micro-insurance scale — is open.
- **The countersign at-risk bound for service legs** (work package: §4
  enforcement staging + `factbond/docs/plans/evidence-policy.md`). "Never
  unlocks more than both parties have at risk" is crisp for escrowed goods
  and fuzzy for services, where nothing sits in escrow and the at-risk
  quantity is reputational: either service legs get a small mandatory
  escrow, or their countersign bound is priced differently. Unresolved.
- **Premium cold start** (work package: §5 +
  `factbond/docs/plans/phase0-simulation.md`). Wide priors are safe but
  blunt: they tax honest newcomers exactly as hard as lemons, and the
  feed's inputs are themselves attackable until volume exists (T2
  statistics pollution; U12 restricts the inputs but cannot thicken them).
  How fast priors may narrow, on how little data, is an actuarial question
  the shared simulation harness must answer before G4.
- **Witness-telemetry privacy** (work package: `P4-privacy.md`). The
  witness feed publishes which catalogue edges real settlements walk —
  trade semantics at edge granularity, exactly the aggregate P4's threat
  model worries about. P4 owns the tension between the demand stream's
  usefulness and its leakage; until it rules, the feed is per-loop-opt-out
  and aggregated before publication.

## What this document does not promise

- **Settlement certifies re-verification, not delivery.** A settled loop
  proves every leg re-derived under pinned roots and committed atomically;
  whether the crate held the cello is an oracle's claim under a named
  policy, and F7 holds on every surface: *'certified ≠ true'*.
- **A hedge is a priced promise to pay, not a guarantee the leg happens.**
  Auto-attached insurance certifies that a pool sold coverage at a price
  under stated caps — nothing more.
- **Premiums are prices, not probabilities** — quotes under capital
  constraints, adverse selection and attack; reading the premium feed as
  calibrated edge-reliability is the misreading §5's wide-prior rule
  exists to prevent.
- **The roster is not a claim that these oracles are strong.** It is an
  admissibility ranking under 2026 conditions, revisable in
  `factbond/docs/plans/evidence-policy.md`; every entry has a named
  failure mode, and `location` is listed precisely because it does not
  work yet.
- **Nothing here makes the core need the fabric.** Every mechanism in this
  document can be absent, and loopmarket must still import, match, solve
  and settle exactly as it does today.
