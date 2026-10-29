# loopmarket and CoW Protocol, compared (for the Devcon Q&A)

Written 2026-10-29 for the Devcon talk. The CoW facts come from CoW's own
documentation (docs.cow.fi, read from its source, github.com/cowprotocol/docs
at `4714a44` of 2026-10-28), from the CIP threads on forum.cow.fi and from
DefiLlama, all read on 2026-10-29. The loopmarket facts come from this
repository at 0.18.1 and from the contracts on Gnosis, read the same day.
Numbers that will move are marked [recheck]. Sources are in §10.

A word on names. CoW Swap is the trading front end. CoW Protocol is what
sits behind it (signed intents, the auction, the settlement contract), and
it is the thing to compare. CoW DAO governs both. Questions will say "CoW
Swap"; answer about CoW Protocol.

## 1. The answer in thirty seconds

> CoW Protocol and loopmarket belong to one family: signed intentions
> instead of transactions, a batch, competing solvers who are trusted with
> nothing essential, and the coincidence of wants as the prize. The
> difference is the market. CoW trades tokens that already have a price on
> every AMM, so a coincidence of wants is a small improvement on a trade
> that would have happened anyway; reports on CoW's own forum this year
> say that its rings almost never pay for their gas. loopmarket trades
> things that have no market at all (a vegetable box, a courier run, a
> shelf for three days), each priced on its maker's own scale, so a loop is
> not an improvement on a trade: it is the trade. The rest follows from
> that: no common unit to score in, matching by meaning in a shared
> catalogue instead of by token address, delivery after clearing backed by
> deposits and arbitration instead of an atomic token transfer, and no
> operator in the middle.

In ten seconds: *CoW finds coincidences of wants among tokens to beat the
AMM price; loopmarket finds them where there is no AMM to beat.*

## 2. CoW Protocol in October 2026

- **Lineage.** Gnosis research in 2018 on multi-token batch auctions with
  one uniform clearing price across all tokens, designed so that ring
  trades could settle; Gnosis Protocol v1 (2020); Gnosis Protocol v2 with
  CoW Swap (2021); CoW Protocol under CoW DAO, with the COW token (2022).
  The settlement contract is still called `GPv2Settlement`.
- **The intent** is an EIP-712-signed order: sell token, buy token, the
  two amounts (which fix the limit price), expiry, sell or buy,
  fill-or-kill or partially fillable, receiver, and `appData`, the hash of
  a JSON document kept on IPFS (hooks, partner fees and fast path ride in
  it). One token for another, nothing else. Placing an order costs no gas
  once the token is approved.
- **The path of an order.** The orderbook API, a service over a database
  it shares with the autopilot, takes the order. The autopilot (one per
  chain, run by CoW's core team) cuts an auction about once a block, with
  a native-token price for every token in it; for Ethereum, CoW's
  researcher Andrea Canidio budgets the 12 s as about 8 s of solving, 2 s
  of auction and 2 s to land the transaction. Solvers (a driver plus an
  engine) return bids, and each winner must land its settlement within a
  deadline (3 blocks on Ethereum and on Gnosis). `GPv2Settlement` checks
  each order's signature and expiry, that it is not already filled and its
  limit price, and only allowlisted solvers may call `settle`. Solvers
  route through AMMs, aggregators and private inventory (CoW calls itself
  a meta-DEX aggregator); a CoW is the part settled peer to peer.
- **The auction: the fair combinatorial auction (CIP-67, voted in May
  2025).** Solvers submit many bids, on single orders and on batches. The
  best bid on each directed token pair is that pair's reference; a batched
  bid that gives any directed pair less than its reference is discarded;
  of the survivors, the protocol picks the set with the largest total
  score, with all orders on one directed pair in one winning bid. Prices
  are uniform per directed pair within a bid. The single price vector
  across all tokens in a batch, the GPv1 idea, was dropped from the rules.
- **The score** is surplus plus protocol fee, converted into the chain's
  native token at prices the autopilot estimates. A token that has no
  price estimate cannot be traded.
- **Solvers are paid weekly in COW.** The performance reward is
  cap(total score − the score without solver *i* − the score *i* won but
  did not settle): second-price, VCG-like. The ceiling is a share β of the
  protocol fees the solver's settlements earned (50% on Ethereum,
  Arbitrum, Base and BNB, 100% elsewhere). The floor is a penalty per
  unsettled order of a few basis points of its volume, at most about $20.
  On top come consistency rewards (bid quality times settlement success,
  counting market orders only since September 2026) and quote rewards (a
  budget of about 10% of protocol revenue, paid per order to the five most
  accurate quotes).
