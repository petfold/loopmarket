"""Loop hunting: negative cycles, determinism, per-node surplus."""

from loopmarket import ExchangeGraph, GeoDisc, Ontology, Thing, TimeWindow, ask, bid
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
        ask("a", Thing(("g1",)), pa, **W), bid("a", Thing(("g3",)), ba, **W),
        ask("b", Thing(("g2",)), pb, **W), bid("b", Thing(("g1",)), bb, **W),
        ask("c", Thing(("g3",)), pc, **W), bid("c", Thing(("g2",)), bc, **W),
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
    assert loop.per_node_ok  # every node's bid >= its ask


def test_unprofitable_book_yields_nothing():
    offers = _triangle(ba=90, bb=45, bc=70)  # every bid below every ask
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


def test_two_cycle():
    offers = [
        ask("a", Thing(("g1",)), 10, **W), bid("a", Thing(("g2",)), 11, **W),
        ask("b", Thing(("g2",)), 10, **W), bid("b", Thing(("g1",)), 11, **W),
    ]
    g = ExchangeGraph.from_matches(candidate_matches(offers, ONT, now=NOW))
    loop = g.find_profitable_loop()
    assert loop is not None and len(loop.matches) == 2
    assert abs(loop.surplus - (1.1 * 1.1 - 1)) < 1e-9
