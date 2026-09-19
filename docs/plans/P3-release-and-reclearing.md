# loopmarket — release prices and re-clearing

Status: direction set by Peter, 2026-09-18 (late evening), from his notes
on bonds and cancellations; nothing built. Companion to
`P3-guarantee-coupling.md` §3a (the slashed-bond doctrine, whose floors this
document reinterprets), `P2-loop-selection.md` (whose packer the re-clear
reuses), `P2-batch-auction.md` (the beat this extends past clearing) and
`THREATS.md`. Cross-repo: factbond's coupling document carries the escrow
asks.

## 1. The neutral point

A maker's required floor (`requires.bond`, and `requires.cancel` before the
leg's window — the v5 record) is to be read, and set, as its **true neutral
point**: the amount, in the bond's asset, at which it does not mind whether
the leg is performed or cancelled with that payment. Set it too high and the
maker would rather be cancelled; too low and it is left feeling short. The
device has a name: a **self-assessed buyout price with a forced-sale right**
(Harberger 1965; Posner & Weyl, "Property Is Only Another Name for Monopoly",
2017, the COST). Their discipline against overstatement is a tax; ours is
admissibility — a counterparty must reserve at least your price to be matched
with you at all (`P2-loop-selection.md` §4a), so overstating shrinks who can
trade with you and understating gets you bought out cheaply.

## 2. Permissionless cancellation

Because the price is the maker's own indifference, **anyone willing to pay
it may cancel that maker's side of a cleared leg** — before the window at
the `cancel` price, after it at the no-show price — and the maker is, by its
own declaration, not made worse off. The giver's own cancellation (§3a
rule 9) is the special case where the payer is the giver. Consequences:

- **Hysteresis by choice.** A high neutral point buys a stable position; a
  low one invites re-clearing. Each maker sets how much stability it wants,
  which is the roadmap's "dynamic pricing quantizes to the beat" doctrine
  with the repost right extended to third parties at the maker's own price.
- **A buyout is a release, not a failure.** The released maker keeps a clean
  record; what changes hands is the payer's payment. U12's statistics need a
  `release/` distinct from a default, and the reputation of a released giver
  is untouched.
- **Churn is a chosen exposure.** A maker who dislikes being bought out
  states a higher price; the register (`THREATS.md`) should record buyout
  churn as a vector priced by the target, not griefing.

## 3. Re-clearing: cancel and replace in one transaction

A solver that sees a substantially better circulation may cancel the whole
or a part of a cleared one, pay every displaced maker its neutral point, and
clear the replacement — **as one transaction**, so no maker is left with a
half-unwound loop (U11 extended past clearing). Rules:

1. **A partial cancellation must re-balance every affected maker in the same
   transaction.** Cancelling one leg orphans the two makers at its ends;
   the replacement must be a valid circulation over old-minus-cancelled plus
   new legs together, verified as any circulation is (potentials exist, U3).
2. **Every displaced maker not re-served is paid its neutral point**, in the
   bond's asset, and its own requirements bound nothing further.
3. **A displaced maker re-served in the new set is owed nothing** — served by
   a give that satisfies its own terms and meets its own requirements, it
   is not worse off by its own declaration.

## 4. The Pareto re-match: first, and free

Rider A cleared with driver B, both far apart, the only option at the time.
A minute later driver C offers and rider D wants a lift, also far apart —
but C is near A and B near D. The re-match A–C, B–D serves everyone; by
rule 3 nobody is owed anything. **This is the first piece to build,** and
it needs no escrow and no payment channel:

- *Selection:* cleared offers re-enter the packer as candidates on the
  condition that every displaced offer stays filled in the new set, scored
  by the same objective (`selection.pack`); the fairness filter reads
  references as before.
- *Records:* a loop that supersedes another — `loop/<new>` naming the loops
  it replaces, the old fills moved to the new loop under one commit (U11:
  every present loop holds every fill it names, none orphaned). A v5
  loop-record bump, to be done once.
