# loopmarket — roadmap

Phased like the sibling projects: each phase has an exit criterion, and a
phase is done when that criterion is met with tests. Keep this file updated
(mark items DONE with a date).

**This file is an index, not a specification.** Each phase below links to its
plan document under [`docs/plans/`](docs/plans/), which holds the decisions,
the measurable gates, the named open problems and the closing "what this
document does not promise" section. Nothing is restated here that lives there.

---

## P0 — the pipeline, in memory and live on Swarm

Goal: uniform offers over an OntoDAG catalogue, a versioned offer book on
recordstore, and a solver finding loops — running end to end.

- [x] The full pipeline in memory (DONE 2026-08-01).
- [x] Live on a real Gnosis-mainnet Bee node (DONE 2026-08-01): catalogue and
      book on Swarm, book head in a signed feed, fills atomic — the gated
      `tests/test_swarm_book.py`.
- [x] One intersection engine (DONE 2026-09): no set arithmetic in loopmarket
      itself, `idx/` retired, candidate generation issues one query not three.

Alpha; interfaces will move.

## P1 — the federated book · [plan](docs/plans/P1-federated-book.md)

Goal: one book per maker under the maker's own feed and signer, folded by an
aggregator that cannot lie about what it folded.

- [x] Federation live (DONE 2026-08-21): per-maker books under their own feeds
      and signers, an `Aggregator` folding them under the U8 admission rules
      into a four-root manifest on its own feed, withdrawal tombstones, and a
      scorched-earth follower reconstructing the cleared world from
      (address, topic) alone — the gated `tests/test_swarm_federation.py`,
      96.5 s on a Bee 2.8.1 node.
- [x] Catalogue from ontodag's `core` pack, and a censoring aggregator
      convicted from its own manifest (DONE 2026-09-04): `audit_manifest`
      with absence proofs, and a solver folding the announced maker books
      itself recovers the honest fold (T14).
- [ ] Two-layer offer authenticity (U8) hardened beyond the demo path:
      detached signatures and fold-time `origin/` records as the plan
      specifies; the detached signature in EIP-712 typed-data form so a
      hardware wallet renders the offer's fields (added 2026-09-11).
- [ ] The command line · [plan](docs/plans/cli.md) — `loop` in the
      package, ontodag's grammar with two conventions (quantity first,
      price last), names as catalogue nodes, last-price memory, the
      direction rule instead of any tolerance parameter, the approval
      block before publish, batch scripts replacing the Python demos.
      Design 2026-09-11, nothing built; `loop-mcp` follows it.

## P2 — verifiable clearing

Three plans, all at *design* as of 2026-08-07, none built.

- [ ] **Batch auction** · [plan](docs/plans/P2-batch-auction.md) —
      fixed-cadence beats with a cancellation cutoff pinning the book root;
      sealed proposals (Shutter on Gnosis, commit-reveal fallback);
      numeraire-free scoring (U14).
- [ ] **Clearing pricing** · [plan](docs/plans/P2-clearing-pricing.md) —
      the equal log-surplus split as the pricing rule. *Clearing* is the
      atomic commit that fixes obligations; *settlement* is the makers
      delivering, which is P3.
- [ ] **Loop selection** · [plan](docs/plans/P2-loop-selection.md) —
      divisible legs are a flow LP, indivisible legs a bounded-cycle packing
      ILP; exact winner determination for small beats.
- [ ] Open before v3: the integer granularity of a give.
- [ ] Decide with the contract design: anchored offer ids (maker-optional,
      bodies on Swarm) as the contract's set authority where present,
      trie proofs otherwise — the alternative recorded 2026-09-11 in
      [P1 §4a](docs/plans/P1-federated-book.md), with the substrate
      capacity table to be refreshed then.

## P3 — the guarantee fabric · [plan](docs/plans/P3-guarantee-coupling.md)

- [ ] Witness-edge emission as derived telemetry at settlement
      re-verification; settlement-attached insurance under the indemnity
      principle; the leg-oracle coupling. Design, 2026-08-07.

## P4 — staged privacy · [plan](docs/plans/P4-privacy.md)

- [ ] Tier 1, with zero new cryptography: mixnet transport, Shutter-sealed
      bodies and submissions, adaptive k-enforced coarsening. Tiers 2 and 3
      follow. Design, 2026-08-07.

---

## Cross-cutting plans

Not phases — they constrain every phase, and each is at design as of
2026-08-07:

- [ ] [Adoption and thickness](docs/plans/adoption-and-thickness.md) —
      vertical selection, and how a market gets thick enough to clear.
- [ ] [Catalogue bootstrap](docs/plans/catalogue-bootstrap.md) — the seed set.
- [ ] [OntoDAG coupling](docs/plans/ontodag-coupling.md) — what loopmarket
      may rely on in ontodag's contract.
- [ ] [Proof fabric](docs/plans/proof-fabric.md) — recordstore's canonical
      roots as the substrate for proofs.
- [ ] [Threats](docs/plans/THREATS.md) — T1–T14; design 2026-08-07 with a
      dated edit 2026-08-21. T14 is closed in P1 above.

## Invariants

U1–U7 are binding and live in [`CLAUDE.md`](CLAUDE.md). **U8–U14 are
planned**: specified in the plan documents that motivate them and summarized
in `ARCHITECTURE.md` §11, they become binding invariants only as the code
that honours them lands. U12 is settled as a rule already: cleared loops
count, delivery never adds credit.
