# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

Started 2026-09-11. Releases are tag-driven (`v*` tags run
`.github/workflows/publish.yml`, PyPI trusted publishing).

## [Unreleased]

The 2026-10 review's item 10 (ontodag's `docs/plans/REVIEW_2026-10.md`
§8): the command line split by area, with a `Reads` object and a
`LegRecord` type. On every record the code writes, no command prints or
does anything different, and no record byte or id changes.

### Changed

- **`MockClearing` is `BookClearing`** (the review's item 12, decided by
  Peter 2026-10-10). The class clears the book in process, with the same
  checklist the chain contract re-derives; it mocks nothing, and the old
  name had readers looking for the real one. `MockClearing` stays an alias
  of the same class for one release.
- **The command line is a package by area.** `cli.py` (4,837 lines)
  became `loopmarket.cli` with one module per area: `settings`, `stores`
  (the session), `spellings`, `render`, `grammar`, `guarantees`,
  `entry`, `drafts`, `options`, `book`, `clients`, `solving`, `beats`,
  `deposits`, `registers`, `claims`, `watch` and `shell`, none above 550
  lines. `from loopmarket import cli`, `loopmarket.cli.dispatch`,
  `Session`, `offer_from_line`, `line_for` and the other public pieces,
  `python -m loopmarket` and the `loop` script work as before, and
  `python -m loopmarket.cli` too. A test that replaces a client replaces
  it on the module that defines it, where every command looks it up:
  `cli.clients._beat_client`, `cli.clients._escrow_client`,
  `cli.clients._MEMORY_SEALED`, `cli.stores._open_book`.
- **`Reads`** (`loopmarket.reads`): what the exact checks, the solver and
  the clearing read beyond the offers, `available`, `held`, `gate`, the
  chain's fills and the escrow's holdings, is one object, passed as
  `reads=` to the matching functions, `MockClearing.verify_leg`,
  `SolverAgent`, `MockClearing`, `ChainClearing` and the auction's
  `outcome` and `baseline_proposals`. The keyword parameters it replaces
  keep working (`available=`, `held=` and `gate=` on the matching
  functions and `verify_leg`; `chain_fills=` and `escrow_held=` on the
  solver, the clearings and the auction), so outside solvers need no
  change. A read given both ways is a `TypeError`, and so is giving a
  solver or a clearing `available`, `held` or a gate, which each pass
  derives from its snapshot.
- **`LegRecord`** (`loopmarket.registry`): the one parser of a `loop/`
  record's legs: the want, the gives (`gives`, else the 2026-08 single
  `give`) and what was taken from each, parsed only when asked.
  `OfferRegistry.loop_legs(loop_id)` reads a loop's legs from a book. The
  U11 check, the beat's evidence, `notice.gives_of` and every command
  that reads a loop go through it. `reservations` read a leg by its
  `gives` alone, so a 2026-08 loop record stopped it with an error; it
  now reads one as every other reader does. The record format is
  untouched.
- **Catalogue setup through `Ontology.declare_*`:**
  `Ontology.declare_place(name, cell, address=, adopted=)` is the write
  `loop place` makes, beside the other `declare_*` methods: the place
  under its `geo` cell, the address on the node, and ontodag's prelude
  adopted first where `geo` is not yet a prefix head (the one adoption
  every `declare_*` method shares). Same catalogue, same root.

## [0.14.5] — 2026-10-09

Found in the 2026-10-09 review of ontodag and loopmarket (ontodag's
`docs/plans/REVIEW_2026-10.md`; pointer in `docs/plans/review-2026-10.md`).

### Dependencies

- **`recordstore>=0.22.2`** (base and `swarm`): committing a large book
  is linear again (0.22.1 was quadratic beyond about 11,000 records).

### Fixed

