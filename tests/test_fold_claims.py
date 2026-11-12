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


def test_a_hold_that_is_used_up_cannot_be_exercised_again():
    """The farmer's 15 kg of grain; hanna and karl each hold 5. In the
    window hanna takes 5 by exercising and 5 more from the free remainder,
    so the last 5 are karl's. A book holding hanna's loops adds a second
    exercise of her spent hold under her second loop: each exercise is
    within the hold and within its own leg, and together they take the hold
    twice. Admitted, hanna's hold read as minus 5, which took karl's hold
    from what is held, and a stranger's loop took the grain karl had paid
    to keep."""
    from loopmarket.clearing import LoopProposal
    from loopmarket.graph import Circulation
    from loopmarket.matching import Leg
    now, long = 10_000, dict(valid=TimeWindow(0, 20_000))
    opened, end = now + 100, now + 1_000
    grain = give("farmer", Thing(("grain",), 15, "kg", divisible=True), 150, **long, nonce=1)

    def option(nonce):
        return give("farmer", Thing(("option(grain)",), 5, "kg"), 5, **long, nonce=nonce, underlying=grain.offer_id,
                    exercise=TimeWindow(opened, end))

    def one(maker, what, price, nonce, kind=give):
        return kind(maker, Thing((what,)), price, **long, nonce=nonce)

    o = {"grain": grain, "opt_h": option(2), "opt_k": option(3),
         "f_lesson": one("farmer", "lesson", 12, 4, want), "f_pear": one("farmer", "pear", 12, 5, want),
         "f_painting": one("farmer", "painting", 60, 6, want), "f_apple": one("farmer", "apple", 60, 7, want),
         "f_car": one("farmer", "car", 60, 8, want),
         "h_opt": want("hanna", Thing(("option(grain)",), 5, "kg"), 12, **long, nonce=9),
         "h_lesson": one("hanna", "lesson", 10, 10),
         "h_grain_a": want("hanna", Thing(("grain",), 5, "kg"), 80, **long, nonce=11),
         "h_painting": one("hanna", "painting", 20, 12),
         "h_grain_b": want("hanna", Thing(("grain",), 5, "kg"), 80, **long, nonce=13),
         "h_apple": one("hanna", "apple", 20, 14),
         "k_opt": want("karl", Thing(("option(grain)",), 5, "kg"), 12, **long, nonce=15),
         "k_pear": one("karl", "pear", 10, 16),
         "x_grain": want("xavier", Thing(("grain",), 5, "kg"), 80, **long, nonce=17),
         "x_car": one("xavier", "car", 20, 18)}
    cat = _cat()
    cat.load({"grain": []})
    blobs = MemoryBytesStore()
    makers = {}
    for offer in o.values():
        makers.setdefault(offer.maker, OfferRegistry(RecordStore(blobs))).publish(offer)
    for reg in makers.values():
        reg.commit()
    honest = OfferRegistry(RecordStore(blobs))               # one clearing, to make the records as clearing writes them
    honest.publish_many(o.values())
    honest.commit()

    def loop(*pairs):
        return Circulation(tuple(Leg(o[w], (o[g],)) for g, w in pairs))

    ids = {}
    for name, circ, at in (("opt_h", loop(("opt_h", "h_opt"), ("h_lesson", "f_lesson")), now),
                           ("opt_k", loop(("opt_k", "k_opt"), ("k_pear", "f_pear")), now),
                           ("a", loop(("grain", "h_grain_a"), ("h_painting", "f_painting")), opened + 1),
                           ("b", loop(("grain", "h_grain_b"), ("h_apple", "f_apple")), opened + 1)):
        receipt = BookClearing(honest, cat, clock=lambda: at).submit(LoopProposal(circ, "", "", "s", at))
        assert receipt.accepted, (name, receipt.reason)
        ids[name] = receipt.loop_id
    assert honest.hold_left(grain.offer_id, ids["opt_h"]) == 0 and honest.hold_left(grain.offer_id, ids["opt_k"]) == 5

    def book_of(names, extra=()):
        wanted = {ids[n] for n in names}
        book = OfferRegistry(RecordStore(blobs))
        for key, rec in honest.store.items():
            named = [part for part in key.split("/") if part in ids.values()]
            if isinstance(rec, dict) and rec.get("loop") in ids.values():
                named.append(rec["loop"])
            if not key.startswith("offer/") and named and set(named) <= wanted:
                book.store.put(key, rec)
        for key, rec in extra:
            book.store.put(key, rec)
        book.store.commit()
        return book

    def folded(extra=()):
        agg = Aggregator(lambda: RecordStore(blobs), ontology=cat)
        for owner, reg in makers.items():
            agg.announce(owner, reg.store)
        agg.announce("clearing-0", book_of(["opt_k"]).store, role=CLEARING)
        agg.announce("clearing-1", book_of(["opt_h", "a", "b"], extra).store, role=CLEARING)
        manifest = agg.fold()
        return OfferRegistry(RecordStore(blobs, root=manifest.book_root)), _rejections(manifest, blobs)

    thief = LoopProposal(loop(("grain", "x_grain"), ("x_car", "f_car")), "", "", "s", opened + 2)

    def karls_grain_is_kept(book):
        """Karl's 5 kg are neither taken nor on offer to anyone else."""
        gone = book.taken(grain.offer_id) + book.available(grain.offer_id, opened + 2)
        return book.hold_left(grain.offer_id, ids["opt_k"]) == 5 and gone + 5 <= 15

    book, rejections = folded()
    assert rejections == {} and book.held(grain.offer_id, opened + 2) == 5 and karls_grain_is_kept(book)
    assert not BookClearing(book, cat, clock=lambda: opened + 2).rehearse(thief).accepted
    again = (f"exercise/{grain.offer_id}/{ids['opt_h']}/{ids['b']}", {"qty": "5"})
    book, rejections = folded([again])
    # the two exercises are each within the hold, and wrong together: both loops of that book go
    assert {f"clearing-1/loop/{ids['a']}", f"clearing-1/loop/{ids['b']}"} <= set(rejections)
    assert all("exercise" in rejections[f"clearing-1/loop/{ids[n]}"] for n in "ab")
    assert karls_grain_is_kept(book)


def test_a_hold_keeps_nothing_less_than_nothing():
    """What is held of an offer is the sum of what each hold still keeps. A
    hold whose exercises outrun it (records from a book not folded through
    the check above, a peer's say) keeps nothing, and takes nothing from
    another holder's hold."""
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    flat = give("landlord", Thing(("flat",), 10, "lease"), 100, **W, nonce=1)
    book.publish(flat)
    for loop, holder in (("aa" * 32, "h1"), ("bb" * 32, "h2")):
        book.store.put(f"option/{flat.offer_id}/{loop}", {"option": "cc" * 32, "holder": holder, "until": NOW + 10,
                                                           "qty": "5"})
    book.store.put(f"exercise/{flat.offer_id}/{'aa' * 32}/{'dd' * 32}", {"qty": "9"})
    assert book.hold_left(flat.offer_id, "aa" * 32) == -4
    assert book.held(flat.offer_id, NOW) == 5
