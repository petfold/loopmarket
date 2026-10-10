"""v1 and v2 offers are retired (the 2026-10 review's item 12, decided by
Peter 2026-10-10): loopmarket makes none and matches none, and reads every
old record under its id (U2). Their place and time were fields, a service
window and a disc; since the v3 record they are terms of the conjunction,
and the constructors say which terms when asked for the old form. The old
records come from the golden corpus (`tests/fixtures/golden_records.txt`),
which pins their bytes."""

import dataclasses
import pickle

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Aggregator, BookClearing, GeoDisc, Loop, LoopProposal, Match, Offer, OfferRegistry,
    Ontology, SolverAgent, Thing, TimeWindow, Tokens, give, want,
)
from loopmarket.dimensions import DimensionIndex, candidate_matches_indexed
from loopmarket.matching import candidate_matches, check_match
from loopmarket.spacetime import cell_for_coords

V = dict(valid=TimeWindow(0))
AUG = 1_785_542_400            # 2026-08-01T00:00Z, the corpus's v1 triangle
DAY = 86_400


def catalogue():
    return Ontology().load({
        "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
        "piano-lesson": ["music-lesson"], "repair": ["service"],
        "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
        "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
    })


def triangle(golden, v):
    """The corpus's demo triangle of version `v`, read as an old book holds
    it, in the order amara, bruno, chen, each give before its want; and a
    moment inside its validity."""
    offers = [Offer.from_record(r) for k, r in golden.items()
              if k.startswith("offer/") and r["v"] == v and r["maker"] in ("amara", "bruno", "chen")]
    offers.sort(key=lambda o: (o.maker, o.kind != "give"))
    return offers, offers[0].valid.start + 3_600 + 60


def test_the_constructors_refuse_v1_and_v2_naming_the_terms_to_write():
    service, where = TimeWindow(AUG, AUG + DAY), GeoDisc(46.05, 14.50, 5_000)
    month = dict(valid=TimeWindow(AUG - DAY, AUG + 30 * DAY))   # a window v1/v2 could hold
    with pytest.raises(ValueError) as refused:
        give("amara", Thing(("piano-lesson",)), 100, service=service, where=where, **month)
    text = str(refused.value)
    assert f"'geo({cell_for_coords(46.05, 14.50, 5_000)})'" in text
    assert "'time(2026-08-01T00:00:00Z..2026-08-01T23:59:59Z)'" in text
    with pytest.raises(ValueError, match=r"'geo\(u2"):
        want("amara", Thing(("produce",)), 100, service=service, where=where, **month)
    for v in (1, 2):
        with pytest.raises(ValueError, match="retired"):
            give("amara", Thing(("piano-lesson",)), 100, service=service, where=where, v=v, **month)
        with pytest.raises(ValueError, match="retired"):
            Offer(maker="amara", gives=Thing(("piano-lesson",)), wants=Tokens("amara", 100),
                  service=service, where=where, v=v, **month)
    with pytest.raises(ValueError, match="retired"):            # the fields on a later record
        give("amara", Thing(("piano-lesson",)), 100, service=service, where=where, v=3, **month)
    # what replaces them is an ordinary v4 offer; v3 can still be asked for
    assert give("amara", Thing(("piano-lesson", f"geo({cell_for_coords(46.05, 14.50, 5_000)})",
                                "time(2026-08-01T00:00:00Z..2026-08-01T23:59:59Z)")), 100, **V).v == 4
    assert give("amara", Thing(("piano-lesson", "geo(u2e4)")), 100, v=3, **V).v == 3


def test_old_records_read_under_their_ids_and_copies_are_not_new_offers(golden):
    """Reading makes a v1/v2 offer, with the id its record hashes to;
    pickling one (a solver's worker processes) keeps it; but copying one
    with a change would make a new v1/v2 offer, and is refused."""
    old = [(k[len("offer/"):], r) for k, r in golden.items() if k.startswith("offer/") and r["v"] < 3]
    assert {r["v"] for _, r in old} == {1, 2}
    for oid, rec in old:
        offer = Offer.from_record(rec)
        assert offer.offer_id == oid and offer.to_record() == rec
        assert pickle.loads(pickle.dumps(offer)) == offer
    with pytest.raises(ValueError, match="retired"):
        dataclasses.replace(Offer.from_record(old[0][1]), nonce=1)


