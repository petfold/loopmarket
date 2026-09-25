# loopmarket — commercial practice review: do the mechanisms encourage what merchants learned?

Status: reference, entered loopmarket's plan corpus 2026-09-25 from the
assurance drafts; its amendments were decided the same day and are woven
into `credentials-cover-and-options.md`. Originally written for decision. This is the review plan D10 asked for:
not compliance with any jurisdiction, which is the makers' concern, but
whether decisions D1–D10 encourage the practices that merchants, private
courts and mutuals converged on over centuries because they were more
efficient, safer and produced fewer conflicts, or whether they re-learn a
mistake. Three literatures were read against the plan: the historical
private-ordering record (the medieval law merchant, the Maghribi and
Genoese traders, the Hanse, the diamond and cotton trades, Iceland and
Somalia, Friedman, Benson, Bernstein, Greif, Ellickson, Ostrom, the
origins of surety and of mutual insurance); modern commercial practice
(documentary credits, demand guarantees, construction security and dispute
boards, statutory adjudication, arbitration, sale-of-goods inspection and
notice rules, insurance principles, credit bureaus, accreditation,
UNIDROIT and Incoterms); and contemporary digital ordering (eBay, Taobao,
Escrow.com, Kleros, UMA, Augur, Nexus Mutual, reputation-system research,
certificate revocation and transparency logs). Claims that could not be
confirmed from a primary or reliable secondary source are marked
*(to verify)*. Sources are listed in §7.

## 0. Verdict

**The spine is right.** Every one of the plan's load-bearing choices has a
long precedent, and none of D1–D10 flatly re-learns a documented mistake:

| plan | the practice it encodes | precedent |
|---|---|---|
| clear only certainties; the gate reads documents, never performance; objective triggers only (D3, D7, D10) | the payer deals in documents, not goods; bright-line rules over "reasonable" | UCP 600 Arts. 4–5, 14; Bernstein's cotton and diamond studies |
| collateral substitutes for identity; the deposit reserved per relying leg (D1) | a liquid, pre-posted security solves the enforcement problem that reputation alone cannot | Milgrom–North–Weingast on transfer technology; Greif on why the Genoese scaled and the Maghribis did not |
| the party whose collateral is at stake does the checking; third-party backing preferred to self-bonds (D1's ladder) | Roman law preferred a solvent surety to a pledge; the relying parties founded Lloyd's Register; TÜV was founded by the inspected as an inspection-and-insurance body | ius commune suretyship; Lloyd's Register 1760; TÜV 1866 |
| the fail-closed gate reading `revoked/` and `suspended/` before clearing (D7) | the law merchant's judge kept a record of unpaid judgments and querying it was the price of using the court | Milgrom–North–Weingast 1990 |
| suspension, not seizure, on silence; money moves only on a ruling (D2, §0 rule 3) | ostracism curable by the party's own act; grace periods replacing impounding | Benson; Greif 2006 on the community responsibility system; the diamond trade's preference for suspension over expulsion |
| the claimant asserts with a bond; the natural disputer has a stake (D3) | the demand must state the breach; a wrongful call is priced | URDG 758 Arts. 15, 23; UMA's assert-and-dispute, which the plan improves by sizing the bond to reliance |
| indemnity from provable reliance, never identity (D3) | insurance is indemnity; no interest, no cover | Marine Insurance Act 1906 ss. 1, 4 |
| bonded, specific accusations; admission and exclusion as bonded statements by members (D2, D9) | an insider who accuses puts his own standing at stake; the sponsor guarantees the newcomer | Greif 1993; the Diamond Dealers Club's sponsor guarantee |
| negative-only, adjudicated records; nothing positive from settlement (U12, D9) | published defaulter lists; negative-only reporting disciplines better than full-file where identities are cheap | GAFTA defaulters list; Padilla–Pagano; Friedman–Resnick on cheap pseudonyms |
| the mutual with peer vetting, nested with reinsurance; conduct judged discretionally outside the fact machine (D9, D10) | club retention, pool, reinsurance; the omnibus rule; expert determination for facts, arbitration for conduct | P&I clubs; Nexus Mutual; Ostrom's nested enterprises |
| the vocabulary pack as opt-in private law bound by edition (D7, U4) | terms gain force by being named in the contract and applied by adjudicators | Incoterms; UNIDROIT Principles |

**The gaps are all by omission, and they fall into six families.** Practice
puts a clock and a stated consequence of lapse on *every* actor; the plan
clocks two (the asserter's evidence period, the claimant's claim period).
Practice keeps small valid claims worth bringing with a free first rung and
bounded costs; the plan starts every dispute at the bonded, fee-bearing
stage. Practice always has a final judge and never lets silence or delay
release security; the plan's "no ruling still escalates" is unbounded.
Practice conditions cover on the insured's disclosure and prevents double
recovery in the payout itself; the plan's resolver cannot. Practice makes
inspection final and publishes what checking means; the plan records the
report hash and stops. Practice specifies who judges a mutual's claims, the
order of recourse and how members leave; the plan leaves the mutual's
governance open. §2 gives the amendments, one per gap, mapped to decisions.

**Six divergences from practice are deliberate and should be stated as
such** (§3), so nobody later reads them as oversights: full transparency of
rulings, no positive credit from history, no supplementary calls, holding
security until a ruling rather than "pay now, argue later", never
reversing a cleared loop even for fraud, and never a vote for admission or
claims.

## 1. What the record says, by decision

Short, with the precedent that bears on each decision and the verdict.
Full citations in §7.

**D1, deposit-backed statements reserved per relying leg.** Encouraged by
the whole surety tradition and by FIDIC's performance security, which stays
valid through the defects period and may be called only for listed events.
Missing: practice caps the bonded party's exposure. FIDIC's defects
notification period defaults to 365 days and may not be extended beyond two
years; CISG Art. 39(2) bars claims after two years absolutely. In D1 the
wanter alone chooses the claim period, so a long period is an unpriced lock
on the giver's deposit, against the plan's own rule 2. Also missing:
practice runs a *short* discovery-to-notice clock inside the long outer
period (CISG Art. 39(1) "within a reasonable time after he has discovered
it"; GAFTA's 21 days; FIDIC 20.2's 28 days), because evidence decays and the
giver cannot mitigate a fault it has not been told of.

**D2, disputes, burden shift, suspension.** Encouraged by Benson (speed,
simple procedure, ostracism as sanction), the cotton trade (three days to
respond, ex parte ruling after notice, decisions in 39 days on the papers),
UCP's preclusion rule, ICC's security for costs and costs-follow-the-event
(the evidence fee E is both in one datum), the diamond trade's fee refund
to the winner, and Ellickson's point that a costly self-help sanction is a
credible signal of a real grievance. Missing on five counts. (i) No clock
on the neutral: UCP gives the examiner five banking days, statutory
adjudication 28 days, dispute boards 84; the plan says "no ruling still
escalates" with no period. (ii) No cheap first rung: 85 per cent of diamond
disputes settle in mandatory conciliation; eBay resolves the majority
amicably and 90 per cent in software before any adjudicator; Ellickson's
groups escalate from gossip through self-help before law. Every credential
dispute in D2 begins at the bonded stage. (iii) Small valid claims may not
be worth bringing: Milgrom–North–Weingast's condition (8), the judgment
"must also be large enough to encourage the injured party to appeal.
Otherwise, information about cheating will never reach the law merchant";
eBay found even free complaints under-filed and the seller a repeat player
with a systematic advantage. In D2 the harmed one-off wanter pre-pays a
stake priced by the asserter's confidence plus E, which for a small leg can
exceed the reserved slice she can recover. (iv) Nothing says who
adjudicates a self-knowable credential claim or how the adjudicator is
paid and held to account; merchant courts used peers of the trade, and the
law merchant's judge stayed honest because his income depended on continued
use. (v) "New evidence is new by definition" means no ruling is ever final;
dispute boards close after a 28-day notice of dissatisfaction and expert
determination is final absent manifest error or fraud; Benson notes the
merchant courts forbade appeals for speed. Reality.eth's answer to judging
novelty is to price it: a repeat challenge at double the stake.

**D3, cover: claimant asserts, one payout, indemnity, never
countersigned.** Encouraged strongly: UCP autonomy, URDG's statement of
breach, the indemnity principle, retention held by a neutral and released
by lapse (better than construction practice, where retention is chronically
withheld). Missing, structurally: insurance's principal defence is
non-disclosure. Under the Insurance Act 2015 the insured must fairly present
every material circumstance and the remedy is proportionate; in D3 the
insured asserts the trigger, the insurer can only dispute the trigger's
truth, and `resolve` fires on certification, so an insured who concealed a
prior loss or a failed inspection collects in full if the gearbox really
failed. Also: "the insurer makes assignment a condition of payout" is not
something the insurer can do when `resolve` fires on a ruling, and a wanter
can currently be paid from the giver's reservation and the cover
reservation for one loss. Marine Insurance Act s. 79: the insurer is
subrogated on payment; the assured is not compensated twice. Two lesser
points: the plan's cover is "claims-made-and-reported within the claim
period for occurrences in the cover period", the strict professional-lines
form, not "occurrence-basis" as `options-and-cover.md` §4.4 says; and practice sells tail
cover (an extended reporting period) at expiry. And Augur's invalid-market
scam: when an ambiguous term resolves "unresolved" and the security returns
to the drafter, ambiguity pays the drafter; the lex mercatoria's answer is
contra proferentem.

**D4, argument-only operators, composed cover, `inspect`.** Encouraged: the
`inspect` leg is GAFTA's registered superintendent and the report hash its
certificate; P&I clubs require entry surveys; Lloyd's Register's surveyors
were the historical answer to the verifier's dilemma. Missing: GAFTA makes
the loading-port certificate *final* as to what it certifies, so the buyer's
remedy on those attributes runs against the inspector, not the seller, and
the inspector's exposure is bounded; nothing in D4 says an inspected
attribute is final between wanter and giver. Lloyd's Register forbade a
surveyor any interest in a ship he inspected and rotated surveyors between
ports; nothing in D4 requires an `inspect` giver to be independent of the
inspected leg. ISO 17065 and UCP's ISBP both publish *what checking
consists of*; an `accredit/` record says only who may issue what.

**D5, per-maker item rule; D6, options under the ladder.** Encouraged:
Ellickson's "live and let live" for overlaps that harm no one; the UK
holding-deposit rules (capped premium, fixed window, grantor's exit fully
refundable, reasons in writing) are D6's shape; Escrow.com sells inspection
periods that end by accept, reject or lapse. Missing, minor: catalogue
defaults for inspection periods and claim periods per category (Taobao
sizes escrow release by delivery mode), so wanters are not inventing
numbers; the rejection path's cost allocation as terms.

**D7, the requirement and statement shapes; registers.** Encouraged
strongly: the pinned `cred/` sidecar is OCSP stapling, fail-closed is
must-staple, mirrors as content-addressed snapshots are CRLite, and
`max_root_age` is the short-lived certificate that the web moved to after
pull revocation failed (Mozilla; CA/B Forum's 47-day lifetimes by 2029).
Pinning every path root in a public proposal is stronger than Certificate
Transparency's gossip, which saw almost no deployment. Missing: an absence
proof is only as good as the completeness of the root it is taken against,
and a heartbeat proves freshness, not completeness. Certificate
Transparency's answer is append-only logs with consistency proofs between
tree heads, monitors, and misissuance as a provable fact (which is what
caught Symantec's 108 misissued certificates). Also: UCP Art. 16(c) requires
one refusal notice listing every discrepancy, because 60 to 70 per cent of
first presentations fail on formalities and a second round should cure
them all; the gate's rejection record should enumerate every failing step.
And credit bureaus age negatives (FCRA's seven years); the loss view is
permanent.

**D8, binding as a door scale and issuance sources.** Encouraged: the
community responsibility system depended on identity-certifying
organisations; the Hanse required heirs to present a certificate from their
city of birth; PayPal's seller protection scales the required evidence with
value (signature confirmation above a threshold). Minor: let a requirement
name a door level by leg-value threshold.

**D9, placement; the mutual first.** Encouraged: TÜV 1866 confirmed from
the primary source as inspection and insurance in one body founded by the
inspected; P&I clubs and friendly societies as the shape; Ostrom's nested
enterprises. Missing on six counts, all about the mutual's own rules. (i)
Admission by member vouching alone reproduces the Maghribi closure, where
efficient outsiders were refused because membership was by affinity; the
Genoese scaled with impersonal contracts. Friendly societies and fire
mutuals required *both* a proposer and a survey of the risk, and refused bad
risks outright. (ii) Vouching has no upside: the Diamond Dealers Club's
introducing member guarantees the newcomer's liabilities *and* earns 1 per
cent of every transaction the newcomer makes; without that the pool will
not grow. (iii) No order of recourse: P&I stacks member retention, then the
pool, then reinsurance, and "pay to be paid" makes the member discharge the
liability first; Roman law's beneficium excussionis made the creditor sue
the principal before the surety, and the paying surety took the creditor's
claim. (iv) No answer to heterogeneity: the community responsibility system
died when large members who could self-bond withdrew from subsidising small
ones; Somali dia-paying groups are bounded above by internal conflict over
unfair burdens. (v) No intermediate sanction and no appeal from exclusion:
Somali groups restrict a member before renouncing him; the Hanse learned in
1511 that unappealable exclusion destroys legitimacy and drives members to
foreign courts; the diamond trade suspends rather than expels because
expulsion is an end game. (vi) Who judges claims is unspecified: Nexus
Mutual replaced open member claim-voting with a named three-person Claims
Committee and a cool-down in November 2025, citing "long-standing member
concerns around incentives, coordination, and decision quality"; P&I
discretionary claims are decided by a directors' committee with recorded
decisions. Warning from Ogilvie and the Hanse: guilds were also cartels;
never let the mutual restrict members' dealings outside it.

**D10, objective triggers; no placeholder rung.** Encouraged: expert
determination for facts ascertainable from documents, arbitration for the
rest, is exactly the plan's facts-versus-conduct split; the P&I omnibus
rule ("absolute authority to pay any discretionary claim in full, in part
or not at all", no reasons, final) is the discretionary product to the
letter. Missing: every working system has a *final* rung (Kleros's General
Court, Augur's fork, Reality's arbitrator, the DAAB's arbitration); the
plan's escalation-with-refund has no end. And the March 2025 Polymarket
resolution, where one holder with a quarter of the votes swung a
seven-million-dollar market against the facts and no refund followed, is
the lesson on what the final rung must not be: a token-weighted vote where
the value at stake exceeds the cost of the vote.

## 2. Proposed amendments, by family

Each is written as a change to a decision, for Peter to accept, amend or
refuse. They are ordered by how much they change.

### A. A clock on every actor (D1, D2, D3, D10)

Practice's most consistent lesson. Proposed fourth rule for plan §0:
*every step has a clock, and lapse has a stated consequence.*

- **A1. The claim period is a matched term with a default and a cap.** The
  give declares its maximum claim period (or a price per period); the want
  asks for at most that; the catalogue carries a default per category
  (FIDIC's 365-day shape) and an outer cap (the two-year shape). A wanter
  who wants longer pays for it in the price, as with everything else.
- **A2. A discovery-to-notice clock inside the claim period.** A claim is
  admissible only if the fault was notified to the giver within N days of
  discovery (policy data per category; CISG's "reasonable time", GAFTA's 21
  days). The notice is a record (`notice/` already exists); the claim
  assertion cites it.
- **A3. A ruling period beside the evidence period.** Each rung must rule
  within a fixed period (policy data; 28 days is the statutory-adjudication
  benchmark, 84 the dispute-board one) or the claim moves up automatically
  to the next rung; the last rung is named and bonded (see C).
- **A4. The first ruling moves the money; reopening is "argue later".** A
  ruling executes at once through the escrow, as statutory adjudication and
  dispute boards do; reopening on new evidence stays, within a **finality
  window** per fact type after which the ruling and its ledger entry close
  except for fraud or a contradicting primary source. Reality.eth's rule
  answers the "is it new?" question without a ruling: a repeat challenge is
  admissible without the novelty test at double the stake.
- **A5. Fixed evidence periods for `self-knowable` claims**, in days
  (order of 7 to 14), with ex parte ruling on the record once notice has
  run, as the cotton trade does.

### B. A cheap first rung and small claims worth bringing (D2, D3)

- **B1. Rung zero: notice and cure.** A free notice from the relying party
  to the giver, with a short cure window, before any bonded dispute; public
  only if unanswered or refused. The plan's "silence counts only after
  notice" is half of this; the other half is that the notice is a record
  with a cure window and most matters end there (85 per cent of diamond
  disputes; the DAAB's avoidance role).
- **B2. A two-signature negotiated settlement on every reservation,
  including `claimOnly` cover.** `settle(split)` signed by both parties,
  nobody else able to trigger it; a clean settlement under rule 3, not a
  default. This is where eBay resolves most of its cases and where
  Escrow.com's accept-or-reject lives.
- **B3. Cap the challenger's total outlay for a claim routed from a
  reservation** at a fraction of that reservation (stake plus evidence fee
  ≤ k × reserved slice, k < 1), and refund E on any ruling in the
  challenger's favour, including a partial one. Otherwise Milgrom's
  condition (8) fails and small cheating never reaches the record. Keep the
  winner's share as the hunter's bounty.
- **B4. Generalise `assign`.** A harmed wanter may assign her claim on a
  reservation to *any* key, not only subrogate to an insurer. Iceland's
  transferable claims and Friedman's middlemen buying bundles of small
  claims are the reason: a claim too small for the victim to pursue is
  pursued when it can be sold. The buyer's own ledger record is the check on
  claims-buying abuse.
- **B5. One conduct rule on costs.** If the asserter produces evidence only
  after the notice period lapsed, E returns to the challenger even if the
  assertion holds. Prices stonewalling without giving the adjudicator
  discretion.

### C. Never exit by silence; always a final judge; the ruling as a record (D2, D10)

- **C1. A held reservation never quiet-settles.** Only a ruling releases
  it; the D10 "unresolved" value means the hold persists, never "release to
  giver". Without this a silent asserter exits with the bond at the end of
  the claim period, losing only matchability, which is nothing to a
  departing fraudster.
- **C2. Every policy class names a final rung, and it is a bonded, named
  adjudicator, never a token-weighted vote.** A class with no named final
  rung may not be used in any `requires` gate. Adjudicators for cover are
  named at policy start, as a dispute board is appointed at contract start.
- **C3. The adjudicator is paid per ruling and is in the calibration
  ledger.** Rulings later reversed on reopening count against the
  adjudicator. For `self-knowable` credential claims the policy names the
  adjudicator class per category (holders of the same credential under the
  same root, or the register itself), each holding a deposit: "did they
  check" applies to the judge too.
- **C4. An impartiality rule.** The policy refuses a resolver whose key is
  a party to the leg or the maker of the deposit at stake. Nothing today
  stops an insurer resolving its own cover claim or a practice ruling on
  its own dentist.
- **C5. The ruling record** carries the referred fact, the notice
  timestamps, both submissions' hashes or the lapse, the resolver's key, the
  category and the evidence-policy and pack versions applied, and a short
  reason naming the rule. The first two are what defeat fast rulings when
  absent (jurisdiction and natural justice are the only grounds that
  succeed against statutory adjudication); the versions are what make a
  ruling reusable as precedent (NGFA's decisions are searchable by rule)
  and what let the pack accumulate the case law that gave Incoterms their
  force. Evidence is disclosed to every rung on the escalation path, not
  only the first.

### D. Conditions the resolver enforces on cover (D3)

- **D-1. Fair presentation.** The `insure` term names a `presentation`
  (hash of the declared facts: the inspection history of `item(h)`, the
  loss-view entries of the insured, the door-binding source). A false
  presentation fact is a `self-knowable` fact the insurer may assert as a
  bonded negation; the resolver applies a certified refutation as a
  proportionate reduction of `min(limit, provable loss)`, the Insurance Act
  2015's remedy.
- **D-2. Assignment before payout, and netting.** The resolver requires
  `assign` of the wanter's claim on the giver's reservation to the insurer
  before a cover `resolve(toWanter)`, and nets any amount already recovered.
  This makes "the insurer makes assignment a condition of payout" true.
- **D-3. Contra proferentem.** A cover term the adjudicator finds
  unadjudicable is construed against its drafter: "unresolved" on a cover
  claim never releases the reservation to the insurer, and the drafter of a
  term refused as unadjudicable forfeits a validity slice. Augur's
  invalid-market scam is the cost of the alternative.
- **D-4. Tail cover.** `LoopEscrow.extendClaim(key, seconds)`, callable by
  the giver only (lengthening one's own exposure is safe), sold as a give:
  the extended reporting period in one primitive. Relabel `options-and-cover.md` §4.4 from
  "occurrence-basis" to "claims-made-and-reported within the claim period
  for occurrences in the cover period".
- **D-5. Staged release.** A reservation schedule (a fraction released at
  countersign, the remainder at claim-period end) as construction releases
  retention in halves; P3 §4b's received/as-described split already points
  to it.

### E. Inspection made final; what checking means, published (D4, D7)

- **E1. Certificate-final.** An `inspect` term flag `certificate-final`
  with the report enumerating the categories it certifies. A claim on a
  certified attribute is admissible only against the inspector's statement
  (its deposit or cover); a claim on an uncertified attribute against the
  giver; the inspector's liability cap is in its offer. This is GAFTA's
  rule and the basis of D10's professional-indemnity-as-fact-cover.
- **E2. Independence.** An `inspect` give is admissible only if its giver's
  key is not a maker or wanter on any other leg of the loop naming
  `item(h)`, checkable at clearing. The practice attesting for its own
  dentists is fine because its collateral is at stake; a neutral inspection
  must be neutral.
- **E3. A `scheme` hash** on `accredit/` records and credential categories,
  pointing at the check procedure in the vocabulary pack: ISO 17065's
  published scheme and UCP's ISBP. It makes "did they check" a recorded
  fact rather than a slogan.
- **E4. The gate's rejection record enumerates every failing step** of doc
  3 §4 in one record, so a re-presentation cures in one round.

### F. The mutual's own rules (D9, D10)

- **F1. Admission: both, priced.** An attester's or register statement (the
  survey) *and* a member's bonded, specific vouch (the proposer); an
  entrant without a vouch is admitted on a survey alone at a higher initial
  retention. This answers D9's open question with the friendly society's
  and fire mutual's rule, and avoids the Maghribi closure.
- **F2. Vouching pays.** The voucher receives a share of the vouchee's
  premiums or calls for the life of the vouch (the diamond trade's 1 per
  cent). Without an upside the pool does not grow.
- **F3. Order of recourse.** The member's own deposit reservation pays
  first, the pool in excess, reinsurance above; a pool payout for a member's
  fault takes an automatic claim on that member's deposit (the surety's
  subrogation; the borough's double indemnity). State the deliberate
  divergence: no supplementary calls, fail-closed at the cap, met by
  reinsurance and upfront capital, because capital cannot be called from a
  key.
- **F4. Heterogeneity.** Contributions risk-rated by each member's reserved
  exposure and loss record; free exit; sibling mutuals may form. This is
  what the community responsibility system lacked.
- **F5. Graduated sanctions and an internal second instance.** After a paid
  claim the mutual raises that member's retention or caps its cover before
  any exclusion; exclusion is a specific refutable statement (D2 already)
  with an internal review under a deadline, cover suspended, not cancelled,
  while review is pending.
- **F6. The claims judge is named.** A small committee of bonded members,
  excluded from ruling on their own vouchees, with a separate reversal and
  replacement power, a claimant deposit refunded on acceptance, a fixed
  decision window and a cool-down before payout; decisions are the bonded
  statements D10 already requires. This is what Nexus Mutual arrived at in
  2025 and what P&I clubs have always done.
- **F7. Rule changes by non-liquid member voice.** "Never a vote" stays for
  admission, exclusion and claims; for changes to the mutual's underwriting
  requirements and retention, members participate by bonded,
  non-transferable proposals, one member one voice. Ostrom's principle 3
  without transferable weight.
- **F8. No restriction on outside dealing.** The mutual never restricts
  members' trades outside it; "member of mutual M" is a wanter's optional
  requirement, never a market-wide one. The Hanse and the Memphis exchange
  show where the alternative leads.

### G. Registers and records (D7, D9)

- **G1. Registers are transparency logs.** Append-only, with consistency
  proofs between heartbeats; "two inconsistent roots signed by register R"
  is a specific, refutable fact about R (a dispute against its bond;
  removal as a trust root); anyone may monitor for the winner's share, and
  the insurer's watch duty is the monitor role. The current-status view
  (`status/`, `revoked/`, `suspended/`) sits on top of the log; a
  `suspended/` record is removed from the view when cleared, its history
  staying in the log.
- **G2. Short lifetimes.** Default statement `until` in weeks with cheap
  renewal (D7 already allows renewal without re-signing the offer); a
  register's declared cadence at or below the shortest plausible
  `max_root_age`.
- **G3. A look-back window on the loss view** (`max_loss_age` beside
  `max_root_age`), append-only underneath: nothing is deleted, nothing
  counts forever by default.
- **G4. The loss view is priceable.** It separates "refuted" from "did not
  perform on a ruling" (the diamond trade's point that what the market
  needs to know is whether a dealer abides by judgments); a dispute the
  asserter wins leaves no negative entry; every published ruling names the
  rule and fact type applied, so an honest misdescription is not read as
  fraud.
- **G5. Record who paid the attester** (subject or relier) in the
  statement: the disclosure that issuer-pays ratings fell back on.

### H. Vocabulary (plan §1)

Define *retention* (the insured's own share, paid first), *deductible* (the
amount below which no claim is paid) and *reservation* (the per-fill slice
of a deposit) side by side; the plan uses "retention" in the insurer's
sense while construction uses it for withheld payment. The pack states its
scope on its face, as Incoterms exclude title, price and breach.

## 3. Deliberate divergences from practice, to be stated in the plan

1. **Transparency.** The diamond trade keeps complied-with awards secret
   and publishes only non-compliance, because a large judgment for an
   honest misunderstanding reads worse than a small one for theft. The plan
   publishes every ruling. Keep transparency, which is an invariant, and
   make the record priceable instead (G4).
2. **No positive credit from history (U12).** Full-file credit reporting
   allocates better than negative-only, but only on identities that cannot
   be manufactured. With keys, positive history is wash-tradeable; the
   plan's positive signals are collateral and bonded vouching.
3. **No supplementary calls.** P&I clubs call capital from members when
   claims exceed estimates; the plan's pool fails closed at the cap, as
   Nexus does, because capital cannot be called from a key.
4. **Security is held until a ruling, not paid on demand.** Practice values
   the beneficiary's liquidity ("pay now, argue later"); the plan trades it
   for rule 3. With A3 and A4 the delay is bounded and the first ruling
   pays, which is most of what practice wanted.
5. **A cleared loop is never reversed, even for fraud.** CISG Art. 40 lifts
   the notice bar where the seller knew of the defect. The plan moves the
   fraud remedy to a bonded negation against the closed assertion and the
   loss view. Coherent, and `options-and-cover.md` should say so, so that nobody reads the
   claim period as a fraud shield.
6. **Never a vote for admission, exclusion or claims.** Ostrom's principle
   3 asks for member participation in rule-making; F7 gives it for rules
   only, without transferable weight, which is what Nexus Mutual's 2025
   retreat from stake-weighted claim votes confirms.

## 4. Where the sources disagree, and the resolution taken

- **Appeals.** Benson: merchant courts forbade appeals, for speed. The
  Hanse and the diamond trade: unappealable exclusion destroyed legitimacy.
  Resolution: facts get one time-boxed ladder with the first ruling paying
  and a finality window (A3, A4); exclusion from a mutual gets an internal
  second instance with a deadline (F5). The two are about different things.
- **Secrecy.** Resolved in §3 item 1.
- **Delete or annotate.** eBay annotates and never deletes; the diamond
  trade would delete a cleared suspension. Resolution: the ledger is
  append-only; status views are current (G1).
- **Sealed evidence.** D2 sends evidence to the adjudicator and publishes
  hashes; Kleros discloses evidence to every appeal panel. Resolution:
  disclosed along the whole escalation path, hashes public (C5).

## 5. Decisions for Peter

The amendments above are proposals. The ones that change a decision's
shape rather than add a term are:

1. **A1 and A2:** the claim period as a matched term with default and cap,
   and a discovery-to-notice clock. Without these, rule 2 is broken on the
   giver's side.
2. **A3, A4, C1, C2:** time-boxed rungs, first ruling pays, a held
   reservation never quiet-settles, a named bonded final rung per policy
   class. Without these, "looks insured, is not" returns by delay.
3. **B1 to B4:** rung zero, negotiated settlement, the challenger's cap and
   refund, generalised `assign`. Without these, small valid claims are not
   brought and the record stays empty where it matters most.
4. **D-1 and D-2:** fair presentation and assignment-before-payout in the
   resolver. Without these, the insurer has no defence against concealment
   and double recovery is possible.
5. **E1 and E2:** certificate-final inspection and inspector independence.
6. **F1 to F8:** the mutual's rules. F1 answers D9's open question.

Everything in G and H is additive and can be folded in without a decision.

## 6. Unverified items

FIDIC's customary 10 per cent performance security; the New York
Convention's current party count; the exact wording of UNCITRAL
Arbitration Rules Art. 42(1); the Dispute Resolution Board Foundation's
60 and 98 per cent figures are the industry body's own; Taobao's public
jury panel size (13 or 31 in different reports); UMA's roughly 1.5 per cent
dispute rate (secondary source); the claim that losing eBay disputants
trade more afterwards; Greif 1994 was read through a summary and Ellickson
through two reviews; the P&I "pay to be paid" wording is from a
practitioner source rather than a club rulebook; Nexus Mutual's Claims
Committee reform is dated November 2025 in its forum (NMPIP-261).

## 7. Sources

**Historical private ordering.** Milgrom, North & Weingast, "The Role of
Institutions in the Revival of Trade", Economics & Politics 2(1) 1990,
https://web.stanford.edu/~milgrom/publishedarticles/The%20Role%20of%20Institutions%20in%20the%20Revival%20of%20Trade,%201990.pdf
· Benson, "The Spontaneous Evolution of Commercial Law", Southern Economic
Journal 55(3) 1989, https://myweb.fsu.edu/bbenson/SEJ1989.pdf · Greif,
"Contract Enforceability and Economic Institutions in Early Trade: The
Maghribi Traders' Coalition", AER 83(3) 1993,
https://ideas.repec.org/a/aea/aecrev/v83y1993i3p525-48.html · Greif, "The
Birth of Impersonal Exchange: The Community Responsibility System and
Impartial Justice", JEP 20(2) 2006,
https://web.stanford.edu/~avner/Greif_Papers/2006%20JEP%20The%20Birth%20of%20Impersonal%20Exchange.pdf
· Greif, Milgrom & Weingast, "Coordination, Commitment, and Enforcement:
The Case of the Merchant Guild", JPE 102(4) 1994 · Zoomer, Urban History 52
(2025), https://doi.org/10.1017/S0963926824000130 · Wubs-Mrozewicz, German
History 29(1) 2011 (abstract) · Friedman, "Private Creation and Enforcement
of Law: A Historical Case", JLS 8(2) 1979,
http://www.daviddfriedman.com/Academic/Iceland/Iceland.html · Friedman,
Leeson & Skarbek, *Legal Systems Very Different from Ours* (Somali and
Romani chapters, drafts at daviddfriedman.com) · Friedman, *Law's Order*
ch. 18, http://www.daviddfriedman.com/Laws_Order_draft/laws_order_ch_18.htm
· Friedman, "Enforcing Rules",
http://www.daviddfriedman.com/Academic/Course_Pages/LegalSystemsWorkshop/EnforcingRules.htm
· Bernstein, "Opting Out of the Legal System: Extralegal Contractual
Relations in the Diamond Industry", JLS 21(1) 1992,
https://ideas.repec.org/a/ucp/jlstud/v21y1992i1p115-57.html · Bernstein,
"Private Commercial Law in the Cotton Industry", 99 Mich. L. Rev. 1724
(2001) · Bernstein, "Merchant Law in a Merchant Court", 144 U. Pa. L. Rev.
1765 (1996), https://scholarship.law.upenn.edu/penn_law_review/vol144/iss5/4/
· Ellickson, *Order Without Law* (1991), via Friedman's review
http://www.daviddfriedman.com/Academic/Less_Law/Less_Law.html · Ostrom,
*Governing the Commons* (1990); Cox, Arnold & Villamayor-Tomás, Ecology and
Society 15(4) 2010, https://www.ecologyandsociety.org/vol15/iss4/art38/ ·
Suretyship (ius commune), Max Planck Encyclopedia of European Private Law,
https://max-eup2012.mpipriv.de/index.php/Suretyship_(Ius_Commune) ·
Lloyd's Register case study,
https://globalcapitalism.history.ox.ac.uk/files/case13-lloydsregisterpdf ·
TÜV SÜD foundation years,
https://www.tuvsud.com/en-us/about-us/history/our-foundation-years-1866-1900
· Philadelphia Contributionship,
https://philadelphiaencyclopedia.org/essays/philadelphia-contributionship/
· Downham Benevolent Society rules 1794–1901,
https://www.downhamvillage.org.uk/index.php/downham-benevolent-society/rules-from-1794-to-1901
· P&I International Group overview,
https://www.doi.gov/sites/default/files/migrated/restoration/upload/Andrew-Bardot-Overview-of-International-Group-and-Clubs-1.pdf
· Swedish Club Rule 19 (omnibus) commentary,
https://www.swedishclub.com/rules-and-exceptions/part-two-comments/chapter-v-other-provisions/rule-19-omnibus-clause/comments-on-rule-19-omnibus-clause/
· Marsh on P&I discretionary claims,
https://www.marsh.com/en/industries/marine/insights/how-protection-and-indemnity-clubs-deal-with-discretionary-claims-and-disputes.html

**Modern commercial practice.** UCP 600 text, https://www.trans-lex.org/123309;
ICC guidance papers,
https://iccwbo.org/wp-content/uploads/sites/3/2023/03/Set-of-Guidance-Papers-on-Recommended-Principles-and-Usages-around-UCP600-Rules.pdf;
discrepancy rates, https://www.doccredit.world/discrepancy-rates-under-ucp-600/;
preclusion, https://www.mondaq.com/uk/compliance/101566/preclusion-under-ucp600-banks-beware
· URDG 758, https://www.tradefinance.training/blog/articles/urdg-758-key-concepts/;
FIDIC 4.2.2 and wrongful calls,
https://riskandcompliance.freshfields.com/post/102gq1n/performance-guarantees-resisting-a-demand-under-fidic-contracts;
Clifford Chance on on-demand bonds (Edward Owen v Barclays),
https://www.cliffordchance.com/content/dam/cliffordchance/briefings/2014/12/ondemand-bonds-is-the-lifeblood-of-international-commerce-still-flowing-freely.pdf
· FIDIC defects notification period,
https://www.fidicterms.org/wiki/index.php/Contracts:Defects_Notification_Period;
retention, https://internationalconstructionknowledgehub.com/retention-in-fidic-contracts-is-it-time-for-a-rethink/;
dispute boards, https://gowlingwlg.com/en/insights-resources/articles/2024/a-guide-to-dispute-resolution-under-fidic
and https://www.drbf.org/benefits-dispute-boards · HGCRA 1996 s. 108,
https://www.legislation.gov.uk/ukpga/1996/53/section/108; King's College
adjudication enforcement report 2024,
https://www.adjudication.org/sites/default/files/KCL_Update_2024_Report.pdf
· New York Convention Art. V,
https://newyorkconvention1958.org/index.php?lvl=cmspage&menu=690&opac_view=-1&pageid=12;
ICC Arbitration Rules 2021,
https://iccwbo.org/dispute-resolution/dispute-resolution-services/arbitration/rules-procedure/2021-arbitration-rules/;
DOCDEX, https://iccwbo.org/dispute-resolution/dispute-resolution-services/adr/docdex/;
expert determination,
https://www.ashurstperkinscoie.com/en/insights/quickguide-expert-determination/
· GAFTA 125, https://jacksonparton.com/news-and-articles/2016/9/5/gafta-update-the-new-gafta-125-arbitration-rules;
GAFTA defaulters list,
https://www.gafta.com/media/iw0fwrtl/defaulters_on_gafta_awards_of_arbitration_2011-present-4-february-2026.pdf;
certificate-final, https://www.owlaw.com/german-customs-law/gafta-certificate-final-terms-caution-with-own-agreements/;
NGFA arbitration decisions, https://www.ngfa.org/arbitration-trade-rules/arbitration-decisions/
· CISG Advisory Council Opinion 2, https://cisgac.com/opinions/cisgac-opinion-no-2/;
CISG Art. 39, https://cisg-online.org/cisg-article-by-article/part-3/art.-39-cisg;
Sale of Goods Act 1979 s. 15, https://www.legislation.gov.uk/ukpga/1979/54/section/15
· Marine Insurance Act 1906, https://www.legislation.gov.uk/ukpga/Edw7/6/41/part/2
and s. 79; Insurance Act 2015 fair presentation,
https://www.airmic.com/technical/library/insurance-act-2015-guide-fair-presentation;
claims-made vs occurrence,
https://www.hpso.com/Resources/Coverage-Information/Claims-made-vs-occurrence;
P&I condition surveys, https://www.westpandi.com/loss-prevention/condition-surveys/;
parametric basis risk, https://www.pwc.ch/en/insights/fs/basis-risk-parametric-insurance.html
· Credit reporting: Jappelli & Pagano, https://core.ac.uk/download/pdf/6925878.pdf;
Padilla & Pagano 2000, https://www.sciencedirect.com/science/article/abs/pii/S0014292100000556;
FCRA §611, https://www.bankersonline.com/regulations/fcra-611; rating
agencies, https://www.cfr.org/backgrounders/credit-rating-controversy;
ISO 17065 impartiality,
https://a2la.org/iso-iec-17065-mechanism-for-safeguarding-impartiality/
· UNIDROIT Principles 2016,
https://www.unidroit.org/wp-content/uploads/2021/06/Unidroit-Principles-2016-English-bl.pdf;
Incoterms, https://www.pinsentmasons.com/out-law/guides/incoterms-for-commercial-contracts
· UK Tenant Fees Act 2019 guidance,
https://www.gov.uk/guidance/tenant-fees-act-2019-guidance-for-tenants

**Digital private ordering.** Rule, "Designing a Global Online Dispute
Resolution System: Lessons Learned from eBay", 13 U. St. Thomas L.J. 354
(2017); ACUS deck, https://www.archives.gov/files/ogis/events-presentations/acus-colin.pdf
· eBay Money Back Guarantee,
https://www.ebay.com/help/policies/ebay-money-back-guarantee-policy/ebay-money-back-guarantee-policy?id=4210;
PayPal seller protection, https://www.paypal.com/us/legalhub/paypal/seller-protection
· Taobao public jury, https://www.sixthtone.com/news/1016578 and
https://www.alizila.com/how-taobao-is-crowdsourcing-justice-in-online-shopping-disputes/
· Escrow.com inspection period, https://www.escrow.com/inspection-period
· Kleros parameterisation, https://blog.kleros.io/parameterization-of-kleros-courts/;
Kleros critique, https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2023.1204090/full;
Aragon Court retrospective, https://blog.aragon.org/legacy-product-update/
· UMA oracle, https://docs.uma.xyz/protocol-overview/how-does-umas-oracle-work;
Polymarket/UMA March 2025,
https://www.coindesk.com/markets/2025/03/27/polymarket-uma-communities-lock-horns-after-usd7m-ukraine-bet-resolves
· Reality.eth whitepaper, https://reality.eth.limo/app/docs/html/whitepaper.html
· Augur disputes, https://augur.net/learn/fork/disputes-and-bonds/;
invalid-market scam, https://decrypt.co/6010/is-augur-being-gamed
· Nexus Mutual MCR, https://docs.nexusmutual.io/protocol/capital-pool/mcr/;
claims assessment, https://docs.nexusmutual.io/protocol/claims-assessment/;
NMPIP-261, https://forum.nexusmutual.io/t/nmpip-261-reform-the-claims-mechanism-to-build-trust-upgrade-governance-to-formally-use-an-optimistic-model/1790;
discretionary nature, https://docs.nexusmutual.io/resources/faq/
· Resnick & Zeckhauser, https://presnick.people.si.umich.edu/papers/ebayNBER/index.html;
Bolton, Greiner & Ockenfels 2013, https://pubsonline.informs.org/doi/10.1287/mnsc.1120.1609;
Nosko & Tadelis, https://www.nber.org/papers/w20830; Dellarocas 2000,
https://dl.acm.org/doi/10.1145/352871.352889; Friedman & Resnick, "The
Social Cost of Cheap Pseudonyms",
https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1430-9134.2001.00173.x;
Douceur, "The Sybil Attack",
https://www.microsoft.com/en-us/research/publication/the-sybil-attack/;
EigenTrust, https://dl.acm.org/doi/10.1145/775152.775242
· Mozilla revocation plan, https://wiki.mozilla.org/CA:RevocationPlan;
CA/B Forum SC-081v3,
https://cabforum.org/2025/04/11/ballot-sc081v3-introduce-schedule-of-reducing-validity-and-data-reuse-periods/;
Certificate Transparency gossip study, https://arxiv.org/pdf/1806.08817;
Symantec misissuance,
https://www.techtarget.com/searchsecurity/news/450411573/Certificate-Transparency-snags-Symantec-CA-for-improper-certs
· Ostrom's principles applied to DAOs,
https://blog.colony.io/applying-ostroms-principles-to-dao-governance/