- *Chain:* `BeatClearing` records fills per offer, so a re-match through the
  same offers is convicted as a double fill unless the new beat
  **supersedes** the old one; within the challenge window that is a
  contract verb (the superseded beat's pending fills released, its bond
  returned); after finalization fills are permanent, so re-clearing past
  the window needs a `release(offer, loop)` recorded with its payment —
  escrow-scale work, with the escrow.
- *Makers:* `watch` tells each displaced maker its counterparty changed;
  handoffs are re-sealed to the new counterparty.

## 5. Compensation: what a bond is, and what it is held in (revised the same night)

Peter's corrections, in the order they came, replaced everything this
section first said about "the bond's asset":

- **A personal unit cannot be a bond.** It is internal — it cannot be paid
  to anyone — and it is instantaneous, for the clearing that consumes it;
  it cannot travel in time, so it cannot sit in escrow. A bond in the
  giver's own unit would be an IOU redeemable only through the defaulter's
  own future gives, which is the credit the bond exists to avoid; and it
  cannot be converted without either a market in that token (U14 forbids
  it) or a loop that happens to exist at the moment of failure.
- **The loop is tried first.** On a failure, before anything held pays out,
  the solver looks for a compensating circulation: the wanter receives one
  of its own wants worth at least the lost leg plus its **switch cost**,
  declared on the wanter's own scale, from the defaulter's other gives or
  anyone's. All on the wanter's scale; no asset needed; not guaranteed to
  exist when the ride does not come — so a first attempt, not the only one.
- **Compensation is what the wanter will still want later.** A wanter's
  ordinary wants are for now (the ice cream, already bought by then; not
  holdable anyway); compensation is for later and must be durable and
  holdable — a gold coin, BTC, a stablecoin, whatever *she* trusts against
  inflation. The protocol names none of them: her requirement names the
  asset categories she accepts, each with her price per unit on her own
  scale, beside her neutral and cancellation points on that scale.
- **Conversion happens once, at clearing, on private scales.** The giver's
  deposit has a value on the giver's scale; the wanter's neutral point has
  a value on hers and a price per unit for each asset she accepts. A leg is
  admissible when the deposit's category falls under one she accepts
  (the catalogue, as for any want) and the quantity reserved for this fill,
  in the asset's own unit, covers her neutral point at her price for it.
  Two conversions each inside one maker's scale, one comparison in the
  asset's unit; no shared numeraire ever appears. "Later" is then no
  conversion at all: the escrow hands over the reserved quantity of the
  asset she named. Her one exposure is her own valuation drifting, which
  choosing durable assets bounds.
- **Escrowability is relative to who holds — the escrow is a service.**
  An escrow agent is a storage operator whose output is bound to a
  ruling; in general it is a maker with an offer: what it holds, for how
  long, released on what condition, at what fee. **Medium term, only the
  smart-contract agent is built** (§5a); physical custody, agents with
  fees on their own scale and agents that can themselves fail go to the
  end of the roadmap, where that recursion belongs.

## 5a. The crypto escrow: a smart contract as a maker (medium term)

Doable, with two rules where a contract differs from a keyed maker:

1. **A contract signs by state.** It has an address but no key, so it
   cannot sign a feed or a detached offer signature (U8). It registers the
   ids of its standing offers in its own storage from its own code, and a
   reader authenticates an offer whose maker is a contract address against
   that mapping instead of a signature; the record may live in anyone's
   book. It announces its book by calling `LoopBookRegistry.announce`
   itself (`msg.sender` is then the contract).
2. **A contract takes no personal tokens.** A fee on its own scale would be
   bookkeeping meaningless to code, and a zero-priced leg would put a zero
   rate into the loop (U5). So the **fee-less contract escrow is a
   condition on the giver's give, not a leg in the value arithmetic**: the
   record says "this give is backed by escrow contract E holding asset A,
   quantity Q"; clearing verifies the wanter accepts A and the quantity
   reserved for this fill covers her neutral point; the deposit is the
   giver's obligation at settlement. A contract that charges an on-chain
   fee is a bridge leg and comes later.

