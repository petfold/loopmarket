# loopmarket — catalogue bootstrap

Status: design, 2026-08-07. Decided here: the seed set and its licenses
(GS1 GPC + UNSPSC + Google Product Taxonomy + Wikidata; ECLASS skipped);
the per-release import pipeline — repeatable, emitting a new pinned root
plus an explicit old→new mapping, never mutating the shared catalogue in
place; vocabulary adoption by fingerprint with diff-preview and endorsement
(the Mercury-collision defense); the governance split — schema gated and
eventually bonded, offers permissionless; the two norms as instrumented
protocol rules; contested-edge bonds sized off settlement-weighted
centrality, no token-voting curation anywhere; LLM-assisted authoring as
retrieve-then-verify, classification as the maker's bondable assertion;
interim encodings for condition grades and opening hours. Open here:
cross-seed alignment, the bootstrap-period gate, cold-start bond sizing,
the ordinal/cyclic kinds (filed upstream).

This document is the *content* side of the shared catalogue: where its
first hundred thousand nodes come from and who may change them. The
*contract* side — dimension terms, unit families, match degrees, the
upstream-vs-local tripwire table — is `docs/plans/ontodag-coupling.md`.
Governance economics adopt factbond's mechanism design
(`factbond/docs/plans/mechanism-design.md`); the coupling mechanics are
`docs/plans/P3-guarantee-coupling.md`; catalogue capture is
`docs/plans/THREATS.md` T6 (primary: `factbond/docs/plans/THREATS.md`);
the book these categories serve is `docs/plans/P1-federated-book.md`;
thickness — offers, not nodes — is `docs/plans/adoption-and-thickness.md`.

## 1. The seed set, and why these licenses

Every taxonomy that stayed maintained has somebody paid to maintain it —
GS1 by members, Google by its shopping feed. Self-maintaining a hundred
thousand nodes recreates the semantic-web maintenance vacuum, so the
catalogue imports actively-maintained taxonomies on *their* release
cadence and spends its own governance budget only on the marginal edges no
upstream will assert. The seeds (decided 2026-08, imported with P1):

| seed             | covers                        | license / cadence   |
|------------------|-------------------------------|---------------------|
| GS1 GPC          | goods; Segment/Family/Class/  | free; ~2 releases   |
|                  | Brick + brick attributes      | a year (GSMP)       |
| UNSPSC           | services; 5 levels, ~tens of  | free with a no-cost |
|                  | thousands of commodities      | account             |
| Google Product   | ~6,000+ node human-legible    | free open standard  |
| Taxonomy         | upper layer and cross-map     | (plain-text/TSV)    |
| Wikidata         | long tail, cross-taxonomy     | CC0                 |
|                  | bridging                      |                     |

