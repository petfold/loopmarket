# loopmarket — staged privacy (P4)

Status: design, 2026-08-07. Decided here: privacy ships in three tiers,
Tier 1 with zero new cryptography (mixnet transport, Shutter-sealed
bodies and submissions, adaptive k-enforced coarsening, per-batch
aggregates, ERC-5564 stealth payment legs, ACT coarse-first disclosure,
per-epoch maker keys); the P2 format-freeze dependency list (§5),
including the ruling that the `fill/` keyspace stays public —
auditability wins the stealth-vs-audit tension at the record layer;
disclosure is per-offer and market-priced, never mandated; U3 reframed
as the privacy asset — every layer needs confidentiality only, never
integrity; FHE ruled out on throughput, book-wide MPC rejected on
Cycles' grounds, self-operated threshold committees ruled out on
Penumbra's datum, TEE admitted as mid-tier only. Open here: k-cohort
sybil poisoning; anonymity-set thinness; longitudinal correlation;
hidden fills; witness-telemetry aggregation; reference-rate governance.

This is the P4 design CLAUDE.md's known simplification #7 waits on ("do
not add ad-hoc encryption before that design lands" — this is that
design). It constrains P2 rather than following it: §5 lists the
record-format decisions `P2-batch-auction.md`, `P2-settlement-pricing.md`
and `proof-fabric.md` may not freeze without answering this document.
Companions: `P1-federated-book.md` (the per-maker split every key scheme
rides), `P3-guarantee-coupling.md` (whose witness-telemetry leak is owned
here), `THREATS.md` (the economic register T1–T9, deliberately numbered
apart from this document's privacy vectors), and factbond's corpus
(certificates as the reputation bridge across rotated keys).

## 1. Threat model: what a plaintext book leaks

Offers are rich semantic objects — category cones, a service window, a
geo disc, a maker identity — on a world-readable Swarm book, and
settlement links k parties per loop under one content-addressed root.
Privacy here is also market safety, not only confidentiality: concealed
[ask, bid] bounds protect truthful revelation the same way sealed bids
do (Roth's safety criterion — a market that punishes revealed truth
teaches shading and thins itself; `P2-settlement-pricing.md` §7), so
several defenses below earn their cost twice.
Six vectors, numbered PV1–PV6 to stay distinct from the register T1–T9:

- **PV1 — book surveillance.** Anyone syncing the book reads what every
  maker wants and has, at what rate, where, when. Recurring offers are a
  mobility and schedule trace, and the re-identification literature is
  unforgiving: 4 hourly antenna-resolution spatiotemporal points uniquely
  identify 95% of 1.5M people, and uniqueness decays only as
  ~(resolution)^(1/10) — coarsening 10× buys ~20% less uniqueness
  (de Montjoye et al., Scientific Reports 2013; the same group's
  credit-card result: 4 purchases identify 90%). The largest leak, and
  it exists at P0 by design.
- **PV2 — counterparty deanonymization.** Cone + disc + window is a
  strong quasi-identifier even under pseudonymous keys, and matching
  necessarily reveals it to the counterparty. Matching *is* disclosure —
  no tier changes that, only to whom and when.
- **PV3 — the solver as adversary.** `registry.snapshot()` hands every
  solver a plaintext book. A malicious solver can profile all
  participants, **insert its own offers into a discovered loop to skim
  surplus** (the loop-economy analogue of sandwich MEV), or selectively
  censor offers from candidate generation. The beat's fairness floor
  bounds the skim (every member must beat its reference —
  `P2-batch-auction.md` §5) and sealed proposals remove copy-racing; the
  register carries auction-side misconduct under T3. The *privacy* face
  — the solver reads everything — is this document's.
- **PV4 — settlement linkage, permanent.** All fills of a loop commit
  under one root with a shared `loop_id`: participants are
  cryptographically co-located forever, and when P2 anchors roots and
  inclusion proofs on Gnosis the linkage becomes public and on-chain.
  Personal tokens vanishing at settlement does **not** help — the
  linkage lives in the `fill/` records, not the tokens.
- **PV5 — network metadata.** Publishing reveals the maker's IP to their
  Bee node and peers; owner-signed feeds tie every update to one key
  (U8 deliberately strengthens that tie for authenticity).
- **PV6 — submission front-running.** Observers of the settlement queue
  can race a proposal. Gnosis has run Shutter's threshold-encrypted
  mempool since July 2024; `P2-batch-auction.md` §3 adopts it.

## 2. U3 is the privacy asset; disclosure is priced

"Settlement trusts no solver" (U3) was written as an integrity
invariant; it is also the load-bearing privacy fact. Because settlement
re-derives every leg from scratch, **no privacy layer here is ever asked
to protect integrity — only confidentiality.** A compromised enclave, a
malicious trusted solver, a broken mixnet, a leaky PSI implementation:
each caps at privacy loss, never fund loss or a forged loop. That is the
opposite of the usual private-DEX posture, where the private component
must also be correct (Renegade's ~$209K exploit, May 2026, is what
integrity-bearing privacy machinery costs), and it is why loopmarket can
adopt mid-trust tools — TEEs, trusted solvers, publisher-managed ACT
lists — that would be reckless anywhere the private component could
steal. Confidentiality mechanisms compose in front of U3; nothing ever
replaces it.

Privacy is also not a protocol setting: each offer chooses its own
disclosure dial — exact terms in the clear (matches fastest, leaks
most), cohort-coarse terms with exact geometry disclosed pairwise
post-match, a sealed body with coarse routing hints, or full terms held
by a chosen solver only (Tier 2). Coarser offers match at lower degrees
and later (the match-degree ladder, `ontodag-coupling.md`), so the
privacy premium is paid by the maker who wants it, never socialized. Two
consequences are named now: the dial has a lemons face — systematically
coarse offers correlate with counterparties hiding something, which is
T7 (lemons routing), priced by P3's risk-priced routing, not policed —
and the dial cannot buy reward asymmetry: per U12, quoted exactly,
"reward/reputation statistics count settled fee-paid loops only", and
settled loops disclose their legs (§5 item 1), so a maximally private
maker earns standing exactly as a public one does.

## 3. Tier 1 — ships with zero new cryptography

Running infrastructure and key management only (decided 2026-08, lands
with P2 — the plan-index matrix lets Tier 1 ship alongside P2).

1. **Mixnet transport.** Offer publication is low-rate and
   latency-tolerant — the ideal mixnet workload. Route maker→Bee and
   solver→manifest traffic through Nym (the one production mixnet:
   5-hop Sphinx with cover traffic; NymVPN live 2025-03-13, dApp SOCKS5
   mode 2026) or equivalent. Answers PV5's IP half; key linkage is
   items 6–7's job.
2. **Shutter-sealed offer bodies.** Threshold-encrypt the body to a
   decryption epoch via the Shutter API (a service since March 2025; the
   keyper set has run on Gnosis since July 2024); the book stores
   {`offer_id`, ciphertext, coarse routing hints}. Solvers match after
   decryption, but pre-positioning against *fresh* offers dies.
   Settlement submissions ride the shutterized mempool — PV6 closed with
   infrastructure that already runs. Sealed *proposals* are
   `P2-batch-auction.md` §3's, same machinery.
3. **Adaptive k-enforced coarsening.** Fixed-grid coarsening is privacy
   theater (the ~(resolution)^(1/10) decay, §1). The only coarsening
   with proven bounds is enforced k-anonymity by generalization: publish
   the generalized cell/bucket only when ≥k live offers share the cohort
   — zero unequivocal re-identifications, 1/k random-guess success
   (arXiv:1808.01113). The aggregator computes cohort populations at
   fold time and publishes them in the manifest's `index_root`; a
   maker's client generalizes until its cohort clears k; exact windows
   and discs disclose pairwise post-match (item 5). Honest scope: this
   mitigates PV1/PV2 per snapshot, not longitudinally, and the k-count
   is sybil-poisonable — padding a victim's cohort with fakes makes the
   mechanism disclose finer cells around a real crowd of one. The count
   must be sybil-costed: THREATS.md T2 (sybil offer spam & statistics
   pollution) surface, registered below.
4. **Per-batch aggregates.** Batching is itself a privacy mechanism —
   the shipped half of Penumbra's design (uniform per-block clearing
   hides individual fills in batch totals). The beat publishes
   per-directed-pair clearing rates and beat totals; per-loop price
   vectors live only in private receipt envelopes (§5 item 4). This
   hides price granularity, not linkage — linkage is ruled permanent
   (§5 item 1), and this document says so rather than implying otherwise.
