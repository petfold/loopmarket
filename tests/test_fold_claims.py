"""What a clearing book may say beside its loops. Anyone may announce a
clearing book, so the fold re-checks every loop it holds and takes its
fills and holds only if they are the ones clearing that loop writes
(review item 9). The same holds for the other two records a clearing
writes under a loop: an item claim (`item/<h>/<maker>/<loop>`) and an
exercise (`exercise/<offer>/<option loop>/<loop>`). One that clearing the
loop would not have written rejects the loop: admitted on the loop's id
alone, a claim planted for another maker kept that maker's item from
clearing for every reader, and a record that was no record at all stopped
their solvers."""

from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import Aggregator, BookClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.federation import CLEARING
from loopmarket.items import term, vin_id

NOW = 1_700_000_000
OPEN, END = NOW + 100, NOW + 1_000
W = dict(valid=TimeWindow(NOW - 1, NOW + 30 * 86_400))
H = vin_id("1HGCM82633A004352")


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_item_heads()
    cat.declare_graph_heads(["option"])
    cat.load({"car": [], "lesson": [], "apple": [], "pear": [], "apartment": [], "flat": ["apartment"],
              "painting": []})
    return cat


CAT = _cat()


def _book(blobs, offers):
    reg = OfferRegistry(RecordStore(blobs))
    reg.publish_many(offers)
    reg.commit()
    return reg


def _fold(blobs, books, clearing=None):
    agg = Aggregator(lambda: RecordStore(blobs), ontology=CAT)
    for owner, reg in books.items():
        agg.announce(owner, reg.store)
    if clearing is not None:
        agg.announce("clearing-0", clearing.store, role=CLEARING)
    return agg.fold()


def _rejections(manifest, blobs):
    return {k[len("reject/"):]: v["reason"]
            for k, v in RecordStore.at(manifest.provenance_root, blobs).items("reject/")}


def _step(blobs, root, now):
    """A writable book at `root`, and what one solver step clears in it."""
    reg = OfferRegistry(RecordStore(blobs, root=root))
    receipts = SolverAgent(reg, CAT, clearing=BookClearing(reg, CAT, clock=lambda: now), solver_id="s").step(now=now)
    return reg, receipts


def _car_market(blobs):
    """The seller's car, an item, and its buyer; and two makers who trade
    fruit between themselves."""
    car = give("seller", Thing(("car", term(H)), 1, "car"), 50, nonce=1, **W)
    return car, {
        "seller": _book(blobs, [car, want("seller", Thing(("lesson",), 1, "hour"), 80, nonce=2, **W)]),
        "buyer": _book(blobs, [want("buyer", Thing(("car", term(H)), 1, "car"), 100, nonce=3, **W),
                               give("buyer", Thing(("lesson",), 1, "hour"), 5, nonce=4, **W)]),
        "mal1": _book(blobs, [give("mal1", Thing(("apple",), 1, "kg"), 10, nonce=5, **W),
                              want("mal1", Thing(("pear",), 1, "kg"), 12, nonce=6, **W)]),
        "mal2": _book(blobs, [give("mal2", Thing(("pear",), 1, "kg"), 10, nonce=7, **W),
                              want("mal2", Thing(("apple",), 1, "kg"), 12, nonce=8, **W)]),
    }


def _fruit_loop(blobs, books):
    """A clearing book holding the one loop of the two fruit makers."""
    reg, (receipt,) = _step(blobs, _fold(blobs, {k: books[k] for k in ("mal1", "mal2")}).book_root, NOW)
    assert receipt.accepted
    return reg, receipt.loop_id


def test_an_honest_clearing_books_item_claim_is_admitted():
    blobs = MemoryBytesStore()
    car, books = _car_market(blobs)
    clearing, receipts = _step(blobs, _fold(blobs, books).book_root, NOW)
    assert [r.accepted for r in receipts] == [True, True]
    manifest = _fold(blobs, books, clearing)
    assert _rejections(manifest, blobs) == {}
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    [(_loop, claim)] = folded.item_claims(H, "seller")
    assert claim == {"offer": car.offer_id, "until": NOW + 30 * 86_400}
    assert list(folded.offers(now=NOW)) == []


