# loopmarket — a 30-minute introduction for a Swarm audience

Draft 2, 2026-09-07 (draft 1: 2026-09-04; revised after `issues.txt`).
Speaker: Peter Földiák. Title: **"Combinatorial marketplace without a
platform: the loop economy on Swarm"**.

Arc (four parts, ~30 minutes):

| # | Part | Minutes | Slides |
|---|------|--------:|-------:|
| 1 | What is wrong with internet commerce | 6 | 1–4 |
| 2 | A general solution: the loop economy | 11 | 5–22 |
| 3 | What is built, one demo, what is planned | 8 | 23–28 |
| 4 | The Swarm AI Data Exchange and loopmarket: differences, convergence | 8 | 29–33 |
| — | Close and asks to the room | 1 | 34 |

Draft 2 runs long for 30 minutes: part 2 grew from 4 slides to 16 at
the owner's request (barter first, private scales, OntoDAG on its own,
longer loops, solvers, factbond). Cut candidates if time is short:
slides 12 (fits-within, three ways), 17 (multi-hop chain), 22 (bridge:
already covered by the exchange leg on 16).

Conventions in this draft: **bold** lines are what goes on the slide;
indented text is speaker notes; `[verify]` marks a number to check
before the talk; `[demo]` marks a live or recorded terminal moment.
Numbers quoted from the plan corpus carry their source doc.

---

## Part 1 — What is wrong with internet commerce (6 min)

### Slide 1 — Two failure modes, one cause

**Big tech marketplaces: the platform is the market.**
**Tiny web shops: each shop is an island.**
**Common cause: the market itself is somebody's property, or nobody's.**

    Open with the two pictures everyone knows. On one side a handful of
    platforms that own discovery, ranking, payment and the customer
    relationship, and charge for all of it. On the other side millions
    of independent shops that nobody finds, each with its own checkout,
    its own catalogue vocabulary, its own trust problem. The point to
    land: these are not opposites. Both come from the same missing
    piece — there is no *shared, unowned* market structure, so either a
    company builds one and rents it out, or there is none.

### Slide 2 — The rent, the gate, the ranking

**Take rates: app stores 15–30%; Amazon referral 8–15% of price plus
fulfilment and ads, all-in around half of a seller's revenue
(Marketplace Pulse).**
**Gatekeeping: delisting is unilateral and unappealable.**
**Ranking: the platform's algorithm decides who exists.**

    Keep this short; the room knows it. The one idea to add: platform
    power is *structural*, not moral. Whoever holds the only index can
    charge for inclusion and shape the market by omission. Say the word
    "omission" — it comes back in part 3 as a thing we can prove.

### Slide 3 — The everyday misery: buying one thing for a renovation

**Fifteen steps to buy one well-defined item; and that is a good, not
a service. Your bathroom tap leaks — where do you even start?**
**Conclusion: it's a mess; we can do better at discovery, selection,
comparison, logistics, delivery.**

    Personal experience, told fast; the list is on the slide, don't read
    it. Land two things: (1) the effort is all *search and comparison*
    across shops that each hold a private slice of the market; (2) for
    services there is not even a slice to search. The five words at the
    bottom are the five things the rest of the talk is about.

### Slide 4 — The trades that never happen

**Midnight in Barcelona after a late flight; you forgot your toothbrush.
The petrol station 300 m away sells one. Neither of you knows.**
**The want is precise: a thing, within 10 m of the reception, within 30
minutes. You should not have to search. The system should solve it.**

    This is the slide that separates loopmarket from "yet another
    marketplace": by far the most, and the best, potential interactions
    are lost not to price but to search. The example comes back twice —
    as a longer loop with a delivery leg in part 2, and as the
    content-routed GSOC question in part 3.

---

## Part 2 — A general solution: the loop economy (10 min)

### Slide 5 — The simplest loop: barter

**Amara offers 5 apples for 4 oranges. Bruno offers 6 oranges for 4
apples. No money, no units.**
**Walk one apple round the loop: it comes back as 1.875 apples. The
loop closes with room to spare; 4 apples for 5 oranges satisfies both.**

    Start with barter so the loop condition is visible with nothing but
    the two offers. Do NOT mention internal units or scales here. The
    "walk one apple round" phrasing is the product-of-rates condition in
    disguise; name it as such only on the negative-cycle slide.

