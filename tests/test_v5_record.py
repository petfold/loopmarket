"""The v5 record as accepted 2026-09-19 (`docs/plans/P3-release-and-reclearing.md`
§5d): admissibility by declaration — a maker's `requires` (its neutral point
on its own scale, the cancellation ladder over lead time, the durable assets
it accepts as compensation with its own prices, witness types, escrow kinds)
and a giver's `bond` (a deposit — asset, quantity, unit — worth a value on
the giver's scale, held by an escrow). Matching refuses a leg unless each
side's requirement is met by the other's declaration, the deposit reserved
per fill (U7, fail closed); no asset is named by the protocol; nothing
converts after clearing (U14). v4 re-encodes byte for byte."""

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Acceptance, Bond, MockClearing, Offer, OfferRegistry, Ontology, Requires, SolverAgent, Thing,
    TimeWindow, give, want,
)
from loopmarket.clearing import LoopProposal
from loopmarket.graph import Loop
from loopmarket.matching import Match, candidate_matches, check_aggregate, check_match, check_parts, meets

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
EUR = Acceptance(("stablecoin-eur",), "EUR", 1)
SAT = Acceptance(("btc",), "sat", "1/2000")


def _cat():
    return Ontology(OntoDAG()).load({"apple": [], "lesson": [], "repair": [], "ticket": [], "transport": [],
                                     "money": [], "stablecoin-eur": ["money"], "btc": ["money"]})


def _deposit(concepts, qty, unit, value, escrow="0xE"):
    return Bond(Thing(concepts, qty, unit), value, escrow)


def test_the_v5_record_round_trips_and_v4_is_untouched():
    amara = want("amara", Thing(("transport",), 1, "run"), 40, **V,
                 requires=Requires(point=50, ladder=((604800, 5), (86400, 20), (0, 50)),
                                   accepts=(SAT, EUR), escrows=("contract",)))
    assert amara.v == 5 and amara.bond is None
    rec = amara.to_record()
    assert rec["bond"] is None
    assert rec["requires"] == {"point": "50", "ladder": [["604800", "5"], ["86400", "20"], ["0", "50"]],
                               "accepts": [[["btc"], "sat", "1/2000"], [["stablecoin-eur"], "EUR", "1"]],
                               "oracles": [], "escrows": ["contract"]}
    back = Offer.from_record(rec)
    assert back == amara and back.offer_id == amara.offer_id
    driver = give("driver", Thing(("transport",), 1, "run"), 45, **V,
                  bond=_deposit(("stablecoin-eur",), 60, "EUR", 45))
    assert driver.v == 5 and driver.requires.empty
    rec2 = driver.to_record()
    assert rec2["bond"] == {"asset": {"concepts": ["stablecoin-eur"], "min": "0", "qty": "60", "step": "60",
                                      "unit": "EUR"}, "value": "45", "escrow": "0xE"}
    assert rec2["requires"] == {"point": "0", "oracles": [], "accepts": []}
    assert Offer.from_record(rec2) == driver
    # the ladder reads linearly, the far amount beyond its far end
    assert amara.requires.at(3 * 86400) == 15 and amara.requires.at(10 * 86400) == 5 and amara.requires.at(0) == 50
    # v4 is untouched: a float bond, no requires key, the same bytes
    o4 = give("a", Thing(("apple",), 3), 9, **V, nonce=7)
    assert o4.v == 4 and "requires" not in o4.to_record() and o4.to_record()["bond"] == 0.0
    assert Offer.from_record(o4.to_record()).offer_id == o4.offer_id
    with pytest.raises(ValueError, match="v5 form"):
        give("a", Thing(("apple",), 3), 9, **V, bond=_deposit(("btc",), 1, "sat", 1), v=4)
    with pytest.raises(ValueError, match="v5 form"):
        Offer.from_record(dict(o4.to_record(), requires={"point": "0", "oracles": [], "accepts": []}))
    with pytest.raises(ValueError, match="carries requires"):
        Offer.from_record({k: v for k, v in rec.items() if k != "requires"})
    with pytest.raises(ValueError, match="ordered by lead"):
        Requires(point=5, ladder=((0, 5), (100, 1)))
    with pytest.raises(ValueError, match="between 0 and the neutral point"):
        Requires(point=5, ladder=((100, 9), (0, 5)))
    with pytest.raises(ValueError, match="positive price"):
        Acceptance(("btc",), "sat", 0)


