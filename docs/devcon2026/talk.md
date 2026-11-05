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

Everything is one kind of record: an offer, signed by its maker. It says
what, in terms from a shared catalogue; where, as a box of GPS
coordinates; when, as a time window; and a price on the maker's own
scale. That is a private unit where only ratios count, so k gives and m
wants need k plus m numbers instead of k times m exchange rates. [It can
carry a bond and name an arbitrator.] Its id is the hash of its canonical
bytes. [The last line is the real command.]

### 5. Loops: the trade nobody could find (45 s)

Solvers combine offers into loops. The simplest is barter: Alice has
apples and wants a ride; Bob drives to the airport and wants apples. That
needs a double coincidence of wants, and it is rare. Now say Bob wants
money, not apples, and Carol pays in USDC and wants apples. No two of
them can trade, but the three can: apples to Carol, USDC to Bob, the ride
to Alice. Money is just one more leg. The test: multiply the rates round
the loop, and if the product is above one there is surplus. In minus
logs that is a negative cycle, and Bellman–Ford finds it. [It is the
search DEX arbitrage bots run,] except that here the surplus goes to the
makers.

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
Swarm site.] The chain holds only what needs consensus.

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
  three-way loop, Bob wants money instead of apples, and Carol pays in
  USDC (Peter, 2026-11-05: "one example should include traditional USDC
  money"). It has no vegetable box. Carol is the usual third name in
  cryptography (Charlie is the other).
- **Arbitrator, not adjudicator**, on the offer card: in this repository
  an arbitrator is the key both parties chose; *adjudicator* names a rung
  of factbond's ladder (CLAUDE.md, conventions).
- **No rates on the loop diagrams.** The edges say what moves, the centre
  says ∏ r > 1, and the box under them defines r. The numbers are on
  backup slide 11 (personal scales).

## Facts the slides rely on (checked 2026-11-05)

- Every ontodag word on slide 6 is from ontodag's core pack v14, except
  `ride`, which the slide adds with `put`. The edges shown are core's, a
  selection: `fruit` also sits under `botanical-fruit`, and
  `transportation` under `commercial-enterprise`.
  `odag get food produce` returns 117 items, `almond apple apricot
  artichoke …`.
- The command on slide 4 was run in a scratch home with ontodag 0.34's
  `odag` and the installed `loop` (places `bkc` 19.065,72.865±1 km and
  `bom` 19.09,72.87±2 km, `from`/`to` as roles of `geo`, `ride` under
  `transportation`). It resolves to the rectangles on the card. `loop`
  takes UTC times with seconds, so 18:00–20:00 IST is written
  `12:30:00Z..14:30:00Z`. The bond and the arbitrator come from
  settings, and the id on the card is not that run's.
- A challenge that proves a leg wrong pays the proposer's bond to the
  challenger (`BeatClearing.challenge`). The window is 720 blocks, about an
  hour on Gnosis. Batches are `SealedBeat`'s commit and reveal.
- Sealed delivery details are ECIES to the counterparty's key, written
  into the maker's own book (`handoff.py`), not Swarm's ACT.
- The Swarm properties are Peter's list in `devcon.txt`, shortened.

## Devcon 8's speaker guidelines

Devcon 8 is in India, and its speaker guidelines
(devcon.org/Devcon8-Speaker-Guidelines-2026.pdf) forbid promoting crypto
assets or regulated services. They also restrict QR codes and links that
lead to trading, ask speakers not to call digital assets "currency",
"securities", "custodian" or "depositories", and forbid live crypto
transactions and profit promises. The deck is written to stay educational:

- the QR codes and links go only to source code on GitHub;
- no asset is promoted, and USDC appears once as the example payment
  leg (twice on backup slide 10), never called a currency;
- nothing is sent on stage;
- "surplus" is the makers' gain from a trade, not a return on anything.

Clause 11(a) asks for a printed risk disclaimer on any display that
references crypto products in material that promotes goods or services.
This talk promotes nothing, so the deck carries none. If in doubt, either
replace "8 USDC" with "money" on slide 5 or add the disclaimer's sentence
under the loops.

## Before going on stage

- Scan the QR codes from the back of the room. The title slide's is the
  largest; on slide 9 the ontodag code is the smaller one.
- Rehearse once with a timer. Slide 5 and slide 8 are the long ones.
- Questions: the CoW comparison's §7
  (`../talk/cow-protocol-comparison.md`) has the expected questions with
  answers. Backup slides 10–13 are after the last slide.
