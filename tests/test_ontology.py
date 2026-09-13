"""The catalogue facade: pinned roots and their constructor kwargs."""

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import Ontology


def test_root_reflects_the_committed_catalogue():
    # regression: EagerOntoDAG carries its store as `.store`; reading a
    # stale attribute name made .root silently '' for every persistent
    # catalogue, so solver proposals pinned nothing (U4 vacuous)
    ont = Ontology.persistent(RecordStore(MemoryBytesStore()))
    assert ont.root == ""                     # nothing committed yet
    ont.load({"produce": [], "vegetable-box": ["produce"]})
    committed = ont.commit()
    assert committed and ont.root == committed
    assert Ontology().root == ""              # in-memory: never pinned


def test_known_accepts_terms_ontodag_can_interpret_and_nothing_else():
    """A parametric term of a declared head is vocabulary though no node
    exists (2026-09-12); undeclared heads and malformed values fail closed."""
    from ontodag import OntoDAG
    from ontodag.prelude import apply as apply_prelude
    dag = OntoDAG()
    apply_prelude(dag)
    dag.put("from", ["prefix-dimension"])
    dag.put("ride", [])
    ont = Ontology(dag)
    assert ont.known("ride") and ont.known("from(u2e4x)") and ont.known("weight(..11kg)")
    assert not ont.known("bogus(u2e)") and not ont.known("durian")
    assert not ont.known("weight(11 kg)")             # malformed value
    assert ont.covers("from(u2e)", "from(u2e4x)")
    assert not ont.covers("from(u2e4x)", "from(u2e)")
    assert ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e)"])
    assert not ont.satisfies(["ride", "from(u2e4x)"], ["ride", "to(u2e)"])


# ---------------------------------------------------------------- roles
# One relation for every term (Peter, 2026-09-12): the want is the wider
# cone, the give the narrower. `from`/`to`/`when`/`where` are roles of the
# geo and time dimensions — heads under heads, so their parameters may be
# places — and they match by containment like any category. The overlap
# relation for "service roles" under a marker node lived one day.

ROLES = {"from": "geo", "to": "geo"}


def _roles_catalogue():
    from ontodag import OntoDAG
    ont = Ontology(OntoDAG())
    ont.declare_roles(ROLES)
    ont.declare_handover(["geo", "time"])
    ont.load({"amphora": [], "ride": []})
    ont.dag.put("made_in", ["geo"])             # descriptive: opts out
    ont.dag.put("made", ["time"])
    ont.declare_descriptive(["made_in", "made"])
    return ont


def test_declare_roles_adopts_the_prelude_and_pins_kinds():
    ont = _roles_catalogue()
    assert ont.head_kind("time") == "calendar-dimension"
    assert ont.head_kind("from") == ont.head_kind("made_in") == "prefix-dimension"
    assert ont.head_kind("geo") and ont.head_kind("prefix-dimension") is None
    assert "service-role" not in ont.dag.nodes
    ont.declare_roles(ROLES)                    # idempotent, like the prelude
    ont.declare_service_roles(ROLES)            # the 2026-09-12 name, one release
    import pytest
    with pytest.raises(ValueError):
        ont.declare_roles({"at": "amphora"})    # not a value space


def test_descriptive_terms_the_amphora():
    """`made_in`/`made` are geo/time terms describing the thing: the
    offered one must be at least as specific as the wanted one, exactly
    like a category — and not the other way round."""
    ont = _roles_catalogue()
    corinthian = ["amphora", "made_in(u2e4x)", "made(1850)"]
    greek = ["amphora", "made_in(u2e)", "made(1800..1899)"]
    assert ont.satisfies(corinthian, greek)
    assert not ont.satisfies(greek, corinthian)
    assert not ont.satisfies(["amphora", "made_in(u2e5)"], ["amphora", "made_in(u2e4)"])


