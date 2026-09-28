# loopmarket — credentials, cover and options: the cross-repository plan

Status: design, decided 2026-09-25 (the twelve decisions Peter took with the
assurance drafts), amended by dated edit since. **The full text lives in
factbond:**
[`factbond/docs/plans/credentials-cover-and-options.md`](https://github.com/petfold/factbond/blob/main/docs/plans/credentials-cover-and-options.md).
One copy, so the decisions cannot drift apart between the repositories
(until 2026-09-28 both carried the whole text and every amendment had to be
made twice). This file is loopmarket's index to it: which decisions are
carried out here and where their detail lives. The labels used across the
plan corpus — D1–D10 and the sub-decisions A1–A5, B1–B5, C1–C5, D-1–D-5,
E1–E4, F1–F8 and G1–G5 — are the full text's.

loopmarket's detailed designs are
[`options-and-cover.md`](options-and-cover.md),
[`items-and-ownership.md`](items-and-ownership.md) and
[`counterparty-gate.md`](counterparty-gate.md); the record the plan was
checked against is [`commercial-practice-review.md`](commercial-practice-review.md).

## The decisions, and where each is carried out

| # | decision | carried out |
|---|---|---|
| D1 | A credential statement is backed by a deposit and reserved per relying leg | here: `cred/`, the deposit check in the gate, per-leg reservations (`counterparty-gate.md`) |
| D2 | Disputes with clocks: burden shift for self-knowable facts, suspension on silence, a cheap first rung, bounded costs, a paid and ledgered judge, a final ruling | factbond (policy, procedure, ledger); here: `notice/` with its cure deadline and the `suspended/` read (R6, R4) |
| D3 | Cover: the insured asserts the trigger; one payout through the reservation; indemnity, presentation, assignment, netting; never countersigned | here: the escrow's acts and the cover grammar (`options-and-cover.md`, C5), factbond as resolver |
| D4 | Argument-only operators; composed cover; inspection made final; what checking means, published | here (`options-and-cover.md`, D4's gate) |
| D5 | The per-item rule is per maker; cross-maker exclusivity priced or witnessed, later | here (`items-and-ownership.md`) |
| D6 | Options are obligations under P3's ladder; exercise needs a loop | here (`options-and-cover.md`) |
| D7 | One requirement shape, one statement shape, registers as logs, one v6 bump | here (`counterparty-gate.md`, R1–R5) |
| D8 | Identity binding is a door scale and a set of issuance sources | here as witness types (R7); the binding itself is hansa's |
| D9 | Placement; the mutual as the first pooled form, with its rules; the loss view | factbond and hansa |
| D10 | Objective triggers; the discretionary product; final rungs; the standard the plan is held to | all; the makers' disclaimer in the README here |

Amended since 2026-09-25, each dated in the full text: the burned slice of
a loser's stake gave way to the adjudicator's fee and the asserter's
concession; the notice step belongs to a claim on a reservation, never to a
dispute of a live factbond assertion; the boolean escalation value is
superseded, since a lapsed rung's case moves up with the stakes held and
nothing resolves without a ruling.

What lands in loopmarket's documents (the README's disclaimer, CLAUDE.md's
invariants, P2, P3, P4, THREATS, the ROADMAP) is the full text's §4, under
"loopmarket"; the sequencing is its §6, refined by the development sequence
of 2026-09-25 and amended 2026-09-29 (the ROADMAP's P3b "order of work":
E1 built; R1 before E2, which reads v6; E3 paired with factbond's redeploy,
after factbond isolates consumer reverts).
