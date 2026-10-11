"""loopmarket.browser, the read-only page's Python, driven through a fake of
the page's JavaScript blob store (docs/plans/BROWSER.md). The real page runs
it under Pyodide; browser/check.py runs that against a Bee node."""

import json

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import OfferRegistry, Thing, TimeWindow, give, want
from loopmarket.browser import MarketPage

NOW = 1_700_000_000
W = dict(valid=TimeWindow(NOW - 1, NOW + 30 * 86_400))


class Promise:
    def __init__(self, value):
        self.value = value


def bridge(promise):
    assert isinstance(promise, Promise), "not through the async boundary"
    return promise.value


class PageBlobs:
    """The page's BlobStore (browser/swarm.js): download, downloadMany; a
    blob it cannot produce is a rejection."""

    def __init__(self, blobs):
        self.blobs = blobs

    def download(self, ref):
        if ref not in self.blobs.blobs:
            raise RuntimeError(f"chunk {ref} is not retrievable")
        return Promise(self.blobs.blobs[ref])

    def downloadMany(self, refs):
        return Promise([self.download(r).value for r in refs])


def book(blobs, offers):
    reg = OfferRegistry(RecordStore(blobs))
    reg.publish_many(offers)
    return reg.commit()


def market():
    blobs = MemoryBytesStore()
    roots = {
        "amara": book(blobs, [give("amara", Thing(("piano-lesson",), unit="course"), 100, nonce=1, **W),
                              want("amara", Thing(("vegetable-box",), unit="course"), 104, nonce=2, **W)]),
        "bruno": book(blobs, [give("bruno", Thing(("vegetable-box",), unit="course"), 50, nonce=3, **W)]),
        # a forged offer: "amara" sells cheap, says mallory, with no signature
        "mallory": book(blobs, [give("amara", Thing(("piano-lesson",), unit="course"), 1, nonce=666, **W),
                                give("mallory", Thing(("bicycle",), unit="course"), 9, nonce=7, **W)]),
    }
    books = [{"owner": o, "book": f"swarm:{o}-book", "role": "maker", "root": r} for o, r in roots.items()]
    books.append({"owner": "clara", "book": "swarm:clearing", "role": "clearing", "root": roots["bruno"]})
    books.append({"owner": "dora", "book": "swarm:dora-book", "role": "maker", "root": None,
                  "why": "its feed has no update"})
    return MarketPage(PageBlobs(blobs), bridge=bridge), books


def test_the_page_folds_the_maker_books_and_lists_their_offers():
    page, books = market()
    folded = json.loads(page.fold(json.dumps(books)))
    by_owner = {b["owner"]: b for b in folded["books"]}
    assert [o for o, b in by_owner.items() if b["folded"]] == ["amara", "bruno", "mallory"]
    assert by_owner["amara"]["offers"] == 2
    assert "clearing book" in by_owner["clara"]["why"]
    assert by_owner["dora"]["why"] == "its feed has no update"
    rows = json.loads(page.offers(now=NOW))["rows"]
    assert sorted((r[1], r[2], r[4]) for r in rows) == [
        ("give", "amara", "piano-lesson"), ("give", "bruno", "vegetable-box"),
        ("give", "mallory", "bicycle"), ("want", "amara", "vegetable-box")]


def test_a_forged_offer_is_rejected_and_named():
    page, books = market()
    folded = json.loads(page.fold(json.dumps(books)))
    assert [(r["owner"], r["reason"]) for r in folded["rejections"]] == [
        ("mallory", "foreign maker without valid signature")]
    rows = json.loads(page.offers(now=NOW))["rows"]
    assert not any(r[2] == "amara" and r[5] == "1" for r in rows)


def test_offers_filter_by_text():
    page, books = market()
    page.fold(json.dumps(books))
    rows = json.loads(page.offers("vegetable", now=NOW))["rows"]
    assert {(r[1], r[2]) for r in rows} == {("give", "bruno"), ("want", "amara")}
    assert json.loads(page.offers(now=NOW))["columns"][:3] == ["id", "side", "maker"]


def test_an_unreachable_book_is_an_error_not_an_empty_book():
    page, books = market()
    page._source._js.blobs = MemoryBytesStore()            # every blob gone
    try:
        page.fold(json.dumps(books))
    except Exception as e:                                   # noqa: BLE001
        assert not isinstance(e, KeyError)
    else:
        raise AssertionError("a fold over unreachable books answered")
