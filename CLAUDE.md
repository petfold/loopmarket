# CLAUDE.md

Guidance for Claude Code in this repository: what is true now, and which
rules hold. Keep it that way. When the state, a rule or a decision changes,
edit its line here in the same commit, and put the story elsewhere:
`CHANGELOG.md` for what a release changes, `ARCHITECTURE.md` or a plan in
`docs/plans/` for why, and `docs/plans/JOURNAL.md` for what a session did,
deployed and measured. The journal holds this file's diary up to
2026-10-09, moved there unchanged.

## What this project is

`loopmarket` is a universal combinatorial marketplace. Every economic
intention is one uniform, content-addressed **offer**: a thing described
as a conjunction of OntoDAG categories (where and when it changes hands are
terms in that conjunction), priced on the maker's **personal scale**, a
bookkeeping numeraire that is never held or transferred. Each maker keeps
an **offer book**, a recordstore keyspace (on Swarm in deployment), and
aggregators fold the announced books into one. **Solver agents** look for
**loops**: circulations whose exchange-rate product exceeds 1, including
composed legs (an operator such as transport moving a thing), aggregated
legs and declared parts. **Clearing** re-verifies every proposed loop from
scratch and commits all its legs at once; on chain, an optimistic beat
contract verifies the structural half of each leg and records the fills.
Deposits are held by an escrow contract, and contested claims are
adjudicated by factbond.

`ARCHITECTURE.md` is the design rationale, including what is deliberately
not built; read it before structural changes. The design corpus (P1–P4,
the threat register, catalogue bootstrap, the factbond coupling) is in
`docs/plans/`, indexed in `README.md`. User documents:
`docs/USER-GUIDE.md` and `docs/REFERENCE.md`. The background is the Loop
Economy essay (`docs/loop-economy.md`).

## The stack

```
loopmarket  →  ontodag (>=0.30.6)  →  recordstore (>=0.22.2)  →  swarmfs  →  Swarm (optional)
```

- **ontodag** (`../ontodag`): the shared catalogue. A want's terms are one
  query, `get([...], items_only=True)`, and every term matches by
  containment: a want is the wider cone, a give the narrower. `Ontology`
  (`ontology.py`) is the facade (`covers`, `satisfies`, `accepts` over
  `is_below`) where pinned catalogue roots surface. Names are the identity
  at its boundary. `cli.py` still opens stores through ontodag's CLI
  module (`_open_catalogue`) and reads recordstore's private
  `_addressing_name`; ontodag 0.31 will have the public `ontodag.open`.
- **recordstore**: the book's kernel: canonical roots, snapshots
  (`RecordStore.at(root, blobs)`; the attribute is `.blobs`), three-way
  merge, `commit(reconcile=True, resolver=...)`, proofs, extension proofs.
- **Swarm**: reached only through recordstore (`swarm_store(topic,
  signer=/owner=)`, which uses swarmfs). `registry.swarm_offer_book()` and
  `Ontology.persistent()` are the only places that name it.
- **factbond** (`../factbond`): adjudication; its `Assertions` contract is
  the escrow's resolver. Six chain tests compile its `Assertions.sol` from
  that checkout.

## Dependency boundaries (`tests/test_boundaries.py`, must always pass)

- **B1** `import loopmarket`, the whole model (schema, ontology, matching,
  graph, solver, mock clearing) and the CLI work with no network, no Bee
  node and no optional dependency.
- **B2** One-way dependencies: loopmarket imports ontodag and recordstore,
  never the reverse. Swarm's clients (swarmfs, aiohttp, coincurve) and
  web3 load only inside the call paths that need them.

## Invariants (do not weaken; add tests when touching them)

Binding: U1–U7, U9, U11. U8, U10 and U12–U14 are planned in the plan
documents and enter here only when their enforcing code and tests land.

- **U1 Uniform offer form.** One side of every `Offer` is a thing (a
  `Thing`, or `Parts` on a want), the other `Tokens`, and the token issuer
  is the maker (`Offer.__post_init__`). All loop arithmetic depends on it.
- **U2 Offers are immutable, canonical values.** `canonical_bytes()` is
  deterministic and `offer_id` is its SHA-256. A new field needs a record
  version bump (`"v"`, now 1–7), and `from_record` keeps reading old
  records: it dispatches on `"v"` and raises on an unknown one, and
  `to_record` re-encodes each offer in its own version, so old ids never
  change (pinned by corpora, e.g. `tests/test_v6_record.py`).
