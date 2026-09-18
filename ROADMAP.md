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
      into a manifest on its own feed (three roots since 2026-09-12), withdrawal tombstones, and a
      scorched-earth follower reconstructing the cleared world from
      (address, topic) alone — the gated `tests/test_swarm_federation.py`,
      96.5 s on a Bee 2.8.1 node.
- [x] Catalogue from ontodag's `core` pack, and a censoring aggregator
      convicted from its own manifest (DONE 2026-09-04): `audit_manifest`
      with absence proofs, and a solver folding the announced maker books
      itself recovers the honest fold (T14).
- [x] The command line · [plan](docs/plans/cli.md) (DONE 2026-09-12,
      released 0.2.0; live-checked the same day): `loop` in the package,
      ontodag's grammar with two conventions (quantity first, price last)
      and a third on the want side (`+` between parts), names as catalogue
      nodes, last-price memory, the approval block before publish, batch
      scripts replacing the Python demos; drafts, `place`, `handoff`,
      `watch`, `handoffs`. `loop-mcp` still follows it (deferred by Peter).
- [x] Spacetime as catalogue terms (DONE 2026-09-12/13, 0.3.0–0.5.0 ·
      [plan](docs/plans/P1-spacetime-terms.md)): the v3 record without
      `service`/`where` fields, bare geo and time terms, handover
      coordinates matching when one side contains the other, the operator
      form (`transport(...)`, its argument the operator's own want,
      2026-09-13); ontodag #14–#19 asked and landed (0.25.0–0.26.2).
- [x] The circulation solver (DONE 2026-09-13, 0.5.0): composed legs,
      node potentials, the deterministic hunt; clearing re-derives them.
- [x] The read path (DONE 2026-09-14, 0.7.0): the registry event on the
      chain Swarm settles on is the one announcement channel (GSOC dropped
      — `LoopBookRegistry` deployed on Gnosis at
      `0xD4379E494a488411D964BebDb210C0bf628d97af`), `loop announce` /
      `announced` / `fold`, every session folding the announced set under
      U8 itself; a never-folded book is a proven omission
      (`audit_manifest(expected=)`), so aggregators are caches, not
      trusted by agreeing with each other. Live gate passed the same day
      (maker and reader on one machine).
- [ ] The read path from a second machine: live-Swarm announced books
      folded by a session that shares nothing with the publisher.
- [ ] Two-layer offer authenticity (U8) hardened beyond the demo path:
      detached signatures and fold-time `origin/` records as the plan
      specifies; the detached signature in EIP-712 typed-data form so a
      hardware wallet renders the offer's fields (added 2026-09-11).
- [ ] The three upstream asks in [cli.md §11](docs/plans/cli.md):
      coordinate input for `geo`, relative time in `time(...)`, a public
      store opener — each deletes a loopmarket-only behaviour.

## P2 — verifiable clearing

Design 2026-08-07; the record, the solver's objects and the contracts
built 2026-09-13 to 2026-09-18 (0.5.0–0.10.0). What follows is what stands.

- [x] **The v4 record** (DONE 2026-09-14, 0.8.0): exact rationals on the
      clearing path — U9 binding — `step` and `min` in place of
      `divisible`, wants of `Parts`, fills naming every give with the
      quantity taken, a versioned loop record.
- [x] **Integer granularity of a give** (DECIDED 2026-09-14): `step`
      replaces the boolean; the stepped clearing regime is the exact one,
      no rounding, since fills take the wants' own quantities.
- [x] **Partial fills and aggregation by quantity** (DONE 2026-09-14,
      0.9.0): a divisible give's remainder stays open under per-loop fill
      keys, U11 catches an oversold give; several gives of one thing add
      up to one want (the six lifters).
- [x] **Clearing prices as node potentials** (DONE 2026-09-13/14): the
      potentials are computed exactly and carried in the loop record —
      public while offers are plaintext (P4 §5 item 4 ruled conditional
      2026-09-14: receipts arrive with sealed offers). The equal
      log-surplus *split* of [P2-clearing-pricing](docs/plans/P2-clearing-pricing.md)
      §2 is not the rule in force: fills clear at the wants' own
      quantities and the potentials are the least feasible ones.
- [x] **The contracts** (DONE 2026-09-15, 0.10.0; decided with Peter the
      same day: an optimistic beat with a structural verifier on chain,
      fills recorded by the contract): `TrieProofVerifier.sol`
      (recordstore's proofs on the EVM, 1.2–1.6 M gas per inclusion),
      `LoopVerifier.sol` (one leg's structural half from the anchored root
      and the record bytes, ~3.5 M gas), `BeatClearing.sol` (one outcome
      per beat with a bond, a challenge window, fills recorded at
      finalization, an arbiter hook for the semantic half) — deployed on
      Gnosis at `0xFD1022636c2f0Cd3bbE5f4e40E0ee33C39654D08`; `beat.py`,
      `ChainClearing`, `loop propose` / `finalize`; beat 1 posted live
      and finalized (2026-09-18).
- [x] **Anchored ids versus proofs** (DECIDED 2026-09-15 with the contract
      design): the contract's own fill set is the authority on "unfilled",
      offers are proven under the beat's book root by trie proof; no
      per-offer anchoring is required (P1 §4a stays maker-optional).
- [ ] **The sealed-proposal beat** in front of the contract ·
      [plan](docs/plans/P2-batch-auction.md) §3–§7: sealed proposals
      (Shutter on Gnosis, commit-reveal fallback), numeraire-free scoring
      (U14), the fairness filter, winner selection, solver rewards. Today
      one submitter posts one outcome per beat.
- [ ] **Loop selection** · [plan](docs/plans/P2-loop-selection.md) — the
      LP/ILP selection over *competing* sets; the baseline hunts and clears
      the first feasible circulation.
- [ ] A `challenge` verb: the CLI does not keep the submission it posted;
      a challenger rebuilds it from the clearing book's loop record and the
      snapshot.
- [ ] The BMT (keccak) variant of the trie verifier, for books on Swarm
      (`addressing: "swarm"`); a compact node encoding asked upstream
      (recordstore issue #1) would cut the gas several-fold.
- [ ] Composed wants (`Parts`) verified on chain; today `LoopVerifier`
      refuses them and the beat carries only simple, operator-composed and
      aggregated legs.
- [ ] A want-side floor (the partial-fill question mirrored).

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
- [x] [Proof fabric](docs/plans/proof-fabric.md) — recordstore's canonical
      roots as the substrate for proofs: the on-chain half built 2026-09-15
      (`TrieProofVerifier.sol`, measured gas in §1); the doctrine fork
      (certificates versus U3 re-derivation) resolved in shape the same
      day — structural half on chain, semantic half optimistic.
- [ ] [Threats](docs/plans/THREATS.md) — T1–T14; design 2026-08-07 with a
      dated edit 2026-08-21. T14 is closed in P1 above.

## Invariants

U1–U7, U9 (exact rationals, since 2026-09-14) and U11 (loop atomicity,
since 2026-08-20) are binding and live in [`CLAUDE.md`](CLAUDE.md). **U8,
U10, U12–U14 are planned**: specified in the plan documents that motivate
them and summarized in `ARCHITECTURE.md` §11, they become binding
invariants only as the code that honours them lands (U10's pin checks run
in clearing and on chain already; its enforcement entry waits for the
proofs to be demanded, not merely verified). U12 is settled as a rule
already: cleared loops count, delivery never adds credit.
