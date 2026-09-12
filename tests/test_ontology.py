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


# ---------------------------------------------------------------- service roles
# Two relations in one conjunction (docs/plans/P1-spacetime-terms.md §3):
# containment for what the thing is, overlap for where and when it changes
# hands. The head decides, and the head's role is catalogue vocabulary.

def _roles_catalogue():
    from ontodag import OntoDAG
    ont = Ontology(OntoDAG())
    ont.declare_service_roles()                 # when→time, where/from/to→geo
    ont.load({"amphora": [], "ride": []})
    ont.dag.put("made_in", ["geo"])             # descriptive: same kind, no role
    ont.dag.put("made", ["time"])
    return ont


def test_declare_service_roles_adopts_the_prelude_and_pins_kinds():
    ont = _roles_catalogue()
    assert ont.head_kind("when") == "calendar-dimension"
    assert ont.head_kind("from") == ont.head_kind("made_in") == "prefix-dimension"
    assert ont.is_service_role("when") and ont.is_service_role("to")
    assert not ont.is_service_role("geo") and not ont.is_service_role("made_in")
    assert ont.head_kind("geo") and ont.head_kind("prefix-dimension") is None
    ont.declare_service_roles()                 # idempotent, like the prelude
    import pytest
    with pytest.raises(ValueError):
        ont.declare_service_roles({"at": "amphora"})   # not a value space


def test_descriptive_terms_keep_containment_the_amphora():
    """`made_in`/`made` are geo/time terms describing the thing: the
    offered one must be at least as specific as the wanted one, exactly
    like a category — and not the other way round."""
    ont = _roles_catalogue()
    corinthian = ["amphora", "made_in(u2e4x)", "made(1850)"]
    greek = ["amphora", "made_in(u2e)", "made(1800..1899)"]
    assert ont.satisfies(corinthian, greek)
    assert not ont.satisfies(greek, corinthian)
    assert not ont.satisfies(["amphora", "made_in(u2e5)"], ["amphora", "made_in(u2e4)"])


def test_service_roles_match_by_overlap_the_ride():
    """`from` is the same geo kind, but a *role*: a give from anywhere in
    `u2e` serves a want at `u2e4x`, and a give at `u2e4x` serves a want
    from anywhere in `u2e`. Siblings share no point and refuse; roles are
    never confused with each other."""
    ont = _roles_catalogue()
    assert ont.satisfies(["ride", "from(u2e)"], ["ride", "from(u2e4x)"])
    assert ont.satisfies(["ride", "from(u2e4x)"], ["ride", "from(u2e)"])
    assert not ont.satisfies(["ride", "from(u2e4)"], ["ride", "from(u2e5)"])
    # roles are never confused: the give's `to` is what answers a `to`
    assert not ont.satisfies(["ride", "from(u2e4x)", "to(u2e5)"], ["ride", "to(u2e4x)"])
    # a route: both places must overlap, independently
    give = ["ride", "from(u2e4)", "to(u2e5)"]
    assert ont.satisfies(give, ["ride", "from(u2e4x)", "to(u2e5m)"])
    assert not ont.satisfies(give, ["ride", "from(u2e4x)", "to(u2e4x)"])


def test_absent_service_term_is_unconstrained_uninterpretable_fails_closed():
    ont = _roles_catalogue()
    assert ont.satisfies(["ride"], ["ride", "from(u2e4x)"])     # from anywhere
    assert ont.satisfies(["ride", "from(u2e)"], ["ride"])       # don't care
    # an extra unknown *category* only narrows the give: ignorable ...
    assert ont.satisfies(["ride", "mystery"], ["ride"])
    # ... an uninterpretable *service term* would widen it: never ignored
    assert not ont.satisfies(["ride", "when(garbage)"], ["ride"])
    assert not ont.satisfies(["ride"], ["ride", "when(garbage)"])
    assert not ont.satisfies(["ride", "at(u2e)"], ["ride", "at(u2e)"])  # no head
    # provably disjoint same-head terms: an empty conjunction matches nothing
    assert not ont.satisfies(["ride", "from(u2e4)", "from(u2e5)"], ["ride"])
    assert not ont.satisfies(["ride"], ["ride", "from(u2e4)", "from(u2e5)"])
    # two same-head terms that do meet are their intersection
    assert ont.satisfies(["ride", "from(u2e)", "from(u2e4)"], ["ride", "from(u2e4x)"])
    assert not ont.satisfies(["ride", "from(u2e)", "from(u2e4)"], ["ride", "from(u2e5)"])


def test_when_role_equals_the_service_window_gate():
    """The equivalence step 2 of the elimination promises: `when(a..b)` under
    overlap decides exactly what `TimeWindow.overlaps` decides today, over
    random windows — inclusive calendar values encode the half-open second
    window as [start, end-1], the `dimensions.time_term` convention."""
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
    agree = disagree = 0
    for _ in range(300):
        a = TimeWindow(base + rng.randrange(0, 3600), base + rng.randrange(3601, 7200))
        b = TimeWindow(base + rng.randrange(0, 3600), base + rng.randrange(3601, 7200))
        # narrow the second so boundary cases (touching ends) occur often
        if rng.random() < 0.5:
            b = TimeWindow(a.end, a.end + 60) if rng.random() < 0.5 else \
                TimeWindow(a.end - 1, a.end + 60)
        expect = a.overlaps(b)
        got = ont.satisfies(["ride", when(a)], ["ride", when(b)])
        assert got == expect, (a, b)
        agree += expect
        disagree += not expect
    assert agree and disagree           # both outcomes exercised