def test_handover_terms_match_either_way_the_ride():
    """A give from `u2e4x` serves a want from anywhere in `u2e`, and a give
    from anywhere in `u2e` serves a want at `u2e4x` — whichever side is
    the flexible one (Peter, 2026-09-13). Siblings refuse; roles are never
    confused; a bare cell is the handover place with no head at all."""
    ont = _roles_catalogue()
    assert ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e)"])
    assert ont.satisfies(["ride", "from(u2e)"], ["ride", "from(u2e4x)"])
    assert not ont.satisfies(["ride", "from(u2e4)"], ["ride", "from(u2e5)"])
    assert ont.satisfies(["ride", "geo(u2e)"], ["ride", "geo(u2e4x)"])
    assert ont.satisfies(["ride", "geo(u2e4x)"], ["ride", "geo(u2e)"])
    assert not ont.satisfies(["ride", "geo(u2e4)"], ["ride", "geo(u2e5)"])
    # roles are never confused: the give's `to` is what answers a `to`
    assert not ont.satisfies(["ride", "from(u2e4x)", "to(u2e5)"], ["ride", "to(u2e4x)"])
    # a route: both places, independently
    give = ["ride", "from(u2e4x)", "to(u2e5m)"]
    assert ont.satisfies(give, ["ride", "from(u2e4)", "to(u2e5)"])
    assert not ont.satisfies(give, ["ride", "from(u2e4)", "to(u2e4)"])


def test_silence_and_vocabulary():
    ont = _roles_catalogue()
    assert ont.satisfies(["ride", "from(u2e)"], ["ride"])       # want: don't care
    assert not ont.satisfies(["ride"], ["ride", "from(u2e4x)"])  # give: says nothing
    # an extra unknown *category* only narrows the give: ignorable ...
    assert ont.satisfies(["ride", "mystery"], ["ride"])
    # ... a term the want names that nobody can interpret never matches
    assert not ont.satisfies(["ride"], ["ride", "time(garbage)"])
    assert not ont.satisfies(["ride", "at(u2e)"], ["ride", "at(u2e)"])  # no head
    # provably disjoint same-head terms describe nothing, on either side
    assert not ont.satisfies(["ride", "from(u2e4)", "from(u2e5)"], ["ride"])
    assert not ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e4)", "from(u2e5)"])
    # two same-head terms that do meet are their intersection
    assert ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e)", "from(u2e4)"])
    assert not ont.satisfies(["ride", "from(u2e5)"], ["ride", "from(u2e)", "from(u2e4)"])


def test_time_terms_match_when_one_window_contains_the_other():
    """`time(a..b)` on a give fits within `time(c..d)` on a want exactly
    when the give's half-open window lies inside the want's — inclusive
    calendar values encode [start, end-1]."""
    import random
    from datetime import datetime, timezone
    from loopmarket import TimeWindow

    def iso(t):
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def time(w):
        return f"time({iso(w.start)}..{iso(w.end - 1)})"

    ont = _roles_catalogue()
    rng = random.Random(2026_09_12)
    base = 1_800_000_000
    inside = outside = 0
    for _ in range(300):
        want = TimeWindow(base + rng.randrange(0, 3600), base + rng.randrange(3601, 7200))
        give = TimeWindow(base + rng.randrange(0, 3600), base + rng.randrange(3601, 7200))
        if rng.random() < 0.5:                    # boundary cases often
            give = TimeWindow(want.start, want.end) if rng.random() < 0.5 else \
                TimeWindow(want.start, want.end + 1)
        expect = (want.start <= give.start and give.end <= want.end) or \
                 (give.start <= want.start and want.end <= give.end)
        assert ont.satisfies(["ride", time(give)], ["ride", time(want)]) == expect, (give, want)
        inside += expect
        outside += not expect
    assert inside and outside


def _operators():
    from ontodag import OntoDAG
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo"})
    cat.declare_handover(["geo", "time"])
    cat.declare_operator({"transport": ("from", "to")})
    cat.load({"goods": [], "small-item": ["goods"], "bicycle": ["small-item"],
              "racing-bicycle": ["bicycle"], "piano": ["goods"],
              "bicycle-courier": ["transport"]})
    cat.dag.put("barcelona", ["geo"]); cat.dag.put("geo(sp3e)", ["barcelona"])
    cat.dag.put("flat", ["geo(sp3e3)"]); cat.dag.put("shop", ["geo(sp3e7)"])
    return cat


