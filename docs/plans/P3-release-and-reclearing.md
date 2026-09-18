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

## 5. Payments: who pays the neutral points, and in what

"The better circulation must be sufficiently better to cover all the
bonds" is **not computable from surplus**: surplus is numeraire-free (U14),
the neutral points are in the bond's asset. It becomes computable once the
payer is named: **the entrant who wants in — or a solver on its behalf —
bids in the bond's asset**, and the re-clear is admissible when the bids
cover every displaced maker's price under §3. Everything paid is then in one
asset by declaration and no conversion is ever made. That is the auction
Peter names: a position may be bought at its holder's price, and the money is
the entrant's, never the loop's. What a solver cannot do is fund buyouts from
the surplus of the loop it improves; its own compensation stays the
endogenous spread leg (`P2-batch-auction.md` §7).

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
4. **The paid release is the escrow's** (P3, factbond). The escrow holds
   the payer's bid, pays the maker's key, and calls one authorized
   `release(offer, loop)` on the clearing contract — the arbiter hook's
   shape — so the clearing contract's checks stay few and the money lives
   in the contract built to hold it.

## Open problems

- **The payment channel** for §5: who holds the entrant's bid, when it is
  released to the displaced makers, and its atomicity with the new clearing
  — the escrow's, with factbond.
- **Supersession on chain** past the window: `release(offer, loop)` with its
  payment; the fill authority learns to un-fill.
- **The neutral point under partial fills:** the reserved share per fill
  (§3a rule 8) is what a buyout pays for that fill.
- **Timing:** a re-clear during a leg's handover window pays the no-show
  price; the boundary is the window's start.

## What this document does not promise

- It does not price anything in personal tokens against the bond's asset;
  every payment here is in one asset by the payee's declaration.
- It does not weaken clearing's finality: a release is a recorded,
  paid transfer, not an undo.
- The Pareto re-match is the only part claimed buildable without the
  escrow; everything paid waits for it.