def test_a_book_of_old_offers_is_still_folded(golden):
    """History stands: a maker's book holding its v2 offers is announced and
    folded with every offer admitted and readable."""
    offers, _ = triangle(golden, 2)
    blobs = MemoryBytesStore()
    book = OfferRegistry(RecordStore(blobs))
    mine = [o for o in offers if o.maker == "amara"]
    book.publish_many(mine)
    book.commit()
    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce("amara", book.store)
    folded = OfferRegistry(RecordStore(blobs, root=agg.fold().book_root))
    assert {o.offer_id for o in folded.offers(include_filled=True)} == {o.offer_id for o in mine}


@pytest.mark.parametrize("v", [1, 2])
def test_v1_and_v2_offers_match_nothing(golden, v):
    """The demo triangle matched among itself in v1 and v2; read today, no
    pair matches, by the product or by the index, and no v1/v2 offer meets
    a current one on either side."""
    ont = catalogue()
    offers, now = triangle(golden, v)
    gives = [o for o in offers if o.kind == "give"]
    wants = [o for o in offers if o.kind == "want"]
    assert all(check_match(g, w, ont, now=now) is None for g in gives for w in wants)
    assert list(candidate_matches(offers, ont, now=now)) == []
    assert list(candidate_matches_indexed(offers, ont, now=now)) == []
    index = DimensionIndex(ont)
    assert not any(index.file(g) for g in gives)
    assert all(index.candidates(w) == set() for w in wants)
    current = dict(valid=TimeWindow(now - DAY, now + DAY))
    for old in gives:
        assert check_match(old, want("dora", Thing(old.thing.concepts, unit="course"), 999, **current),
                           ont, now=now) is None
    for old in wants:
        assert check_match(give("dora", Thing(("vegetable-box", "piano-lesson", "bicycle-repair"),
                                              unit="course"), 1, **current), old, ont, now=now) is None


def test_a_book_of_old_offers_clears_nothing(golden):
    """The solver proposes no loop through v2 offers, and clearing refuses
    the loop the 2026-08 code cleared: its legs no longer re-derive."""
    ont = catalogue()
    (amara, amara_w, bruno, bruno_w, chen, chen_w), now = triangle(golden, 2)
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many([amara, amara_w, bruno, bruno_w, chen, chen_w])
    book.commit()
    clearing = BookClearing(book, ont, clock=lambda: now)
    assert SolverAgent(book, ont, clearing).step(now=now) == []
    loop = Loop((Match(amara, chen_w), Match(chen, bruno_w), Match(bruno, amara_w)))
    receipt = clearing.submit(LoopProposal(loop, book.store.root, ont.root, "t", now))
    assert not receipt.accepted and "re-verification" in receipt.reason


def test_an_option_on_an_old_offer_clears_nowhere(golden):
    """A v6 option whose underlying is a v1/v2 give would clear a hold on an
    offer nothing matches any more, a hold no exercise could ever take: the
    gate refuses it with the retirement's reason (closing what the
    retirement left open, item 12)."""
    from recordstore import MemoryBytesStore, RecordStore
    from loopmarket.gate import CounterpartyGate
    from loopmarket.schema import GIVE, Offer
    old = next(o for o in (Offer.from_record(r) for k, r in sorted(golden.items())
                           if k.startswith("offer/") and r["v"] == 2)
               if o.kind == GIVE)
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish(old)
    option = give(old.maker, Thing(("option(x)",), old.thing.qty, old.thing.unit), 5,
                  valid=old.valid, nonce=99, underlying=old.offer_id,
                  exercise=TimeWindow(old.valid.start + 1, old.valid.start + 2))
    book.publish(option)
    book.commit()
    gate = CounterpartyGate.over(book, {}, now=old.valid.start)
    assert gate.option_fault(option) == \
        "the underlying is a retired v1/v2 offer: read, never matched"
