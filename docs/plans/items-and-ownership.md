# loopmarket: items, lots and ownership

Status: design, 2026-09-23; corrected and decided 2026-09-25; entered
loopmarket's plan corpus 2026-09-25 from the assurance drafts. Dn, A1–G5
name decisions in `credentials-cover-and-options.md`. Proposed: an inspection is worth something only if the delivered
item *is* the inspected one, so unique items get a content-addressed identity
`item(h)`; **ownership is not a clearing concept** (Peter's revision of
2026-09-23: "better to keep ownership out of loopmarket") — "not his to
sell" is non-performance like "does not exist", checked at settlement where a
register exists, covered by bonds and fact cover (title insurance) where not.
No NFT in the protocol. The per-item double-sale rule *across all makers*
was the assistant's extension of the earlier per-maker rule; the review found
it a cheap denial-of-sale attack and plan D5 replaces it.

## 1. Item identity

### 1.1 The genesis record

`item(h)` names a content-addressed **genesis record** holding only what
identifies the item. Everything that changes — condition, mileage, reports,
repairs, owners — is an assertion, a report or a fill that *names* h, never
part of the record (a changed record would be a new id).

```
genesis: { scheme, identifier | fingerprint, binding evidence, tagger? }
```

### 1.2 Derived where possible

| the item has | h is | canonical? |
|---|---|---|
| a natural identifier: VIN, land-register / cadastral number, maker + serial, a grading lab's report number | `hash(scheme, identifier)` — anyone computes the same id | yes |
| none (a watch without papers, an artwork, furniture) | hash of the **tagging record**: fingerprint (image features, an applied random pattern such as a paint splatter or glitter seal, a secure-element chip's key) + the tagger's signature | only through the tagger |

Derived ids stop re-registration from defeating double-sale detection. For
tagged items, the tagger's bond carries more of the trust. *(added
2026-09-25)* In ontodag's own terms (`PACKS.md` principle 4, the "stranger
test"): a hash of a natural identifier is an identity anyone re-derives from
meaning, and passes; a tagger-signed hash can only be minted by the tagger,
and does not. That is the honest statement of what a tagged id is: an
attested identity, as strong as its attester.

The inspecting buyer is safe either way: the want names the h that was
inspected.

### 1.3 The term

`item(h)` is a parametric term with an equality-only value (a hash kind) — a
thing term like any other; a want naming it takes only that item. Ontodag
needs an identity kind for h (equality, no order) — an upstream ask.

### 1.4 Sale by sample

The show-apartment case: the offer names a category plus `sample(h)` — the
delivered item must conform to the inspected sample; the warranty is
conformity. Same machinery, a different term.

## 2. The per-item rule — per maker *(applied plan D5, 2026-09-25)*

At most **one active option record or open (unperformed) fill per
`(maker, item(h))`**. It stops one seller double-selling the same item by
accident. It says nothing across makers: two makers may both offer h (owner
and broker, a reseller chain), and whichever cannot deliver is a
non-performance covered by deposit, point and fact cover as everything in
§5.3. The earlier rule "across all makers" was a free denial-of-sale attack
(anyone computes a VIN's hash, posts an offer on someone else's car, takes an
option from a second key, and blocks the owner at no cost) and contradicted
§5.1: exclusivity without an entitlement check.

