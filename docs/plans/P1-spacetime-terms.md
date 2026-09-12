# Spacetime as catalogue terms: `service` and `where` leave the offer

Status: work package, written 2026-09-12 from the CLI design discussion of
2026-09-11 and its continuation on 2026-09-12 (Peter and Claude). It
supersedes the session note `where-elimination.md` of the same morning;
that note's argument is §1 here. Two rulings by Peter on 2026-09-12 fix
the design: **cells and region nodes are the exact truth and the disc
retires** (§4), and **a term's match relation is declared in the
catalogue, not in code** (§3). Step 2 of the path (§5) landed the same
day; the record change (step 5) landed that night. Later the same day Peter
ruled that v2×v3 pairs are refused at matching (open problems), and
added two more: **no discs anywhere after v3** (§4) and **`when`/`where`
are optional at publication** (§2, §3) — an internet service has no
sensible place, and an offer with no time stands for any time until
withdrawn, dangerous but sometimes exactly what is meant. And two that
sharpen the package (Peter, 2026-09-12, evening): **`valid` may be
open-ended** — an offer stands until its tombstone (§2); and **loopmarket
names no heads** — not even optionally: the maker puts whatever spacetime
terms they want into the conjunction as ontodag categories, and the one
thing the core knows is the `service-role` marker that says which heads
match by overlap (§3).

Where it sits: this is the implementation package for
`ontodag-coupling.md` §2 ("spacetime becomes dimension terms, lands with
P1") plus the schema consequence that document left implicit — the offer's
`service` window and `where` disc are *fields of the P0 shape*, not
concepts of the model, and they go. `cli.md` §2 and §4 already speak the
target grammar; `P2-loop-selection.md` §10 (composition along a dimension)
consumes the coordinates this package puts into the conjunction.

## 0. One-line version

An offer's place and time are terms in its conjunction like everything
else; a term's head says whether it matches by containment (what the thing
is) or by overlap (where and when it changes hands); the catalogue declares
which; the exact geo truth is cell containment; so `service` and `where`
leave the record at the v3 bump and nobody retypes an offer.

## 1. History: how the separation arose, and the 2026-09-11 thread

**The P0 shape.** `Offer` carries `Thing.concepts` (a conjunction of
catalogue names), `service: TimeWindow`, `where: GeoDisc` and `valid`.
Meaning matched through the catalogue; time and place matched through
exact geometry in `schema.py` — interval overlap, haversine disc
intersection. `ARCHITECTURE.md` §3 called them "catalogue dimensions" from
the start, but ontodag had no parametric dimensions in the P0 weeks, so
they lived beside the taxonomy as fields with their own gates in
`check_match`. The split is historic: it records what the catalogue could
not yet do.

**2026-07-30.** ontodag shipped dimension lattices (parametric terms with
computed containment, `get_overlapping`). `ontodag-coupling.md` §2
decided the completed shape — time windows as exact interval terms, cells
as prefix terms, regions as nodes above their cells — and `dimensions.py`
rehearsed it in a derived index, recall-exact against the baseline. The
truth stayed in the fields.

**2026-09-11, the CLI design.** The first proposals treated the three
non-thing fields as settings or trailing keywords — `when`, `where`,
`valid`. Peter's objection, in substance: *the `where` may be unnecessary
as it is just another ontodag concept; the place / time / description
distinction in loopmarket is too strict and probably historic — we started
out that way. I'd prefer `set my_home 46.0553356,14.5053221,10m`, and
`loop ride from(my_home) to(my_supermarket)` is more doable.* Four
consequences were decided that day and built the next
(`cli.md` §2, §4, §12):

- a bare word is a category (`my_home` included); `head(param)` is a term
  in ontodag's spelling (`from(my_home)`, `when(...)`); the only
  loopmarket-only conventions are quantity-first and price-last. Nothing
  bare is reserved, so `where` cannot collide with a category;
- `where(...)`, `when(...)` and `valid(...)` survive only as *heads the
  CLI interprets onto fields*, with a startup check that they are disjoint
  from the dimension heads the loaded catalogue declares — so that when the
  fields go, the heads become ordinary catalogue heads with the same names
  and nothing changes at the prompt;