- **One announced book could stop every reader's fold.** Anyone may
  announce a book, but a record that is not an object raised
  `AttributeError` inside the admission rules, and a "clearing" book with a
  loop and no fills raised `PartialLoopError` after the merge; either
  aborted `Aggregator.fold()` for everyone. Now an unreadable book is
  rejected whole (`reject/OWNER/*`, with the error's type), and a clearing
  book is admitted only if its loops are whole (U11) against the maker
  books alone. Each book is tested on its own, so which other books were
  announced, and how their owners sort, cannot decide whether it gets in.
  Two books that are each whole but claim one offer still fail U11
  loudly: choosing between them is the open problem of
  `P1-federated-book.md` §3, and settling it by owner name would let a
  chosen owner id win races.
- **A number in a record could stall or crash the reader.** `q`, which
  reads every quantity and amount, handed strings to `Fraction`, which
  computes `10**e` exactly: `"1e10000000"` took 12 s, and every further
  digit of the exponent costs at least ten times more. `"1/0"` raised
  `ZeroDivisionError`, which the fold's admission rules did not catch. An
  exponent beyond 4300 (Python's own limit on digits read from a string)
  and a zero denominator are now `ValueError`s, so such a record is
  rejected on its own and the rest of its book is folded. Found by
  fuzzing `Offer.from_record` (20,000 mutated records: none escapes now);
  the seeded mutator is now a test (3,000 records, under a second).
- **A statement that was not an object rejected its whole book.** The
  admission rule for `cred/` records caught `ValueError`, `KeyError` and
  `TypeError` but not the `AttributeError` such a statement raises, so
  the book's honest offers were dropped with it. It is now rejected on
  its own. Found by a fold test that puts garbage under every keyspace of
  a maker book (200 books, none rejected whole).
- **`loop help` listed about thirty flags that `loop` refused** (for
  example `loop --registry memory: status` was an argparse error). The
  global flags are now derived from the settings table, so every flag the
  help prints is accepted.
- **`watch` missed the second giver of a composed leg.** It matched a
  fill only against a leg's first give, so a second giver got no "filled"
  line, and the wanter's line named only the first giver. It now matches
  every give and names every giver.
- **The approval block rounded durations.** `cli.py` defined
  `_duration_text` twice, and the second, rounding definition replaced
  the exact one, so a 36-hour `claim_max` showed as `1.5d` and a
  100-second one as `1.67m`. The rounding one is now `_duration_approx`,
  used only by the option notes that estimate.

### Changed

- **Faster solver steps.** `Offer.offer_id` and `Offer.unit_price` are
  computed once and cached on the offer (outside the record, equality and
  the hash). The solver asked for them a few hundred thousand times per
  step. `SolverAgent.find_loops` over 100 offers a side: 26 s → 7.9 s.
  Most of the remaining time is `enumerate_cycles`; the bigger win is the
  indexed candidate generator (8–13× faster than the product, same
  matches), which the solver still does not use (review §6, §8).
- `Ontology.argument` uses ontodag's public `surface.elaborate` instead
  of the private `dag._canonical_name`.
- The B2 boundary test also checks that `import loopmarket` loads none of
  the Swarm path's clients since recordstore 0.22: `swarmfs`, `aiohttp`,
  `coincurve`.

## [0.14.4] — 2026-10-08

### Changed

- **Floor `ontodag>=0.30.6`.** ontodag now stores a graph-kind term with
  several constraints as its parts and drops a redundant constraint
  instead of refusing it, so a give spelled `transport(bicycle
  small-item)` is known and accepts bicycles (once bicycles are small
  items), where it used to be refused and matched nothing. The test that
  pinned the refusal now pins the new reading. The index's candidates are
  unchanged: two same-head terms on one give still mean one thing that
  meets both.

## [0.14.3] — 2026-10-08

### Changed

- **Floors: `ontodag>=0.30.5`, `recordstore>=0.22.1`** (and the `swarm`
  extra `recordstore[bee,feeds]>=0.22.1`). ontodag 0.30.1 fixed a store
  with a role head under `geo` answering `get geo(...)` with nothing after
  a native load, which is loopmarket's `from`/`to`; 0.30.5 is the current
  release. recordstore 0.22.1's `diff()` and `merge()` load ahead level by
  level, so the aggregator's `RecordStore.merge` folds read a maker's book
  in a few rounds per trie level instead of one per node. That matters for
  large books; the live federation test, whose books are small and whose
  time goes to feed lookups, took the same time (359 s, 350 s before).
  0.22 reaches Bee
  only through swarmfs, so the `swarm` extra pulls neither `requests` nor
  `swarm-bee`.

## [0.14.2] — 2026-10-08

### Changed

- **Signatures go through swarmfs's shared signer, not eth-keys.** Offer
  signatures, contact cards and door witnesses (`sigs.py`, `witness.py`)
  sign and recover with `swarmfs.signer` (0.14.0: libsecp256k1 through
  coincurve, the same signer that owns the maker's feed). The stored form
  is unchanged byte for byte: `tests/test_sigs.py` pins eth-keys' own
  outputs for three keys, and recovers them with and without coincurve
  (a reader needs no compiled library). Only that form is accepted now: a
  signature with v 27/28 was refused by eth-keys' parser and is refused by
  ours. The `sig` extra is `swarmfs[feeds]>=0.14.0`, `eth-hash`,
  `coincurve`, `cryptography`; eth-keys is gone from it.

## [0.14.1] — 2026-10-08

### Changed

- **The `swarm` extra needs recordstore 0.21.1**, whose `BeeBytesStore`
  (the book's blobs on Swarm, through `swarm_store`) keeps 32 reads in
  flight instead of 16. 16 was a guess; measured against a Bee 2.8.2 light
  node, reads of chunks the node must fetch scale about linearly to 32
  (60/s at 16, 85-108/s at 32), so a follower hydrating a book from the
  network reads about twice as fast. Nothing in loopmarket set the number,
  so nothing else changes. swarmfs 0.12 (released the same night) changes
  nothing here: the book does not use a local-first store.

## [0.14.0] — 2026-10-07

### Changed

- **ontodag 0.30 (prelude v4): the mass head is `mass`, not `weight`.**
  ontodag's prelude no longer declares `weight` (weight is a force) and
  pins `mass` to the mass family, so a catalogue's typed masses are spelled
  `mass(..8kg)`. A graph-kind term sorts its constraints, so the courier's
  term is now stored as `transport(mass(..8kg) small-item)`. Requires
  `ontodag>=0.30.0`. Tests, docstrings and docs follow.
- **The example catalogues carry prelude v4** (`examples/delivery.od`,
  `examples/triangle.od`): their inlined prelude was v3, so they refused
  `mass(...)`.
- **An unknown prelude term says how to get it**: `weight(...)` is told to
  spell `mass(...)`; a store whose prelude predates a head (`mass`, `in`,
  `about`, `shared-with`) is told to merge the current one, which moves the
  catalogue root.

- **The on-chain verifier compares version pins by major, as matching
  does** (`LoopVerifier._verifyOffer`, `beat.submission`). A beat pins the
  registry and contract majors (`"4"`, `"0"`), and every offer pinned
  within them verifies. It used to demand the beat's exact versions,
  taken from the first want, so offers written either side of an ontodag
  minor upgrade (registry 4.2 and 4.3) matched off-chain and reverted
  on-chain with "registry pin". Sound because ontodag's contract 0.4 (G7)
  promises a minor never takes an answer away on one catalogue root; a
  different major is still refused. `_LEGACY_BEATS` and the struct keep
  their field names, so encoding is unchanged. Redeployed on Gnosis the
  same day: BeatClearing `0x4A35ee6e86C266de94134BaD5523A8D7C8fA5cF4`
  (predecessor and retired: `0xC475…11d4`), SealedBeat
  `0xfC5519dD267c8C398Cd29Fa1B9748078A180B5cE`; a mixed 4.2/4.3 loop checked
  live verifies there and is refused by the retired contract.

### Fixed

- **A head pinned to a unit family is its own base** (`Ontology.base_head`,
  `head_kind`, `_kind_of`, the CLI's `_head_kind` and handover-base
  lookup). ontodag 0.30 files `mass ⊑ linear-dimension(mass)`; the family
  node is a kind node, never a head, and the base lookup had returned it,
  depending on set order.
- **`Ontology.load` takes typed parents**: a term the store makes on first
  use (`in(egg)`, `mass(3kg)`) or a family pin (`linear-dimension(mass)`),
  in any order. Core v12 and the packs now file parts that way.

## [0.13.0] — 2026-10-01

The v6 and v7 records and everything built on them since 0.12.0: the
counterparty gate, registers and their roots' sequence, options (holds)
and items, cover on the escrow with the deductible, assignment and
netting, the escrow's acts as verbs, arbitrators accepted by property,
the default arbitrator — one named key both sides accept, final — with
contact cards and the case channel, notices and cures, the title
register as a witness, and door requirements that clear on chain. Pins:
ontodag>=0.26.1, recordstore>=0.21.0.

### Deployed

- **The default arbitrator, live on Gnosis** (2026-10-01,
  `scripts/gate_arbitrator.py`): against the escrow `0xddDB…b5A9` with a
  throwaway key as arbitrator, through `loop` — contact cards, the
  wanter's claim of 0.0015 sealed to the arbitrator and the giver, the
  giver's answer, the arbitrator's `hold` and final ruling of 0.001 paid
  on chain, the reasons opened by the wanter's `watch`, and `loop
  arbitrators` reading the ruling from the escrow's log.
- **The escrow redeployed with assignment and netting** (2026-09-29 night,
  C5 stage 2): `LoopEscrow` at `0xddDB7276F705671673F0885aEf93B99b890Eb5A9`.
  Live, the taxi case: a cover claim refused until the insured assigned her
  claim on the driver, the insurer recovering the driver's deposit as the
  assignee, and a cover payout netting what the driver's deposit had
  already paid.
- **The escrow and the clearing contracts redeployed with the deductible**
  (2026-09-29 evening, C5): `LoopEscrow` at
  `0x3936E3B8A736814Ae8850Da3e75C02B476CdF3f2`; `BeatClearing` at
  `0xC47575b57E08b389c344AaBf415606Cd0B3011d4` (`LegVerifier`
  `0xf3c3cbC774641aea48Fa7aced4441C75F835468B`, `StatementVerifier`
  `0x9b961FF48d374066846b91AfbaeC6E57eBefD9c7`, `SealedBeat`
  `0x513731eC7ca8012F296E54e1b148044c5e9B0Bd9`), `0x8beD…72BC` retired to it.
  Live: a claim within the deductible refused, a certified claim paid less
  it, a v7 give cleared and verified; the E3 escrow gate rerun.
- **The clearing trio redeployed on Gnosis** (2026-09-29, C4 + I3 + R3b):
  `BeatClearing` at `0x8beD11c07aC7aCAa542dF5B0F8db94FC6C1F72BC`, `LegVerifier` at
  `0x1f6Da29dC92422Dfecec3D0cc0A7704C58aC5B13`, `StatementVerifier` at
  `0x2BC03bb1750464e3Ca45BA07Fb5063bA513f82CF`, `SealedBeat` in front at
  `0x107eA9Bd27115ea7Bfce64c275ff823eE9042d38`; `0xaF1BBE…691e` its
  predecessor, retired to it. The live gate (`scripts/gate_beat_v6.py`): an
  option beat and a credential beat verify from a fresh session, a forged
  beat pinning the register root after a revocation is convicted, and the
  older contracts' fills are the new one's floor; after the windows the
  hold and the item claim are the chain's, a non-holder's exercise is
  convicted, and the holder's clears, filling the flat once and using the
  hold up.
- **`LoopEscrow` redeployed on Gnosis at `0xA49Cc9F9dab95aAB7093F138A084027ef66dD936`** (2026-09-29, E3)
  with E1 and E2, its resolver factbond's `Assertions` redeployed the same
  day at `0x3c1B4C944398bcc30890d6A6c78f1F9AA2dFe270`. The live gate, `scripts/gate_escrow.py`, passed:
  a cover reservation refusing the countersign, the giver's own claim
  refused at `hold`, the wanter's claim holding it and, retracted,
  reopening it, a split settling on the second signature, the giver's
  `extendClaim`. The config's `escrow` and `resolver` name the new pair.

### Added

- **A personal view of arbitrators** (2026-10-01, step 4 of the default
  arbitrator; `reputation.py`, `loop arbitrators [--trust KEYS]`, the
  `trust` setting, `EscrowClient.events`): from the escrow's log, the
  arbitrators named where I or a maker I trust was a party, their rulings,
  and who among us lost a ruling under one and chose it again with an offer
  posted after the loss — a later fill of an offer posted before it is no
  new choice — with the accreditation each presents. Never read by a gate;
  nothing outside the circle counted.
- **A case before one named arbitrator** (2026-10-01, step 3 of the
  default arbitrator; `case.py`): the escrow already gave a key resolver
  its `hold` and final `resolve`; the book now carries the case between
  them — the wanter's claim, the giver's answer, the arbitrator's reasons —
  as sealed records in each writer's own book, each to one recipient, the
  fold admitting only the writer's speech to the recipient the key names.
  `loop claim`, `answer`, `hold`, `rule --reason`, `cases`; `watch` opens
  each. Each party sees the other's submission. A local-EVM test runs a
  claim through to a split ruling paid by the escrow (`tests/test_case.py`).
- **Contact cards** (2026-10-01, step 2 of the default arbitrator): `key/<address>`
  in a key's own book, a signature over a fixed message naming the
  address (`sigs.sign_contact_card`), so anyone may seal to a key that never
  signed an offer — an arbitrator receiving a claim. The fold admits a
  card only in its owner's book; sealing falls back to it where an offer
  carries no signature; `loop contact-card` writes mine.
- **The default arbitrator, said where it is decided** (2026-10-01,
  Peter: one named arbitrator both sides accept, final, is the default;
  factbond's bonded ladder an option). The approval block notes a bonded
  give that names no arbitrator (the clearing's own resolver would rule a
  claim on its deposit) and a want relying on a deposit that accepts
  whichever the give names; the `arbitrator` setting's help and the user
  guide describe the default.
- **The title register as the handover witness** (2026-09-29 night, I4):
  `registry-transfer(ID)` — a give naming an item is performed when the
  register ID shows it held by the wanter (`witness.transfer_faults`,
  `Register.transfer`/`holder` over `title/<h>`); clearing admits the type
  only on a give that names an item; `oracle registry-transfer(ID)`,
  `require_transfer`, `register transfer ITEM KEY`, `watch` reporting the
  transfer and `countersign` refusing before it.
- **Statements and registers at the command line** (2026-09-29 night,
  C7): `loop cred [SUBJECT]` and `cred present FILE`; `loop register
  issue|revoke|suspend|reinstate|accredit|heartbeat|status` running a
  register in the session's book; `set require_credentials` putting
  `requires.counterparty` entries on my wants. The dentist case runs from
  the command line end to end (`tests/test_notice.py`).
- **Inspector independence** (2026-09-29 night, E2): an inspection give
  (under the catalogue's `inspect`) is admissible only if its giver is no
  party to any leg of the loop naming an item the inspected thing names,
  its own leg included — `matching.independence_faults`, refused at
  clearing and never proposed by the baseline solver.
- **Notices at the command line and registers read by the CLI**
  (2026-09-29 night, R6): `loop notice OFFER --cure DURATION [--fact
  STATEMENT]` (the wanter's notice, sealed to the giver, the opening kept
  for a claim), `loop cure OFFER [--evidence REF]` (the giver's answer,
  sealed back); `watch` opens both and re-checks the statements a want's
  credential relied on against the registers' heads (`notice.lapsed`),
  reporting a revocation or suspension once. The `registers` setting
  (`ID=SPEC` pairs) and every book announced under the `register` role
  are read per command and handed to the solver (pinned), the clearing
  (re-read at the pins), `finalize` and `challenge`, with the resolvers'
  chain records; the CLI's gates read the handover window through the
  calendar. `notice.ref` is factbond's record reference. Live on Bee the
  same night (`tests/test_swarm_register.py`): a register on a Swarm feed
  read at its tip by spec, a proposal pinning the root before a
  revocation refused for what the newer root says.
- **The escrow's acts as verbs** (2026-09-29 night, C6): `loop
  reservations [--all]` (what the escrow holds behind my legs, read from
  the contract, the loops from the fold), `countersign`, `cancel`,
  `assign OFFER KEY`, `settle OFFER [SPLIT]` (quiet, or my signature of a
  split — `all`, `N%`, `NxDAI`, or an amount on my scale at my
  `default_asset` price), `extend-claim OFFER DURATION`, `collect
  [--check]`; a reservation named by its offer's prefix, `--loop` when
  the book knows several. Live the same night on the Gnosis escrow
  `0xddDB…b5A9` (`scripts/gate_verbs.py`): each verb as a command line,
  a 25% split signed by the giver and, in xDAI, by the heir the claim was
  assigned to, paying the heir.
- **Arbitrators accepted by property** (2026-09-29 night; Peter: "build
  acceptance of arbitrators by property"; `counterparty-gate.md` §7a;
  THREATS T20). `arbitrators.py`: an `Accept` admits a resolver whose every
  ruling key is accredited as an `arbitrator` under a named root (a
  statement in its own book, the gate's steps over pinned registers read
  at their newest roots), with at least `min_deposit` on the requirer's
  scale at stake on a reversed ruling, and no reversal within `clean_for`
  on a record at least that long — `chain_profile` reads factbond's
  `Assertions` (adjudicator, arbiter, rung deposit up to `depositWei`,
  `Reversed` events). Both sides accept: a give states an acceptance too,
  and the leg's resolver is the first candidate both admit, in the
  records' order (`resolver_of`, used by the gate and by
  `reservations_for` alike); a required leg's giver is admitted by
  accreditation for the leg's category. `named_registers` includes the
  acceptances' roots; `MockClearing`/`SolverAgent(resolver_profile=)`;
  `require_resolvers` takes `root:ID`, `min:AMOUNT`, `clean:DURATION` and
  applies to gives as well as wants; `arbitrator` seeded in `triangle.od`.
  No record change.
- **Possession is the door's default; the photo says what it costs**
  (2026-09-29, Peter; THREATS T19, biometric linkage at the door). `set
  require_door possession|photo` on my wants, `set oracle
  countersign|possession|photo-match` on my gives; a photo requirement or
  declaration notes in the approval block that it links a face to a key
  and its history. Recorded the same day: arbitrators as credentialed roles
  accepted by property (`counterparty-gate.md` §7a), identity beyond the
  deposit by an attester's escrowed disclosure, and a key per trade
  (`P4-privacy.md`).
- **Cover paid by the escrow, stage 1 (C5)** (2026-09-29). A cover
  reservation's window is the covered period — the `time(…)` inside the
  insured's `insure(…)` want, else the insurer's, else the leg's handover —
  with the claim period from its end; with the reservation cover-only, a
  claim asserted on factbond, disputed and ruled for the insured is paid out
  of the deposit (the limit) and the rest returns to the insurer
  (`tests/test_cover.py`, local EVM). Stage 2's assignment and netting
  follow (D-2, below); presentation (D-1, a ruling that states an amount)
  is factbond's decision and not built.
- **Cover stage 2: assignment and netting (D-2)** (2026-09-29, Peter's taxi
  case). A cover composed with a bonded thing records the reservation it
  covers; the insured's claim on the cover opens only once her claim on
  the covered reservation is assigned to the insurer (unless nothing is
  left there), and the cover's payout nets whatever that reservation
  already paid her. `tests/test_cover.py`: a taxi no-show paid once, the
  driver's deposit first — by assignment (the insurer recovers the
  driver's 0.05) or by netting (the cover pays 0.25 after her 0.05).
- **The deductible on the deposit, the v7 record** (2026-09-29, Peter).
  `Bond(asset, value, escrow, deductible)`: an amount of the deposit's own
  asset — money the wanter accepts, factbond's rule — for the give's whole
  quantity, a fill taking its share; only a deductible makes an offer v7
  (v4–v6 ids unchanged, three pinned in `tests/test_cover.py`). The escrow
  reserves the share with the fill, refuses a claim within it at `hold`,
  and a ruling pays the claim less it; a deposit counts against a wanter's
  neutral point only up to what it can pay, in `meets`, the gate and on
  chain (`LoopVerifier` reads v7). `set deductible AMOUNT` at the command
  line, on my scale like `bond`, held in the asset at the price my deposit
  states.
- **Options made easy to write** (2026-09-29, Peter: useful only if makers
  write them). `loop option ID` needs no numbers: the window is
  `option_window` of the lead (a quarter by default) and the premium
  `option_premium` — `suggest`ed from the book's demand for the thing, a
  flagged guess while there is none, a percentage or an amount otherwise —
  shown with their reasons for approval; `set options on` writes a give's
  option with it, in one approval block. And the demand signal: a want of
  an option on a thing like mine shows in `show` and `watch`, and `option
  ID --for WANT` answers it; `show` lists the options written on an offer.
- **Several options exercised together** (2026-09-29, Peter): `loop exercise
  O1 O2 … PRICE` wants every held offer as one composed want — a part per
  offer, one price, open until the first window closes — so a bundle's
  components can be held one by one as they are found and committed all
  or nothing at the end. In memory, from the command line, and on a local
  EVM (the composed leg verifies with each part counting only others'
  holds; finalize uses up every hold).
- **Holds, item claims and statements on chain (C4, I3, R3b)** (2026-09-29;
  local EVM, not yet deployed). `LoopVerifier` reads v6 records; an option
  leg carries its underlying's record and a beat commits the holds its
  option legs write, the item claims its gives write and its register pins,
  each give's fill naming its taker. A challenge checks them against the
  leg; `finalize` records holds and claims, consumes a holder's holds with
  its fill and cancels a beat whose hold or claim races what the chain has
  recorded since. The remainder a leg is checked against counts every
  active hold but the taker's own, so a non-holder's exercise is convicted.
  Statements go in each leg's commitment and a new `StatementVerifier`
  (split from `LegVerifier` at EIP-170) checks their `cred/` inclusion and
  their `revoked/`/`suspended/` absence under the issuer's pinned register
  root: a revoked statement is convicted by challenge. The leg ABI changed,
  so the clearing contracts are redeployed together; the verifier's record
  scanning is word-at-a-time (an option leg had cost ~11 M gas; now 4.2 M, a plain leg 2.4 M).
- **Register roots form a checked sequence (R5, option A)** (2026-09-29).
  Every register root names its predecessor and number (`chain`, written by
  `Register.commit`), and the counterparty gate refuses a root that drops a
  revocation its predecessor held — recordstore's new extension proofs, a
  root that cannot be checked failing closed. With the registers' feed tips
  read (`MockClearing(register_latest=)`, `register.newest_reader`), a
  newer root published by clearing's clock refuses a leg whose statement it
  revokes or suspends: a stale pin cannot hide what the register has said.
  Needs recordstore's extension proofs: the pin is now `recordstore>=0.21.0`.
- **CLI: `option`, `exercise`, `holds` (C7)** (2026-09-29). `loop option
  ID --until T --premium X` writes an option on my own open offer (v6);
  `loop exercise OPTION PRICE` wants its offer as the holder while the
  window is open, anyone else refused; `loop holds` (first spelled `options`) lists the holds in the
  fold. `examples/apartment.loop` waits for a way to name an offer in a
  script without its id.
- **Items: `item(h)` and the per-item rule, per maker (I1–I2)**
  (2026-09-29; `items-and-ownership.md` §1–§2). `items.py` derives h from
  a VIN, a land-register number or a maker and serial (the same identifier
  however spelled, the same h) or a tagger's record;
  `Ontology.declare_item_heads` puts `item` on the prefix kind until
  ontodag's identifier kind ships, and the matching gates refuse any item
  term that is not a whole id. Clearing writes `item/<h>/<maker>/<loop>`
  with the fill or the option's hold; a maker's second offer of an item it
  holds an open claim on is refused until the claim ends; two makers on one
  item both clear. `examples/triangle.od` seeds `item`.
- **Argument-only operators and `requires.legs` (D4)** (2026-09-29).
  `Ontology.declare_argument_operator` declares `insure` and `inspect` as
  operators by their argument alone (the `operator-argument` marker, no
  ends); `check_composition` lets such a give attach to the thing when its
  argument accepts it; `matching.legs_faults` checks a want's
  `requires.legs` — a give under each named category from a giver the
  entry admits, never a party to the leg — and the solver composes it. An
  inspection and cover composed with a car clear as one circulation of
  four makers. `escrow.cover_predicate` now recognises `insure(...)` terms;
  `examples/triangle.od` seeds both operators.
- **Options on plain offers, in memory (C1–C3)** (2026-09-29;
  `options-and-cover.md` §3). `Ontology.declare_graph_heads` makes
  `option(...)` a non-operator graph-kind head that matches by plain
  containment (the seed in `examples/triangle.od`). An option give names
  its `underlying` and `exercise`; the gate's `option_fault` checks the
  underlying; clearing writes `option/<P>/<loop>` with the option's fill
  and `exercise/` records when the holder takes it; `available(oid, now)`
  subtracts active holds, the holder's exercise adds its own back inside the
  window, and a hold expires with no write; the solver's packing capacity
  counts what holders may exercise; U11's fold check covers holds and
  exercises. Not built: holds on chain (C4), transfers.
- **R7: the door's witness types** (2026-09-29; `counterparty-gate.md`
  §7). `witness.py`: `possession` — a fresh challenge signed by the giver's
  key with the id it vouches for, spent by `DoorCheck` on its first
  response (a replay, another key or a foreign challenge fails) — and
  `photo-match` — possession plus the attester's salted photo commitment
  opened at the door and confirmed by the counterparty. A requirement's
  `oracles` may name a door level, a cumulative category
  (`door-at-least-possession`, `door-at-least-photo`; `accepted_types`);
  both types are in clearing's verifiable set; `countersign_ready` is the
  settlement check a wanter's client runs before countersigning. hansa's
  `binding` is now the device side over it. The roster rows are in
  factbond's evidence policy.
- **R6: notices before claims** (2026-09-29; `counterparty-gate.md` §6).
  `notice.py`: a claimant's `notice/<loop>/<offer>` sealed to the giver
  and the giver's `cure/<loop>/<offer>` sealed back, each beside a salted
  commitment to its plaintext (`sealed`, `read`, `opens`), in factbond's
  `Notice`/`Cure` shape (`notice_record`, `cure_record`);
  `OfferRegistry.send_notice`/`send_cure`/`notice`/`cure`; the fold admits
  each only as its writer's own speech. A cured matter leaves nothing
  readable in public (factbond THREATS T17); a claim discloses the opening
  and anyone checks it. `lapsed` is the watch's re-check for a relied-on
  statement revoked or suspended since clearing. The clocks are factbond's
  procedure; `loop watch` does not run the re-check yet.
- **R4: the counterparty gate** (2026-09-29; `counterparty-gate.md` §4).
  `gate.CounterpartyGate` checks each `requires.counterparty` credential
  against the statements the other side presented (`cred/`), under the
  pinned registers: category and kind; a path through `accredit/` to a
  named trust root, every register on it pinned; not revoked; each
  register fresh (`Register.heartbeat`, within `max_root_age`); valid
  through the handover window; a named deposit's free share after this
  fill's reservation covering `min_bond` at the requirer's price; not
  suspended. `faults` returns every failing step (plan E4) and clearing's
  refusal lists them. `meets`, `_gates`, the `check_*` functions and the
  candidate generators take `gate=`; `SolverAgent(registers=, span=)`
  builds it over its snapshot and pins every register;
  `MockClearing(register_at=, span=)` re-reads the pinned roots (U3).
  `rehearse` now also consults the clearing's `escrow_held`. The dentist
  case passes and clears in memory (`tests/test_gate.py`), and each
  failure is refused with its step named.
- **R3a: registers, separately rooted and pinned** (2026-09-29;
  `counterparty-gate.md` §3.3). `register.Register` over its own store:
  `status/`, `revoked/` (monotone; absence under a pinned root is a proof
  anyone verifies), `suspended/` (`reinstate` clears it), `accredit/`
  with `scheme`. The announcement channel carries a third role,
  `register` (uint8 2 on chain; the contract emits it unread), and the
  aggregator records a register's root in the announcement set without
  folding it. `LoopProposal.register_roots` pins every register a leg's
  requirement names (`named_registers`); the loop record carries them as
  its v2 (v1, without pins, is unchanged); `MockClearing` refuses a
  proposal missing one before any leg work, and the challenger's reader
  takes v2. The chain half (R3b) waits for the clearing-contract redeploy.
- **R2: the `cred/` sidecar** (2026-09-29; `counterparty-gate.md` §3.2).
  `OfferRegistry.present(statement, presentation)` writes
  `cred/<subject>/<statement id>` beside `sig/` and `handoff/`;
  `statements(subject)` reads them. The fold admits a presentation only in
  its subject's own maker book under the statement's own content address,
  and rejects every other with attributed provenance (U8): a statement
  about another key, a mis-addressed or unreadable record, a presentation
  outside a maker book. Whether a statement is true is R4's gate.
- **E2: the claim period and the resolver per leg** (2026-09-29, on the
  v6 record). `escrow.reservations_for` takes the leg's claim period —
  the want's `claim_period`, else `escrow_claim`, never beyond the give's
  `claim_max` — refuses a resolver who is a party to the leg (C4's
  formality) or outside the want's `resolvers`, and marks cover through
  `cover_predicate` (a give under the catalogue's `insure`). `meets`
  admits a `resolvers` acceptance by key (`matching.admits`; roots and
  floors fail closed until R3/R4). CLI settings `arbitrator`, `claim_max`,
  `require_claim`, `require_resolvers`, `claim_min_challenge`,
  `claim_min_ruling`; the render shows the v6 fields. `LoopEscrow.reserve`
  refuses a resolver who is the wanter or the depositor and `assign`
  refuses the resolver (source and artifact; not deployed).
- **The v6 record** (2026-09-29, R1; `docs/plans/counterparty-gate.md` §1–§2,
  `options-and-cover.md` §3.1, one bump as decided in D7). `Requires` gains
  `counterparty` (`Credential`: category, kinds, `min_bond`, trust
  `roots`, `max_root_age`), `legs` (`RequiredLeg`: category, `Accept`),
  `resolvers` (`Accept`: keys or accrediting roots, floors on deposit,
  look-back without reversal, issuance source; never a count) and
  `claim_period`, the want's ask in the matched claim period; an offer
  gains `claim_max` (a give's) and an option's `underlying` and
  `exercise`; `Statement` is the one statement shape (subject, category,
  issuer, kind, validity, evidence, path, `paid_by`, deposit, scheme,
  issuance), content addressed. Any v6 field selects v6; a v4/v5 corpus
  keeps the ids the previous code computed. Fail closed until the gates
  exist: a credential, a required leg or a resolver acceptance meets
  nothing (R4), an option clears nowhere (C2); a claim period is met by a
  give whose `claim_max` reaches it. `requires.claim_period` is the one
  field the decided list did not name: plan A1's "the want asks for at
  most that" needs a place, and a later bump for it would break "one v6
  bump".


- **Plans: credentials, cover and options** (2026-09-25). Five documents
  entered the plan corpus from the assurance drafts:
  `docs/plans/credentials-cover-and-options.md` (the cross-repository
  plan: ten decisions, a shared vocabulary, stated divergences from
  commercial practice, the fold-in map), `counterparty-gate.md`,
  `options-and-cover.md`, `items-and-ownership.md` and
  `commercial-practice-review.md`. Existing plans amended by dated edit:
  P3-guarantee-coupling §3 rule 1, §4a (the per-item NFT note overruled)
  and §4b items 2–3 (the v6 `credentials` field superseded by the `cred/`
  sidecar), P2-loop-selection §4a (open decisions (a) and (d) answered),
  P3-release-and-reclearing §8 (options and cover under the ladder and the
  escrow), P4-privacy §8, THREATS T15–T16 and a closed-items note, ROADMAP
  P3b, CLAUDE.md's planned extensions, and the README's disclaimer.
  ROADMAP's "factbond as the resolver" item marked done (live since
  2026-09-19).

### Changed

- **`default_asset` has no default price** (2026-09-29, Peter). A bare
  amount on my scale — `bond 5`, a `require_point` with no
  `require_accepts` — is converted at my own price for an asset, so it is
  refused until `set default_asset 'xdai xDAI PRICE'` states it; before, the
  CLI assumed xDAI at 1 per scale unit. Every amount stays on the maker's
  scale, converted once at posting at the maker's own price.
- **`recordstore>=0.21.0`** (2026-09-29): the release with extension proofs
  and a feed's verifiable sequence of roots, which a register's checked
  root sequence (R5) needs; the tests that skipped without it now run.
- **Docs** (2026-09-29): the user guide gains options (§7.3), items (§7.4)
  and credentials (§7.5), the current Gnosis addresses (§11.1) and the
  `chain`/`evm` extras; the reference gains the v6 record, `Statement`, the
  gate, registers, items, the door's witnesses and notices, the new
  keyspace and the escrow's E1 acts; the README's status and plan table and
  an ARCHITECTURE update note follow.


- **`LoopEscrow`: the parties' four acts and the claim read at `hold`**
  (2026-09-28, E1 of the development sequence of 2026-09-25; local EVM,
  not yet deployed). `reserve` takes a `Terms` tuple (window, claim
  seconds, `minChallenge`, `minRuling`, `claimOnly`); a `claimOnly`
  reservation (cover) refuses `countersign`; `assign(offer, loop, to)` by
  the wanter to any key, not while a claim is open; `settle(offer, loop,
  toWanter)` settles at a split once the wanter and the giver have each
  signed it, held and cover reservations included; `extendClaim` by the
  giver, only longer. With a contract resolver, `hold` reads the claim
  and opens only the wanter's own, naming the giver as `about`, a payout
  above 0 and within the reservation, windows no shorter than the
  reservation's, one at a time; a retraction reopens the reservation; a
  close after the parties settled moves nothing; a settlement payout the
  recipient refuses is credited to `owed` for `collect`. `EscrowClient`
  gains `assign`, `settle(to_wanter=)`, `extend_claim`, `collect`, `owed`
  and the terms in `reservation`; `reservations_for` takes `claim_only`,
  `min_challenge`, `min_ruling` (none set by the CLI yet: E2 reads them
  from v6). The shipped artifact is rebuilt; the other three are
  unchanged.

### Fixed

- **A door requirement clears on chain** (2026-10-01, Peter's decision 11).
  `require_door possession` wrote the level's name,
  `door-at-least-possession`, which the off-chain gate expands but the
  on-chain verifier compares by exact name, so an honest leg against a
  give declaring `possession` was refused and `ChainClearing` never posted
  it. The record now lists the types the level stands for
  (`photo-match`, `possession`; `photo` writes `photo-match`), the
  approval block still says "door at least possession", and
  `accepted_types` still reads a level's name. A want lists today's types
  and lapses with its validity; a new door type joins `DOOR_LEVELS`, and
  later wants list it. Pinned on a local EVM
  (`tests/test_loop_verifier.py`, beside `registry-transfer(ID)`).
- **A leg too large to verify in one call is never posted** (2026-09-29).
  The dry run now tells a revert without a reason — the verification
  running out of gas — from a node refusing the call: `OUT_OF_GAS`, which
  `ChainClearing` refuses before the bond and a challenger never counts as
  a conviction. Earlier the same day an empty revert had become "no
  verdict", which let such a leg through.
- **The escrow is the authority on aggregated and composed legs too**
  (2026-09-29). The held rule of 2026-09-19 (a deposit naming an escrow
  counts only up to what the contract holds) reached `check_match` and
  `check_parts` but not `check_aggregate`, the pool of `aggregate_legs`, or
  the operator gives of `check_composition`: there a declared, never-funded
  deposit still met a counterparty's point. Every share and operator is
  now gated with `held`.


- **The settings table named six settings twice** (2026-09-23). An older
  copy of `maker`, `terms`, `valid`, `bond`, `require_bond` and
  `require_cancel` sat below the current ones, and a Python dict keeps the
  last of two equal keys silently: `bond` and `require_cancel` showed their
  pre-v5 help ("in the bond's asset", "at most require_bond"), and the
  retired `require_bond` — read by nothing since the accepted v5 record —
  was still accepted. The stale copy is gone, `set require_bond` is refused
  as unknown, and a test fails if a setting is ever named twice.

### Security

- **THREATS T18: claim hijack at the escrow's consumer edge** (found
  2026-09-28 while building E1, confirmed on a local EVM). Anyone could
  void a reservation whose resolver is factbond's `Assertions` by
  asserting a claim on it and retracting it at once: the retraction's
  outcome 0 refunded the giver, bypassing the claim and the cancellation
  ladder, for the assertion fee. A claim above the reservation could never
  certify, and a recipient refusing payment could block any settlement,
  a ruling's included. Closed in the contract source above; the Gnosis
  pair (`0x299CE4…69Bf` with `0xfa6f…BF99`) keeps the hole until the E3
  redeploy.

### Documentation

- **The documentation checked against the code for the release**
  (2026-10-01). The User Guide's tutorial (§2–§7) runs as written again:
  the shared catalogue in its own file (`odag -f market.od …`, `loop set
  catalogue market.od`) so places stay private and publish as their cell,
  bare place and `time(…)` terms where the retired `where(…)`/`when(…)`
  heads stood, outputs recaptured from a scratch home, the Python
  snippets exact (`Fraction`s) and run in order; §7.2 on who rules (the
  default arbitrator, factbond's ladder as the option, the deductible as
  each resolver applies it), §8's federation through the `registry`
  setting, §9's seats with a step and a floor and published composed
  wants, §11's Swarm setup and TTL note. The Reference Manual gains the
  announcement channel, arbitrators, cases and the reputation view, the
  current signatures (`Offer`, `check_match`, `MockClearing`,
  `ChainClearing`, `SolverAgent`, `selection`, the registry's sidecars),
  the fold's admission table, the `key/`, `case/` and `auction/` keys, U9,
  and the CLI's step/floor grammar; README and ARCHITECTURE say what is
  built at 0.13.0. `loop announce --role register` is accepted.
- **factbond's documentation is factbond's** (2026-09-28): what was a
  second copy of factbond material now points to factbond. The
  cross-repository plan `docs/plans/credentials-cover-and-options.md`
  becomes an index (which decisions are carried out here, where) linking
  factbond's single full text; the threat register's factbond-primary
  entries (T4–T6, T9–T13) become stubs holding loopmarket's own part and
  a link, under a revised content-sync rule; `P3-guarantee-coupling.md`
  §4 keeps the oracle roster's table and its enforcement rules and links
  factbond's `evidence-policy.md` §3 for the rulings, and §8 points to
  factbond's `loopmarket-coupling.md` §5 for the coupling's sequencing;
  the User Guide (§7) and the Roadmap mention factbond's contested-claim
  procedure and changes briefly and link factbond's new User Guide and
  Roadmap. factbond's register does the reverse for this register's
  primaries, so every threat entry has one full copy.

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
