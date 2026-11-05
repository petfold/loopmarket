# The Loop Economy: the 5-minute lightning talk

Devcon 8, Mumbai, Lightning Stage, Friday 6 November 2026, 11:00–11:07
(the schedule gives the slot 7 minutes; the talk is planned for 5).
Accepted title: *The Loop Economy: A Universal Combinatorial Marketplace
Without a Platform* (cfp.devcon.org/devcon8/talk/KFG7ZQ). Speaker: Peter
Földiák. Slides: `slides.pdf`, built from `slides.tex` with `make`. The
brief is `devcon.txt`.

## Timing

| # | Slide | Starts | Seconds |
|---|---|---:|---:|
| 1 | Title (QR code to the repository) | 0:00 | 10 |
| 2 | Most good trades never happen | 0:10 | 35 |
| 3 | Describe, don't search | 0:45 | 30 |
| 4 | One offer form for everything | 1:15 | 30 |
| 5 | Loops: the trade nobody could find | 1:45 | 45 |
| 6 | OntoDAG: one relation, *fits within* | 2:30 | 35 |
| 7 | Swarm: a server nobody owns | 3:05 | 35 |
| 8 | From offer to delivery | 3:40 | 45 |
| 9 | Where it stands (two QR codes) | 4:25 | 35 |
| 10–13 | Backup: composition, personal scale, CoW, who pays | Q&A only | |

The script below is about 800 words, roughly 5½ minutes at a calm pace.
The sentences in [brackets] can go, which brings it to about 700 words, or
5 minutes.

## Script

### 1. Title (10 s)

I'm Peter Földiák. This is the loop economy: a marketplace for anything,
with no platform in the middle. The code is behind this QR code.

### 2. Most good trades never happen (35 s)

Markets are how strangers cooperate, voluntarily. Online, that
cooperation runs through search: shop after shop, each with its own
catalogue, terms and checkout, and you never know whether you found the
best deal. Or it runs through a platform that owns the index. It takes a
cut, decides who is seen, and can delist anyone. So most trades that
would make both sides better off never happen. The price is not what
stops them. Finding them costs more than they are worth.

### 3. Describe, don't search (30 s)

So don't search. Say what you give and what you want, and let algorithms
find the trade. Three properties. *Universal*: anything that can be
described precisely: rides, repairs, storage, energy, care, and money as
well. *Combinatorial*: many offers combine into one trade. *Permissionless*:
every maker keeps their own offer book on Swarm. If you know CoW
Protocol: CoW finds coincidences of wants among tokens, to beat the AMM
price. We look for them where there is no AMM to beat.

### 4. One offer form for everything (30 s)

Everything is one kind of record: an offer, signed by its maker. Here
Bob offers a ride from the Jio World Centre to the airport. It says
what, in terms from a shared catalogue; where, as boxes of GPS
coordinates; when, as a time window; and a price on Bob's own scale.
That is a private unit where only ratios count, so k gives and m wants
need k plus m numbers instead of k times m exchange rates. [It can carry
a bond and name an arbitrator.] Its id is the hash of its canonical
bytes. [The last line is the real command.]

### 5. Loops: the trade nobody could find (45 s)

Solvers combine offers into loops. The simplest is barter: Alice has
apples and wants a ride; Bob drives to the airport and wants apples. That
needs a double coincidence of wants, and it is rare. Now say Bob wants
money, not apples, and Carol pays dollars for apples. No two of them can
trade, but the three can: apples to Carol, eight dollars to Bob, the ride
to Alice. Money is just one more leg. The numbers on the arrows are the
rates. Multiply them round the loop, and if the product is above one
there is surplus: 1.44 for the pair, 1.728 for the three. [That is 1.2
per leg in both, and clearing shares it equally.] In minus logs it is a
negative cycle, and Bellman–Ford finds it, as in DEX arbitrage, except
that here the makers keep the surplus.

### 6. OntoDAG: one relation, fits within (35 s)

What does "what" mean? That is OntoDAG, the shared catalogue. Categories
form a DAG, not a tree: an apple is food and produce at once. There is
one relation, *fits within*. You put a word under its parents, and get
returns the intersection of cones. Space and time are categories too: a
geo box or a time window, ordered by computation. [The catalogue is
canonical: equal content, equal hash, and every offer pins the catalogue
it was written in.] A give matches a want when it fits within it, in
meaning, place and time.

### 7. Swarm: a server nobody owns (35 s)

Where do the offers live? On Swarm, which gives us a server nobody owns.
Content addressing: an offer's id is its hash, and the same books always
give the same root. Feeds: each maker's book is their own feed, so
identity is a key, with no account and no platform. Postage: the maker
pays for their own book, and reading it costs them nothing. Thousands of
independent nodes: nobody can delist an offer, and an aggregator that
drops a book is caught by an absence proof. [Even the market page is a
Swarm site: loopmarket.eth.limo, at the foot of every slide.] The chain
holds only what needs consensus.

### 8. From offer to delivery (45 s)

