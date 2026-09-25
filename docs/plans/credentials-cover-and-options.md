# loopmarket — credentials, cover and options: the cross-repository plan

Status: design, entered loopmarket's plan corpus 2026-09-25. This is the
cross-repository plan agreed in the assurance drafts (consolidated
2026-09-25); factbond, ontodag and the assurance repository carry the
same decisions from their side. loopmarket's detailed designs are
`options-and-cover.md`, `items-and-ownership.md` and
`counterparty-gate.md`; the practice record it was checked against is
`commercial-practice-review.md`. It resolves the
problems the review of 2026-09-25 (in the assurance drafts) §2 and §3 found in the 2026-09-23 drafts,
one decision per problem, and it incorporates the twelve decisions Peter
took on 2026-09-25: six on the plan's own open items and six families of
amendments from `commercial-practice-review.md`. The round-by-round record
of how each decision was reached is in the amended plan (in the assurance drafts);
this file states only the result. The drafts' bodies already carry every
decision, marked *(applied plan …)*; the labels A1–A5, B1–B5, C1–C5,
D-1–D-5, E1–E4, F1–F8, G1–G5 used there are kept here as the names of the
sub-decisions they cite.

The plan is written to be split by repository: §4 says which plan document
in which repository receives each part. The drafts remain the detailed
design; where this plan and a draft disagree, this plan wins until it is
folded in, then the repository's plan corpus wins. Compliance with any
jurisdiction's law is the makers' concern (D10); the standard the plan holds
itself to is good commercial practice.

## 0. What this plan optimises for

Four rules, in order:

1. **Nothing new where the corpus already has the mechanism.** Reservations,
   the cancellation ladder, the escrow's deposit shape, factbond's evidence
   policy and calibration ledger, ontodag's kinds. Several of the drafts'
   proposals turned out to be re-inventions; each such case is resolved by
   naming the existing mechanism.
2. **No unpriced lock, no free option.** Every exclusivity, hold or claim
   costs its holder something proportional to what it denies others. This
   is the rule the item rule, the void withdrawal, the burden shift and the
   wanter-chosen claim period all broke.
3. **Money moves only on a ruling or a clean settlement**, never by default.
   factbond's 2026-09-19 escalation decision, kept and extended.
4. **Every step has a clock, and lapse has a stated consequence.** The
   claimant's notice and claim, the asserter's evidence, the adjudicator's
   ruling and each escalation rung all run against a fixed period, and what
   happens at lapse is written down in advance. Practice's most consistent
   lesson, from UCP's five banking days to the dispute board's 84.

## 1. Shared vocabulary

These words mean the same thing in every repository after this plan. Where
a draft used a word differently, the draft changes.

| word | meaning | not to be used for |
|---|---|---|
| **deposit** | a `Bond` on a v5 give: the giver's own collateral in `LoopEscrow`, reserved per fill | the financial instrument (`bond → security-finance` in the catalogue) |
| **reservation** | the per-fill share of a deposit, with its window, claim period and resolver | an option (see *option record*) |
| **claim period** | `LoopEscrow`'s per-reservation `claimSeconds` after the window: how long a wanter may still open a claim; a matched term with a catalogue default and cap (D1) | factbond's challenge window |
| **challenge window** | factbond's per-assertion liveness: how long a dispute may be opened on an assertion | the claim period |
| **notice** | `notice/<loop>/<offer>`: a timestamped record from one party to another; with a cure deadline it is rung zero of every claim (D2) | a dispute |
| **hold** | the escrow resolver's `hold` on a reservation once a claim is asserted; released only by a ruling (D10) | an option's effect on an offer |
| **option record** | `option/<P>/<loop>`: the effect of a cleared option leg on its underlying offer P, active while `now < until` | "hold", "claim" |
| **statement** | `{subject, category, issuer, kind, as_of, until, evidence, path, deposit?, paid_by, scheme}`, the one shape the gate reads; kinds in v1: *signed*, *attested*, *self-bonded* | a factbond assertion (an assertion may back a statement; it is not one) |
| **register** | a separately rooted, append-only recordstore log with a current-status view (`status/`, `revoked/`, `suspended/`, `accredit/`), announced under the `register` role with a declared heartbeat cadence and consistency proofs between roots | the shared catalogue |
| **trust root** | a register a wanter names as the top of an acceptable accreditation path | every register on the path (those are pinned, not named) |
| **accept** | how a requirement admits a third party (a resolver, an inspector): by key, by accrediting root, by deposit floor, or by absence of reversals in a look-back window; never by a count (D7) | a reputation score |
| **cover** | a give under `insure(…)` whose deposit is reserved to the insured; settles only through `resolve`, a two-signature `settle(split)`, or the quiet `settle` when no claim was asserted | a statement (a standing policy statement is *insured* kind, deferred) |
| **presentation** | the hash, named in an `insure` term, of the facts the insured declared when buying cover (D3) | the credential presentation in a `cred/` sidecar |
| **finality window** | the period per fact type after which a ruling and its ledger entry close except for fraud or a contradicting primary source (D2) | the claim period |
| **argument-only operator** (`operator-argument`) | a graph-kind head under `operator` declared by its argument alone, no ends: its give attaches to a thing (`insure`, `inspect`) | a moving operator declared by ends (`transport`) |
| **item claim** | `item/<h>`, written by the clearing role: the one open option record or unperformed fill a *maker* has on `item(h)` | an index; a title |
| **calibration ledger** | factbond's per-asserter outcome record, with entries for adjudicators too; the **loss view** is its asserter-indexed negative half, queried with a look-back | a reputation score |
| **retention** | the insured member's own share of a loss, paid from its own deposit reservation before the pool (D9) | withheld payment, construction's sense |
| **deductible** | the amount of a loss below which cover pays nothing, a term of the `insure` give | retention |
| **scheme** | the published check procedure a credential category or an accreditation points at: what is examined, what a pass is, what the examiner signs (D4) | the category itself |

## 2. Decisions

### D1. A credential statement is backed by a deposit and reserved per relying leg

**Problem.** The factbond draft's standing mode (an open-ended challenge
window closed only by withdrawal after notice) locked capital to time rather
than reliance, made dormant keys harvestable, and contradicted factbond's
2026-09-21 decision that a standing bonded position is the escrow's deposit
shape applied to a claim. The wanter alone chose the claim period, an
unpriced lock on the giver; and nothing required a claimant to give the
giver notice before claiming.

**Decision.**

- **The statement names the deposit that backs it.** `cred/K/<id>` with
  `kind: self-bonded` or `kind: attested` carries `deposit: {offer,
  escrow}`. In v1 that is the deposit on the service offer being cleared:
  one shared deposit, the wanter's floor sized to cover both faults. The
  statement says "K holds C; a refutation is non-performance on any leg
  that relied on this statement, within that leg's claim period". A
  dedicated deposit per statement stays open as a later upgrade; the field
  already allows it.
