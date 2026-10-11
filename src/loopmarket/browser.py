"""loopmarket in a browser: what the read-only page asks (docs/plans/BROWSER.md).

The page (`browser/` in this repository) runs under Pyodide. Its JavaScript
finds the books announced on the registry on Gnosis and each book's newest
root (through Freedom Browser's `window.swarm`, or a Swarm node over HTTP),
and hands them here; this module folds them with loopmarket's own
`Aggregator`, as `loop fold` does, and answers as JSON text, so nothing but
strings crosses into JavaScript. Blobs are read through ontodag's
`JsBytesStore`, so a chunk the page could not fetch, or one that did not
match its address, is an error and never an empty book.

Read-only: clearing books are not folded here, since re-checking their
loops needs the catalogue the page does not load; the page says which.
"""

from __future__ import annotations

import json
import time

from .federation import MAKER, Aggregator
from .registry import OfferRegistry


class MarketPage:
    """The market as the page shows it: `fold(books)` then `offers(text)`.

    `js_store` is the page's blob store (`download`, `downloadMany`);
    `bridge` defaults to Pyodide's `run_sync` (JSPI)."""

    def __init__(self, js_store, bridge=None):
        from ontodag.browser import JsBytesStore
        if bridge is None:
            from pyodide.ffi import run_sync        # type: ignore
            bridge = run_sync
        self._source = JsBytesStore(js_store, bridge)
        self.folded = None

    def fold(self, books_json: str) -> str:
        """`books_json` lists `{owner, book, role, root}` (root null for a
        book whose feed the page could not read). Each maker book is read as
        its announced owner's and folded; the answer lists every book with
        `folded`, how many offers it holds, and why one was left out, plus
        what the fold rejected."""
        from recordstore import MemoryBytesStore, RecordStore
        books = json.loads(books_json)
        blobs = MemoryBytesStore()
        agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="loop-page")
        for b in books:
            b["folded"] = False
            if b.get("role") != MAKER:
                b["why"] = "a clearing book: its loops are re-checked by `loop fold`, not here"
                continue
            if not b.get("root"):
                b["why"] = b.get("why") or "its feed could not be read"
                continue
            source = OfferRegistry(RecordStore.at(b["root"], self._source))
            staged = OfferRegistry(RecordStore(blobs))
            staged.absorb(source)
            staged.commit()
            agg.announce(b["owner"], staged.store, role=MAKER)
            b["folded"] = True
            b["offers"] = sum(1 for _ in source.offers(include_filled=True))
        manifest = agg.fold()
        self.folded = (OfferRegistry(RecordStore.at(manifest.book_root, blobs))
                       if manifest.book_root else None)
        rejections = []
        if manifest.provenance_root:
            provenance = RecordStore.at(manifest.provenance_root, blobs)
            rejections = [{"owner": rec.get("owner", ""),
                           "key": key[len("reject/"):].partition("/")[2],
                           "reason": rec.get("reason", "")}
                          for key, rec in provenance.items("reject/")]
        return json.dumps({"books": books, "book_root": manifest.book_root,
                           "rejections": rejections})

    def offers(self, text: str = "", now: int | None = None) -> str:
        """The fold's open offers, as `loop offers` lists them (id, side,
        maker, qty, thing, price, state), those whose row mentions `text`."""
        from .cli.render import _COLUMNS, _row
        if self.folded is None:
            return json.dumps({"columns": list(_COLUMNS), "rows": []})
        now = int(time.time()) if now is None else now
        rows = [_row(o, now, self.folded) for o in self.folded.offers(now=now)]
        text = text.strip().lower()
        if text:
            rows = [r for r in rows if any(text in str(v).lower() for v in r)]
        rows.sort(key=lambda r: r[0])
        return json.dumps({"columns": list(_COLUMNS), "rows": rows})