### Slide 6 — Private units, for internal bookkeeping only

**Left: n gives against m wants is n×m exchange rates, and they can
contradict each other.**
**Right: one private scale per maker is n+m prices; every implied rate
is a ratio, so no arbitrage is possible by construction.**

    This is where the "personal scale" enters, and why. Stress that it
    is bookkeeping: nothing is issued, held or transferred, each maker's
    scale is their own, and only ratios ever leave the maker. The record
    encoding calls it the maker's personal token; in speech say "scale".

### Slide 7 — The simplest loop, on two private scales

**Amara: gives a cordless drill (100), wants a box of floor tiles (120).
Bruno: gives the tiles (50), wants the drill (60). Rates 0.60 and 2.40;
product 1.44.**

    Well-defined items, one barcode each, so nothing about the *thing*
    needs negotiating — only the rate does. (The earlier vegetable-box
    example was dropped: what is in the box, what "weekly" means and how
    it is paid were all under-specified.) Around the loop the units
    cancel; nothing is held on either scale.

### Slide 8 — One uniform offer

**Every economic intention is one record: a thing (a conjunction of
catalogue categories), a service time window, a service region, a
validity window, a price on the maker's own scale.**
**Give or want — the same form. A shop, a person, a courier, a bus with
empty seats, a stablecoin: all makers.**

    Show the offer card. The audience has now seen why the scale exists,
    so this slide is just "and here is the record".

### Slide 9 — OntoDAG: categories as a DAG, not a tree

**One relation, fits-within; one query, the intersection of descendant
cones. Multiple parents are normal: a jigsaw is a saw *and* a power
tool; fruit is botanical-fruit, food and produce.**
**Typed dimensions are ordinary categories with a computed order:
time(2026-09-07), weight(..5kg), a geohash cell.**
**Canonical form: equal content ⇒ equal root; a catalogue is adoptable
by fingerprint.**

    Introduce ontodag on its own before using it. The three small DAGs
    are real edges from the `core` pack. The third one (Flight, Japan,
    boarding pass) makes the "items are categories" point: `get Japan`
    returns the boarding pass nobody filed under Japan. Arrows always go
    up: supercategories above subcategories, on every figure.

### Slide 10 — The catalogue: a want is a conjunction, a give is a point

**A want for {saw} is met by any saw; a want for {power-tool, saw} is
met by the intersection of the two cones: table-saw, jigsaw.**

    The music-lesson example is gone (people who want a lesson know
    whether it is piano or violin). A renovator who wants "a saw for the
    weekend" genuinely accepts any saw; adding power-tool narrows it.
    Point at the two dashed cones and their overlap.

### Slide 11 — ontodag as the language of offers

**Match = the give's categories lie inside every cone the want names.
Unknown category ⇒ never matches (fails closed).**
**Shipped this week: ontodag's `core` pack, 4,137 consensus categories
(WordNet, SUMO, OpenCyc, Wikidata, schema.org as witnesses), plus ten
domain packs — a catalogue as a pinned root, adoptable by fingerprint.**

    One sentence on why the catalogue is a *root*: every offer pins the
    catalogue version it was written against, so a match is reproducible
    forever. Honest footnote: core's goods layer is rich (toaster, jeans,
    jigsaw); its *services* layer is thin — the next pack to build.

### Slide 12 — Fits-within, three ways

**The same relation orders meanings, minutes and map cells. Exact time
and geo checks remain the truth at match time.**

### Slide 13 — Loops: the solver finds the trade nobody asked for

**No pair can trade. The triangle clears.**
**Amara teaches piano, wants vegetables. Bruno grows vegetables, wants
his bikes fixed. Chen fixes bikes, her daughter wants piano lessons.**
**Rates 0.830 · 0.650 · 2.080 = 1.12, surplus 12%.**

    `[demo-lite]` The triangle demo's output as static text. Explain the
    surplus in one line: everyone gets at least their asking price, and
    12% is left over to distribute. Say that this is P0 arithmetic; the
    fair distribution of surplus is specified for P2.

### Slide 14 — A profitable loop is a negative cycle

**A loop is profitable iff the product of its rates exceeds 1 — a
negative cycle under −log weights. Bellman–Ford finds it,
deterministically.**

### Slide 15 — The toothbrush, solved: one want, many gives

