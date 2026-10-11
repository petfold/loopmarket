# loopmarket on Swarm, read-only, in the browser

The market as the books announced on Gnosis say it is: the page reads the
LoopBookRegistry's events (through Freedom Browser's chain access, or the
public RPC), each announced book's newest root through its Swarm feed, folds
the books with loopmarket's own `Aggregator` under Pyodide
(`loopmarket.browser.MarketPage`), and lists the open offers. Design:
`docs/plans/BROWSER.md` §5a.

Published: `bzz://b25a77e389e8b0d08a33553cc55feb04ca17be0bb14d5b72b7c927f80ce5bd13/`
(open it in Freedom Browser; through a node:
`http://localhost:1633/bzz/b25a77e389e8b0d08a33553cc55feb04ca17be0bb14d5b72b7c927f80ce5bd13/`;
in any browser, serve `dist/` and add `?gateway=https://api.gateway.ethswarm.org`).

| file | what it is |
|---|---|
| `index.html`, `app.js` | the page: open offers (with a filter), the books announced on the registry, what the fold left out |
| `registry.js` | the registry's events, decoded in the page; the latest announcement per owner |
| `build.py` | assembles `dist/`: the page, ontodag's `demo/freedom/swarm.js` and its keccak (one source), Pyodide's core, wheels built from the recordstore, ontodag and loopmarket checkouts; `--publish --batch ID` uploads it |
| `check.py` | runs `dist/` in Chromium through a stand-in for Freedom's provider (or `--url`, as a node or with `?gateway=`) and compares the offers with the same fold computed natively |
| `freedom_check.cjs` | runs the published page in real Freedom Browser from a Freedom checkout |

Run `check.py` with the checkouts on the path:
`PYTHONPATH=src:../ontodag/src python3 browser/check.py`.
