# loopmarket — architecture

A distributed offer registry and loop-finding system over the
OntoDAG / recordstore / Swarm stack. This document records the design and its
rationale; `CLAUDE.md` records the working rules derived from it.

## 1. The shape of the system

```
                       ┌───────────────────────────────┐
                       │   shared catalogue (OntoDAG)   │
                       │  categories ⊑ categories;      │
                       │  pinned roots via EagerOntoDAG │
                       └──────────────┬────────────────┘
                                      │ satisfies(offered, wanted)
   makers                             ▼
  ┌───────┐  publish   ┌───────────────────────────────┐   snapshot(root)
  │ offer │──────────▶ │   offer book (recordstore)     │◀───────────────┐
  └───────┘            │  offer/ fill/ loop/ idx/{c,t,g}│                │
       ▲               │  canonical roots, snapshots,   │        ┌──────┴──────┐
       │ fills land    │  reconcile-merge, Swarm blobs  │        │ solver agent │
       │ atomically    └──────────────┬────────────────┘        │ (any number, │
       │                              │                          │  competing)  │
  ┌────┴─────────┐   verified loop    │                          └──────┬──────┘
  │  settlement  │◀───────────────────┼──────────── LoopProposal ───────┘
  │ (re-verifies │                    │              (pinned book_root,
  │  everything) │────────────────────┘               ontology_root)
  └──────────────┘
```

One catalogue, one book, many solvers, one verifier. Discovery is expensive,
competitive and untrusted; verification is cheap, neutral and mandatory.

**Update 2026-08-07 — the book federates.** The diagram above remains the
*logical* shape; the committed *deployment* shape (P1, decided 2026-08) is
one book per maker under the maker's own feed and signer, folded by
aggregators into a published snapshot — deployment shape 3 of §5, promoted
from roadmap item to primary target. What changes is who writes where;
nothing about the keyspace, the solver interface, or settlement's
trust-nothing stance moves. The full work package, including the
announcement channel and the aggregator's operational footprint, is
`docs/plans/P1-federated-book.md`; the design-plan corpus is indexed on
the repo front page (`README.md`).

## 2. The uniform offer (schema.py)

Every offer exchanges a **Thing** (conjunction of catalogue categories +
quantity + service `TimeWindow` + service `GeoDisc` + validity window)
against **Tokens** of the maker's personal numéraire. Exactly one side is the
maker's own token — enforced in the constructor, not documented as a
convention. This uniformity is what makes the entire marketplace one data
structure: transport, storage, aggregation, compute and cabbages differ only
in their category sets.

The **personal scale** is bookkeeping (a personal numeraire — "personal
token" is this concept's earlier name, kept by the record encoding's
`Tokens` side and older documents; vocabulary settled 2026-08-21): a maker
prices everything on one private scale, so k gives and m wants relate
through k+m numbers, not k×m pairwise rates — and the factoring makes a
maker's quotes transitive by construction, so nobody can arbitrage a maker
against their own rate matrix. Nothing is held or transferred: the scale's
numbers exist only long enough for a loop to pass through the maker
and cancel; liquidity is supplied by offers whose Thing is itself a currency
(bridge offers), never by personal scales.

Offers are immutable values with a canonical encoding (recordstore's
canonical JSON; concept tuples sorted) and a content address
(`offer_id = SHA-256(canonical_bytes)`). The Swarm reference a blob store
assigns is a storage detail; the logical id is the application-layer key.
`bond`, `oracle`, `arbitrator` ride in the encoding from day one (identity
stability for P3) but are not yet enforced.

