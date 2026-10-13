# loopmarket in a browser

Status (2026-10-14): the read-only page (§5, step 1) is built and runs in
Freedom Browser. The maker's half of step 2, making, publishing and
withdrawing offers under a key file through the person's own node, is
built too (§5c), and so is announcing the book, though no announcement
has been sent from the page yet. Drafts and the ledger are next;
publishing from Freedom waits on Freedom #647. ontodag's
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

The maker's key is one key, the same in every client (ontodag BROWSER.md
§11). It does three jobs:

- it owns the book's feed;
- it signs offers exactly as now: a recoverable secp256k1 signature over
  the offer id (`sigs.py`);
- it opens sealed handoffs, notices and cases, by ECDH with the same key.

loopmarket's protocol therefore doesn't change.

**For now, a key file** (ontodag's questions 37 and 38, decided 2026-10-13,
its BROWSER.md §14.3). The page writes as `loop` does:
- a random key, kept by the person in a plain file (the `bee_signer` value);
- paid with the node's batches.

Later, a wallet signature (dappdata) or Swarm ID carries that same key to
a new device. It is not replaced, so offers, the book and the registry
announcement never change maker.

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

**On iPhones** (2026-10-12) the page reads by retrying, since Pyodide
there cannot be suspended by JSPI: a fold that reaches a blob not yet
fetched stops, and the page fetches it and folds again (ontodag
BROWSER.md §15). A book absorbs record by record, so a fold needs about
one run per blob of its books.

## 5b. Local first: what may stay on this computer (Peter, 2026-10-12)

ontodag's page now keeps a store of your own in a local `.od` file, never
written to Swarm (ontodag BROWSER.md §14). For loopmarket the line falls
between what a person keeps for themselves and what the market relies on.

**Local, and better for it:**
- **Inventory and wants:** what you have, can do or need, filed under
  categories (`road-bike ⊑ bicycle`, `in(rome)`). Not an offer, but what
  offers are made from: kept private, and no retyping when you make one.
- **Saved searches:** a query over the fold, such as piano lessons in Rome
  under 30. What you are looking for is nobody's business, so these never
  go to Swarm. The page re-runs them after each fold and marks what is new.
- **Drafts and templates of offers:** clearly drafts, not offers.
- **Your own ledger:** what you offered, the loops you were in, fills,
  receipts, counterparties, anything you may need as evidence. The book
  and the chain stay authoritative; this is your copy, as a file.

**Never queued locally: what others act on.**
- **Offers.** An offer means something only from the moment it is
  published, and only while its prices, times and places still hold.
  Publishing a queued offer later is publishing a stale one.
- **Withdrawals, fills, notices, cures.** They must reach the book when
  made. Removing something from a local copy does not remove it from the
  market: whoever holds the old offer brings it back on merge. That is why
  loopmarket withdraws and retracts with published records.
- **Being reachable.** Once others match against an offer, its maker must
  be able to withdraw it and answer notices. Offline-first makes that
  worse.

A book is a mergeable store, so it *could* be edited offline and synced
later without inconsistency (the CLI already writes it locally and then
syncs). The objection is not consistency: a commitment that waits is a
bad commitment.

**The page, then:**
- drafts in the local file, labelled as drafts;
- **Publish** signs and announces now, and refuses a draft whose window
  has passed; withdraw and retract are immediate, never saved for later;
- saved searches and the ledger stay local for good.

Publishing waits on the write route (ontodag BROWSER.md §14.2) and the
identity (§3). Order: saved searches first (useful at once, purely local,
no stamps, no key), then drafts and the ledger, then Publish.

## 5c. Your offers, built (2026-10-14)

Peter asked for writing from the page, "similarly" to ontodag's Publish
(ontodag BROWSER.md §16). It works as `loop give`, `loop want` and
`loop withdraw` do:
- **The key** is a random one in a file the person keeps (§3, ontodag's
  questions 37 and 38): `0x` and 64 hex digits, the `bee_signer` value
  `loop` takes.
