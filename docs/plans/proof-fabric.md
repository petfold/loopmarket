# loopmarket — the proof and certificate fabric

Status: design, 2026-08-07. Decided here: recordstore's canonical-trie
inclusion/absence proofs are the primary proof route in every phase, POT
`ForkPathProof` demoted to a conditional on-chain mirror (**flagged revision**
— ARCHITECTURE.md §8 and CLAUDE.md's P2 roadmap line previously committed to
POT and were revised in place 2026-08-07; owner sign-off on the reversal
still pending, discussion agenda item); ontodag's certificate envelope adopted wholesale for
loop proposals and receipts; the pin tuple {book_root, ontology_root,
REGISTRY_VERSION, CONTRACT_VERSION} made load-bearing (U10), closing the
fail-open `''`-pin gate; `is_below` certificates wired into settlement as a
double-check; the Merkle-cone-commitment tripwire fired formally at P2 start.
Open here: whether certificates may ever *replace* U3 re-derivation (doctrine
fork, discussion item); POT mirroring cost and gas; what "no better loop" can
actually prove.

This document is the cross-phase companion to `P2-batch-auction.md` and
`P2-loop-selection.md` (which consume these proofs in the beat design),
`P1-federated-book.md` (whose aggregator publishes the roots everything here
pins), and factbond's `docs/plans/records-and-anchoring.md` (whose dispute
rung zero is this same fabric). Normative upstream: ontodag `docs/CONTRACT.md`
§7 and recordstore's proof primitives (shipped v0.16.0). ARCHITECTURE.md §8
is revised in place to match.

## 1. The fork, resolved: trie proofs first, POT only on demand

Two proof systems can testify about the book. ARCHITECTURE.md §8 committed to
the Proximity Order Trie: `ForkPathProof` (BMT proofs over 4 KB Swarm chunks)
verified on-chain by `POTProofVerifier` (`ethersphere/proximity-order-trie`).
That commitment predates the fact that decided this document: **recordstore
shipped inclusion AND absence proofs over the trie the book already uses**
(v0.16.0, 2026-08-01, built for ontodag `CONTRACT.md` §7 Tier 2).
`RecordStore.prove(key)` returns a self-describing envelope
(`format: "recordstore-trie-proof", version: 1`) of raw trie-node blobs
along the key's path; `verify_proof(proof, root)` checks it with **no store
access** — hash-chain recomputation against a 32-byte root. Absence is
provable because the encoding is canonical (one root, one possible location
per key: exhibit the path where the key would live). The proofs are
O(depth), against the roots loopmarket already pins everywhere (U4).

The reversal's rationale, in order of force:

1. **Shipped versus pre-1.0.** The trie proofs exist, self-verify at prove
   time, and are exercised daily by ontodag's certificate layer. The POT
   repo is active but early: 57 commits, 13 open issues, fork-counting and
   segment-index proof bugs fixed as recently as 2026, and **no published
   gas benchmarks anywhere** for `assertForkPathProof`.
2. **Our roots are not POT roots.** Adopting POT means an explicit mirroring
   step, and the mirrored root's fidelity to the primary root becomes a
   *new* proof obligation. A proof system that testifies about a copy is
   strictly weaker than one that testifies about the original.
3. **The on-chain path is open either way.** Swarm's BMT addressing is
   keccak-based — the EVM's native hash — and ontodag `CONTRACT.md` §7 marks
   root anchoring committed, "waits only on a consumer".

POT survives as a conditional mirror: **adopted only if the P2 on-chain
verifier design demands proofs a contract can check more cheaply than
BMT-verified trie paths, and then only after (a) the mirroring step is
specified and its root-fidelity obligation discharged, (b)
`assertForkPathProof` gas is self-benchmarked on Gnosis — the research
envelope (tens of thousands of gas per path node; a 500k-gas verification ≈
$0.0001 at 0.2 gwei xDAI) is an estimate, not a number — and (c) the
dependency is a pinned, vetted commit with our own conformance tests**
(decided 2026-08, lands with P2). Watch item alongside: b33son (Trón & Tóth)
— a canonical field-ordered, 32-byte-segment-aligned record encoding whose
BMT proofs reveal one field without the whole record; if offer records
adopt it, disputes could disclose a single field on-chain.

## 2. The envelope policy, adopted wholesale

Every proof-bearing artifact this repo emits uses ontodag's certificate
envelope (`CONTRACT.md` §7): a self-describing JSON object
`{format, version, root, subject, evidence}`, where evidence carries **raw
hex-encoded trie/record blobs** and verification is **hash-chain
recomputation over those exact bytes, never re-serialization** — the policy
that "eliminates canonicalization drift by construction". Format-name
versioning means readers ignore unknown formats instead of misreading them;
transport is opt-in because proofs cost fetches (feed lookups dominated the
~51 s live-Swarm triangle run, not hashing).

