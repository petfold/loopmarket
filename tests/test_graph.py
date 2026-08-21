"""Loop hunting: negative cycles, determinism, per-node surplus."""

from loopmarket import ExchangeGraph, GeoDisc, Ontology, Thing, TimeWindow, give, want
from loopmarket.matching import candidate_matches

NOW = 5_000
W = dict(
    service=TimeWindow(1_000, 100_000),
    where=GeoDisc(46.0, 14.0, 50_000),
    valid=TimeWindow(0, 1_000_000),
)
ONT = Ontology().load({"g1": [], "g2": [], "g3": []})


def _triangle(pa=100, ba=104, pb=50, bb=52, pc=80, bc=83):
    return [
        give("a", Thing(("g1",)), pa, **W), want("a", Thing(("g3",)), ba, **W),
        give("b", Thing(("g2",)), pb, **W), want("b", Thing(("g1",)), bb, **W),
        give("c", Thing(("g3",)), pc, **W), want("c", Thing(("g2",)), bc, **W),
    ]


def test_profitable_triangle_found():
    g = ExchangeGraph.from_matches(
        candidate_matches(_triangle(), ONT, now=NOW)
    )
    loop = g.find_profitable_loop()
    assert loop is not None
    assert set(loop.nodes) == {"a", "b", "c"}
    expected = (52 / 100) * (83 / 50) * (104 / 80)
    assert abs(loop.product - expected) < 1e-9
    assert loop.per_node_ok  # every node's want >= its give


def test_unprofitable_book_yields_nothing():
    offers = _triangle(ba=90, bb=45, bc=70)  # every want below every give
    g = ExchangeGraph.from_matches(candidate_matches(offers, ONT, now=NOW))
    assert g.find_profitable_loop() is None


def test_min_surplus_threshold():
    g = ExchangeGraph.from_matches(
        candidate_matches(_triangle(), ONT, now=NOW)
    )
    assert g.find_profitable_loop(min_surplus=0.5) is None
    assert g.find_profitable_loop(min_surplus=0.05) is not None


def test_determinism():
    g = ExchangeGraph.from_matches(candidate_matches(_triangle(), ONT, now=NOW))
    l1, l2 = g.find_profitable_loop(), g.find_profitable_loop()
    assert l1.loop_id == l2.loop_id


def test_loop_id_is_rotation_invariant_but_pairing_sensitive():
    from loopmarket import Loop
    from loopmarket.matching import Match

    # one fungible good: either way of chaining the same six offers is real
    a_give, a_want = give("a", Thing(("g1",)), 10, **W), want("a", Thing(("g1",)), 11, **W)
    b_give, b_want = give("b", Thing(("g1",)), 10, **W), want("b", Thing(("g1",)), 11, **W)
    c_give, c_want = give("c", Thing(("g1",)), 10, **W), want("c", Thing(("g1",)), 11, **W)
    # pairing 1: a -> c -> b -> a
    p1 = (Match(a_give, c_want), Match(c_give, b_want), Match(b_give, a_want))
    # same cycle, entered at a different node: the same settlement decision
    assert Loop(p1).loop_id == Loop((p1[1], p1[2], p1[0])).loop_id
    # pairing 2: the same six offers chained the other way round
    p2 = (Match(a_give, b_want), Match(b_give, c_want), Match(c_give, a_want))
    assert Loop(p1).loop_id != Loop(p2).loop_id
    assert sorted(Loop(p1).offer_ids) == sorted(Loop(p2).offer_ids)


def test_two_cycle():
    offers = [
        give("a", Thing(("g1",)), 10, **W), want("a", Thing(("g2",)), 11, **W),
        give("b", Thing(("g2",)), 10, **W), want("b", Thing(("g1",)), 11, **W),
    ]
    g = ExchangeGraph.from_matches(candidate_matches(offers, ONT, now=NOW))
    loop = g.find_profitable_loop()
    assert loop is not None and len(loop.matches) == 2
    assert abs(loop.surplus - (1.1 * 1.1 - 1)) < 1e-9
