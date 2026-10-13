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
        """The default catalogue (`cli.setup.fill_catalogue`), built once and
        committed over a memory store, so its root is the one `loop setup`'s
        `rs:` catalogue has (equal knowledge, equal root): offers made here
        pin it and match offers made with `loop`."""
        if getattr(self, "_catalogue", None) is None:
            from recordstore import MemoryBytesStore, RecordStore

            from .cli.setup import fill_catalogue
            from .ontology import Ontology
            ontology = Ontology.persistent(RecordStore(MemoryBytesStore()))
            fill_catalogue(ontology.dag)
            ontology.dag.commit()
            self._catalogue = ontology
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


class MakerBook:
    """Your book as a maker, in the page (docs/plans/BROWSER.md §3, §5b).

    An offer is made from a line exactly as `loop give` and `loop want`
    make it (`prepare`, through `cli.entry.offer_from_line`, with this
    object standing in for loop's session: maker, now, catalogue, book). The
    page shows the approval block, signs the offer id with the maker's key
    (in JavaScript) and `publish`es it at once: into the book as its feed
    has it, read first, so what another device or `loop` published stays,
    committed onto `blobs` (ontodag's `StagedBlobs`) for the page to upload
    before it moves the feed. `withdraw` goes the same way. Nothing is
    queued: an offer means something only from when it is published.

    The book is the one `loop setup` names for this key,
    `swarm:loop-<the address's first 8 hex digits>` (`topic`). Every answer
    is JSON text. `recover(offer_id, signature)`, the address a signature
    recovers to, checks each signature before it is stored (fail closed):
    loop's own by default, the page's JavaScript secp256k1 in the page,
    where loop's signer does not install."""

    def __init__(self, maker: str, catalogue, now: int | None = None, recover=None):
        from recordstore import MemoryBytesStore, RecordStore

        from .registry import OfferRegistry
        self.maker = maker
        self.catalogue = catalogue
        self._now = now
        self._recover = recover
        self.book = OfferRegistry(RecordStore(MemoryBytesStore()))
        self._pending = {}

    @property
    def now(self) -> int:
        return int(time.time()) if self._now is None else self._now

    def view(self):
        """What names resolve against, as loop's session's `view()`: here
        the catalogue alone (the page keeps no personal layer)."""
        return self.catalogue.dag

    @property
    def topic(self) -> str:
        return f"loop-{self.maker[2:10].lower()}"

    def _read(self, feed_root, blobs):
        from recordstore import RecordStore

        from .registry import OfferRegistry
        return OfferRegistry(RecordStore(blobs, root=feed_root) if feed_root else RecordStore(blobs))

    def _mine(self, book, now):
        from .cli.render import _COLUMNS, _row
        rows = [_row(o, now, book) for o in book.offers(now=now) if o.maker == self.maker]
        rows.sort(key=lambda r: r[0])
        return {"columns": list(_COLUMNS), "rows": rows}

    def prepare(self, line: str) -> str:
        """The offer a line makes, not yet published: its id (what the page
        signs) and the approval block `loop` prints."""
        from .cli.entry import offer_from_line
        from .cli.render import render_offer
        try:
            offer = offer_from_line(line, self)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        if offer.maker != self.maker:
            return json.dumps({"error": f"the offer's maker is {offer.maker}, not {self.maker}"})
        self._pending[offer.offer_id] = offer
        return json.dumps({"id": offer.offer_id, "kind": offer.kind, "block": render_offer(offer)})

    def publish(self, offer_id: str, signature: str, feed_root: str | None, blobs) -> str:
        """Publish a prepared offer with the maker's signature over its id:
        into the book the feed holds (`feed_root`, or a new book), committed
        onto `blobs`. The root to point the feed at, and the maker's offers."""
        offer = self._pending.get(offer_id)
        if offer is None:
            return json.dumps({"error": "that offer was not prepared here; prepare it again"})
        book = self._read(feed_root, blobs)
        oid = book.publish(offer)
        try:
            book.attach_signature(oid, signature, recover=self._recover)
        except ValueError as e:
            return json.dumps({"error": f"not published: {e}"})
        root = book.commit()
        self.book = book
        self._pending.pop(offer_id, None)
        return json.dumps({"root": root, "id": oid, "mine": self._mine(book, self.now)})

    def withdraw(self, offer_id: str, feed_root: str | None, blobs) -> str:
        """Withdraw one of the maker's open offers, in the book the feed
        holds: a published record, so whoever folds the book sees it."""
        book = self._read(feed_root, blobs)
        try:
            offer = book.get(offer_id)
        except KeyError:
            return json.dumps({"error": f"{offer_id[:12]} is not in this book"})
        if offer.maker != self.maker:
            return json.dumps({"error": f"{offer_id[:12]} is {offer.maker}'s, not yours"})
        if book.is_filled(offer_id):
            return json.dumps({"error": f"{offer_id[:12]} is filled: a cleared leg is an obligation"})
        if book.is_withdrawn(offer_id):
            return json.dumps({"error": f"{offer_id[:12]} is already withdrawn"})
        book.withdraw(offer_id)
        root = book.commit()
        self.book = book
        return json.dumps({"root": root, "withdrawn": offer_id, "mine": self._mine(book, self.now)})

    def fetch(self, feed_root: str | None, blobs) -> str:
        """The book as its feed holds it: the maker's open offers, and what
        the next offer's nonce and price memory read."""
        self.book = self._read(feed_root, blobs)
        return json.dumps({"root": feed_root, "mine": self._mine(self.book, self.now)})
