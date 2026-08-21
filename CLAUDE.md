# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`loopmarket` is a **universal combinatorial marketplace**: every economic intention is one uniform, content-addressed **offer** (a thing described as a conjunction of OntoDAG categories, a service time window, a service region, a validity window — priced on the maker's **personal scale**, a pure-bookkeeping numeraire that the record encoding calls the maker's personal token: nothing is ever held or transferred, the numbers cancel in-loop); a distributed **offer book** holds them as a versioned recordstore keyspace (Swarm-backed in deployment); competing **solver agents** hunt profitable **loops** (cycles whose exchange-rate product exceeds 1 ⇔ negative cycles under −log weights); a **settlement** layer re-verifies every proposed loop from scratch and commits all its legs atomically. The full design rationale — including the parts deliberately not built yet — is in `ARCHITECTURE.md`. Read it before structural changes. The forward design corpus (P1–P4 work packages, threat register, catalogue bootstrap, factbond coupling) lives under `docs/plans/` — indexed on the front page, `README.md` (doc table, phase↔doc map, reading order); planned invariants U8–U14 are specified there and enter this file only when their enforcing code and tests land (U11 entered 2026-08-20).

The conceptual background is the "Loop Economy" essay (offers, loops, bridges, bonds, nano-bets, solver ecology). This repo is phase P0 of that programme: the in-memory/prototype track that must stay runnable end-to-end at all times.

## The stack and its direction

```
loopmarket  →  ontodag (>=0.13.0)  →  recordstore (>=0.16.0)  →  Swarm (optional)
```

- **ontodag** (github.com/petfold/ontodag): the shared catalogue. One query primitive — intersection of descendant cones. `Ontology` in `src/loopmarket/ontology.py` is a thin matching-oriented facade (`covers`, `satisfies`) and the place where pinned catalogue roots surface. Identity at ontodag's public boundary is the *name* (plain strings accepted anywhere an `Item` is).
- **recordstore** (github.com/petfold/recordstore): the book's kernel. Canonical roots (equal content ⇒ equal reference), snapshot isolation via `RecordStore.at(root, blobs)` (note: the blob-store attribute is **`.blobs`**), three-way `merge`, `commit(reconcile=True, resolver=...)` for multi-writer convergence. The interface summary lives in ontodag's `docs/recordstore-interface.md`; treat it as the API reference.
- **Swarm**: reached only through recordstore (`BeeBytesStore` + `SwarmFeedPointer`, assembled by `swarm_store(topic, signer=/owner=)`). `registry.swarm_offer_book()` and `Ontology.persistent()` are the only places that name it.

## Dependency boundaries (tests/test_boundaries.py — must always pass)

- **B1 The core works offline.** `import loopmarket` and the whole model (schema, ontology, matching, graph, solver, mock settlement) must function with no network, no Bee node, and no optional dependency. Swarm is a persistence backend chosen at the edges, never a requirement of the model.
- **B2 One-directional dependencies.** loopmarket imports ontodag and recordstore; never the reverse, and never `requests`/`swarm_bee` at module import time (they load lazily inside the Swarm call paths, as in recordstore itself).

## Core invariants (do not weaken; add tests when touching them)

- **U1 Uniform offer form.** Exactly one side of every `Offer` is a `Thing`, exactly one is `Tokens`, and the token issuer **is** the maker. Enforced in `Offer.__post_init__`; the whole loop arithmetic depends on it.
- **U2 Offers are immutable, canonical values.** `canonical_bytes()` is deterministic (concept tuples sorted, recordstore's canonical JSON); `offer_id` = SHA-256 of it. Never add a field without bumping the record's `"v"` and keeping `from_record` reading old records. Enforced since 2026-08-20: `from_record` dispatches on `"v"` and *raises* on unknown versions, and `to_record` re-encodes each offer in its native version, so old records keep their ids.
- **U3 Settlement trusts no solver.** `MockSettlement.submit` asserts the proposal's ontology pin equals its own (step 0 — U10's rehearsal), re-derives every leg with `check_match` against the *current* book and its own ontology, re-checks chaining/product/fills, and only then commits — all fills under one root (atomicity = one recordstore commit). Any future settlement backend keeps this shape.
- **U4 Solve against pinned roots.** Solvers work on `registry.snapshot()` (a frozen `RecordStore.at`) and pin `ontology_root`/`book_root` in proposals. Reproducibility and auditability beat freshness.
- **U5 Positive rates only.** The loop math is products of positive ratios / sums of logs. There are no negative prices anywhere: disposal is a positively-priced service, emptiness a positively-priced good (see ARCHITECTURE.md §7). Reject any change that introduces signed prices into `Match.rate`.
- **U6 Determinism in the baseline solver.** `ExchangeGraph.find_profitable_loop` iterates nodes/edges in sorted order; the same book must yield the same loop on every replica. Smarter solvers may be stochastic; the baseline may not.
- **U7 Vocabulary fails closed.** Unknown categories never match (`Ontology.satisfies` is strict). Silent drift must break loudly.
- **U11 No partially-filled loop survives a merge unnoticed.** (Entered 2026-08-20; the id is fixed by the plan corpus, hence the gap after U7.) Post-merge, every `loop/` record holds a `fill/` for each of its legs and every fill points at a present loop; `verify_loop_atomicity` checks this on every reconciled commit and raises `PartialLoopError`. Checked, not resolved — evicting a settled loop would be a finality rollback; the deterministic loop-granularity resolver is a registered open problem (`docs/plans/P1-federated-book.md` §3).

