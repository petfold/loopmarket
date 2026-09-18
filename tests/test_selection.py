"""Loop selection (P2, `docs/plans/P2-loop-selection.md` §1–§4, §6, §8;
built 2026-09-18): the packer is exact against brute force under
capacities and deterministic in §8's order, falls back to the greedy by
size and by budget never by clock, weighs a failure prior as a length
penalty, and the baseline's candidates are recall complete — the
best-rate reduction and the threshold masking of §6 (gate G1) no longer
lose a feasible loop — and shared divisible gives are packed up to what
is left of them."""

import random
from fractions import Fraction
from itertools import combinations

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import ExchangeGraph, MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.graph import enumerate_cycles
from loopmarket.matching import candidate_matches
from loopmarket.selection import Item, greedy, item_of, objective, order_key, pack, weight

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


# --------------------------------------------------------------------------- #
# The packer
# --------------------------------------------------------------------------- #

def _item(name, takes, legs, gain):
    return Item((name, "", ""), {k: Fraction(v) for k, v in takes.items()}, legs, Fraction(gain))


def _brute(items, capacity, prior=0):
    """Every subset, the feasible one with the best §8 key."""
    best = None
    for r in range(len(items) + 1):
        for combo in combinations(items, r):
            used = {}
            for it in combo:
                for oid, t in it.takes.items():
                    used[oid] = used.get(oid, Fraction(0)) + t
            if any(used[oid] > capacity.get(oid, Fraction(0)) for oid in used):
                continue
            key = order_key(combo, prior)
            if best is None or key < best[0]:
                best = (key, sorted(combo, key=lambda it: it.key))
    return best[1]


def test_pack_is_exact_against_brute_force_under_capacities():
    rng = random.Random(2026_09_18)
    for trial in range(150):
        offers = [f"o{i}" for i in range(rng.randint(3, 6))]
        capacity = {o: Fraction(rng.choice([1, 1, 2, 3, 5, 10])) for o in offers}
        items = []
        for i in range(rng.randint(2, 8)):
            picked = rng.sample(offers, rng.randint(2, min(4, len(offers))))
            takes = {o: Fraction(rng.choice([1, 1, 2, 5])) for o in picked}
            items.append(_item(f"L{i}", takes, len(picked), Fraction(rng.randint(1, 40), 100)))
        packing = pack(items, capacity)
        assert packing.exact
        assert [it.key for it in packing.chosen] == [it.key for it in _brute(items, capacity)], trial
        # every winner alone fits, and together they never oversell an offer
        used = {}
        for it in packing.chosen:
            for oid, t in it.takes.items():
                used[oid] = used.get(oid, Fraction(0)) + t
        assert all(used[oid] <= capacity[oid] for oid in used)


def test_pack_is_deterministic_and_the_greedy_is_a_floor():
    items = [_item("a", {"x": 1, "y": 1}, 2, "1/10"), _item("b", {"y": 1, "z": 1}, 2, "1/10"),
             _item("c", {"x": 1, "z": 1}, 2, "1/10"), _item("d", {"w": 1}, 1, "1/20")]
    cap = {"x": Fraction(1), "y": Fraction(1), "z": Fraction(1), "w": Fraction(1)}
    exact = pack(items, cap)
    # three equal loops pairwise overlapping: one of them plus d; §8 picks the smallest key among ties
    assert [it.key[0] for it in exact.chosen] == ["a", "d"]
    for _ in range(5):
        shuffled = list(items); random.shuffle(shuffled)
        assert [it.key for it in pack(shuffled, cap).chosen] == [it.key for it in exact.chosen]
    # the size threshold and the budget both hand over to the greedy, which is never better than exact
    by_size = pack(items, cap, exact_up_to=2)
    by_budget = pack(items, cap, budget=1)
    assert not by_size.exact and not by_budget.exact
    assert objective(by_size.chosen) <= objective(exact.chosen)
    assert [it.key for it in by_size.chosen] == [it.key for it in greedy(items, cap)]
    # an item that cannot clear alone is set aside with its reason
    tight = pack(items + [_item("e", {"w": 5}, 1, "1/2")], cap)
    assert "takes more" in tight.infeasible[("e", "", "")] and [it.key[0] for it in tight.chosen] == ["a", "d"]


