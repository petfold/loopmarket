# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

Started 2026-09-11. Nothing has been released yet: `pyproject` says 0.1.0 and
the distribution builds cleanly, but the name is **not yet on PyPI** — the
upload has been blocked since 2026-09-10 by PyPI's `429 Too many new projects
created` limiter. There are no release tags either.

## [Unreleased] — 0.1.0 pending

A universal combinatorial marketplace: uniform offers over an OntoDAG
catalogue, a versioned offer book on recordstore/Swarm, and solver agents
hunting profitable loops.

### The model, as settled so far

- **The primitive is a circulation; the loop is its smallest case.** `loop`
  keeps its name and widens its meaning, with `cycle` reserved for where the
  reasoning goes round — settled by two vocabulary audits.
- **Composition: one want, many gives** — the buyer pays once.
- **Clearing is not settlement.** The commit fixes obligations; delivery
  settles them. Cleared loops count; delivery never adds credit (U12).
  `settlement` was renamed to `clearing` throughout, and
  `P2-settlement-pricing` became `P2-clearing-pricing`.
- **Who commits is not the solver.** Smarter solver species live outside this
  repo; the public repo names no particular solver.
- **Hyper-legs and hypergraphs**: the pallet as one hyper-leg, with the
  hypergraph defined where hyper-legs are used.

### Added

- **One intersection engine** — no set arithmetic in loopmarket itself, and
  `idx/` retires.
- Candidate generation issues one query rather than three.
- Plans: one clearing commit per beat, and publication of the anchored root.
- A live federation demo recorded on Bee, with commits retrying transient 5xx.

### Open before v3

- The integer granularity of a give in loop selection is a decision still
  outstanding.