**Update 2026-08-07 — authenticity and the v2 record (decided 2026-08;
the record bump landed 2026-08-20).** The multi-writer book needs makers
to be unforgeable. The decided design (planned invariant U8) is two-layer:
in per-maker books, *feed ownership* is the primary authenticity — an
offer is the maker's because it arrived on the maker's signed feed — and a
*detached* signature over the offer's id (the hash of its canonical bytes)
covers offers circulating outside their home feed. The signature never
enters the canonical bytes (root purity and `offer_id` stability are the
treaty with ontodag; nothing that varies between honest replicas may enter
identity), and aggregators record `origin/<offer_id>` so provenance
survives the merge. Landed 2026-08-20: the sign/recover primitives
(`sigs.py`, the `sig` extra) and the registry's fail-closed `sig/`
sidecar; the fold rule that makes them an *invariant* lands with the P1
aggregator. The same v2 bump carries: pins widened to
{`book_root`, `ontology_root`, `REGISTRY_VERSION`, `CONTRACT_VERSION`}
(planned U10 — the dimension registry participates in canonical reduction,
so the ontology root alone under-specifies the pinned semantics; the
fail-open empty-pin gate in `check_match` closed 2026-08-20 — a pinned
catalogue refuses unpinned offers, mixed pinning always refuses, and
settlement demands pin equality), `from_record`
version dispatch that *raises* on unknown versions (U2 enforced rather
than assumed), and a decision on `loop_id` encoding leg pairing (decided
and landed 2026-08-20: the id hashes the leg cycle under its
lexicographically minimal rotation — rotation-invariant,
pairing-sensitive — so distinct pairings over the same offer set cannot
collide on one `loop/` key). One scope rule enters schema validation now: flat roles are sound
only for one filler per role per offer (ontodag `BINDING` §1) — composite
offers are separate legs joined by the solver, never bundles.

## 3. Time and place are catalogue dimensions (spacetime.py)

Interval containment, region containment and category subsumption are the
same partial order — *fits-within*. The prototype keeps exact geometry in
`schema.py` (interval overlap/containment; disc containment/intersection via
haversine) and derives discretised **names** whose prefix structure mirrors
containment:

- time: `2026` ⊐ `2026-08` ⊐ `2026-08-14` (day buckets + chains)
- space: geohash prefixes, where every longer cell fits within every shorter
  prefix of itself

These names serve today as recordstore index prefixes (`idx/t/`, `idx/g/`),
and on the P1 roadmap become *generated category nodes in the shared
OntoDAG*, so that candidate generation is one native query — the
intersection of descendant cones of {concept, cell, bucket} — with exact
geometry as the refinement. Cells index disc centres only (boundary-crossing
discs also touch neighbours), which is safe because cells are hints:
`matching.py` re-checks everything exactly.

The full catalogue contract — the completion of this migration, unit
families for quantities and personal tokens, the match-degree ladder, and
the upstream-vs-local tripwire table — is `docs/plans/ontodag-coupling.md`
(2026-08-07); the seeding and governance of the catalogue's *content* is
`docs/plans/catalogue-bootstrap.md`.

