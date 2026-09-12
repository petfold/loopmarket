# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

Started 2026-09-11. Releases are tag-driven (`v*` tags run
`.github/workflows/publish.yml`, PyPI trusted publishing).

## [Unreleased]

### Added

- **Service roles in the catalogue** (`docs/plans/P1-spacetime-terms.md`,
  decided with Peter 2026-09-12): `Ontology.satisfies` now walks one
  conjunction with two relations — containment for what a thing is,
  overlap for where and when it changes hands — and the *head* decides
  which, declared in the catalogue under the marker node `service-role`
  (`Ontology.declare_service_roles()`: `when` under `time`, `where`/`from`/
  `to` under `geo`). A give from anywhere in `u2e` now serves a want at
  `u2e4x` and vice versa; `made_in(u2e4x)` still only satisfies
  `made_in(u2e)` one way. Absent role = unconstrained; same-head terms are
  their meet; an uninterpretable role term fails closed on either side.
  No record change: the `service`/`where` field gates still run beside it,
  and a catalogue that declares no roles behaves exactly as before. The
  fields leave at the v3 bump, the package's step 5.
- **Drafts and composed wants at the command line** (`docs/plans/cli.md`
  §13, `P2-loop-selection.md` §10 "Declared parts", decided with Peter
  2026-09-12): a theatre ticket with transport is one want with two parts,
  cleared together or not at all. `draft [NAME] want|give ...` stages a
  resolved offer or part (a price optional; a local file, never the book),
  `draft [NAME] A + B` composes drafts with the same `+` the one-line want
  uses, `drafts` lists them in canonical spelling with the typed spelling
  as notes, `offer NAME [PRICE]` turns a draft into an offer, `discard`
  drops them; `want PART + PART ... PRICE` is the one-line form. Simple
  drafts publish today; a composed want renders its full block and then
  **refuses** until the v3 record lets `wants` carry parts. Composition is
  want-side only: the give side gets a minimum fill (the chartered bus,
  the cow), never parts.
- **`clearing`** is the clearing-house command; `clear` (delete, on every
  terminal) stays a silent alias for one release.
- **The offer line as Python's literal**: `cli.offer_from_line` and
  `cli.line_for` round-trip an `Offer` and its canonical line.
- `where(LAT,LON,R)` as a literal place, the spelling `place` takes, so a
  canonical draft line re-parses to the same disc.
- Live-checked on a Bee 2.8.2 light node after the changes: both gated
  Swarm suites pass (5m38s), and the triangle script on a Swarm feed
  clears in 58s to the same `loop_id` and book root as before.

### Fixed

- A place name in a role term now takes its *most specific* cell: a place
  hangs under its own cell and, by computed containment, under every
  coarser one, and the first ancestor in set order was sometimes the
  coarse one.

## [0.2.0] — 2026-09-12

### Added

- **The command line, `loop`** (`src/loopmarket/cli.py`, `python -m
  loopmarket`; design record `docs/plans/cli.md`). Ontodag's grammar plus
  two conventions — a bare number first is the quantity, last is the price
  — every name a catalogue node (places via `loop place NAME LAT,LON,R`, a
  dated bridge), an omitted price the maker's last unit price for the same
  thing, the fully resolved offer shown and approved before anything is
  published, and `show ID` printing that same block later. Commands for
  the maker (`give`, `want`, `withdraw`, `mine`, `place`), the reader
  (`offers`, `show`, `matches`, `status`), the solver (`loops`) and the
  clearing house (`clear`), plus `set`, `export`, `import`. Settings share
  odag's format and precedence rule and inherit its Bee configuration; a
  bare `loop` at a terminal is a prompt, a pipe is a batch. Live-checked
  with the book on a Swarm feed the same day.
- **Role terms match.** `Ontology.known` accepts a parametric term of a
  declared dimension head (it asks the DAG to order the term against
  itself), so `from(u24m)` in an offer fits within `from(u2)` by ontodag's
  computed containment. At the command line a catalogue *name* in a term's
  parameter takes its public value (`from(home)` → `from(u24m)`), printed
  as a note; the published offer holds public vocabulary only.
- `examples/triangle.loop` + `examples/triangle.od`: the triangle demo as
  a fifteen-line script; `tests/test_cli.py` (gates G1–G6 and the rules
  around them).

### Changed

- The user guide is a command-line tutorial with the API alongside; the
  README leads with `loop`; the reference manual gains §17 (grammar,
  commands, settings) and the `LOOP_*` environment.
- Dependency floor: `ontodag>=0.23.0` (the CLI uses its store backends,
  prelude and surface layer).

### Rulings recorded (Peter, 2026-09-12)

- The binary is `loop`; `loopmarket` is the long alias.
- In a batch under `confirm auto`, a line whose price was *reused* refuses
  rather than publishing a number nobody saw.
- Ontodag interprets the *name* in `from(my_home)`; the CLI carries its
  value into the term.

### Known

- Quantity and time terms (`weight(...)`, `time(...)`) are accepted by the
  grammar and refused at publish until quantities and spacetime become
  catalogue terms (`ontodag-coupling.md` §2–3). `peers` is a trusted
  union; U8 admission arrives with the `fold` command. The schema has no
  numeric normalization (`1` ≠ `1.0` as records) — the CLI keeps the typed
  form; the fix is D9's in the v3 bump.

## [0.1.0] — 2026-09-11

First release on PyPI (the tag workflow succeeded on its third run, after
the `[sig]` extra gained its hashing backend).

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
