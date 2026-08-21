# loopmarket — P1: the federated book

Status: design, 2026-08-07. Decided here: one book per maker under the
maker's own feed and signer, maker = feed-owner address; two-layer offer
authenticity (U8) with detached signatures and fold-time `origin/` records;
fill determinism and loop-granularity merge (U11); GSOC announcements with
a Gnosis registry-event fallback and defined switchover thresholds; the
aggregator as a full Bee node publishing the manifest tuple
`{book_root, provenance_root, index_root, announcement_root}` (the
fourth element added 2026-08-21); stamp TTL as the hard
offer-lifetime bound, permissionless top-up as a solver-ecology mechanism;
withdrawal as monotone tombstones; the shared-Swarm-book deployment demoted
to a development tool (flagged); dead `idx/{c,t,g}` writes dropped from
maker books, reborn as the aggregator's derived index. Open here: the
deterministic loop-granularity resolver; resurrection windows; aggregator
economics; GSOC reliability; the announcement-layer spam floor.

This is the per-maker-book work package: everything between today's
shared-book demo (`tests/test_swarm_book.py`, settled live 2026-08-01) and
a multi-writer network book a solver can read at solver speed. Everything
below is unbuilt unless stated; record-format changes are marked "lands
with the v2 bump". Companions: `ARCHITECTURE.md` §5,
`docs/plans/proof-fabric.md` (pins, proofs), `docs/plans/P2-batch-auction.md`
(fees), `docs/plans/THREATS.md` (T2, T8), `docs/plans/P4-privacy.md`,
`docs/plans/ontodag-coupling.md` (derived-index discipline), and factbond's
`docs/plans/records-and-anchoring.md` (anchored time).

## 1. One book per maker, and who an offer is from (U8)

The key layout does not change; write authority does. Each maker publishes
their own recordstore keyspace under their own Swarm feed and signer — no
shared write authority anywhere. Feeds are addressed by (owner Ethereum
address, topic); we make **maker = the feed-owner address**, so one
identity serves three roles: feed ownership authenticates publication,
signature recovery authenticates off-feed copies, and P2's on-chain
settlement gets the same address for free.

Today `maker` is an unauthenticated string — anyone can publish offers
naming anyone (loopmarket-code review, 2026-08-06) — and a fold launders
the forgery: once merged, nothing records which feed an offer came from.
Two layers close this (planned invariant **U8**: "two-layer offer
authenticity (feed ownership primary; detached signature for off-feed
circulation; nothing signed enters canonical bytes)"):

- **Primary: feed ownership.** At fold time the aggregator verifies each
  offer's `maker` equals the owner of the feed it was read from, and
  records `origin/<offer_id> = {owner, topic, feed_index}` in its own
  provenance store (§2) — an attributed observation, so "which feed said
  this" is answerable forever and forged makers cannot reappear at the
  merge layer.
- **Secondary: a detached signature** — secp256k1 over the 32-byte
  `offer_id`, recoverable to `maker` — for offers circulating outside
  their home feed (gossip, solver forwarding, registry events, P2
  calldata). It lives beside the offer (`sig/<offer_id>`), never inside
  `canonical_bytes()`: offer ids stay stable, roots stay pure. (The v2
  bump landed 2026-08-20: `from_record` gained the version dispatch U2
  promised, and the sign/recover primitives plus the registry's
  fail-closed `sig/` sidecar shipped with it.) Fold rule, fail-closed in
  U7's spirit: an offer from a foreign feed without a valid signature
  never enters the fold — the aggregator's to enforce when it lands.

Who writes what: maker books carry `offer/` and `withdraw/` (§5) only.
Settlement is its own writer — `fill/` and `loop/` publish under the
settlement instance's feed and fold like any other book, so every keyspace
is single-writer at the source and conflicts exist only at the fold (§3).
The `idx/{c,t,g}` keys are written today and read by nothing (the solver
full-scans; `DimensionIndex` duplicates their job in memory); on Swarm each
publish would pay ~10+ chunk writes of waste. Decided 2026-08, lands with
P1: **dropped from maker books**, reborn as the aggregator's *derived*
index under `index_root` (§2) — the "wired" half of wired-or-dropped, at
the layer that actually queries.

## 2. The aggregator and the manifest tuple

Feed lookups cost seconds: Bee 2.7.0 (2026-02-04) made feed resolution
deterministic, but the live triangle still ran ~51 s end-to-end on a
Gnosis-mainnet light node, and a solver polling N maker feeds pays N
lookups. Aggregation is mandatory for solver-speed reads, not an
optimization. An **aggregator** is a full Bee node (GSOC reception
requires one, §4) that: subscribes to announcements; folds maker and
settlement books with `RecordStore.merge` under the loop-aware resolver
(§3), delta-driven via `RecordStore.diff` — the `merge_delta` pattern
ontodag shipped 2026-08-04, O(divergence), never O(store), which raises
loopmarket's recordstore floor from >=0.13.1 to >=0.16.0 (diff landed in
0.15.0; 0.16.0 adds `prove`/`verify_proof`, which
`docs/plans/proof-fabric.md` wants anyway); caches the last-seen feed
index per maker (sequence feeds resume from a known index — cold
multi-second probes become single-chunk reads); and publishes, under its
own feed, a signed **manifest tuple** `{book_root, provenance_root,
index_root, announcement_root}` — the pattern ontodag's cone summaries
pinned:

- `book_root` — the pure fold of the input books. Byte-identical across
  aggregators that saw the same inputs, in any fold order (merge is
  commutative; ontodag CONTRACT G5 is the precedent). The Gates check it.
- `provenance_root` — the aggregator's attributed speech acts: `origin/`
  records, fold decisions, rejections. Per-aggregator by construction
  (two aggregators legitimately observe different feed indices),
  union-merged, never part of `book_root` — ontodag's PROVENANCE split
  (attribution must never enter the knowledge root).
- `index_root` — derived query structures: the book-side cone-summary
  analogue, the `DimensionIndex`'s published sibling. Regenerable from
  `book_root`, short-TTL stamped (§6), ignored when stale, never merged —
  the derived-values-never-merge rule ontodag learned from counts.
- `announcement_root` (added 2026-08-21, with the item-4
  aggregator-revenue ruling) — a commitment to the announced input set
  this fold consumed. Completeness becomes first-class: two manifests are
  diffable at the input side, and (announced set) − (makers under
  `book_root`), backed by absence proofs against the registry-log ground
  truth, turns omission — including pay-to-be-indexed — into a proof,
  never a suspicion (T14). Aggregators charge for *serving* (latency,
  indexes, queries); an aggregator charging for *inclusion* is a
  censoring aggregator and is caught as one.

Solvers read manifests, never poll maker feeds. A thin solver need not
hydrate anything: `LazyOntoDAG` plus published summaries make broad-term
queries affordable (ontodag measured 375 → 3 fetches; live on Swarm,
1 record + 2 index fetches vs 71). Anyone can run an aggregator — inputs
are public feeds and byte-identical `book_root`s make aggregators
auditable against each other, so no solver gets exclusive order flow. U4
is unchanged: solvers solve against the manifest's pinned roots, and
proposals carry the full pin tuple — planned invariant **U10**:
"load-bearing pins {book_root, ontology_root, REGISTRY_VERSION,
CONTRACT_VERSION}, verifiers refuse on mismatch or absence". The
fail-open `''`-pin gate in `check_match` closes with the v2 bump; the
full pin table is `docs/plans/proof-fabric.md`'s.

## 3. Merge discipline: fills, loops, U11

Two code-review findings make today's fills unmergeable. `mark_filled`
stamps wall-clock `at`, ignoring settlement's injectable clock, so the
same logical settlement on two replicas yields different bytes — breaking
"equal content ⇒ equal root"; and `or_set_resolver` resolves `fill/` per
key, so two concurrently-settled loops sharing one offer merge into a
book where the losing loop keeps its `loop/` record and its *other*
fills — a "settled" loop missing a leg, which nothing repairs. Fixes:

- **Fill determinism** (landed 2026-08-20, with a replica-determinism
  test): the `fill/` record drops
  `at` — content is `{"loop": <loop_id>}`, a pure function of the
  settlement decision. Timestamps that matter are attributed provenance;
  when trustworthy time is needed (§5, dispute windows) it is **anchored
  time** — feed index or on-chain anchor — which is factbond's to build
  (factbond `docs/plans/records-and-anchoring.md`). The injectable clock
  still threads through settlement for validity checks; it never enters a
  record.
- **Loop-granularity resolution** — planned invariant **U11**: "no
  partially-filled loop survives a merge". Post-merge, every present
  `loop/<loop_id>` has a `fill/` for every leg pointing at it, and every
  fill points at a present loop. When two loops claim one offer across a
  merge, the resolver keeps one loop *whole* and removes the other
  *whole*. The per-key `min(loop_id)` rule is retired as policy; the
  post-merge invariant checker shipped first (2026-08-20:
  `verify_loop_atomicity`, run on every reconciled commit), as a stopgap
  that fails loudly.
- **The resolver algorithm is a registered open problem** (below): it
  must be deterministic, commutative, and stable as late information
  arrives; conflict chains make greedy-by-sorted-`loop_id`
  order-sensitive in exactly the way that matters.