**Update 2026-07-30 — ontodag dimension lattices.** ontodag's
parametric-items design is agreed (`ontodag/docs/DIMENSIONS.md`) and
**shipped the same day as ontodag 0.4.0 on PyPI** — including
`get_overlapping`, the possibly-satisfies query op the time/geo gates
want, and `LazyOntoDAG` support. **Adopted here 2026-07-30 as
`dimensions.py`**: a `DimensionIndex` files gives under their exact service
window (one linear-interval value) and centre cell (one prefix value) in a
*derived deepcopy* of the catalogue — never the shared catalogue itself, so
offer-pinned roots stay stable — and `candidate_matches_indexed` generates a
want's candidates from `get(wanted)` ∩ `get_overlapping(window)`, recall-exact
against the baseline product (tests/test_dimensions.py proves equality over
randomized books). Geo deliberately stays with the exact check. The original
plan below is kept for context; the bucket/cell chains it describes are
superseded:
time windows become exact linear-interval terms (`time(a..b)`), queryable
as *virtual* terms — generated time-bucket nodes drop out entirely;
geohash cells become a `prefix-dimension` whose containment is computed
from the name, so only used cells materialize; named service regions
become ordinary nodes over their interior cells (any shape, holes,
disconnected), with coverage queries as ancestor walks; and a
`get_overlapping` query op (ontodag's first follow-up) eventually replaces
bucket fan-out for the overlap-shaped time/geo gates. Two rules to observe
on adoption: **never multi-parent an offer under several cells** — that
asserts the (near-empty) intersection, not the union; use a region node
(ontodag will reject provably-disjoint parametric parents) — and **pin
ontodag's dimension-registry version alongside the ontology root**, since
the computed order participates in canonical reduction. None of this
moves the truth: `check_match` stays exact and self-contained; cells and
cones remain recall-safe hints.

## 4. The catalogue (ontology.py)

`Ontology` wraps an `OntoDAG` with the one primitive matching needs:
`satisfies(offered_concepts, wanted_concepts)` — every wanted category is
covered by some offered concept (equal or an ancestor of it). Unknown
vocabulary fails closed. Since 2026-07-31 the per-pair coverage test runs on
ontodag's Boolean `is_below` (>= 0.7.0): an upward walk from the offered
concept with early exit, bounded by its shallow ancestor cone — never by
enumerating the wanted category's descendants. Division of labor with §6:
*queries* (`get`/`get_overlapping`, the DimensionIndex) generate candidates
one-to-many; the *Boolean* answers the pairwise truth that settlement
re-verifies — same fits-within relation, set-valued for discovery,
point-valued for proof.

Persistence goes through `EagerOntoDAG` over a duck-typed RecordStore;
`commit()` yields a canonical root. Offers pin the root they were written
against, matching refuses to pair offers pinned to different roots, and
proposals carry the root they were checked under: the semantic ground cannot
move beneath a committed loop, and "which catalogue said the cello fits the
crate" is answerable forever. Bonded assertions (stakes on ⊑ edges, scaled to
centrality) are P3; `assert_edge(sub, supers, bond=)` already carries the
argument.

**Update 2026-08-01 — the P3 mechanism design has a home: factbond**
(github.com/petfold/factbond, design stage; grew out of the
prediction-markets-for-facts discussion). Its bonded-assertion /
optimistic-oracle design — bonds sized to adjudication cost not notional,
odds-weighted disputes set by the asserter's stated confidence, a shared
yield-bearing bond pool, an escalating adjudication ladder — is exactly the
machinery "stakes on ⊑ edges" needs, so P3 should adopt it rather than
redesign it. Two loopmarket-specific consequences worked out in factbond's
`docs/INTEGRATION.md` §8:

- **Settlement-attached information insurance.** A settling loop *relied
  on* specific catalogue edges (`satisfies` walked them; settlement
  re-verified them) — exactly the facts whose falsity costs the
  participants money, i.e. insurable facts with natural consumers.
  Settlement can auto-attach a hedge on those edges; a payout auto-funds a
  dispute on the edge that lied. Loop participants become the shared
  catalogue's verification workforce, and the pool's loss experience
  becomes a per-edge reliability audit of the catalogue — the data P3's
  "aggregated risk markets feeding rate premia" needs.
- **Claims about the pinned catalogue adjudicate mechanically.** "The
  catalogue at root R says the cello fits the crate" settles by certificate
  (ontodag `CONTRACT.md` §7 — `is_below` witness paths, trie
  inclusion/absence proofs), the same proof family as the §8 settlement
  path below; only "and the crate really held it" needs oracles,
  countersigning, or arbitrators. The split keeps the expensive machinery
  off the structural half of every dispute.

**Update 2026-08-07 — the coupling is now committed mechanism, not
analysis.** The two consequences above graduated from "worked out in
factbond's INTEGRATION.md" to a specified work package on both sides:
`docs/plans/P3-guarantee-coupling.md` here (witness-edge instrumentation —
settlement emits the exact ⊑ edges `satisfies` walked per settled loop;
insurance payouts capped by *provable reliance* on those edges, which
settlement roots supply for free; per-edge loss experience feeding solver
rate premia; the oracle roster; solver bonds routed through the shared
pool) and `docs/plans/loopmarket-coupling.md` in factbond (sequencing: the
coupling ships only after factbond's Phase-0 simulation is green *and*
P2's record formats freeze — witness telemetry alone lands earlier, since
it depends on nothing). The boundary discipline is unchanged: the core
model keeps running with no guarantee fabric present.

