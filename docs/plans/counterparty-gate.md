# loopmarket: counterparty requirements — statements, registers, revocation

Status: design, 2026-09-23; corrected and decided 2026-09-25; entered
loopmarket's plan corpus 2026-09-25 from the assurance drafts. Dn, A1–G5
name decisions in `credentials-cover-and-options.md`. Proposed: a wanter may require things of the counterparty (a
licence, independence, cover, an identity binding) as **categories** (Peter's
choice), checked fail-closed by the matching gate like everything in v5's
admissibility by declaration; the gate reads one **statement** shape whatever
its source; statements are presented as sidecars in the maker's book,
registers are separately rooted and pinned; revocation is pulled and proven
by absence, with a maximum age chosen by the wanter; the protocol never
requires a government credential (Peter's rule). The statement shape, the
revocation design and the adapter split were the assistant's answers to the
chat's open decisions 4–7, not recorded agreements. loopmarket defines the
shape and the gate; the **assurance** repo produces statements (adapters,
registers, insurers).

Two things in loopmarket's own corpus this draft answers and must be
reconciled with *(added 2026-09-25)*: `P2-loop-selection.md` §4a's open
decision (a), "the declared-requirement field and what it may name (bond
floor, oracle type, history)"; and `P3-guarantee-coupling.md` §4b item 3
(2026-09-19), which already plans "a v6 offer field `credentials` (registry,
identifier) … checked by the same crawler that checks sources". Plan D7
decides one shape and one v6 bump.

## 1. The requirement (v6)

*(applied plan D7, 2026-09-25)* `Requires` gains

```
counterparty: [ { category, kinds, min_bond?, roots: [register id, ...], max_root_age }, ... ]
legs:         [ { category, accept }, ... ]   # plan D4: the loop must contain such a give
resolvers:    accept                          # plan C4: who may resolve this leg's reservation
```

where `accept` (plan C4, E2) names how a third party, an inspector or a
resolver, earns acceptance: by key, by accrediting root, by a deposit
floor, or by the absence of reversals within a look-back window, and
optionally an issuance binding (D8). **Never by a count of rulings or
inspections**, which puppet cases manufacture for the price of the burn
slice. Keys are free; stake and accreditation are not. The give side gains
`claim_max` (plan A1), the longest claim period the giver will carry.

- **`counterparty`** is the other side of the leg, whichever side the
  requirer is on: a wanter may require of a giver (a licence), a giver of a
  wanter (age for alcohol, a prescription, a tenant check). §4 reads "the
  counterparty's book" accordingly.
