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

## 2. The uniform offer (schema.py)

Every offer exchanges a **Thing** (conjunction of catalogue categories +
quantity + service `TimeWindow` + service `GeoDisc` + validity window)
against **Tokens** of the maker's personal numéraire. Exactly one side is the
maker's own token — enforced in the constructor, not documented as a
convention. This uniformity is what makes the entire marketplace one data
structure: transport, storage, aggregation, compute and cabbages differ only
in their category sets.

Personal tokens are bookkeeping: a maker's several offers relate through
ratios in their own unit, so k asks and m bids cost k+m offers, not k×m
pairings. Tokens exist only long enough for a loop to pass through the maker
and cancel; liquidity is supplied by offers whose Thing is itself a currency
(bridge offers), not by the tokens.

Offers are immutable values with a canonical encoding (recordstore's
canonical JSON; concept tuples sorted) and a content address
(`offer_id = SHA-256(canonical_bytes)`). The Swarm reference a blob store
assigns is a storage detail; the logical id is the application-layer key.
`bond`, `oracle`, `arbitrator` ride in the encoding from day one (identity
stability for P3) but are not yet enforced.

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

**Update 2026-07-30 — ontodag dimension lattices.** ontodag's
parametric-items design is agreed (`ontodag/docs/DIMENSIONS.md`) and
**shipped the same day as ontodag 0.4.0 on PyPI** — including
`get_overlapping`, the possibly-satisfies query op the time/geo gates
want, and `LazyOntoDAG` support. It changes the P1 shape of this section:
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
vocabulary fails closed.

Persistence goes through `EagerOntoDAG` over a duck-typed RecordStore;
`commit()` yields a canonical root. Offers pin the root they were written
against, matching refuses to pair offers pinned to different roots, and
proposals carry the root they were checked under: the semantic ground cannot
move beneath a committed loop, and "which catalogue said the cello fits the
crate" is answerable forever. Bonded assertions (stakes on ⊑ edges, scaled to
centrality) are P3; `assert_edge(sub, supers, bond=)` already carries the
argument.

## 5. The book (registry.py)

One book = one recordstore keyspace = one root reference per version:

```
offer/<offer_id>                the immutable offer record
fill/<offer_id>                 {"loop": <loop_id>, "at": t}
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

Postage-stamp economics (who pays for an offer's chunks, for how long — the
validity window has a natural counterpart in stamp TTL) is deliberately not
modelled yet; it belongs with P1's live-node work.

## 6. Matching (matching.py)

`check_match(ask, bid, ontology, now)` is the exact, self-contained pairwise
truth: kinds and distinct makers; both validity windows open; service windows
overlap (a delivery instant exists); service discs intersect (a handover
point exists); quantity within capacity (equality unless divisible); same
unit; agreeing ontology pins; and `satisfies` under the catalogue. Its
self-containedness is a design requirement, not tidiness: settlement re-runs
it, so no index, cache or heuristic may be load-bearing for correctness.

The baseline candidate generator is the full ask×bid product with the
constant-time gates doing the pruning — right for in-memory books, and the
benchmark smarter generators must not fall behind on recall.

## 7. The arithmetic of loops (graph.py)

Nodes are personal tokens; a `Match` is an edge giver→receiver with rate
`r = bid.unit_price / ask.unit_price`. Around a cycle the product telescopes
into Π(node's bid price / node's ask price): **product > 1** means positive
surplus. With divisible quantities this is exact — quantities can scale so
each node's token inflow and outflow cancel, and the slack is genuinely
distributable surplus. With indivisible unit legs, exact cancellation needs
the conservative **per-node condition** (each node's bid ≥ its own ask),
which `Loop.per_node_ok` reports and settlement enforces for non-divisible
loops. Real settlement pricing — choosing actual prices inside each
[ask, bid] interval and distributing the surplus — is P2.

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
the pinned book root. This is precisely what the Proximity Order Trie
provides — `ForkPathProof` (BMT proofs over Swarm chunks) verified on-chain
by `POTProofVerifier` (`ethersphere/proximity-order-trie`) — and is the main
reason the book's index should converge with the POT track planned in
recordstore: the same structure then serves queries off-chain and proofs
on-chain. Batch auctions (collect proposals per beat, rank by participant
surplus, rebate it — the anti-sniping design) are P2 alongside.

## 9. The solver agent (solver/agent.py)

`step()`: snapshot → load active offers → exact matches → best-rate graph →
negative cycles → proposals. Deliberately trust-poor in both directions:
solves only against pinned roots (reproducible), and produces nothing that
is believed (settlement re-derives). `run()` polls a live book. Multiple
agents against one book are safe by construction: first valid proposal
wins, the rest are rejected on the `fill/` check.

## 10. What is deliberately absent

Bonds/oracles/arbitrators (carried, unenforced — P3), aggregated risk
markets and rate premia (P3), batch auctions and settlement pricing (P2),
privacy — staged disclosure, committed offers, ZK fits-within proofs (P4),
bridges to legacy inventory (thin adapters that publish ASK/BID pairs plus a
currency leg; they are ordinary makers and need no new mechanism, so they
live outside this repo), and postage-stamp economics (P1). Each absence is a
scheduled decision, not an oversight; see CLAUDE.md "Known simplifications".
