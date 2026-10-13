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


def test_the_pages_catalogue_pins_the_root_loop_setup_stores(tmp_path):
    # Equal knowledge, equal root: the page's catalogue, committed over a
    # memory store, pins what `loop setup`'s rs: catalogue pins, so offers
    # made in the page match offers made with `loop`.
    import ontodag

    from loopmarket.cli.setup import build_catalogue
    from loopmarket.ontology import Ontology
    page = searching_market()
    spec = f"rs:{tmp_path / 'cat'}"
    root = build_catalogue(spec)
    assert page.catalogue().root == root == Ontology(ontodag.open(spec).dag).root


# The maker's book (BROWSER.md §3, §5b): offers made from lines as `loop give`
# and `loop want` make them, signed with the maker's key, published at once.

_MAKER_KEY = "11" * 32


def maker_book(catalogue=None):
    import pytest
    pytest.importorskip("coincurve")
    from loopmarket.browser import MakerBook
    from loopmarket.ontology import Ontology
    from loopmarket.sigs import maker_address
    from tests.test_cli import CATALOGUE
    catalogue = catalogue or Ontology().load(dict(CATALOGUE))
    return MakerBook(maker_address(_MAKER_KEY), catalogue, now=NOW)


def signed_publish(book, line, feed_root, blobs):
    from loopmarket.sigs import sign_offer
    prepared = json.loads(book.prepare(line))
    assert "error" not in prepared, prepared
    offer = book._pending[prepared["id"]]
    return prepared, json.loads(book.publish(prepared["id"], sign_offer(offer, _MAKER_KEY), feed_root, blobs))


def test_an_offer_is_made_signed_and_published_into_the_book():
    from loopmarket.sigs import verify_offer_sig
    book, blobs = maker_book(), MemoryBytesStore()
    prepared, answer = signed_publish(book, "give piano-lesson 30", None, blobs)
    assert "give     piano-lesson" in prepared["block"]
    assert answer["id"] == prepared["id"]
    published = OfferRegistry(RecordStore.at(answer["root"], blobs))
    offer = published.get(answer["id"])
    assert offer.maker == book.maker
    assert verify_offer_sig(offer, published.signature(answer["id"]))
    assert [r[0] for r in answer["mine"]["rows"]] == [answer["id"][:12]]


def test_a_publish_keeps_what_another_device_published():
    book, blobs = maker_book(), MemoryBytesStore()
    _p, first = signed_publish(book, "give piano-lesson 30", None, blobs)
    elsewhere = maker_book()          # the same key on another device, not told
    _p, second = signed_publish(elsewhere, "want apple 9", first["root"], blobs)
    _p, third = signed_publish(book, "give bicycle-repair 40", second["root"], blobs)
    kinds = sorted(r[4] for r in third["mine"]["rows"])
    assert kinds == ["apple", "bicycle-repair", "piano-lesson"]


def test_withdrawing_is_a_published_record_and_once():
    book, blobs = maker_book(), MemoryBytesStore()
    prepared, answer = signed_publish(book, "give piano-lesson 30", None, blobs)
    gone = json.loads(book.withdraw(prepared["id"], answer["root"], blobs))
    assert gone["withdrawn"] == prepared["id"] and gone["mine"]["rows"] == []
    assert OfferRegistry(RecordStore.at(gone["root"], blobs)).is_withdrawn(prepared["id"])
    assert "already withdrawn" in json.loads(book.withdraw(prepared["id"], gone["root"], blobs))["error"]


def test_a_signature_is_checked_by_whoever_recovers_it():
    # In the page loop's signer does not install; the page's JavaScript
    # recovers the address, and a signature that is not the maker's is
    # still refused before anything is stored.
    from loopmarket.browser import MakerBook
    from loopmarket.ontology import Ontology
    from tests.test_cli import CATALOGUE
    maker = "0x" + "33" * 20
    for recovered, published in ((maker, True), ("0x" + "44" * 20, False)):
        book = MakerBook(maker, Ontology().load(dict(CATALOGUE)), now=NOW, recover=lambda oid, sig: recovered)
        prepared = json.loads(book.prepare("give piano-lesson 30"))
        answer = json.loads(book.publish(prepared["id"], "0x" + "00" * 65, None, MemoryBytesStore()))
        assert ("root" in answer) == published, answer
        if not published:
            assert "does not recover to the offer's maker" in answer["error"]


def test_what_cannot_be_published_says_why():
    book, blobs = maker_book(), MemoryBytesStore()
    assert "unknown category" in json.loads(book.prepare("give nonsense-thing 5"))["error"]
    assert "not prepared" in json.loads(book.publish("ab" * 32, "0x00", None, blobs))["error"]
    stranger_book = MemoryBytesStore()
    reg = OfferRegistry(RecordStore(stranger_book))
    oid = reg.publish(give("0x" + "22" * 20, Thing(("piano-lesson",)), 10, nonce=1, **W))
    root = reg.commit()
    assert "not yours" in json.loads(book.withdraw(oid, root, stranger_book))["error"]


def test_an_offer_made_in_the_page_meets_one_made_with_loop():
    # Under the default catalogue both pin one root; matching refuses mixed
    # or different pins, so this is what lets page and laptop trade.
    from loopmarket.matching import check_match
    page = searching_market()
    catalogue = page.catalogue()
    book, blobs = maker_book(catalogue), MemoryBytesStore()
    prepared, _answer = signed_publish(book, "give piano-lesson 30", None, blobs)
    made_here = book.book.get(prepared["id"])
    assert made_here.ontology_root == catalogue.root != ""
    theirs = want("0x" + "22" * 20, Thing(("lesson",)), 35, nonce=2,
                  valid=TimeWindow(NOW - 1, NOW + 30 * 86_400), **catalogue.pins)
    assert check_match(made_here, theirs, catalogue, now=NOW) is not None