- **The protocol's fees.** 2 bps of volume (0.3 bps between correlated
  assets such as stablecoins), plus half of any improvement over the quote
  on market orders and half of the surplus on out-of-market limit orders
  (each capped at 0.98% of volume). Integrators may add up to 1%, of which
  CoW keeps a quarter by default.
- **Solver entry** is bonded and allowlisted. A bonding pool holds
  $500,000 in stablecoins and 1.5M COW. Most solvers join CoW DAO's own
  pool instead, which means KYC (company, shareholders, passports),
  starting on BNB Chain, a 15% service fee on rewards after six months and
  a quarter of weekly rewards locked. Reduced pools exist ($50k and 500k
  COW, growing to $100k and 1M COW). The allowlist is an upgradeable
  contract with a manager.
- **Enforcement** has three layers. The contract enforces limit prices and
  the allowlist. The off-chain protocol enforces scores, uniform
  directional prices, winner selection, deadlines and the use of the
  contract's buffers. Governance enforces the rest: no worse than a
  reference AMM route ("EBBO"), no score inflation, no surplus shifting,
  no pennying, through monitoring, a request to reimburse within 72 hours
  and slashing by DAO vote. The autopilot itself "doesn't verify that a
  solver's transaction is valid, nor that it matches the score". There
  have been two slashings so far, both for negligence and both repaid: the
  Barter solver (CIP-22, February 2023, $166,182.97) and GlueX (CIP-55,
  November 2024, $76,783).
- **Around the core.** Limit, TWAP and programmatic orders (ERC-1271,
  ComposableCoW), Milkman, pre- and post-hooks, Atomic Bundles, flash
  loans, swap-and-bridge and x402 paid quotes. New in 2026 are fast-path
  orders, in which the winner of the quote competition settles an order
  on its own, right after it is placed, outside the batch. Ten EVM chains
  take part in the competition (Ethereum, Gnosis, Arbitrum, Base,
  Avalanche, Polygon, BNB, Linea, Plasma, Ink), and Solana is in alpha,
  proposed in September 2026 with no volume fee for its first year.
  MEV Blocker, which CoW DAO co-created, was sold to Consensys's Special
  Mechanisms Group in January 2026.
- **Size [recheck].** DefiLlama on 2026-10-29: about $3.0B in the last 30
  days, $53B in the last year and $187B since December 2023, where its
  series starts. The monthly peak was about $12.7B, in August 2025.
- **Where it is heading.** One proposal would decentralise the autopilot by
  running the auction on pod network (September 2025). Canidio called the
  discussion "long overdue" but said more research is needed before it
  could become a CIP, and it is still a forum thread. The other change opens up solving: BYOS, "Bring Your Own Solver"
  (CoW DAO's RFP of June 2026), is a bonded solver that takes signed routes
  from permissionless sub-solvers who post an escrow. It runs on BNB Chain
  only so far, with an audit under way and L2s and Ethereum next.

## 3. What they share

1. **Intents, not transactions.** A maker signs what it would accept, and
   someone else finds the way. A CoW order and a loopmarket offer are both
   signed statements with a limit, and both stand until they expire or are
   withdrawn.
2. **The coincidence of wants is the prize.** It is CoW's name, and the
   essay's first problem (the double coincidence of wants). CoW's
   documentation calls a match of three or more users a "multidimensional
   (ring) CoW".
3. **Solvers are outsiders and trusted with nothing essential.** CoW's
   contract enforces limit prices whatever the solver says, and
   loopmarket's clearing re-derives every leg (U3).
4. **Batches, so that speed buys nothing inside one.** P2-batch-auction §1
   gives loopmarket's reasoning.
5. **The fairness filter.** CoW applies CIP-67 per directed token pair.
   loopmarket applies it per offer over cycles, built in
   `auction.fairness_filter`, with the baseline's loops in every reference
   set.
6. **Several winners per batch, packed by score.** CoW's winner selection
   does this, as does loopmarket's `selection.pack` (exact while small,
   greedy beyond).
7. **One price per directed pair.** CoW has its uniform directional
   clearing price. loopmarket has a precedence rule for an offer shared by
   several loops (P2-clearing-pricing §5, designed).
8. **No gas to trade.** CoW orders are gasless. A loopmarket offer is
   signed and stored on Swarm (postage), the book is announced once on
   Gnosis for a little xDAI, and whoever proposes a loop pays to post it.
9. **Gnosis Chain.** CoW settles there among its ten chains, and
   loopmarket's registry, beat, escrow and factbond contracts live there.

## 4. Side by side