- `category` — a credential category from the shared catalogue
  (`dentist-licensed-eu-annex-v`, `inspector-type-a`,
  `door-at-least-photo`; plain nodes, not parametric terms, per
  the assurance drafts' `ontodag-asks.md` §2); the counterparty's statement must be of a category
  below it (one-way containment; an unknown category fails closed, U7).
- `kinds` — which statement kinds satisfy this entry, from `signed`,
  `attested`, `self-bonded` (v1; `insured` after pooled cover, D4).
- `min_bond` — a floor that applies whenever the satisfying statement names
  a deposit (D1), whatever its kind; free capacity after this fill's
  reservation must be at least it.
- `roots` — the **trust roots** the wanter accepts: registers at the top of
  an acceptable accreditation path. The registers *on* the path are not
  named; the proposal pins them (§3.3).
- `max_root_age` — how old each pinned register root on the path may be,
  against clearing's clock (§5).

Entries are conjunctive; one statement answers one entry. The only
disjunction is inside an entry: "licensed **or** self-bonded ≥ B" is one
entry with `kinds: [signed, attested, self-bonded]` and `min_bond: B`.
Cross-category alternatives ("an EU or a UK licence") live in the catalogue
as recognition edges under one node, not in the record. Empty
`counterparty` (the default) requires nothing; most trades need nothing.

`legs` is the composed-cover and inspection requirement (D4): each named
category must appear as a give in the loop whose argument accepts the
wanted thing, composed by the solver like `transport`.

This one v6 bump carries, with `options-and-cover.md`'s `underlying` and `exercise`, all the
new fields; P3 §4b's planned `credentials` field is subsumed by the `cred/`
sidecar, which a credential can renew or lose without re-signing the offer.

## 2. The statement — the one shape the gate reads

```
statement: { subject: K,            # the maker key it is about
             category: C,
             issuer: I,
             kind: signed | attested | self-bonded   (| insured, after pooled cover),
             as_of, until,
             evidence: hash of what was presented,
             path: [issuer → ... → root],
             deposit: { offer, escrow }?, # when a deposit backs it (plan D1)
             paid_by: subject | relier,   # who paid the attester (plan G5)
             scheme: hash }               # the check procedure applied (plan E3)
```

Sources (all produced outside loopmarket, by assurance): an EU / W3C
credential (*signed*), an attester who read paper or an online register
(*attested*, including a practice attesting for its practitioners, backed
by the practice's deposit), the subject's own declaration backed by a
deposit (*self-bonded*; the degenerate case of attested with subject =
maker). *Insured* (a standing policy) waits for pooled cover (plan D4, D9);
composed cover in v1 is a `requires.legs` entry, not a statement. The gate
never sees the source format.

## 3. Where statements and registers live

### 3.1 Vocabulary — the shared catalogue

Credential categories and slow recognition edges (`de-approbation ⊑
eu-annex-v`) are categories like any other. Keys never become catalogue nodes
(the catalogue's root is pinned by every offer; per-person facts would churn
it).

### 3.2 Presentations — sidecars in the maker's book

`cred/<maker>/<statement id>` → the statement plus the presentation it was
derived from, beside `sig/` and `handoff/`; covered by the book root the
proposal already pins. Public, because admissibility is a matching gate: the
solver must see it before proposing (`meets` in candidate generation). The
public form carries the minimum (a ZK or selectively disclosed statement);
photos and documents are never published (assurance's binding, §7); where a
door check needs the photo, the statement carries a commitment (hash) to it
and the door presentation reveals it, signed by the issuer.

*(corrected 2026-09-25)* Fold admission cannot reuse `handoff/`'s rule: that
rule is per **offer** (`handoff/<loop>/<offer>` is admitted only beside an
offer this book's owner made and sent, `federation.py`), and a statement
about a key has no offer to sit beside; today the fold rejects it as an
unknown keyspace. `cred/` needs its own rule: admitted when
`statement.subject == book owner`, with the same attributed rejection
record otherwise (U8).

### 3.3 Registers — separately rooted, pinned

A register is a recordstore keyspace owned by an issuer, an accreditor or an
insurer:

```
status/<statement id>   -> issued | suspended | revoked, at t
revoked/<statement id>  -> t                      (the absence-proof set)
accredit/<issuer>/<C>   -> by whom, since, until, scheme  (who may issue what, and how it is checked)
```

*(applied practice review, 2026-09-25)* Three rules on registers:

- **A register is a transparency log** (plan G1): append-only, with a
  consistency proof between one heartbeat's root and the next; the status
  keyspaces above are the current view on the log. "Two inconsistent roots
  signed by register R" is a specific, refutable fact about R, disputable
  against R's bond and grounds for removal as a trust root; anyone may
  monitor for the winner's share, and an insurer's watch duty (charter
  E.6) is the monitor role. An absence proof needs the root to be
  complete; a heartbeat proves only freshness; the consistency proof is
  what makes completeness checkable.
- **Short lifetimes** (G2): a statement's default `until` is weeks, with
  renewal cheap (the sidecar renews without re-signing the offer); a
  register's declared cadence is at or below the shortest plausible
  `max_root_age`. The web abandoned pull revocation for short lifetimes and
  complete pushed sets.
- **`scheme`** (E3): an accreditation and a credential category both name
  the check procedure in the vocabulary pack (what is examined, what a pass
  is, what the examiner signs). "Did they check" becomes a recorded fact,
  and a ruling (plan C5) cites it.

- announced on the announcement channel under a new role `register` (beside
  `maker` and `clearing`). *(corrected 2026-09-25)* The on-chain
  announcement reads `role == 1` as clearing and anything else as maker
  (`announce.py`), so a third role is a change to the announcement
  contract's reading, and the fold keys admission on the role;
- a proposal pins `register_roots` (U4); clearing re-derives against them
  (U3). *(corrected 2026-09-25)* A proposal pins more than two things today:
  the on-chain `Beat` carries `bookRoot, ontologyRoot, registryVersion,
  contractVersion, addressing`. `register_roots` is added to `LoopProposal`,
  the `loop/` record (a version bump), `LoopVerifier.Beat` and
  `beat.submission`;
- external registers (EU trusted lists, EBSI's Trusted Issuers Registry,
  status lists) enter as content-addressed snapshots on Swarm, pinned the
  same way.

## 4. The check at a leg

*(applied plan D7, 2026-09-25)* For each entry of the requirer's
`requires.counterparty`, the counterparty's book holds a statement with

1. `category` below the required one in the catalogue, and `kind` in the
   entry's `kinds`;
2. a `path` from its issuer, through `accredit/` records, to a root the
   entry names in `roots`, with **every register on the path pinned** in
   the proposal's `register_roots` (an unpinned register on the path fails
   closed; the solver discovers and pins them);
3. an **absence proof** of every statement id on the path under each named
   register's pinned root (recordstore's `prove`/`verify_proof` — as
   `audit_manifest` uses; `TrieProofVerifier.verifyAbsence` checks it on
   chain). *(confirmed 2026-09-25)* Both exist: `RecordStore.prove` returns
   an inclusion-or-absence proof because the encoding is canonical, and the
   on-chain verifier has `verifyAbsence` tested under both addressings, at
   about 0.64 M gas. `LoopVerifier` today calls only `verifyInclusion` for
   `offer/<id>`; this gate is the first design that puts absence on the leg
   path, which R3/R4 wire;
4. freshness of every pinned register root on the path (§5);
5. validity (`as_of`, `until`) through the leg's **handover window** — a
   licence expiring before the appointment meets nothing;
6. when the statement names a `deposit` (D1): the deposit's free capacity
   after this fill's reservation is at least the entry's `min_bond` (the
   existing `meets(held=)` check, the chain as the authority); the fill
   then reserves that floor for the leg's claim period, and a refutation is
   a claim on that reservation;
7. no `suspended/<statement id>` record under the issuer's pinned root
   (plan D2: a self-knowable claim whose evidence was not produced in time
   is suspended until ruled).

Any step unprovable ⇒ the leg meets nothing (U7). An unnamed or unreachable
register fails closed; nothing is fetched speculatively. *(applied plan
E4)* The attributed rejection record (U8) **enumerates every failing step**
in one record, so a re-presentation cures in one round: most first
documentary presentations fail on formalities, and UCP requires one
refusal listing every discrepancy for that reason.

## 5. Freshness without giving up U4

*(applied plan D7, 2026-09-25)* Freshness is the **pinned register root's
age**, not the credential's issue date: a diploma from 1999 is as valid as
its status register says today. The requirer's Δ (`max_root_age`) bounds
how old each pinned root on the path may be, against clearing's clock:

- a register publishes its root at a **declared cadence** (public, in its
  announcement) and must **heartbeat** at least that often; a requirer
  whose Δ is shorter than a register's cadence simply excludes that
  register; a silent register's statements meet nothing for every requirer
  whose Δ it has outrun. (This is a liveness cost on the register's
  issuees, a denial-of-service surface to record in THREATS: a register
  taken offline invalidates everyone it certified, for strict requirers.)
- the statement's `as_of`/`until` are validity, not freshness, and are
  checked against the handover window (§4 step 5); an attestation's
  `as_of` is its check date and doubles as its freshness, renewed past Δ.

**Which root:** a register's roots form a sequence in its feed, so "the
latest root as of t" is well defined. The proposal pins the latest root as of
its book pin; clearing checks no newer root precedes its own clock. U4 stays
(everything pinned and reproducible) and a solver cannot pick an old root to
miss a revocation. If the contract must decide "latest" itself, registers
anchor their roots on chain.

Δ is the exposure window, chosen by stakes: hours for a surgeon's licence,
months for a course certificate.

## 6. Revocation after clearing, before handover

- The leg becomes the giver's non-performance: bond, the wanter's point, the
  solver's repair (the wanter free to refuse).
- **Notices:** whoever watches (an insurer, the register, the `watch` client)
  writes `notice/<loop>/<offer>` in its own book — timestamped, provable —
  and the counterparty's client reads it. Notification moves the risk: a
  wanter who proceeds after notice bears it; harm before notice is the
  watcher's (the insurer's, when cover exists — assurance).
- **The notice is also rung zero of every claim** *(applied plan A2, B1)*:
  a claim on a reservation must cite a prior `notice/` record from the
  claimant to the giver, which carries a **cure deadline**; the notice must
  fall within the claim period; the giver may cure within the deadline
  (deliver, refund at the ladder, correct the statement); only refusal or
  silence past it opens the bonded dispute, and nothing is public before
  that; the claim must then be asserted within M days of the notice
  (policy data per category). Three record-checkable clocks, no judgement
  about when the claimant discovered the fault.
- What cannot be revoked: holds and cover already reserved (`options-and-cover.md` §4.4).
- The `watch` client re-checks the registers before each window.

## 7. Binding the key to the person at the handover

A statement binds a key; the person at the door must control it. Two new
witness types. *(corrected 2026-09-25)* How witness types enter: the
**giver** declares its `oracle` (one string, default `countersign`);
`requires.oracles` only filters which declared types the wanter accepts;
and clearing refuses any offer whose type is outside its `verifiable_oracles`
set (`clearing.py`; `P3-guarantee-coupling.md` §3 rule 1). The roster itself
(countersign, locker, digital-proof, attested-photo, location) is consumed
by loopmarket and owned by factbond's `evidence-policy.md`. So a new type is
three changes: the roster, the clearing's verifiable set, and the settlement
adapter. The two types:

- `possession` — a fresh challenge–response from the practitioner's key
  (nothing reusable exists; a copied code dies at once);
- `photo-match` — the counterparty's client shows the photo bound to K in the
  credential (never published, shown locally) and the counterparty confirms.

*(applied plan D8, 2026-09-25)* Binding is **two things**, both nameable in
a requirement: a **door scale** (ordered, cumulative names, the witness
types above: `door-at-least-possession ⊒ door-at-least-photo ⊒
door-at-least-proximity`) and a **set of issuance sources** the requirer
accepts (`issued-by-attester-in-person`, `issued-by-web-of-trust`,
`issued-by-state-document-zk`, `issued-by-state-document-eid`): the
statement records which source bound the key to the person at issuance.
The photo reaches the counterparty's device by selective disclosure at the
door; the public statement carries only a commitment to it (§3.2). A
government credential is one source a requirer may accept; **it is never
required by the protocol.**

## 8. Boundaries

- B1: the gate is pure: statement shape, catalogue, absence proofs. Verifying
  EU seals, X.509 or SD-JWTs lives in assurance's adapters (or behind an
  optional extra, lazily imported — B2), and an unverifiable statement meets
  nothing.