- **The deposit need not belong to the statement's subject.** A practice
  with six dentists is the maker of the service offers and posts the
  deposit; each dentist's key is the statement's subject and is checked at
  the door (D8). The practice checked the licences, so its statement is
  `kind: attested`, backed by its own deposit; the solo practitioner's
  `self-bonded` statement is the degenerate case with subject = maker. The
  party best placed to check is the party whose collateral is at stake.
  One step out, the practice's insurer does the same as a condition of
  cover, and where such cover exists the wanter should prefer it, since it
  pools and it watches. Bond, practice, insurer: the same statement,
  backed at increasing scale.
- **The gate's check** for a statement naming a deposit is the existing
  deposit check: free capacity of the named deposit, after this fill's
  reservation, is at least the entry's `min_bond` (`meets(held=)` as for
  bonds today), so the same collateral is never promised to two wanters.
  Reliance is reserved per fill for that fill's claim period and released
  on clean settlement, exactly as performance is; the residual stays free;
  withdrawal is the deposit's `notice`/`withdraw`.
- **What the credential floor covers.** Only "the giver was not what the
  statement said", a self-knowable fact the giver can prove and the wanter
  can challenge under D2. A botched procedure by a qualified dentist is
  negligence, excluded from objective triggers (D10); the dentist example
  says so, or "bonded" reads as a warranty on the work.
- **A claim** ("K did not hold C") is an ordinary escrow claim: after
  notice and cure (D2), the harmed wanter asserts it on factbond, the
  resolver holds the reservation, the giver disputes with evidence under
  D2, and a ruling pays the reservation up to the indemnity (D3).
- **A1. The claim period is a matched term.** The give declares its
  maximum (`claim_max`, v6); the want asks for at most that; the catalogue
  carries a default and an outer cap per category (FIDIC's 365-day default
  and two-year cap are the shape); a give may later declare a price per
  period instead. A wanter who wants longer pays for it in the price. The
  reserved slice survives the deposit's withdrawal by notice for the whole
  period, so the claim period is the credential's effective challenge
  window and a brief bond cannot outrun a long one.
- **A2. Notice before claim, three clocks, no judgement.** A claim must
  cite a prior `notice/` record from the claimant to the giver; the notice
  must fall within the claim period; the claim must be asserted within M
  days of the notice (policy data per category). No "reasonable time after
  discovery" standard: early warning for the giver, bounded delay after
  notice, all checkable from records.
- Optionally, K may post a one-shot factbond assertion of the same fact
  with a long window (F1) to earn a certified record in the calibration
  ledger. It is reputation, not the gate's input. Completeness
  declarations ("these are all the licences I hold or held") are
  statements of the same kind and settle the same way.

**Consequences.** factbond F2 is dropped; F1 (per-assertion window,
bounded) stays. `LoopEscrow` is unchanged; `reservations_for` reads the
matched claim period. loopmarket's gate gains the deposit check and the
`min_bond` floor; the give record gains `claim_max`; the statement gains
`deposit`, which may name another maker's deposit.

### D2. Disputes with clocks: burden shift for self-knowable facts, suspension on silence, a cheap first rung, bounded costs, a paid and ledgered judge, a final ruling

**Problem.** Burden shift at factbond's odds-priced challenge stake let a
challenger force real evidence work for a trivial stake; "no evidence in
time ⇒ refuted" reversed the 2026-09-19 principle; sealed evidence broke
"anyone re-derives"; counter-assertions duplicated disputes and were
undefined against a closed assertion. And every dispute began at the
bonded stage, nothing clocked the adjudicator, no ruling was ever final,
and for a small leg the harmed party's outlay could exceed what she could
recover, so small cheating would never reach the record (Milgrom, North
and Weingast's condition (8)).

**Decision.**

*The primitive.*

- **Counter-assertions are not a primitive.** Against a live assertion a
  contradiction is a dispute at the existing stake formula. Against a
  closed assertion or a key that asserted nothing, a bonded negation is an
  ordinary assertion the accused may dispute at the odds. Two rules
  survive into disputes generally: a dispute names a specific, refutable
  fact, never a label; and silence counts only after notice and only
  through a ruling.
- **Fact-type class `self-knowable`** is added to factbond's evidence
  policy as data. For a claim of this class, a dispute obliges the
  asserter to deliver evidence to the adjudicator within the evidence
  period; a scanned document alone is dispute input to a staked rung,
  never sole evidence, per the policy's own rulings.
- **Silence moves no money by itself.** Unproduced evidence at the end of
  the period is an input to the ruling: the policy tells the adjudicator
  that, for a self-knowable claim, it is grounds to rule against the
  asserter, ex parte, on the record. Only a ruling moves money; no ruling
  escalates. Between lapse and ruling the statement is **suspended**: a
  `suspended/<statement id>` record in the issuer's register (for a
  self-bonded statement, the giver's own book), which the gate reads as
  "meets nothing" until cleared.
- **Evidence hashes and rulings are public**; the evidence itself is
  disclosed to every rung on the escalation path. The burn slice on the
  loser's stake stays (it is load-bearing against self-dispute laundering,
  factbond THREATS T11).

*The clocks (rule 4).*

- **B1. Rung zero: notice and cure.** The `notice/` record of D1's A2
  carries a cure deadline. The giver may cure within it (deliver, refund
  at the ladder, correct the statement); only refusal or silence past the
  deadline opens the bonded dispute, and nothing is public before that.
- **A5. The evidence period has a fixed shape.** For `self-knowable`
  claims, of the order of 7 to 14 days (the number is policy data); after
  lapse the adjudicator rules ex parte on the record.
- **A3. A ruling period per rung.** Each rung must rule within a fixed
  period (policy data; 28 days is the statutory-adjudication benchmark, 84
  the dispute board's); at lapse the claim moves up automatically and the
  lapsing adjudicator forfeits its fee for that claim.
- **A4. The first ruling pays; a finality window.** A ruling executes at
  once through the escrow. Reopening is allowed within a finality window
  per fact type, on evidence that did not exist at ruling time, or at any
  time within the window at **double the stake** without a novelty test.
  After the window, only fraud or a contradicting primary source reopens.
  This is factbond's own existing rule (`mechanism-design.md` §6:
  reopenable "within a window"); the drafts' "new by definition" was
  drift from it.

*The costs.*

- **The challenger pre-pays an evidence fee** E (policy data per class)
  beside its stake; E goes to the asserter if the assertion holds and back
  to the challenger if it is refuted.