def test_an_operators_argument_is_its_want_and_matches_reversed():
    """Peter, 2026-09-13: `want 1kg fruit` matches `give 50kg apples`, and
    `want transport(bicycle)` matches `give transport(goods)` — the
    parameter of the transport is what the courier accepts, a want from the
    courier's side, so it is matched with the sides swapped."""
    cat = _operators()
    ok = cat.satisfies
    assert ok(["transport(goods)", "from(barcelona)", "to(barcelona)"],
              ["transport(bicycle)", "from(flat)", "to(shop)"])
    # the specialist takes racing bicycles and nothing else
    assert ok(["transport(bicycle)"], ["transport(racing-bicycle)"])
    assert not ok(["transport(bicycle)"], ["transport(piano)"])
    # a vague want against a constrained courier refuses — the mirror of
    # `give fruit` against `want apples`
    assert not ok(["transport(bicycle)"], ["transport(goods)"])
    assert not ok(["transport(bicycle)"], ["transport"])
    # a courier who takes anything takes the bicycle
    assert ok(["transport"], ["transport(bicycle)"])
    # the operator itself goes the usual way: a bicycle courier is transport
    assert ok(["bicycle-courier(bicycle)"], ["transport(racing-bicycle)"])
    assert not ok(["transport(bicycle)"], ["bicycle-courier(racing-bicycle)"])
    # a want naming no operator is not served by one
    assert not ok(["transport(goods)"], ["bicycle"])
    assert not ok(["transport(goods)"], ["goods"])


def test_a_conjunction_in_the_argument_is_several_constraints():
    """`transport(small-item weight(..8kg))` is the same term as
    `transport(small-item) transport(weight(..8kg))` — a list of cones the
    payload must sit within, however the two sides spell it; the 12 kg
    bicycle fails the 8 kg limit in every spelling."""
    cat = _operators()
    ok = cat.satisfies
    courier = ["transport(small-item weight(..8kg))"]
    split = ["transport(small-item)", "transport(weight(..8kg))"]
    for give in (courier, split):
        assert ok(give, ["transport(bicycle weight(5kg))"])
        assert ok(give, ["transport(bicycle)", "transport(weight(5kg))"])
        assert not ok(give, ["transport(bicycle weight(12kg))"])
        assert not ok(give, ["transport(bicycle)"])          # silent on weight
    assert cat.known("transport(small-item weight(..8kg))")
    assert not cat.known("transport(unicorn)")               # fails closed (U7)
    # ontodag #19 refuses a redundant constraint (one canonical name per
    # set): the spelling is unknown here, and a give carrying it is not read
    # as "accepts anything" — it matches nothing
    assert not cat.known("transport(bicycle small-item)")
    assert not ok(["transport(bicycle small-item)"], ["transport(racing-bicycle)"])
    assert cat.argument("transport(weight(..8000g) bicycle)") == ("bicycle", "weight(..8kg)")
    assert not cat.known("delivery(bicycle)")                # not an operator
    assert cat.argument("transport(weight(..8kg) small-item)") == \
        ("small-item", "weight(..8kg)")
    assert cat.operator_of("transport") == "transport" and cat.operator_of("from(flat)") is None
    assert cat.ends(["transport", "from(flat)", "to(shop)"]) == [("geo", "from(flat)", "to(shop)")]
    assert cat.ends(["transport", "from(flat)"]) == []
    assert cat.accepts(["bicycle", "flat"], ["transport(small-item)"])
    assert not cat.accepts(["piano", "flat"], ["transport(small-item)"])


def test_declare_operator_takes_a_category_and_two_ends():
    from ontodag import OntoDAG
    import pytest
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo", "depart": "time"})
    with pytest.raises(ValueError):
        cat.declare_operator({"geo": ("from", "to")})        # the 0.5.0 shape
    with pytest.raises(ValueError):
        cat.declare_operator({"transport": ("from", "depart")})  # two dimensions
    with pytest.raises(ValueError):
        cat.declare_operator({"transport": ("geo", "to")})   # a base, not a role
    cat.declare_operator({"transport": ("from", "to")})      # the category is created
    assert cat.operator_of("transport(x)") == "transport"
