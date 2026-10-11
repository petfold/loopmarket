# loopmarket in a browser

Status (2026-10-12): the read-only page (§5, step 1) is built and runs in
Freedom Browser; writing waits on Freedom #647 and the key (§3). ontodag's
`docs/plans/BROWSER.md` is the base:

- the code runs under Pyodide;
- a page reaches Swarm through four calls on chunks, with one adapter per
  client: Freedom's `window.swarm`, Weeb-3, a Bee or Ant node over HTTP, a
  gateway (its §10);
- the identity (its §11);
- access control (its §12).

This document records what is loopmarket's own.

## 1. What runs as it is

- **The core should install.** Its base dependencies are ontodag and
  recordstore, both pure Python, so loopmarket should install under Pyodide
  with micropip. Not tried yet.
- **The computation is plain Python:** matching, loops, clearing and the
  solver. Expect it to run slower than natively.
- **So is the command dispatcher,** so a console page like ontodag's
  in-browser demo could run `loop` lines.

## 2. What needs replacing

- **The catalogue.** Building the default catalogue (prelude, core, the
  handover roles) takes about a minute natively, and longer under Pyodide.
  Ship it prebuilt (a canonical `.od` file loads directly), or read the
  published core pack from Swarm lazily (ontodag BROWSER.md §4).
- **The book.** recordstore over ontodag's four-call adapter, with the
  book's head in a feed owned by the maker's key (§3), in recordstore's
  feed format, so laptops and pages read each other's books.
- **The registry.** Read the LoopBookRegistry's logs through
  `window.ethereum` (`eth_getLogs`; Freedom checks such answers against
  several RPCs) or through a public RPC. Announce and retract as
  transactions. web3.py isn't needed: the registry has two calls and two
  events to encode.
- **Chain commands** (propose, deposit, settle and the rest) take the same
  route: transactions signed by the maker's key (§3), paying gas.
- **The `sig`, `chain`, `swarm` and `evm` extras** don't install there
  (coincurve and the Python Swarm stack; ontodag BROWSER.md §1).
  Signatures come from a JavaScript secp256k1 library, or from the
  pure-Python fallback `ontodag.act` already has. That fallback is fine
  for signing but slow for checking every offer of a fold, so checking
  belongs in JavaScript.

## 3. Identity (decided A, Peter, 2026-10-11)

The maker's key is the key derived from one wallet signature, the same in
every client (ontodag BROWSER.md §11). It does three jobs:

- it owns the book's feed;
- it signs offers exactly as now: a recoverable secp256k1 signature over
  the offer id (`sigs.py`);
- it opens sealed handoffs, notices and cases, by ECDH with the same key.

loopmarket's protocol therefore doesn't change.

Consequences:

- **Announcing and retracting** are transactions from that key's address,
  so it needs a little xDAI. The wallet funds it with one transaction, as
  `loop setup` funds loop's key from the Bee wallet on a desktop.
- **In Freedom,** a page can read folds and offers now. Publishing needs
  Freedom to accept a single-owner chunk the page signed (Freedom #647).
  Writing under a Freedom identity would make the maker a different
  address, so it isn't done.
- **On the desktop,** `loop setup` makes a random key or uses the Bee
  node's key (question 35, `cli.md` §16). Being the same maker in a
  browser and on a laptop needs the laptop to derive or import the
  browser's key; how is open.

The alternative, B, was the wallet itself: one approval per feed update,
`personal_sign`-form offer signatures that loopmarket would have to accept
as a second form, and still a derived key for opening sealed records,
since no wallet does ECDH.

## 4. What a page can't do

- **Duties with deadlines happen only while the tab is open:**
  - `watch` (sealing a handoff after a fill);
  - challenging a beat within its window;
  - `finalize`;
  - claim and answer periods.

  A maker who gives, wants and checks in is fine in a browser. A clearing
  book, a challenger, or anyone with a deadline needs `loop` on a machine
  that stays on.
- **Desktop-only steps:** the terminal CLI itself, and `loop setup`'s edits
  to Bee's configuration (the withdrawal whitelist).

## 5. The first page

1. **Read-only.** Fold the books announced on the registry and show their
   offers (what `loop announced`, `offers`, `fold` and `categories` do).
   It needs no key, no postage and no request upstream, and works in
   Freedom and over a gateway.
2. **A maker page** (give, want, withdraw, announce, retract) under the §3
   key: with Weeb-3 or an HTTP node first, in Freedom once #647 is
   accepted.
3. **Sealed messages and chain duties last.**

## 5a. The read-only page, built (2026-10-12)

`browser/` (index.html, app.js, registry.js) with `loopmarket.browser`
(`MarketPage`). In the page:

- **The registry:** `registry.js` reads the LoopBookRegistry's events from
  block 48,249,000. It goes through Freedom's own chain access
  (`window.ethereum`, which checks log answers against several RPCs, with
  10 s at most for an answer), or else the public Gnosis RPC, which allows
  any origin. It keeps the latest announcement per owner, with the owner
  checksummed, since the fold compares it with offers' makers as strings.
- **Each book's newest root:** read through ontodag's `swarm.js`: the
  feed's newest index (`swarm_readFeedEntry`), then that update's
  single-owner chunk (`swarm_readSingleOwnerChunk`), whose 40 bytes are a
  timestamp and the root.
- **The fold:** `MarketPage.fold` reads each maker book through ontodag's
  `JsBytesStore` and folds it with loopmarket's own `Aggregator`, as
  `loop fold` does. Clearing books are listed but not folded, since
  re-checking their loops needs the catalogue. Without crypto in the page,
  an offer in its maker's own book enters (feed ownership authenticates
  it), and a foreign one is rejected and named.
- **The offers:** `MarketPage.offers(text)` lists the open offers as
  `loop offers` does.

`build.py` copies in ontodag's `swarm.js`, so there is one source.
Checked:

- **`check.py`:** Chromium through a stand-in for Freedom's provider
  answered from a Bee node, and through the node itself over HTTP. In both,
  the offers equal the same fold computed natively (web3 for the
  announcements, `SwarmFeedPointer` for the roots, `BeeBytesStore` for the
  books).
- **`freedom_check.cjs`:** real Freedom Browser, run from its checkout with
  the Bee node as its external node. The registry came through
  `window.ethereum`, the book through `window.swarm` (5 chunks), and the
  market was shown in 7.7 s from opening the page, with the one standing
  offer.

## 6. Open

- Which message the wallet signs: ontodag's SHARING_ON_SWARM.md S1, shared
  with ontodag.
- The desktop's key (§3).
- dappdata as the layer for the adapters, the key and the stamper (ontodag
  BROWSER.md §10.1).
- Whether the solver and the clearing run in the page at all, or only for
  small books.