- "Why is it not ontodag's job to know where my_home is?" It is. A place
  is vocabulary, vocabulary has a store, overlays, history and pinned
  roots, and a names table in a config file would be a second, weaker
  knowledge store. Time names need nothing from loopmarket (`odag put
  evenings 'time(...)'` works today). Places need one thing upstream, a
  coordinate input spelling for `geo`; meanwhile `loop place NAME
  LAT,LON,R` writes the node with its disc as metadata, the dated bridge;
- the same-root constraint: `check_match` refuses offers pinned to
  different roots, so a private name resolves to its *public value* before
  encoding — `from(my_home)` is published as `from(u2e4x)` (Peter,
  2026-09-12: ontodag interprets the name; the CLI only carries the value).
  *Narrowed the same night, when ontodag #15 landed:* a name the pinned
  catalogue holds stands as spelled (`where(ljubljana)`), ontodag orders
  the node; only a name the root does not carry — a place in the
  personal layer — publishes as its cell.

**The two-place offer** was the motivating example and the requirement:
`want ride from(my_home) to(my_supermarket)` has an origin and a
destination, and one `where` disc cannot hold two places. The grammar
expresses it today; the field is what stops it from *matching* correctly.

**2026-09-12.** Peter widened the goal from `where` to the separation
itself: *"ancient Greek amphora" is a concept that is a combination of
location, time and description; ontodag can handle all of them together.*
That example turned out to name the one design decision the note had
skipped (§3), and the two rulings followed.

## 2. The target record

| Today (v2) | Target (v3) | Why |
|---|---|---|
| `Thing.concepts` | `Thing.concepts`, now carrying `when(...)`, `where(...)`/`from(...)`/`to(...)` and any descriptive spacetime term | one conjunction, one match walk |
| `service: TimeWindow` | *gone*; `when(a..b)` in the conjunction, **optional** — absent means any time (Peter 2026-09-12: dangerous, but sometimes meant: the offer stands until withdrawn) | §3, §4 |
| `where: GeoDisc` | *gone*; `where(cell)` or a route's `from(cell) to(cell)`, **optional** — an internet service has no sensible place (Peter 2026-09-12) | §3, §4 |
| `valid: TimeWindow` | **stays**, and at v3 **may have no end** (Peter 2026-09-12: valid until withdrawn; `TimeWindow` gains a half-bounded form, `is_open_at` follows; lifecycle is the tombstone and, on Swarm, the postage batch) | a property of the *record* (while the offer stands), read by the book against `now`, never by the catalogue against another offer; it also bounds every generated horizon (recurrence, §7 of the coupling plan) |
| `qty`, `unit`, `divisible` | **stay** for this package | quantities as unit-family terms are `ontodag-coupling.md` §3's own package (U9); widening this one to it would couple two record bumps |
| pins, `bond`, `oracle`, `arbitrator`, `nonce`, `maker`, `Tokens` | unchanged | — |

`from_record` keeps reading v1 and v2 (U2); `to_record` re-encodes each in
its native version, so old ids never move. The v3 constructor refuses
`service`/`where`.

## 3. Two relations, one conjunction: the role-head rule

**The decision the note skipped.** Today the match relation is encoded in
the *field*: concepts match by containment (the offered thing fits within
the wanted description), the service window and disc match by overlap (a
delivery instant, a handover point exists). Fold everything into one
conjunction and the relation can no longer come from the field. The
amphora shows it cannot come from the *dimension* either:

- `amphora made_in(corinth) made(time(-550))` against a want for
  `amphora made_in(greece) made(-800..-100)`: **containment**. The same
  geo and time kinds as the service fields, but *descriptive* — they say
  what the thing is, and the offered thing must be at least as specific as
  asked, exactly like a category.
- `ride from(my_home) when(evenings)` against a give `ride from(ljubljana)
  when(2026-09..)`: **overlap**. A large give region serves a small want
  place, so the direction even flips relative to concepts; what must hold
  is that the two denotations share a point.

So the relation is a property of the **role head**, not of the dimension.
`made_in` and `made` are plain heads under `geo` and `time`; `when`,
`where`, `from`, `to` are *service roles*.