- **B3. The challenger's outlay is capped; E is refunded on any win.** For
  a claim routed from a reservation, stake plus E is at most a fraction
  k < 1 of the reserved slice (policy data); E returns to the challenger on
  any ruling in her favour, including a partial one; the winner's share
  stays as the hunter's bounty. The harmed party already has value at
  stake in the reservation, so the odds-priced stake was double-counting
  her risk.
- **B5. One conduct rule on costs.** If the asserter produces evidence
  only after the notice period lapsed, E returns to the challenger even
  when the assertion holds. Stonewalling is priced without adjudicator
  discretion.

*The judge.*

- **C2. Every fact-type class names a final rung**, a bonded, named
  adjudicator or panel; a class without one may not be used in any
  `requires` gate. The final rung is never a token-weighted vote: where the
  value at stake exceeds the cost of the vote, the vote is bought (the
  March 2025 Polymarket resolution). Adjudicators for cover are named at
  policy start, as a dispute board is appointed at contract start.
- **C3. The adjudicator is paid per ruling and is in the calibration
  ledger.** A fee per ruling, forfeited on lapse; a ledger entry per
  adjudicator, with a reversal at the final rung recorded and the
  adjudicator's deposit forfeited; the policy names the adjudicator class
  per category (holders of the same credential under the same root, or the
  register itself), each holding a deposit. **Ruling counts are never a
  signal**: puppet cases manufacture them for the burn slice (U12's reason,
  applied to judges). The one positive entry the ledger may carry for an
  adjudicator is a ruling escalated at doubled stake to the final rung and
  upheld there, which costs the washer a real review.
- **C5. The ruling record** carries the referred fact, the notice
  timestamps, both submissions' hashes or the lapse, the resolver's key,
  the category and the evidence-policy and pack versions applied, and a
  short reason naming the rule. The first two are what defeat fast rulings
  when absent (excess of jurisdiction and denial of a hearing are the only
  grounds that succeed against statutory adjudication); the versions make
  a ruling reusable as precedent, which is how Incoterms and NGFA's
  decisions got their force.

**Consequences.** factbond's F3–F7 as in the draft's table.
`Assertions.sol` gains nothing beyond F1 and a per-fact-type escalation
value (D10); the fee, the cap, the clocks and the notice are policy data
and consumer-hook behaviour. The `suspended/` record is a register
keyspace loopmarket's gate reads (R4).

### D3. Cover: the insured asserts the trigger; one payout through the reservation; indemnity, presentation, assignment, netting; never countersigned

**Problem.** The draft had the insurer asserting the covered fact on
factbond and reserving in the escrow, so one refutation paid twice.
`LoopEscrow.countersign` returns the whole reservation to the giver, so an
insured who countersigned would void her cover. No indemnity rule was
stated. The insurer had no defence against concealment, "the insurer makes
assignment a condition of payout" was not something a resolver firing on a
ruling could enforce, and one loss could be paid from two reservations.

**Decision.**

- **The insured asserts the trigger**, in event cover and fact cover alike
  ("the gearbox failed on D", "the seller did not have title as of D"), as
  a fresh factbond assertion with a normal window, after D2's notice and
  cure; the insurer is the natural disputer; `assert_` calls the consumer's
  `hold` on the reservation and the ruling calls `resolve`. The insurer
  never asserts the covered fact at cover time; its "did they check" is
  visible in its underwriting legs (D4).
- **Indemnity.** `resolve(toWanter)` pays `min(limit, provable loss) −
  deductible`, provable loss bounded by the value of the legs that pinned
  the insured edge (loopmarket THREATS T5, factbond F3). For event cover
  the pinned leg's value is the provable loss with no further proof, or the
  parametric product loses its point.