5. **ACT coarse-first disclosure.** Swarm's Access Control Trie
   (Bee 2.2: per-grantee Diffie-Hellman-derived keys, encrypted grantee
   manifest, membership hidden) is the ready-made "reveal exact terms to
   qualified counterparties" layer. Modeled **append-only**: ACT
   revocation is forward-only — anything granted stays readable — so a
   grant is irrevocable disclosure, never a lease. Publisher-managed
   lists, not attribute-based; one manifest round-trip per read.
6. **ERC-5564 stealth settlement legs.** Every on-chain value transfer a
   settlement makes — fee payments, bridge legs, payouts — pays to a
   fresh stealth address (standardized; Umbra 77k+ stealth addresses; EF
   pushed native integration Feb 2026). The viewing/spending key split
   comes with it: auditors can be granted sight the public does not get.
7. **Per-epoch maker keys.** Rotation rides the P1 per-maker split for
   free — a key is a feed is a book, so an epoch key is a new book (with
   its own postage floor; rotation is not gratis). Breaks cross-epoch
   linkage of the *identifier*; behavioral fingerprints survive (open
   problem), and reputation must be rebridged — Tier 2's association
   sets, with factbond certificates as the bridge.

## 4. Tier 2 — proven components, heavy engineering (1–3 years)