**The station gives a toothbrush on the forecourt (3). The courier gives
carriage, forecourt to reception, 00:15 to 00:35 (9). The traveller has
one want — a toothbrush at the reception by 00:35 — and one divisible
money give. brush@forecourt ⊗ transport ⊑ brush@reception.**
**Every give is unconditional; the conjunction lives in the one want, so
all-or-nothing is free; clearing splits the payment 3 + 9.**

    Composition on the want side (P2-loop-selection.md §10, decided
    2026-09-07). Say why the obvious drawing — the courier as a maker who
    wants the brush and gives it back delivered — was rejected: their want
    could clear alone in another loop and leave them holding a toothbrush;
    fixing that needs give-side bundles, the combinatorial door that stays
    shut. The courier sells carriage, not toothbrushes: an operator on the
    place coordinate, as storage is on time and exchange on denomination.
    Not a cycle: a balanced flow with a hub. The principle is "every node
    nets to zero on its own scale"; a loop is the smallest case.

### Slide 16 — One want, six gives: the buyer pays once

**Six people to lift a heavy object. Six unconditional gives of one
person-hour; one want with a minimum quantity of six; one divisible money
give, split six ways at the clearing prices.**

    Composition by aggregation along quantity, the other rule of §10.
    The buyer does not post six wants and pay six times — five lifters
    could clear and the sixth not. The minimum quantity on the single want
    is what makes it all-or-nothing, and it is the flow LP with one lower
    bound, nothing new. The P0 solver cannot see either of these shapes; a
    solver that composes is a different species, and clearing re-verifies
    the composition exactly as it re-verifies a leg.

### Slide 17 — Longer loops: place, time and currency are just more legs

**Factory in Shenzhen → container line → warehouse → van → buyer in
Utrecht. The buyer pays euros; the factory is paid USDC; an exchange
sits in between.**

    Shipping moves a thing in place, storage in time, an exchange moves
    value across currencies. Each is an ordinary maker. The solver
    composes the chain; clearing commits every leg or none.

### Slide 18 — Solvers: outside the protocol, competing, trusted with nothing

**The CoW Protocol shape: anyone runs a solver; the best proposal wins;
the solver is paid from the surplus it found — an endogenous spread
bounded by the reserve bid.**
**Solvers may be as clever, private and stochastic as they like. The
baseline in the repo is deterministic and is the reserve bid.**

    Solvers are external to loopmarket proper, exactly as CoW's solvers
    are external to the protocol. The repo ships one — the species the
    others have to beat — and nothing in clearing depends on any of
    them being honest. P2's batch auction: sealed proposals per beat,
    numeraire-free scoring, a fairness floor (P2-batch-auction.md).

### Slide 19 — Clearing trusts no one

**Clearing re-derives every leg from the pinned book and catalogue,
re-checks the product, and commits all legs atomically — one root.**
**A follower with nothing but an address reads the cleared world back.**

### Slide 20 — Who commits? Not the solver

**The maker signs the offer once and may go offline: a signed offer is a
standing commitment. The solver only proposes. Clearing is the one
writer of `fill/` and `loop/`: one commit, one root. Everyone else folds
the clearing feed like any maker's.**
**Today clearing is one process with its own signed feed — the one
point of trust. In P2 it is a contract on Gnosis: the winning solver
submits the transaction, the contract verifies inclusion and absence
under the pinned root and records the fills.**
**Races: today first valid wins; P2 packs offer-disjoint winners per
beat. A consumed offer is a fill record, never a delete; a stale solver
is simply refused (U11 keeps loops and fills consistent after folds).**

    This answers the question the room will ask after the clearing
    slide: "so who actually commits?" Close with: the commit records
    obligations; the goods still have to move, and that is what P3's
    bonds, oracles and factbond certificates secure.

### Slide 21 — Where verification cannot reach: factbond

**A bonded assertion: one party posts a claim backed by a bond sized to
the cost of adjudication; the world is the latent counterparty during a
challenge window; undisputed claims certify by timeout for free; the
expensive machinery runs only on the ~1% that someone disputes.**
**Information insurance: the one about to act on a fact buys a cheap
hedge; the premium is a market-priced reliability signal.**
**In loopmarket (P3): bonds on the ⊑ edges a loop relied on, on oracle
attestations ("delivered at reception, 00:21"), on identity facts.**

    factbond is the sister repo (design stage, nothing implemented) and
    is mentioned later on the reputation and ERC-8004 slides, so it
    needs this introduction. Prediction markets cannot scale down to
    millions of near-certain mundane facts; bonded assertions can.

