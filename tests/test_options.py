"""Options on plain offers, in memory (C1–C3, 2026-09-29;
`docs/plans/options-and-cover.md` §3). An option is a give by the writer of
a plain offer P — `option(...)`, a non-operator graph-kind head matching by
plain containment (C1) — naming P as its `underlying` and an `exercise`
window. Its leg clears like any other and writes a hold,
`option/<P>/<loop>`, in the same commit: while it is active P is admissible
only to the holder, who may exercise inside the window; a second option
finds no capacity; after the window P is free again, with no write; a
divisible P is held only in part (C2). The baseline never proposes a leg
on held capacity except the holder's exercise (C3)."""

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.gate import CounterpartyGate
from loopmarket.matching import check_match

NOW = 10_000
OPEN, END = NOW + 100, NOW + 1_000
LONG = dict(valid=TimeWindow(0, NOW + 10_000))
W, H, X = "landlord", "holder", "other"


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_graph_heads(["option"])
    cat.load({"apartment": [], "flat": ["apartment"], "lesson": [], "painting": [], "grain": [],
              "car": []})
    return cat


def test_an_option_matches_by_containment_of_its_argument():
    """C1: the held flat fits a want for an option on an apartment, not one
    on a car; the bare head holds nothing."""
    cat = _cat()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    p = give(W, Thing(("flat",), 1, "lease"), 100, **LONG, nonce=1)
    o = give(W, Thing(("option(flat)",), 1, "lease"), 5, **LONG, nonce=2, underlying=p.offer_id,
             exercise=TimeWindow(OPEN, END))
    book.publish_many([p, o])
    book.commit()
    gate = CounterpartyGate.over(book, {}, now=NOW)
    wants = lambda term: want(H, Thing((term,), 1, "lease"), 12, **LONG, nonce=3)
    assert check_match(o, wants("option(apartment)"), cat, now=NOW, gate=gate) is not None
    assert check_match(o, wants("option(car)"), cat, now=NOW, gate=gate) is None
    assert check_match(o, wants("option(apartment)"), cat, now=NOW) is None          # no gate, no option (U7)


class Market:
    """The landlord's flat P and its option O; the holder buys the option
    for a lesson and exercises it for a painting; another buyer wants the
    flat too."""

    def __init__(self, *, qty=1, unit="lease", held=1, step=None):
        self.book = OfferRegistry(RecordStore(MemoryBytesStore()))
        kw = {} if step is None else {"step": step}
        self.p = give(W, Thing(("flat" if unit == "lease" else "grain",), qty, unit, **kw), 100, **LONG, nonce=1)
        head = "option(flat)" if unit == "lease" else "option(grain)"
        self.o = give(W, Thing((head,), held, unit), 5, **LONG, nonce=2, underlying=self.p.offer_id,
                      exercise=TimeWindow(OPEN, END))
        wants_head = "option(apartment)" if unit == "lease" else "option(grain)"
        self.book.publish_many([
            self.p, self.o,
            want(H, Thing((wants_head,), held, unit), 12, **LONG, nonce=3),
            give(H, Thing(("lesson",), 1, "hour"), 10, **LONG, nonce=4),
            want(W, Thing(("lesson",), 1, "hour"), 12, **LONG, nonce=5)])
        self.book.commit()

    def step(self, now):
        cat = _cat()
        return SolverAgent(self.book, cat, clearing=MockClearing(self.book, cat, clock=lambda: now),
                           solver_id="t").step(now=now)

    def exercise_offers(self, qty=1, unit="lease", nonce=10, maker=H, price=150):
        thing = ("apartment",) if unit == "lease" else ("grain",)
        return [want(maker, Thing(thing, qty, unit), price, **LONG, nonce=nonce),
                give(maker, Thing(("painting",), 1, "piece"), 20, **LONG, nonce=nonce + 1),
                want(W, Thing(("painting",), 1, "piece"), 120, **LONG, nonce=nonce + 2)]