- **D-1. Fair presentation.** The `insure` term names a `presentation`: a
  hash of the facts the insured declared (the inspection history of
  `item(h)`, the insured's loss-view entries, the door-binding source). A
  false presentation fact is a `self-knowable` fact the insurer may assert
  as a bonded negation; a certified refutation reduces the payout
  proportionately (the Insurance Act 2015's remedy). Without a
  presentation duty, concealment is priced into everyone's premium.
- **D-2. Assignment before payout, and netting.** The resolver requires
  `assign` of the insured's claim on the giver's reservation to the insurer
  before a cover `resolve(toWanter)`, and nets any amount already recovered
  from it (Marine Insurance Act s. 79: subrogation on payment, no double
  recovery).
- **D-3. Contra proferentem.** A cover term the adjudicator finds
  unadjudicable is construed against its drafter: "unresolved" on a cover
  claim never releases the reservation to the insurer, and the drafter of
  a term refused as unadjudicable forfeits a validity slice. Otherwise
  ambiguity pays the drafter (Augur's invalid-market scam).
- **The cover reservation is never countersigned.** `reservations_for`
  marks a reservation whose give is under `insure` as `claimOnly`;
  `LoopEscrow` refuses `countersign` on it; it settles by `resolve`, by
  `settle(split)`, or by the quiet `settle` when no claim was asserted.
  `cancel` by the insurer after the window begins pays the whole
  reservation to the insured, the right outcome. The cover is
  claims-made-and-reported within the claim period for occurrences in the
  cover period, the professional-lines form, not "occurrence-basis".
- **Periods.** The cover period and the claim period come from the
  `insure` term's `period(…)`, matched per D1's A1; `claim_seconds` is per
  leg. **D-4. Tail cover:** `LoopEscrow.extendClaim(key, seconds)`,
  callable by the giver only (lengthening one's own exposure is safe), sold
  as a give.
- **B2. A two-signature negotiated settlement.** `settle(split)`, signed by
  the reservation's wanter and the deposit's giver, on any reservation
  including `claimOnly` cover; nobody else can trigger it. A clean
  settlement under rule 3, not a default; it is where most disputes end in
  practice.
- **B4. `assign` to any key.** A claim on a reservation may be assigned by
  its wanter to anyone, not only to an insurer: a claim too small for the
  victim to pursue is pursued when it can be sold (Iceland's transferable
  claims). The assignee's own ledger record is the check on abuse.
- **The resolver is acceptable to both sides** (D7's C4); `reservations_for`
  checks it at clearing, since the resolver is fixed at `reserve`.
- **D-5. Staged release, deferred.** A reservation schedule (a fraction
  released at countersign, the remainder at claim-period end) is accepted
  in principle and deferred: it touches the settle path, and B2 already
  lets parties release part by agreement.

**Consequences.** `LoopEscrow`: `claimOnly` at `reserve`; `assign` to any
key; `settle(split)` with two signatures; `extendClaim` by the giver; the
`resolve` path checks assignment and nets. `escrow.py`: periods from the
term, per-leg claim seconds, the matched claim period, the accepted
resolver. The `insure` term gains `presentation(…)`. factbond: no change;
fact cover claims are `attribute-matches-source` claims with the insurer
holding the evidence.

### D4. Argument-only operators; composed cover; inspection made final; what checking means, published

**Problem.** `insure` and `inspect` could not be operators: the operator
algebra requires two ends of one dimension and rejects an operator that
moves nothing. The *insured* statement kind could not be checked at
matching time under fully collateralised cover. An inspection settled
nothing between wanter and giver, nothing required an inspector to be
independent, an accreditation said who may issue what but not what
checking means, and a fail-closed gate said only "meets nothing".

**Decision.**

- **The marker `operator-argument`**, beside `operator-input` and
  `operator-output` (which name an operator's ends): a graph-kind head
  under `operator` declared by its argument alone. An operator declared by
  ends moves a thing; one declared by argument only attaches to it (cover,
  a report, a warranty). `check_composition` accepts such a give when
  `ontology.accepts(thing, terms)` holds and skips the ends and coordinate
  replacement. Declared in the seed as `insure graph-dimension
  operator-argument`, `inspect graph-dimension operator-argument`. The
  marker only lets the composition check accept the give; the behaviour
  lives in `requires.legs`, since nothing in a want triggers this
  composition the way a coordinate gap triggers `transport`.
- **`requires.legs: [{category, accept}]`**: the loop must contain a give
  under each named category whose argument accepts the wanted thing, from
  a giver the entry accepts (D7's `accept`). Checked fail-closed; the
  solver composes it as it composes `transport`.
- **Two cover shapes.** Composed cover (v1) is a `requires.legs` entry
  naming `insure(…)`; the cover reservation is made to the wanter at
  clearing (D3). A standing policy as a statement (`kind: insured`) is
  deferred until pooled cover exists (D9); the gate's kinds in v1 are
  signed, attested, self-bonded.
- `insure` terms use nested role heads (`subject(…) peril(…) period(…)
  limit(…) deductible(…) presentation(…)`); wanters name the perils they
  want (the graph kind's silent-want rule is accepted as is).
- **E1. Certificate-final.** An `inspect` term may carry
  `certificate-final`, and its report (hash in the fill) enumerates the
  categories it certifies. A claim on a certified attribute is admissible
  only against the inspector's statement (its deposit or cover, capped in
  its offer); a claim on an uncertified attribute runs against the giver.
  GAFTA's loading-port rule; the basis of D10's professional indemnity as
  fact cover; the inspector is a bonded attester like every other checker.
  Inspection history of `item(h)` is the set of `inspect` fills naming it.
- **E2. Inspector independence.** The free formality: an `inspect` give is
  admissible only if its giver's key is not a maker or wanter on any other
  leg of the loop naming `item(h)`. The real mechanism, since keys are
  free: the `requires.legs` entry accepts inspectors by root, deposit floor
  or absence of reversals, never by a count, and the inspector's deposit is
  what a false certificate forfeits. A practice attesting for its own
  dentists stays legitimate because its collateral is at stake; a neutral
  inspection is neutral because the wanter required it to be.
- **E3. A `scheme`.** `accredit/` records and credential categories name
  the check procedure in the vocabulary pack: what is examined, what a
  pass is, what the examiner signs (ISO 17065's published scheme; UCP's
  ISBP). "Did they check" becomes a recorded fact, and a ruling (D2's C5)
  cites it.
- **E4. The rejection record lists every failing step.** The attributed
  rejection record (U8) for a `requires` failure enumerates all failing
  steps of the gate in one record, so a re-presentation cures in one round
  (UCP Art. 16(c)).

**Consequences.** `ontology.py` (marker, `declare_argument_operator`),
`matching.py` (`check_composition`; `meets` for `requires.legs` with
acceptance), the solver, the seed; the `inspect` term gains
`certificate-final` and a certified-categories list; `accredit/` records
and categories gain `scheme`; the gate's rejection record enumerates. One
new `Requires` field in the same v6 bump as D7.

### D5. The per-item rule is per maker; cross-maker exclusivity is priced or witnessed, later

**Problem.** With a derived id anyone can compute, a cross-maker rule let a
griefer block any car's sale for the price of an option premium paid to
himself, and it contradicted "ownership is not a clearing concept".

**Decision.**

- **Per maker, in v1:** at most one active option record or unperformed
  fill per `(maker, item(h))`. It stops one seller double-selling by
  accident. Two makers may both offer h (owner and broker, a reseller
  chain); whichever cannot deliver is a non-performance, covered by
  deposit, point and fact cover as everything in `items-and-ownership.md` §5.3.
- **Why this is enough.** Two makers on one item is only a problem where
  the buyer has sunk cost into the specific item (the inspected car, the
  wedding venue), and there the buyer's remedy exists today:
  `requires.point` sets the giver's deposit floor to what the loss would
  actually cost them. A sufficiently high bond makes every case safe: owner
  and broker, the reseller chain, the double-dealer (whose ladder must not
  be cheaper than the price difference between two buyers, P3's sizing
  concern) and the griefer (who, without a free exclusivity rule, merely
  posts an offer nobody takes). Thief and owner is a title problem,
  answered by the stolen-goods register and fact cover.
- **Priced exclusivity, the first post-v6 addition**, its field shape
  fixed now (`items-and-ownership.md` §8): a give naming `item(h)` may declare `exclusive:
  true`, admissible only if its deposit is at least the leg's value for the
  option's or fill's duration; while such a claim is open the clearing
  refuses other makers' legs on h. Blocking an item then costs its value in
  locked capital. Its duration is the option record's window, so it
  follows D6.
- **Witnessed exclusivity (later):** the same without the price where an
  entitlement witness exists (`registry-transfer` for registered goods, a
  tagger's statement for tagged goods).
- Item claims are a clearing keyspace `item/<h>` written by the clearing
  role, never a book index, and go on chain beside option records.

**Consequences.** `items-and-ownership.md` §2 and I2/I3 as rewritten; `exclusive` ships in
the bump after v6.

### D6. Options are obligations under P3's ladder; exercise needs a loop; names

**Problem.** The draft made W's withdrawal "void" during a hold: an
unpriced lock, against P3's permissionless, priced cancellation, and
against the chat's own objection to time-dependent fill state. "Hold" and
"claim" collided with the escrow's meanings.

**Decision.**

- **The cleared option leg is an obligation** like any other. W's exit is
  a cancellation of that leg at the ladder's price, paid to the holder from
  the deposit on O; a no-show at exercise is non-performance on P, covered
  by P's deposit and the holder's point. A withdrawal of P during an active
  option is read as W cancelling the option leg. No unpriced lock exists.
- **The option record** `option/<P>/<loop>` carries `until =
  O.exercise.end`; fills stay time-free; availability subtracts active
  option records.
- **Exercise is a clearing** and needs a closing loop. For a token-priced P
  it is two legs; for barter the option is a right of exclusivity, not a
  guaranteed trade.
- An item claim (D5) ends when the option leg's window ends or the fill is
  performed.
- **Names:** the record is `option/`; "hold" and "claim" keep their escrow
  meanings (§1); `options-and-cover.md` says "one model, two routes".
- "Build it general" is honoured by not closing the door: `underlying` is
  one offer id in v1; a category or a whole loop as underlying,
  non-exclusive options, Bermudan windows and a firm price without
  exclusivity are extensions of the same record, none blocked by it.

**Consequences.** `options-and-cover.md` §2, §3 as rewritten; the loop record's new field
(a loop-record version bump); nothing new in `LoopEscrow`.

### D7. One requirement shape, one statement shape, registers as logs, one v6 bump

**Problem.** The requirement had no `kind`; freshness conflated a
credential's issue date with the register root's age; the wanter had to
name every register on a path it cannot know; the check was giver-only;
three uncoordinated v6 bumps were on the table beside the corpus's own
planned `credentials` field; nothing said who may resolve a leg; an
absence proof was only as good as an unverified root's completeness.

**Decision.**

- **The requirement.**
  ```
  counterparty: [ { category, kinds, min_bond?, roots, max_root_age }, ... ]
  legs:         [ { category, accept }, ... ]
  resolvers:    accept
  ```
  *Counterparty* is the other side of the leg, whichever side the requirer
  is on (a giver may require of a wanter: age, a prescription, a tenant
  check). Entries are conjunctive; one statement answers one entry; the
  only disjunction is inside an entry, the `kinds` list plus `min_bond`
  ("licensed or self-bonded ≥ B" is one entry). `min_bond` applies whenever
  the satisfying statement names a deposit, whatever its kind.
  Cross-category alternatives ("an EU or a UK licence") live in the
  catalogue as recognition edges under one node; cross-root alternatives
  are not supported; general alternatives can be added later as an outer
  list without changing the entry.
- **`accept`**, for resolvers and for the givers of `legs`: by key, by an
  accrediting root (a bonded accreditor's collateral is what the wanter
  really relies on), by a deposit floor, or by the absence of reversals
  within a look-back window; optionally an issuance binding (D8). **Never
  by a count** of rulings or inspections, which puppet cases manufacture.
- **C4. The resolver is chosen before the dispute by both sides, and what
  it has at stake is what makes it impartial.** Keys are free, so
  impartiality cannot come from who the resolver is. The give names its
  resolver (`arbitrator`, as today); a leg clears only where that resolver
  is within the requirer's `resolvers` acceptance; the resolver's deposit
  is what a ruling puts at risk, and reversal at the final rung forfeits
  it and enters the ledger (D2's C3). The cheap formality stays: a resolver
  is never the key of a party to the leg or of the deposit's maker. The
  final rung (D2's C2) is the backstop: a puppet that slips through only
  delays, and its deposit pays for the delay. The mutual's discretionary
  decisions remain judge-in-own-cause by design and labelled as such
  (D10).
- **Roots, not registers:** the wanter names trust roots; the solver
  discovers the path's registers and the proposal pins every one of them in
  `register_roots`; clearing checks each hop against its own pinned root;
  an unpinned register on the path fails closed.
- **Freshness is the pinned root's age:** `max_root_age` bounds how old
  each pinned register root may be relative to clearing's clock; a
  register's declared cadence is public and a wanter whose bound is shorter
  simply excludes it (a liveness cost on the register's issuees, recorded
  as a threat). The statement's `as_of`/`until` are validity, checked
  against the handover window; an attestation's `as_of` is its check date
  and doubles as its freshness.
- **G1. Registers are transparency logs.** Append-only, with a consistency
  proof between one heartbeat's root and the next; the status keyspaces are
  the current view on the log; "two inconsistent roots signed by register
  R" is a specific, refutable fact about R, disputable against R's bond and
  grounds for removal as a trust root; anyone may monitor for the winner's
  share, and an insurer's watch duty is the monitor role. A `suspended/`
  record leaves the view when cleared, its history staying in the log. An
  absence proof needs completeness; a heartbeat proves only freshness; the
  consistency proof is what makes completeness checkable.
- **G2. Short lifetimes.** A statement's default `until` is weeks, with
  renewal cheap (the sidecar renews without re-signing the offer); a
  register's declared cadence is at or below the shortest plausible
  `max_root_age`.
- **The statement** as the drafts, plus `deposit` (D1), `paid_by` (**G5**:
  who paid the attester, subject or relier, the disclosure issuer-pays
  ratings fell back on) and `scheme` (D4's E3). `cred/` admission: `subject
  == book owner`, with the attributed rejection record otherwise.
- **P3 §4b's `credentials` field is subsumed** by the `cred/` sidecar: a
  credential renews or is revoked without re-signing the offer, which a
  field cannot do; the crawler check P3 describes is the attester adapter's
  automated rung.
- **One v6 bump:** `underlying`, `exercise`, `claim_max` (D1, D6);
  `requires.counterparty`, `requires.legs`, `requires.resolvers` (D4, D7).
  `exclusive` (D5) in the bump after. Loop record v2: option record, item
  claims, `register_roots`. `Beat` gains `register_roots`.
- Door checks (D8) are witness types, routed through the roster as `counterparty-gate.md`
  §7 says.

**Consequences.** `counterparty-gate.md` as rewritten; `schema.py` once; `announce.py` reads
a third role; `LoopProposal`, the loop record, `LoopVerifier.Beat` and
`beat.submission` carry `register_roots`; `verifyAbsence` enters the leg
path. P2 §4a's open decision (a) is answered ("bond floor, oracle type,
counterparty statement, loop structure, acceptable third parties; never
history") and (d) is answered "no".

### D8. Identity binding is a door scale and a set of issuance sources

**Problem.** One chain mixed presentation-time checks with issuance-time
bindings and asserted false subsumptions.

**Decision.**

- **Door scale** (ordered, cumulative names, witness types in the roster):
  `door-at-least-possession ⊒ door-at-least-photo ⊒ door-at-least-proximity`.
- **Issuance sources** (a set the wanter accepts, not a level):
  `issued-by-attester-in-person`, `issued-by-web-of-trust`,
  `issued-by-state-document-zk`, `issued-by-state-document-eid`. The
  statement records which source bound the key; the requirement lists the
  acceptable ones. Government eID is one source, never required by the
  protocol.
- The photo reaches the counterparty's device by selective disclosure at
  the door; the public statement carries only a commitment to it.
- Evidence classes are factbond's catalogue; the only ordered chains in the
  assurance pack are the door scale and, if the evidence classes are ever
  ordered, that one. That is the second vertical for ontodag's ordinal kind
  (the assurance drafts' `ontodag-asks.md` §2): ontodag decides between the kind and cumulative
  names as the interim.

### D9. Placement; the mutual as the first pooled form, with its rules; the loss view

**Problem.** The three-repo split and the relocation of pooled cover and
the trust score to assurance were decided in the drafts, on a reading of
factbond that was not accurate. The mutual's own rules were unspecified.

**Decision.**

| repository | owns after this plan |
|---|---|
| **loopmarket** | the record (v6), the gate with `accept`, `cred/` and `notice/` sidecars with cure deadlines, the `register` role and `register_roots` pin, absence and consistency proofs on the leg path, option records, item claims, argument-only operators, `claimOnly` reservations, `assign`, `settle(split)`, `extendClaim`, the cancellation ladder applied to options |
| **factbond** | F1; the `self-knowable` class with its evidence period, ruling periods, evidence fee, challenger cap, finality window, suspension and final rung in the evidence policy; adjudicators in the calibration ledger; the loss view (from `Asserted ⋈ Refuted`, the asserter in the correction feed's payload) with look-back; **pooled cover**: the geared payout reserve of `netting-and-reserves.md` applied to cover gives, fail-closed at the cap, with per-fact notional caps, and the mutual's rules below; the coverage give for any pack used in bonded matching |
| **assurance** | adapters (attester first, EU and W3C later), register services and mirrors as transparency logs with declared cadence, the credential layer of the vocabulary (on ontodag-core's occupations pack) with `scheme` per category, identity binding (D8) and the handover app, the insurer's product layer (underwriting `requires.legs`, presentation, retention, watching and notice duty as the monitor role, graduated sanctions and exclusion, terms construed against the drafter), and a scoring service as one more attester if anyone builds one |
| **ontodag / ontodag-core** | the identifier kind (registry 4.3), the ordinal decision, the general vocabulary additions in the assurance drafts' `ontodag-asks.md` §3, the legal-vocabulary check of §3b |

- **The trust score is deferred.** An attested statement "from seeds S,
  function F version v, over roots D, K scores ≥ x" is admissible as any
  attester's statement; no repository computes a score; nothing positive
  flows from settlement (U12). The charter's A6 is dropped and A7 moves to
  factbond; the charter is otherwise A0–A5.
- **A mutual is the first pooled form.** Members' deposits pool under the
  reserve's minimum capital rule; membership is the members' own vetting,
  "did they check" in its oldest form (TÜV began in 1866 as an
  inspection-and-insurance body founded by the inspected; Nexus Mutual is
  the chain precedent). It grows out of D1's ladder without a new actor:
  the practice is a mutual of its dentists; a pool is the practice with
  more members. A specialist insurer is the same shape with one member and
  outside capital, so nothing built for the mutual is wasted, and regulated
  entrants are not waited for. Correlated risk is priced by the reserve's
  concentration cap; a mutual may buy reinsurance as a cover give from
  another pool, the free recursion. The reserve is factbond's; the
  underwriting requirements are assurance's product layer, the same for a
  mutual and for an insurer.
- **The mutual's rules.**
  - **F1. Admission: survey and vouch, both, priced.** An attester's or
    register statement (the survey) and a member's bonded, specific vouch
    (the proposer); an entrant without a vouch is admitted on a survey
    alone at a higher initial retention. Vouching alone reproduces the
    Maghribi closure; a statement alone admits sybils through any
    compromised register.
  - **F2. Vouching pays.** The voucher receives a share of the vouchee's
    premiums or calls for the life of the vouch (the Diamond Dealers Club's
    1 per cent).
  - **F3. Order of recourse.** The member's own deposit reservation pays
    first (its retention), the pool in excess, reinsurance above; a pool
    payout for a member's fault takes an automatic claim on that member's
    deposit. **No supplementary calls**: the pool fails closed at the cap,
    because capital cannot be called from a key; the gap is met by upfront
    capital and reinsurance.
  - **F4. Heterogeneity.** Contributions risk-rated by each member's
    reserved exposure and loss record; free exit; sibling mutuals may form.
  - **F5. Graduated sanctions; an internal second instance for
    exclusion.** After a paid claim the mutual raises that member's
    retention or caps its cover before any exclusion; exclusion is a
    specific refutable statement with an internal review under a deadline;
    cover is suspended, not cancelled, while review is pending. A
    discretionary claim decision stays final (the omnibus rule); exclusion,
    which ends the relationship, gets a second look.
  - **F6. The claims judge is named.** A small committee of bonded members,
    excluded from ruling on their own vouchees; a separate reversal and
    replacement power held by another body; a claimant deposit refunded on
    acceptance; a fixed decision window; a cool-down before payout.
    Decisions are the bonded statements D10 requires.
  - **F7. Rule changes by non-liquid member voice.** Changes to the
    mutual's underwriting requirements and retention are made by bonded,
    non-transferable member proposals, one member one voice. Admission,
    exclusion and claims stay with bonded statements and the committee.
  - **F8. No restriction on outside dealing.** The mutual never restricts
    members' trades outside it; "member of mutual M" is a wanter's optional
    requirement, never a market-wide one.
- **The loss view.** **G3.** Queried with a look-back window
  (`max_loss_age`, beside `max_root_age`), append-only underneath: nothing
  is deleted, nothing counts forever by default. **G4.** Priceable: it
  separates "refuted" from "did not perform on a ruling"; a dispute the
  asserter wins leaves no negative entry; every published ruling names the
  rule and fact type applied, so an honest misdescription is not read as
  fraud. Adjudicators have entries of their own (D2's C3).

### D10. Objective triggers; the discretionary product; final rungs; the boolean escalation value; the standard the plan is held to

- **v1 cover has objective triggers only**; negligence is not insurable in
  v1. Professional indemnity reduces to fact cover on licence validity and
  on the existence and content of certificate-final inspection reports.
- **No placeholder rung.** A rung with no adjudicator produces cover that
  escalates instead of paying, "looks insured, is not", against rule 3.
  Negligence-type claims are a **mutual's discretionary product**, outside
  factbond's ladder: the mutual's claims committee (D9's F6) judges a
  member's conduct, pays from the pool, and records the decision as a
  bonded statement. It is not re-derivable and not challengeable on the
  merits, so it is labelled discretionary, and it may enter a `requires`
  gate only as "member of mutual M", never as a certified fact. factbond
  certifies facts; mutuals judge conduct.
- **C1. A held reservation never quiet-settles.** Only a ruling releases a
  reservation the resolver has held; the "unresolved" value means the hold
  persists, never "release to giver". With D2's automatic move-up a ruling
  always arrives, and the one path by which a silent asserter could exit
  with the bond is closed.
- **C2** (stated under D2): every fact-type class names a bonded, named
  final rung; a class without one may not be used in a `requires` gate.
- **The boolean escalation value.** `escalate` resolves at `outcome ×
  50%`, which reads a boolean assertion as 0. factbond adds a per-fact-type
  escalation value to the policy (for a boolean, "unresolved", which a
  consumer treats as neither, and which for a cover claim means the hold
  persists) before any long-lived boolean use.
- **Good practice, not compliance.** loopmarket is open source on the
  internet with no organisation behind it; compliance with any
  jurisdiction's law is entirely the makers' responsibility, stated as a
  disclaimer in loopmarket's README and the charter. The standard the
  design holds itself to is good commercial practice, the solutions
  merchants, private courts and mutuals converged on because they were
  more efficient, safer and produced fewer conflicts; the plan was read
  against that record in `commercial-practice-review.md` and amended
  accordingly (the A–G items above).

## 3. Consistency check

**Invariants touched.**

- loopmarket U1, U5: unchanged; options and cover are uniform offers with
  positive prices; payouts never clear. U2: one v6 bump (D7), v5 byte for
  byte. U3, U4: option records, item claims, statements, register roots
  and acceptances are all re-derived from pinned data. U7: unknown
  categories, unpinned registers, unrostered witness types, suspended
  statements, unaccepted resolvers and classes without a final rung all
  meet nothing. U8: `cred/` has its own attributed admission rule, and
  rejections enumerate. U11 extended as `options-and-cover.md` §7 says. **U12 respected**:
  nothing in this plan adds credit from settlement, and no acceptance
  criterion counts rulings or inspections.
- factbond F1 (status from speech acts: suspension is a register record,
  not contract status), F3 (indemnity, D3), F4 (fail-closed at the cap,
  D9), F7 (certified ≠ truth: a certified self-assertion is reputation, not
  the gate's input). The 2026-09-19 escalation principle is kept and
  extended (D2, D10). The contract stays subject-agnostic: no
  self-assertion or counter-assertion fields.
- ontodag: the identifier kind is a registry minor with the kind node
  outside the prelude; no per-key or per-item nodes enter any shared
  catalogue; the stranger test is stated for tagged ids.

**Deliberate divergences from commercial practice**, stated so they are not
read as oversights:

1. **Every ruling is public.** The diamond trade publishes only
   non-compliance, because a large judgment for an honest misunderstanding
   reads worse than a small one for theft. Transparency is an invariant
   here; the record is made priceable instead (D9's G4).
2. **Nothing positive from history (U12).** Full-file credit reporting
   allocates better than negative-only, but only on identities that cannot
   be manufactured. With keys, positive history is wash-tradeable; the
   positive signals are collateral and bonded vouching.
3. **No supplementary calls.** P&I clubs call capital from members; the
   pool here fails closed at the cap because capital cannot be called from
   a key (D9's F3).
4. **Security is held until a ruling.** Practice values the beneficiary's
   liquidity ("pay now, argue later"); rule 3 trades it for certainty. With
   D2's A3 and A4 the delay is bounded and the first ruling pays.
5. **A cleared loop is never reversed, even for fraud.** CISG Art. 40 lifts
   the notice bar where the seller knew; here the fraud remedy is a bonded
   negation against the closed assertion and the loss view, so the claim
   period is never a fraud shield.
6. **Never a vote for admission, exclusion or claims.** Members' voice
   exists only for rule changes and is non-transferable (D9's F7).

**Cross-checks that must hold in the folded plans.**

1. The claim period (escrow) and the challenge window (factbond) are never
   used for each other (§1).
2. Every place that says "hold" means the escrow's `hold`; every option
   effect says "option record".
3. Every cover payout goes through one reservation; no cover design asserts
   the covered fact on factbond at cover time; every cover `resolve` checks
   assignment and nets.
4. Every requirement kind the gate accepts in v1 is one of signed, attested,
   self-bonded; *insured* appears only under "after pooled cover".
5. Every ordered chain in any pack has cumulative names, or the ordinal kind
   exists.
6. No document counts a countersign, a fill, a ruling count or an
   inspection count as positive reputation.
7. Every claim path has a notice with a cure deadline before it, an
   evidence period, a ruling period per rung, a named final rung and a
   finality window; a held reservation has no exit but a ruling or a
   two-signature settlement.
8. Every third party a requirement admits (resolver, inspector, register,
   mutual member) is admitted by stake, accreditation or negative record,
   never by volume.

## 4. Fold-in map

Which repository plan document receives what. Gates reuse the drafts' gates
as rewritten on 2026-09-25.

### loopmarket

| receives | what |
|---|---|
| `README.md` | the makers' disclaimer (D10) |
| `CLAUDE.md` invariants | U11 extension; v6 as one bump; `requires.counterparty`, `requires.legs`, `requires.resolvers` in the fail-closed list; rule 4's clocks |
| `docs/plans/P3-guarantee-coupling.md` §4b | item 3 (`credentials` field) replaced by the `cred/` sidecar and the gate (D7); item 2's received/as-described split noted as the countersign shape for inspected goods; §3 rule 1 gains `possession`, `photo-match`, `registry-transfer` once rostered; certificate-final inspection (D4) |
| `docs/plans/P2-loop-selection.md` §4a | open decisions (a) and (d) answered (D7) |
| `docs/plans/P3-release-and-reclearing.md` | options as obligations under the ladder (D6); item claims end with the window; `settle(split)` and `extendClaim` beside cancel and release (D3) |
| `docs/plans/P4-privacy.md` | `cred/` is public by design (a matching gate); the photo commitment; no salted ids; who paid the attester in the statement |
| `docs/plans/THREATS.md` | T5's indemnity rule applied to cover (D3); exit by silence closed (D10's C1); register liveness as denial of service on issuees, priced by `max_root_age`; the item denial-of-sale attack closed by D5; puppet resolvers and inspectors answered by `accept` (D7) |
| `ROADMAP.md` | the `register` role; absence and consistency proofs on the leg path; `claimOnly`, `assign` to any key, `settle(split)`, `extendClaim`; argument-only operators; the identifier kind as an upstream dependency; also fix ROADMAP's stale "factbond as resolver" item (live since 0.12.0) |
| new plan doc, from `options-and-cover.md` | options and cover (as rewritten, with D3, D4, D6) |
| new plan doc, from `items-and-ownership.md` | items (as rewritten, with D5, E1, E2) |
| new plan doc, from `counterparty-gate.md` | the gate (as rewritten, with D7, D8, E3, E4, G1, G2) |

### factbond

| receives | what |
|---|---|
| `contracts/Assertions.sol`, `docs/DESIGN.md` | F1: per-assertion window with bounds and default; per-fact-type escalation value (D10) |
| `docs/plans/evidence-policy.md` | the `self-knowable` class; evidence period, ruling period per rung, evidence fee, challenger cap, finality window, notice with cure deadline, suspension as a register record, "unproduced evidence is grounds to rule against", the named final rung per class, the adjudicator class per category, the impartiality formality (D2, D7, D10) |
| `docs/plans/mechanism-design.md` | the evidence fee beside the stake; the cap relative to the reservation; the doubled-stake re-challenge and the finality window reconciled with §6's reopening rule; adjudicators' fees, deposits and ledger entries; the loss view as part of the calibration ledger (D2, D9) |
| `docs/plans/records-and-anchoring.md` | the correction feed payload gains the asserter; the loss view derived from `Asserted ⋈ Refuted` with look-back; the ruling record's content (D2's C5) |
| `docs/plans/insurance-products.md` | the claimant-asserts route with presentation, assignment and netting (D3); cover gives; the mutual as the first pooled form with F1–F8 (D9); the discretionary product (D10) |
| `docs/plans/netting-and-reserves.md` | the geared reserve applied to cover gives; per-fact notional caps carried over; fail-closed at the cap, no calls; order of recourse and risk-rated contributions (D9) |
| `docs/plans/ontodag-first.md` | the coverage give required for the credential pack once bonded offers match on it |
| `docs/plans/THREATS.md` | defamation on a permanent store (specific disputes only); dormant-key harvesting (closed by D1/D2); griefing by cheap disputes (the evidence fee and cap); ruling-count washing (closed by C3); ambiguity paying the drafter (closed by D-3) |

### ontodag and ontodag-core

| receives | what |
|---|---|
| `src/ontodag/dimensions.py`, `docs/DIMENSIONS.md` | the identifier kind, registry 4.3, kind node outside the prelude |
| `docs/plans/EVOLUTION.md` §3 | the ordinal decision, with loopmarket's condition chain and the door scale as the two verticals |
| ontodag-core packs | `warranty`, `inspection`, `survey`, `certification`, `qualification`, `diploma`, `accreditation`, `theft`, `stolen-goods`, `recall`, `serial-number`, the batch sense of lot, `surety-bond` (§3 of the asks); the occupations pack unchanged; the legal-vocabulary check (the assurance drafts' `ontodag-asks.md` §3b) |

### assurance (new repository)

| receives | what |
|---|---|
| charter | as rewritten: components A–E and E′ (the mutual's rules); A0–A5; D8's two scales; D3's product-layer duties (presentation, retention, notice duty as monitoring, contra proferentem, tail cover); D4's certificate-final inspection and `scheme`; D10's trigger rule and the disclaimer |
| first gate A0 | the dentist case end to end on memory stores: a practice's attested statement about a dentist's key backed by the practice's deposit, `cred/`, the gate; revoked, suspended, expired-before-window, unaccredited, silent-register and floor-not-free each refused; the rejection record enumerates |

## 5. Decision record

| # | decided | outcome |
|---|---|---|
| 1 | 2026-09-25 | D1: one shared deposit in v1; the deposit may be another maker's (the practice); the practice's statement is *attested* |
| 2 | 2026-09-25 | D5: per-maker rule in v1; priced exclusivity next, field fixed now |
| 3 | 2026-09-25 | D9: mutual first; a specialist insurer is the one-member case |
| 4 | 2026-09-25 | D10: negligence excluded from v1; a mutual's discretionary product; no placeholder rung; good-practice review, not compliance |
| 5 | 2026-09-25 | names: `option/`, `operator-argument`, the repository keeps `assurance` (`surety` the best single alternative) |
| 6 | 2026-09-25 | D7: `kinds` plus `min_bond` is the only OR; cross-category alternatives via recognition edges |
| 7 | 2026-09-25 | family A (clocks): all five; rule 4; A2 reshaped to three record-checkable clocks |
| 8 | 2026-09-25 | family B (first rung, small claims): all |
| 9 | 2026-09-25 | family C (silence, final judge, ruling record): all; C4 reshaped: acceptance by stake and negative record, never by count |
| 10 | 2026-09-25 | family D (cover conditions): D-1 to D-4; D-5 deferred |
| 11 | 2026-09-25 | family E (inspection, scheme): all, E2 in C4's form |
| 12 | 2026-09-25 | family F (the mutual's rules): all eight; closes D9's admission question |

Applied without a decision: G (registers as logs, short lifetimes, the loss
view's look-back and priceability, who paid the attester) and H
(vocabulary). Remaining before fold-in: the ontodag legal-vocabulary check
(the assurance drafts' `ontodag-asks.md` §3b) and the fold-in itself (§4).

## 6. Sequencing

Ordered by what unblocks what; nothing blocks current development.

1. **factbond F1** (per-assertion window, bounded) and the evidence-policy
   data of D2 (`self-knowable`; evidence, ruling and finality periods; fee
   and cap; notice with cure deadline; suspension; the final rung and
   adjudicator class per category). Small; unblocks credentials and long
   claims.
2. **loopmarket escrow small changes:** `claimOnly` at `reserve`, `assign`
   to any key, `settle(split)`, `extendClaim`, per-leg claim seconds, the
   periods from the term, the accepted-resolver check, a held reservation
   released only by ruling (D3, D7, D10). Small; unblocks cover.
3. **loopmarket v6 and the gate** (D7, D8 door scale, D4's `legs`): R1–R4
   as rewritten, with `cred/`, `notice/` with cure deadlines, the `register`
   role, `register_roots` in the proposal, the loop record and `Beat`,
   `verifyAbsence` and consistency proofs on the leg path, `accept`, the
   enumerating rejection record, argument-only operators. **assurance A0**
   against it. This is the piece that answers the motivating question.
4. **ontodag:** the identifier kind (registry 4.3) and the ordinal decision.
   Unblocks items and the door scale's naming.
5. **loopmarket options and items** (D6, D5): C1–C3 and I1–I2 in memory,
   then C4/I3 on chain across `BeatClearing` and `LegVerifier`.
6. **cover end to end** on the collateralised escrow (D3, D4): the `insure`
   grammar with presentation, composed cover, certificate-final inspection,
   a certified claim paying under the indemnity rule net of assignment; then
   **factbond's reserve applied to cover gives** and the mutual with F1–F8
   (D9).
7. **assurance A1–A5.**