Loop proposals and receipts become envelope-carrying records: a
`LoopProposal` may attach per-leg inclusion proofs and `is_below`
certificates; a `Receipt` cites the roots it settled between and can carry
the proofs settlement checked (decided 2026-08, lands with P2). Under U8
("two-layer offer authenticity: feed ownership primary; detached signature
for off-feed circulation; nothing signed enters canonical bytes") the same
discipline binds proofs: **envelopes, signatures and certificates are
transport artifacts — no field of theirs ever enters `canonical_bytes()`**,
so `offer_id` and `loop_id` never depend on the evidence riding along.

## 3. The pin table: what every artifact names, and who refuses

U10, quoted from the plan: "load-bearing pins {book_root, ontology_root,
REGISTRY_VERSION, CONTRACT_VERSION}, verifiers refuse on mismatch or
absence." Two defects in the working system make this necessary rather than
decorative: `check_match` step 7 passes whenever either ontology pin is `''`
(the demo and every in-memory test run entirely unpinned — fail-open), and
`LoopProposal.book_root`/`ontology_root` are decoration settlement never
verifies. Both close (decided 2026-08: offer-side pins land with the v2
record bump; proposal/settlement enforcement lands with P2, rehearsed in
`MockSettlement` before that).

Why four elements and not two: the registry's dimension arithmetic
participates in canonical reduction, so **an ontology root without its
REGISTRY_VERSION is an incomplete pointer** (ontodag `DIMENSIONS.md` §10 —
"where it rides in loopmarket's offer encoding is loopmarket's decision";
today it rides nowhere). CONTRACT_VERSION (`ontodag.CONTRACT_VERSION`, 0.1,
conformance-tested G1–G6) names the guarantee set the verifier assumed.

| artifact           | book_root | ontology_root | registry | contract |
|--------------------|-----------|---------------|----------|----------|
| offer (record v2)  | — (a)     | pins (v1 already) | pins | pins     |
| loop proposal      | pins, load-bearing | pins | pins     | pins     |
| receipt            | pre+post roots | inherits proposal's | inherits | inherits |
| dispute (factbond) | (b)       | (b)           | pins     | pins     |
| certificate/proof  | (c)       | (c)           | pins (`is_below`) | pins |

(a) an offer cannot pin the book it is about to enter — self-reference.
(b) a dispute pins its claim subject's basis root: whichever store the
claim is about. (c) the envelope's `root` field is the root its evidence
hash-chains to.

Who refuses, on mismatch **or absence**:

- **`check_match`** refuses to pair offers whose {ontology_root,
  REGISTRY_VERSION, CONTRACT_VERSION} disagree or are missing — the `''`
  wildcard dies once the shared catalogue has a persistent root.
- **Settlement** asserts the proposal's pins against its own book and
  ontology and refuses otherwise — the pin check becomes the U3 checklist's
  step 0.
- **`verify_proof` / `verify_below`** already refuse: the hash chain fails
  on any wrong root; an `is_below` certificate pins REGISTRY_VERSION and a
  mismatched verifier refuses (shipped behavior, adopted as-is).
- **factbond's proof-checker rung** refuses structural disputes whose claim
  subject lacks a basis root — an unpinned structural claim is not
  adjudicable (factbond `docs/plans/records-and-anchoring.md`).

Version semantics follow ontodag's D10: order-affecting registry changes
bump the major and **refuse across it**; vocabulary-additive changes bump
the minor and interoperate. Pins record the full version; refusal triggers
on major mismatch; minor skew is tolerated in matching but recorded in
receipts (the audit trail must show what interpreted what).

## 4. Certificates in settlement: double-check now; replacement is a fork

ontodag ships `is_below` certificates in **both polarities**
(`ontodag.certificates`, 2026-08-01): the prover bundles a recordstore proof
for every record in the answer's order-invariant dependency closure, and the
verifier **re-runs the real `is_below` over a strict fragment store serving
only proof-verified records** — "a coverage gap fails verification, never
validates a wrong answer". Verification needs only the 32-byte root.

Adopted now as a **double-check**: settlement's step-2 re-derivation
(`check_match` per leg) gains an optional parallel path that verifies a
proposal's attached `satisfies` certificates against the pinned
ontology_root and cross-checks the verdicts (decided 2026-08, rehearsed in
`MockSettlement`, lands with P2). Any disagreement between re-derivation and
certificate verification is a fabric bug and halts settlement — the two
methods answer the same fits-within question by construction, so divergence
means broken code, not ambiguity.

