# loopmarket — the command line (P1 tooling)

Status: design, 2026-09-11 (settled in discussion with Peter; nothing
built). Decided here: the CLI lives *in the package* as `loop`, a sibling
of ontodag's `odag`, lifted from it where the code is generic; its grammar
is ontodag's grammar with exactly two loopmarket-only conventions (a bare
number first is the quantity, a bare number last is the price); every
name that describes the world — including "my home" — is a catalogue
node, never a CLI alias; settings live in a config file that shares
odag's format and inherits odag's; an omitted price is the maker's own
last unit price for the same thing; a bare quantity takes the direction
its role implies (a want is a floor, a capacity is a ceiling) and the
approval block says so in words; **quantity tolerance is not a protocol
concept** — it is a settlement norm per leg and category, and the rule
"declare in the direction you know" replaces any tolerance parameter;
nothing is published before the fully resolved offer is displayed and
approved. Open here: the binary's name, the confirmation rule in batch
mode, the upstream asks in §11, and everything the v3 record bump owns.

This document is the design CLAUDE.md's roadmap now points at for the
command line; it is *tooling*, not protocol — no invariant changes, and no
paragraph below adds matching or clearing semantics. Companions:
`ontodag-coupling.md` (§2 spacetime terms, §3 quantities as terms — the
two schema steps the grammar is written ahead of), `P2-loop-selection.md`
(integer granularity, the one quantity question that *is* a record
question), `P3-guarantee-coupling.md` (where over-delivery disputes land),
`P4-privacy.md` (publishing private place names).

## 1. Why in the package, and what it is for

Three reasons, in order of weight:

- **The boundaries hold for free.** argparse and shlex are stdlib. Swarm
  stays a lazy import inside the `swarm:` store path, so B1 and B2 cover
  the CLI as they cover the model, and `tests/test_boundaries.py` keeps
  guarding both.
- **Versions stay in step.** The CLI encodes offers through `to_record`
  and must move with every record bump. A separate wrapper would pin
  loopmarket independently and drift.
- **It is the demo.** `examples/demo_triangle.py` is ninety lines of
  Python; as a batch script it is twelve lines (§8). The user guide and
  the talk shorten with it.

What to lift from `ontodag/__main__.py`, attributed in the module
docstring: the settings table with its single precedence rule, the config
reader/writer with the 0600 handling, the stdin batch and REPL runner, the
tty-versus-pipe rendering switch. About 250 lines. odag's *private*
helpers are not imported — they churn — with one exception noted in §11:
opening a catalogue from an odag store spec should be a public ontodag
call, not a copy of `_load_native`.

Layout: `src/loopmarket/cli.py` (parsing, dispatch, rendering) and a
two-line `src/loopmarket/__main__.py` so `python -m loopmarket` works;
console scripts `loop` and `loopmarket` (§Open problems on the name); a
`loop-mcp` sibling later (§10).

**Job description.** The CLI is the contract between whatever talks to a
human — a person at a prompt, a shell script, an assistant — and the
strict protocol beneath. The protocol stays strict and dumb (points,
bands, unknown vocabulary fails closed). The CLI adds *deterministic*
kindness: defaults, the price memory, the direction rule, the approval
block — every one of them a small tested rule printed in words. Judgement
(asking a grower how precisely they weigh, noticing every courier in town
caps at 10 kg) lives above the CLI, in a person or an assistant, and never
below it. This is the same position solvers hold: outside the trust
boundary, proposing, never verifying.

## 2. Grammar: ontodag's, plus two conventions

The house rule, Peter 2026-09-11: *keep the ontodag and loopmarket syntax
as close as possible and deviate only when absolutely necessary* — two
grammars would be the confusing part. So a token after the verb is one of
three things:

- **A bare word is a category.** `apple`, `ride`, `piano-lesson`,
  `my_home` (§4). Nothing bare is ever reserved.