**The rule, as landed in `Ontology.satisfies` (2026-09-12):**

1. Partition each side's conjunction into service-role terms (grouped by
   head) and the rest.
2. *Containment* for the rest: every wanted term is covered by some
   offered term (`is_below`), unchanged from P0.
3. *Overlap* for the roles: for each head **both** sides name, the meet
   of the offered terms and the meet of the wanted terms intersect
   (`ontodag.dimensions.intersect` is not None). A head only one side
   names constrains nothing — the other side said "anywhere", "anytime".
4. Same-head terms on one side are their meet (a conjunction *is* the
   intersection of its terms; ontodag's disjoint-parents lint refuses to
   file the empty case, and `satisfies` matches it against nothing).
5. Fail closed, with one deliberate asymmetry: a wanted category nobody
   knows never matches (U7, as before); an *extra unknown category on the
   offered side* is ignorable, because it can only narrow the offer; an
   *uninterpretable service-role term* on **either** side refuses, because
   ignoring it would silently widen the offer to "anywhere" — the
   spacetime analogue of U2's rule that a record you cannot fully read must
   not be matched.

**Why the catalogue declares the role, not the code.** Peter's ruling
2026-09-12. The marker is a plain node, `service-role`; a head below it is
a service role. Consequences: the relation is pinned with the root, so
clearing re-verifies under the same semantics the solver used (U3, U4); a
fork of loopmarket cannot change how a pinned catalogue matches; "names
live in the catalogue" applies to the names' *behaviour* too; and a
vertical can declare its own roles (`pickup`, `dropoff`, `valid_at`) with
no loopmarket release. `Ontology.declare_service_roles()` writes the four
roles the `loop` grammar speaks — `when` under `time`, `where`/`from`/`to`
under `geo` — each under its base head (inheriting the value grammar and
the kind ontodag orders it by) and under the marker; it adopts ontodag's
prelude if the bases are missing, the same merge `odag prelude` performs.
This is a catalogue write: on a persistent catalogue it moves the root and
belongs with the seed declarations, before offers pin it.

**loopmarket names no heads** (Peter, 2026-09-12, evening: *it is the
maker's job to specify an ontodag category that includes them if they
want them; loopmarket does not need to worry about when and where*).
Correct, with the one caveat above: the core must know the *relation*,
and that is exactly one catalogue name, `service-role`. So the four-head
table `SERVICE_ROLES` and the defaults of `declare_service_roles` that
landed in step 2 were seed vocabulary in the wrong place — **removed the
same evening**: the core takes the marker and nothing else, the tests
declare their own roles, and the example catalogues get theirs at step 4. A maker or a vertical declares its own
roles with `odag put from geo service-role`. Consequences downstream:
the CLI interprets no head but `valid` after v3; there is no
"anywhere / any time" rendering, because printing it would need the CLI
to know which heads are place and time — the approval block shows the
terms the offer carries and nothing more; `set where` becomes at most a
generic "terms appended to every offer" setting, or goes; the candidate
index files a give under whatever role terms it carries and asks overlap
for each role head the want names, no head hardcoded.