def test_an_item_claim_clearing_did_not_write_rejects_its_loop():
    """The two fruit makers' loop is valid, and their clearing book adds a
    claim on the seller's car under that loop's id. The loop is rejected
    with its records, and the seller's car clears for a reader as before."""
    blobs = MemoryBytesStore()
    car, books = _car_market(blobs)
    clearing, loop = _fruit_loop(blobs, books)
    clearing.store.put(f"item/{H}/seller/{loop}", {"offer": "00" * 32, "until": 2 ** 62})
    clearing.commit()
    manifest = _fold(blobs, books, clearing)
    reasons = _rejections(manifest, blobs)
    assert list(reasons) == [f"clearing-0/loop/{loop}"] and "item claims" in reasons[f"clearing-0/loop/{loop}"]
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    assert folded.item_claims(H, "seller") == [] and not folded.item_claimed(H, "seller", NOW, offer_id=car.offer_id)
    reader, receipts = _step(blobs, manifest.book_root, NOW)
    assert [r.accepted for r in receipts] == [True, True] and reader.is_filled(car.offer_id)


def test_an_item_record_that_is_no_record_rejects_its_loop_and_stops_no_reader():
    blobs = MemoryBytesStore()
    car, books = _car_market(blobs)
    for hostile in ("not a record", 7, None, {"offer": car.offer_id}, {"offer": car.offer_id, "until": "soon"},
                    {"offer": car.offer_id, "until": True}, {"offer": car.offer_id, "until": -1},
                    {"offer": car.offer_id, "until": 2 ** 70}):
        clearing, loop = _fruit_loop(blobs, books)
        clearing.store.put(f"item/{H}/seller/{loop}", hostile)
        clearing.commit()
        manifest = _fold(blobs, books, clearing)
        assert list(_rejections(manifest, blobs)) == [f"clearing-0/loop/{loop}"], hostile
        reader, receipts = _step(blobs, manifest.book_root, NOW)         # the solver runs, and the car clears
        assert reader.is_filled(car.offer_id), hostile


def test_a_claim_for_the_loops_own_give_must_be_the_one_clearing_writes():
    """The seller's car did clear in this book, so a claim on it belongs
    there: with the offer that gave it and the end clearing set, and no
    other."""
    blobs = MemoryBytesStore()
    car, books = _car_market(blobs)
    base = _fold(blobs, books).book_root
    for forged in ({"offer": "00" * 32, "until": NOW + 30 * 86_400},           # another offer of the seller's
                   {"offer": car.offer_id, "until": 2 ** 62},                   # held for ever
                   {"offer": car.offer_id, "until": NOW + 30 * 86_400, "extra": 1}):
        clearing, receipts = _step(blobs, base, NOW)
        loop = next(r.loop_id for r in receipts if clearing.store.contains(f"item/{H}/seller/{r.loop_id}"))
        clearing.store.put(f"item/{H}/seller/{loop}", forged)
        clearing.commit()
        reasons = _rejections(_fold(blobs, books, clearing), blobs)
        assert list(reasons) == [f"clearing-0/loop/{loop}"] and "item claims" in reasons[f"clearing-0/loop/{loop}"], forged
    # and one the loop wrote for nobody: the buyer gave no item
    clearing, receipts = _step(blobs, base, NOW)
    loop = next(r.loop_id for r in receipts if clearing.store.contains(f"item/{H}/seller/{r.loop_id}"))
    clearing.store.put(f"item/{H}/buyer/{loop}", {"offer": car.offer_id, "until": NOW + 30 * 86_400})
    clearing.commit()
    assert list(_rejections(_fold(blobs, books, clearing), blobs)) == [f"clearing-0/loop/{loop}"]


