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
python3 -m pytest tests/ -v           # 25 tests
PYTHONPATH=src python3 examples/demo_triangle.py
```

The demo publishes the smallest nontrivial book — a piano teacher, a market
gardener and a bicycle mechanic, no pair of whom can trade — and watches the
solver find, verify and settle the triangle at a 12% surplus.

Candidate generation can also run through ontodag's **parametric
dimensions** (ontodag ≥ 0.4.0): `DimensionIndex` files asks under their
exact service window and centre cell, and `candidate_matches_indexed`
prunes by concept cones and window overlap — provably the same matches as
the exhaustive baseline (the recall test enforces set-equality), with far
fewer exact checks. The index is a derived, per-solver copy; the shared
catalogue and its pinned roots never move because of it. Swap the
in-memory store for `recordstore.swarm_store("offers", signer=...)`
(extra: `pip install -e ".[swarm]"`, plus a Bee node and a postage batch)
and the same code runs with the book on Swarm.

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — the design and its rationale:
  the uniform offer form, time/place as fits-within dimensions, the book's
  keyspace and multi-writer story, the loop arithmetic (and why prices are
  never negative), the trust model, and the Swarm/POT settlement path.
- **[CLAUDE.md](CLAUDE.md)** — working rules for development: dependency
  boundaries, core invariants, known simplifications, roadmap phases
  P0 (this repo) → P1 (Swarm book) → P2 (verifiable settlement, batch
  auctions) → P3 (bonds, oracles, arbitration) → P4 (privacy).

## Status

P0 — a runnable in-memory prototype of the full pipeline, with the Swarm
deployment path wired through recordstore but not yet exercised against a
live node. Alpha; interfaces will move.