- **U3 Clearing trusts no solver.** `MockClearing.submit` checks the
  proposal's ontology pin and register pins, re-derives every leg against
  the current book and its own ontology (`check_match`, or
  `check_composition` for a composed leg), re-checks balance (node
  potentials exist), surplus and fills, and only then commits all fills
  under one root. Any clearing backend keeps this shape.
- **U4 Solve against pinned roots.** Solvers work on `registry.snapshot()`
  and pin `ontology_root` and `book_root` in proposals.
- **U5 Positive rates only.** Disposal is a positively priced service,
  emptiness a positively priced good (ARCHITECTURE.md §7). Never signed
  prices in `Match.rate`.
- **U6 Determinism in the baseline solver.** Sorted iteration; the same
  book yields the same loop on every replica. Smarter solvers may be
  stochastic; the baseline may not.
- **U7 Vocabulary fails closed.** An unknown category never matches
  (`Ontology.satisfies` is strict), and so does every requirement the
  build cannot check: an unpinned register, an unaccepted resolver, a
  suspended statement.
- **U9 Exact rationals in everything clearing re-verifies.** Quantities,
  amounts, rates, potentials and surplus are `Fraction`s (`schema.q`),
  records spell them `n/d` (`schema.rat`), and no epsilon survives in a
  gate. The solver's `-log` search stays floating point: a search is a
  heuristic, clearing is the truth. A float typed by a person is the
  decimal it prints as.
- **U11 No partially filled loop survives a merge unnoticed.** After a
  merge every `loop/` record has a fill for each leg (whole, or per loop
  for a divisible give), every fill points at a present loop, no give is
  filled both whole and in part, and the parts of one give sum to at most
  its quantity; `verify_loop_atomicity` raises `PartialLoopError`. Every
  `option/` hold and `exercise/` record names present loops, and fills plus
  active holds stay within a give's quantity (checked when an option
  clears). Checked, not resolved: the loop-granularity resolver is an open
  problem (`docs/plans/P1-federated-book.md` §3).

The v6/v7 extensions (`docs/plans/credentials-cover-and-options.md`):
every claim path has a clock (notice and cure, evidence, ruling,
finality); a held reservation is released only by a ruling or by both
parties; and no acceptance criterion ever counts rulings, inspections,
fills or countersigns.

## Running tests

```bash
python3 -m pytest                      # everything (conftest.py puts src/ on the path)
python3 -m pytest tests/test_boundaries.py
PYTHONPATH=src python3 examples/demo_triangle.py    # must find and clear 1 loop
LOOP_HOME=$(mktemp -d) PYTHONPATH=src python3 -m loopmarket --catalogue examples/triangle.od < examples/triangle.loop
```

- With every extra installed: about 330 tests in about 11 minutes, most of
  it the chain tests on a local EVM (the `evm` extra). Without `evm` they
  skip.
- Extras: `[test]` for development; `[sig]` signatures and sealed
  handoffs; `[chain]` the on-chain clients; `[evm]` the local-EVM tests;
  `[swarm]` a Bee node. This Python is PEP 668 managed: use a venv or
  `--break-system-packages`.
- Live-node tests (`test_swarm_book.py`, `test_swarm_federation.py`,
  `test_swarm_register.py`) skip unless `BEE_API` and `BEE_BATCH` are set; always pass a real batch, so nothing auto-buys.
  Those that write feeds need a throwaway `BEE_SIGNER`; they use
  timestamped topics, so reruns don't inherit an old book.
- CI: `tests.yml` on every push (the suite without `evm`, plus pyflakes);
  `chain.yml` every night at 03:17 UTC and on demand, and `publish.yml`
  before each release, both with `[test,sig,evm]` and factbond cloned
  beside the checkout. ontodag's release gate runs this suite (without
  `evm`) against every ontodag candidate.
- Lint: `git ls-files -- '*.py' | xargs python3 -m pyflakes` with pyflakes
  3.4.0. It ignores `# noqa`: fixtures several test modules share (`env`,
  `chain`) live in `tests/conftest.py`, never imported from another test
  module; an optional import goes through `importlib.import_module`; a
  re-export is declared in `__all__`.

## Map of the code

`src/loopmarket/`:

- `schema.py`: the offer form (`Thing`, `Parts`, `Tokens`, `TimeWindow`,
  `Offer`; `Requires`, `Bond`, `Credential`, `RequiredLeg`, `Accept`,
  `Statement`), canonical encoding and ids, record versions 1–7, exact
  numbers (`q`, `rat`). Where and when are terms in the thing's concepts
  (since v3); v1/v2 discs survive only to read old records.
- `spacetime.py`: geohash cells; `LAT,LON,R` becomes the finest cell
  containing the radius. Input only; ontodag orders the stored names.
- `ontology.py`: the catalogue facade: build (`load`, the `declare_*`
  methods), query (`covers`, `satisfies`, `accepts`), pin
  (`persistent`, `commit`). The matching rules: handover coordinates
  (`geo`, `time` and roles under the `handover` marker) match when one side
  contains the other; categories and descriptive terms match one way (the
  give within the want); an operator's argument matches the other way
  round (want within give). Whoever fixes a value states a fact, whoever
  leaves it open an acceptance, and the fact lies within the acceptance.
- `dimensions.py`: `DimensionIndex` and `candidate_matches_indexed`, the
  ontodag-backed candidate generator (one `get` per want), recall-exact
  against the baseline. Not yet used by the solver (review item 2).
- `matching.py`: the exact checks (`check_match`, `check_composition`,
  `check_parts`, `check_aggregate`), `meets` (every requirement fails
  closed) and the give × want candidate generator the solver uses.
- `graph.py`: `ExchangeGraph`, Bellman–Ford, `Loop`, `enumerate_cycles`,
  `Circulation`, `find_circulations`.
- `selection.py`: `pack`, the set of loops worth most under the offers'
  capacities (exact up to `EXACT_UP_TO` items, greedy beyond).
- `solver/agent.py`: `SolverAgent`: snapshot, match, candidates, select,
  propose. The baseline species and the beat's reserve bid; smarter
  species live outside this repo.