def _flat_market(blobs):
    """The landlord's flat and an option on it; the holder buys the option
    for a lesson, and later exercises it for a painting."""
    flat = give("landlord", Thing(("flat",), 1, "lease"), 100, nonce=1, **W)
    option = give("landlord", Thing(("option(flat)",), 1, "lease"), 5, nonce=2, underlying=flat.offer_id,
                  exercise=TimeWindow(OPEN, END), **W)
    landlord = [flat, option, want("landlord", Thing(("lesson",), 1, "hour"), 12, nonce=5, **W)]
    holder = [want("holder", Thing(("option(apartment)",), 1, "lease"), 12, nonce=3, **W),
              give("holder", Thing(("lesson",), 1, "hour"), 10, nonce=4, **W)]
    later = {"landlord": [want("landlord", Thing(("painting",), 1, "piece"), 120, nonce=12, **W)],
             "holder": [want("holder", Thing(("apartment",), 1, "lease"), 150, nonce=10, **W),
                        give("holder", Thing(("painting",), 1, "piece"), 20, nonce=11, **W)]}
    return flat, {"landlord": _book(blobs, landlord), "holder": _book(blobs, holder)}, later


def _exercised(blobs):
    """The makers' books and a clearing book in which the option cleared
    and the holder then exercised it: (flat, books, clearing, the option's
    loop, the exercise's loop)."""
    flat, books, later = _flat_market(blobs)
    first, (r1,) = _step(blobs, _fold(blobs, books).book_root, NOW)
    assert r1.accepted and first.holds(flat.offer_id)
    for owner, offers in later.items():
        books[owner].publish_many(offers)
        books[owner].commit()
    clearing, (r2,) = _step(blobs, _fold(blobs, books, first).book_root, OPEN + 1)
    assert r2.accepted and clearing.hold_left(flat.offer_id, r1.loop_id) == 0
    return flat, books, clearing, r1.loop_id, r2.loop_id


def test_an_honest_exercise_is_admitted():
    blobs = MemoryBytesStore()
    flat, books, clearing, option_loop, exercise_loop = _exercised(blobs)
    manifest = _fold(blobs, books, clearing)
    assert _rejections(manifest, blobs) == {}
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    assert folded.store.get(f"exercise/{flat.offer_id}/{option_loop}/{exercise_loop}") == {"qty": "1"}
    assert folded.hold_left(flat.offer_id, option_loop) == 0 and folded.is_filled(flat.offer_id)


def test_an_exercise_clearing_did_not_write_rejects_its_loop():
    """An exercise takes from a hold: more than the leg took, less than
    nothing, of a hold that is another's, or of an offer the loop never
    gave, it is not the record clearing wrote."""
    blobs = MemoryBytesStore()
    for forge in ("more", "negative", "unreadable", "another offer", "no record"):
        flat, books, clearing, option_loop, exercise_loop = _exercised(blobs)
        key = f"exercise/{flat.offer_id}/{option_loop}/{exercise_loop}"
        if forge == "more":
            clearing.store.put(key, {"qty": "5"})
        elif forge == "negative":
            clearing.store.put(key, {"qty": "-3"})
        elif forge == "unreadable":
            clearing.store.put(key, {"qty": "1/0"})
        elif forge == "no record":
            clearing.store.put(key, "all of it")
        else:
            clearing.store.put(f"exercise/{'00' * 32}/{option_loop}/{exercise_loop}", {"qty": "1"})
        clearing.commit()
        reasons = _rejections(_fold(blobs, books, clearing), blobs)
        assert f"clearing-0/loop/{exercise_loop}" in reasons, forge
        assert "exercise" in reasons[f"clearing-0/loop/{exercise_loop}"], forge
        assert f"clearing-0/loop/{option_loop}" not in reasons, forge       # the option's own loop stands