- **`head(param)` is a term**, in ontodag's canonical spelling —
  `weight(10kg..10.5kg)`, `time(2026-10-01..2026-12-31)`,
  `from(my_home)`, `valid(2h)`. Quoted in a shell exactly as odag's own
  help says ("quote the parentheses in a shell"); unquoted at the `loop`
  prompt and in batch scripts. A `key=value` spelling was proposed and
  **rejected** on 2026-09-11 for being a second grammar; if a shell-safe
  spelling is ever wanted it lands upstream (§11) and loopmarket follows.
- **A bare number first is the quantity, a bare number last is the
  price.** `give 10kg apple 100`; `give apple 100`; `give apple` (§5).
  odag has neither concept, so these are the only deviations; the long
  forms `weight(10kg)` and an explicit price are always accepted, so
  anything valid at the odag prompt is valid here.

```
loop give 10kg apple 100
loop want ride 'from(my_home)' 'to(my_supermarket)' 'when(today)' 5
loop give piano-lesson 'valid(2h)'
loop give apple                      # 1 unit, last apple price, all defaults
```

**Heads the CLI interprets today.** Until `ontodag-coupling.md` §2 lands,
`Offer` still has a `service` window and a `where` disc as fields, so
three heads map onto fields rather than into the conjunction: `when(...)`
→ `service`, `where(...)` → `where`, `valid(...)` → `valid`. Every other
head passes through into `Thing.concepts` as a catalogue term. When §2
lands, `when`/`where` become ordinary catalogue heads with the same names
and the mapping code is deleted with nothing changing at the prompt.
A startup test asserts the interpreted heads are disjoint from the
dimension heads the loaded catalogue declares, so a future pack cannot
silently shadow one.

**Relative time is input vocabulary.** `valid(2h)`, `when(today..+90d)`
elaborate to fixed ISO-8601 UTC at entry — the coupling plan's rule that
"timezones elaborate at creation" applied to durations too. Stored terms
are absolute; the approval block shows both UTC and local. This is a
*superset* of odag's time grammar, not a conflict; §11 asks whether
upstream wants the same spellings so the superset disappears.

**Verbs stay explicit.** A bare thing with no `give`/`want` is an error,
not a default want: the two are opposite obligations.

## 3. Settings: odag's rule, odag's file, odag's inheritance

Every setting resolves by one rule, odag's — **flag > environment >
config > default** — and is settable four ways: one dashed flag per
setting *before* the command (`loop --maker bruno give ...`,
`loop -f rs:~/other < script.loop`), an environment variable (`LOOP_*`,
with `BEE_*` shared), `set KEY VALUE` (durable), the default. `set` with no
key lists everything; with a key shows it; unknown keys are errors
(fails closed — no aliases hide here, §4). Secrets print masked.

| setting | meaning | default |
|---|---|---|
| `book` | my writable book: `rs:PATH` or `swarm:TOPIC` | `rs:~/.loopmarket/book` |
| `catalogue` | the ontodag store spec offers pin (any odag spec) | odag's active store |
| `peers` | read-only maker books / manifests folded into every answer | none |
| `maker` | my identity; the signer's address when `sig` is installed | none — required to publish |
| `where` | default place term (a catalogue node, §4) | none — required |
| `when` | default service window (relative or absolute) | `..+90d` |
| `valid` | how long my offers stand | `30d` |
| `now` | the clock, for reproducible runs and tests | wall clock |
| `confirm` | `auto` / `on` / `off` (§7) | `auto` |
| `render`, `limit` | as odag: readable at a tty, raw in a pipe | `auto` |
| `bee_api`, `bee_batch`, `bee_signer` | as odag; `bee_signer` secret | inherited |

**Not in the catalogue, and why.** Peter asked whether settings could live
in ontodag too. Three reasons they cannot, each decisive: `bee_signer` is
a private key and a content-addressed store never forgets a blob; the
setting that names which catalogue to open cannot live inside it; and
changing my default validity must not move a catalogue root that every
offer pins. odag reached the same conclusion for its own settings.