## 5. The book (registry.py)

One book = one recordstore keyspace = one root reference per version:

```
offer/<offer_id>                the immutable offer record
fill/<offer_id>                 {"loop": <loop_id>}
loop/<loop_id>                  the settled loop record
idx/c/<concept>/<offer_id>      per thing concept
idx/t/<bucket>/<offer_id>       per touched day + its month/year chain
idx/g/<cell-prefix>/<offer_id>  per geohash prefix of the service cell
```

recordstore supplies exactly the properties the book needs:

- **Snapshot isolation for solving.** `snapshot()` = `(root,
  RecordStore.at(root, blobs))`; a solver works against a frozen,
  self-consistent book for as long as it likes, at zero cost.
- **Atomic settlement.** All fills of a loop plus the loop record land in one
  `commit()` — a reader sees the loop entirely settled or not at all.
- **Canonical roots.** Equal book content ⇒ equal root, independent of
  history: books are diffable, auditable, and byte-identically reproducible.
- **Multi-writer convergence.** Offers are add-only values of canonical
  content, so concurrent publication is naturally an OR-set;
  `commit(reconcile=True, resolver=or_set_resolver)` merges concurrent
  writers, with the one racy key class (`fill/` — settlement claims)
  resolved first-writer-wins by smallest loop id, deterministically and
  commutatively on every replica.

Deployment shapes, same key layout throughout:

1. **Local / tests:** `RecordStore(MemoryBytesStore()|DirBytesStore(...))`.
2. **Shared book on Swarm:** `swarm_offer_book(topic, signer=...)` —
   recordstore's `swarm_store`: blobs through `BeeBytesStore` (Bee `/bytes`),
   the mutable head an owner-signed `SwarmFeedPointer`, with best-effort
   `compare_and_set` for cross-process reconcile.
3. **Fully peer-to-peer (P1):** one book per maker, each under the maker's
   own feed and signer — no shared write authority at all. Aggregators
   (solvers, indexers) fold maker roots with `RecordStore.merge`, which the
   canonical trie makes O(divergence). Publication authenticity comes from
   feed ownership; nothing about the layout changes.

**Update 2026-08-07 — shape 3 is the production shape; shape 2 is demoted
to a development and demo tool (ratified by owner sign-off 2026-08-21).** The demotion is forced by an honest look
at the substrate, not a change of heart: `SwarmFeedPointer.compare_and_set`
is best-effort (Swarm has no feed index-claim primitive), so two writers on
one feed can race — the one-signer-per-feed rule of shape 3 *is* the safety
model, and settlement atomicity must never rest on the feed CAS. The
2026-08-01 live milestone stands as proof the stack works end-to-end on a
real network; it is the write-authority shape that does not survive
multi-writer production. With federation come the decided mechanics
(`docs/plans/P1-federated-book.md`): maker→aggregator announcement over
GSOC with a Gnosis registry-event fallback; the aggregator (a full Bee
node) publishing a manifest tuple {book_root, provenance_root, index_root,
announcement_root} (fourth element 2026-08-21: the folded input-set
commitment that makes aggregator completeness provable — T14)
as the one solver-speed read path (feed lookups cost seconds — polling
per-maker feeds does not scale); withdrawal as signed tombstones under
grow-only merge; and two merge-discipline fixes found by code review
(planned invariant U11): fill records lose their wall-clock timestamp —
equal settlements must produce equal roots (landed 2026-08-20, with a
replica-determinism test) — and fill-conflict resolution moves from
per-key to loop granularity, checked by a post-merge invariant that every
`loop/` record has all its `fill/` keys (the loudly-failing checker
landed 2026-08-20; the deterministic loop-granularity *resolver* remains
the registered open problem). The ops posture is
equally explicit: the network is thin (~4,000 reachable full nodes,
provider-concentrated), so the book always keeps one self-hosted pinning
node; blobs get erasure coding, feed heads cannot (single-chunk — they rely
on neighbourhood replication); feed batches are mutable, and postage expiry
is silent data loss, so stamp TTL is treated as a *hard offer-lifetime
bound* with a TTL monitor. **In-memory landing, 2026-08-21:** withdrawal
tombstones, the aggregator fold with the U8 admission rules and a U11
check inside every fold, and the four-root manifest are code
(`federation.py`), with memory-backed convergence, follower and
withdrawal gate tests green; the feed, announcement and durability
halves remain the live-Bee work.