- `clearing.py`: `LoopProposal`, `Receipt`, `MockClearing` (the production
  verifier, despite its name), `ChainClearing` (`MockClearing` plus the
  beat; it asks the contract's verifier before paying the bond).
- `registry.py`: the book and its keyspaces (`offer/`, `sig/`,
  `withdraw/`, `fill/`, `loop/`, `handoff/`, `cred/`, `option/`,
  `exercise/`, `item/`), snapshots, availability, `or_set_resolver`,
  `verify_loop_atomicity`, `swarm_offer_book`. No index in the book.
- `federation.py`: `Aggregator` folds announced books under the admission
  rules (rejections kept as attributed provenance) into a `Manifest`;
  `audit_manifest` checks a manifest against the announced set.
- `announce.py`: the announcement channel (`chain:`, `file:`, `memory:`;
  on chain the `LoopBookRegistry` event log).
- `sigs.py`: maker signatures and contact cards, by `swarmfs.signer`.
- `handoff.py`: settlement text sealed to the leg's counterparty after
  clearing. `notice.py`: notices and cures. `case.py`: a case before one
  arbitrator (claim, answer, ruling, sealed).
- `items.py`: item identity (`item(h)`) and the per-item rule.
- `gate.py`: `CounterpartyGate`, the seven checks on a required
  credential; `faults` lists every failing one. `register.py`: registers
  (status, revoked, suspended, accredit), chained roots, extension proofs.
  `arbitrators.py`: arbitrators accepted by property; `resolver_of`.
  `witness.py`: door witness types (possession by default, a photo only
  when asked for). `reputation.py`: a personal view of arbitrators from the
  escrow's log, never read by a gate.
- `escrow.py`: the `LoopEscrow` client: deposits behind offer ids,
  reservations per fill, settle, countersign, cancel, hold and resolve,
  cover and the deductible.
- `beat.py`: the `BeatClearing` side: `submission`, `BeatClient` (submit,
  challenge, finalize, `filled`), finding a beat's evidence.
  `auction.py`: the sealed-proposal beat (`SealedBeat`: commit, reveal,
  outcome).
- `cli.py` (and `__main__.py`): the `loop` command line, about 4,800
  lines (review item 10). It encodes only what the schema holds.

`contracts/`: the Solidity sources (`LoopBookRegistry`,
`TrieProofVerifier` with `SwarmAddress`, `LoopVerifier`, `LegVerifier`
with `StatementVerifier`, `BeatClearing`, `SealedBeat`, `LoopEscrow`);
the compiled artifacts the package needs ship in
`src/loopmarket/contracts/`. `scripts/build_beat.py` rebuilds them, `scripts/deploy_*.py` deploy, `scripts/gate_*.py` are the
live gates.

## Deployed on Gnosis (in use)

| contract | address |
|---|---|
| LoopBookRegistry (announcements) | `0xD4379E494a488411D964BebDb210C0bf628d97af` |
| BeatClearing (version pins by major) | `0x4A35ee6e86C266de94134BaD5523A8D7C8fA5cF4` |
| LegVerifier | `0x9E5A4D42B406119321C9d2C18A5064029DeFFD2b` |
| StatementVerifier | `0xAF3644Ff2eE6608D94c23EFC8F21f1f6218051b2` |
| SealedBeat | `0xfC5519dD267c8C398Cd29Fa1B9748078A180B5cE` |
| LoopEscrow | `0xddDB7276F705671673F0885aEf93B99b890Eb5A9` |
| factbond `Assertions` (the escrow's resolver) | `0x3c1B4C944398bcc30890d6A6c78f1F9AA2dFe270` |

`~/.loopmarket/config` names them. A new `BeatClearing` names its
predecessors, so cleared offers never clear again: the next redeploy passes
`--predecessors 0x4A35…5cF4 --retire 0x4A35…5cF4`. Earlier addresses keep
their beats as history (the journal lists them). Deploy only on Peter's
word.

## Known simplifications (deliberate; each has a roadmap home)

1. **Pricing.** Clearing re-checks exact rates, potentials and surplus
   (U9), and a loop carries a uniform per-leg gain. Choosing each leg's
   price and recording it is P2's design (`docs/plans/P2-clearing-pricing.md`:
   the equal log-surplus split, prices in private receipts). For
   indivisible legs `per_node_ok` is the conservative extra check.
   Selection is built (`selection.py`). Composition by operator,
   aggregation by quantity and declared parts are built; give-side bundles
   stay excluded (the reseller is the route), and a give's floor is in the
   record but the CLI spelling `10kg..` on a give is not wired.
2. **Candidate generation is the give × want product in the solver.** The
   indexed generator (`dimensions.py`) finds the same matches 6–16× faster
   from 100 offers a side. Decided (review item 2, 2026-10-10), not built
   yet: it becomes the one engine, for simple matches and the aggregation
   search, with no threshold, and the default solver is kept apart from
   the rest of loopmarket, the way an outside solver would be.
3. **Geo: cells for v3 and later, discs for v1/v2.** A place is a cell, a
   place node under a cell, or a region node above cells, and containment
   is exact; a region's covering is a lower bound. Covering as a value
   (`where(u24m+u24q)`) is deferred upstream (ontodag DIMENSIONS.md §14).
4. **Books.** One book per maker (its own feed and signer), folded by
   aggregators (`docs/plans/P1-federated-book.md`). A shared Swarm book is a
   development tool only: feed compare-and-set is best effort.
5. **Guarantees.** A maker's requirements (a neutral point, a ladder,
   accepted assets, witness types, escrow kinds, credentials) are enforced
   off chain and on; deposits are held by `LoopEscrow` and reserved per
   fill at `finalize`; a contested claim goes to the resolver fixed at
   clearing (factbond). Not built: `BeatClearing` reserving from the escrow
   itself, and a ruling that states an amount (factbond's to decide). The
   P3 mechanism design is factbond's (`docs/INTEGRATION.md` there).
6. **Batch auctions.** The sealed-proposal beat is built (`SealedBeat`,
   `auction.py`). Not built: Shutter as the sealing, solver bonds, the
   spread leg.
7. **No privacy layer.** Offers are plaintext. P4 is staged in
   `docs/plans/P4-privacy.md`; add no ad-hoc encryption before it lands.

## Roadmap (state)

- **P0**, the in-memory prototype: done.
- **P1**, the Swarm book: done on one machine (books on Swarm, the
  announcement channel on Gnosis, folds as the default read path, the CLI).
  Open: announced books folded live from a second machine, and two
  upstream asks to ontodag (`docs/plans/cli.md` §11): coordinates for
  `geo`, and relative times in `time(...)`. The third ask, a public store
  opener, is in ontodag's unreleased 0.31.
- **P2**, verifiable clearing: the contracts, the challenger, Swarm
  addressing on chain and the sealed beat are built. Open: Shutter, solver
  bonds and the spread leg, chains and netting (G4, G5), priors from data
  (G3).
- **P3**, the guarantee fabric: escrow, cover, deductible, notices, cases,
  registers and the counterparty gate are built, with factbond as the
  resolver. Whether P3 ran ahead of the README's gates is review item 17.
- **P4**, privacy: staged, not started.
- **Later**: price and capacity schedules inside one offer
  (`docs/plans/P2-loop-selection.md`, open problems).

## The 2026-10 review

The joint review is in ontodag (`docs/plans/REVIEW_2026-10.md`;
`docs/plans/review-2026-10.md` here points to it). Decided for loopmarket
so far: it is in ontodag's release gate, its chain tests run nightly and
before releases, and pyflakes runs in CI (item 5, built); one matching
engine, ontodag's index, with the default solver kept apart from the rest
of loopmarket (item 2); matching and clearing refuse an offer whose
registry or contract major differs from the installed ontodag's (item
4); every reader's fold re-checks a clearing book's loops, and where a
chain is configured only on-chain fills hide an offer (item 9; until then
anyone can hide an offer with an invented loop); `cli.py` split by area,
with a `Reads` object and a `LegRecord` type, built first of these (item
10); durations and relative times in ontodag's units, `min` and `wk`, a
bare `m` or `w` refused with the fix named (item 11); v1/v2 offers
retired once circulator's benchmark and the tests write v4+ (old records
stay readable), and `MockClearing` renamed `BookClearing` (item 12). Of
these only item 5 is built: Peter decides the remaining questions first,
then everything decided is built. Open for Peter: item 17 (the build
order against the README's gates).

## Conventions

- `src/` layout; tests with pytest from the repo root.
- Names are the identity at public boundaries (strings accepted where
  objects are), as in ontodag.
- Docstrings explain why (the decision), comments why not (the rejected
  alternative). Both say what is true now: history goes to CHANGELOG.md,
  a plan or the journal, not into dated notes in the code.
- One invariant, one commit.
- **Loop, cycle, circulation.** A *loop* is any cleared circulation (the
  essay's word, and `Loop`, `LoopProposal`, `loop/`, `loop_id` in code). A
  *cycle* is the strict circle, which is what the reasoning means when it
  depends on going round (products around it, negative cycles, cycle
  packing). *Circulation* is the term when flow theory is invoked
  (`docs/plans/P2-loop-selection.md` §11).
- **Arbitrator, resolver, adjudicator.** An *arbitrator* decides a claim in
  the default form: chosen by the parties, its award final (an offer's
  `arbitrator`, `loop arbitrators`). The *resolver* is the escrow's word for
  whoever may `hold` and `resolve` a reservation (an arbitrator's key or a
  contract). *Adjudicator* and *arbiter* name factbond's ladder rungs only.
  A *contact card* (`key/<address>`, `loop contact-card`) carries only a
  key's public key, signed.
- **Clearing is not settlement.** *Clearing* is the atomic commit that
  turns a proposal into fixed obligations (`clearing.py`, U3).
  *Settlement* is the makers delivering (P3: oracles, bonds, factbond).
  *Commit* is only the recordstore or chain write. Older plan documents
  and ARCHITECTURE.md still say "settlement" for clearing; read them with
  that mapping, and use the new words.

## Working with Peter

- Peter decides; Claude records the decision and builds it. An open
  question is put on its own: the question, a concrete example, the
  options with pros and cons, and a recommendation with the reason.
- Commit and push when a piece is done. Releases (a `v*` tag publishes to
  PyPI), deployments and on-chain spending only on Peter's word.
- Never print key material, and never print an RPC URL from the config
  (it can carry a key). Throwaway signers come from
  `python3 -c 'import secrets;print(secrets.token_hex(32))'`.

## Starting a session

1. `git status` and `git log --oneline -5` here, and in ontodag before
   relying on its behaviour.
2. Read "The 2026-10 review" and "Roadmap (state)" above.
3. Before changing code, run the suite or the test files the change
   touches; `tests/test_boundaries.py` always.
4. When the state, a rule or a decision changes, update its line here in
   the same commit.