### Slide 22 — Money is just another offer

**Money enters as a *bridge offer*: a maker whose thing is a currency.
Bridges turn almost-loops failing only on a money leg into loops.**

    The system does not *exclude* money, it *demotes* it to one more kind
    of offer. That is the frame for part 4: x402 and stablecoins are
    welcome, as legs.

---

## Part 3 — What is built, one demo, what is planned (8 min)

### Slide 23 — The stack, and why it is Swarm-shaped

**loopmarket → ontodag → recordstore → Swarm.**
**Book = a versioned key-value keyspace with canonical roots (equal
content ⇒ equal reference). One book per maker, under the maker's own
feed and signer. Maker identity *is* the feed owner address.**
**Clearing writes under its own feed. Aggregators fold public feeds
into one root and publish it under theirs.**
**Postage TTL is the offer's real lifetime; withdrawal is a tombstone,
never a delete — the book cleans itself.**

    Swarm audience: dwell here. Points they will care about:
    one-signer-per-feed as the safety model (the shared multi-writer feed
    was demoted to a dev tool because feed CAS is best-effort); everything
    so far runs on a *light* node; a full node is needed only for pinning
    and GSOC reception; the book head lives in a feed so a reader needs
    (owner, topic) and nothing else.

### Slide 24 — Invariants the code enforces

**U1 uniform offer · U2 immutable, content-addressed · U3 clearing
trusts no solver · U4 solve against pinned roots · U5 positive rates
only · U6 deterministic baseline solver · U7 vocabulary fails closed ·
U11 no partially-filled loop survives a merge.**

    One breath per invariant; the slide is the list. The takeaway is
    "the design is written down as things tests refuse to let you
    break", and that the same discipline runs across ontodag and
    recordstore.

### Slide 25 — `[demo]` The federated book, live on Bee (≈ 3 min)

**Three makers, three feeds. Two honest aggregators fold in different
orders — byte-identical manifests. Mallory forges an offer in Amara's
name — refused at the fold with an attributed reason. Bruno withdraws
an offer — a tombstone that survives merges.**
**Cain announces Chen's book and silently drops it. His own manifest
convicts him: same announcement root as the honest aggregators,
different book root; the audit hands back absence proofs anyone
verifies with no store. A solver that folds the maker feeds itself
lands on the honest root byte for byte.**
**Clearing bases its own book on the fold; the loop clears; a
follower reads six atomic fills from the manifest alone.**

    Run `examples/demo_federation.py` against the Bee node if the network
    is kind (both gated live tests passed on Swarm Desktop's node on
    2026-09-04: triangle 100 s, federation 432 s — the federation run
    is too long for the stage; use the in-memory run live, ~5 s, and
    have a recording of the live run as backup). Narrate Cain, not the
    triangle: this is the censorship-proof claim made mechanical.
    Line to say: "an aggregator is whoever happened to compute the
    root; the root is the market."

### Slide 26 — Are aggregators necessary? (an honest open question)

**Not for correctness, trust or permission — the fold is pure; any
reader can recompute it.**
**For read cost: a feed lookup costs seconds; a solver folding 1,000
maker feeds pays 1,000 lookups per beat.**
**Direction: solver-side folding is the default, manifests are
disposable caches. Discovery via a public log (Gnosis registry events
as the floor, GSOC as the fast path), never via a party who can omit.**
**Question for this room: GSOC reception from light nodes, and pub/sub.**

    This is the slide that earns the Swarm audience's engagement. Ask
    the question genuinely. Content-routed GSOC (one address per
    catalogue cone × geo cell × day) would make the index *the address
    space* — offers for bicycle repair in this town this week live at a
    computable address, each stamped by its maker. Stamps are not the
    problem (every chunk carries its uploader's stamp; readers need
    none); delivery guarantees and light-node reception are.

### Slide 27 — Who pays for what