def test_matching_reserves_the_deposit_per_fill_and_converts_once_on_private_scales():
    cat = _cat()
    amara = want("amara", Thing(("transport",), 1, "run"), 40, **V,
                 requires=Requires(point=50, accepts=(SAT, EUR), escrows=("contract",)))
    rich = give("d1", Thing(("transport",), 1, "run"), 45, **V, bond=_deposit(("stablecoin-eur",), 60, "EUR", 45))
    poor = give("d2", Thing(("transport",), 1, "run"), 45, **V, bond=_deposit(("btc",), 30_000, "sat", 45))
    unheld = give("d3", Thing(("transport",), 1, "run"), 45, **V, bond=_deposit(("stablecoin-eur",), 60, "EUR", 45, ""))
    bare = give("d4", Thing(("transport",), 1, "run"), 45, **V, v=5)
    legacy = give("d5", Thing(("transport",), 1, "run"), 45, **V)
    assert check_match(rich, amara, cat, now=NOW) is not None        # 60 EUR at 1/EUR covers 50
    assert check_match(poor, amara, cat, now=NOW) is None            # 30 000 sat at 1/2000 is 15
    assert check_match(unheld, amara, cat, now=NOW) is None          # she requires an escrow
    assert check_match(bare, amara, cat, now=NOW) is None and check_match(legacy, amara, cat, now=NOW) is None
    # a point with no acceptance can be met by nothing (fail closed); a point of zero needs no deposit
    assert check_match(rich, want("b", Thing(("transport",), 1, "run"), 40, **V, requires=Requires(point=1)), cat, now=NOW) is None
    assert check_match(bare, want("b", Thing(("transport",), 1, "run"), 40, **V, requires=Requires(point=0, oracles=("countersign",))), cat, now=NOW) is not None
    # the category is the catalogue's: `money` accepts a stablecoin deposit, not the other way
    money = want("b", Thing(("transport",), 1, "run"), 40, **V, requires=Requires(point=50, accepts=(Acceptance(("money",), "EUR", 1),)))
    assert check_match(rich, money, cat, now=NOW) is not None
    generic = give("d6", Thing(("transport",), 1, "run"), 45, **V, bond=_deposit(("money",), 60, "EUR", 45))
    assert check_match(generic, amara, cat, now=NOW) is None
    # reserved per fill: 100 kg with a 10 EUR deposit reserves 4 EUR for 40 kg
    farm = give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, bond=_deposit(("stablecoin-eur",), 10, "EUR", 8))
    assert check_match(farm, want("b", Thing(("apple",), 40, "kg"), 90, **V, requires=Requires(point=4, accepts=(EUR,))), cat, now=NOW)
    assert check_match(farm, want("b", Thing(("apple",), 40, "kg"), 90, **V, requires=Requires(point=5, accepts=(EUR,))), cat, now=NOW) is None
    assert meets(amara, rich, cat, taken=1, whole=1) and not meets(amara, poor, cat, taken=1, whole=1)
    # aggregated shares reserve by share; a composed want gates give by give
    evening = want("b", Thing(("ticket",), 2), 60, **V, requires=Requires(point=1, accepts=(EUR,)))
    t = give("t", Thing(("ticket",), 4, step=1), 80, **V, bond=_deposit(("stablecoin-eur",), 2, "EUR", 2))
    u = give("u", Thing(("ticket",), 4, step=1), 80, **V, bond=_deposit(("stablecoin-eur",), 2, "EUR", 2))
    assert check_aggregate(evening, [t, u], [1, 1], cat, now=NOW) is None                  # 1 of 4 reserves 1/2
    assert check_aggregate(want("b", Thing(("ticket",), 4), 120, **V, requires=Requires(point=1, accepts=(EUR,))),
                           [t, u], [2, 2], cat, now=NOW) is not None
    from loopmarket import Parts
    night = want("b", Parts((Thing(("ticket",), 2), Thing(("transport",), 1, "run"))), 60, **V,
                 requires=Requires(point=1, accepts=(EUR,)))
    theatre = give("th", Thing(("ticket",), 10, step=1), 200, **V, bond=_deposit(("stablecoin-eur",), 5, "EUR", 5))
    assert check_parts(night, (theatre, rich), cat, now=NOW) is not None
    assert check_parts(night, (theatre, poor), cat, now=NOW) is None


def test_the_solver_never_proposes_an_inadmissible_loop():
    """b requires 1 EUR of cover from whoever serves it. The richer loop runs
    through a seller with no deposit: not a candidate; the covered seller's
    loop clears; a hand-built proposal through the other is refused."""
    cat = _cat()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [want("b", Thing(("apple",), 3), 15, **V, requires=Requires(point=1, accepts=(EUR,))),
              give("cheap", Thing(("apple",), 3), 9, **V, v=5),
              give("covered", Thing(("apple",), 3), 12, **V, bond=_deposit(("stablecoin-eur",), 1, "EUR", 1)),
              give("b", Thing(("lesson",)), 10, **V, v=5),
              want("cheap", Thing(("lesson",)), 11, **V, v=5),
              want("covered", Thing(("lesson",)), 13, **V, v=5)]
    book.publish_many(offers); book.commit()
    assert not any(m.give.maker == "cheap" and m.want.maker == "b" for m in candidate_matches(offers, cat, now=NOW))
    agent = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t", min_surplus=0.0)
    assert [r.accepted for r in agent.step(now=NOW)] == [True]
    assert book.is_filled(offers[2].offer_id) and not book.is_filled(offers[1].offer_id)
    forged = Loop((Match(give=offers[1], want=offers[0]), Match(give=offers[3], want=offers[4])))
    verdict = MockClearing(book, cat, clock=lambda: NOW).rehearse(LoopProposal(forged, book.store.root, cat.root, "t", NOW))
    assert not verdict.accepted