Where the buyer has sunk cost into the specific item (the inspected car, the
wedding venue), the buyer's remedy exists today: `requires.point` sets the
giver's deposit floor to what the loss would actually cost them. A high
enough bond makes every two-maker case safe, including the double-dealer,
whose cancellation ladder must not be cheaper than the price difference
between two buyers (P3's sizing concern).

- The clearing writes an item claim: `item/<h>` → { maker, offer, loop } of
  the claiming option record or fill, in the same commit (U3). This is a
  **clearing claim keyspace** written by the clearing role, like `fill/`,
  not a book index ("there is no index in the book … never book keys",
  `registry.py`, ruling of 2026-09-12).
- Clearing refuses a leg on a give naming `item(h)` by maker W while
  another claim on (W, h) is active.
- The fill authority records item claims at finalization (`BeatClearing`
  beside fills and option records), and the leg verifier checks them — the
  same contract change as option records (`options-and-cover.md` C4).
- A claim ends when the leg is performed (countersigned), its claim period
  passes, or the option record's window ends (`options-and-cover.md` §3.6); the next sale of
  h by the same maker is then admissible.

**Priced exclusivity, the first post-v6 addition** (field shape fixed now,
§8): a give naming `item(h)` may declare `exclusive: true`, admissible only
if its deposit is at least the leg's value for the option's or fill's
duration; while such a claim is open the clearing refuses *other* makers'
legs on h. Blocking an item then costs its value in locked capital.
Witnessed exclusivity (a `registry-transfer` witness, a tagger's statement
naming the holder) may later grant the same without the price.

## 3. Inspection history — no hidden reports

Every inspection of h is a leg (an `inspect(subject(item(h)) …)` give by
the inspector) naming h, so the book shows inspections done. *(corrected
2026-09-25)* `options-and-cover.md` §4 defines no `inspect`; and an inspector's give cannot
be an operator under the current algebra, which requires an operator to move
the thing along a dimension. The chat's semantics ("inspection moves
certification": the argument matches want-within-give, `car
inspected(dekra)`) need the composition shape of plan D4.

*(applied practice review, 2026-09-25)* Two rules on inspection legs:

- **Certificate-final** (plan E1): an `inspect` term may carry
  `certificate-final`, and its report enumerates the categories it
  certifies. A claim on a certified attribute is admissible only against
  the inspector's statement (its deposit or cover, capped in its offer); a
  claim on an uncertified attribute runs against the giver. GAFTA's
  loading-port rule: after a certificate-final inspection the buyer's
  remedy on those attributes runs against the inspector, and the
  inspector's exposure is bounded.
- **Independence** (E2): an `inspect` give is admissible only if its
  giver's key is not a maker or wanter on any other leg of the loop naming
  h, a free formality; the real mechanism, since keys are free, is that the
  wanter's `requires.legs` entry accepts inspectors by accrediting root,
  deposit floor or absence of reversals, never by a count, and the
  inspector's deposit is what a false certificate forfeits. A seller who ordered three and
shows one is visible. A wanter may require "all inspections of h disclosed" —
fact cover written by the seller.

Reports themselves live on Swarm, name h, are signed by the inspector, and are
sealed to the buyer like handoffs; the hash sits in the inspection fill. In a
dispute anyone can check that the report shown is the one that existed.

## 4. Lots

Between fungible and unique: `lot(h)` for a batch (medicines, food) — the
recall unit. A register entry "lot h recalled" (`counterparty-gate.md`'s revocation pattern)
makes legs naming it meet nothing from then on and triggers notices to
holders of cleared, unperformed legs.

## 5. Ownership

### 5.1 Not a clearing concept

An offer is a **promise to deliver**, not a claim of title. Selling what one
does not yet own is often legitimate: the reseller (loopmarket's preferred
route over give-side bundles), next season's crop, a courier's run.
Requiring title at posting would break these. So clearing knows nothing of
ownership; "not his" is the giver's non-performance, as "does not exist" is.

### 5.2 Registered goods: checked at settlement

For land and vehicles the register is the title. Its transfer is the
handover **witness**: a v5 `oracles` type `registry-transfer`, named in the
wanter's `requires`. The leg is performed when the register shows the
transfer; a failed transfer is non-performance (bond, point, repair).

### 5.3 Unregistered goods: bonds, opt-in checks, fact cover

- The giver's bond and the wanter's point cover "not his".
- **Theft** differs from non-existence by the true owner, who may reclaim
  from a good-faith buyer (in many jurisdictions good-faith acquisition does
  not cover stolen goods). High-value categories want longer claim periods —
  the wanter's choice.
- **Opt-in by category:** for portable, valuable, resaleable goods (bicycles,
  phones, tools, jewellery) a wanter may require an **absence proof from a
  stolen-goods register** — `counterparty-gate.md`'s revocation pattern, not ownership.
- **Fact cover (title insurance):** "the seller had the right to sell h as of
  D" — the insurer does the search and pays if refuted. The general answer
  for anything valuable (hansa's insurer toolkit).
- A bond sized to the item's value, forfeited on reclaim within the claim
  period, makes fencing unprofitable within those limits.

### 5.4 Provenance for free

The chain of fills naming h — W sold to B, B to C — is provenance, not title:
an off-book sale leaves it stale. Buyers may read it; nothing requires it.

### 5.5 No NFT in the protocol

The 2026-08-21 ruling (no on-chain token objects; reification must be
justified against the bookkeeping baseline) concerned *personal-token*
objects; the same reasoning applies here: an NFT does not solve the physical
binding, is not title, and the fill chain gives provenance. *(corrected
2026-09-25)* The corpus also records a deferred per-item NFT suggestion by
Viktor Trón (`P3-guarantee-coupling.md` §4a: the seal identifier as token
id, the countersign as its transfer, "not before the countersign record
exists; not a matching concern at any point"). This draft overrules it
explicitly rather than by extension: the fill chain naming `item(h)` *is*
that token's history without the token. Where an NFT register exists
outside, an adapter reads it as one more register (hansa) — a source of
statements, never title at clearing.

## 6. Privacy

A fill chain naming a derived h publishes an item's owner history; a VIN is
public anyway. Salting h would hide it and lose canonicity. *(corrected
2026-09-25)* P4 does not discuss salting and is not neutral on the
trade-off: it rules linkage permanent, `fill/` plaintext, and stealth fills
incompatible with auditability (`P4-privacy.md` §5 item 1). A salted id
would need P4 reopened; this draft keeps derived ids.

## 7. Work packages and gates

| # | Package | Gate |
|---|---|---|
| I1 | `item(h)` term: the ontodag hash kind (upstream), derived-id helpers for VIN / land register / serial | the same VIN yields the same h everywhere; a mismatched h never matches |
| I2 | item claim keyspace + per-item rule in registry and clearing (per maker, plan D5) | two offers by one maker on one h: the second leg refused while the first is open; admissible after performance; two makers on one h both clear, and the loser is a non-performance |
| I3 | item claims on chain (with `options-and-cover.md` C4) | a second claim on h in a concurrent beat is caught at finalize or by challenge |
| I4 | `registry-transfer` witness type | a leg naming it performs only on the witness's statement |
| I5 | inspection history query + "all inspections disclosed" requirement | a hidden inspection of h makes the requirement unmet |
| I6 | `lot(h)` and recall through a register | a recalled lot's uncleared legs meet nothing; notices written for cleared ones |

## 8. Open

- The ontodag identifier kind for `item(h)` (upstream ask, the assurance drafts' `ontodag-asks.md`
  §1: registry minor, kind node in loopmarket's seed, `lot → item`,
  `sample → item` as role heads).
- When exactly an item claim ends for services-on-items (a car in repair).

- The `exclusive` field, post-v6 (D5): `exclusive: bool` on a give naming
  `item(h)`; admissible only if `bond.value ≥ leg value` for the claim's
  duration; the item claim record gains `exclusive: true`; clearing refuses
  other makers' legs on h while it is open. Ships in the bump after v6.

Decided in `credentials-cover-and-options.md` and **applied here on 2026-09-25**: D4
(§3: `inspect` as an `operator-argument` give), D5 (§2, I2), D6 (§2: an
item claim ends with the option record's window).