Postage-stamp economics went from "deliberately not modelled" to a decided
frame (2026-08-07): the stamp is the offer's rent — validity windows must
fit inside batch TTL; anyone may top up a batch permissionlessly, which
makes "solvers subsidize the books that feed them loops" a concrete
solver-ecology mechanism; and the per-offer postage cost doubles as the
sybil floor (§11). Numbers, granularity and the open steady-state question
live in `docs/plans/P1-federated-book.md`.

## 6. Matching (matching.py)

`check_match(give, want, ontology, now)` is the exact, self-contained pairwise
truth: kinds and distinct makers; both validity windows open; service windows
overlap (a delivery instant exists); service discs intersect (a handover
point exists); quantity within capacity (equality unless divisible); same
unit; agreeing ontology pins; and `satisfies` under the catalogue. Its
self-containedness is a design requirement, not tidiness: settlement re-runs
it, so no index, cache or heuristic may be load-bearing for correctness.

The baseline candidate generator is the full give×want product with the
constant-time gates doing the pruning — right for in-memory books, and the
benchmark smarter generators must not fall behind on recall.

## 7. The arithmetic of loops (graph.py)

Nodes are personal tokens; a `Match` is an edge giver→receiver with rate
`r = want.unit_price / give.unit_price`. Around a cycle the product telescopes
into Π(node's want price / node's give price): **product > 1** means positive
surplus. With divisible quantities this is exact — quantities can scale so
each node's token inflow and outflow cancel, and the slack is genuinely
distributable surplus. With indivisible unit legs, exact cancellation needs
the conservative **per-node condition** (each node's want price ≥ its own give price),
which `Loop.per_node_ok` reports and settlement enforces for non-divisible
loops. Real settlement pricing — choosing actual prices inside each
[give, want] interval and distributing the surplus — is P2.

**No negative prices, ever (invariant U5).** −log of a rate requires the
rate positive; a minus sign anywhere breaks the cycle arithmetic. Disposal
is a positively-priced *service* ("removal of X"); emptiness is a
positively-priced *good*. The waste/recycling economy needs no signed
numbers, only the right category names.

Search: weights `w = −log r`, so profitable loops are negative cycles;
Bellman–Ford with predecessor extraction finds one in O(V·E), deterministic
by sorted iteration (same book ⇒ same loop on every replica — reproducible
audits). `find_profitable_loops` greedily extracts disjoint loops. This is
the *baseline species*: exact, slow, honest. The solver ecology is expected
to beat it (motif libraries, planners over the index prefixes, learned
candidate generators); nothing they do is trusted, so nothing they do is
restricted.

**Update 2026-08-07 — the boundary has a name, and the baseline has a
recorded defect.** The divisibility caveat is exactly the complexity
boundary of the clearing literature: with divisible legs the clearing
problem is a min-cost-flow LP (polynomial — the Cycles protocol's
formulation, validated against Slovenia's compulsory set-off data); with
indivisible
legs and bounded cycle length it is maximum-weight vertex-disjoint cycle
packing, NP-hard (Abraham–Blum–Sandholm), solved exactly at realistic beat
sizes by ILP. Greedy negative-cycle extraction provably blocks better
packings, so at P2 it is demoted from settlement-facing selector to the
protocol's *reserve bid* (§8) — a promotion to normative status (ratified
by owner sign-off 2026-08-21, agenda item 3) that is
**preconditioned** on *fixing* a recorded defect — the document-only
fallback was withdrawn at ratification: the
best-rate-per-pair edge reduction can lose feasible loops (a lower-rate
parallel edge may satisfy the per-node condition where the best-rate edge
fails), and the post-hoc `min_surplus` check can mask qualifying cycles
behind a sub-threshold one. Two further commitments land with P2: *chains*
alongside cycles — receive-before-give ordering degrades gracefully
(renege = truncation, the kidney-chain result), while any give-before-
receive leg is a bridge donor and needs a bond, i.e. P3 machinery — and
*exact arithmetic* (planned invariant U9): every quantity, price and rate
settlement re-verifies becomes a reduced rational via ontodag unit
families; `−log` weights remain a search heuristic, never a truth an
on-chain verifier is asked to reproduce. Formulations, the failure-aware
objective and pre-commit netting: `docs/plans/P2-loop-selection.md`.

## 8. Settlement (settlement.py)

`LoopProposal` = the loop + the pinned `book_root` and `ontology_root` + the
solver's identity. `MockSettlement.submit`:

1. every offer exists in the *current* book, is unfilled, is used once;
2. every leg re-derived with `check_match` — the solver's matches are
   never believed;
3. product ≥ minimum surplus; per-node condition when any leg is indivisible;
4. one atomic commit: all `fill/` records + the `loop/` record under a
   single new root.

The interface (`Settlement.submit(proposal) → Receipt`) is the stable
boundary. The P2 on-chain backend keeps its shape: a Gnosis Chain contract
receives the loop plus **inclusion proofs** that each offer is present under
the pinned book root.

**Update 2026-08-07 — the proof route is reversed (ratified by owner
sign-off 2026-08-21).**
An earlier revision of this section committed to the Proximity Order Trie
(`ForkPathProof` + `POTProofVerifier`). That commitment is withdrawn:
recordstore's canonical-trie **inclusion and absence proofs shipped**
(`RecordStore.prove` / `verify_proof`, recordstore ≥ 0.16.0) and prove
against the very root the book already pins — no mirroring step, and
absence proofs come free (a settlement dispute can prove "offer X is *not*
in book root R"). POT remains the conditional fallback if the on-chain
verifier demands BMT-native proofs, adopted only after a mirroring step
(recordstore roots are not POT roots), self-benchmarked gas (none
published), and pinning a vetted commit of a pre-1.0 repo whose proof
logic saw fixes as late as 2026. The decision rule, the certificate
envelope policy, the four-element pin table, and the role of `is_below`
certificates in settlement (double-check now; whether they may ever
*replace* re-derivation is a flagged doctrine fork on U3) are
`docs/plans/proof-fabric.md`.

The vague "rank by participant surplus, rebate it" is replaced by a
committed beat design (2026-08-07): sealed per-beat proposals (a loop
proposal is trivially copyable), numeraire-free scoring, a per-offer
fairness floor generalized from CoW's CIP-67 (subsuming `per_node_ok` as
policy), marginal-contribution solver rewards capped by the fees the
solver's own loops generated, and the deterministic baseline as permanent
reserve bid — `docs/plans/P2-batch-auction.md`. The pricing rule that
turns a winning loop's surplus into per-leg prices — equal log-surplus
split under uniform directional clearing — is
`docs/plans/P2-settlement-pricing.md`.

## 9. The solver agent (solver/agent.py)

`step()`: snapshot → load active offers → exact matches → best-rate graph →
negative cycles → proposals. Deliberately trust-poor in both directions:
solves only against pinned roots (reproducible), and produces nothing that
is believed (settlement re-derives). `run()` polls a live book. Multiple
agents against one book are safe by construction: first valid proposal
wins, the rest are rejected on the `fill/` check.

## 10. What is deliberately absent

Bonds/oracles/arbitrators (carried, unenforced — P3; the mechanism design
now lives in the **factbond** sister repo — see the §4 update), aggregated
risk markets and rate premia (P3, fed by factbond's per-edge loss
experience), batch auctions and settlement pricing (P2 — now specified in
`docs/plans/P2-batch-auction.md` and `docs/plans/P2-settlement-pricing.md`),
privacy — staged disclosure, committed offers, ZK fits-within proofs (P4 —
now staged in `docs/plans/P4-privacy.md`, whose Tier 1 needs no new
cryptography and whose format-freeze list *constrains P2*),
bridges to legacy inventory (thin adapters that publish GIVE/WANT pairs plus a
currency leg; they are ordinary makers and need no new mechanism, so they
live outside this repo — their economics as the cheapest thickness
multiplier are in `docs/plans/adoption-and-thickness.md`), and
postage-stamp economics (framed in the §5 update, numbers in
`docs/plans/P1-federated-book.md`). Each absence is a scheduled decision,
not an oversight; see CLAUDE.md "Known simplifications" and the plan index
on the front page (`README.md`).

## 11. Economic security (planned; specified 2026-08-07)

One structural fact shapes everything here: **legitimate loops are
self-financing cycles** — the exact graph shape every wash-trading detector
keys on. Shape detection would flag the product itself, so the defenses are
by construction, not by policing:

**Update 2026-08-21 — agenda item 4 ratified: no protocol fees.** The
bullets below were specified assuming a per-leg fee; the ruling deletes
the assumption and strengthens the position. There are **no protocol
emissions at all** — no fees, rewards, rebates, or treasury — so U13
hardens to factbond F9's shape and the inequality below becomes the gate
any *future* emission proposal must pass. U12's ledger is settled
**cost-borne** loops (floor: postage + settlement gas). Solver
compensation is an endogenous spread bounded by the reserve bid;
aggregators sell service, never inclusion (T14); revisit triggers
(monoculture, aggregator scarcity, measured statistics pollution) are the
only path back to any emission, through the U13 gate.

- **The wash-loop inequality (planned invariant U13).** For any loop a
  single principal could run through sybils, the sum of all subsidies and
  rewards it can reach must be strictly less than the fees it pays — a
  budget-balance condition checkable at design time. Corollaries: fees are
  charged per leg in an external asset (never personal tokens, never
  rebated in anything volume-linked), and surplus rebates redistribute only
  the loop's *own* surplus.
- **Statistics count settled, fee-paid loops only (planned U12).** A sybil
  cannot appear in a settled loop without a real counterparty on every leg,
  so that ledger is the one thing sybils cannot cheaply populate; every
  reward, reputation, centrality and premium statistic reads from it and
  nothing else.
- **Sybil defense is a cost curve, not detection.** Per-offer postage plus
  per-commit fees set a floor; no per-offer benefit may exceed it.
- **Scoring is numeraire-free (planned U14).** No external price of any
  personal token is ever assumed in scoring, fairness, or rewards.

The threat register — nine attacks ordered by expected damage to a *young*
system, each with its economics, by-construction defense, residual risk and
tripwire metric — is `docs/plans/THREATS.md` (mirrored in factbond). The
full set of planned invariants U8–U14 is specified across the plan docs
that motivate each (index: the front-page `README.md`; U8/U10 in §2's update
note above, U11 in §5's, U9 in §7's, U12–U14 here); they enter CLAUDE.md
as binding invariants only when the enforcing code and tests land.

## 12. What this architecture does not promise

The honesty discipline every design document in this programme carries,
stated once at architecture altitude. Settlement certifies *re-verification
against pinned roots*, not delivery — the physical world can still renege;
that gap is priced (P3), never closed. The catalogue certifies asserted
structure, never world-truth (ontodag L1); "the cello fits the crate" at
root R is a fact about R. factbond's `Certified` means *nobody found it
profitable to dispute under a named procedure at named stakes* — and every
consumer surface must preserve that wording (factbond invariant F7).
Premiums and odds are prices under capital constraints and attack, not
probabilities. And a green simulation certifies nothing about model risk:
Phase-0 gates can kill designs, never prove them.
