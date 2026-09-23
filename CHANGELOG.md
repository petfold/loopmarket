# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

Started 2026-09-11. Releases are tag-driven (`v*` tags run
`.github/workflows/publish.yml`, PyPI trusted publishing).

## [Unreleased]

## [0.12.0] — 2026-09-23

### Added

- **What a counterparty must be able to trust — the claims, ranked**
  (P3 §4b, Peter, 2026-09-19): performance, description (the roster's
  countersign split into *received* and *as described*, the item-not-as-
  described dispute as its own proposition), credentials for services
  (matches a registry; a future `credentials` field), the handover point's
  liveness (factbond's first domain, seen from the leg), maker track
  record (U12), catalogue edges. **Start with the automated boxes** (§4c):
  parcel lockers' existence, access hours and peer-handover model as the
  first bonded handover points — no person speaks for a box, and every
  handover through one reports back.
- **factbond as the resolver** (2026-09-19 evening): `LoopEscrow` gains
  the key-only `hold(bytes32)` / `resolve(bytes32, uint256)` — the
  `subject` a generic resolver names, keccak(offer, loop), derivable from
  the record — beside the (offer, loop) spellings; a `Reservation`
  remembers its offer; `EscrowClient.subject`. The CLI's `resolver`
  setting names who resolves the reservations `finalize` sends (factbond's
  `Assertions` once deployed; a give's declared `arbitrator` wins; empty:
  my key). `tests/test_escrow.py::test_factbond_as_the_resolver` compiles
  factbond's contract from the sibling checkout and runs a claim on a
  real reservation both ways — certified by timeout and paid, disputed
  and refuted with the giver refunded — skipping without `../factbond`.
  Live on Gnosis the same night: `LoopEscrow` redeployed at
  `0x299CE499fdDA61bCB006718E5Ac551B5006269Bf`, factbond's `Assertions` at
  `0xfa6f9367A283A8c53AA876C1416D4B49027bBF99`, and a claim on beat 2's
  reservation certified by timeout and paid through the escrow.

### Fixed

- **`loop matches` on Python 3.11** (2026-09-23): the rate, an exact
  `Fraction` since the v4 record, was formatted with `:.4g`, which
  `Fraction` supports only from 3.12 — CI's 3.11 job had failed on every
  push since. Formatted as a float, as every other rate in the CLI is. The
  README's test count is current again (216).

- **Offers cleared under an old clearing contract no longer clear again
  after a redeploy** (2026-09-23; `proof-fabric.md`'s open problem of
  2026-09-18). `BeatClearing` takes its `predecessors` at construction and
  answers `filled` as its own `recorded` fills plus theirs — the old
  contracts' fills are the floor. `retire(successor)` (the arbiter, once)
  stops new beats on a contract, and its still-open beats count the
  successor's fills at finalize. Leg verification moved into
  `LegVerifier.sol`, deployed once beside the clearing contract (the two no
  longer fit EIP-170 together: 10.2 kB + 16.8 kB). `beat.deploy` deploys
  both; `scripts/deploy_beat.py` takes `--predecessors`, `--verifier`,
  `--retire`; `BeatClient` gains `recorded`, `predecessors`, `successor`,
  `retire`. Redeployed on Gnosis the same evening: BeatClearing
  `0xaF1BBE184bb52981841919FBAc9BfF9f2a04691e`, LegVerifier
  `0x21fD83C2A3DEee6042a359E4ad3A4a4537F41803`, SealedBeat
  `0x6E8f425eb89d20cB3B85F26dE1EDC17E3218E40C`, the six earlier contracts
  with beats as predecessors; live, the loop cleared on the previous contract
  found no candidate from a book that never saw its fills, and posted straight
  to the new contract was convicted on challenge.

- **`BeatClearing.finalize` can no longer overfill an offer** (2026-09-23).
  `submit` took fills without their offers' quantities, so `finalize` added
  them blindly: two beats solved against one book, each sound at its root
  and open at once, recorded every fill twice unless someone challenged the
  second. Each committed fill now carries its offer's cap (a give's
  quantity, a want's 1/1); `finalize` checks all of a beat's fills against
  what the chain recorded since and, if any no longer fits, cancels the beat
  whole and refunds the bond. A false cap, a want committed as less than
  whole, or a give fill differing from its leg convicts on challenge (the
  last used to revert the challenge instead). `beat.submission` commits the
  caps; `BeatClient.verdict` reports the fill faults as the contract would
  (`fill_fault`, `cap_fault`); `pending_fills` returns the cap. The `Fill`
  ABI changes; redeployed on Gnosis the same day — BeatClearing
  `0x8997131ABD1a7A9a11A60cf828D82d6cEAA42913`, SealedBeat
  `0x2161FB768fDc5e9331dcF3aa04178ADDF1b44cba` (bond 0.01 xDAI, window 720
  blocks; period 240, commit 120). Live gate the same day: one loop posted
  twice, the first finalize recorded its four fills, the second cancelled the
  racing beat and returned its bond; the apples were filled once. `loop finalize` reports a beat the contract cancelled
  as cancelled (exit 1) and reserves nothing behind it; before, it printed
  "finalized" whatever happened and, with an escrow set, would have reserved
  deposits for a beat that recorded no fills.

## [0.11.0] — 2026-09-19

### Added

- **The crypto escrow — `LoopEscrow.sol` and `loopmarket.escrow`** (P3
  §5a, 2026-09-19). A smart contract as a maker: it signs by state
  (`registerOffer`) and takes no personal tokens, so its holding is a
  condition on the giver's give, not a leg. A giver's declared v5 `Bond`
  is deposited behind the offer id (`deposit` in the chain's native coin,
  `depositToken` for an ERC-20); the arbiter reserves a share per fill
  (bond × taken / quantity), pays the wanter on a ruling of failure
  (`release`, the excess of the reservation returning to the giver) and
  returns the reservation on the wanter's countersignature or after the
  window (`refund`); the giver withdraws only what no fill holds and only
  after a notice period. `EscrowClient` (the `chain` extra), `to_wei`
  refusing a quantity the asset cannot hold exactly (U9),
  `scripts/deploy_escrow.py`, the artifact shipped by
  `scripts/build_beat.py`. CLI: `set escrow chain:RPC@CONTRACT` (the
  record names the address only) and `loop deposit [ID] [--check]`,
  funding each of my gives' bonds in the gas token. **Rebuilt the same day
  as custody plus a resolver interface** (§5e, Peter: *a ruling or a
  timeout*): every undisputed case settles without a ruling — `settle`
  after a quiet claim period by anyone, the wanter's `countersign`, the
  giver's `cancel` at the ladder's amount for that lead (`ladderAt`) —
  and a contested claim is factbond's bonded assertion about (offer,
  loop), the resolver fixed at clearing making exactly two calls, `hold`
  and `resolve`, bounded to that fill. The clearing's key reserves with
  the leg's wanter, window, resolver, claim period and ladder. Seven tests
  on a local EVM. **And the chain is the authority on a deposit** (the
  same day): `matching.meets(held=)` counts a deposit naming an escrow
  only up to what the contract holds — threaded through every gate, the
  agent (`escrow_held`), the clearing (`MockClearing(escrow_held=)`) and
  the CLI whenever `escrow` is set — so a declared, unfunded bond meets
  nothing; and `loop finalize` reserves on the escrow the share of every
  bonded give the finalized loop relies on (`escrow.reservations_for`:
  the share in smallest units, the wanter's key, the give's arbitrator or
  my key as resolver, the want's time term as the window, `escrow_claim`
  as the claim period, the wanter's ladder converted at her price into
  the asset). **Deployed on Gnosis at
  `0x7bee68244f2Bc2d67F21E5ae2eE7696Afca9c55F`** and gated live the same
  day: no loop while the bond was unfunded, the loop after `deposit`,
  posted as a beat, and after the window `finalize` recorded the fills
  and reserved the share on the escrow, read back from a fresh client. Not yet: `BeatClearing` reserving from the contract
  itself, and factbond's contract as the resolver.