| | CoW Protocol | loopmarket |
|---|---|---|
| Traded | ERC-20 tokens (SPL on Solana, alpha) | anything the catalogue describes: goods, services, where and when they change hands, transport and storage as operators |
| Matching | the same two token addresses and a limit price | containment in the OntoDAG catalogue: the give's terms fit within the want's (place and time either way), an operator's argument the other way round |
| The intent | `GPv2Order`: tokens, amounts, expiry, kind, partial fill, receiver, `appData` | an offer: a thing (catalogue terms, quantity, step, minimum) against the maker's own scale; content-addressed (SHA-256), record versions 1–7; requirements, deposits, credentials, options |
| Unit of price | token amounts; scores in the native token at estimated prices | each maker's personal scale, never held or transferred; the score is Σ log surplus, unit-free |
| Liquidity | CoWs first, then AMMs, aggregators and private market makers | only the offers; currency legs and bridges are ordinary makers; nothing to fall back on |
| Where intents live | CoW's orderbook database; `appData` on IPFS | each maker's book on its own Swarm feed, announced by one event on Gnosis; every reader folds the books itself |
| Who runs the auction | the autopilot, one per chain, CoW's core team | no one: `SealedBeat` on Gnosis (commit, reveal); the outcome is a function anyone computes from the revealed set |
| Cadence | about one auction per block; settle within 3 blocks | beats of 240 blocks (about 20 min: 120 to commit, 120 to reveal), then a 720-block (about 1 h) challenge window before fills are final |
| Solver entry | bonded and allowlisted; KYC under CoW DAO's pool | anyone; posting a beat takes a 0.01 xDAI bond today; solver bonds through factbond are designed, not built |
| What the chain checks | signature, expiry, not already filled, limit price, an allowlisted caller | on challenge, a leg's structural half: its offers under the pinned book root (trie proofs, Swarm BMT addressing), version pins, fills within capacity, potentials, holds, item claims, statements |
| What is checked off chain | scores, winner selection, EBBO, surplus shifting: core-team monitoring, reimbursement, DAO slashing | everything, by every reader: clearing re-derives each leg (U3), each fold re-checks clearing books; catalogue fit, when contested, goes to the contract's `arbiter` |
| Winner selection | the fair combinatorial auction | the fairness filter generalised to cycles, then packing; the deterministic baseline's loops enter as a permanent reserve bid |
| Prices | uniform per directed pair within a bid | node potentials, one per maker, rates multiplying to 1 round every cycle; designed: one rate per directed pair across loops, an exact equal split |
| Who gets the surplus | the order, less the protocol's fees | the makers in the loop, the same factor each; no protocol cut |
| Solver pay | COW rewards funded by protocol fees | none built; designed as a spread leg bounded by the reserve bid; no fees, no token, no emissions |
| Atomicity | one transaction: the tokens move or nothing happens | one commit: all legs become obligations or none; delivery comes later |
| After the trade | nothing; the tokens arrived | delivery, notices and cures, deposits reserved per fill, cover, a case before an arbitrator both sides accepted, factbond as the escrow's resolver |
| Arithmetic | `uint256` token amounts | exact rationals in everything clearing re-verifies (U9) |
| Partial fills | a flag per order; market orders fill or kill | divisible gives with a step and a minimum; several gives aggregated into one want; wants of parts, all or nothing |
| Composition | hooks, Atomic Bundles, flash loans, programmatic orders | operators (transport moves a thing in space, storage in time), parts, aggregation, options |
| Conditions on the counterparty | none in the order; tokens need a price and must not be on the bad-token list | a want may require credentials under registers, a deposit, an arbitrator it accepts |
| Privacy | orders visible to solvers and on the public API | offers in plaintext (privacy is P4, staged); proposals sealed by commit-reveal; settlement text sealed to the counterparty |
| Governance | CoW DAO, the COW token, CIPs voted on Snapshot | no token, no DAO |
| Scale | about $3B a month on ten chains [recheck] | before launch: contracts live on Gnosis at test amounts |

## 5. The differences that matter

### 5.1 Liquidity: CoW improves trades, loopmarket creates them

Every pair CoW trades already has a price on an AMM, and arbitrage keeps
the orders' limits close to it. A coincidence of wants saves the AMM's fee
and some gas. Its slack is the tiny gap between limits that all sit near
one market price. CoW's own forum measured this in 2026. In July an
independent developer preparing to enter the solver competition examined
the rings in recent mainnet auctions (a small sample, by their own account).
Of 53 three- and four-token rings detected, 32 had funded orders and 14 had
limits that could all be met at once. None of the 14 carried enough
surplus to pay for its gas: they fell short by two to eight orders of
magnitude. Between 60% and 94% of the detected crossings and rings involved
dead orders (cancelled, expired or unfunded). In September a production
solver replied: "Rings: zero a day". It added that only 6–7% of winning
solutions contain more than one order.

