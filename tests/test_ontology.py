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

ROLES = {"when": "time", "where": "geo", "from": "geo", "to": "geo"}


def _roles_catalogue():
    from ontodag import OntoDAG
    ont = Ontology(OntoDAG())
    ont.declare_roles(ROLES)
    ont.load({"amphora": [], "ride": []})
    ont.dag.put("made_in", ["geo"])             # descriptive: the same shape
    ont.dag.put("made", ["time"])
    return ont


def test_declare_roles_adopts_the_prelude_and_pins_kinds():
    ont = _roles_catalogue()
    assert ont.head_kind("when") == "calendar-dimension"
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


def test_handover_terms_are_the_same_shape_the_ride():
    """A give from `u2e4x` fits within a want from anywhere in `u2e`; a
    give from anywhere in `u2e` does not fit a want at `u2e4x` (the give
    is the narrower cone). Siblings refuse; roles are never confused."""
    ont = _roles_catalogue()
    assert ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e)"])
    assert not ont.satisfies(["ride", "from(u2e)"], ["ride", "from(u2e4x)"])
    assert not ont.satisfies(["ride", "from(u2e4)"], ["ride", "from(u2e5)"])
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
    assert not ont.satisfies(["ride"], ["ride", "when(garbage)"])
    assert not ont.satisfies(["ride", "at(u2e)"], ["ride", "at(u2e)"])  # no head
    # provably disjoint same-head terms describe nothing, on either side
    assert not ont.satisfies(["ride", "from(u2e4)", "from(u2e5)"], ["ride"])
    assert not ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e4)", "from(u2e5)"])
    # two same-head terms that do meet are their intersection
    assert ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e)", "from(u2e4)"])
    assert not ont.satisfies(["ride", "from(u2e5)"], ["ride", "from(u2e)", "from(u2e4)"])


def test_when_term_is_window_containment():
    """`when(a..b)` on a give fits within `when(c..d)` on a want exactly
    when the give's half-open window lies inside the want's — inclusive
    calendar values encode [start, end-1]."""
    import random
    from datetime import datetime, timezone
    from loopmarket import TimeWindow

    def iso(t):
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def when(w):
        return f"when({iso(w.start)}..{iso(w.end - 1)})"

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
        expect = want.start <= give.start and give.end <= want.end
        assert ont.satisfies(["ride", when(give)], ["ride", when(want)]) == expect, (give, want)
        inside += expect
        outside += not expect
    assert inside and outside