- **A bare `set bond N` is N on my scale** (2026-09-19): deposited as
  `default_asset` at my price for it (5 on my scale at 2 per xDAI is
  2.5 xDAI), as the design says — the value on the giver's scale,
  converted once at the giver's declared price.
- **`xdai` in the triangle catalogue** under `stablecoin cryptocurrency
  currency`, the names of ontodag's economics pack (v6 carries `dai`,
  `xdai`, `usdc`, `bzz`, `xbzz`), so the demo's makers can bond in the
  chain's gas token.

- **The `challenge` verb — the optimistic beat gets its challenger**
  (P2, 2026-09-18). The CLI keeps no copy of what `propose` posted: the
  book is the channel. `loop challenge BEAT [LEG] [--check] [--book SPEC]`
  reads the beat from the contract (pins, the committed leg and potential
  hashes, the window), finds the `loop/` record behind it — in the
  submitter's announced clearing book (the beat's `msg.sender` is the
  announcing key, U8), or `--book`, or my own — by rebuilding the
  submission from the record and the snapshot at the beat's book root and
  hashing to exactly the commitments (`beat.find_evidence`,
  `proposal_from_record`, `commitment`); re-derives every leg off chain
  with the checklist that cleared it (`MockClearing.verify_leg`, factored
  out of `submit`; `rehearse` runs the whole checklist without
  committing) against what the snapshot *and the chain* leave of each
  give; asks the contract's own verifier for its verdict on each leg for
  free (`BeatClient.verdict`: `verifyLegExternal` through `eth_call` sent
  as the contract itself, funded by a state override where the node has
  one); and sends the challenge only for a leg the contract would convict
  — the beat cancelled, the bond the challenger's. A fault only the
  off-chain check sees (a give that does not fit the want, an expired
  window, a withdrawn offer) is reported as the arbiter's, and no gas is
  spent on it; a beat with no record anywhere is reported as unverifiable
  (exit 2). `loop beats [--open]` lists the beats and their state.
  `tests/test_beat_client.py`: an honest beat verifies and nothing is
  sent; a structural forgery (105 kg of a 100 kg give) is convicted from
  the forger's own record and the bond paid; a semantic fault is reported
  and kept off chain; the CLI end to end on a local EVM.
- **The submitter asks the contract before paying the bond.**
  `ChainClearing.submit` runs every leg of the submission through the
  contract's verifier by the same free `eth_call` (`BeatClient.verdict_of`,
  under the submission's own pins) after the local checklist and before
  `submit`; a leg the contract would convict is a rejection naming the
  reason, and no beat is posted. Found live the same day (below): an
  honest beat from a Swarm-addressed clearing book was convictable.