- **Association sets for reputation across rotated keys.** The Privacy
  Pools primitive (Buterin–Illum–Nadler–Schär–Soleimani 2023; 0xbow live
  2025-03-31 — $6M volume, 1,500+ users, 1,186 withdrawals in year 1):
  prove membership in an approved set rather than full anonymity. Here a
  maker proves "this key is in the set with clean settled history /
  unslashed bonds" without revealing which member — sets maintained from
  U12-eligible statistics, factbond certificates as the natural
  criterion (kin to the exclusion-set machinery of factbond's
  `docs/plans/insurance-products.md` §5). Disputes force selective
  disclosure: this is the compliance story, and it is selective
  disclosure by design, not anonymity from authorities.
- **Structure-aware PSI for the pairwise handshake — only.** "Do our
  offers match?" is a structured intersection: a geo disc is an ℓ2 ball,
  a window a 1-D interval, a cone a set. Garimella–Rosulek (CRYPTO 2022)
  structure-aware PSI handles sets-of-balls with communication scaling
  in the number of balls (45–60% less time, 85% less communication than
  plain-PSI reductions, via function secret sharing). Strictly
  two-party: a pre-disclosure handshake between matched candidates or
  maker↔solver, never book-wide matching.
- **The trusted-solver tier.** Renegade's honest trust statement —
  "private from everyone except your relayer" — maps onto a per-maker
  trusted solver: the maker publishes only the cohort-coarse commitment
  (§5 item 2) and sends exact terms to solvers it chooses; terms travel
  maker→solver→settlement and become public only when a loop settles.
  The win is precise: today *unmatched* offers leak forever; under this
  tier only settled legs disclose. Renegade's tractability trick —
  import an external midpoint so private matching is a boolean cross
  test, not price formation — has a native analogue in trailing settled
  rates per directed pair (`P2-settlement-pricing.md` §9), usable only
  after the reference-rate governance problem (below) is ruled.
- **TEE solvers, mid-tier.** An attested-TDX solver matching over sealed
  offers, BuilderNet-style (Flashbots evaluated SGX/MPC/FHE/TDX and
  chose TEEs for production orderflow, with operator diversity as
  defense-in-depth). Admissible *because of §2*: post-TEE.Fail
  (Oct 2025 — ECDSA attestation keys extracted from Intel's Provisioning
  Certification Enclave on fully patched DDR5 machines given physical
  access; TDXploit, USENIX Security 2025) attestation is not a
  cryptographic guarantee, so a TEE may hold confidentiality, never
  integrity — under U3 its compromise costs privacy, never funds.
  Cycles' ZK+TEE sidecar (obligations encrypted to an enclave, the solve
  inside, a ZK proof of subset flow and balanced flow on-chain) is the
  evaluated precedent to adapt, not rediscover.