**Roles are heads: one head, one value space** (Peter's question,
2026-09-12 evening: *should transport's `from()`/`to()` be geo, or general?*).
Ontodag settles the mechanics (`ontodag/docs/plans/BINDING.md` §1, the
London→Rome example): roles are distinguishable category heads, declared
as prefix-kind heads over geo so role hierarchies compute; a head holds
exactly one kind and one value space, so a `from` over `geo` refuses
`from(2026-03)` at `put`; nested `transport(from(..), to(..))` is rejected
by the grammar and is at most `elaborate()` sugar. So `from`/`to` **are
geo roles**, and a pair in another dimension is another pair of heads.
Time: one handover has one interval (`when(2026-03..2026-06)` is storage
"from March to June"), but a transport has a departure window *and* an
arrival window (Peter, 2026-09-12), two separately matched intervals —
so `depart(a..b)` and `arrive(a..b)` are two calendar-kind roles under
`time` and `service-role`, each matched by overlap on its own, the mirror
of `from`/`to`; `when` stays the generic single-handover time. What the
catalogue cannot state is that arrival follows departure — a constraint
across two terms, the maker's business, like the absence of cross-part
constraints in composed wants. Denomination needs no pair: a bridge's
from and to are the offer's own two sides (it gives one currency; the
next leg carries the other).
"Transport has from, to, depart and arrive" is four catalogue lines of
the form `put("from", ["geo", "service-role"])`, each stating value
space and relation at once, in the shared seed — not a loopmarket rule;
requiring them on a `transport` is
not needed for correctness (a give with `from(A)` and no `to` says "to
anywhere") and as a recommendation is tooling: a `roles` hint in the
category's node metadata the CLI reads generically. Two-leg routes stay a
solver join (one filler per role per item; composition at the query
layer, `P2-loop-selection.md` §10). One naming ambiguity for the seed:
"amphora from Greece" is provenance — `made_in`/`origin`, never `from`,
which is the handover origin; the CLI can flag role terms generically in
the approval block by reading the marker.

**Guaranteed and possible.** Containment in either direction is the
coupling plan's *guaranteed* match; mere overlap is *possible* — a
handover point exists, and which one is the makers' business (or, once
composition lands, the solver's: `P2-loop-selection.md` §10's transport
operator moves exactly this coordinate). For P0 the match stays Boolean;
the degree ladder remains advisory (`ontodag-coupling.md` §4).

## 4. Cells are the truth; the disc retires

**The ruling** (Peter, 2026-09-12), closing the one open question the
session note flagged: the exact geo truth becomes containment on cells and
region nodes; `GeoDisc.intersects` leaves `check_match` and the disc leaves
the record.

**The argument.**

1. A disc was never anyone's real service area. It was a modelling
   convenience for the P0 weeks. A cell covering with adaptive precision
   (`ontodag/docs/DIMENSIONS.md` §9: any shape, holes, disconnected
   regions, coarse interior cells beside fine boundary cells) is a *better*
   description of a real region, and ontodag already computes containment
   on it.
