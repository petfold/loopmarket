"""The reads a check takes beyond the offers and the catalogue: one `Reads`
object, or the five keyword parameters it replaced, which outside solvers
still pass. Both spellings must mean the same reads, everywhere they are
taken: the exact checks, the solver, the clearing."""

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import BookClearing, OfferRegistry, Reads, SolverAgent, Thing, give, want
from loopmarket.matching import aggregate_legs, check_aggregate, check_match, meets
from loopmarket.reads import NO_READS, reads_of
from loopmarket.schema import Requires
from test_v5_record import EUR, NOW, V, _cat, _deposit


def _bonded():
    amara = want("amara", Thing(("transport",), 1, "run"), 50, **V,
                 requires=Requires(point=50, accepts=(EUR,)))
    rich = give("d1", Thing(("transport",), 1, "run"), 45, **V, bond=_deposit(("stablecoin-eur",), 60, "EUR", 45))
    return amara, rich


def test_a_read_passed_as_a_keyword_or_in_reads_is_the_same_read():
    cat = _cat()
    amara, rich = _bonded()
    for held, meets_it in (({}, False), ({rich.offer_id: 40}, False), ({rich.offer_id: 60}, True)):
        by_keyword = check_match(rich, amara, cat, now=NOW, held=held)
        by_reads = check_match(rich, amara, cat, now=NOW, reads=Reads(held=held))
        assert (by_keyword is not None) is (by_reads is not None) is meets_it
        assert meets(amara, rich, cat, taken=1, whole=1, held=held) is \
            meets(amara, rich, cat, taken=1, whole=1, reads=Reads(held=held)) is meets_it
    halves = [give(f"f{i}", Thing(("apple",), 2, step=1), 20, **V, bond=_deposit(("stablecoin-eur",), 4, "EUR", 4))
              for i in (1, 2)]
    wants4 = want("amara", Thing(("apple",), 4), 50, **V, requires=Requires(point=2, accepts=(EUR,)))
    funded = Reads(held={g.offer_id: 4 for g in halves})
    assert check_aggregate(wants4, halves, (2, 2), cat, now=NOW, reads=funded) is not None
    assert check_aggregate(wants4, halves, (2, 2), cat, now=NOW, reads=Reads(held={})) is None
    assert list(aggregate_legs([wants4, *halves], cat, now=NOW, reads=funded))


def test_a_read_given_twice_is_refused_unless_it_is_the_same_object():
    held = {"x": 1}
    assert reads_of(None) is NO_READS and reads_of(Reads(held=held)).held is held
    assert reads_of(Reads(held=held), held=held).held is held
    with pytest.raises(TypeError, match="held given twice"):
        reads_of(Reads(held=held), held={"x": 1})
    cat = _cat()
    amara, rich = _bonded()
    with pytest.raises(TypeError):
        check_match(rich, amara, cat, now=NOW, held={}, reads=Reads(held={rich.offer_id: 60}))


def _market(held_qty):
    cat = _cat()
    amara, rich = _bonded()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many([amara, rich, want("d1", Thing(("apple",), 1), 46, **V),
                       give("amara", Thing(("apple",), 1), 28, **V)])
    book.commit()
    return cat, book, (lambda oid: held_qty if oid == rich.offer_id else 0)


def test_a_solver_and_a_clearing_take_their_authorities_by_either_spelling():
    """The escrow's holdings given as `escrow_held=` or in `reads=` clear
    the same loop, or refuse it the same way; the older attributes still
    answer."""
    for held_qty, accepted in ((60, True), (0, False)):
        outcomes = []
        for spelling in ("keywords", "reads"):
            cat, book, escrow_held = _market(held_qty)
            if spelling == "keywords":
                clearing = BookClearing(book, cat, clock=lambda: NOW, escrow_held=escrow_held)
                agent = SolverAgent(registry=book, ontology=cat, clearing=clearing, solver_id="t",
                                    escrow_held=escrow_held)
            else:
                reads = Reads(escrow_held=escrow_held)
                clearing = BookClearing(book, cat, clock=lambda: NOW, reads=reads)
                agent = SolverAgent(registry=book, ontology=cat, clearing=clearing, solver_id="t", reads=reads)
            assert clearing.escrow_held is escrow_held and clearing.chain_fills is None
            assert agent.escrow_held is escrow_held and agent.reads.escrow_held is escrow_held
            receipts = agent.step(now=NOW)
            outcomes.append(bool(receipts and receipts[0].accepted))
        assert outcomes == [accepted, accepted]


def test_a_solver_and_a_clearing_derive_the_per_pass_reads_themselves():
    """`available`, `held` and the gate are what each pass derives from its
    snapshot: given at construction they would be silently replaced, so
    they are refused."""
    cat, book, _ = _market(60)
    for given in (Reads(available={}), Reads(held={}), Reads(gate=object())):
        with pytest.raises(TypeError, match="derives"):
            BookClearing(book, cat, reads=given)
        with pytest.raises(TypeError, match="derives"):
            SolverAgent(book, cat, clearing=None, reads=given)


def test_the_clearing_keeps_its_old_name_for_one_release():
    """`MockClearing` was renamed `BookClearing` (review item 12); the old
    name stays an alias of the same class for one release."""
    import loopmarket
    from loopmarket.clearing import BookClearing, MockClearing
    assert MockClearing is BookClearing
    assert loopmarket.MockClearing is loopmarket.BookClearing is BookClearing