- **The BMT verifier: books on Swarm prove on chain** (P2, 2026-09-18,
  the roadmap item the live gate below turned into a blocker).
  `contracts/SwarmAddress.sol` computes Swarm's content address on the EVM
  — keccak256 of the little-endian span and the binary Merkle root over the
  payload's 32-byte segments zero-padded to 4096 (the all-zero subtrees a
  constant per level, so a 400-byte record costs ~15 keccaks), and the
  chunk tree above one chunk (leaves of 4096, intermediates of up to 128
  references, a lone entry promoted) — mirroring swarmfs's splitter, which
  Bee's plain upload matches. `TrieProofVerifier` takes an `addressing`
  argument (0 sha256, 1 swarm) and hashes nodes and values under it;
  `LoopVerifier.Beat` pins it as a fifth field, so the beat commits to the
  scheme its root is in; `beat.submission` reads it from the proof
  envelope. Measured: 57 k gas to address a 400-byte blob, 277 k a full
  chunk, 321 k two chunks; a Swarm-addressed inclusion 1.0–1.2 M. Verified
  against swarmfs's `content_address` at every tree shape (empty, partial
  segment, one chunk, two leaves, a one-byte tail) and on a Swarm-addressed
  book's real proofs; a beat from such a book posts and verifies.
  **Redeployed on Gnosis at `0x1277B4906b6Aab4dF806dd85c5ED980135C12931`** (the pins ABI changed;
  bond 0.01 xDAI, window 720 blocks, arbiter the deployer's key). The
  artifact is rebuilt by `scripts/build_beat.py`. **Live the same evening:**
  a fresh Swarm clearing book announced on Gnosis posted the triangle as
  beat 1 on the new contract in one attempt (recordstore 0.20.3's probe
  retry behind it), and a fresh session's `loop challenge 1` found the
  record through the announcement, read it from Swarm, held every leg off
  chain and heard "leg verifies" from the contract on each — the beat
  stands, exit 0; finalized after its window (six fills, 384 k gas).

- **Composed wants on chain** (P2, 2026-09-18 evening). `LoopVerifier`
  reads a v4 `Parts` want — the `"parts":[...]` array, each part's
  quantity and unit from its own `{"concepts":...}` object — and verifies
  the composed leg's structural half: one give per part, the quantity
  taken from give i exactly part i's, in part i's unit, on top of the
  per-give step/floor/remainder and the potentials; parts on the give side
  refuse (U1). **The want-quantity rule** came with it for plain legs: the
  thing's give (give 0, or the aggregated gives together) hands over the
  want's quantity in the want's unit — a submitter taking two tickets for
  a want of one lesson, or a run for a lesson, is convicted structurally
  now; which give among operators is the thing stays the semantic half's.
  Measured: 6.3 M gas for a two-part composed leg, 3.7 M for a one-give leg
  under the new checks. `tests/test_loop_verifier.py` on the evening
  (two tickets and a transport, cleared by the Python clearing) with every
  new refusal; `tests/test_beat_client.py` posts it as a beat through
  `ChainClearing` and the challenger verifies it. **Redeployed on Gnosis at
  `0x6614D98e9659ED5f14DdD68c98C7e223a0CA47Bf`** (bond 0.01 xDAI, window 720 blocks, arbiter the
  deployer's key); `0x1277B4906b6Aab4dF806dd85c5ED980135C12931` keeps the morning's beat 1.
  Live at once: a fresh Swarm clearing book posted the triangle as beat 1
  on it in one attempt and a fresh session's `challenge 1` answered
  *verifies*; finalized after its window (six fills, 383 k gas).

- **The sealed-proposal beat** (P2, `docs/plans/P2-batch-auction.md`
  §2–§6, 2026-09-18 evening). `contracts/SealedBeat.sol` in front of
  `BeatClearing`: beats on a fixed cadence from deployment (`period`
  blocks, the first `commitBlocks` the commit phase, the rest the reveal
  phase); one commitment — keccak256(proposal || salt) — per solver per
  beat, never replaced; the reveal emits the proposal bytes, so the
  revealed set is the chain's and the same for every reader; `record`
  pins the outcome a submitter derived (the hash of the revealed set it
  read and of the winners), the first standing and a different later one
  a visible `Disputed`. `src/loopmarket/auction.py`: a proposal is a
  *bundle* of loop records pinning one root (`bundle_bytes`, `seal`,
  `unbundle`); the numeraire-free score is the exact product of (1 + gain)
  over the winning loops — Σ log surplus, invariant to any maker's unit
  (U14); the fairness filter (§5, CIP-67 generalized to cycles) gives every
  offer the best gain any candidate through it offers as its reference and
  drops a loop that gives a member less; the deterministic baseline's
  loops enter every beat as the reserve bid (§8), a revealed loop
  outranking the reserve's copy; selection (§6) is offer-disjoint packing
  maximising the score — exact over subsets up to twelve survivors, greedy
  by gain beyond — with ties by loop_id then bundle hash (U6 extended to
  the beat); `outcome` re-derives every revealed loop with the clearing
  checklist first (U3). Winners go to `BeatClearing` loop by loop through
  `ChainClearing` (offer-disjoint, so never conflicting) and the clearing
  book records `auction/<beat>`. `SealedBeatClient` and `MemorySealedBeat`
  (an in-process beat with a block counter) behind `open_sealed`. CLI: the
  `auction` setting (`chain:RPC@CONTRACT` or `memory:`), `commit` (solve on
  the fold, seal, keep the opening in `sealed/BEAT.json`), `reveal [BEAT]`,
  `outcome [BEAT] [--check]`, `sealed [BEAT]`. `tests/test_sealed_beat.py`:
  a ring that withholds the good loop loses to the reserve bid; the memory
  and chain beats keep their phases and refuse a second commitment, an
  early or wrong reveal; the outcome posts, verifies under `challenge`, and
  a divergent record is a dispute; the CLI end to end. Not built: Shutter
  threshold encryption (the plan's primary sealing, behind the same phases),
  solver bonds (factbond, §8), the LP/ILP packing over partial-fill
  capacity (`P2-loop-selection.md`), the endogenous spread leg (§7).
  **Deployed on Gnosis at `0xbE1Af10c55dc9969539f5a1de79eD663bdaDDCd5`** (240-block beats, 120 to commit,
  outcomes to `0x6614D98e9659ED5f14DdD68c98C7e223a0CA47Bf`).
  **Live the same evening, on its third beat:** a Swarm clearing book
  announced on Gnosis committed the triangle's fresh offers in the commit
  phase, revealed them in the reveal phase, and at the close derived the
  outcome — one candidate, the solver's own loop winning over the reserve
  bid — posted it as beat 2 on the clearing contract and recorded it on
  `SealedBeat`; a fresh session read the recorded outcome and `challenge 2`
  answered *verifies*; finalized after its window (six fills, 383 k gas). The two earlier live beats surfaced the two fixes
  above it: a fold computed under the book's addressing, and the chain's
  fills subtracted by the hunt and the checklist.

- **A fold is computed under the book's addressing** (2026-09-18 evening,
  found by the sealed beat's first live run): a proposal solved on the
  memory fold pinned a sha256 root while the Swarm clearing book held the
  same content under a BMT root, so the revealed loop was "solved against
  another root". `Session.fold` builds the fold in a store of the book's
  own addressing — a scratch directory under Swarm addressing for a
  Swarm-addressed book — so the fold's root is the root the book has once
  it absorbs the fold, and a pinned root is one the book and the chain
  resolve.
- **The chain's fills are subtracted everywhere the book's remainder is
  asked** (the second live run): a fold of twelve offers, six filled on
  chain by a finalized beat it had never seen, proposed a loop through a
  spent one — refused by the pre-bond dry run, but it should not have been
  proposed. `MockClearing` takes `chain_fills` (`BeatClearing.filled`),
  refuses an offer the chain has filled whole or down to dust and caps the
  rest; `ChainClearing` wires it by default; `SolverAgent.chain_fills`
  drops spent offers from the hunt; `auction.outcome` and the reserve bid
  take it; the CLI passes the clearing contract's `filled` to `loops`,
  `commit`, `propose` and `outcome` whenever `beat` is set.

- **Loop selection** (P2, `docs/plans/P2-loop-selection.md` §1–§4, §6,
  §8; 2026-09-18 evening). `src/loopmarket/selection.py`: a candidate loop
  is an `Item` — what it takes from each offer (a want whole, a give by
  the leg's quantity), its legs, its gain — and `pack` chooses the set
  worth most under the offers' capacities: an indivisible offer or a want
  once, a divisible give shared up to what is left of it (U11's oversold
  rule, seen from the front). Exact by depth-first branch and bound up to
  N\* = 24 candidates within a 200 000-node budget — a function of the
  instance, never the clock (U6) — and the deterministic greedy beyond;
  ties in §8's total order (score, fewer legs, sorted loop ids, canonical
  legs). The objective is §4's failure-aware expected surplus with the
  prior as one uninformative constant (gate G3 not yet open): at its
  default 0 plain log surplus compared as the exact product of (1 + gain);
  a positive prior is a length penalty evaluated in fixed-precision
  decimal, whose `ln` is correctly rounded by specification. **The
  recall-gap fix (§6, gate G1 — ruled required for the reserve bid):**
  `graph.enumerate_cycles` walks the whole match multigraph, every
  parallel match an edge, and judges every simple cycle up to `max_legs`
  on its own surplus and per-node feasibility, in a canonical order with a
  `complete` flag when its cap cut it; the loop the best-rate reduction
  lost and the loop the threshold masked are both found. The baseline
  (`SolverAgent.find_loops`) now enumerates candidates — cycles, and the
  circulation hunt's composed sets — and packs them under what is left of
  every offer, so two wants of one divisible give clear in one step and
  the better loop wins a tight give; Bellman–Ford's extraction tops up
  only when the enumeration was cut. The beat (`auction.select`) packs
  through the same function with capacities, and the fairness filter
  reads an offer's reference against displacement: a better loop through
  a divisible give with room for both is no alternative to the second.
  `tests/test_selection.py` (brute force over 150 random instances,
  determinism, size and budget fallbacks, the prior, both §6 cases, the
  shared give) and a beat test of the capacity rule. Not built: chains
  (§5), netting (§7), priors from data, cycle cancelling as a species.

- **Bonds and performance risk in the beat's objective — registered**
  (Peter's question, 2026-09-18 evening; `docs/plans/P2-loop-selection.md`
  §4a, cross-noted in the batch-auction plan §5, P3 §5, THREATS T7, the
  roadmap's P3 and factbond's coupling document). The corpus prices
  failure to *clear* in selection and failure to *perform* solver-side
  only (premium-weighted edges), while the offer's own `bond` is carried,
  not weighed — so winner determination, the fairness filter and the
  reserve bid score nominal surplus and a lemons leg at the best rate wins
  the beat against a bonded alternative. §4a lays out a member's expected
  benefit (π · the thing + (1 − π) · compensation, both moved by the
  bond), the numeraire wall (U14 admits only dimensionless factors), the
  three routes — admissibility by a maker's declared counterparty
  requirements (the first candidate: fail-closed, deterministic,
  F6-clean, a record field for the escrow bump), a risk-weighted
  objective from pinned sources only, or the status quo — the gaming
  mirror (bond-bought priority), and the decisions left to the escrow
  bump. `selection.weight(factor=)` is the hook: a dimensionless per-item
  factor in (0, 1] that weighs a candidate's expected benefit through the
  same order and fallbacks; nothing sets it yet. factbond is asked for the
  doctrine size per leg, a pinned adjudication-outcome record, and who
  receives a slashed bond.

- **Admissibility by declaration — the v5 record** (Peter's ruling on the
  question above, 2026-09-18 evening). `schema.Requires(bond, oracles)`:
  what a maker requires of any counterparty on a leg through its offer — a
  bond floor in the bond's own asset (no numeraire enters, U14) and the
  witness types it accepts (empty: any). It rides every v5 offer as
  `requires`, and the maker's own `bond` is an exact rational there (U9);
  passing `requires` to `give`/`want` selects v5 as `service`/`where`
  selected v2; v4 records re-encode byte for byte and refuse a `requires`
  key; a v5 record without one is refused. `matching._gates` refuses a leg
  unless each side's requirement is met by the other side's declaration,
  fail closed (U7), in every check — so no inadmissible leg is ever a
  candidate, the reserve bid honours requirements for free, and the
  clearing checklist refuses what a solver hand-builds. `LoopVerifier`
  accepts v4 and v5, reads the declared bond and the requirement, and
  convicts an unmet floor ("bond below the counterparty's requirement") or
  an unaccepted witness type structurally; a v4 counterparty declares no
  rational bond and fails any floor above zero. CLI: `set bond AMOUNT` and
  `set require_bond AMOUNT` (validated non-negative), shown in the render
  as `requires`. Until P3's escrow a bond is a declaration the gate
  compares; the escrow makes it true. `tests/test_v5_record.py`, the
  verifier's convictions, a v5 book through the beat, the CLI settings.
  Not built: an accepted-oracles setting in the CLI (the API has it), a
  history requirement (needs U12 statistics), the escrow. **Redeployed on
  Gnosis:** `BeatClearing` at `0x6699A442630356fcBB4E0DFbD67c2E6D5550F7Ea` (v4 and v5 legs;
  bond 0.01 xDAI, window 720) and `SealedBeat` at `0x2014e7D3A097a709c3d27Df67617dcF9879A2A2A`
  pointing at it (240-block beats, 120 to commit); the earlier addresses
  keep their beats as history. **Live at once:** three makers declared a
  bond of 1 and required 1 of every counterparty, a fourth offered the
  better-priced repair with no bond — it was never matched — and the
  bonded triangle posted as beat 3 from a fresh Swarm clearing book and
  *verifies* from a fresh session, v5 legs on chain. The same run showed
  what a redeploy is: a fresh fill authority — the two earlier rounds'
  offers, filled on the previous contracts, cleared again as beats 1 and
  2 on the new one; all three finalized after their windows. Migrating a
  fill set across a redeploy is registered as an open problem
  (`proof-fabric.md`).

- **Who receives a slashed bond — working doctrine** (Peter's examples,
  2026-09-18 late; `docs/plans/P3-guarantee-coupling.md` §3a). Cleared
  obligations stand and the failed leg is replaced by a payment; the
  wanter's required floor is liquidated damages, declared to cover its
  whole reliance — payments to the innocent counterparties of the same
  leg, the substitute, the inconvenience — so bonds on gives will be high
  and every give of an all-or-nothing leg covers the whole loss alone;
  adjudication comes off the top and the remainder returns to the
  defaulter; several defaulters split the one loss by their shares;
  repair is the wanter's choice, a replacement leg paid in the bond's
  asset from the payout; claims are staked. **Ruled the same evening and
  built:** a bond is **reserved per fill** — `Requires.met_by(taken=)`
  compares bond × taken / quantity in every matching check and
  `LoopVerifier` convicts "bond share below the counterparty's
  requirement"; the requirement carries a **`cancel` floor** (v5; `set
  require_cancel`) owed when the giver cancels the leg before its window
  — a late ride cancels and re-offers with the new time, so there are no
  degrees of default;
  and the repair protocol (P3 §3a rules 8–10): the solver fixes the
  circulation first from the reserved share, the wanter is told only when
  no quick fix exists, offered a pre-computed fix as an optional draft,
  and is under no obligation from the moment it is told. Open: the
  payout's timing, what "quickly" is. **Redeployed on
  Gnosis** for the share check: `BeatClearing` at `0xe5699BE764CE66209b29D25c22413feffD63433A`,
  `SealedBeat` at `0x79493a82F36B9EEABDE974044020F72055Bf4A32` (same parameters).

- **Release prices and re-clearing — direction** (Peter, 2026-09-18 late;
  `docs/plans/P3-release-and-reclearing.md`). The required floor is the
  maker's true neutral point, a self-assessed buyout price anyone may pay
  to cancel its side of a cleared leg (Harberger's device without the
  tax; admissibility is the discipline); hysteresis by choice; a buyout is
  a release, not a failure; re-clearing is cancel-and-replace in one
  transaction, re-balancing every affected maker; the Pareto re-match
  (everyone still served) owes nothing and is the first piece to build —
  superseding loop records, a superseding beat within the window; the
  payments are the entrant's bids in the bond's asset, never the loop's
  surplus (U14). Nothing built yet.

- **What a bond is held in — direction** (Peter, 2026-09-18 night;
  `P3-release-and-reclearing.md` §5–§5a, P3 §3a, factbond's coupling
  document). A personal unit cannot be a bond (internal, instantaneous,
  unescrowable); the protocol names no asset; the wanter names the
  durable, escrowable categories she accepts with her prices per unit on
  her own scale, beside her neutral and cancellation points; conversion
  happens once at clearing on private scales and "later" is a transfer of
  the reserved quantity; the loop is tried first as compensation (the
  switch cost, in kind). The escrow is a service; medium term only the
  smart-contract agent: a contract signs by state (its registered offer
  ids), takes no personal tokens, and its holding is a condition on the
  giver's give rather than a leg (U5 stays), with `deposit`/`release`/
  `refund` and a verdict hook on the clearing contract; physical escrow
  goes to the roadmap's end. The v5 `bond`/`requires` change is held until
  read.

- **The neutral point over lead time — a ladder** (Peter, 2026-09-19;
  `P3-release-and-reclearing.md` §5c). What a cancellation costs depends
  on when: a few `(lead, amount)` points on the maker's own scale,
  interpolated linearly, read at the cancellation's lead time; the CLI
  derives it from `require_cancel` and `require_bond` over a horizon that
  is a fraction of the lead at posting, in one of a few shapes (`set
  ladder linear|late|early|flat`), the record carrying only the points; the counterparty's bond covers the ladder's maximum, so the
  gate is unchanged; fixed at clearing; symmetric. Replaces the single
  `cancel` number in the held v5 change.

- **The v5 record in its accepted shape** (2026-09-19; `docs/plans/
  P3-release-and-reclearing.md` §5d, accepted by Peter). `Requires(point,
  ladder, accepts, oracles, escrows)`: the maker's neutral point on a
  no-show on its own scale; the cancellation ladder over lead time
  (ordered `(lead, amount)` points, linear between, read at the
  cancellation's lead before the leg's handover window — `Requires.at`);
  the durable, escrowable asset categories it accepts as compensation,
  each with its own price per unit (`Acceptance`); witness types; escrow
  kinds. `Bond(asset, value, escrow)` on a give: a deposit — a `Thing` —
  worth `value` on the giver's scale, held by an escrow contract, reserved
  per fill (`Bond.reserved`). `matching.meets` is the gate in every check:
  witness type and escrow kind accepted, the deposit under an accepted
  category through the catalogue in that entry's unit, the reserved share
  covering the point at the acceptance's price; two conversions each on
  one scale, one comparison in the asset's unit, no asset named by the
  protocol (U14), a point with no acceptance met by nothing (U7).
  `LoopVerifier` reads the deposit object and the acceptance table and
  checks the same structurally where an acceptance equals the deposit's
  category by name ("no deposit", "not in an escrow", "deposit share below
  the counterparty's neutral point"); subsumption stays the semantic
  half's. CLI: `set bond 'QTY[UNIT] CATEGORY... VALUE'`, `set escrow`,
  `set require_point`, `set require_cancel`, `set ladder linear|late|
  early|flat` (the ladder derived over the lead to the offer's time term),
  `set require_accepts 'CATEGORY... UNIT PRICE; ...'`, `set
  require_escrows`; the render shows the deposit and the requirement. The
  day-old `bond`/`requires` numbers are replaced within v5, not bumped.
  **The default asset is the chain's gas token** (Peter, 2026-09-19): a
  bare-number `set bond 5` deposits 5 xDAI worth 5, and a `require_point`
  with no `require_accepts` accepts xDAI at 1 — `default_asset`, `xdai
  xDAI 1` while Swarm settles on Gnosis, a CLI default the record spells
  out (the protocol names no asset); an asset category the catalogue
  lacks is refused at publish rather than matching nothing (U7).
  **Redeployed on Gnosis** for the verifier: `BeatClearing` at `0x75025e88749963B85c95f2EFB0143D76eA7169B8`,
  `SealedBeat` at `0xFB533254050087E384DEB98CAF2be4874Ba7c592` (same parameters; measured 6.4 M gas for a
  one-give v5 leg with a deposit and an acceptance table).

### Live gate, 2026-09-18

The challenger from a fresh session. Three makers' `rs:` books announced
on a file channel; the clearing session on a fresh Swarm feed announced
itself on the Gnosis registry as `clearing` (owner = the chain key) and
`loop propose` posted the triangle as **beat 2** from that Swarm book. A
session sharing nothing with it but the chain and the Bee node — an
empty book, its own copy of the pinned catalogue, the chain registry only,
no key — ran `loop challenge 2`: the announced set gave the submitter's
clearing book, the loop record was read from Swarm, rebuilt and hashed to
the beat's commitments, every leg re-derived off chain and held, and the
contract's verifier answered **"node hash mismatch"** on every leg: the
Swarm-addressed book proves under BMT roots the deployed sha256 verifier
cannot check (the roadmap's unbuilt BMT variant), so the honest beat was
convictable by anyone. Sent with a key, the challenge cancelled beat 2 on
chain and the bond went to the challenger (24 s end to end). Until the BMT
verifier exists, beats are posted from `rs:` (sha256) clearing books, and
the pre-bond dry run above refuses the rest. The gate also surfaced
recordstore's cold feed probe raising at one transient 500 (three
`propose` runs in a row failed in the first commit to a fresh feed);
fixed as recordstore 0.20.3 (the probe retries with backoff, like `get`).

## [0.10.0] — 2026-09-15

P2 clearing on chain: recordstore's trie proofs verified on the EVM, the
structural half of a leg verified from the anchored root and the record
bytes, and the optimistic beat — one outcome per beat with a bond, a
challenge window, fills recorded at finalization — deployed on Gnosis and
posted to from `loop propose`. Contracts, the Python client and the CLI
verbs; the semantic half stays optimistic with an arbiter hook. Needs
ontodag 0.26.1; the `evm` extra runs the contract tests.

### Added

- **The on-chain trie-proof verifier** (P2 clearing, step one; decided
  with Peter 2026-09-15: an optimistic beat with a structural verifier on
  chain, fills recorded by the contract). `contracts/TrieProofVerifier.sol`
  verifies recordstore's proofs (sha256 addressing) on the EVM with no
  JSON parser — sha256 per node, the child for the next key byte read
  after `"XX":"` — inclusion with the value blob, and absence.
  `tests/test_trie_verifier.py` compiles it with py-solc-x and runs it on
  eth-tester against real book proofs (new `evm` extra). Measured: 1.2–1.6 M
  gas per inclusion, 0.64 M per absence on three-node paths.
- **The on-chain loop verifier** (step two): `contracts/LoopVerifier.sol`
  verifies the structural half of one leg — the value envelope and the
  record's hash against its id, inclusion under the beat's root, v4 and
  the pins, sides and makers, each quantity taken within the give and on
  its step and floor and within what is unfilled, and the potentials
  balancing the leg by exact cross-multiplication — reading fields from
  the canonical bytes by pattern. Measured ~3.5 M gas per one-give leg.
  Composed wants are not on chain yet. `tests/test_loop_verifier.py` feeds
  it real proposals from the Python clearing.
- **The optimistic beat contract** (step three): `contracts/BeatClearing.sol`
  — one outcome per beat posted as commitments with a bond; a challenge
  re-verifies one leg on chain against its committed hash and, if it
  fails, cancels the beat and pays the challenger (an out-of-gas
  verification is a refusal, not a conviction); after the window anyone
  finalizes and the contract records the fills exactly — the chain as the
  authority on what is filled; an arbiter address may cancel for what the
  contract cannot compute. Measured: submit 0.57 M, challenge 3.7 M,
  finalize 0.28 M gas. `tests/test_beat_clearing.py`.
- **The beat from Python** (step four): `beat.submission(proposal,
  snapshot)` builds what the contract commits to — leg hashes over the ABI
  encoding, fills, potentials, pins — and `BeatClient` submits, challenges,
  finalizes and reads `filled`; `clearing.ChainClearing` runs
  `MockClearing`'s checklist and posts the beat, the book keeping the data
  and the chain the commitments; the CLI gains the `beat` setting,
  `propose` and `finalize BEAT`; the compiled ABI ships in
  `loopmarket/contracts/BeatClearing.json` (inside the package). `tests/test_beat_client.py`.
- **The beat contract is deployed** on Gnosis at `0xFD1022636c2f0Cd3bbE5f4e40E0ee33C39654D08` (bond 0.01
  xDAI, window 720 blocks); `loop propose` posted the triangle as beat 1
  the same day, six fills, in five seconds; `loop finalize 1` recorded
  them on chain after the window. The compiled artifact ships inside the
  package (`loopmarket/contracts/BeatClearing.json`) so an installed
  wheel talks to the contract; the README quotes CI's collected count.

## [0.9.0] — 2026-09-15

The v4 record put to work: the quantity token carries a give's floor and
step, a divisible give is filled in part and its remainder stays open, and
several gives of one thing add up to one want. Live Bee gates and the
whole suite green with the node up.

### Added

- **Aggregation by quantity** (`P2-loop-selection.md` §10, the six lifters).
  One want of one thing met by several gives of it: `Leg.quantities`
  carries the shares (and enters the leg's key), `check_aggregate` is the
  exact check, `aggregate_legs` the deterministic depth-first baseline
  search — largest shares first, smaller multiples of a step after — wired
  into the agent; clearing re-derives the split; the fill names every give
  with its share. `tests/test_aggregation.py`.
- **Partial fills of divisible gives.** A fill takes exactly the want's
  quantity and the remainder stays open for the next loop:
  `OfferRegistry.available`/`taken`/`loops_of`/`availability`, matching
  and the composition searches take `available=`, the solver passes the
  book's remainders, clearing re-derives against its own. A give taken in
  part is filled at `fill/<offer>/<loop>` (whole at `fill/<offer>` as
  before); U11 now also refuses a give filled whole and in part, or
  oversold. A remainder below the floor or one step is dust and exhausts
  the offer (`Thing.exhausted`). The stepped clearing regime is therefore
  the exact one: no rounding. `Loop.per_node_ok` is the circulation's
  rule (lot paid against unit price times quantity taken; it compared unit
  prices of two different things before). `show` prints what is left.
  `tests/test_partial_fills.py`.
- **The quantity token carries the floor and the step**: `[MIN..]QTY[UNIT][:STEP]`
  — `50kg..100kg:25 flour` is a hundred kilos in 25 kg sacks, fifty at
  least; `1000:1 apple` a thousand by the piece (cli.md §6). Rendered back
  the same way; a floor or ceiling alone names no quantity and is refused
  with the encodable spelling named; a want refuses a floor or a step,
  since the give's decide a fill.

## [0.8.0] — 2026-09-14

The v4 record — exact rationals (U9), `step` and `min` in place of
`divisible`, wants of `Parts`, fills with quantities — and the registry
contract deployed on Gnosis with the live read-path gate passed. Every
offer id changes, as any record bump does; v1–v3 records re-encode byte
for byte and the v3 form stays available with `v=3`.

### Added

- **The v4 record** (decided with Peter and built 2026-09-14; the plans'
  four items in one bump). Exact rationals on the clearing path — U9
  enters the invariants: `schema.q`/`rat`, `Fraction` rates, potentials
  and surplus, no epsilon in any gate, floats only in the `-log` search;
  a typed float is the decimal it prints as. `step` and `min` on a
  `Thing` in place of `divisible` (0 continuous, the whole quantity
  indivisible, 1 whole apples, 25 sacks; the floor is the chartered bus;
  `Thing.takes(qty)` the one rule, identical to the old one on old
  records). A want of `Parts` — several things, all or nothing, one price
  — publishes: `check_parts`, `parts_legs`, the CLI's `+` line and
  composed drafts now publish (the `not encodable until v4` refusal is
  gone), `show`/`offers` render parts, `line_for` round-trips with a
  trailing `valid(...)`. Fills name every give with the quantity taken
  (`LoopProposal.fills`; a want's fill lists `gives` with `qty`) and
  nothing else — no prices, per P4 §5 item 4, ruled conditional the same
  day (receipts arrive with sealed offers). The `loop/` record carries
  `"v": 1`, `taken` per give, exact numbers and the potentials (public
  for now, outside `loop_id`). v1–v3 records re-encode byte for byte;
  the 2026-08 fill shape still reads. Not yet: a CLI spelling for `step`
  and for the give floor (`10kg..` is still refused at publish), partial
  fills of divisible gives, and the stepped clearing regime.
  `tests/test_v4_record.py`.
- **The registry is deployed**: `LoopBookRegistry` at `0xD4379E494a488411D964BebDb210C0bf628d97af` on Gnosis
  (2026-09-14). `loop set registry chain:https://rpc.gnosischain.com@0xD4379E494a488411D964BebDb210C0bf628d97af`;
  `loop announce` from a `bee_signer` key sends the transaction as that
  key, and a session with only the registry setting reads the announced
  set back with `announced`; with the Bee node up, the same clean
  session read the maker's offer from the announced Swarm feed with
  `offers` and printed the fold's root with `fold` — the read-path gate,
  live, no peer configured anywhere. The contract header is a plain
  comment now (solc read `@OWNER` in the NatSpec text as a tag).

## [0.7.0] — 2026-09-14

The read path: a book becomes discoverable by one announcement on the
chain Swarm settles on, every reader folds the announced set under U8 as
each book's owner, and a manifest is a cache audited against that set.
GSOC and the aggregator-agreement check dropped; terms stored in the
catalogue's canonical spelling; two aliases kept "one release" removed.
Needs ontodag 0.26.1. The registry contract is written and tested against
a client with web3's face; deployment on chain follows.

### Added

- **The announcement channel, and the read path** (Peter, 2026-09-14:
  skip GSOC, go straight to the chain; the aggregator-agreement check
  goes with it). `announce.py`: a book becomes discoverable by one
  announcement — `Announcement(owner, book, role)`, latest per owner,
  retractions — on one of three backends chosen by spec:
  `chain:RPC_URL@CONTRACT` (the `LoopBookRegistry` contract,
  `contracts/LoopBookRegistry.sol`, its event log read with
  `eth_getLogs`, announcements sent as the maker's own transaction so
  `msg.sender` is the feed-signing owner; web3 behind the new `chain`
  extra, lazy), `file:PATH` (sessions on one machine), `memory:`; several
  comma-separated specs are one channel (`UnionAnnouncements`, per owner
  the last-listed wins, writes go to all) so a move to another EVM chain
  is a setting, not a change — nothing in contract or code names a chain;
  the deployment follows the chain Swarm settles postage on.
  `Aggregator.subscribe(channel, open_book)` folds exactly the announced
  set; `audit_manifest(expected=channel.announced())` reports a book
  announced and never folded as an omission with an absence proof, so
  completeness is one reader's computation and aggregators are no longer
  trusted by agreeing with each other. CLI: the `registry` setting and
  `announce [--role]`, `announced`, `fold`; with a registry set every
  fold is the announced set folded through `Aggregator` under U8 as each
  book's announced owner — the solver-self-fold as the default read
  path, manifests as caches. `scripts/deploy_registry.py` deploys the
  contract; not yet run against a deployed one. Plan: `P1-federated-book.md`
  §4 rewritten, T14 updated. Tests: `tests/test_announce.py`, the
  three-maker file-registry flow in `tests/test_cli.py`.

### Changed

- **Terms are stored in the catalogue's canonical spelling.** The CLI runs
  every known term through ontodag's `surface.elaborate` before it enters
  an offer — `weight(8000g)` → `weight(8kg)`, `time(2026-10)` → the
  month's full range (as a bare `2026-10` already was), `transport(weight(..8kg)
  small-item)` → `transport(small-item weight(..8kg))` — so one denotation
  is one offer id (U2). `schema.canonical_term`, the interim sort that
  only ordered an operator's constituents, is gone; `Thing` sorts
  concepts and nothing else.

### Removed

- `Ontology.declare_service_roles` (the 0.3.0 name, kept one release) and
  the `loopmarket.settlement` import alias (the pre-2026-09-07 name, kept
  one release). Both had outlived the release they were kept for.

## [0.6.0] — 2026-09-14

The operator's argument is its want: `transport(small-item weight(..8kg))`
on the courier's give is what the courier accepts, matched want-within-
give against the wanter's `transport(bicycle)`; the term is ontodag's graph
kind (0.26.1). Breaking: `declare_operator` takes the category and its two
ends. Needs ontodag 0.26.1.

### Added

- **An operator's argument is its want** (Peter, 2026-09-13 evening: *the
  parameter of the transport is a want from the transporter's side*).
  `give transport(small-item weight(..8kg)) from(barcelona) to(barcelona)`
  says what the courier accepts; `want transport(bicycle weight(5kg))
  from(flat) to(shop)` says what the wanter hands over; the argument is
  matched want-within-give, constraint by constraint (`bicycle ⊑
  small-item`; the 12 kg bicycle fails the 8 kg limit; a give constraint
  the want is silent on refuses), the operator category itself
  give-within-want. `transport(A B)` is the same term as `transport(A)
  transport(B)`; `schema.canonical_term` sorts the constituents so the
  spellings are one offer id (U2). The same argument is the payload check
  of a composed leg (`Ontology.accepts`): the small-item courier moves the
  box and not the piano — the gap 0.5.0's composition had. A direct
  transport want now matches the courier in `check_match`. New facade
  methods `operator_of`, `argument`, `ends`, `accepts`; the CLI rejoins a
  term's tokens while a parenthesis is open. The term is ontodag's
  **graph kind** (#19, asked and landed the same evening, ontodag
  0.26.1 — the pin moves): `declare_operator` puts the category under
  `graph-dimension` as well as `operator`, ontodag canonicalises the
  argument (sorted, deduplicated; a redundant constraint such as
  `transport(bicycle small-item)` refused, an unknown one failing closed)
  and orders two such terms by the graph, and a give whose argument the
  catalogue refuses matches nothing rather than "anything". Tests in
  `test_ontology.py`,
  `test_circulation.py`, `test_schema.py`, `test_cli.py`; the index recall
  book carries operator terms; `examples/delivery.loop`'s courier says
  `transport(small-item)`.

### Changed

- **`declare_operator` takes the category and its two ends** —
  `{"transport": ("from", "to")}` puts `transport` under the new `operator`
  marker and the roles under `operator-input`/`operator-output`; 0.5.0's
  `{base: (in, out)}` shape raises. `Ontology.operators()` is gone: a
  give's moves are read off the ends it names (`ends`), and an operator
  give is recognised by its operator term, not by carrying two role terms.
  The seeds (`triangle.od`, `delivery.od`, the demos) declare
  `graph-dimension dimension`, `transport graph-dimension operator`
  and `storage graph-dimension operator`. Pin `ontodag>=0.26.1`.

- **Composition search: only where needed, and up to two hops** (Peter's
  follow-up questions, 2026-09-13). `composed_legs` no longer composes an
  operator onto a give that already reaches the want (a lesson at the door
  already serves a want anywhere in the city), and chains up to two
  distinct operator gives for one thing — two couriers of the same packet,
  shop to hub, hub to door — proposing a chain only where a shorter one
  does not reach. `check_composition` always applied operators in
  sequence; clearing verifies chains of any length. Tests: two deliveries
  in one ring, two couriers of one packet (`tests/test_circulation.py`).

## [0.5.0] — 2026-09-13

The day after 0.4.0, from one worked example (a vegetable box, a shop, a
courier, a door): no `where`/`when` heads, handover coordinates matching
when one side contains the other, and a baseline solver that finds
circulations — a want met by several gives at once, cleared as one leg.
Needs ontodag 0.25.0.

### Added

- **The baseline solver finds circulations** (Peter, 2026-09-13: "the
  whole point of a solver is to find circulations"). A want may be met by
  several gives at once: `matching.Leg`, `check_composition(want, gives)`
  — the thing's give moved by an operator give the catalogue declares
  (`Ontology.declare_operator({"geo": ("from", "to"), "time": ("depart",
  "arrive")})`; the operator's input must be comparable with the thing's
  coordinate, its output replaces it) — and `composed_legs`, the cubic
  one-hop search. `graph.Circulation` is a set of legs in which every
  maker both gives and receives; feasibility is the existence of node
  potentials (a Bellman–Ford-shaped fixpoint; for a simple cycle exactly
  product > 1), `surplus` compounds the largest uniform per-leg gain and
  equals `Loop.surplus` on a cycle, `loop_id` agrees with `Loop` there.
  `find_circulations` is a deterministic depth-first hunt the agent runs
  after Bellman–Ford's simple cycles. Clearing re-derives composed legs
  with `check_composition` and checks the potentials; the `loop/` record's
  legs carry `gives` and a composed set its `potentials`; U11 reads them.
  `examples/delivery.loop` clears the grocer's box at the shop plus the
  courier's run to the door as one composed leg (with the ring closed by
  two lessons); the seeds declare the operators.

### Changed

- **No `where`/`when` heads; handover coordinates match either way**
  (Peter, 2026-09-13, from the vegetable-box example). Where an offer
  holds is a bare geo term in its conjunction — `give vegetable-box shop`,
  a cell, a region, a place node — and when it holds a bare time term; a
  head stays only for the two ends of a route or transport
  (`from`/`to`, `depart`/`arrive`) and for descriptive geo/time terms
  (`made_in`, `made`). A handover coordinate on a give answers the want's
  when it fits within it *or contains it*: the seller delivering anywhere
  in the city serves the want at the door, the shop serves the buyer who
  collects anywhere; partial overlap is not a match; categories and
  descriptive terms stay one-way. The seed marks the dimensions:
  `declare_handover(["geo", "time"])` (roles under them inherit),
  `declare_descriptive(["made_in"])`. `DimensionIndex.candidates` queries
  the one-way terms only and leaves place and time to `check_match`. The
  seeds, demos, `triangle.loop` (`give piano-lesson amara_flat 100`) and
  the CLI (`set terms home`, a bare `LAT,LON,R` or `today..+7d`) follow;
  `examples/delivery.loop` and `tests/test_handover.py` carry the example,
  including the leg the P0 solver cannot yet compose (the shop's box plus
  the courier's `from(barcelona) to(barcelona)` — P2's operator form).

## [0.4.0] — 2026-09-13

Needs ontodag 0.25.0 (role parameters naming nodes, `items_only`, the
dimension cache; released the same day). The night's design thread: one
relation, containment, for every term — the overlap rule of 0.3.0 was a
modelling error (Peter: a want is the wider cone, a give the narrower).

### Changed

- **One relation: containment, for every term** (Peter, 2026-09-12 night:
  "an overlap of everything with A is just A"; "a want is a wider cone and
  a give is a narrower cone" — the toothbrush wanted within five metres of
  the reception desk within thirty minutes is a narrow want, and the give
  that fits within it matches). Where and when a thing changes hands are
  terms like its categories: `Ontology.satisfies` is `is_below` term by
  term, a want's place and window are query terms, and a give must fit
  within them. The 0.3.0 overlap relation for "service roles" — heads
  under a `service-role` marker matched by "a handover point exists" — is
  gone with the marker: `declare_roles({head: base})` declares a role of a
  dimension (one edge, `odag put from geo`; `declare_service_roles` stays
  one release as an alias), and `is_service_role`/`split_roles`/`meet`
  left the facade. A give that says nothing about where it hands over does
  not satisfy a want that says where; a want that says nothing does not
  care. The example catalogues and `triangle.od` drop the marker.
- **`DimensionIndex.candidates` is one `get` of the want's own conjunction**
  (`get([line marker, *want.concepts], items_only=True)`): place and time
  prune like categories because they are terms like categories. No
  overlap queries, no set arithmetic on the answer, nothing filed but what
  a give says (the v1/v2 window and disc are fields the exact check gates).
  The day's detours — three queries intersected in Python, ontodag #14's
  `overlapping=` planner argument, a whole-space value for silence — are
  withdrawn with ontodag's overlap query mode. Suite 54 s → 11 s.

### Added

- **Names stand in role terms** (ontodag #15, 2026-09-12). A role head
  takes the base dimension's nodes as parameters, so a catalogue name in
  a role term is published as spelled — `where(ljubljana)` (a region above
  cells), `where(my_home_4th)` (a floor under a building), `from(my_home)`
  — and ontodag orders it by the graph. The CLI substitutes a value only
  for a *private* place (a name only the personal store holds, which the
  pinned root cannot carry): it publishes as its cell and the name stays
  private; a private region or floor is refused. A name outside the
  dimension is refused in ontodag's words, never read as a literal cell.
### Removed

- **The `idx/{c,t,g}` recordstore index** (`index_offers`,
  `OfferRegistry.ids_by_index`, `spacetime.cell_for`/`cell_chain`/
  `day_buckets`/`bucket_chain`, the `service-cell` index head): read by
  nothing since 2026-08-21, retired as decided 2026-09-07 now that the
  one-query generator exists. **`Manifest.index_root` is gone with it**
  (three roots: book, provenance, announcement); cone summaries get a
  root of their own if they ever come (`P1-federated-book.md` §2).

### Changed

- Live-checked 0.3.0 on the Bee 2.8.2 light node right after release:
  `loop -f swarm:TOPIC --catalogue examples/triangle.od < examples/triangle.loop`
  published six v3 offers, found and cleared the triangle (`loop_id`
  `2eab00cd3c84c475…`, the same id the in-memory G1 test produces — a
  fixed `now` makes the live book byte-reproducible) in 1m51s; a fresh
  session read the book root and six filled offers back in 11s.
- The federation demo live on the same node with ontodag's core pack, 4m25s:
  three per-maker feeds and a Swarm catalogue with v3 offers, two aggregators
  folding to byte-identical manifests, the censoring aggregator convicted by
  two absence proofs verified without a store, the forgery refused, the
  tombstone honoured, the triangle cleared at 12.22% on a book re-based on
  the fold, and a follower reading the loop and six fills from the manifest.

## [0.3.0] — 2026-09-12

The day's design thread, `docs/plans/P1-spacetime-terms.md`: place and
time leave the offer's fields for its conjunction (the v3 record), the
catalogue declares which heads match by overlap, cells are the geo truth,
and the address reaches the courier through the book.
The record that will carry composed-want parts, per-fill quantities and
D9 rationals — called "v3" in 0.2.0's notes — is now **v4**.

### Added

- **Sealed handoffs and `watch`** (`docs/plans/P1-spacetime-terms.md` §4,
  decided with Peter 2026-09-12): the address is settlement text on the
  place node (`loop place NAME LAT,LON,R [ADDRESS...]`), never vocabulary
  or record. After a loop clears, `loop watch` reports the maker's fills
  (the fill record is the notification), seals each remembered text to the
  leg counterparty's public key — recovered from the signature on their
  own offer, no registry — and writes it as `handoff/<loop>/<offer>` beside
  the maker's filled offer in their own book; the counterparty's `watch`
  opens it with `bee_signer`. `loop handoff ID TEXT` sets the text for one
  offer, `loop handoffs` lists what was sealed to you, the `interval`
  setting paces `watch`. New module `loopmarket.handoff` (ECIES over the
  makers' secp256k1 keys; the `sig` extra gains coincurve and
  cryptography), `sigs.recover_public_key`, registry
  `attach_handoff`/`handoff`/`handoffs`/`loop_of`, and fold admission of a
  maker's own handoffs only.
- **The v3 offer record** (`docs/plans/P1-spacetime-terms.md` step 5,
  decided with Peter 2026-09-12): no `service` window, no `where` disc —
  where and when a thing changes hands are role terms in the conjunction
  (`when(a..b)`, `where(cell)`, `from`/`to`, `depart`/`arrive`), matched by
  overlap through the catalogue; cells and region nodes are the exact geo
  truth, and no record holds a disc. `valid` may be open-ended (`[start,
  null]`: the offer stands until withdrawn). v1/v2 records still read and
  match among themselves, and the field form of `give`/`want` still
  yields a v2 record; `check_match` refuses pairs across the v2/v3 line.
  `spacetime.cell_for_coords` is the v3 spelling of `LAT,LON,R`: the
  finest cell containing that radius. The triangle clears in v3 form
  (`tests/test_v3_record.py`, both demos, `examples/triangle.loop`
  unchanged).
- **Service roles in the catalogue** (`docs/plans/P1-spacetime-terms.md`,
  decided with Peter 2026-09-12): `Ontology.satisfies` now walks one
  conjunction with two relations — containment for what a thing is,
  overlap for where and when it changes hands — and the *head* decides
  which, declared in the catalogue under the marker node `service-role`.
  The marker is the only name the core knows: which heads are roles
  (`from`/`to` over `geo`, `depart`/`arrive` over `time`) is seed
  vocabulary, written with `odag put from geo service-role` or
  `Ontology.declare_service_roles({...})`. A give from anywhere in `u2e`
  now serves a want at
  `u2e4x` and vice versa; `made_in(u2e4x)` still only satisfies
  `made_in(u2e)` one way. Absent role = unconstrained; same-head terms are
  their meet; an uninterpretable role term fails closed on either side.
  No record change: the `service`/`where` field gates still run beside it,
  and a catalogue that declares no roles behaves exactly as before. The
  fields leave at the v3 bump, the package's step 5.
- **Role terms in candidate generation** (step 4 of the same package):
  `DimensionIndex` files a give under its service-role terms and
  `candidates` asks overlap per role head the want names, plus the gives
  silent on that head — place prunes through cells for the first time.
  Recall-exact against the baseline over randomized books carrying
  `from`/`to`/`depart`/`made_in` terms. `Ontology.split_roles` and
  `Ontology.meet` are public. The example seeds (`triangle.od`, both
  demos) declare `from`/`to` over `geo` and `depart`/`arrive` over `time`
  under `service-role`; `triangle.od` carries ontodag's prelude for it.
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

### Changed

- **`loop` speaks only catalogue terms.** `when(...)` and `where(...)` pass
  through as role terms (the seed declares them; `triangle.od` carries
  ontodag's prelude for it); the one interpreted head is `valid(...)`,
  now accepting `valid(A..)`; `time(...)` terms are accepted; a
  `LAT,LON,R` parameter of any geo-kind head becomes the containing cell;
  the approval block shows terms and validity only; `place` writes the
  node under its cell and no disc metadata. The `where`/`when` settings
  and `--where`/`--when` flags are replaced by one `terms` setting
  (`--terms`): terms added to every offer whose line does not name that
  head; unset, an offer is anywhere, any time (Peter's ruling: optional).

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