**One system with odag's config instead.** Same `key = value` file
format, same `set` semantics, and loopmarket reads `~/.ontodag/config` as
a fallback layer for the settings the two share: configure the Bee node
once in odag and `loop` inherits `bee_api`, `bee_batch`, `bee_signer`,
and odag's active store becomes the default `catalogue`. Precedence:
flag > env > loop config > odag config > default. `peers` is the twin of
odag's `overlays` — read-only stores merged into every answer is exactly
what `Aggregator.fold` does.

## 4. Names live in the catalogue

"Why is it not ontodag's job to know where my_home is?" (Peter,
2026-09-11). It is. A place is vocabulary; vocabulary has a persistent
store, overlays, history and pinned roots already; a names table in a
loopmarket config file would be a second, weaker knowledge store beside
it. So there is no alias mechanism in the CLI at all, `set` stays
fail-closed, and `my_home` is a bare word like any other.

- **Time names need nothing from loopmarket.** `odag put evenings
  'time(2026-09-11T18:00:00Z..2026-09-11T21:00:00Z)'` works today and
  `want piano-lesson 'when(evenings)'` is then an ordinary term whose
  containment ontodag computes. This is the test that the principle is
  right.
- **Places need one thing from upstream** (§11): a coordinate input
  spelling for the prelude's `geo` head, so `odag put my_home
  'geo(46.0553356,14.5053221,10m)'` canonicalises to a cell at the
  precision the radius implies — the same device as `24C` becoming
  kelvin, input vocabulary that never appears in stored names. Geohash
  is exact bit interleaving on rationals; the determinism doctrine
  admits it. **Meanwhile:** a temporary `loop place NAME LAT,LON,R`
  writes the node through the `Ontology` facade and is deleted the day
  odag accepts coordinates.
- **What the offer carries, today.** The exact geo truth is
  `GeoDisc.intersects` and discs are barred from the catalogue, so for
  P0 the place node carries its disc as node metadata beside its cell
  edge; at publish time the CLI reads that value and encodes it into the
  offer's disc field. *The offer carries coordinates, ontodag carries
  the name.* When §2 of the coupling plan lands the field goes and the
  offer references the node.

**The same-root constraint.** `check_match` refuses offers pinned to
different catalogue roots, so a name that *appears in an offer* must be
in the shared catalogue, not only in my layer. §6 of the coupling plan
already admits region nodes; catalogue federation is not built. For P0
the resolution above sidesteps it — a private name resolves to a
shared-vocabulary *value* before encoding and the shared root is
untouched. Publishing `my_home` itself as a public region node is the
later step and a `P4-privacy.md` question (plaintext offers already leak
the disc today, so it is a naming leak, not a new one).

## 5. An omitted price is my last unit price

`give 5kg apple` reuses the maker's own previous price. Three
refinements make that safe:

- **Key = side + bare categories.** A give and a want for the same thing
  are different prices, so the lookup is by verb and by the sorted
  *non-parametric* concepts; parametric terms (`time(...)`, `from(...)`)
  are ignored, since a `time` that changes on every offer would otherwise
  defeat the memory. Broader or narrower categories are never consulted —
  that would be guessing.
- **Unit price, scaled.** Offers store the lot price, but `Match.rate`
  already divides through to unit prices; the memory stores the unit
  price and multiplies by the new quantity, so `give 10kg apple 100` then
  `give 5kg apple` means 50.
- **The book is the memory.** No price file. The latest offer by *me*
  with that key — live, filled or withdrawn — is the previous price;
  deterministic, moves with the book, and strictly on my own scale.
  Peers' numbers are on other scales and must never leak into a default.
  No earlier offer ⇒ an error, not a guess.

A reused price is exactly where a stale number slips in, so the approval
block (§7) marks it: *price 50, unit price 10/kg from offer 3f9a… (3 days
ago)*.

## 6. Quantities: declare in the direction you know

The question started as "does `10kg` mean infinite precision?" and ended
somewhere more useful. The record of the argument, because it will be
re-asked:

1. *A point is exact, and real quantities are not.* True, but today's
   matching already reads a **give** quantity as a capacity when the good
   is divisible (`w.qty ≤ g.qty`); only indivisible lots compare exactly,
   which is right for one bicycle or one lesson.
2. *10 kg of apples is 10 kg if both sides agree.* Nobody arbitrates over
   10.1 kg; 9.8 kg may be disputed. **Precision belongs to the category,
   not the number** — apples trade by commercial weight, a calibration
   mass is a different good — and tolerance is a **settlement norm**
   (P3: oracle, arbitrator, factbond adjudication), never a matching
   parameter. Matching and clearing stay exact on the number (U5, U6).
3. *But 10.4 kg is fine for the recipient and not for the courier.*
   Two kinds of leg read the same number oppositely: for a consumer the
   quantity is a **floor**, for a service whose input is the good
   (transport, storage, processing) it is a **ceiling** — a capacity, or
   the work that was priced. The principle from (2) survives *per leg*:
   the apple leg is judged by apple custom, the transport leg by
   transport custom. The clash appears only when one object satisfies
   two legs — the composed want of `P2-loop-selection.md` §10.
   Over-delivery is free only where nothing downstream depends on the
   number; where it does, the grower's rounding becomes the recipient's
   misdeclaration to the courier, and **recourse follows the legs**
   (courier → recipient → grower), which is how contracts already work
   and what factbond would see: two disputes, two legs, one cause.
4. *Should the recipient then order transport with leeway, `..11kg`?*
   Case-dependent and guessy. The resolution: **each party declares only
   the direction they know**, and containment composes.
   - the grower knows the variability: `give apple 'weight(10kg..10.5kg)'`
     (10 nominal, never more than 10.5; a precise grower declares a point);
   - the recipient knows their floor: `weight(10kg..)`;
   - the courier knows their ceiling: `weight(..11kg)`.
   Nobody invents leeway for anyone else; the solver checks the grower's
   band ⊑ the recipient's floor and ⊑ the courier's ceiling by
   containment on stored names — exact, deterministic. No courier whose
   ceiling holds the band ⇒ no match, which is the truth rather than a
   dispute waiting to happen. Case-dependence lives in offers, priced by
   the market (a `..11kg` courier at a `..10kg` price is *selling* the
   leeway) — which is how logistics prices already: weight bands, one
   offer per band, the user guide's one-offer-per-seat pattern.

**Decision: no tolerance parameter, no default band, ever.** An implicit
band would make a want quietly match a different amount than typed —
the class of mistake the approval block exists to catch.

**The direction rule (deterministic, CLI-side).** Real people type
"10 kg". The direction a bare quantity takes is derivable from the verb,
the unit's kind and whether the category is a good or a capacity service
(the last is catalogue knowledge: an edge under a kind node, read by the
CLI and by anything above it):

| spelling | side | reading printed | encodable today |
|---|---|---|---|
| `10kg` on a good | give | up to 10 kg, divisible | yes (qty 10, divisible) |
| `3` on `bicycle` | give | 3, indivisible | yes; 2 of 3 is not a partial fill |
| `10kg` on a good | want | at least 10 kg | **no** — encoded as the point 10 kg, printed as such |
| `10kg` on a capacity service | give | up to 10 kg | as divisible capacity |
| `9kg..11kg`, `10kg..`, `..11kg` | any | band / floor / ceiling | **no** |
| `10kg..` on a give | give | minimum order quantity | **no** |

The band spellings are accepted (they are the grammar) and **refused at
publish time** with the point spelling named as the fallback, until
`ontodag-coupling.md` §3 makes quantities unit-family terms — at which
point quantity overlap is the same overlap-shaped gate as time windows,
with the cleared amount a point in the intersection chosen by clearing
(P2 flow). Until then the approval block prints the *reading* — "up to
10 kg, divisible", "10 kg" — so the default is visible before yes.

Integer granularity (1,000 apples by the apple; 2 of 3 bicycles) is the
one quantity question that is a record question; it is owned by
`P2-loop-selection.md` ("DECISION REQUIRED before the v3 record bump")
and not re-decided here.

## 7. Nothing publishes unseen

Every `give` and `want` renders the fully resolved offer before anything
is written, through the same renderer `show ID` uses later — what you
approved is what the book displays. Resolved means every default and
shorthand expanded:

- side, maker, quantity with its *reading* (§6), unit, the sorted
  conjunction with each parametric term in canonical spelling;
- price and unit price, marked when reused, with the source offer's id
  and age (§5);
- service window and validity as absolute UTC **and** local time —
  relative spellings and time zones are where mistakes hide;
- the place with coordinates and radius as read from the catalogue node,
  so a stale `my_home` is visible;
- catalogue root (prefix), registry and contract versions, bond, oracle,
  arbitrator, and the `offer_id` it will receive.

Then `publish? [y/N]`, default no. The `confirm` setting follows odag's
`auto` pattern: at a terminal it asks; in a batch it prints the same
block and proceeds (the script author wrote the lines); `confirm on`
forces the question even in a batch — the safe choice when a script
relies on reused prices; `confirm off` is for tests and demos. By
exception to odag's silent-on-success rule the command prints the new
id: publishing is a commitment, and the id is what `withdraw` needs.

## 8. Streams: three uses, no more

1. **Batch on stdin.** No command ⇒ read commands from a pipe, or open a
   prompt on a tty (odag's mode). The triangle demo as a script over the
   shared dev/demo book (`set maker` is durable, as odag's `set` is — a
   demo-book convenience, not the federated shape):

   ```
   set where my_home
   set maker amara
   give piano-lesson 100
   want produce local weekly 104
   set maker bruno
   give vegetable-box 50
   want bicycle-repair 52
   set maker chen
   give bicycle-repair 80
   want music-lesson 83
   loops
   clear
   ```
2. **Record streams.** `export`/`import` move offers as JSON lines of
   their canonical records (ids survive: `to_record` encodes natively);
   `offers` prints a table at a tty and tab-separated lines in a pipe.
3. **Exit codes as predicates.** `loops` exits 1 when nothing is
   profitable, so `loop loops && loop clear` reads naturally (odag's
   `below`).

The book itself is never piped — a book is a root over a blob store, and
`-f`/`set book` selects it. `-o FILE` exists only because the REPL has no
shell redirect.

## 9. Commands, by the role a person is playing

| role | commands |
|---|---|
| maker | `give`, `want`, `withdraw ID`, `mine`, `place NAME LAT,LON,R` (temporary, §4) |
| anyone reading | `offers [CATEGORY...]` (filtered through `satisfies`), `show ID`, `matches`, `status` (roots, counts, settings in force) |
| solver | `loops` (find on a pinned snapshot, print, never clear), `propose` |
| clearing / aggregator | `clear` (local `MockClearing` over the fold — "you are running the clearing house"), `fold` (write a manifest), `audit MANIFEST` (T14 absence proofs) |
| plumbing | `set`, `export`, `import`, `help`, `--version` |

One binary for all roles keeps P0 runnable end to end from one machine;
odag split `odag-mcp`/`odag-web` out only when they carried different
dependencies, and the same rule applies here (§10).

## 10. Assistants sit above the contract

Real users will type "10 kg" and nothing else; some of the watching is
mechanical (§6's direction rule, §7's block) and belongs in the CLI; the
rest is conversation and belongs to an assistant. Two constraints keep
that safe: an assistant produces the same command lines (or the same
Python calls — Peter, 2026-09-11: it can use the API directly) a human
would, so every offer it drafts is reproducible and auditable as text;
and it never bypasses the approval block — the assistant types, the human
approves, and the block is identical whichever typed the line. An
assistant wrong about a courier costs one rejected match; an assistant
inside matching or clearing would cost determinism. `loop-mcp`, shaped
like `odag-mcp` (every answer cites its root; errors teach; failed calls
logged as tripwire evidence), comes after `loop` exists — the assistant
needs the contract before it can speak it. Deferred by Peter on
2026-09-11: "let's leave that for later".

## 11. Upstream asks (ontodag), in priority order

Filed into `ontodag-coupling.md` §7's tripwire table the same day; none
blocks `loop` shipping, each removes a loopmarket-only behaviour.

1. **Coordinate input spelling for `geo`.** `geo(LAT,LON,R)` → a cell at
   the precision the radius implies; input vocabulary only (D10 shape),
   exact on rationals. Removes `loop place` (§4).
2. **Relative time spellings in `time(...)`.** `today`, `+2h`, `..+90d`,
   elaborated to fixed UTC at input. Removes §2's superset.
3. **A public opener for store specs.** `ontodag.open(spec)` or similar
   over `.od` / `rs:` / `swarm:` so loopmarket's `catalogue` setting
   resolves through public API rather than a copy of `_load_native`.
4. **(Optional) a shell-safe term spelling**, e.g. `head=param` as an
   input-only alias of `head(param)`, canonical rendering unchanged.
   Only if odag wants it for itself; loopmarket adds no spelling alone
   (§2). Peter, 2026-09-11: syntax changes upstream are possible now
   ("people only look at demos yet").

## Gates

- **G1 — the triangle as text.** `loop < examples/triangle.loop` with
  `confirm off` finds and clears one loop with the same `loop_id` the
  Python demo produces (U6 through the CLI).
- **G2 — one grammar.** Fuzz: every canonical ontodag term round-trips
  through the `loop` tokenizer unchanged (`elaborate(render(t)) == t`
  holds across the boundary); every odag prompt line that is a query is
  accepted or rejected for the same reason at the `loop` prompt.
- **G3 — boundaries.** `import loopmarket.cli` under
  `tests/test_boundaries.py`: no network, no optional dependency.
- **G4 — approve = show.** The approval block and `show ID` are one
  renderer, byte-identical for the same offer.
- **G5 — nothing reserved.** A generated catalogue whose category names
  equal every setting name and every interpreted head still parses in
  bare position; the interpreted-head/dimension-head disjointness check
  fires on a constructed collision.
- **G6 — bands refuse.** Every band spelling in §6's table is accepted by
  the parser and refused at publish with the point fallback named, until
  the v3 bump flips the table.

## Open problems

- **The binary's name.** `loop` proposed (short, reads as the sentence
  "loop give apple 100"); collision audit against common distributions
  not done; `lm` is opaque; `loopmarket` stays as the long alias either
  way. Unconfirmed by Peter.
- **Confirmation in batch mode with reused prices.** `auto` proceeds in a
  batch; a script that omits prices therefore publishes numbers its
  author never saw. Whether `auto` should mean *ask if any price was
  reused* is undecided.
- **Private names under the same-root rule.** §4's value-resolution
  sidestep works for places (a disc value) and times (a term); a private
  *category* has no value to resolve to and simply cannot appear in an
  offer until catalogue federation or pin agility exists
  (`ontodag-coupling.md`, open problems).
- **Direction rule inputs.** "Good vs capacity service" is catalogue
  knowledge; which kind node carries it, and whether the core pack
  already implies it (`service` there is the *financial* sense), is for
  `catalogue-bootstrap.md`.
- **Anchoring as an offer term.** If `P1-federated-book.md` §4a's
  maker-optional anchoring is adopted, a give or want carries an
  `anchor(...)` term, the approval block shows the transaction the wallet
  will sign, and the reused-price and direction readings appear on the
  device's typed-data display (EIP-712) rather than only on screen.
- **Which commands ship first.** Maker + reader + `loops`/`clear` is the
  minimum for G1; `fold`/`audit`/`propose` follow the federation demo.

## What this document does not promise

No matching or clearing semantics change: the CLI encodes only what the
schema holds, refuses the rest loudly, and never scales, rounds or
tolerates a quantity. No name resolution happens outside the catalogue,
and no setting ever enters it. No assistant, and no CLI rule, sits inside
U3's re-verification. The CLI does not replace `odag` for catalogue
editing — the temporary `place` bridge is the single exception, dated and
deletable. And the grammar is written *ahead* of two schema steps
(spacetime terms, quantities as terms): until those land, several
spellings this document shows are accepted and refused, not silently
approximated.