**Makers pay postage for their own book (the stamp's TTL is the offer's
lifetime) and never gas. Solvers pay clearing gas and earn the spread.
Aggregators sell serving, never inclusion. The protocol takes and gives
nothing: no fees, no token, no rewards, no treasury.**

    Ruling of 2026-08-21 (P2-batch-auction.md §9). Every actor bears its
    own real cost, so a wash loop through sybils can never be paid for by
    the system it games. Revisit triggers: solver monoculture, aggregator
    scarcity, measured statistics pollution.

### Slide 28 — Roadmap

**P0 in-memory prototype — done. P1 Swarm book — federation live; open:
read-path decentralization, GSOC announcements, latency/durability
gates, spacetime as catalogue dimension terms.**
**P2 verifiable clearing on Gnosis: inclusion/absence under the pinned
book root via recordstore's canonical-trie proofs; batch auctions;
clearing pricing; loop selection as flow-LP / packing-ILP.**
**P3 guarantee fabric (factbond): bonds, oracles, arbitration, bonded
catalogue edges.**
**P4 privacy: staged disclosure, committed offers, ZK fits-within.**

    Thirty seconds. The one thing to say out loud: the single point of
    trust today is clearing, and P2 removes it. Everything else is
    already permissionless.

---

## Part 4 — The Swarm AI Data Exchange and loopmarket (9 min)

### Slide 29 — Same substrate, same idioms

**Both: content-addressed catalogues on Swarm; an atomic root in a
feed; feed owner as identity; a light node suffices to read.**
**Exchange: Agent Card (ERC-8004) → catalog feed → Mantaray root →
item.jsonld; ACT-encrypted content; x402 purchase endpoint.**
**loopmarket: per-maker feed → recordstore root → offer records;
aggregator manifests; clearing feed.**

    Open the comparison generously — you are an investor and a
    contributor, and the room knows it. Name what the exchange got
    right and shipped: ACT for per-purchase encryption, schema.org-first
    vocabulary discipline, server minimization as a stated principle,
    a working purchase flow. Then: "the two projects made the *same*
    architectural choices at the storage layer. The differences are one
    level up."

### Slide 30 — The differences

| | Swarm AI Data Exchange | loopmarket |
|---|---|---|
| Trade shape | bilateral: one publisher, one buyer, one item | multilateral loops; no pair needs to want each other |
| Price | set by the publisher, in a stablecoin | discovered; each maker on their own scale; surplus when Π rates > 1 |
| Medium | required (stablecoin via x402) | none required; money is a bridge offer |
| Described | data assets (schema.org + `swarm-cat:`) | anything: catalogue conjunction × time × place |
| Required server | the publisher's x402 endpoint | none for makers; clearing only (on chain in P2) |
| Trust | ERC-8004 reputation + facilitator | re-verification; bonds where verification fails; reputation derived, never a gate |
| Privacy | ACT per purchase | none yet (P4) |
| Maturity | working purchase flow | prototype; live on Swarm; mock clearing |

    Read the table by rows, not cells. Be explicit that the last row is
    the exchange's advantage today. Then the one-sentence thesis:
    "a storefront and a clearing house — and the clearing house is the
    bigger problem, because it creates trades that a storefront cannot."

### Slide 31 — Why not reputation-based

**eBay: 0.3% of transactions rated negative, yet P(negative | partner
rated negative) > 37% — retaliation suppressed truthful feedback until
one-sided ratings in 2007 (Resnick & Zeckhauser; THREATS.md T8).**
**Cheap ratings inflate toward uselessness (Filippas–Horton–Golden).**
**loopmarket's rule U12: standing counts cleared, fee-paid loops only;
loss experience comes from bonded, adjudicated events (factbond).
Reputation is a *statistic you derive*, not an institution you believe.**

    This is where "loopmarket is not reputation-based" becomes a
    positive claim rather than an omission. Reputation answers "should I
    trust this seller"; loopmarket tries to make the question
    unnecessary where it can (clearing recomputes everything) and
    expensive to game where it cannot (bonds).

### Slide 32 — x402 and ERC-8004 fit loopmarket — as legs, identities and proofs