2. It removes the only floats in offer identity other than quantity and
   price: `[lat, lon, radius_m]` in the canonical bytes was a latent
   canonical-JSON hazard across implementations (D9's rational question
   for the remaining two is `ontodag-coupling.md` §3's).
3. The exact check becomes `dimensions.intersect` on stored names —
   deterministic, a function of the pinned catalogue, re-verifiable by
   clearing with no geometry library (U3 gets simpler, not weaker).
4. The planar tangent-plane upgrade (`ontodag-coupling.md` §2) stops being
   a correctness path. "Within 10 km" becomes *input* convenience:
   `geo(lat,lon,r)` canonicalising to a cell, or a covering region node
   generated at publication.

**What it changes.**

- *Precision is the maker's statement.* A give covers what it says it
  covers. The input rule (built at step 5): `LAT,LON,R` becomes the
  **finest cell that contains the whole radius**, not the cell at the
  radius' precision — a point near a cell edge names the coarser cell
  that covers what the maker meant (the triangle's three places all say
  `u24`), and the exact covering is a region node (ontodag #15, landed
  2026-09-12: `where(ljubljana)` stands in the offer and the region's
  covering is a lower bound — `from(ljubljana) ⊑ from(u2)` is False until
  the region is filed under `geo(u2)`, CONTRACT G2). A want five metres across a cell edge from a give's covering does
  not match unless the covering includes the neighbour cell — and the maker
  who wanted that says so with one more cell, or a coarser one. The disc
  made the same kind of claim with a circle nobody meant.
- *The third coordinate is a node, not a number* (Peter's question,
  2026-09-12: delivery on the fourth floor). Not an elevation dimension:
  nobody delivers to 12.5 m, one building's fourth floor is another's
  height, and ground / mezzanine / P3 have no metric value — an invented
  magnitude would enter identity and lie (the ordinal tripwire in
  `ontodag-coupling.md` §7). A floor is a **sub-place node**:
  `my_home_4th ⊑ my_home ⊑ geo(u24mc)` by a plain edge under the
  building, names local to the building (numbering differs by country;
  P3 is one car park's convention); "floors 1–4" is a region node above
  four floor nodes, the same device as a region above cells. Matching
  needs nothing new — a give to the whole building serves a fourth-floor
  want by overlap, a ground-floor-only courier and a fourth-floor want are
  siblings and never match. Metric elevation stays available as a plain
  linear term where it is real (`elevation(400m..600m)` on a vineyard).
  The dependency was ontodag #15 (role heads accepting place nodes) —
  **landed 2026-09-12**: `where(my_home_4th)` stands as a stored term, the
  floor is below the building, two floors are siblings, and
  `tests/test_matching.py` and `tests/test_cli.py` carry the building
  (`test_places_regions_and_floors_match_through_the_graph`,
  `test_regions_and_floors_are_names_in_role_terms`).
- *A postal address is settlement data, not vocabulary* (Peter,
  2026-09-12: geo primary, the address secondary, but a delivery needs
  one). It rides as free text in the place node's metadata — where the
  disc used to — so no canonicalisation is ever needed: two envelopes
  spelling it differently describe one node, and the floor is in the
  text unless the maker makes it a sub-place node. It never enters the
  record, identity or the catalogue's order; matching runs on the cell
  (the node, after ontodag #15). It moves once, after clearing, to the
  one party who needs it — the delivery leg's counterparty — over P3's
  settlement channel (`P3-guarantee-coupling.md`), which is P4's Tier 1
  by construction: cell public, name private, address disclosed to a
  counterparty only. A shop or venue may instead publish its node with
  the address in the shared catalogue. Not a gazetteer hierarchy of
  country/city/street: a bootstrap problem the cell already answers.
  **Built 2026-09-12:** `place NAME LAT,LON,R [ADDRESS]` stores the text on
  the node; an offer naming the place shows it in its approval block and
  remembers it per offer (`handoff ID TEXT` overrides).
- *How the address reaches the courier — an encrypted sidecar, not a
  message* (Peter, 2026-09-12: no side channel; an adversary may offer
  courier service only to harvest addresses). Makers already hold
  secp256k1 keys (the `sig` extra; a feed owner's public key is
  recoverable from the feed's chunk signatures, a signer's from any
  `sig/` record), so no key registry: after a loop clears, the maker whose
  place it is writes `handoff/<loop_id>/<offer_id>` into their own book —
  the address (and gate codes, "ring twice") ECIES-encrypted to the leg
  counterparty's public key — a sidecar beside `sig/`, never in identity,
  OR-set-merged, carried by aggregators unread; the courier reads the fold
  they already follow and decrypts. Against harvesting: disclosure follows
  *obligation* (the record exists only for a cleared leg, under P3 only
  after the courier's bond is escrowed, so each address costs a bonded,
  slashable obligation); *timing* (write it when the service window is
  near, not at clearing); and *no address at all* (`oracle="locker"` or a
  public pickup node — the `oracle` field is where the maker names the
  settlement mode; coarse-first disclosure is the maker's dial). Home: P3's
  settlement channel (`P3-guarantee-coupling.md`), P4 Tier 1 by
  construction; ontodag's deterministic encrypted store is the later seam
  for a whole private place layer. **Built 2026-09-12:** `handoff.py`
  (ECIES: ephemeral key, ECDH, HKDF-SHA256, AES-GCM), `sigs.recover_public_key`,
  `OfferRegistry.attach_handoff`/`handoff`/`handoffs`/`loop_of`, fold
  admission of a maker's own handoffs, and the CLI's `watch`, `handoff`,
  `handoffs` (`tests/test_handoff.py`: sealing, recovery, the sidecar and
  its admission, and the two-maker flow end to end).
- *Whose job, when, where; and how anyone learns they cleared* (Peter,
  2026-09-12). A smart contract cannot keep a secret — everything it holds
  is public — so "encrypt to the contract, it re-encrypts to the courier"
  needs a threshold committee or an enclave: possible, heavy, not first.
  What the contract does is name the courier unambiguously. The
  responsibility is the place-owner's *client*, into its *own book*,
  triggered by the fill: on seeing `fill/<my offer>` it reads the loop,
  recovers the counterparty's key and writes `handoff/…`; nothing goes
  anywhere else. Timing is a settlement obligation: readable before the
  service window opens, else the leg fails on the recipient's side (a
  recipient never online between clearing and delivery cannot take
  delivery either). The CLI gets this as `watch`: poll the fold, report
  fills, publish handoffs. **Notification** is the fill record itself; the
  question is only cost: today a poll of the book (on Swarm one feed-head
  lookup per clearing book; a maker checks only its own offer ids); push
  with GSOC (per-maker topic from the address — the same mechanism the P1
  announcement channel wants, `P1-federated-book.md`); the P2 contract's
  clearing event as a third signal. The book stays the authority a client
  verifies against. **Built 2026-09-12** as `loop watch [--once]`.
- *Time was exact already.* `when(a..b)` over fixed ISO-8601 UTC seconds;
  calendar values are inclusive, `TimeWindow` is half-open, so the
  encoding rule is `[start, end-1]` — `dimensions.time_term`'s convention,
  proven equivalent to `TimeWindow.overlaps` over random windows in
  `tests/test_ontology.py`. Time zones elaborate at entry; recurrence stays
  the cyclic tripwire (`ontodag-coupling.md` §7) — `when(saturdays)` as a
  node over asserted day terms works today within an asserted horizon.
- *Input spellings survive as spellings; discs do not survive at all*
  (Peter, 2026-09-12, afternoon). `where(LAT,LON,R)` at the prompt and
  `loop place NAME LAT,LON,R` keep working; both canonicalise to a cell
  (or, later, a covering) instead of a disc, through a plain function of
  latitude, longitude and radius. `GeoDisc` and `haversine_m` are
  **deleted** at v3, not kept as helpers; `spacetime.py` keeps only the
  geohash encoder and the radius→precision table, and loses those too
  when ontodag accepts `geo(lat,lon,r)`. The place node's `disc` metadata
  is written only while the CLI still publishes v2.
- *Region nodes as service parameters* (`from(ljubljana)`) wait on
  upstream (§5, step 3b); until then role terms carry cell values, as the
  CLI already publishes them.

## 5. The path

1. **The grammar — done 2026-09-11/12** (`cli.md` §12). `where` is neither
   keyword nor alias; `where(...)`/`when(...)`/`valid(...)` are interpreted
   heads with the disjointness check; names are catalogue nodes; `place` is
   the dated bridge; role terms carry the public cell value;
   `Ontology.known` accepts interpretable terms.

2. **`Ontology.satisfies` over mixed terms — landed 2026-09-12.**
   `SERVICE_ROLE`, `SERVICE_ROLES`, `declare_service_roles`, `head_kind`,
   `is_service_role`, and the five-point rule of §3. No record change: the
   field gates in `check_match` still run beside it, and a catalogue that
   declares no roles behaves exactly as before. Tests: the amphora
   (containment, directional), the ride (overlap, both directions,
   siblings refuse, a two-place route), absent-is-unconstrained and the
   fail-closed asymmetry, same-head meets, the 300-window equivalence with
   `TimeWindow.overlaps`, and `check_match` accepting the
   broad-give/narrow-want pair under a role-declaring catalogue while a
   plain-`geo` catalogue refuses it (`tests/test_matching.py`).

3. **Upstream asks** (rows in `ontodag-coupling.md` §7):
   - (a) coordinate input for `geo` — filed 2026-09-11; deletes `loop
     place`;
   - (b) **role heads accepting a place node as parameter** — filed as
     [ontodag #15](https://github.com/petfold/ontodag/issues/15);
     **landed 2026-09-12** (ontodag main, `DIMENSIONS.md` §14: stored as
     spelled, ordered by the graph, a name outside the dimension refused;
     the covering-as-a-value refinement deferred to the anonymity
     tripwire). Consumed the same night: `Ontology.known` accepts the
     terms, the CLI keeps a catalogue name as spelled and substitutes a
     cell only for a private place (`cli.md` §12), `DimensionIndex` files
     names as spelled. Probe
     2026-09-12: with `from` declared under `geo`, `from(ljubljana)` is
     accepted and silently read as a literal cell named "ljubljana" — the
     footgun the CLI's `_value_of` exists to guard. Ask: a head declared
     under another head accepts that head's nodes as parameters and
     denotes their value (or their covering, for a region node), so
     `from(ljubljana)` stands as a stored term and `from(my_home) ⊑
     from(ljubljana)` computes. Deletes the CLI's value substitution;
     *Refinement filed 2026-09-12 (after the 0.3.0 live run put the whole
     triangle in `u24`):* a **covering as a value** — a prefix-kind
     parameter that is a set of cells, `where(u24m+u24q)`, the union
     computed setwise, canonical form the sorted minimal set — needs no
     node, hence no name, hence no privacy question; region nodes stay for
     named public places. If the grammar cannot carry it, loopmarket
     publishes anonymous region nodes named by content instead;
   - (c) **a Boolean overlap face**, `overlaps(a, b)` — filed as
     [ontodag #16](https://github.com/petfold/ontodag/issues/16), which also
     carries (d); **landed 2026-09-12** (`OntoDAG.overlaps` and
     `OntoDAG.meet`, units from the store; consumed: `satisfies`' overlap
     half is one `overlaps` per head, `Ontology.meet` folds with
     `OntoDAG.meet`, `dimensions.intersect`/`canonicalize` left
     loopmarket) — the mirror of
     `is_below` for `get_overlapping` — region nodes included on both
     sides, so region∩region needs no enumeration in loopmarket;
   - (d) graph-declared units reaching `intersect` through public API
     (today `satisfies` calls `dimensions.intersect` without the store's
     unit declarations, which time and geo do not need; a role over a
     linear head with declared units would fail closed).

4. **The shared catalogue carries the roles; the index files them — done
   2026-09-12** (`triangle.od` with the prelude, both demos,
   `DimensionIndex` role-aware, `TestRoleTerms` recall-exact; the private
   `service-time`/`service-cell` heads stay for the v2 fields until v3).
   ~~The four-head table leaves the core~~ (done 2026-09-12:
   `declare_service_roles({head: base})`, no default); the roles are
   declared in the example catalogues and by the CLI's convenience layer (`catalogue-bootstrap.md`'s release
   pipeline for the shared seed).
   `DimensionIndex.file` puts a give under its `when`/place terms directly
   — no more private `service-time`/`service-cell` heads — and
   `candidates` gains the place term, becoming one `get(...,
   overlapping=[...])` call when ontodag #14 lands (`ontodag-coupling.md`
   §5). **Done 2026-09-12 night** (#14 landed): `candidates` is exactly one
   `get([line marker, *plain], overlapping=[v2 window, role meets],
   items_only=True)`; a give silent on a role is filed under nothing for
   it and passes the overlap term unvisited (ontodag #17, resolved that
   way the same night); the `idx/{c,t,g}` index retired with it. The CLI cannot flip yet: it publishes v2 and must keep mapping
   `when`/`where` onto fields until the record changes.

5. **The v3 record — done 2026-09-12.** `service` and `where` leave `to_record`/`from_record`
   for v3 (v1/v2 still read; a v3 record carrying the keys is refused); `check_match` drops the two field gates for
   v3 pairs and relies on `satisfies`; `MockClearing` is untouched (it
   calls `check_match`); `idx/{t,g}` retire (decided 2026-09-07). The CLI
   in the same release: `_INTERPRETED_HEADS` shrinks to `("valid",)`,
   `when`/`where` pass through as terms and are **optional** — the
   "no place" refusal and the `where` default's obligation go (a `set
   where` default still applies when set), the mapping code and the
   disjointness check for them are deleted, `place` writes a region node
   (or a cell via (a)), the drafts' `Part` record carries terms, the
   approval renderer shows them. `examples/triangle.loop` is byte-identical
   across the flip — that was the whole point of step 1.

## Gates

- **G1 — relation equivalence.** Time: `when` under overlap decides
  exactly what `TimeWindow.overlaps` decides over random windows
  (**landed**). Geo: the cell rule's cases — same cell, nesting either way,
  siblings refuse, a route's two places independent (**landed**). At the
  v3 flip the triangle clears the same three legs from terms as it did
  from fields.
- **G2 — the catalogue decides.** The broad-give/narrow-want pair matches
  under a catalogue declaring `from` a service role and is refused under
  one declaring it a plain `geo` head, through `check_match` (**landed**).
- **G3 — fail closed.** An uninterpretable service-role term refuses on
  either side; a provably empty same-head conjunction matches nothing
  (**landed**).
- **G4 — id stability across the bump (U2).** Every v1/v2 record in the
  test corpus reads back to its original id; a v3 constructor refuses
  `service`/`where`; `from_record` raises on v4.
- **G5 — the prompt does not move.** `examples/triangle.loop` and every
  line in `tests/test_cli.py` parse and publish identically before and
  after the flip; the interpreted-head disjointness check fires only for
  `valid`.
- **G6 — one-query generation stays exact.** `DimensionIndex` filing
  gives under role terms is recall-exact against the baseline product
  (the existing `tests/test_dimensions.py` pattern), with place now
  pruning too.

## Open problems

- ~~**Cross-version pairs.**~~ **Decided 2026-09-12 (Peter): refuse.** A v2
  offer's truth is its disc; a v3 offer's is its cell; a view of the disc
  as a cell would say something the maker never said. So `check_match`
  refuses a pair whose record versions differ across the v2/v3 line (the
  same shape as the pin gates: agreement cannot be confirmed, so it is
  refused). Validity windows are short and `loop` can repost; an offer
  means what its record version defines (U2). Lands with step 5, with a
  test that a v2 give and a v3 want over the same cell do not match.
- ~~**Publishing policy.**~~ **Decided 2026-09-12 (Peter):** `when` and
  `where` are optional at publication too, not only in matching. An
  internet service has no sensible place; an offer with no `when` serves
  at any time and stands until withdrawn or its `valid` window ends —
  dangerous, and sometimes exactly what is meant. Neither the CLI nor U8
  admission requires them; the CLI's "no place" refusal goes at v3 (a
  configured `set where` default still fills in when present). The
  approval block shows the terms the offer carries; it cannot say "any
  time" / "anywhere", since the core names no heads (§3).
- ~~**Open-ended validity?**~~ **Decided 2026-09-12 (Peter):** `valid`
  may have no end; the offer stands until withdrawn. `TimeWindow` gains
  a half-bounded form at v3 (record-visible, so in the same bump), the
  CLI accepts `valid(2026-09-12..)`, and the approval block shows the
  open end plainly.
- **The marker's name.** `service-role` is provisional until v3 freezes it
  into published roots; `handover-role` was the alternative.
- **Region nodes as service parameters** — upstream (b). Until then the
  offer names cells and a place's covering is one cell at the radius'
  precision.
- **Composition needs these coordinates.** `P2-loop-selection.md` §10's
  operator form (`transport(u2ed→u2ef, ...)`) shifts exactly the `from`/`to`
  coordinate; the role terms are the coordinates it reads. Whether the
  operator itself is a catalogue term is the ask recorded in ontodag's
  `DIMENSIONS.md` §8.
- **Named places and privacy.** Publishing `my_home` as a public region
  node is a naming leak on top of the existing plaintext one
  (`P4-privacy.md`); role terms carrying cell values leak the cell either
  way, and the cell's precision is the maker's coarse-first disclosure
  knob — Tier 1 needs nothing new.
- **Recurrence.** `when(saturdays)` works within an asserted horizon; fine
  recurrence × long validity is the cyclic-kind tripwire.

## What this document does not promise

The catalogue certifies asserted structure, never world-truth: `from(u2e)`
matching `from(u2e4x)` says the two names share a cell, not that the
courier will be there. The overlap relation reports that a handover point
*exists*, not which one — choosing it is settlement (P3) or composition
(P2), never matching. Nothing here changes the arithmetic of loops, the
uniform offer form (U1), the pins (U4/U10), or clearing's trust-nothing
shape (U3); it moves two gates from geometry into the pinned catalogue and
removes two fields. The upstream asks were asks: every "meanwhile" above —
cell values in role terms, the CLI's value substitution, region∩region by
enumeration — had to stay livable if ontodag never built them. It did,
2026-09-12 (#15, #16, #14, in that order); the one "meanwhile" that
survives is the private-place substitution, and it survives for the
same-root reason, not for want of a grammar.