def test_the_failure_prior_is_a_length_penalty_and_the_default_is_log_surplus():
    short = _item("s", {"x": 1, "y": 1}, 2, "1/10")           # 10 % over two legs
    long = _item("l", {"x": 1, "z": 1, "w": 1, "v": 1}, 4, "12/100")   # 12 % over four
    cap = {k: Fraction(1) for k in "xyzwv"}
    assert [it.key[0] for it in pack([short, long], cap).chosen] == ["l"]           # more surplus wins
    assert [it.key[0] for it in pack([short, long], cap, prior="1/5").chosen] == ["s"]  # (0.8)^4 taxes the long one
    assert weight(short) == Fraction(11, 10) and objective([short, long]) == Fraction(11, 10) * Fraction(112, 100)
    assert weight(short, "1/5") > weight(long, "1/5")


# --------------------------------------------------------------------------- #
# The recall gap (§6, gate G1): the baseline's candidates are complete
# --------------------------------------------------------------------------- #

def _cat():
    cat = Ontology(OntoDAG())
    return cat.load({"cello": [], "apple": [], "lesson": [], "pear": [], "repair": []})


def test_the_best_rate_reduction_no_longer_loses_the_feasible_loop():
    """Two parallel matches A->B: the cello at rate 2 whose lot cannot
    cancel B's lesson, and the apples at rate 1.1 whose lot can. Bellman-
    Ford over the best-rate graph certifies the cello cycle, clearing
    refuses it per node, and the apple cycle was never seen; the
    enumerator sees both and the packer clears the apples."""
    cat = _cat()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("A", Thing(("cello",)), 10, **V), want("B", Thing(("cello",)), 20, **V),
              give("A", Thing(("apple",), 1), 100, **V), want("B", Thing(("apple",), 1), 110, **V),
              give("B", Thing(("lesson",)), 100, **V), want("A", Thing(("lesson",)), 101, **V)]
    book.publish_many(offers); book.commit()
    matches = list(candidate_matches(offers, cat, now=NOW))
    old = ExchangeGraph.from_matches(matches).find_profitable_loops()
    assert len(old) == 1 and not old[0].per_node_ok                 # the cello cycle: infeasible
    cycles, complete = enumerate_cycles(matches)
    assert complete and len(cycles) == 1 and cycles[0].per_node_ok    # only the apple cycle is admissible
    agent = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True]
    assert book.is_filled(offers[2].offer_id) and not book.is_filled(offers[0].offer_id)


def test_the_threshold_no_longer_masks_a_qualifying_cycle():
    """Two disjoint cycles, 2 % and 20 %; with min_surplus 10 % the greedy
    extractor stopped at the first certified cycle's None; the enumerator
    judges each on its own product."""
    cat = _cat()
    offers = [give("A", Thing(("apple",)), 100, **V), want("B", Thing(("apple",)), 101, **V),
              give("B", Thing(("lesson",)), 100, **V), want("A", Thing(("lesson",)), 101, **V),
              give("C", Thing(("pear",)), 100, **V), want("D", Thing(("pear",)), 110, **V),
              give("D", Thing(("repair",)), 100, **V), want("C", Thing(("repair",)), 109, **V)]
    matches = list(candidate_matches(offers, cat, now=NOW))
    cycles, complete = enumerate_cycles(matches, min_surplus=0.1)
    assert complete and [round(float(c.surplus), 3) for c in cycles] == [0.199]
    g = ExchangeGraph.from_matches(matches)
    first = g.find_profitable_loop()
    if first.surplus < Fraction(1, 10):                      # the masking case, when Bellman-Ford lands there first
        assert g.find_profitable_loop(min_surplus=0.1) is None
    book = OfferRegistry(RecordStore(MemoryBytesStore())); book.publish_many(offers); book.commit()
    agent = SolverAgent(book, cat, clearing=None, solver_id="t", min_surplus=0.1)
    _r, loops = agent.find_loops(now=NOW)
    assert [round(float(l.surplus), 3) for l in loops] == [0.199]


def test_enumeration_is_canonical_bounded_and_flags_the_cut():
    cat = _cat()
    offers = [give("A", Thing(("apple",)), 100, **V), want("B", Thing(("apple",)), 110, **V),
              give("B", Thing(("lesson",)), 100, **V), want("A", Thing(("lesson",)), 105, **V),
              give("B", Thing(("pear",)), 100, **V), want("C", Thing(("pear",)), 110, **V),
              give("C", Thing(("repair",)), 100, **V), want("A", Thing(("repair",)), 105, **V)]
    matches = list(candidate_matches(offers, cat, now=NOW))
    cycles, complete = enumerate_cycles(matches)
    assert complete and sorted(len(c.matches) for c in cycles) == [2, 3]
    ids = [c.loop_id for c in cycles]
    assert [c.loop_id for c in enumerate_cycles(list(reversed(matches)))[0]] == ids    # order of arrival is irrelevant
    cut, complete = enumerate_cycles(matches, limit=1)
    assert not complete and len(cut) == 1
    assert enumerate_cycles(matches, max_legs=2)[0][0].loop_id == next(c.loop_id for c in cycles if len(c.matches) == 2)