## Running tests

```bash
python3 -m pytest tests/ -v            # everything (conftest.py puts src/ on the path)
python3 -m pytest tests/test_boundaries.py -v   # B1/B2 — must always pass
PYTHONPATH=src python3 examples/demo_triangle.py  # end-to-end smoke: must find & settle 1 loop
```

Installing deps: this environment's Python may be PEP-668 externally managed — use `pip install --break-system-packages` (or a venv). `pip install -e ".[test]"` for development; add `.[swarm]` only when running against a Bee node.

Live-node runs follow ontodag's convention: skip unless `BEE_API` **and** `BEE_BATCH` are set, and always pass a real purchased batch id so nothing auto-buys. The Swarm-book test additionally needs `BEE_SIGNER` (a throwaway key: it writes feeds under timestamped topics so reruns don't inherit an old book).

## Architecture map (one line per module)

- `src/loopmarket/schema.py` — the offer form: `TimeWindow`, `GeoDisc`, `Thing`, `Tokens`, `Offer` (+ `ask`/`bid` helpers), canonical encoding, content-addressed ids.
- `src/loopmarket/spacetime.py` — geohash cells and day buckets: containment chains (prefix = fits-within) used as index names; never a correctness dependency.
- `src/loopmarket/ontology.py` — the catalogue facade: `assert_edge`/`load` to build, `covers`/`satisfies` to query, `persistent()`/`commit()` for pinned roots via `EagerOntoDAG`.
- `src/loopmarket/registry.py` — the book: `offer/`, `sig/`, `withdraw/`, `fill/`, `loop/` keyspace over a duck-typed RecordStore (`idx/{c,t,g}` is aggregator-derived via `index_offers` — maker books never write it); `snapshot()`, `withdraw()` tombstones, `or_set_resolver` for multi-writer merges, `verify_loop_atomicity` (U11), `swarm_offer_book()`.
- `src/loopmarket/federation.py` — the federated book: `Aggregator` folds announced per-maker and settlement books under the U8 admission rules (rejections as attributed provenance, U11 per fold) into the four-root `Manifest` {book, provenance, index, announcement}.
- `src/loopmarket/sigs.py` — detached maker signatures (U8's off-feed layer): sign/recover over offer ids, eth-keys loaded lazily behind the `sig` extra.
- `src/loopmarket/matching.py` — the exact pairwise check (`check_match`) and the O(asks×bids) baseline candidate generator.
- `src/loopmarket/graph.py` — `ExchangeGraph` (best rate per pair), Bellman–Ford negative cycles, `Loop` (product, surplus, per-node check, `loop_id`).
- `src/loopmarket/settlement.py` — `LoopProposal`, `Receipt`, the `Settlement` protocol, `MockSettlement` (injectable `clock` for deterministic tests).
- `src/loopmarket/solver/agent.py` — the baseline `SolverAgent`: snapshot → match → graph → hunt → propose; the species other solvers must beat.

## Known simplifications (deliberate; each has a roadmap home)

1. **Divisibility caveat.** The product condition (Π rates > 1) prices out exactly only when quantities can scale so per-node token balances cancel. Indivisible legs get the conservative `per_node_ok` gate in settlement. Proper settlement pricing (choosing actual prices between each ask and bid, distributing surplus) is P2 — now specified: equal log-surplus split under uniform directional clearing (`docs/plans/P2-settlement-pricing.md`); the divisible/indivisible line is the LP/ILP complexity boundary (`docs/plans/P2-loop-selection.md`).
2. **Candidate generation is O(asks×bids) by default.** Correct and fine in memory. **The dimension-backed generator landed 2026-07-30** (`src/loopmarket/dimensions.py`, needs ontodag>=0.4.0): `DimensionIndex` + `candidate_matches_indexed` prune by concept cones and exact window overlap, recall-exact vs the baseline (tests/test_dimensions.py); the index is a derived deepcopy of the catalogue — never file offers into the shared catalogue, that would churn pinned roots. Geo stays with the exact check (sibling cells share no prefix — a cell filter loses recall). The baseline remains the default in `SolverAgent` and the recall benchmark; wire the indexed generator into the solver when book sizes ask for it.
3. **Geo cells index disc centres only.** Boundary-crossing discs touch neighbour cells; that's why cells are hints and `GeoDisc.intersects` is the truth. Neighbour-cell fan-out or S2 coverings: P1, only if profiling says so.
4. **Single shared book in the demo.** The decentralized shape is one book per maker (own feed, own signer), aggregated with `RecordStore.merge` under `or_set_resolver`. The key layout is already identical; the aggregator loop is P1 — now specified end-to-end (announcement channel, aggregator manifest, merge discipline incl. the fill-determinism and loop-granularity fixes, tombstones, postage economics) in `docs/plans/P1-federated-book.md`. Note the 2026-08-07 demotion: the *shared* Swarm book (one feed, many writers) is a dev/demo tool only — feed CAS is best-effort, so one-signer-per-feed is the safety model.
5. **`bond`, `oracle`, `arbitrator` are carried, not enforced.** They are in the canonical encoding from day one so ids don't churn when P3 lands (bond escrow, oracle adapters, arbitration hooks, bonded ontology assertions — `Ontology.assert_edge` already takes `bond=`). **The P3 mechanism design now has a dedicated sister repo (2026-08-01): factbond** (github.com/petfold/factbond — bonded assertions/optimistic adjudication, odds-weighted bonds, shared bond pool, information insurance). Adopt, don't redesign: the loopmarket coupling (settlement-attached insurance on the ⊑ edges a loop relied on; per-edge loss experience as the catalogue reliability audit; certificates settling the structural half of disputes) is worked out in factbond's `docs/INTEGRATION.md` §8 and ARCHITECTURE.md §4's update note here.
6. **Batch auctions absent.** MockSettlement is first-valid-wins. The P2 beat is now specified (sealed proposals, numeraire-free scoring, fairness floor, capped marginal-contribution rewards, baseline as reserve bid) in `docs/plans/P2-batch-auction.md`.
7. **No privacy layer.** Offers are plaintext. Coarse-first disclosure, commitments, ZK fits-within proofs: P4 — now staged in `docs/plans/P4-privacy.md`; its Tier 1 needs no new cryptography, and its format-freeze list constrains P2 record formats. Do not add ad-hoc encryption before that design lands.

## Roadmap phases

- **P0 (this repo, done)** — in-memory prototype: uniform schema, book over recordstore, exact matching, negative-cycle solver, trust-nothing mock settlement, triangle demo green.
- **P1 Swarm book** — ~~run the demo against a Bee node (`swarm_offer_book`)~~ **done 2026-08-01**, permanent as the gated `tests/test_swarm_book.py` (needs `BEE_API`+`BEE_BATCH`+`BEE_SIGNER`): catalogue on Swarm, offers pinning its root end-to-end, book head in a signed feed, triangle solved and settled in ~51s on a Gnosis-mainnet light node, a scorched-earth follower reading the settled loop and all six atomic fills back from the network, second pass empty. The v2 record bump and its gates landed 2026-08-20 — version dispatch, widened pins with the `''`-gate closed, fill determinism, leg-paired loop ids, U8 sidecar primitives, the U11 stopgap checker; the P1 plan's code unblockers are cleared. The in-memory federation landed 2026-08-21: withdrawal tombstones, per-maker books folded by `Aggregator` under the U8 admission rules, the four-root manifest (incl. `announcement_root`), `idx/` demoted to aggregator-derived state, and memory-backed variants of the convergence/follower/withdrawal gates. Still open in P1: the live-Swarm variants (per-maker feeds, GSOC/registry announcements, read-latency + durability gates); spacetime as ontodag parametric dimension terms in the *shared* catalogue (the derived DimensionIndex landed 2026-07-30 — see ARCHITECTURE.md §3); the read-path decentralization investigation (T14, mandated pre-P1-completion).
- **P2 Verifiable settlement** — a Gnosis Chain contract verifies offer inclusion/absence under the pinned book root via recordstore's shipped canonical-trie proofs (`prove`/`verify_proof`, ≥ 0.16.0); POT ForkPathProof is the conditional fallback only if the on-chain verifier demands BMT-native proofs (decision rule in `docs/plans/proof-fabric.md`); batch auctions over competing sealed proposals (`docs/plans/P2-batch-auction.md`); real settlement pricing (`docs/plans/P2-settlement-pricing.md`); loop selection as flow-LP/packing-ILP (`docs/plans/P2-loop-selection.md`).
- **P3 Guarantee fabric** — bond escrow and slashing, oracle adapters (countersign, locker, photo, digital proof), arbitrator hooks, bonded ontology assertions, aggregated risk markets feeding rate premia. Design home since 2026-08-01: the **factbond** sister repo (see Known simplifications #5).
- **P4 Privacy** — staged disclosure, committed offers, ZK fits-within/range proofs, private matching experiments.
- **Later (post-P4) — price schedules in offers** (owner-added 2026-08-21): the offer's single price generalizes to a static, immutable schedule over quantity (supply/demand curves) and/or validity time (a pre-committed Dutch/English ladder in one offer — no oversell, unlike a ladder of short-validity offers). Divisible-leg clearing stays a polynomial flow-LP under piecewise-linear convex costs; details and the standing rejections (continuous in-protocol price dynamics: speed races, U4/U6) in `docs/plans/P2-loop-selection.md` open problems. Until then, dynamic pricing quantizes to the beat: tombstone + repost.

## Conventions

- `src/` layout; tests via pytest from the repo root (conftest handles the path).
- Names are identity at public boundaries (strings accepted where objects are), matching ontodag.
- Docstrings explain *why* (the design decision), comments explain *why not* (the rejected alternative). Keep both current when changing behaviour.
- One invariant, one commit — mirror ontodag's fix history style.
