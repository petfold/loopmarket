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


# Saved searches (BROWSER.md §5b): the person's own, in a local file.

_CATALOGUE = []


def searching_market():
    """The market, folded, with the default catalogue built once per run."""
    page, books = market()
    page.fold(json.dumps(books))
    if not _CATALOGUE:
        _CATALOGUE.append(page.catalogue())
    page._catalogue = _CATALOGUE[0]
    return page


def test_the_page_builds_the_catalogue_loop_setup_stores(tmp_path):
    import ontodag
    from ontodag import native

    from loopmarket.cli.setup import build_catalogue
    page = searching_market()
    spec = f"rs:{tmp_path / 'cat'}"
    build_catalogue(spec)
    assert native.dumps(page.catalogue().dag) == native.dumps(ontodag.open(spec).dag)


def test_a_search_is_loop_offers_with_categories():
    page = searching_market()
    rows = json.loads(page.search("lesson", now=NOW))["rows"]
    assert [(r[1], r[2], r[4]) for r in rows] == [("give", "amara", "piano-lesson")]
    assert json.loads(page.search("vehicle", now=NOW))["rows"][0][4] == "bicycle"


def test_a_category_the_catalogue_does_not_know_is_an_error():
    page = searching_market()
    assert "not in the catalogue: durian-pastry" in json.loads(
        page.search("lesson durian-pastry", now=NOW))["error"]
    assert "error" in json.loads(page.search("  ", now=NOW))


def test_saved_searches_mark_what_is_new_until_seen():
    from loopmarket.browser import SavedSearches
    page = searching_market()
    saved = SavedSearches(name="mine.json")
    saved.add("lessons", "lesson")
    saved.add("rides", "vehicle")
    saved.add("nonsense", "durian-pastry")
    results = {r["name"]: r for r in json.loads(saved.run(page, now=NOW))["results"]}
    assert len(results["lessons"]["new"]) == 1
    assert len(results["rides"]["new"]) == 1           # mallory's bicycle
    assert "not in the catalogue" in results["nonsense"]["error"]
    saved.mark_seen("rides", json.dumps(results["rides"]["new"]))
    again = {r["name"]: r for r in json.loads(saved.run(page, now=NOW))["results"]}
    assert again["rides"]["new"] == [] and len(again["rides"]["rows"]) == 1
    assert len(again["lessons"]["new"]) == 1
    saved.add("rides", "vehicle geo(41.8..42,12.4..12.6)")   # changed: seen again from scratch
    assert saved.searches[1]["seen"] == []


def test_saved_searches_round_trip_their_file_and_refuse_another():
    import pytest

    from loopmarket.browser import SavedSearches
    saved = SavedSearches()
    saved.add("lessons", "lesson")
    saved.mark_seen("lessons", json.dumps(["abc123"]))
    assert json.loads(saved.summary())["changed"]
    text = saved.text()
    assert not json.loads(saved.saved("mine.json"))["changed"]
    again = SavedSearches.from_text(text, "mine.json")
    assert again.searches == saved.searches and again.text() == text
    with pytest.raises(ValueError, match="not a file of saved searches"):
        SavedSearches.from_text('{"format": "something else"}', "other.json")
    saved.remove("lessons")
    assert json.loads(saved.summary())["searches"] == []


# Retry mode (ontodag BROWSER.md §15): where Python cannot wait on Swarm
# (Pyodide on iOS), the page fetches what a fold needed and folds again.

class RetryBlobs:
    """The page's BlobStore in retry mode: `cached` answers from what was
    fetched, `fetch` is the page's await between runs."""

    def __init__(self, blobs):
        self.blobs = blobs.blobs
        self.held = {}

    def cached(self, ref):
        return self.held.get(str(ref))

    def fetch(self, refs):
        for r in refs:
            self.held[r] = self.blobs[r]


def test_a_fold_by_retrying_equals_the_waiting_fold():
    from ontodag.browser import RETRY, NeedBlobs
    waiting, books = market()
    want = json.loads(waiting.fold(json.dumps(books)))
    js = RetryBlobs(waiting._source._js.blobs)
    page = MarketPage(js, bridge=RETRY)
    for runs in range(1, len(js.blobs) + 2):
        try:
            got = json.loads(page.fold(json.dumps(books)))
            break
        except NeedBlobs as need:
            js.fetch(need.refs)
    else:
        raise AssertionError("the fold kept needing blobs")
    assert got == want
    assert json.loads(page.offers(now=NOW)) == json.loads(waiting.offers(now=NOW))
    assert runs <= len(js.held) + 1
