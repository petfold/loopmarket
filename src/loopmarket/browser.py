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

Saved searches (`SavedSearches`, docs/plans/BROWSER.md §5b) are the
person's own and never leave their computer: a small JSON file the page
opens and saves, each search a list of categories as `loop offers` takes
them, with the offers already seen so the page can mark what is new.
`MarketPage.search` answers one against the fold under the default
catalogue (ontodag's prelude, core and loop's markers, as `loop setup`
builds it), built in memory the first time a search needs it.
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

    def catalogue(self):
        """The default catalogue (`cli.setup.fill_catalogue`), built once."""
        if getattr(self, "_catalogue", None) is None:
            from ontodag import OntoDAG

            from .cli.setup import fill_catalogue
            from .ontology import Ontology
            self._catalogue = Ontology(fill_catalogue(OntoDAG()))
        return self._catalogue

    def search(self, categories: str, now: int | None = None) -> str:
        """The fold's open offers with a part that satisfies every category
        in `categories` (space separated), as `loop offers CATEGORIES`
        lists them. A category the catalogue does not know is an error,
        since it could never match (U7). Relative times are read with the
        clock, as at the `loop` command."""
        import shlex

        from ontodag import surface

        from .cli.render import _COLUMNS, _row
        now = int(time.time()) if now is None else now
        ontology = self.catalogue()
        try:
            wanted = [surface.absolute(t, ontology.dag, now) for t in shlex.split(categories)]
        except ValueError as e:
            return json.dumps({"error": str(e)})
        if not wanted:
            return json.dumps({"error": "name the categories to search for"})
        unknown = [t for t in wanted if not ontology.known(t)]
        if unknown:
            return json.dumps({"error": f"not in the catalogue: {', '.join(unknown)}"})
        if self.folded is None:
            return json.dumps({"columns": list(_COLUMNS), "rows": [], "categories": wanted})
        rows = [_row(o, now, self.folded) for o in self.folded.offers(now=now)
                if any(ontology.satisfies(p.concepts, wanted) for p in o.parts)]
        rows.sort(key=lambda r: r[0])
        return json.dumps({"columns": list(_COLUMNS), "rows": rows, "categories": wanted})

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


class SavedSearches:
    """The person's saved searches, kept in a local file (JSON), never on
    Swarm. Each has a name, its categories (as typed; relative times are
    read again at every run) and the ids of the offers already seen, so a
    run marks what is new. Every method answers JSON text with `changed`
    (unsaved changes)."""

    FORMAT = "loopmarket saved searches"

    def __init__(self, searches=None, name="searches.json"):
        self.searches = list(searches or [])
        self.name = name
        self.changed = False

    @classmethod
    def from_text(cls, text: str, name: str = "searches.json"):
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("format") != cls.FORMAT:
            raise ValueError(f"{name} is not a file of saved searches")
        searches = [{"name": str(s["name"]), "categories": str(s["categories"]),
                     "seen": [str(i) for i in s.get("seen", [])]}
                    for s in data.get("searches", [])]
        return cls(searches, name)

    def text(self) -> str:
        return json.dumps({"format": self.FORMAT, "version": 1,
                           "searches": self.searches}, indent=1) + "\n"

    def saved(self, name: str | None = None) -> str:
        if name:
            self.name = name
        self.changed = False
        return self.summary()

    def _find(self, name):
        return next((s for s in self.searches if s["name"] == name), None)

    def summary(self) -> str:
        return json.dumps({"name": self.name, "changed": self.changed,
                           "searches": [{"name": s["name"], "categories": s["categories"]}
                                        for s in self.searches]})

    def add(self, name: str, categories: str) -> str:
        name, categories = name.strip(), categories.strip()
        if not name or not categories:
            return json.dumps({"error": "a search needs a name and categories"})
        found = self._find(name)
        if found is not None:
            if found["categories"] != categories:
                found["categories"], found["seen"] = categories, []
        else:
            self.searches.append({"name": name, "categories": categories, "seen": []})
        self.changed = True
        return self.summary()

    def remove(self, name: str) -> str:
        before = len(self.searches)
        self.searches = [s for s in self.searches if s["name"] != name]
        self.changed = self.changed or len(self.searches) != before
        return self.summary()

    def run(self, market: MarketPage, now: int | None = None) -> str:
        """Every search against the fold: its offers, which of them are new."""
        results = []
        for s in self.searches:
            answer = json.loads(market.search(s["categories"], now=now))
            if "error" in answer:
                results.append({"name": s["name"], "error": answer["error"]})
                continue
            seen = set(s["seen"])
            ids = [r[0] for r in answer["rows"]]
            results.append({"name": s["name"], "categories": s["categories"],
                            "columns": answer["columns"], "rows": answer["rows"],
                            "new": [i for i in ids if i not in seen]})
        return json.dumps({"results": results, "changed": self.changed})

    def mark_seen(self, name: str, ids_json: str) -> str:
        """Count these offers (ids, as a JSON list) as seen by search `name`."""
        found = self._find(name)
        if found is None:
            return json.dumps({"error": f"no saved search named {name}"})
        new = [i for i in json.loads(ids_json) if i not in found["seen"]]
        if new:
            found["seen"].extend(new)
            self.changed = True
        return self.summary()
