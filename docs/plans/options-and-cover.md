# loopmarket: claims — options that clear, cover that settles

Status: design, 2026-09-23; corrected and decided 2026-09-25; entered
loopmarket's plan corpus 2026-09-25 from the assurance drafts. Dn, A1–G5
name decisions in `credentials-cover-and-options.md`. Proposed, from the conversation with Peter: an option is a **hold**
on a plain offer, written by clearing and lapsing with time (Peter's
alternative, adopted); options and cover share **one model** with **two
exercise routes** (clearing for a holder-triggered claim, settlement through
the escrow for an event-triggered one; agreed); cover starts fully
collateralised (the assistant's ordering, not a recorded decision). Open:
transferable rights (§3.8), pooled cover (factbond's, plan D9), and the plan
decisions listed in §9.

## 1. Why

Goods and services that must be inspected or tried — the apartment viewed,
the car taken to a mechanic — cannot clear the moment a loop closes. The rule
that keeps loopmarket's properties: **clear only certainties; trade the
uncertainty as a separate, positively-priced thing.** The buyer first buys
the *right to decide* (an option: the apartment held for her), decides after
the inspection, and exercises — an ordinary clearing, re-verified from scratch
(U3). Nothing uncertain enters a circulation; nothing cleared is reversed.

Event-triggered claims — insurance, warranty, a refund if the mechanic
certifies a defect — are the same kind of thing, a claim on a writer's
commitment, but exercised without counter-performance.

## 2. One model, two routes *(applied plan D6, 2026-09-25)*

A **right** is recorded at clearing, keyed per (offer, loop), exclusive, on
part of the writer's capacity, with an expiry after which it returns to the
writer by itself. It is one *model* with two records in two places: an
option record in the book, a reservation on chain. ("Claim" is reserved for
the escrow's claim period; "hold" for the resolver's hold on a reservation.)

```
right: { on: offer | deposit,
         trigger: holder | event(E),
         window: TimeWindow,
         quantity }
```

| | holder-triggered (option) | event-triggered (cover) |
|---|---|---|
| on | a plain offer P | a `Bond` deposit in `LoopEscrow` |
| recorded as | an option record `option/<P>/<loop>` | a reservation (existing) |
| reduces | `available = qty − fills − active option records` | `free = held − reserved` (existing) |
| exercised by | **clearing** a new leg on P (a trade with counter-performance) | **settlement**: the insured asserts the trigger, factbond certifies, the resolver releases to the insured |
| default at expiry | P available again, no write | deposit back to the writer after the quiet period |

The split is principled: a payout has no counter-performance, and a clearing
leg needs a positive price on both sides (U1, U5); forcing a payout through
clearing would need a fictitious price and a bond on the payout itself.

## 3. Option records — options on plain offers

### 3.1 Records (v6)

P is an ordinary v5 offer; **nothing about P changes.** The option O is a new
offer by the same maker W:

- `give`: a `Thing` whose concepts describe what the holder will be able to
  take — `option(apartment item(h) ljubljana-center)`. Matching is one-way,
  give within want, so a want `option(apartment ljubljana)` takes it.
  *(corrected 2026-09-25)* `option` is **not** a `descriptive` head: in
  loopmarket that marker opts a geo/time dimension head out of the two-way
  handover reading, and `_mark` refuses a non-dimension head
  (`ontology.py` `declare_descriptive`). A head taking a conjunction is
  ontodag's graph kind, and the only graph-kind heads loopmarket declares
  today are operators. `option` is therefore a **non-operator graph-kind
  head**, which falls into `satisfies`' plain containment branch: plausible,
  but a new, untested path (`_consistent` skips graph terms). C1 must cover
  it.
- `want`: `Tokens(W, premium)` — U1 holds.
- new field `underlying: <id of P>`;
- new field `exercise: TimeWindow`.

A new offer field means v6 (U2): v5 re-encodes byte for byte; `from_record`
dispatches on `"v"`.

### 3.2 The option record

When O's leg clears, the same commit (one root, U3) writes

```
option/<P>/<loop>  ->  { option: <id of O>, until: O.exercise.end, qty }
```

The record never changes. Its effect is a function of time: **active while
now < until**. Deterministic against the clearing's clock and the chain's
block time.

### 3.3 While an option record is active

- P is admissible only to O's **current holder** (the wanter of O's fill,
  §3.8 for transfers).
- **W's exit is priced, not void** *(applied plan D6)*. The cleared option
  leg is an obligation like any other under P3's ladder: W may cancel it
  permissionlessly at the ladder's price, paid to the holder from the
  deposit on O, and the option record then ends. A withdrawal of P recorded
  while the record is active is read as that cancellation. A no-show at
  exercise is non-performance on P, covered by P's deposit and the holder's
  `requires.point`. No unpriced lock exists anywhere.
- `available(P)` subtracts the optioned quantity: a second option on P, or
  any other leg on P, finds nothing (or only the free remainder of a
  divisible P).

### 3.4 Checks at the option leg

*(corrected 2026-09-25)* The presence, ownership and withdrawal checks live
in `MockClearing.submit` step 1 and in `rehearse` (what `ChainClearing` and
`challenge` run), against the current book; `verify_leg` only dispatches
the match checks. The package touches both.

- P is present under the pinned root, made by W (= O's maker), unwithdrawn;
- `P.valid` covers `O.exercise`;
- `available(P) ≥ qty` after fills and active option records;
- the ordinary match and requirement checks on O's leg.

### 3.5 Checks at the exercise leg

- now ∈ `O.exercise`;
- an active option record on P names O;
- the leg's wanter is O's current holder;
- the ordinary `check_match` / composition / `meets` on P's leg.

A filled exercise consumes the record's quantity as a fill.

**Exercise is a clearing, so it needs a closing loop** *(applied plan
D6)*. For a token-priced P the loop is two legs and trivial. For barter the
option is a right of exclusivity, not a guaranteed trade: the holder may
fail to find a loop that closes within the window, and the premium bought
only that nobody else could take P meanwhile.

### 3.6 Expiry

After `until` the option record stops having effect: P is simply available
again. No reinstatement write, nobody obliged to make one. (A withdrawal W
recorded while the record was active was already a priced cancellation,
§3.3; nothing is pending at expiry.)

### 3.7 Divisible offers

Optioning 200 kg of a 1000 kg give is a hold on 200: the partial-fill
arithmetic (`OfferRegistry.available`, `taken`) gains one term. Step and
floor apply to the optioned quantity as to a fill (`Thing.takes`).

### 3.8 Transferable rights (deferred)

The holder H resells: a give `option(…)` with a holder requirement proving H
holds O; current holder = the end of the chain of fills of rights in O under
the pinned root; one transfer per holding (the U11 family). The fill chain is
the book-native ownership ledger — no token contract. Build when someone
needs it.

### 3.9 Variants without new machinery

- **Put / buyback** (a return right): P is W's *want*; same fields.
- **Premium credited against price:** W prices P lower.
- **Non-delivery after exercise:** settlement failure, covered by W's bond on
  P and the holder's `requires.point`, as any leg.

## 4. Cover — through the escrow

### 4.1 Shape

The insurer I posts a give `insure(subject(…) peril(…) period(…) limit(…)
deductible(…))` carrying a v5 `Bond` deposit (the limit), wanting a premium
on I's scale. *(corrected 2026-09-25)* The term is one graph-kind term with
nested role heads; ontodag's graph kind has no positional arguments, so
`insure(car, theft, 2026)` is refused (the assurance drafts' `ontodag-asks.md` §2). It clears
alone or composed with the thing. It **cannot** be "an operator leg, like
`transport`" as the operator algebra stands: `declare_operator` requires two
ends of one dimension and `check_composition` returns nothing for an
operator that moves nothing (`matching.py`, "not an operator give, or one
that moves nothing"). Composition of legs that move nothing is a new shape,
decided in plan D4.

### 4.2 At finalize

`escrow.reservations_for` (existing) reserves the deposit's share to the
insured: resolver factbond (already the live default when a resolver is
set, loopmarket 0.12.0), window the cover period, claim period covering it.
*(corrected 2026-09-25)* "No change to the reservation logic" holds for the
contract, not for the Python side: `reservations_for` derives the window
from the want's first `time(…)` term and applies one `claim_seconds` to
every leg, so a per-policy cover period and claim period need a change there
and in the CLI. Two contract paths the draft had not addressed:

- **`countersign` returns the whole reservation to the giver.** An insured
  who countersigned anything on the cover leg would void her cover. The
  cover reservation is never countersigned (plan D3).
- **`cancel` after the window begins pays the whole reservation to the
  wanter.** So "cover already sold cannot be withdrawn" (§4.4) is true in a
  stronger form: an insurer's cancel is a full payout.

Then *(applied plan D3, 2026-09-25)*:

- **the reservation is marked `claimOnly`** at `reserve` (set by
  `reservations_for` from the give being under `insure`): `countersign` is
  refused on it; it settles only by `resolve` or by the quiet `settle`;
- the cover period and claim period come from the `insure` term's
  `period(…)`, and `claim_seconds` is per leg;
- no claim: `settle` after the claim period returns the deposit to I;
- a claim: **the insured asserts the trigger** on factbond ("the gearbox
  failed on D", "the seller did not have title as of D") as a fresh
  assertion with a normal window; `assert_` calls the consumer's `hold` on
  the reservation; I is the natural disputer; certification calls
  `resolve`. I never asserts the covered fact at cover time, so nothing
  pays twice. I's "did they check" is visible in its underwriting legs
  (`requires.legs`, D4), not in a second bonded assertion;
- **indemnity:** `resolve(toWanter)` pays `min(limit, provable loss) −
  deductible`, and provable loss is bounded by the value of the legs that
  pinned the insured edge (loopmarket THREATS T5, factbond F3); the
  resolver applies it; partial payouts exist, the rest to I.

*(applied practice review, 2026-09-25)* Conditions the resolver enforces,
and the clocks:

- **fair presentation** (plan D-1): the `insure` term names a
  `presentation(…)`, a hash of the facts the insured declared (the
  inspection history of `item(h)`, the insured's loss-view entries, the
  door-binding source); a false presentation fact is a self-knowable fact I
  may assert as a bonded negation, and a certified refutation reduces the
  payout proportionately;
- **assignment before payout, and netting** (D-2): the resolver requires
  the insured's claim on the giver's reservation to be assigned to I before
  a cover `resolve(toWanter)`, and nets any amount already recovered;
- **contra proferentem** (D-3): a term the adjudicator finds unadjudicable
  is construed against I; "unresolved" never releases the reservation to
  I, and a term refused as unadjudicable forfeits a validity slice;
- **a held reservation never quiet-settles** (C1): once a claim is
  asserted, only a ruling releases it; each rung rules within its period or
  the claim moves up (A3) to a final rung that is a named, bonded
  adjudicator, never a token vote (C2), named at policy start;
- **the resolver is acceptable to both sides** (C4): I names it; the
  insured's requirement accepts it by name, accrediting root, deposit
  floor or absence of reversals, never by a count of rulings;
  `reservations_for` checks this at clearing;
- **a negotiated settlement** (B2): `settle(split)` signed by the insured
  and I ends a claim without a ruling; a clean settlement, not a default;
- **the first ruling pays** (A4); reopening within the finality window on
  new evidence or at double the stake; after it, only fraud or a
  contradicting primary source.

### 4.3 Limits accepted for v1

- **Fully collateralised only** (`free = held − reserved`). Pooled cover — the
  capital efficiency specialist insurers live on — is **factbond's**
  *(corrected 2026-09-25, plan D9)*: its geared payout reserve applied to
  cover gives, fail-closed at the cap; not loopmarket's, and not
  assurance's beyond the underwriting requirements.
- **One resolve per reservation.** A policy allowing several claims needs
  several reservations (or a remaining-cover counter, later).
- **The cover period and the claim period are matched terms** *(applied
  plan A1)*: the give declares its maxima, the want asks for at most that,
  the catalogue carries a default and an outer cap per category. Tail
  cover (D-4) is `LoopEscrow.extendClaim(key, seconds)`, callable by the
  giver only and sold as a give.
- **Objective triggers only:** E and F must be catalogue-expressible,
  adjudicable claims. Taste is not insurable, and neither is negligence
  *(applied plan D10)*: "the work was bad" is a judgement, not a fact the
  ladder can certify. Professional indemnity reduces here to fact cover on
  licence validity and on inspection reports; conduct claims are a mutual's
  discretionary product outside the escrow (plan D9, D10).

### 4.4 Cover already sold cannot be withdrawn

A reservation holds it. An insurer may stop *selling* (its register, `counterparty-gate.md`);
it cannot cancel cover on a cleared leg (a cancel after the window begins
pays the whole reservation to the insured). *(relabelled, plan D-4)* Per-fill
reservation is **claims-made-and-reported within the claim period, for
occurrences in the cover period**, the strict professional-lines form, not
"occurrence-basis": a claim not asserted within the claim period is gone,
and the insured's relief is tail cover (`extendClaim`).

## 5. What the solver and clearing must know

- `OfferRegistry.available` subtracts active option records; `SolverAgent` and
  `MockClearing` pass the chain's holds beside `chain_fills` (same plumbing).
- The `loop/` record of an option loop carries the hold; the snapshot at a
  pinned root shows it. *(corrected 2026-09-25)* The loop record is
  versioned (`"v": 1`); a new field is a loop-record bump, which
  `P4-privacy.md` §5 already anticipates.
- `graph`/`selection`: a held offer has capacity only for its holder's
  exercise leg.

## 6. Contracts

### 6.1 The `finalize` remainder gap — shipped *(corrected 2026-09-25)*

The gap this section described (two concurrent beats could overfill one
offer because `finalize` never saw the offer's quantity) was closed in
loopmarket 0.12.0 on 2026-09-23, an hour after this draft was written. What
exists now: each committed fill carries its offer's cap (`Fill{offer, n, d,
capN, capD}`); `finalize` checks every fill against what the chain recorded
since, including predecessor contracts' fills, and cancels the whole beat
without slashing if any no longer fits, refunding the bond; a false cap, a
want committed as less than whole, or a give fill differing from its leg
convicts on challenge (`BeatClearing._capFault`, comparing against the
quantities `LegVerifier.verify` returns). Gates met: the two-beat race test
and a live Gnosis run. Package C0 is dropped.

One consequence for §6.2: the leg verifier moved out of `BeatClearing` into
`LegVerifier` (EIP-170), and `LoopVerifier._requireTakes` reads fills
through an `IFills` callback. Holds on chain therefore span two contracts.

### 6.2 Holds on chain

- `finalize` records holds from the beat beside fills:
  `_held[P] += qty until t`, with the option id;
- the remainder check in `LoopVerifier._requireTakes` subtracts active
  holds: either a second callback beside `IFills.filled`, or holds folded
  into what `filled` returns for the duration of the hold;
- the exercise leg's holder check is structural: an inclusion proof of O's
  fill naming the wanter, and the hold naming O. *(corrected 2026-09-25)*
  `LoopVerifier` today reads only `offer/<id>` inclusion proofs; a `fill/`
  inclusion proof is a **new proof type** on chain, not evidence it already
  reads.

### 6.3 `LoopEscrow.assign`

The reservation's `wanter` is fixed at `reserve` (confirmed: no setter,
nothing named `assign` exists). Add `assign(key, to)`, callable by the
wanter only: redirects the payout. *(corrected 2026-09-25)* Subrogation
reads: the **harmed wanter**, after the insurer pays her, assigns her claim
on the giver's deposit reservation to the insurer, and the insurer makes
that assignment a condition of payout. It is not "the insured's own bonds":
a practitioner cannot assign reservations on his own deposits, since their
wanter is the harmed party.

*(applied practice review, 2026-09-25)* Three more escrow functions of the
same size:

- **`assign` to any key** (plan B4): a claim on a reservation may be
  assigned by its wanter to anyone, not only to an insurer. A claim too
  small for the victim to pursue is pursued when it can be sold (Iceland's
  transferable claims); the assignee's own ledger record checks abuse.
- **`settle(split)`** (B2): a negotiated release signed by the
  reservation's wanter and the deposit's giver; nobody else can trigger it.
- **`extendClaim(key, seconds)`** (D-4): the giver alone may lengthen a
  reservation's claim period; tail cover in one primitive.

## 7. Invariants

U1 (O and P uniform) · U2 (v6; v5 byte for byte) · U3 (option records, holder and
availability re-derived from clearing's own book) · U4 (pinned roots; the
clock is clearing's injectable, not part of U4) · U5 (premium and price
positive) · U6 (deterministic; holds keyed and iterated in sorted order) · U7
(an unknown `option(…)` term or an absent hold meets nothing) · U9
(quantities and premium exact) · **U11 extended:** a hold names a present
loop; fills plus active option records on P never exceed its quantity; one exercise
per hold (the last clause is this draft's addition, not in U11 today).

## 8. Work packages and gates

| # | Package | Gate |
|---|---|---|
| ~~C0~~ | `finalize` cap check (§6.1) — **shipped in 0.12.0, 2026-09-23** | met: `test_two_beats_racing_over_one_book_cannot_overfill`, live Gnosis gate |
| C1 | v6 record: `underlying`, `exercise`; `option` as a non-operator graph-kind head in `triangle.od`'s seed (one v6 bump shared with `counterparty-gate.md`, plan D7) | v5 corpus re-encodes byte for byte; v6 round-trips; unknown `v` raises; a graph-kind non-operator give matches by containment |
| C2 | holds in registry + clearing (§3.2–3.6) | option then exercise clears; second option refused; W's exit during the hold is priced at the ladder (plan D6), not void; after expiry P clears to anyone; divisible 200/1000 |
| C3 | solver awareness (§5) | the baseline never proposes a leg on held capacity except the holder's exercise |
| C4 | holds on chain (§6.2), across `BeatClearing` and `LegVerifier` | an exercise by a non-holder is convicted by `challenge`; an honest one verifies; a `fill/` inclusion proof verifies on chain |
| C5 | cover via escrow, end to end (§4): `claimOnly`, presentation, matched periods, acceptable resolver | local EVM: cover cleared, finalized, reserved; the insured asserts, I disputes, a certified claim pays `min(limit, loss) − deductible` net of what the giver's reservation paid, after assignment; a countersign on a `claimOnly` reservation is refused; a false presentation reduces the payout proportionately; a leg whose resolver is outside the insured's accepted set does not clear; quiet period returns when no claim was asserted; a held reservation is never released by the quiet path |
| C6 | `LoopEscrow.assign` to any key, `settle(split)`, `extendClaim` (§6.3) | only the wanter can assign, to anyone; payout goes to the assignee; a split needs both signatures and nobody else can trigger it; only the giver can extend, and only lengthen |
| C7 | CLI: `option ID [--until T] [--premium X]`, `exercise OPTION`, `options` | G-style CLI gates; an `examples/apartment.loop` viewing → option → exercise |

C1–C3 are the in-memory core; C4–C7 follow.

## 9. Open

- Transferable rights (§3.8) — when needed.
- Whether a hold may turn P public to others *before* expiry when the holder
  declines early (a release call by the holder) — cheap to add.
- Knock-in hybrids (a holder-triggered claim exercisable only if E) — later.

Decided in `credentials-cover-and-options.md` and **applied here on 2026-09-25**: D3
(§4.2), D4 (§4.1; the composition shape itself is loopmarket's
`operator-argument` marker and `requires.legs`, specified in the plan), D6
(§2, §3.2–3.6), D9 (§4.3), D10 (§4.3). Extensions of the same record that
D6 leaves open, none blocked by it: a category or a whole loop as
`underlying`; non-exclusive options; Bermudan windows; a firm price without
exclusivity ("hold this price till Friday").

The practice review's amendments (`commercial-practice-review.md`, decided
2026-09-25) are applied in §4.2 to §4.4 and §6.3: A1, A3, A4, B2, B4, C1,
C2, C4, D-1 to D-4. Deferred: D-5, staged release of a reservation.