- On chain: the statement's signature, inclusion and absence proofs are the
  structural half; category subsumption and source-format verification the
  optimistic half — as `LoopVerifier` today.

## 9. Work packages and gates

| # | Package | Gate |
|---|---|---|
| R1 | v6 `requires.counterparty` + statement type in `schema.py` | round-trip; v5 byte for byte; empty requirement changes nothing |
| R2 | `cred/` sidecar + its own fold rule (`subject == owner`) | a foreign statement in a fold is rejected with attributed provenance (U8) |
| R3 | registers as keyspaces + `register` role (announcement reading) + `register_roots` in `LoopProposal`, the `loop/` record, `Beat` and `beat.submission`; `verifyAbsence` on the leg path | a proposal missing a named register's root is refused; a revoked statement's absence proof fails on chain |
| R4 | the gate in `meets` (§4) incl. handover-window validity | the dentist case, in its primary form (plan D1): a **practice** is the maker, its deposit backs an *attested* statement about each dentist's key, and the dentist's key is checked at the door; licensed passes; revoked, expired-before-window, unaccredited issuer, silent register, and a floor not free after this fill's reservation each refused; the solo dentist's *self-bonded* statement is the degenerate case with subject = maker |
| R5 | "latest root as of t" + heartbeat + consistency proofs between roots (§3.3, §5) | a proposal pinning a stale root is refused when a newer one precedes clearing; a root that does not extend its predecessor is refused; two inconsistent roots signed by one register are a refutable fact |
| R6 | `notice/` sidecar with cure deadline + `watch` re-check (§6) | revocation between clearing and window yields a notice and a non-performance path; a claim without a prior notice, or asserted after M days from it, is refused; a cure within the deadline ends the matter with no public record |
| R7 | `possession` / `photo-match` witness types (§7): roster entry (factbond evidence policy), clearing's verifiable set, settlement adapter | countersign requires the witness; a replayed response fails; an offer naming an unrostered type is refused at submit |

## 10. Open

- Alternatives within one entry ("licensed or self-bonded ≥ B") — the record
  shape (plan D7 makes `kinds` part of the entry, which is the same
  question).
- Cross-register matching of a person (a ban recorded under another
  jurisdiction's identifier) — near term by self-bonded completeness
  declarations (factbond doc), longer term P4.
- Linkability of public statements. *(corrected 2026-09-25)* P4 is not
  neutral here: it rules linkage permanent and stealth fills incompatible
  with auditability (`P4-privacy.md` §3 item 4, §5 item 1), and ships no
  unlinkability language before its G2. Unlinkable ZK presentations are
  assurance's and outside P4's scope.

Decided in `credentials-cover-and-options.md` and **applied here on 2026-09-25**: D1
(§2, §4 step 6), D2 (§4 step 7), D4 (§1 `legs`, §2), D7 (§1, §4, §5), D8
(§7). Still open: general alternatives across entries, if a wanter ever
needs them (an outer list, without changing the entry).

The practice review's amendments (`commercial-practice-review.md`, decided
2026-09-25) are applied: A1 and A2 (§1 `claim_max`, §6), B1 (§6), C4 and
E2 (§1 `accept`), E3 and G1, G2 (§3.3), E4 (§4), G5 (§2).
