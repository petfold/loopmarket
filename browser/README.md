# loopmarket on Swarm, read-only, in the browser

The market as the books announced on Gnosis say it is: the page reads the
LoopBookRegistry's events (through Freedom Browser's chain access, or the
public RPC), each announced book's newest root through its Swarm feed, folds
the books with loopmarket's own `Aggregator` under Pyodide
(`loopmarket.browser.MarketPage`), and lists the open offers. Design:
`docs/plans/BROWSER.md` §5a.

Stable address (a feed manifest; every publish advances the feed, so it
always opens the current version): `bzz://a0e5384ab667abe869c07c97c21a8e4b9dd68332f8c0760d9db60af31672b340/`. The publisher key is
`~/.ontodag/page-feeds/loopmarket.key` on the publishing machine (never
committed); `ontodag/demo/freedom/page_feed.py` makes and moves the feed.

Names: `bzz://loopmarket.gwei/` in Freedom Browser, `https://loopmarket.gwei.domains/`
in any browser, and `http://localhost:1633/bzz/loopmarket.eth/` with a local Bee
node such as Swarm Desktop, no gateway (all resolve the feed).

Published: `bzz://ab6dbd46f29e307b70c378fb7439a9e18c445cc8c92edfdc3089a5452aea938c/`
(2026-10-12; Pyodide loaded from the shared folder `PYODIDE` in `app.js`;
through a node: `http://localhost:1633/bzz/ab6dbd46f29e307b70c378fb7439a9e18c445cc8c92edfdc3089a5452aea938c/`;
in any browser, serve `dist/` and add `?gateway=https://api.gateway.ethswarm.org`).

| file | what it is |
|---|---|
| `index.html`, `app.js` | the page: open offers (with a filter), the books announced on the registry, what the fold left out |
| `registry.js` | the registry's events, decoded in the page; the latest announcement per owner |
| `build.py` | assembles `dist/`: the page, ontodag's `demo/freedom/swarm.js` and its keccak (one source), wheels built from the recordstore, ontodag and loopmarket checkouts; `--publish --batch ID` uploads it. Pyodide comes from the shared folder on Swarm (`app.js`, `PYODIDE`), as in ontodag's page |
| `check.py` | runs `dist/` in Chromium through a stand-in for Freedom's provider (or `--url`, as a node or with `?gateway=`) and compares the offers with the same fold computed natively |
| `freedom_check.cjs` | runs the published page in real Freedom Browser from a Freedom checkout |

Run `check.py` with the checkouts on the path:
`PYTHONPATH=src:../ontodag/src python3 browser/check.py`.