## 5. The P2 format-freeze dependency list

The record-format decisions blocked on this document; none may freeze in
the owning P2 document without the named answer (decided 2026-08; items
2–3 land with the v2 bump, the rest with P2).

1. **The fill keyspace stays public — ruled here.** The tension, named:
   `proof-fabric.md` §5 froze the verifier shape "per-leg inclusion of
   the offer *and* absence of its fill, both against the anchored root",
   and §6 froze per-participant receipts carrying inclusion proofs of
   one's own offer and fill under the settled root. Both require
   `fill/<offer_id>` to be derivable from the offer id by *any* verifier
   — and a blinded key every verifier can derive is not blind. Stealth
   fills are incompatible with the frozen auditability shape, and
   auditability wins: `fill/` stays plaintext and permanent, PV4 is
   accepted at the record layer, and the privacy budget goes to key
   rotation, aggregates, and stealth *payment* legs instead. The only
   escape is Tier 3 research (ZK absence-of-fill, registered below).
2. **Sealed bodies are a commitment scheme, fixed at the v2 bump.**
   `offer_id` = SHA-256 of *plaintext* canonical bytes, always; a sealed
   offer publishes the id, ciphertext, and coarse hints beside it, and
   decryption lets anyone check hash(plaintext) = id. Ciphertext and
   hints are transport artifacts under U8's discipline ("nothing signed
   enters canonical bytes" — nor does anything sealed). If P2's contract
   assumes offer records are plaintext-parseable at proposal time,
   sealing dies — it must not.
3. **Payout address ≠ maker address.** `P1-federated-book.md` §1 makes
   maker = feed-owner address serve three roles and notes P2 settlement
   "gets the same address for free". It must not take it: contract and
   receipt formats carry a per-leg payout field never *required* to
   equal the maker address, and the v2 offer record reserves an optional
   ERC-5564 stealth meta-address — riding in the encoding as
   `bond`/`oracle`/`arbitrator` already do, so ids don't churn when it
   activates.
