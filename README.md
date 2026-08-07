# loopmarket

[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)

A universal combinatorial marketplace over the
[ontodag](https://github.com/petfold/ontodag) /
[recordstore](https://github.com/petfold/recordstore) /
[Ethereum Swarm](https://www.ethswarm.org/) stack.

Every economic intention is one uniform, content-addressed **offer** — a
thing described as a conjunction of OntoDAG categories, with a service time
window and region, exchanged against the maker's **personal token**. A
distributed, versioned **offer book** holds them (recordstore keyspace;
Swarm-backed via `BeeBytesStore` + a signed `SwarmFeedPointer`). Competing
**solver agents** hunt profitable **loops** — cycles whose exchange-rate
product exceeds one, i.e. negative cycles under −log weights — and a
**settlement** layer re-verifies every leg from scratch and commits the
whole loop atomically.

```python
from recordstore import MemoryBytesStore, RecordStore
from loopmarket import (Ontology, OfferRegistry, MockSettlement,
                        SolverAgent, Thing, ask, bid, ...)

ontology = Ontology().load({"produce": [], "vegetable-box": ["produce"], ...})
registry = OfferRegistry(RecordStore(MemoryBytesStore()))
registry.publish_many([...])          # asks and bids, one uniform form
registry.commit()

agent = SolverAgent(registry, ontology, MockSettlement(registry, ontology))
agent.step()                          # snapshot → match → hunt loops → settle
```

## Try it

```bash
pip install -e ".[test]"              # (--break-system-packages or a venv)
python3 -m pytest tests/ -v           # 32 tests (one needs a live Bee node)
PYTHONPATH=src python3 examples/demo_triangle.py
```

The demo publishes the smallest nontrivial book — a piano teacher, a market
gardener and a bicycle mechanic, no pair of whom can trade — and watches the
solver find, verify and settle the triangle at a 12% surplus.

Candidate generation can also run through ontodag's **parametric
dimensions**: `DimensionIndex` files asks under their exact service window
and centre cell, and `candidate_matches_indexed` prunes by concept cones
and window overlap — provably the same matches as the exhaustive baseline
(the recall test enforces set-equality), with far fewer exact checks. The
index is a derived, per-solver copy; the shared catalogue and its pinned
roots never move because of it. Swap the in-memory store for
`recordstore.swarm_store("offers", signer=...)` (extra:
`pip install -e ".[swarm]"`, plus a Bee node and a postage batch) and the
same code runs with the book on Swarm.

## What is built, and what is designed

**Built (P0, plus the live-Swarm milestone):** the full pipeline above runs
in memory, and since 2026-08-01 also end-to-end on a real Gnosis-mainnet
Bee node — catalogue and book on Swarm, book head in a signed feed, fills
atomic (the gated `tests/test_swarm_book.py`). Alpha; interfaces will move.

**Designed (2026-08-07):** most of what loopmarket *is* now lives as a
decided, research-grounded plan corpus under `docs/plans/` — one document
per work package, each with measurable gates, named open problems, and a
closing "what this document does not promise" section. Anything implying
unbuilt code carries a dated marker ("decided 2026-08, lands with the v2
bump / P1 / P2"). Planned invariants **U8–U14** are specified in the
documents that motivate them and summarized across `ARCHITECTURE.md`'s
update notes and §11; they enter `CLAUDE.md` as binding invariants only
when their enforcing code and tests land. factbond's mirror corpus is
`factbond/docs/plans/`.

## The plan corpus

| Document | One line |
|---|---|
| [`P1-federated-book.md`](docs/plans/P1-federated-book.md) | Per-maker books under own feeds/signers; announcement, aggregation, merge discipline, lifecycle, postage economics, spam floors. |
| [`P2-batch-auction.md`](docs/plans/P2-batch-auction.md) | The beat: sealed proposals, numeraire-free scoring, the fairness floor, capped solver rewards, collusion resistance, fees. |
| [`P2-settlement-pricing.md`](docs/plans/P2-settlement-pricing.md) | Turning a winning loop's surplus into per-leg prices: equal log-surplus split under uniform directional clearing. |
| [`P2-loop-selection.md`](docs/plans/P2-loop-selection.md) | Clearing as optimization: flow LP vs packing ILP, chains, failure-aware objective, pre-commit compression. |
| [`proof-fabric.md`](docs/plans/proof-fabric.md) | Cross-phase proofs and certificates: trie proofs vs POT, the pin table, certificate envelopes, absence proofs. |
| [`P3-guarantee-coupling.md`](docs/plans/P3-guarantee-coupling.md) | loopmarket's half of the factbond coupling: witness edges, reliance-capped insurance, oracle consumption, risk-priced routing. |
| [`P4-privacy.md`](docs/plans/P4-privacy.md) | Staged privacy: Tier 1 with zero new cryptography, the P2 format-freeze list, explicit dead/deferred rulings. |
| [`ontodag-coupling.md`](docs/plans/ontodag-coupling.md) | The catalogue contract: dimension terms, unit families, match degrees, the upstream-vs-local tripwire table. |
| [`catalogue-bootstrap.md`](docs/plans/catalogue-bootstrap.md) | Seeding and governing the shared catalogue: seed taxonomies, the import pipeline, norms as protocol rules. |
| [`adoption-and-thickness.md`](docs/plans/adoption-and-thickness.md) | Where the first loops come from: launch verticals, the broker surface, bridge liquidity, thickness engineering. |
| [`THREATS.md`](docs/plans/THREATS.md) | The threat register, T1–T9, ordered by expected damage to a young system; mirrored in factbond. |

**Phase ↔ document map.** P1 (federation): `P1-federated-book.md`,
supported by `ontodag-coupling.md` and `catalogue-bootstrap.md`. P2
(verifiable settlement): the three P2 docs plus `proof-fabric.md`,
*constrained* by `P4-privacy.md`'s format-freeze list and gated by
`THREATS.md` tripwires. P3 (guarantee fabric): `P3-guarantee-coupling.md`
plus factbond's entire corpus — gated by factbond's Phase-0 simulation
going green *and* the P2 format freeze. P4 (privacy): `P4-privacy.md`,
whose Tier 1 may ship alongside P2. Cross-phase: `proof-fabric.md`,
`THREATS.md`, `adoption-and-thickness.md`, `catalogue-bootstrap.md`,
`ontodag-coupling.md`.

**Reading order.** First pass: `ARCHITECTURE.md` → `THREATS.md` →
`P1-federated-book.md`. Settlement track: `P2-loop-selection.md` →
`P2-settlement-pricing.md` → `P2-batch-auction.md` → `proof-fabric.md`.
Guarantee track: factbond `DESIGN.md` → `mechanism-design.md` →
`insurance-products.md` → `phase0-simulation.md` →
`P3-guarantee-coupling.md`. Market track: `adoption-and-thickness.md` →
`catalogue-bootstrap.md` → `ontodag-coupling.md`.

Order of documents is not order of construction — gates decide that; and a
document's existence proves nothing about feasibility. The Phase-0
simulation and the named empirical gates can kill designs recorded here;
the corpus is built so that they can.

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — the design and its rationale:
  the uniform offer form, time/place as fits-within dimensions, the book's
  keyspace and multi-writer story, the loop arithmetic (and why prices are
  never negative), the trust model, the proof fabric, economic security,
  and what the architecture does not promise.
- **[CLAUDE.md](CLAUDE.md)** — working rules for development: dependency
  boundaries, core invariants U1–U7, known simplifications, roadmap phases
  P0 (built) → P1 (federated book) → P2 (verifiable settlement, batch
  auctions) → P3 (guarantee fabric via factbond) → P4 (privacy).
- **[docs/loop-economy.md](docs/loop-economy.md)** — the vision essay: the
  loop economy, its gallery of loops, the solver ecology, judges without
  swords, and the path in.