From offer to delivery. One: the maker signs the offer, writes it to
their book and announces the book once, on chain. Two: anyone can solve.
A deterministic baseline solver is built in, and we expect smarter,
specialist solvers. Three: solvers submit sealed proposals per batch.
Four: clearing trusts no solver. It checks every leg again from scratch
and commits all legs at once, and anyone can challenge it on chain for an
hour. That is clearing. Five is settlement: the makers deliver, in the
real world, with bonds in escrow. In a dispute, an arbitrator both sides
accepted decides[, or factbond's bonded assertions, for high stakes among
strangers]. Makers pay for their own storage, and a proposer pays gas and
stakes a bond. The protocol takes no fee and has no token.

### 9. Where it stands (35 s)

It is all open source and on PyPI, and it is live on Gnosis at test
amounts: books on Swarm, the solver, sealed batches, challengeable
clearing, the escrow, a command line and a page in the browser. [OntoDAG
has a core of about 4,800 categories.] What stays hard: oracles for
physical delivery, private matching with zero-knowledge proofs, wash
loops, capture of the catalogue, and books thick enough to close loops.
Thank you. The code is behind the QR codes, and I'm @petfold.

## Departures from `devcon.txt`

- **Order.** Problem, idea, offer, loops, OntoDAG, Swarm, the lifecycle,
  status. Swarm comes after the offer and the catalogue, so that its
  slide can say what it does for offers and books, and just before the
  lifecycle, which starts on Swarm.
- **The problem and the idea are two slides**, because each needs its
  own half minute.
- **The loops.** Alice and Bob barter apples for a ride. In the
  three-way loop Bob wants money instead of apples, and Carol pays $8
  (Peter, 2026-11-05: one example with money, written as dollars). It has
  no vegetable box. Carol is the usual third name in cryptography
  (Charlie is the other).
- **Rates on the legs** (Peter, 2026-11-05). They come from these
  prices, each on its maker's own scale: Alice gives apples at 10 and
  wants the ride at 12; Bob gives the ride at 5 and wants apples at 6 (or
  the $8 at 9); Carol gives the $8 at 20 and wants apples at 16. A leg's
  rate is the wanter's price over the giver's, so the pair multiplies to
  0.6 × 2.4 = 1.44 and the three to 1.6 × 0.45 × 2.4 = 1.728: a gain of
  1.2 per leg in both, which clearing shares equally.
- **Arbitrator, not adjudicator**, on the offer card: in this repository
  an arbitrator is the key both parties chose; *adjudicator* names a rung
  of factbond's ladder (CLAUDE.md, conventions).
- **The footers** carry github.com/petfold/loopmarket and
  loopmarket.eth.limo, except on the title slide (no GitHub link, which
  is under the QR code) and slide 6 (github.com/petfold/ontodag and
  ontodag.eth.limo). @petfold is beside the name on the title slide and in
  the middle of slide 9's footer. The QR codes carry `https://`, so that a
  phone camera opens them as links; no URL on a slide shows it.

## Facts the slides rely on (checked 2026-11-05)

- Every ontodag word on slide 6 is from ontodag's core pack v14, except
  `ride`, which the slide adds with `put`. The edges shown are core's, a
  selection: `fruit` also sits under `botanical-fruit`, and
  `transportation` under `commercial-enterprise`.
  `odag get food produce` returns 117 items, `almond apple apricot
  artichoke …`.
- The command on slide 4 was run in a scratch home with ontodag 0.34's
  `odag` and the installed `loop` (places `Jio` 19.065,72.865±1 km and
  `BOM` 19.09,72.87±2 km, `from`/`to` as roles of `geo`, `ride` under
  `transportation`). It resolves to the rectangles on the card. `loop`
  takes UTC times with seconds, so 18:00–20:00 IST is written
  `12:30:00Z..14:30:00Z`. The bond and the arbitrator come from
  settings, and the card shows no id from that run.
- A challenge that proves a leg wrong pays the proposer's bond to the
  challenger (`BeatClearing.challenge`). The window is 720 blocks, about an
  hour on Gnosis. Batches are `SealedBeat`'s commit and reveal.
- Clearing gives every leg of a loop the same gain (`graph.py`, the
  uniform per-leg gain).
- Sealed delivery details are ECIES to the counterparty's key, written
  into the maker's own book (`handoff.py`), not Swarm's ACT.
- loopmarket.eth.limo and ontodag.eth.limo both answered with a page on
  2026-11-05.
- The Swarm properties are Peter's list in `devcon.txt`, shortened.

## Devcon 8's speaker guidelines

Devcon 8 is in India, and its speaker guidelines
(devcon.org/Devcon8-Speaker-Guidelines-2026.pdf) forbid promoting crypto
assets or regulated services. They also restrict QR codes and links that
lead to trading, ask speakers not to call digital assets "currency",
"securities", "custodian" or "depositories", and forbid live crypto
transactions and profit promises. The deck stays educational:

- the QR codes go to source code on GitHub, and the footers to the
  repositories and the projects' pages on Swarm;
- money appears as dollars, and no crypto asset is named on the nine main
  slides; backup slide 12 says "tokens" only to compare CoW's mechanism;
- nothing is sent on stage;
- "surplus" is the makers' gain from a trade, not a return on anything.

## Before going on stage

- Scan the QR codes from the back of the room. The title slide's is the
  largest; on slide 9 the ontodag code is the smaller one.
- Rehearse once with a timer. Slide 5 and slide 8 are the long ones.
- Questions: the CoW comparison's §7
  (`../talk/cow-protocol-comparison.md`) has the expected questions with
  answers. Backup slides 10–13 are after the last slide.