# --------------------------------------------------------------------------- #
# Capacities: a divisible give shared by two loops
# --------------------------------------------------------------------------- #

def test_two_wants_of_one_divisible_give_clear_in_one_step():
    """The farm's 100 kg by 5; b1 and b2 each want 40 kg and each closes
    its own return leg. The disjoint extraction took one loop per step;
    the packer takes both, and the fold's remainder is 20 kg."""
    cat = _cat()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V),
              want("b1", Thing(("apple",), 40, "kg"), 90, **V), give("b1", Thing(("lesson",)), 80, **V),
              want("farm", Thing(("lesson",)), 85, **V),
              want("b2", Thing(("apple",), 40, "kg"), 84, **V), give("b2", Thing(("repair",)), 80, **V),
              want("farm", Thing(("repair",)), 81, **V)]
    book.publish_many(offers); book.commit()
    agent = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True, True]
    assert book.available(offers[0].offer_id) == 20 and not book.is_filled(offers[0].offer_id)
    book.verify_loop_atomicity()
    # with only 50 kg the two cannot both clear: the better loop wins
    tight = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers2 = [give("farm", Thing(("apple",), 50, "kg", step=5), 100, **V)] + offers[1:]
    tight.publish_many(offers2); tight.commit()
    agent2 = SolverAgent(tight, cat, clearing=MockClearing(tight, cat, clock=lambda: NOW), solver_id="t", min_surplus=0.0)
    receipts2 = agent2.step(now=NOW)
    assert len(receipts2) == 1 and receipts2[0].accepted
    assert tight.is_filled(offers2[1].offer_id) and not tight.is_filled(offers2[4].offer_id)   # b1's 19.5 % over b2's 6 %


def test_item_of_reads_a_circulation():
    cat = _cat()
    offers = [give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V),
              want("b1", Thing(("apple",), 40, "kg"), 90, **V), give("b1", Thing(("lesson",)), 80, **V),
              want("farm", Thing(("lesson",)), 85, **V)]
    matches = list(candidate_matches(offers, cat, now=NOW))
    loop = ExchangeGraph.from_matches(matches).find_profitable_loop()
    from loopmarket.graph import Circulation
    it = item_of(Circulation.from_loop(loop), "x")
    assert it.takes[offers[0].offer_id] == 40 and it.takes[offers[1].offer_id] == 40      # the give by the want's quantity, the want whole
    assert it.takes[offers[2].offer_id] == 1 and it.takes[offers[3].offer_id] == 1
    assert it.legs == 2 and it.gain == loop.surplus and it.key[0] == loop.loop_id and it.key[2] == "x"


def test_a_performance_factor_weighs_the_expected_benefit_when_given():
    """§4a's hook: a dimensionless factor per candidate — nothing sets it
    today. Two exclusive loops, the flakier one richer: nominal surplus
    picks it; a factor halving its weight picks the other; the packer's
    order and fallbacks are the same code either way."""
    rich = _item("rich", {"x": 1, "y": 1}, 2, "12/100")
    safe = _item("safe", {"x": 1, "z": 1}, 2, "10/100")
    cap = {k: Fraction(1) for k in "xyz"}
    assert [it.key[0] for it in pack([rich, safe], cap).chosen] == ["rich"]
    flaky = lambda it: Fraction(1, 2) if it.key[0] == "rich" else Fraction(1)
    assert [it.key[0] for it in pack([rich, safe], cap, factor=flaky).chosen] == ["safe"]
    assert weight(rich, 0, flaky) < weight(safe, 0, flaky) and objective([rich], 0, flaky) == weight(rich, 0, flaky)
    with pytest.raises(ValueError, match="performance factor"):
        weight(rich, 0, lambda it: Fraction(3, 2))
    assert [it.key[0] for it in pack([rich, safe], cap, factor=flaky, exact_up_to=1).chosen] == ["safe"]  # the greedy weighs it too