4. **Per-leg settled prices stay out of public loop records.** The
   settled price vector goes into private per-participant receipt
   envelopes (`proof-fabric.md` §6's legal artifacts); the public beat
   record carries per-directed-pair aggregates.
   `P2-settlement-pricing.md` §9's commitment to keep settled rates
   queryable per directed pair must be satisfiable from aggregates —
   never by identity-keyed plaintext.
5. **Reputation formats key on provable membership, not raw addresses.**
   Key rotation dies at the reputation layer if standing (successRate,
   U12 statistics, bond history, `P2-batch-auction.md` §9's "bonded,
   aged, or fee-paying makers" eligibility) hard-binds to a permanent
   address. Every such format must accept an association-set membership
   proof (§4) wherever it accepts an address history.
6. **b33son field-granular records — shared watch item.** The
   field-aligned encoding would let a dispute reveal one offer field
   instead of the record; the choice reshapes record identity and must
   not churn `offer_id` (U2). Owned jointly with `proof-fabric.md`'s
   open problem and factbond evidence storage; no encoding that
   precludes it freezes without a recorded decision.
7. **Proof shapes stay ZK-wrappable.** `proof-fabric.md` §6 promised
   "designed ZK-wrappable, not ZK-promised": authenticated-path proofs
   are the circuit family Tier 3 wraps for private book inclusion. Any
   P2 proof-format change re-checks that property before freezing.

## 6. Tier 3 — research track (do not block P4 on it)

- **ZK fits-within — fire the ontodag wall first.** ontodag walls "ZK
  proofs over private ontologies" behind the tripwire "a real
  privacy-demanding counterparty, loopmarket-shaped" — this document is
  that counterparty, and `proof-fabric.md` §7's discipline applies:
  **file the upstream ask before designing anything here** (upstream
  positioning is noted as unusually good: deterministic canonical
  encoding, one query primitive, integer-only values — circuit-
  friendly). The ask: a derived transitive-closure commitment published
  beside each pinned catalogue root (own store, own root, never merged —
  the same admissible form, plausibly the same index, as the
  cone-commitment ask proof-fabric files at P2 start). "A fits-within B"
  then splits exactly as the DimensionIndex split: the semantic half is
  one committed-set membership proof (Merkle inclusion, or lookup
  arguments — Caulk/cq/Lasso — for prover-sublinear membership); the
  spatiotemporal half is algebraic — range circuits for windows, prefix
  circuits for cells — proven directly, never enumerated. Bounded-depth
  path proofs leak depth unless padded; Nova folding (CRYPTO 2022) if
  catalogues get deep. The numbers say feasible: client proving is
  commodity at this size (Mopro; the FibRace benchmark, Sept 2025,
  6,000+ users across 1,420 device models — most modern smartphones
  prove in under 5 s) and Groth16 verification is ≈181,150 +
  6,150·(public inputs) gas — well under a cent on Gnosis. Feasibility
  is not priority; nothing in P4 blocks on this.
- **Private book inclusion.** ZK-wrapping the recordstore trie proofs
  (§5 item 7) gives "my offer is in book root R" without revealing
  which — the same circuit family as closure membership.
- **Sealed-bid rate proofs.** A solver proves its sealed proposal's rate
  product exceeds 1 (and beats the reference score) without revealing
  legs before reveal — U9's exact rationals keep the arithmetic
  circuit-reproducible. Unscoped; noted so the beat's scoring stays
  rational-only.
- **ZK absence-of-fill under blinded keys.** The only escape from §5
  item 1: prove "no fill exists for this offer" against a committed book
  without a public fill key. Genuinely open; registered below.

## 7. Ruled out

- **FHE matching — dead for the P4 horizon, with the numbers.** Zama's
  fhEVM (first production FHE mainnet, 2025-12-30) does ≈20 TPS on CPUs
  for confidential *transfers*; the roadmap says 500–1,000 TPS on GPUs
  by end-2026, ASICs 100k+ TPS in 2027–28. One encrypted transfer is
  tens of comparisons; candidate generation plus Bellman–Ford over even
  a thousand encrypted offers is orders of magnitude beyond, and
  threshold decryption hands confidentiality to a key committee anyway.
  Watch item at the ASIC generation; compare-only uses (encrypted
  reserve prices) may be revisited then. No design dependency.
- **Book-wide MPC matching — rejected on Cycles' grounds.** Cycles
  evaluated MPC for private clearing and rejected it on collusion and
  performance, choosing the ZK+TEE sidecar; loopmarket adopts that
  ruling rather than re-running the evaluation. Renegade's live MPC
  works only because crosses are pairwise and price is an imported
  midpoint; loops are k-party cycles with endogenous rates — the general
  problem is open, and its salvageable fragments are already placed
  (pairwise PSI, §4; reference-rate pegging, §4/§6). Renegade's May 2026
  exploit stands as the implementation-complexity datum.
- **Self-operated threshold committees — ruled out.** Penumbra designed
  threshold flow encryption and has not shipped it in 2+ years of
  mainnet (amounts revealed, identities shielded, ~$3.77M shielded
  value) — the cautionary datum from a well-funded specialist team.
  Loopmarket never operates its own keyper or decryption committee; it
  uses committees that already run (Shutter's, on the chain P2 settles
  on).
- **TEE as anchor — ruled out; mid-tier only.** Grounds and role in §4.
- **Ad-hoc encryption outside the tiers — refused.** CLAUDE.md
  simplification #7's rule, discharged by this document: proposals that
  encrypt something not named in §3–§6 are rejected on arrival.

## Gates

- **G1 — Tier 1 end-to-end.** An offer published via mixnet transport
  with a sealed body and k-enforced coarse hints; decrypted at its
  epoch; matched; settled with a stealth payout leg on Gnosis testnet.
  Latency and cost overhead vs the plaintext path measured, acceptance
  threshold fixed before the run (Phase-0 pre-registration style).
- **G2 — coarsening bounds hold.** Adaptive k over a replayed/simulated
  book: re-identification ≤ 1/k under honest cohorts, and the
  sybil-poisoning playbook (THREATS.md T2 economics) run in the shared
  harness (`factbond/docs/plans/phase0-simulation.md`) with a
  pre-registered pass criterion.
- **G3 — format-freeze discharge.** Every §5 item has a recorded
  decision in its owning P2 document before the P2 contract freezes.
  Procedural; owner: P2 kickoff, jointly with `proof-fabric.md` G2/G5.
- **G4 — the ZK wall filed first.** Before any Tier 3 circuit work, the
  upstream ask (closure-commitment index) exists in ontodag's tripwire
  log and `ontodag-coupling.md` records the answer — mirroring
  `proof-fabric.md` G5. No local ZK fits-within design without it.
- **G5 — linkage audit.** A linking adversary (heuristic clustering over
  book + chain data) run against rotation + stealth legs; measured
  cluster recovery recorded. No unlinkability language ships before G2
  and G5 pass.

## Open problems

- **k-cohort sybil poisoning.** The cohort count driving adaptive
  coarsening is an attacker-writable statistic: padding a victim's
  cohort triggers finer disclosure around a real crowd of one, and
  poisoned cohorts pollute per-batch aggregates. Counting only
  cost-floored makers (postage-aged, settled per U12) resists it but is
  circular — proving history without identity needs §4's association
  sets. Work package: Tier 1 + THREATS.md T2 + the Phase-0 adversary
  playbook.
- **Anonymity-set thinness.** Every mechanism here is bounded by the
  crowd: a young, thin book has small k everywhere, whatever the
  mechanism. Thickness engineering is privacy engineering. Work package:
  `adoption-and-thickness.md`.
- **Longitudinal correlation.** k-enforced coarsening defends snapshots;
  offer *histories* still correlate across epochs, and behavioral
  fingerprints (category mix, rate habits, cadence) survive key
  rotation. Quantifying the residual under realistic rotation is unowned
  analysis. Work package: Tiers 1–2, measured in the shared harness.
- **Hidden fills.** §5 item 1 rules the fill keyspace public; the ZK
  absence-of-fill construction (§6) is the only known escape and is
  unscoped research. Work package: Tier 3, jointly with
  `proof-fabric.md`.
- **Witness-telemetry aggregation.** Accepted from
  `P3-guarantee-coupling.md`: the witness feed publishes which catalogue
  edges real settlements walk — trade semantics at edge granularity. P4
  owns the trade-off between the demand stream's usefulness and its
  leakage; until ruled, that document's interim stands (per-loop
  opt-out, aggregation before publication). Work package: P3 coupling +
  Tier 1 aggregates.
- **Reference-rate governance.** Accepted from
  `P2-settlement-pricing.md` §9: trailing settled rates become a
  manipulation target the moment private matching pegs to them (settle
  small loops, move the peg). Whether and how §4's trusted-solver cross
  test may consume them must be ruled here before anything consumes
  them. Work package: P4, before that tier ships.

## What this document does not promise

Not anonymity: k-enforced coarsening yields 1/k, thin books make k small
everywhere, and matching itself discloses to the counterparty — these
tiers raise the cost of surveillance, they do not make it impossible.
Not retraction: everything P0/P1 published in plaintext is
content-addressed and permanent; no tier reaches backward
(`P1-federated-book.md` said it first: nothing can be retracted from the
world). Not integrity: every mechanism here protects confidentiality
only — U3's re-verification is untouched, and a failing privacy
component fails into disclosure, never into a forged loop. Not
resistance to longitudinal or behavioral correlation — Tier 1 defends
snapshots; the residual is a named open problem, not a solved one. Not
anonymity from authorities: association sets are selective-disclosure
instruments and disputes can compel disclosure. And Tier 3 is research,
not roadmap: no ZK fits-within is promised, and the wall it needs
crossed is ontodag's to cross, once, upstream — never forked locally.