- **Lineage**: each writer tracks the `base_root` it last folded, as
  `EagerOntoDAG` does; save-onto-moved-head is the CRDT merge, never
  last-writer-wins or locking (ontodag's 2026-08-04 decision).

Everything derived — `idx/`, `DimensionIndex`, `index_root` — is
re-derived after merge, never merged. Ontodag's descendant counts are the
cautionary tale: derived state conflicts on every concurrent write.

## 4. Announcements: GSOC first, registry events as the floor

A maker must be discoverable: "my book is (owner, topic)". **GSOC** is
the Swarm-native many-to-one channel — a key is mined (`gsocMine`,
default 16 matched prefix bits) so the single-owner-chunk address lands
in the aggregator's neighbourhood; any writer derives the same key and
posts; the aggregator subscribes (`gsocSubscribe`) and validates
announcements with the assert-function hook of Solar Punk's
`@solarpunkltd/gsoc`. Announcements use mutable batches (immutable ones
burn a slot per update). Two structural caveats: one mined address serves
one neighbourhood, so each aggregator needs its own mined id; and GSOC is
experimental with **no delivery guarantees**.

So the fallback is permanent: a minimal registry event on Gnosis Chain
(~5.15 s blocks, gas ~0.2 gwei in xDAI — sub-cent per registration).
Switchover is defined by measured loss, not sentiment: during burn-in
makers dual-publish and the aggregator measures GSOC delivery against the
registry-event ground truth. Chosen tripwires (ours, adjustable with
evidence): GSOC is promoted to primary when measured announcement loss
stays **< 1% over a 30-day window**; demoted — registry events mandatory
again — when rolling 7-day loss exceeds **5%** or any 24-hour outage
occurs. Announcements are idempotent and re-emittable, so measurement is
cheap. PSS stays out: best-effort, receiver-must-be-listening — at most
ephemeral solver gossip, never discovery.

**Upstream watch (noted 2026-08-07).** GSOC and Swarm pub/sub are under
active development (Viktor Trón and Viktor Tóth are working on both), so
the "experimental, no delivery guarantees" caveat above has a live path to
obsolescence. Track that work and feed our burn-in loss measurements back
as the consumer evidence it needs; a pub/sub primitive with delivery
semantics would also revisit the "PSS stays out" ruling for solver-facing
feeds. Channel: the Swarm ecosystem directly (Solar Punk maintains
`@solarpunkltd/gsoc`).

## 5. Lifecycle: withdrawal, expiry, compaction

Today an offer has no exit but expiry, and the book grows forever.
Withdrawal must survive a grow-only merge, and deletion cannot —
ontodag's 0.16.0 `--additions` rationale: "a removal is lossy … and
does not commute with a concurrent addition … a file whose effect depends
on when it is applied cannot be a fold." So withdrawal is an **add**: a
maker-signed monotone tombstone `withdraw/<offer_id>` in the maker's own
book (lands with P1). Tombstones merge as ordinary OR-set presence;
matching and settlement treat a tombstoned offer as closed, fail-closed
the moment the tombstone is visible at fold time. Re-adding the offer
does not un-withdraw it — a fresh intention is a fresh offer, fresh
nonce, fresh id.

Expiry is judged against anchored time, never wall clocks; until
anchoring exists (factbond `docs/plans/records-and-anchoring.md`), expiry
stays advisory outside settlement, which re-checks validity windows with
its own clock (U3 unchanged). Compaction is **re-publication under a new
root, never in-place deletion**: dropping keys does not merge, so a
compacted book is a new generation — a fresh topic (or generation counter
in the announcement), named in the manifest, folding forward only. The
hazard is the resurrection window: if a generation drops an offer *and
its tombstone*, a stale peer folding old state resurrects the offer
without its withdrawal. How long tombstones must outlive their offers is
a registered open problem.

## 6. Postage economics: TTL is the offer's real lifetime

When a batch's TTL hits zero the data is gone forever — silent, permanent
loss. "Offer validity window > stamp TTL" is therefore a bug class, and
P1 makes it unrepresentable: **publication refuses offers whose validity
window extends past the batch's TTL horizon** (with margin), and a **TTL
monitor** alarms well before expiry — recordstore's
`BeeBytesStore.batch_status()` already warns under one week of validity
and at ≥80%-full buckets; Swarm-CLI v3.2.0 surfaces expiration dates. Bee
has no auto-top-up (open issue ethersphere/bee#4992); the monitor is ours
to run.

The numbers are small: batch cost = 2^depth × amount, minimum depth 17
(131,072 chunk-slots, ≈512 MB theoretical); at the 24,000 PLUR/chunk/block
reference price a depth-17 batch for a year ≈ 2 xBZZ — with BZZ at
$0.04–0.19 (sources disagree 4×: CoinMarketCap $0.0432, CoinGecko
$0.049–0.156, Aug 2026), cents to well under $1 per maker-year. Feeds and
GSOC use **mutable batches** (immutable ones reject writes when any of
the 2^16 buckets fills; mutable overwrite oldest — right for a
continuously-updated head, wrong for archival blobs, which get their own
immutable batch). Two mechanisms fall out of the stamp design:

- **Permissionless top-up is a solver-ecology mechanism.** Anyone with
  BZZ can top up anyone's batch: a solver that profits from a maker's
  offers keeps that maker's book alive; an aggregator tops up stale
  batches it still values. Offers outliving negligent makers becomes an
  economic choice by whoever the offers feed — the first genuinely new
  economics P1 introduces, with no protocol change at all.
- **Provenance-driven stamping.** Asserted records (offers, tombstones,
  fills, loops) get durable stamps; derived state (`index_root`,
  summaries) gets short-TTL stamps — losing a derived index is a cache
  miss, not data loss (ontodag's provenance routing: asserted = durably
  stamped, derived = lazily recomputed).
- **Write-heavy legs, pre-registered tripwire.** No decided design puts a
  high-frequency stream (fill firehose, proposal flood) on Swarm — beats
  commit one root, proposals go sealed to settlement. If that changes, the
  sanctioned upstream pattern is ontodag's `SWARM_DESIGN_update` §4:
  POT-whirl as a write-ahead log on short-TTL stamps, compacting LSM-style
  into recordstore checkpoints — never a replacement for the canonical
  trie. File the consumer need upstream; do not improvise a hot path.

## 7. Swarm ops honesty

- **Feed CAS is best-effort.** `SwarmFeedPointer.compare_and_set` is not
  atomic — feeds have no index-claim primitive; two writers on one index
  can race. Consequence: **atomicity never rests on it**. Atomicity lives
  in recordstore commits (one root); convergence lives in CRDT merge; a
  raced pointer is repaired by the next fold, not prevented.
- **Discussion agenda #5, ratified by owner sign-off 2026-08-21: the
  shared Swarm book
  (ARCHITECTURE §5 shape 2) is demoted to a development/demo tool.** Its
  cross-process reconcile leans on exactly that best-effort CAS. This
  reframes the just-shipped P1 milestone: what the 2026-08-01 run proved
  — live end-to-end settlement, the follower witnessing atomic fills —
  survives; the deployment shape it used does not. Multi-writer
  production shape is per-maker books + fold, full stop.
- **The network is thin and concentrated.** January 2026 state of the
  network: 4,270 reachable full nodes (down from 4,760), 1,939 staking
  (down from 2,060), Finland 1,723 of 1,939 staking nodes; live swarmscan
  ~4,007 reachable, Germany 1,650 + Finland 1,081, ~14–25 nodes per
  neighbourhood against target redundancy 4. A hosting-provider outage is
  a correlated failure replication math ignores. Mitigation: **one
  self-hosted always-on full node pinning the book** — it doubles as the
  aggregator node, which must be full anyway (Bee 2.7 stopped evicting
  pinned chunks; before that even pinning wasn't airtight).
- **Erasure coding protects blobs, not feed heads.** Reed-Solomon per
  128-chunk group (`Swarm-Redundancy-Level`; Medium = 9 parities, 7.6%
  overhead, tolerates 1% chunk loss; theory arXiv 2409.01259; usable as
  of Bee 2.7+). Single-chunk objects — a feed's SOC head, one small
  record — get no parity; only ~4× neighbourhood replication guards them.
  The pinning node guards the heads; redundancy headers guard payloads.
- **A calendar experiment before trust** (Gates): publish a sacrificial
  book on a short-TTL batch and *watch it die* — when chunks actually
  vanish after expiry, whether pinned copies survive, how GC behaves.
  Postage-expiry/GC behaviour is documented but unmeasured by us;
  ontodag's live Bee runs left the same question open.

## 8. Spam floors (T2)

Publishing costs the maker real money: their own batch (the postage
floor) plus per-commit chunk writes. The design-time rule (shared with
`docs/plans/P2-batch-auction.md`): **no per-offer benefit may exceed the
per-offer cost floor**. In P1 the only benefits an unsettled offer earns
are attention and statistics, and statistics are defended by planned
invariant **U12**: "reward/reputation statistics count settled fee-paid
loops only" — fake offers earn nothing; unsettleable spam only pays rent.
Aggregator-side defense is **admission-by-reference**: an aggregator
folds books it chooses and un-merges a flooder (ontodag PROVENANCE's
stance); no store-side rate limiting to game. Economic spam pricing
beyond these floors arrives later as factbond's layer. Full attack
economics: `docs/plans/THREATS.md` T2 (sybil offer spam & statistics
pollution — primary here) and T8 (reputation gaming). Residual: the
announcement layer is floored only by sub-cent registry events and GSOC
mining — far below the storage floor; registered below.

## 9. Tests: the scorched-earth follower is the template

Ontodag 0.14.0–0.15.0 shipped a store that published a feed **nobody
could follow** — the follower path was never exercised from zero state
(fixed 2026-08-06 with `_bootstrap_root`/`_clone_from_swarm`, the clone
verified by canonical addressing: re-commit must reproduce the root).
`tests/test_swarm_book.py` already has the antidote: a follower built
from nothing but the feed address, no shared Python state, reading the
settled loop and all six fills back from the network. Rule (lands with
P1): **every multi-writer path ships with a scorched-earth follower
test** — follower of a maker book, of an aggregator manifest, after a
fold, after a compaction generation — each with a memory-backed variant
always green in CI (boundary B1) and a gated live variant under
`BEE_API`+`BEE_BATCH`+`BEE_SIGNER`.

## Gates

Unblockers: ~~the v2 record bump (U8 signature sidecar, fill `at` removal,
`from_record` version dispatch, pin fields)~~ and ~~recordstore floor
>=0.16.0~~ — both landed 2026-08-20; ~~owner sign-off on flagged decision
#5 (shared-book demotion)~~ — landed 2026-08-21. All unblockers are
cleared.

- **Convergence.** 3 makers, 2 aggregators folding in different orders,
  1 solver: byte-identical `book_root` on both aggregators; one loop
  settled. Memory-backed in CI; gated live on Bee.
- **Follower.** A scorched-earth follower reconstructs the settled loop
  and every fill from feed addresses alone; a second solver pass over the
  followed book settles nothing.
- **Withdrawal.** A tombstone propagates to a deliberately stale peer;
  post-fold the offer is unmatchable everywhere; the U11 checker passes
  on every fold of the run.
- **Fill determinism.** Two replicas settling the same loop produce
  byte-identical `fill/` and `loop/` records, hence equal roots.
- **Read latency.** From cold, a solver reads an aggregator manifest and
  snapshots a 1,000-offer book in ≤60 s on a light node, ≤5 s warm
  (targets ours, set against the measured 51 s triangle).
- **Durability.** The calendar experiment has run to batch death with
  observations recorded; the TTL monitor alarms ≥1 week before expiry; a
  third party demonstrably extends a batch it does not own.
- **Announcements.** Burn-in loss statistics collected against the
  registry-event ground truth; the <1%/30-day and 5%/7-day thresholds
  evaluated with data, not assumed.

## Open problems

- **The loop-granularity resolver** (this work package). U11 needs a
  deterministic, commutative rule that keeps loops whole under merge.
  Greedy over the conflict graph by sorted `loop_id` is order-independent
  only given the *full* conflict set; aggregators see conflicts
  incrementally, so a loop accepted at one fold could be evicted at the
  next — and evicting a settled loop is a finality rollback nobody can
  accept. Honest candidates: partition write authority so overlapping
  settlement cannot happen concurrently (one settlement writer per offer
  partition), or accept fold-stable-but-eventually-consistent settlement
  until P2's on-chain settlement serializes it. Neither is chosen here.
- **Resurrection windows** (this work package, with factbond
  records-and-anchoring). How long must tombstones outlive their offers
  before a compaction generation may drop them, when peer staleness has
  no bound? Anchored time gives a horizon to declare against; without it
  the crude bound is "maximum offer validity ever issued, plus margin".
  Needs a decided rule before the first compaction ships.
- **Aggregator economics** (adoption-and-thickness). A full Bee node with
  pinning is a real operational footprint. Who runs aggregators and why —
  solvers vertically integrating, a commons funded from settlement fees
  (`docs/plans/P2-batch-auction.md`), makers' cooperatives — decides
  whether neutrality-by-auditability holds when only one aggregator is
  worth reading. See `docs/plans/adoption-and-thickness.md`.
  **Owner directive (2026-08-21, given with the #5 sign-off):
  distributed, permissionless and censorship-proof is loopmarket's main
  value; several independent aggregators are the deployment floor — a
  single-aggregator steady state is a failure condition, not an
  acceptable optimum — and stronger decentralization of the read path
  (e.g., solvers folding maker feeds themselves by default, with
  manifests as disposable caches) is a mandated investigation before P1
  completes.** Registered as threat T14 (`docs/plans/THREATS.md`).
- **GSOC reliability** (this work package). No delivery guarantees, an
  experimental library, per-aggregator mined ids that grow announcement
  fan-out with aggregator count. The burn-in measures loss, not
  adversarial suppression; a neighbourhood censoring announcements is
  detectable only against registry events — which is why the fallback is
  permanent, not transitional.
- **The announcement-layer spam floor** (THREATS T2 residual). Sub-cent
  registry events and cheap GSOC mining make *discovery* spam orders of
  magnitude cheaper than *storage* spam. Assert-functions and
  admission-by-reference contain it operationally; a principled cost
  floor (stake, fees, proof-of-settled-history for announcement priority)
  is undesigned.

## What this document does not promise

Federation is not decentralized settlement: P1 settlement remains a
single trusted writer per instance, and what it certifies is
re-verification against pinned roots, never delivery of goods. There are
no proofs here — inclusion/absence proofs exist upstream (recordstore
0.16.0) but P1 verifiers still re-execute; `docs/plans/proof-fabric.md`
and P2 own that upgrade. There is no privacy: publication is plaintext,
permanently linkable, content-addressed — see `docs/plans/P4-privacy.md`
before assuming anything can be retracted from the world. Durability is
statistical, not guaranteed: a stamped, pinned, erasure-coded book on a
~4,000-node provider-concentrated network is a well-hedged bet, not a
custody arrangement. Spam defense is a cost floor, not a wall. And
byte-identical convergence is a claim about the fold, not the instant:
two aggregators agree on what both have seen, never on what exists.