**x402 is a bilateral rail; it cannot settle a k-leg loop. It fits
three places the plan already has: the stablecoin leg of a bridge offer
(settlement cargo, never the scoring numeraire — U14); paid aggregator
*serving*, never inclusion (agenda item 4); solver fee collection.**
**ERC-8004 identity: an Agent Card `services[]` entry naming the
maker's book feed owner is exactly P1's announcement channel, with the
chain registry as the censorship-resistant floor. The exchange already
uses this pattern for its catalog feed.**
**ERC-8004 reputation: publish one-sided, aggregated signals derived
from cleared loops; consume feedback as one input to P3 risk premia;
never gate a trade on it.**
**ERC-8004 validation: clearing receipts and factbond certificates are
validation events with proofs, not opinions.**

    Keep the tone "and", not "instead". The line: "x402 for the money
    leg, loopmarket for the parts x402 cannot see."

### Slide 33 — How we could converge

**1. Shared identity: one ERC-8004 Agent Card carrying both a
`swarm-ai-catalog` and a `loopmarket-book` service.**
**2. Bridge adapter: every exchange catalog item is a give offer priced
in a stablecoin — publish the catalog into a loopmarket book unchanged.
The exchange gains buyers who pay in things, not money.**
**3. The x402 endpoint as a fulfilment oracle: an ACT grant is a
verifiable proof of delivery — the cheapest oracle in P3.**
**4. Shared vocabulary: the exchange's schema.org/`swarm-cat:` terms as
an ontodag pack, so both catalogues speak one fits-within order.**
**5. Discovery as a public log, not an indexer: keep "no synthesized
server views" and add "no party who can omit" — if a Marketplace Event
Collector exists, let it be auditable against the chain like an
aggregator against its announcement root.**
**6. Keep the one-currency assumption out of the data model — a price is
a number on *some* scale; let the scale be a field.**

    This is the slide you actually want people to remember. Items 1–4
    are additive to the exchange as it stands. Items 5 and 6 are the
    "please don't go too far in a different direction" asks, phrased as
    design principles the exchange already half-holds (its own
    server-minimization principle). Say what you would take *from* the
    exchange in return: ACT as a P4 Tier-1 candidate, x402 pragmatism,
    ERC-8004 identity, and the habit of shipping.

---

## Close (2 min)

### Slide 34 — Asks to the room

**GSOC reception from light nodes; pub/sub timing.**
**A services layer for ontodag's core pack (the goods are in; repair,
tutoring, cleaning are not).**
**A first vertical: digital services, agents first — the exchange's own
wedge.**
**Repos: loopmarket, ontodag, recordstore, factbond (github.com/petfold).**

    End on the sentence from slide 25: the root is the market; Swarm
    holds the books; the chain is the floor for discovery; the one
    remaining point of trust is clearing, and it is next.

---

## Backup material (not in the 30 minutes)

- **Divisibility and the P2 pricing rule.** Equal log-surplus split under
  uniform directional clearing (`docs/plans/P2-clearing-pricing.md`).
- **Why no protocol fees or emissions.** Nothing to farm ⇒ wash loops
  have no surface (agenda item 4, THREATS T1).
- **Batch auctions.** Sealed proposals, numeraire-free scoring, the
  baseline solver as reserve bid (`docs/plans/P2-batch-auction.md`).
- **Bridge liquidity curve.** 0% → 9.5%, 10% → ~50%, 20% → ~70% of debt
  cleared (arXiv:2507.22309, Fig. 10); Sardex ~25% of net internal debt
  (Fleischman & Dini 2020).
- **Live numbers.** 2026-08-01: triangle cleared on Gnosis-mainnet light
  node in ~51 s. 2026-08-21: federation gate 96–105 s. 2026-09-04 (cold
  node, minutes after postage sync): 100 s / 432 s.
- **Threat register** T1–T14, mirrored with factbond (`docs/plans/THREATS.md`).

## To do before the talk

- [x] take-rate figures on slide 2: app stores 15–30%, Amazon referral 8–15% + fulfilment/ads, ~50% all-in (Marketplace Pulse); the `[verify]` tag is gone from the slide.
- [ ] Record the in-memory federation demo (~5 s) and the live run (minutes) as terminal recordings; decide which to show.
- [ ] Decide whether to show the triangle as a live 30-second run or as static output on slide 13.
- [ ] Read `swarm-ai-data-exchange/documents/...design-v1...md` §10–11 once more for the exact purchase-flow wording on slide 29.
- [ ] Check with Solar Punk whether the Marketplace Event Collector is planned as a required discovery component (slide 33, item 5) before saying so on stage.