Whether certificates may ever **replace** U3 re-derivation is a **flagged
doctrine fork**, registered as an open problem below and on the discussion
agenda. For: the verifier re-executes the real algorithm over authenticated
fragments, so verification *is* re-derivation fed by proofs — and it is the
only shape an on-chain verifier can take, since a contract cannot hold the
book. Against: U3's sentence is "settlement trusts no solver", and accepting
solver-supplied certificates narrows "re-derive everything against the
*current* book" to "verify what the solver chose to prove against the roots
it chose to pin" — freshness (still unfilled?) and completeness (all gates
run?) are exactly what a certificate does not carry. Until the fork is
decided, the rule is: **certificates may make settlement cheaper, never
smaller** — every U3 gate still runs, sourced from the live book or from a
verified proof against it.

## 5. Absence proofs: every non-monotone claim names a root

ontodag's as-of clause (`CONTRACT.md` §4): "Monotone questions may be asked
of the living store. Non-monotone questions must name a root." Adopted
verbatim for the book, with recordstore's absence proofs as the evidence
(planned-invariant tail, quoted: "non-monotone claims (offer absent, no
better loop) always name a root (backed by absence proofs)"). Concretely:

- **"Offer X is not in the book"** is ill-formed; "offer X is not in book
  root R" is a trie absence proof for `offer/<offer_id>` against R.
- **"Offer X is unfilled"** — the claim every settlement and every dispute
  turns on — is an absence proof for `fill/<offer_id>` against a named root.
  The P2 contract consumes exactly this shape: per-leg inclusion of the
  offer *and* absence of its fill, both against the anchored root.
- **"Maker M has not withdrawn X"** is an absence proof for the tombstone
  key (`P1-federated-book.md`), against the aggregator's manifest root.
- **"No better loop than L"** decomposes honestly: the book being *exactly*
  the set proven is root-naming plus absence proofs, but the superlative is
  a claim about search completeness, which no trie proof carries. Provable:
  the inputs and the deterministic baseline's replayability (U6 — same book,
  same loop). Only attested: that a *smarter* solver could not have done
  better. The batch auction scores accordingly (`P2-batch-auction.md`); the
  residual is an open problem below.

## 6. Proofs as legal artifacts

Every loop participant receives, with their receipt, inclusion proofs of
their own offer and their own fill under the settled root — following the
Cycles protocol's practice of per-party cryptographic inclusion proofs kept
for legal purposes (arXiv:2507.22309). The participant needs no Bee node, no
Python, and no trust in the aggregator to hold evidence that their leg
settled: a receipt envelope plus 32 bytes is a self-contained exhibit
(decided 2026-08, lands with P2). This is also the privacy-compatible shape:
an authenticated-path proof is exactly the circuit family P4 would wrap in a
SNARK for private book inclusion, so nothing here needs redesign when
`P4-privacy.md` lands — designed ZK-wrappable, not ZK-promised.

## 7. The cone-commitment tripwire, fired at P2 start

ontodag's `DATABASE_DIRECTION.md` walls off the Merkle-ized semantic DAG
(per-node cone commitments) behind a tripwire: "someone needs a ⊑ claim
verified on-chain (factbond dispute settlement, loopmarket P2 settlement)".
It would buy path-sized, order-free positive subsumption proofs — "the one
proof shape a contract can check, where re-execution certificates cannot
run". **This document fires that tripwire formally at P2 start**: when the
on-chain verifier design begins, loopmarket files the upstream ask for a
*derived cone-commitment index* (own store, own root, never merged — the
sanctioned admissible form, kin to the DimensionIndex discipline) rather
than building any subsumption verification loopmarket-side, which would fork
`is_below` into a second implementation with its own bugs. The treaty
(`ontodag-coupling.md`) exists so walls are crossed upstream, once, with
conformance tests.

## 8. One fabric, two consumers: factbond's rung zero

factbond F8, quoted: "structural claims settle by certificate only." A
dispute of the form "the catalogue at root R says the cello fits the crate"
or "offer X was in book root R" terminates at a proof checker — no jurors,
no evidence policy, no adjudication ladder — using the same `verify_proof` /
`verify_below` this document standardizes (factbond `docs/INTEGRATION.md`
§5, `docs/plans/records-and-anchoring.md`). Only `attribute-matches-world`
claims ("and the crate really held it") escalate to the expensive rungs.
This split is a threat-surface decision, not just an economy: it removes the
structural half of every dispute from T4 (adjudication capture & dispute
griefing — primary: factbond `docs/plans/THREATS.md`) because a captured
tribunal cannot overrule a hash chain, and it narrows T9 (basis-risk
disputes — primary: factbond) by making "what the record said" mechanically
undisputable, leaving only "what the world did" contestable. One proof path,
two consumers, shared conformance tests.