**ECLASS is skipped** despite being the industrial-strength option
(IEC 61360 property model, dominant in German manufacturing): it is
copyright-licensed and paid — per-release "Single license", multi-year
"Concordance license", or membership fees — and a content-addressed public
catalogue cannot carry nodes whose redistribution is licensed. PCS2OWL
(Hepp's group, OWL conversions of several classification systems) is
reused as converter scaffolding. GPC brick attributes map to ontodag
parametric dimensions — the one seed feature touching the contract side;
rules in `ontodag-coupling.md`.

## 2. The import pipeline: releases become roots, never edits

Each upstream release runs through a repeatable importer (decided 2026-08,
lands with P1) whose entire output is **a new pinned catalogue root, an
explicit old→new category mapping, and a diff report**. The shared
catalogue is never mutated in place — grow-only merge makes in-place
correction impossible anyway (ontodag EVOLUTION §1: "Vagueness is
repairable by addition; wrongness is not repairable at all") — so the
pipeline treats every release the way eBay treats category revisions:
versioned trees with stable ids, scheduled revisions, migration notices to
sellers. The mapping file *is* the migration notice; a release without one
does not publish.

Pinned roots make this cheap for makers. An offer pins the
`ontology_root` it was classified under, so a release re-files nothing:
old offers keep matching under their pinned root until their makers
republish against the new one, using the mapping. This is the direct
answer to the Amazon browse-node trust failure — no open spec, no release
notes, unilateral restructures, ML auto-recategorizing listings over
seller objections. Here **no path ever re-files an offer without the
maker**, and "which catalogue said the cello fits the crate" is answerable
forever (ARCHITECTURE.md §4). Determinism is the pipeline's own gate:
equal release input must produce a byte-identical root on independent runs.

## 3. Adoption by fingerprint: the Mercury defense

ontodag's `merge` unions same-named nodes silently — two vocabularies each
defining `Mercury` fold into one wrong node with no error (ontodag
PACKS.md §3). In a marketplace this is not a naming quibble: a wrongly
merged category changes what `covers`/`satisfies` matches, which changes
what *settles*. The defense (decided 2026-08, lands with P1, following
PACKS §7's trust box):

- **Adopt by fingerprint, never by name.** Every seed release and
  third-party vocabulary is adopted as a pinned golden root (the pattern
  ontodag ships for its `crypto-core` pack, golden root `4d501a43…`); the
  importer records which root each release came from.
- **Diff-preview before adoption.** The importer computes the full
  same-name union set against the current catalogue and refuses to publish
  while any collision is unresolved. Each collision resolves by explicit
  human decision recorded in the release mapping: either the union is
  intended (a cross-map — GPC brick and UNSPSC commodity genuinely naming
  one thing) or a qualified plain name is minted (`mercury-element`,
  `mercury-planet`). No upstream Namespaces feature is assumed — ontodag
  lists Namespaces as under discussion, and lookalike names (`XBT`) remain
  a social residue the importer cannot close.
- **Pack-root endorsement.** Adoption is announced as a signed endorsement
  record over the adopted root (the provenance-store speech-act shape), so
  "who vouched for this vocabulary, against which basis" is auditable —
  and becomes the natural subject for a factbond bond at P3. Upstream
  flags pack-root attribution as design-needed; this is loopmarket
  registering as its first consumer.

## 4. The governance split: gate the schema, free the offers

Wikidata is the governance precedent that survived contact with users; its
load-bearing move is the split: property creation centrally gated while
items are open-edit, 88% of edits by bots admitted through a formal
Request-for-Permissions process, automated scoring (ORES) plus a
protection policy for hot items. The vandalism base rate justifies the
asymmetry — among reverted edits by non-trusted users, ~68% were
intentional vandalism, ~92% at least damaging. loopmarket adopts the split
with an economic upgrade path (decided 2026-08):

- **Schema (⊑ edges) is gated now, bonded later.** Until factbond ships,
  the gate is administrative: a named maintainer set merges seed releases
  and marginal edges under written conduct and removal rules adopted
  *before the first dispute* — the Croatian Wikipedia capture (2011–2020,
  ~10 admins) was diagnosed as missing constitutional constraints on
  administrators, a rules-about-rulers failure (TeBlunthuis et al., CSCW
  2024). With P3 the gate becomes economic: `assert_edge(sub, supers,
  bond=)` already carries the argument, and a factbond bond is the
  economic form of Wikidata's property-creator right — anyone may assert,
  but assertion has a price and a dispute path (§6).
- **Offers stay permissionless.** An offer is an instance, not schema; its
  spam floor is postage and fees (`P1-federated-book.md` §8, THREATS.md
  T2), never an admissions committee. The importer and any LLM authoring
  service are automation and *do* register — Wikidata's bot-admissions
  lesson — but registration gates write throughput, never market entry.
- **Consumers read pinned roots, never a live head.** The 2018 OSM
  "Jewtropolis" vandalism propagated to Mapbox and Snapchat because
  consumers tracked the head; loopmarket offers structurally cannot (they
  pin roots), and solver and settlement tooling must never be looser than
  the offers are.

## 5. Two norms, instrumented

OSM's two surviving norms transfer, but as protocol rules with
instruments, not wiki etiquette:

**Never re-mean a category.** OSM: don't unilaterally redefine existing
tags. Content addressing already enforces the hard half: a category is a
name inside a pinned root, offers pin the root, so nobody can change what
a settled offer meant — re-meaning is representable only as a new root
plus a mapping entry, which is exactly the §2 pipeline. The instrument is
the mapping file's mandatory-ness: a release that renames, splits or
re-parents without mapping entries fails the importer, loudly (U7's
fail-closed spirit applied to releases instead of names).

**Don't tag for the solver.** OSM: don't tag for the renderer. The
loopmarket abuse has a name — **category-stuffing**: filing an offer under
categories it does not honestly satisfy, to widen its match set. This is
the over-claiming failure GoodRelations' incentive lesson predicts:
fail-closed matching makes annotation the price of visibility, so the
pressure is always toward claiming *more*. The tripwire metric (decided
2026-08, instrumented from P1): **per-maker, per-category match-to-settle
conversion** — offers generating matches far above the book median while
settling far below it are the stuffing signature, because `check_match`
and counterparty selection filter what U7-satisfying breadth cannot fake.
The metric is diagnostic only, never reward-bearing; anything reward- or
reputation-bearing reads U12, quoted exactly — "reward/reputation
statistics count settled fee-paid loops only" — so stuffing buys attention
at postage cost and earns nothing. Enforcement teeth arrive with P3: a
settled leg that fails delivery *because* the category was stuffed becomes
factbond loss experience against both the maker and the walked edge (§7),
and premiums reprice the maker's legs (T7 lemons routing, THREATS.md).

The catalogue's admission boundary is the two-axis criterion ontodag holds
at its wall (DATABASE_DIRECTION): admissible content is monotone under
merge *and* cheaply semantically canonicalizable. Anything failing either
axis — disjointness, ratings, quality claims — stays out of the asserted
graph and arrives, if at all, as policy or as bonded assertions beside it.

## 6. Contested-edge economics (T6)

Wikidata's edit wars concentrate on identity-adjacent properties ('sex or
gender' highest — arXiv 2210.15495); loopmarket's equivalents are
value-laden placements — *organic*, *halal*, *refurbished* — where an edge
is a marketing claim wearing a ⊑ suit. The economics (decided 2026-08,
lands with P3; adopted from factbond, not redesigned):

- **Bonds scale with settlement-weighted centrality.** Bond =
  max(adjudication-cost floor, k × settlement-weighted reliance/centrality
  of the claim) — factbond `DESIGN.md` §3's revised doctrine. The
  centrality ledger is U12's: witness-edge traffic from settled fee-paid
  loops (`P3-guarantee-coupling.md` §2), inflatable only by paying real
  fees to real counterparties. Static graph degree was rejected — degree
  is farmable at the cost of a few asserted edges, the Curve-wars lesson
  that any cheap centrality proxy becomes the thing attackers manufacture.
  This is Wikidata's protection policy in economic form: hot nodes get
  expensive automatically, with no administrator deciding what is hot.
- **No token-voting curation, anywhere.** AdChain — the first mainnet TCR,
  April 2018 — died of exactly what a voted catalogue would import: no
  shared judging criteria, purely financial incentives attracting
  mercenary voters without domain knowledge, per-entry voting that does
  not scale, no demand-side users. The curation signal here is **per-edge
  insurance loss experience from paid coverage** — usage generates the
  signal, underwriters are paid domain specialists, nothing is voted on in
  the happy path, and adjudication runs only on dispute under factbond's
  constitution (F5, quoted exactly: "tribunal independence + soulbound
  stake" — no liquid adjudication token for a Votium-style bribe market to
  price). Capture economics and the escalation ladder are T6's primary
  entry in `factbond/docs/plans/THREATS.md`; the loopmarket-side
  residual — a captured maintainer set during the administrative period —
  is registered below.
- **Bonds attach to claim subjects, not edges** (F2): canonical reduction
  can re-route edges innocently; the witness list is edge-shaped, the
  bonded claims are subject-shaped, the translation is factbond's
  (`factbond/docs/plans/records-and-anchoring.md`).

## 7. LLM-assisted authoring: retrieve-then-verify

Classifying an offer into ~10⁵ nodes by hand is the annotation cost that
killed OWL-S-era marketplaces; LLMs remove it only under discipline,
because zero-shot single-model mapping into large taxonomies is unstable —
prompt sensitivity, hallucinated labels, category inflation — and
structured ensembles across model families consistently beat any single
model's ceiling (eLLM, arXiv:2511.15714; the LLMs4OL challenges at ISWC
2024 and 2025, where hybrid pipelines with RAG and ensembling win and pure
prompting loses; Amazon Science's dual-expert paradigm). The pattern that
ships (decided 2026-08, lands with P1 alongside the seeded catalogue):
**retrieve-then-verify** — embed the catalogue, retrieve top-k candidate
categories, have the model select from that closed list only, then
validate every emitted name against the catalogue and reject anything not
in it. This is U7 wearing an authoring hat: the LLM proposes,
`Ontology.satisfies` verifies, free-generated vocabulary never enters an
offer. Entry goes through ontodag's surface contract — canonical echo
before confirm, and the maker's pre-elaboration spelling is never stored
(it would enter `canonical_bytes` and churn `offer_id`).

The economics matter more than the accuracy. GoodRelations got real
deployment only on 2012-11-08, when Google/Bing/Yahoo/Yandex absorbed it
into schema.org — annotation happened only once the annotator was paid
immediately and personally, in SEO. loopmarket's incentive is built in (an
unannotated offer is invisible), LLM authoring drops the cost to near
zero, and the third leg closes over-claiming: **a classification is the
maker's assertion** — carried unbonded today, bonded when P3 lands — so a
misclassification that costs a loop becomes factbond loss experience
against that maker and that edge. Truthful annotation becomes strictly
cheaper than stuffing, and the catalogue acquires a continuous per-edge,
per-maker reliability audit that no 2000s semantic marketplace had.

## 8. The ordinal and cyclic gaps: interim encodings

Two offer-shaped needs have no honest ontodag kind yet; both are tripwired
upstream with loopmarket named the likely first consumer. The tripwire
table — including when each interim encoding must trigger the upstream
ask — is `ontodag-coupling.md`'s.

**Condition grades (ordinal).** ontodag EVOLUTION §3 records the ordinal
gap — no kind for ordered, magnitude-free scales — and documents faking
ranks as linear dimension values (`grade(3)`) as a smell: it asserts
magnitudes the scale does not have. The interim encoding is **cumulative
threshold categories forming a plain ⊑ chain**: `condition-new ⊑
condition-at-least-like-new ⊑ condition-at-least-good`. An offer graded
like-new files under `condition-at-least-like-new`; a bid wanting
at-least-good matches through ordinary `covers`. Monotone, canonical, zero
new machinery; the honest loss: no distance semantics for near-miss
ranking, and each vertical mints its own chain — a second vertical needing
one triggers the tripwire.

**Opening hours (cyclic).** Recurring availability ("Mondays 9–17") is a
cyclic dimension; upstream has narrowed the kind to continuous periodic
ranges and queued it. The interim encoding is **unrolling**: publish
concrete service `TimeWindow`s over the near horizon — which the stamp TTL
already bounds (`P1-federated-book.md` §6) — as separate offers or window
lists, exactly what the `DimensionIndex` files today. Never encode
recurrence as a category name ("every-monday" is not fits-within, and
re-meaning it later is the §5 trap). When unrolled windows dominate book
size, the upstream ask fires.

Solver query-category-set logging runs from day one (owned by
`ontodag-coupling.md`): ontodag's parked index machinery opens on measured
hot workloads, and the catalogue should arrive at that gate carrying data.

## Gates

- **G1 — reproducible import.** The importer, run twice independently on
  the same seed release, produces byte-identical roots; a release with an
  unresolved same-name collision or a missing mapping entry fails to
  publish. Checkable in CI with fixture seeds; no network.
- **G2 — re-import survives.** A second GPC release re-imports into a
  clean mapped root with zero manual repair; offers pinned to the old root
  still match under it; a maker republishing through the mapping matches
  under the new one.
- **G3 — authoring accuracy.** Over one launch vertical's test offer set
  (`adoption-and-thickness.md` picks the vertical), LLM-assisted authoring
  files ≥90% of offers into leaf categories human reviewers accept, with
  zero emitted names outside the catalogue (the hard invariant; 90% is the
  usefulness bar).
- **G4 — Mercury fixture.** Adopting two vocabularies with a planted name
  collision is refused until resolved in the mapping; every adopted root's
  endorsement record verifies against its golden fingerprint.
- **G5 — stuffing tripwire live.** The match-to-settle metric computes per
  maker and per category on the P1 book, flags a planted stuffed-offer
  fixture, and demonstrably feeds nothing reward-bearing (U12, checkable
  from the ledger).

## Open problems

- **Cross-seed alignment** (work package: this pipeline +
  `ontodag-coupling.md`). GPC bricks, UNSPSC commodities, Google
  categories and Wikidata items partially name the same things; every
  cross-map edge is a judgment call made at import time, at zero bond.
  Wrong cross-maps are the Mercury problem in slow motion — diff-preview
  catches name collisions, not meaning collisions. Bonded cross-map
  assertions (P3) are the eventual answer; recording every cross-map in
  the mapping file at least makes them disputable objects in the interim.
- **The bootstrap-period gate** (work package: this doc; constitution
  shape from `factbond/docs/plans/mechanism-design.md`). Until bonds
  exist, "gated" means an administrative maintainer set — a trusted
  component in a system built to avoid them, and T6's loopmarket-side
  residual. The written conduct and removal rules must exist before the
  first contested merge; their draft is this work package's first
  deliverable, and the period's length is bounded by P3's shipping gate.
- **Cold-start bond sizing** (work package:
  `factbond/docs/plans/mechanism-design.md` + `phase0-simulation.md`).
  Settlement-weighted centrality is empty at bootstrap — no settled
  traffic before there is a market — so early bonds collapse to the
  adjudication-cost floor everywhere, exactly when the catalogue is
  cheapest to capture. Candidate mitigations (import-time priors from seed
  structure, per-edge exposure caps until traffic exists) are factbond's
  to evaluate; the k parameter and its ramp are theirs.
- **The ordinal and cyclic kinds** (work package: upstream ontodag, via
  `ontodag-coupling.md`'s tripwire table). The §8 encodings are honest but
  lossy; the upstream asks are filed with named triggers. If ontodag's
  levels-of-measurement work lands a real ordinal kind, the cumulative
  chains become a migration — through the §2 pipeline, like any release.

## What this document does not promise

- **Seeds do not confer correctness.** GPC and UNSPSC encode industry
  consensus with its own politics and errors; importing them imports those
  errors at zero bond. The catalogue certifies asserted structure at a
  pinned root, never world-truth — and F7 holds on every surface:
  *"certified ≠ true"*.
- **A hundred thousand nodes is not a market.** Vocabulary without offers
  is a dictionary; thickness is `adoption-and-thickness.md`'s problem, and
  the semantic-web postmortem is explicit that semantics alone never
  created liquidity.
- **The instrumented norms are tripwires, not walls.** A determined
  stuffer pays the postage floor and stuffs; the claim is that stuffing
  earns nothing reward-bearing (U12) and becomes repriceable loss
  experience (P3), not that it becomes impossible.
- **"Gated" is administrative until P3.** The bonded-schema economics are
  decided, not running; between P1 and P3 the catalogue's integrity rests
  on a maintainer set under written rules, and this document says so
  rather than pretending the bonds exist.
- **No LLM accuracy beyond the gate.** Retrieve-then-verify bounds the
  failure mode — the pipeline can never invent vocabulary — not the error
  rate; G3's 90% is a shipping bar for one vertical, not a general claim.