The contract is small: `deposit(loop, fill, token, amount)` by the giver's
key; `release(loop, fill)` on the arbiter's ruling of failure, paying the
wanter's key the reserved quantity (the cancellation quantity if the giver
cancelled before the window); `refund` on the wanter's countersignature of
delivery, or after the window with no claim. The wanter's key is the one it
announces and signs with, so payouts have a destination without a new
identity. Reservation per fill and the cancellation quantity are its
bookkeeping by construction; `BeatClearing` gains a verdict hook the escrow
listens to, the arbiter hook's shape. **No conditional leg shape in
clearing**: the release is the escrow's settlement behaviour, not a branch
in the circulation.

**Built 2026-09-19** (`contracts/LoopEscrow.sol`, `src/loopmarket/escrow.py`,
`loop deposit`), with two departures from the sketch above that the
accepted record forced: the deposit is keyed by the *offer id*, not by
(loop, fill), because `Bond.escrow` is in the record before any loop
exists and a divisible give's one deposit backs every fill it gets; and
the reservation per fill is the arbiter's call (`reserve(offer, loop,
amount)`) until the verdict hook lets the clearing contract's finalization
reserve directly — the giver's withdrawal therefore waits a notice period
and takes only what no fill holds. `release` pays the ruled amount and
returns the excess of the reservation; `refund` is the wanter's own
transaction or the arbiter's after the window. Native coin and ERC-20.

**What the v5 record becomes — held until this is read:** the giver's
`bond` = (asset category, quantity, escrow contract), marked as backing and
never clearable as a give; the wanter's `requires` = neutral point,
cancellation point (both on her scale), and the accepted asset categories
each with her price per unit. Matching and the verifier's quantity check
move onto the reserved asset quantity.

## 5c. The neutral point over lead time: a ladder (Peter, 2026-09-19)

A fixed number cannot express what a cancellation costs, because the cost
depends on *when*: a change two months out is a note in a calendar, a
change in an hour finds the family dressed for the performance. Two parts
of that cost Peter named — the mental transaction cost of re-planning, and
the way plans entangle over time — both rise as the handover approaches.
The shape that expresses it, and that a human can state in one line, is
the one the roadmap reserves for price schedules, applied here: **a ladder
over lead time**. The neutral point is a short list of `(lead, amount)`
points on the maker's own scale, interpolated linearly between them and
read at the lead time between the cancellation and the leg's handover
window — "a week before, 5; the day before, 20; at the door, 50; in
between, proportionally." Ordered points make it monotone by
construction; rationals keep it exact (U9); the cancellation record's
time is the book commit's or the chain's block, so a payout is one exact
read of the ladder. Today's two numbers are the two-point ladder: the
`cancel` amount is its far end, the no-show amount its near end.

Consequences:

- **No formula for humans.** The CLI derives the ladder from the two
  amounts a maker already gives. **The horizon is a fraction of the lead
  at posting** (Peter, 2026-09-19) — the time between posting and the
  window's start, so a performance booked two months out and a box for
  tomorrow each get a ladder scaled to their own wait; a fixed week was
  the wrong unit. **A few ladder types, not many**, each a fixed set of
  knees at fractions of that span, chosen by `set ladder TYPE`:
  `linear` (the default: the cancel amount at the horizon, the no-show
  amount at the window, straight between), `late` (flat at the cancel
  amount for most of the wait, rising over the last fraction — the
  performance, where the cost arrives with the dressing-up), `early`
  (rising over the first fraction, then flat — the chartered bus or the
  catering, where the preparation is the cost), `flat` (the cancel
  amount until the window, then the no-show amount). The fractions are
  the CLI's constants, and **the record carries only the resulting
  points**: no type name, no fraction, no formula enters the protocol,
  and a maker who wants a shape of its own writes the points. The far end
  above zero *is* the mental transaction cost.
- **No new admissibility logic.** The counterparty's reserved bond must
  cover the ladder's maximum, the no-show amount — exactly what the gate
  checks today; only the payout reads the ladder.
- **Fixed at clearing.** The ladder is part of what the counterparty
  agreed to when its bond was reserved against it; it cannot move
  unilaterally afterwards. Before clearing, raising it is tombstone and
  repost, and an agent that manages a maker's ladders manages its offers.
- **Symmetric**, each side of a leg carrying its own ladder for the
  other's cancellation; and it composes with rule 10 of §3a — the cheap
  far end is what makes early notice worth giving.

This replaces the single `cancel` number in the held v5 change: `requires`
carries the ladder (two points by default), the no-show amount being its
last point.

## 5d. The v5 record — ACCEPTED by Peter 2026-09-19, built the same day (consolidates §5a and §5c)

*Built:* `schema.Acceptance`, `schema.Bond`, `schema.Requires(point, ladder,
accepts, oracles, escrows)`, `matching.meets` in every check, the verifier's
structural half, the CLI settings; the escrow contract itself is next.

Today's v5 (built 2026-09-18) carries, on every offer, `bond` as a bare
rational in an unnamed asset and `requires = {bond, cancel, oracles}`,
the two floors likewise in that unnamed asset. The proposal replaces both
so that no asset is named by the protocol, every amount a maker states is
on its own scale, and the cancellation cost is a ladder.

**The wanter's side — `requires`**, what she asks of any counterparty on
a leg through this offer:

| field | meaning | unit |
|---|---|---|
| `point` | her neutral point on a no-show — her whole reliance: payments to the leg's other counterparties, the substitute, the inconvenience | her own scale |
| `ladder` | the cancellation cost over lead time: ordered `[[lead, amount], …]`, lead in seconds before the leg's handover window, amount ≤ `point`, linear between points, the last point at lead 0 (§5c); absent means `point` at every lead | seconds; her own scale |
| `accepts` | the durable, escrowable asset categories she takes as compensation, each with her price per unit on her scale: `[[category, unit, price], …]` (§5) | catalogue term; asset unit; her own scale |
| `oracles` | witness types she accepts; empty means any | names |
| `escrows` | escrow contract kinds she accepts (§5a); medium term `"contract"` only; absent means any | names |

**The giver's side — `bond`**, what it holds against its performance:

| field | meaning |
|---|---|
| `asset` | the deposit: a category, a quantity, a unit — under one of the categories a counterparty accepts (the catalogue decides) |
| `value` | what the deposit is worth to the giver, on its own scale (its bond "in its own unit") |
| `escrow` | the escrow contract's address that holds it (§5a); the deposit is marked as backing, never a give a solver could clear |

**Admissibility at clearing (matching, and the verifier's structural
half):** the deposit's category falls under one the wanter accepts, its
unit is that entry's unit, and the quantity reserved for this fill —
`asset.qty × taken / the give's qty`, the whole for a want, an
indivisible give or an operator's run — is at least `point / price` for
that entry. Two conversions, each inside one maker's scale; one
comparison in the asset's unit; nothing converts later. A payout on a
ruling is the reserved quantity (or the ladder's amount at the
cancellation's lead time, divided by the same price), in the deposit's
asset, to the wanter's key.

**Versioning.** v5 is a day old and carries no live data worth keeping, so
this is a change *within* v5, not a v6: the ids of the handful of v5
offers in scratch books change, nothing else. A v4 offer is untouched.
`Requires` becomes `point, ladder, accepts, oracles, escrows`; `bond`
becomes `asset, value, escrow`. Both sides keep `requires` (a giver may
require a bonded wanter too).

**An example** — Amara wants a ride, one run, 40 on her scale, and would
accept BTC or a euro stablecoin as compensation:

```
"requires": {"point": "50", "ladder": [["604800", "5"], ["86400", "20"], ["0", "50"]],
             "accepts": [["btc", "sat", "1/2000"], ["stablecoin-eur", "EUR", "1"]],
             "oracles": [], "escrows": ["contract"]}
```

A driver whose `bond` is `{"asset": ["stablecoin-eur", "60", "EUR"], "value": "45", "escrow": "0x…"}`
reserves the whole 60 EUR for this one-run fill; her point of 50 at 1 per
EUR needs 50 EUR; admissible. A driver holding 30 000 sat at her price of
1/2000 per sat covers 15 on her scale; not admissible for her.

**What is not in the record:** the ladder type, the horizon fraction, the
escrow's terms (its own offer), any asset name the protocol knows. *The
CLI's default* (Peter, 2026-09-19): a maker who gives only numbers deposits
and accepts the configured chain's gas token at 1 per unit on its scale —
xDAI while Swarm settles on Gnosis, which every maker already holds for
gas — written explicitly into the record like any other acceptance.

## 5b. Payments for buyouts

The entrant's bid for a buyout (§2–§3) is paid the same way: in an asset the
displaced maker accepts, through the escrow, or in kind through the loop
(§5, the switch cost) — never from the surplus of the loop it improves
(U14). What a solver cannot do is fund buyouts from that surplus; its own
compensation stays the endogenous spread leg (`P2-batch-auction.md` §7).


## 6. What this changes in the corpus

- `P3-guarantee-coupling.md` §3a: the floors are neutral points; the giver's
  cancellation is one case of §2; rules 1–10 stand.
- `P2-loop-selection.md`: re-clearing is selection over cleared legs with
  release costs in the bond's asset — §4a's factor hook is not the place;
  the costs are constraints on admissibility, not weights.
- `P2-batch-auction.md`: the beat extends past clearing — a superseding beat
  within the window.
- `THREATS.md`: buyout churn, priced by the target.

## 7. Strategies outside, primitives inside (Peter, 2026-09-18)

The solver options above — which loops to break, whether an entrant's bid
covers the prices, when to re-clear, the auctions — **stay outside
loopmarket**, in solver species (circulator and its kin): solvers propose,
clearing verifies, loopmarket imports no strategy. What loopmarket owes them
is a small set of primitives, in this order:

1. **The delta proposal** (pure Python; first). A proposal is legs to add
   *and fills to release*, verified as one thing by `MockClearing` and
   `ChainClearing`: every released fill exists; the maker of a released
   fill is re-served by the new legs or paid its neutral point; the new
   legs verify as always with the released capacity counted available;
   the commit is atomic — fills moved and added under one root. Today's
   proposal is the case with no releases. This alone makes the Pareto
   re-match (§4) possible for an external solver.
2. **Two records.** `loop/<new>` naming the loops it supersedes, and
   `release/<offer>/<loop>` carrying who paid what to whom — distinct from
   a fill and from a failure (U12's statistics stay clean). U11's check
   learns that a superseded loop's fill may be absent when a successor
   fill or a release stands in its place.
3. **One contract verb, no money in it.** A beat may name unfinalized
   beats it supersedes; at its finalization those are cancelled, their
   pending fills dropped, their bonds returned. Checks: the same pins, not
   finalized, within the window. The verifier already reads the neutral
   point from a v5 record; nothing new is parsed.
4. **The paid release is the escrow's** (P3; the crypto escrow of §5a).
   The escrow holds the payer's bid in an asset the payee accepts, pays
   the maker's key, and calls one authorized `release(offer, loop)` on the
   clearing contract — the arbiter hook's shape — so the clearing
   contract's checks stay few and the money lives in the contract built to
   hold it.

## Open problems

- **The payment channel** for §5: who holds the entrant's bid, when it is
  released to the displaced makers, and its atomicity with the new clearing
  — the escrow's, with factbond.
- **Supersession on chain** past the window: `release(offer, loop)` with its
  payment; the fill authority learns to un-fill.
- **The neutral point under partial fills:** the reserved share per fill
  (§3a rule 8) is what a buyout pays for that fill.
- **Physical escrow** — custodians of goods, agents with fees on their own
  scale, agents that can fail — is deferred to the end of the roadmap.
- **Timing:** a re-clear during a leg's handover window pays the no-show
  price; the boundary is the window's start.

## What this document does not promise

- It never prices a personal unit against any asset; every payment is in
  an asset the payee named, at the payee's own price, converted once at
  clearing; the protocol names no asset.
- It does not weaken clearing's finality: a release is a recorded,
  paid transfer, not an undo.
- The Pareto re-match is the only part claimed buildable without the
  escrow; everything paid waits for it.