loopmarket targets the opposite case: things with no AMM, no order book
and no outside price. There the double coincidence of wants is the whole
obstacle, and a loop is the only way the trade happens, so its surplus is
the full value of a trade that otherwise does not take place. The
arithmetic is the same on both sides. The forum's ring condition (the
product of the orders' limit rates is at most 1) is loopmarket's product of
rates above 1, written upside down. In both, the slack is the ring's entire
surplus.

For the talk, do not sell loopmarket as better CoWs. Sell it as the market
where the alternative to a loop is no trade.

### 5.2 No numeraire

CoW has to compare surplus across tokens. It converts everything into the
chain's native token at prices its autopilot estimates, it pays solvers in
COW at a 24-hour average price to blunt manipulation, and it cannot list a
token nobody can price. The research behind CIP-67 was first titled
*Combinatorial Auctions without a Numeraire* (Canidio and Henneke, 2024).
Tokens have outside prices, but the auction has no common unit in which to
share the gains from batching fairly. That is why CoW's fairness test runs
per directed pair.

loopmarket's version of the problem is total: a personal scale has no
outside price by design, and none may be assumed. The score of a set of
loops is the sum of the logs of their surplus factors. It is dimensionless
and does not change when any maker rescales its own unit. The fairness
filter compares each offer's gain with that offer's own best alternative, a
ratio on its own scale. Both are built, in `auction.py`. Importing a
reference price would import CoW's manipulation surface without CoW's
liquid markets to anchor it (P2-batch-auction §4).

### 5.3 Prices: the price vector moved from tokens to makers

Gnosis Protocol v1 and early CoW cleared a batch at one price per token,
so the rates round any ring multiplied to exactly one. That was the device
that let ring trades settle without arbitrage, and CIP-67 dropped it.
Prices are now uniform only per directed pair within a bid. In the CIP-67
discussion, one participant noted that "going forward we cannot claim
there is a single price vector per auction anymore". Another noted that
the vector had made circular trades hard to batch.