- **The book** is the one `loop setup` names for that key,
  `swarm:loop-<the address's first 8 hex digits>`.
- **The writer** is the page's `publish.js` (ontodag's, copied in by
  `build.py`): the node that served the page and its batches, plain
  uploads, `/stewardship`, the feed found by probing.

In the page:
- **Prepare** makes the offer from a line with loop's own code
  (`MakerBook.prepare`, `cli.entry.offer_from_line`, the book standing in
  for loop's session) and shows loop's approval block.
- **The catalogue pin:** matching refuses mixed and different pins, so
  the page builds the default catalogue (`fill_catalogue`) committed over
  a memory store. Its root then equals the one `loop setup`'s `rs:`
  catalogue has, `55b9805e…` with prelude 5 and core v13 (equal
  knowledge, equal root; measured natively, 3.7 s against 4.6 s for the
  `rs:` store). A test has an offer made by the page meet one made with
  loop's API under that pin.
- **Publish** signs the offer id with the key (`Key.signHash` in
  `publish.js`: r, s and v as 0 or 1, byte for byte what loop's signer
  writes, pinned by ontodag's test vector).
  - **Python** (`MakerBook.publish`) reads the book as its feed has it, adds
    the offer and its signature, and commits onto ontodag's `StagedBlobs`.
  - **The signature check** is the book's own, fail closed. It recovers the
    address with the page's JavaScript secp256k1 (`attach_signature(...,
    recover=)`), since loop's signer, coincurve through swarmfs, does not
    install under Pyodide.
  - **The page** then uploads the staged blobs, waits until all are
    retrievable, writes the feed update and reads it back.
- **Withdraw** goes the same way. Your open offers are listed from the
  book, and **Read my book** brings in what another device published.

Checked:
- **`tests/test_browser.py`:**
  - publishing, a second device's offer kept, withdrawal;
  - the errors;
  - a signature refused by the recovery;
  - the catalogue pin and a match under it.
- **`browser/check.py --url … --publish`,** through Swarm Desktop's node
  under a throwaway key (2026-10-14):
  - published in 17 s (feed update 0), read back natively with the right
    maker, a signature that recovers to it, and the default catalogue's
    pin;
  - withdrawn in 13 s (update 1), seen withdrawn natively;
  - the market fold still matches the native fold.

**Announce my book** (`browser/announce.js`) sends what `loop announce`
sends: an EIP-1559 transaction on Gnosis (chain 100) from the key's
address, calling `announce(string,uint8)` with the book and the maker
role. The page asks the RPC for the nonce, a gas estimate (plus a fifth)
and the fees (twice the base fee plus the tip, as web3 does), says what
the key holds against the most it can cost, and asks before it signs.
The transaction is RLP-encoded and signed in the page with the key file
(`Key.signHash`), then sent, and the page waits for its receipt.

- **`tests/test_page_js.py`** runs `browser/test/test_announce.mjs`: the
  call data and the signed transaction equal, byte for byte, what
  eth_account makes from the same key and fields
  (`make_announce_vector.py`).
- **`browser/check.py --publish`** presses Announce with the throwaway
  key, which holds nothing, and expects the page to stop there with the
  balance and the fee. On 2026-10-14 Gnosis asked 9 wei base fee and a
  1 wei tip, so the fee was about a millionth of a millionth of an xDAI.

Not yet:
- **Announcing live:** no transaction has been sent from the page; that
  needs a funded key and Peter's word. Retracting from the page is not
  built (`loop retract` does it).
- **Drafts and the ledger** (§5b).
- **Freedom** (#647); **retry mode** is wired (`needing`) but not checked
  through a node.

## 6. Open

- Which message the wallet signs: ontodag's SHARING_ON_SWARM.md S1, shared
  with ontodag.
- The desktop's key (§3).
- dappdata as the layer for the adapters, the key and the stamper (ontodag
  BROWSER.md §10.1).
- Whether the solver and the clearing run in the page at all, or only for
  small books.