## Gates

- **G1 — floor raise (unblocks everything).** recordstore floor ≥ 0.16.0
  (`prove`/`verify_proof`); ontodag floor at a release carrying
  `ontodag.certificates`. Go: `tests/test_boundaries.py` still green (B1 —
  proofs are core, not Swarm). Owner: the v2-bump commit.
- **G2 — pin closure.** Closed when: an unpinned offer fails `check_match`
  against any pinned offer in tests; `MockSettlement` refuses a proposal
  whose pins mismatch its roots or are absent; offer record v2 carries
  REGISTRY_VERSION + CONTRACT_VERSION with `from_record` still reading v1;
  the U2 id-stability suite passes across the bump. U10 enters CLAUDE.md
  only when these tests land (marking convention). Owner: the v2 bump.
- **G3 — certificate double-check.** `MockSettlement` verifies attached
  `satisfies` certificates alongside re-derivation; go: N settled loops
  (triangle + randomized books) with zero verdict divergence; any divergence
  is a halting defect filed upstream. No-go blocks the doctrine-fork
  discussion — a fork about replacement is premature while the double-check
  has never run. Owner: P2 prep.
- **G4 — POT adoption (conditional).** Only if the P2 contract design shows
  anchored recordstore roots + BMT-verified trie paths cannot serve the
  verifier; then only with (a) a specified mirroring step whose root
  fidelity is itself proven, (b) self-benchmarked `assertForkPathProof` gas
  on Gnosis, (c) a pinned vetted commit + conformance tests. Absent any of
  the three, POT stays out. Owner: P2 contract work (`P2-batch-auction.md`).
- **G5 — tripwire filing.** At P2 start, the cone-commitment ask is filed
  upstream before any on-chain subsumption design begins here. Go criterion
  is procedural: the ask exists in ontodag's tripwire log and
  `ontodag-coupling.md` records the answer. Owner: P2 kickoff.

## Open problems

- **Certificates replacing U3 re-derivation (the doctrine fork).** §4 keeps
  certificates additive; the on-chain path will pressure them to become
  substitutive, because a contract *cannot* re-derive against a live book.
  Unresolved: whether "verified proof + absence-of-fill against a pinned
  root" is U3-equivalent or U3-weaker, and what freshness guarantee replaces
  "the *current* book" when the verifier is a contract. Discussion agenda
  item; work package: P2 settlement design (`P2-batch-auction.md`),
  revising this document.
- **POT mirroring fidelity.** If G4 fires, the POT root and the recordstore
  root describe the same book through different trees; the proof that they
  agree (every key, both directions) is itself a non-monotone completeness
  claim and must not be hand-waved as "the mirroring code is correct". Work
  package: P2, only if POT is adopted.
- **The provable content of "no better loop".** §5 shows the superlative
  outruns the trie. Candidate resolutions — score-based auctions that never
  claim optimality, per-beat re-execution bounties, committed solver search
  transcripts — belong to the batch-auction design. Work package:
  `P2-batch-auction.md` / `P2-loop-selection.md`.
- **Receipt anchoring cadence.** Which roots go on-chain and how often
  (every settlement, every beat, daily) trades gas against the dispute
  window's evidence needs; factbond's anchored-time design (its
  `docs/plans/records-and-anchoring.md`) is the other consumer of the same
  anchor and should share it. Work package: P2 + factbond records.
- **b33son adoption.** Field-granular BMT proofs would let a dispute reveal
  one offer field instead of the record — valuable for P4, but the encoding
  choice reshapes record identity and must not churn `offer_id` (U2). Watch
  item; work package: P4 (`P4-privacy.md`) jointly with factbond evidence
  storage.

## What this document does not promise

Proofs attest structure, never truth (ontodag's L1; factbond F7 — "certified
≠ true" on every surface). An inclusion proof shows the book at root R
contained the offer — not that the maker will perform, not that the crate
held the cello. Settlement plus this fabric certifies **re-verification, not
delivery**; the world-side residual belongs to oracles and factbond's
evidence policy, priced, never proven. A pinned root is not freshness:
absence at R says nothing about the store one commit later, which is exactly
why U10 forces every such claim to say "at R" out loud. The POT gas figures
quoted here are envelopes, not measurements — no number from §1 may be cited
as a benchmark until G4's own benchmark exists. And nothing here is private:
every proof reveals its subject and its path; ZK-wrappability (§6) is a
compatibility property we preserve, not a privacy layer we deliver — that is
`P4-privacy.md`'s burden, explicitly not discharged here.