loopmarket keeps a price vector, but over makers rather than goods. Each
maker's personal scale is a node potential, every cleared rate is a
difference of potentials, and the rates round every cycle multiply to one
(Kirchhoff's voltage law, in logs; P2-clearing-pricing §10). Goods have no
price of their own; only legs do. Checking a proposal is a potential check
that grows linearly with the number of legs, and the beat contract runs it
on a challenged leg. loopmarket also fixes the split of the surplus in the
protocol: every maker in a loop gets the same factor. Today that is a
uniform per-leg gain; the exact-rational split and one rate per directed
pair across loops are designed in P2-clearing-pricing, not built. CoW
instead gives each order its own surplus and leaves the shares inside a
batched bid to the solver, policed by the fairness filter.

### 5.4 Trust: an operator, or none

CoW's orderbook and autopilot are one service per chain, run by the core
team. It decides what goes into each auction, collects the bids and picks
the winners. The contract guarantees limit prices and that only
allowlisted solvers settle. Everything else, from the correctness of
scores to fair sharing, is enforced afterwards by monitoring, accounting
and DAO votes. CoW's own researchers want this decentralised, and nothing
has shipped.

loopmarket has no such service. Each maker's book is a Swarm feed signed
by the maker, found through one event on Gnosis and folded by every
reader, so there is no orderbook to censor or to switch off. There is no
auctioneer either. Proposals are committed and revealed on `SealedBeat`,
the revealed set is on chain, and the winners are a deterministic function
of it that every replica computes the same way (U6). The first recorded
outcome stands, and a different one shows up as a visible `Disputed`
event. Clearing re-derives every leg from the pinned book and catalogue
(U3), and every fold re-checks every clearing book's loops. On challenge,
the beat contract verifies that each offer is in the pinned book (trie
proofs under Swarm's own addressing). It also checks the version pins,
the fills, the potentials and the statements a leg relies on.

Name the remaining trust before someone else does:

- **The beat contract's `arbiter` role.** It may cancel a beat on semantic
  grounds and retire the contract. Today it is a single key, meant to
  become factbond's adjudication.
- **Data availability.** A beat whose record nobody can find is
  unverifiable; only its bond deters that.
- **The catalogue.** A pinned root makes it fixed, not right; bonded
  assertions are planned.
- **Swarm and Gnosis themselves.**

The price is latency. CoW clears in seconds. loopmarket on Gnosis today
clears in beats of about 20 minutes plus an hour's challenge window. For
a vegetable box delivered on Thursday that is not the bottleneck, and both
are parameters.

### 5.5 Clearing is not settlement

In CoW the trade is the settlement: one transaction moves the tokens at or
above the limit price, or nothing happens, so there is no counterparty
risk to manage. In loopmarket, clearing commits every leg of a loop as an
obligation at once, and the makers deliver over the following days or
months. So loopmarket needs something CoW never does: an answer to "who
pays if it goes wrong, and did they check?". The pieces are:

- deposits held by `LoopEscrow` and reserved per fill;
- cover and deductibles;
- notices and cures;
- a case before an arbitrator both sides accepted;
- factbond's `Assertions` contract as the escrow's resolver.

All of them are live on Gnosis at test amounts. Most of loopmarket's
machinery is here, and so is most of its untested risk.

### 5.6 Money: fees and a token, or neither

CoW is run like a business with a treasury. Protocol fees fund COW rewards
to solvers, and since CIP-74 (late 2025) the reward ceiling is tied to
those fees. loopmarket charges no protocol fees and pays no rewards,
rebates or emissions (decided 2026-08-21). The reason is specific to
loops: a legitimate loop has exactly the shape of a wash trade, a cycle
that finances itself, so any reward linked to volume pays people to trade
with themselves. FCoin and LooksRare are the cautionary tales in
P2-batch-auction §9.

Makers pay postage and a little gas, and the solver who posts a beat pays
its gas. A solver's pay is meant to be a spread leg inside the loop it
found, bounded by the reserve bid. That leg is not built. Today nobody is
paid to solve; the free baseline and makers solving for their own offers
carry the load.

## 6. What loopmarket took from CoW, and what it refused

**The honest framing.** loopmarket did not start from CoW. Its roots are
barter circles and mutual credit (WIR, Sardex), content-addressed offers on
Swarm and a shared catalogue. The essay cites CoW as the proof that
automatic circle-finding works at scale. When P2 designed the auction, it
set out to adopt CoW's mechanism "wherever loopmarket's structure permits"
(P2-batch-auction §1). A CoW researcher who has read the docs will see
that, so say it first: *independent origin, borrowed auction engineering,
credited in the design documents*. The fairness filter in particular is
CoW's idea, generalised from token pairs to cycles.

What it took, and where that lives:

| From CoW | In loopmarket | State |
|---|---|---|
| CIP-67's fairness filter with reference outcomes | per offer over cycles, with the baseline in every reference set; read against capacity (P2-batch-auction §5) | built (`auction.py`) |
| several winners per batch | packing under the offers' capacities (§6) | built (`selection.py`) |
| uniform directional clearing prices | one rate per directed pair across loops (P2-clearing-pricing §5) | designed |
| marginal-contribution rewards (CIP-38, CIP-67), the consistency pool, the success rate | the reward template of §7 | designed, then struck with the no-fees ruling; the success rate kept |
| the settlement deadline (3 blocks on Gnosis) | the beat's deadline (§2) | designed |
| bond sizing from CoW's slashing record | solver bonds through factbond (P3-guarantee-coupling §6) | designed |
| the CIP-72 rule on quote rewards | committed in advance for any quoting tier | designed; CoW has since replaced CIP-72 with CIP-88 |

What it refused, and why:

- **The autopilot,** a trusted auctioneer. It works, and it is the
  censorship point the rest of the architecture exists to avoid
  (P2-batch-auction §3).
- **Scoring in a native-token numeraire.** It needs liquid outside prices,
  which personal scales do not have (§4).
- **Protocol fees and token rewards,** because of wash loops (§9).
- **Allowlisted solver entry.** Entry is open; bonds, when they come, are
  sized to damage, not volume (§8).
- **After-the-fact best-execution policing (EBBO).** It is replaced by the
  deterministic baseline as the reference, which every reader can compute
  from the pinned root (§5).

What it added, with no CoW counterpart:

- the baseline as a permanent reserve bid;
- sealed proposals;
- an on-chain challenge of the structural half of every leg;
- per-maker books with inclusion and absence proofs;
- matching by meaning in a catalogue;
- the guarantee fabric for delivery.

## 7. Questions to expect

**"Isn't this just CoW Swap for physical goods?"**
Same family, different market. CoW's coincidences of wants compete with an
AMM price on every pair, and mostly lose. loopmarket's loops compete with no
trade at all. That changes what a solver does: semantic matching and
planning over a catalogue rather than routing against pools. It changes
what must be verified: fit, place and time, not only a limit price. And it
changes what happens afterwards: delivery, deposits and arbitration.

**"Did you copy CoW's auction?"**
The idea came from elsewhere. The auction engineering is partly CoW's, on
purpose and with credit: the fairness filter is CIP-67 generalised from
token pairs to cycles. Where loopmarket departs from CoW (no autopilot, no
numeraire, no fees, open entry), the design documents say why.

**"CoW found that rings almost never pay. Why would loops?"**
CoW's rings compete with AMMs that already price every pair, so the slack
between limits is tiny: the 2026 forum study found that none of 14 feasible
mainnet rings covered its gas. A courier run, a cellar and a cider pressing
have no AMM. There, the loop's surplus is the value of a trade that
otherwise does not happen.

**"How do you score without a numeraire?"**
By the sum of the logs of each loop's surplus factor, which has no unit and
does not change when any maker rescales its own scale. A fairness filter
then compares each offer only with its own alternatives. The CoW paper
behind CIP-67 began life as *Combinatorial Auctions without a Numeraire*;
loopmarket is the extreme case, with no outside prices at all.

**"Who plays the autopilot?"**
No one. Books are kept per maker on Swarm, discovered on chain and folded
by each reader. Proposals are committed and revealed on chain, and the
winners are a deterministic function of the revealed set that anyone can
compute. The trust that remains is the contract's `arbiter` key (until
factbond adjudication replaces it), data availability and the catalogue.

**"CoW settles in seconds. You take twenty minutes and an hour's challenge
window."**
For tokens, latency is money; CoW even added fast-path orders that skip the
batch. For goods delivered over days it is not the bottleneck. Beat length
and the challenge window are parameters on Gnosis, whose blocks take about
5 seconds, and the right beat length is an open question in
P2-batch-auction.

**"What stops a solver from lying?"**
Nothing a solver says is believed. Clearing re-derives every leg from the
pinned book and catalogue. On chain, anyone can challenge a leg within the
window; the contract re-verifies its structural half against the committed
hash and pays out the bond if the leg fails. Whether the give fits the want
is a graph question over the catalogue. Every reader checks it off chain,
and on chain it belongs to the `arbiter`.

**"Does your contract check that the vegetable box fits the want, the way
CoW's checks the limit price?"**
Not on chain, yet. The contract checks presence under the pinned root,
quantities, fills and potentials exactly. Fit in the catalogue is
re-derived by every reader, and a dispute over it goes to the arbiter.
Whether an `is_below` certificate may one day replace that re-derivation
is an open question in `proof-fabric.md`.

**"Why would anyone run a solver if you pay nothing?"**
Today, makers clear their own offers (the baseline ships with `loop`), and
the baseline makes sure the obvious loops clear even if no one else solves.
Later, a solver will be paid by a spread leg in the loop it found, bounded
by the reserve bid and competed down beat by beat. There are no fees and no
rewards because rewards linked to volume pay for wash loops, and a real
loop looks exactly like one.

**"Isn't a protocol-run baseline what CoW said cannot work?"** (In the
CIP-67 thread, CoW's Felix Henneke said such approaches "seem to hinge on
the protocol being able to be a good solver as well, which will probably
not be possible".)
The baseline need not be good. It only needs to be free, deterministic and
computable by every reader from the pinned root. It sets a floor (the
reserve bid) and gives every offer a reference, and better solvers are
welcome to beat it. CoW's references need live routing against AMM state
within seconds, which only solvers can do. loopmarket's depend on no
outside state.

**"What is your EBBO?"**
There is no outside best bid to compare with: by design, no world price
exists for a personal scale. The guarantee is internal to the beat. No
offer does worse than its best standalone alternative among the beat's
proposals and the baseline's.

**"What about MEV?"**
There is no pool to sandwich, and nothing inside a beat depends on order:
the outcome is a function of the revealed set. Proposals stay sealed until
the commit phase closes. The open exposure is privacy, not ordering:
offers are public plaintext until P4.

**"What happens if the vegetables never arrive?"**
Clearing is not settlement. The giver's deposit is reserved per fill in
`LoopEscrow`. An undisputed case settles by timeout or by both parties. A
disputed one goes to the arbitrator both sides accepted, with factbond as
the escrow's resolver.

**"Could CoW's solvers solve loopmarket?"**
In principle yes. The proposal and record formats are public, and the
baseline is built against the same public interface an outside solver
would use. In practice the skills differ. CoW's solvers route against
pools with inventory; loopmarket's match by meaning, place and time and
compose transport and storage.

**"Could loopmarket use CoW?"**
Possibly, for the money legs. Money is just a thing in a loopmarket offer,
and a bridge maker that sells tokens against its scale could manage its
inventory through CoW. loopmarket itself moves tokens only as escrow
deposits.

**"How big is it?"**
It has not launched yet. The contracts are live on Gnosis, beats have been
posted and challenged live at test amounts, and a browser page reads the
market with nothing installed. CoW does about $3B a month [recheck].

## 8. Where CoW is ahead (say it first)

- **Production.** Real volume, real money, a professional solver field and
  years of mechanism changes tested in production, from a team that
  publishes its research.
- **Latency.** Seconds, against twenty minutes plus a challenge window.
- **Solver pay.** CoW's solvers get paid; loopmarket's spread leg is not
  built.
- **Atomic settlement.** CoW has no counterparty risk. loopmarket's
  delivery risk is real, its guarantee machinery runs at test amounts, and
  factbond's Phase-0 simulation has not been scored.
- **Liquidity.** CoW can always fall back on AMMs. loopmarket depends on
  thick books; the lesson of every barter network (the essay's WIR and
  Sardex) is that circles starve when the web of offers is thin.
- **Dead offers.** CoW's forum finds that most detected crossings and rings
  involve cancelled, expired or unfunded orders, and CoW can at least
  check a balance. A give of a physical thing cannot be checked that way.
  loopmarket answers with validity windows, withdrawals, deposits that the
  gate counts only if the escrow holds them, and non-performance covered by
  deposits, but nothing measures staleness yet.
- **Expressiveness for tokens.** Hooks, flash loans, TWAP and programmatic
  orders.

Where loopmarket is different by design:

- no operator anywhere in the path;
- matching by meaning, place and time, with composed legs;
- no numeraire needed;
- a deterministic baseline any reader can replay;
- delivery guarantees as part of the protocol.

## 9. Check before the talk

These turned up while comparing. None is fixed yet.

1. **A misattribution.** arXiv:2408.12225, the theory behind CIP-67, is by
   Andrea Canidio and Felix Henneke (CoW Protocol), not "Cramton et al." as
   `docs/plans/THREATS.md` (T3) and `docs/plans/P2-batch-auction.md` (§5)
   say. Its current title (v4, July 2026) is *Fair Combinatorial Auctions:
   Endogenous Best Execution in Blockchain Trade-Intent Markets*; v1
   (August 2024) was *Combinatorial Auctions without a Numeraire: The Case
   of Blockchain Trade-Intent Auctions*. CIP-67's authors are Haris
   Angelidakis, Andrea Canidio, Felix Henneke and Bram van den Berg. Any of
   them may be in the room.
2. **CIP-67's date.** P2-batch-auction §5 says it went live on 20 June 2025,
   and P2-clearing-pricing §5 says June 2025. The CIP, voted in mid-May
   2025, planned activation on all chains "around May 20th, 2025". Say
   "since mid-2025" unless the day is confirmed.
3. **CIP-72 is gone.** CoW replaced it with CIP-88 (quote rewards from
   about 10% of revenue, to the five most accurate quotes).
   P2-batch-auction §7 and `adoption-and-thickness.md` still commit in
   advance to "the CIP-72 rule".
4. **β.** CoW's 50% share now applies on Ethereum, Arbitrum, Base and BNB;
   P2-batch-auction §7 leaves out BNB.
5. **The essay's CoW paragraph** (`docs/loop-economy.md`, "Nothing here is
   untested").
   - CoW now cuts an auction about once a block, not every thirty seconds.
   - "Tens of billions of dollars" undersells it: about $187B since
     December 2023 on DefiLlama alone.
   - "Returning the discovered surplus to the traders" is less exact now
     that the protocol takes half of any improvement over the quote
     (capped at 0.98%) and 2 bps of volume.
   - Later in the essay, "an open solver competition on a token exchange
     would drive out the incumbent aggregators within two years" has no
     source in the repo. Find one or soften it.
6. **The Swarm talk's slide 19** says "The CoW Protocol shape: anyone runs
   a solver". Anyone can write one, but only bonded and allowlisted solvers
   settle, with KYC under CoW DAO's pool. BYOS is CoW's 2026 move to let
   anyone propose routes through a bonded solver.
7. **P2-batch-auction §1's "~$3.7B/mo"** is the 2024 paper's figure.
   DefiLlama has about $3.0B for the last 30 days and a peak of about $12.7B
   in August 2025.
8. **MEV Blocker** is no longer CoW's: it was sold to Consensys's Special
   Mechanisms Group in January 2026.

Still accurate:

- CoW's two slashings and their amounts;
- the bonding pool sizes;
- the 72-hour reimbursement window;
- the 24-hour average price for COW payouts;
- the 3-block deadline on Gnosis.

## 10. Sources

CoW documentation (docs.cow.fi; source github.com/cowprotocol/docs at
`4714a44`, 2026-10-28):

- Fair combinatorial auction:
  <https://docs.cow.fi/cow-protocol/concepts/introduction/fair-combinatorial-auction>
- What solving is (orders, score, uniform directional prices):
  <https://docs.cow.fi/cow-protocol/reference/core/auctions/the-problem>
- Competition rules (three layers, deadlines per chain, EBBO base
  liquidity):
  <https://docs.cow.fi/cow-protocol/reference/core/auctions/competition-rules>
- Rewards (performance, penalty caps, consistency, quotes):
  <https://docs.cow.fi/cow-protocol/reference/core/auctions/rewards>
- Accounting (weekly, 24-hour average COW price):
  <https://docs.cow.fi/cow-protocol/reference/core/auctions/accounting>
- Bonding pools:
  <https://docs.cow.fi/cow-protocol/reference/core/auctions/bonding-pools>
- EBBO violations (72 hours, slashing by CIP):
  <https://docs.cow.fi/cow-protocol/reference/core/auctions/ebbo-rules>
- Autopilot (one per chain; "doesn't verify"):
  <https://docs.cow.fi/cow-protocol/tutorials/arbitrate/autopilot>
- Orderbook:
  <https://docs.cow.fi/cow-protocol/tutorials/arbitrate/orderbook>
- Settlement contract and order struct:
  <https://docs.cow.fi/cow-protocol/reference/contracts/core/settlement>
- Allowlist:
  <https://docs.cow.fi/cow-protocol/reference/contracts/core/allowlist>
- Solver onboarding (KYC, BNB first, service fee):
  <https://docs.cow.fi/cow-protocol/tutorials/solvers/onboard>
- Fees: <https://docs.cow.fi/governance/fees>; partner fee:
  <https://docs.cow.fi/governance/fees/partner-fee>
- Fast-path orders:
  <https://docs.cow.fi/cow-protocol/concepts/order-types/fast-path-orders>
- Coincidence of wants (ring CoWs):
  <https://docs.cow.fi/cow-protocol/concepts/how-it-works/coincidence-of-wants>
- Token: <https://docs.cow.fi/governance/token>

CoW forum:

- CIP-67, with the experiments and the discussion of uniform prices:
  <https://forum.cow.fi/t/2967>
- CIP-22, the Barter solver: <https://forum.cow.fi/t/1440>; CIP-55, GlueX:
  <https://forum.cow.fi/t/2649>
- CIP-74, rewards tied to revenue and the volume fee:
  <https://forum.cow.fi/t/3234>
- Ring feasibility and zombie orders (July 2026), with a production
  solver's reply (September 2026): <https://forum.cow.fi/t/3511>
- Decentralising the auction on pod network (September 2025):
  <https://forum.cow.fi/t/3173>
- BYOS RFP (June 2026): <https://forum.cow.fi/t/3469>; the bleu grant and
  its progress: <https://forum.cow.fi/t/3476>
- Solana at 0 bps (September 2026): <https://forum.cow.fi/t/3557>
- CIP-73, the mandate to sell CoW DAO's stake in MEV Blocker:
  <https://forum.cow.fi/t/3222>

Research and other sources:

- Canidio and Henneke, arXiv:2408.12225 (v1 August 2024, v4 July 2026):
  <https://arxiv.org/abs/2408.12225>
- Zhang, *Incentives and Market Structure in Intent-Based Exchanges:
  Evidence from a Solver-Reward Reform*, arXiv:2607.21955 (CIP-74; solver
  concentration by volume rose from HHI 0.176 to 0.241), useful if solver
  monoculture comes up: <https://arxiv.org/abs/2607.21955>
- Gnosis, "Batch auctions with uniform clearing price on plasma"
  (July 2018), the ring-trade origin:
  <https://ethresear.ch/t/batch-auctions-with-uniform-clearing-price-on-plasma/2554>
- SMG acquires MEV Blocker (January 2026):
  <https://www.smg.org/memo/mevblocker>
- DefiLlama, CoW Swap volumes:
  <https://api.llama.fi/summary/aggregators/cow-swap>

loopmarket:

- this repository at 0.18.1: `ARCHITECTURE.md`; `docs/plans/P2-batch-auction.md`,
  `P2-clearing-pricing.md`, `THREATS.md` (T3) and `P3-guarantee-coupling.md`
  (§6); `src/loopmarket/auction.py`; `contracts/SealedBeat.sol` and
  `BeatClearing.sol`;
- the Gnosis contracts read on 2026-10-29: `BeatClearing`
  `0x4A35…5cF4` (bond 0.01 xDAI, window 720 blocks, `arbiter` a single
  key, no beat posted yet on this deployment) and `SealedBeat`
  `0xfC55…B5cE` (period 240 blocks, commit 120).
