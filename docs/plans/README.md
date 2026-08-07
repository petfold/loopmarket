# loopmarket — design plans

Status: index, 2026-08-07. This directory holds the forward design corpus:
what each roadmap phase will build, decided before it is built. Every
document here follows the same discipline — decisions with rationale and
rejected alternatives, measurable gates, named open problems, and a closing
"what this document does not promise" section. `ARCHITECTURE.md` remains
the record of what *is*; these documents record what is *decided*.
factbond's mirror corpus is `factbond/docs/plans/`.

**Marking convention.** Anything in these documents (or in
`ARCHITECTURE.md` update notes) that implies unbuilt code carries a dated
marker — "(decided 2026-08, lands with the v2 bump / P1 / P2)". Planned
invariants **U8–U14** are specified in the documents that motivate them and
summarized across `ARCHITECTURE.md`'s update notes (§2, §5, §7) and §11;
they enter `CLAUDE.md` as binding invariants only when their enforcing
code and tests land.

## The documents

| Document | One line |
|---|---|
| `P1-federated-book.md` | Per-maker books under own feeds/signers; announcement, aggregation, merge discipline, lifecycle, postage economics, spam floors. |
| `P2-batch-auction.md` | The beat: sealed proposals, numeraire-free scoring, the fairness floor, capped solver rewards, collusion resistance, fees. |
| `P2-settlement-pricing.md` | Turning a winning loop's surplus into per-leg prices: equal log-surplus split under uniform directional clearing. |
| `P2-loop-selection.md` | Clearing as optimization: flow LP vs packing ILP, chains, failure-aware objective, pre-commit compression. |
| `proof-fabric.md` | Cross-phase proofs and certificates: trie proofs vs POT, the pin table, certificate envelopes, absence proofs. |
| `P3-guarantee-coupling.md` | loopmarket's half of the factbond coupling: witness edges, reliance-capped insurance, oracle consumption, risk-priced routing. |
| `P4-privacy.md` | Staged privacy: Tier 1 with zero new cryptography, the P2 format-freeze list, and explicit dead/deferred rulings. |
| `ontodag-coupling.md` | The catalogue contract: dimension terms, unit families, match degrees, and the upstream-vs-local tripwire table. |
| `catalogue-bootstrap.md` | Seeding and governing the shared catalogue: seed taxonomies, the import pipeline, norms as protocol rules. |
| `adoption-and-thickness.md` | Where the first loops come from: launch verticals, the broker surface, bridge liquidity, thickness engineering. |
| `THREATS.md` | The threat register, T1–T9, ordered by expected damage to a young system; mirrored in factbond. |

factbond's corpus: `mechanism-design.md` (the deepest document),
`insurance-products.md`, `netting-and-reserves.md`, `evidence-policy.md`
(primary home of the oracle roster), `records-and-anchoring.md`,
`phase0-simulation.md` (the go/no-go instrument), `loopmarket-coupling.md`
(mirror of `P3-guarantee-coupling.md`), `THREATS.md` (mirror register).

## Phase ↔ document matrix

- **P1 (federation)** — `P1-federated-book.md`; supported by
  `ontodag-coupling.md` (spacetime migration, derived indexes) and
  `catalogue-bootstrap.md` (the shared catalogue P1 offers pin).
- **P2 (verifiable settlement)** — `P2-batch-auction.md`,
  `P2-settlement-pricing.md`, `P2-loop-selection.md`, `proof-fabric.md`;
  constrained by `P4-privacy.md` (format-freeze list) and gated by
  `THREATS.md` T1/T3 tripwires.
- **P3 (guarantee fabric)** — `P3-guarantee-coupling.md` +
  factbond's entire corpus; gated by factbond Phase-0 green *and* the P2
  format freeze (witness telemetry lands earlier).
- **P4 (privacy)** — `P4-privacy.md`; Tier 1 may ship alongside P2.
- **Cross-phase** — `proof-fabric.md`, `THREATS.md`,
  `adoption-and-thickness.md`, `catalogue-bootstrap.md`,
  `ontodag-coupling.md`.

## Reading order

First pass: `ARCHITECTURE.md` (the sharpened map) → `THREATS.md` (what can
kill it) → `P1-federated-book.md` (nearest execution). Settlement track:
`P2-loop-selection.md` → `P2-settlement-pricing.md` → `P2-batch-auction.md`
→ `proof-fabric.md`. Guarantee track: factbond `DESIGN.md` (with its
2026-08-07 flagged revisions) → `mechanism-design.md` →
`insurance-products.md` → `phase0-simulation.md` →
`P3-guarantee-coupling.md`. Market track: `adoption-and-thickness.md` →
`catalogue-bootstrap.md` → `ontodag-coupling.md`.

## What this index does not promise

Order of documents is not order of construction — gates decide that; and a
document's existence proves nothing about feasibility. Phase-0 simulation
and the named empirical gates can kill designs recorded here; the corpus is
built so that they can.
