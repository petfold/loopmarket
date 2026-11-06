# The Loop Economy: the 30-minute version

The 5-minute Devcon deck (`../slides.pdf`) grown into a 30-minute talk:
more loops and circulations, five slides on OntoDAG, and the market page
as an example of a dynamic website on Swarm. Slides: `slides.pdf`, built
from `slides.tex` with `make`. The slides it shares with the short deck
are copied from it unchanged, so its rules hold here too: no protocol
timings (latency is an open problem; see P2-batch-auction's "Latency end
to end"), money in dollars, the repository and the project's page in
every footer (ontodag's on the OntoDAG slides), @petfold on the first and
last slides.

## Timing

| # | Slide | Starts | Minutes |
|---|---|---:|---:|
| | **Part 1: the problem and the idea** | | |
| 1 | Title | 0:00 | 0.5 |
| 2 | Most good trades never happen | 0:30 | 1.5 |
| 3 | Describe, don't search | 2:00 | 1.5 |
| | **Part 2: offers, loops and circulations** | | |
| 4 | One offer form for everything | 3:30 | 1.5 |
| 5 | Why a personal scale | 5:00 | 1 |
| 6 | Loops: the trade nobody could find | 6:00 | 1.5 |
| 7 | A loop of five | 7:30 | 1 |
| 8 | A profitable loop is a negative cycle | 8:30 | 1 |
| 9 | Many candidate loops, one offer: selection | 9:30 | 1 |
| 10 | One want, many gives: a circulation | 10:30 | 1.25 |
| 11 | Quantities: aggregation and capacity | 11:45 | 1 |
| 12 | Parts: a want of several things | 12:45 | 0.75 |
| 13 | The object: a circulation on a hypergraph | 13:30 | 1 |
| | **Part 3: OntoDAG** | | |
| 14 | Categories form a DAG | 14:30 | 1 |
| 15 | put and get | 15:30 | 1 |
| 16 | Typed values | 16:30 | 1 |
| 17 | Matching in loopmarket | 17:30 | 1.25 |
| 18 | A shared catalogue, pinned by every offer | 18:45 | 1 |
| | **Part 4: Swarm and the page** | | |
| 19 | Swarm: a server nobody owns | 19:45 | 1.25 |
| 20 | One market from many books: the fold | 21:00 | 1 |
| 21 | The market in a browser | 22:00 | 1.25 |
| | **Part 5: clearing and settlement** | | |
| 22 | From offer to delivery | 23:15 | 1 |
| 23 | The sealed batch | 24:15 | 1 |
| 24 | Optimistic clearing | 25:15 | 1 |
| 25 | Settlement | 26:15 | 1.25 |
| 26 | Who pays for what | 27:30 | 0.75 |
| 27 | CoW Protocol and loopmarket | 28:15 | 1 |
| 28 | Where it stands | 29:15 | 1 |
| 29–30 | Backup: invariants, the stack | Q&A | |

That is about 30¼ minutes. If time is short, cut 5, 13, 18 or 26: each
is a detail the slides around it can carry.

## Notes

**1. Title.** The code is behind the QR code; the page is loopmarket.eth.limo.

**2. Most good trades never happen.** As in the short talk. Land the last
line: trades fail on discovery, not on price.

**3. Describe, don't search.** The three words are the talk's plan:
*combinatorial* is part 2, *universal* is part 3 (the catalogue),
*permissionless* is part 4 (Swarm). End on the CoW line.

**4. One offer form.** Walk the card top to bottom. The command under it
is real: `Jio` and `BOM` are places declared with `loop place`, so the
offer publishes only their boxes.

**5. Why a personal scale.** k gives against m wants need k×m exchange
rates, and those can contradict each other; one private scale needs k+m
prices, and every rate is a ratio of two of them, so nobody can arbitrage a
maker against herself. Nothing is issued or held; round a loop the scales
cancel.

**6. Loops.** The rates come from these prices, each on its maker's scale:
Alice gives apples at 10 and wants the ride at 12; Bob gives the ride at 5
and wants apples at 6, or the $8 at 9; Carol gives the $8 at 20 and wants
apples at 16. A rate is the wanter's price over the giver's. Both loops
come to a gain of 1.2 per leg, and clearing shares it equally.

**7. A loop of five.** Nobody can trade with the person they want
something from, because that person wants something else. Five makers
clear at once. Say what the slide doesn't: the longer the loop, the more
trades exist that no search will ever find.

**8. A negative cycle.** The three weights are −ln 1.6, −ln 0.45 and −ln 2.4;
they sum to −ln 1.728. DEX people know this as arbitrage detection. The
difference: the surplus goes to the makers, not to the searcher.

**9. Selection.** Two candidate loops need Bob's one ride. The packing
takes the set worth most under every offer's capacity, scored in logs, so
no common unit is needed. Exact while small (branch and bound with a work
budget, not a clock), greedy beyond; both deterministic.

**10. A circulation.** The buyer wants one thing: a bookcase *at the
flat*. The shop sells it at the shop; the courier sells carriage. Neither
is conditional on the other; the conjunction is the buyer's. The courier
offers `transport(furniture)`: the argument matches the other way round,
so a bookcase (furniture in ontodag's core) clears through him and a piano
(a musical instrument) does not.

**11. Quantities.** Aggregation: several gives of one thing, each a share,
summing to the want's quantity (the six helpers). Capacity: a divisible
give serves several loops, its fills never past its quantity (U11); a
floor (`8seat..15seat:1`) means at least eight in any one loop.

**12. Parts.** The theatre and the driver don't care about each other;
only you do, so the coupling lives in your want. One price for the lot,
split at clearing. Bundles on the give side are kept out on purpose.

**13. The hypergraph.** For the theory-minded: generalised flow,
circulations, potentials. The line that lands with engineers: clearing
prices are node potentials, so verifying a proposal is linear in its legs.

**14. OntoDAG: a DAG.** Real edges from ontodag's core pack (v14). Arrows
point up, to the wider category. `ride` is not in core; the slide adds it
with `put`.

**15. put and get.** The commands and their output were run in a scratch
store. The point of the Japan example: the boarding pass is found under
Japan though nobody filed it there.

**16. Typed values.** The flight query finds a summer flight with no edge
between the date and the summer. `geo(48.8584,2.2945±500m)` is the Eiffel
Tower. Values are exact rationals, so every replica orders them alike.

**17. Matching.** Three relations, one rule: whoever fixes a value states
a fact, whoever leaves it open states what they accept, and the fact must
lie within the acceptance. Meaning goes one way (give within want), place
and time either way, an operator's argument the other way.

**18. A pinned catalogue.** Why roots matter: two offers pinned to
different catalogues never pair, so a match never changes meaning after
the fact. The core is built by consensus across eight sources; its packs
are on Swarm.

**19. Swarm.** As in the short talk.

**20. The fold.** Every reader can compute the market from the announced
books; the same books give the same root, so an aggregator is only a
cache, and one that drops a book publishes a root nobody else gets.

**21. The market in a browser.** The example of a dynamic website on
Swarm: the page is static content behind a feed (a new version moves the
feed; loopmarket.eth stays), and everything it shows comes from other
feeds and from chain events. loopmarket's own Python runs in the page
under Pyodide, so the page folds exactly as `loop fold` does. Through your
own Bee node it also makes, signs and publishes your offers into your own
book, withdraws them, and announces your book (one transaction it signs).

**22. From offer to delivery.** As in the short talk; no timings.

**23. The sealed batch.** Commit a hash, then reveal; the outcome is a
function of the revealed set, with the baseline's loops as a reserve bid.
The fairness filter is CoW's idea, credited.

**24. Optimistic clearing.** Why challenges at all: the contract records
commitments instead of checking every leg, and anyone can make it check
one. Who challenges: the makers a false batch would bind, rival solvers,
anyone after the bond. Be honest that challenging is manual today
(P2-batch-auction's "Makers' own challenges").

**25. Settlement.** The question at the top is the design's centre. Most
cases settle with no ruling; a dispute goes to the arbitrator both sides
named; factbond is for high stakes among strangers.

**26. Who pays.** The protocol takes nothing and gives nothing: a real
loop looks exactly like a wash trade, so rewards tied to volume would pay
people to trade with themselves.

**27. CoW.** Same family, different market. The answers to the questions
CoW people ask are in `../../talk/cow-protocol-comparison.md` §7.

**28. Where it stands.** Live at test amounts; what stays hard. Thank you.

## Facts checked for the new slides (2026-11-06)

- Core v14: `bookcase` is under `furniture`; `piano` is under
  `musical-instrument`, not furniture; `jigsaw` is under `saw` and
  `power-tool`; `delivery` under `service` and `transport`.
- `odag put`/`get` on slide 15, and the summer query on slide 16, were run
  in a scratch store with ontodag 0.34's `odag`.
- The −log weights on slide 8: −ln 1.6 = −0.470, −ln 0.45 = +0.799,
  −ln 2.4 = −0.875; the sum is −0.547 = −ln 1.728.
- Selection, aggregation, parts and circulations as described in
  `selection.py`, `matching.check_aggregate`, `matching.check_parts` and
  `graph.Circulation`; the browser page as in USER-GUIDE §11.2.
- Storage as an operator (moving a thing in time) is not built, so the deck
  shows transport only.