def test_the_option_clears_writes_a_hold_and_the_holder_exercises_in_the_window():
    m = Market()
    (r,) = m.step(NOW)
    assert r.accepted
    [(loop, hold)] = m.book.holds(m.p.offer_id)
    assert loop == r.loop_id and hold == {"option": m.o.offer_id, "holder": H, "until": END, "qty": "1"}
    assert m.book.available(m.p.offer_id, NOW) == 0 and m.book.held(m.p.offer_id, NOW) == 1
    # before the window the holder cannot exercise; nobody else can take the flat
    m.book.publish_many(m.exercise_offers() + m.exercise_offers(maker=X, nonce=20, price=300))
    m.book.commit()
    assert m.step(OPEN - 1) == []
    # inside the window the holder's exercise clears and the other buyer's never is proposed
    (r2,) = m.step(OPEN + 1)
    assert r2.accepted and m.book.is_filled(m.p.offer_id)
    legs = m.book.store.get(f"loop/{r2.loop_id}")["legs"]
    assert any(leg["give"] == m.p.offer_id and m.book.get(leg["want"]).maker == H for leg in legs)
    assert m.book.hold_left(m.p.offer_id, loop) == 0
    m.book.verify_loop_atomicity()


def test_a_second_option_finds_no_capacity_and_the_flat_is_free_after_expiry():
    m = Market()
    (r,) = m.step(NOW)
    assert r.accepted
    second = give(W, Thing(("option(flat)",), 1, "lease"), 5, **LONG, nonce=30, underlying=m.p.offer_id,
                  exercise=TimeWindow(OPEN, END))
    gate = CounterpartyGate.over(m.book, {}, now=NOW)
    assert gate.option_fault(second) == "no free capacity on the underlying for the hold"
    # the holder never exercises: after the window the other buyer's loop clears, with no write needed
    m.book.publish_many(m.exercise_offers(maker=X, nonce=20, price=300))
    m.book.commit()
    assert m.step(OPEN + 1) == []                                            # still held for the holder
    (r2,) = m.step(END + 1)
    assert r2.accepted and m.book.is_filled(m.p.offer_id)


def test_a_divisible_give_is_held_only_in_part():
    """200 of 1000 kg held: another buyer may take 800 meanwhile, not 801."""
    m = Market(qty=1000, unit="kg", held=200, step=1)
    (r,) = m.step(NOW)
    assert r.accepted and m.book.available(m.p.offer_id, NOW) == 800
    cat = _cat()
    gate = CounterpartyGate.over(m.book, {}, now=OPEN + 1)
    avail = m.book.availability([m.p], OPEN + 1)
    for qty, ok in ((800, True), (801, False)):
        buyer = want(X, Thing(("grain",), qty, "kg"), 900, **LONG, nonce=40 + qty)
        assert (check_match(m.p, buyer, cat, now=OPEN + 1, available=avail, gate=gate) is not None) is ok
    # the holder may take the free part and its own 200 together
    holder = want(H, Thing(("grain",), 1000, "kg"), 900, **LONG, nonce=50)
    assert check_match(m.p, holder, cat, now=OPEN + 1, available=avail, gate=gate) is not None
    assert check_match(m.p, holder, cat, now=OPEN - 1, available=m.book.availability([m.p], OPEN - 1),
                       gate=CounterpartyGate.over(m.book, {}, now=OPEN - 1)) is None   # not yet exercisable


def test_an_option_on_someone_elses_or_an_unfit_offer_clears_nowhere():
    cat = _cat()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    p = give(W, Thing(("flat",), 1, "lease"), 100, valid=TimeWindow(0, OPEN + 10), nonce=1)
    foreign = give(X, Thing(("option(flat)",), 1, "lease"), 5, **LONG, nonce=2, underlying=p.offer_id,
                   exercise=TimeWindow(OPEN, END))
    outlasting = give(W, Thing(("option(flat)",), 1, "lease"), 5, **LONG, nonce=3, underlying=p.offer_id,
                      exercise=TimeWindow(OPEN, END))
    book.publish_many([p, foreign, outlasting])
    book.commit()
    gate = CounterpartyGate.over(book, {}, now=NOW)
    assert gate.option_fault(foreign) == "option by another maker than its underlying's"
    assert gate.option_fault(outlasting) == "the underlying is not valid through the exercise window"
    book.withdraw(p.offer_id)
    book.commit()
    assert CounterpartyGate.over(book, {}, now=NOW).option_fault(outlasting) == "the underlying is withdrawn"
    with pytest.raises(ValueError, match="graph-kind"):
        _cat().declare_graph_heads(["time"])
