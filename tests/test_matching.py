"""Exact pairwise matching: meaning, time, space, quantity, version pins."""

from loopmarket import GeoDisc, Ontology, Thing, TimeWindow, give, want
from loopmarket.matching import check_match

NOW = 5_000
W = dict(
    service=TimeWindow(1_000, 100_000),
    where=GeoDisc(46.0, 14.0, 10_000),
    valid=TimeWindow(0, 1_000_000),
)
ONT = Ontology().load({
    "produce": [], "local": [], "weekly": [],
    "vegetable-box": ["produce", "local", "weekly"],
})


def test_subsumption_match():
    a = give("bruno", Thing(("vegetable-box",)), 50, **W)
    b = want("amara", Thing(("produce", "weekly")), 104, **W)
    m = check_match(a, b, ONT, now=NOW)
    assert m is not None and abs(m.rate - 104 / 50) < 1e-12


def test_subsumption_is_directional():
    a = give("bruno", Thing(("produce",)), 50, **W)          # too generic
    b = want("amara", Thing(("vegetable-box",)), 104, **W)   # wants specific
    assert check_match(a, b, ONT, now=NOW) is None


def test_unknown_vocabulary_fails_closed():
    a = give("x", Thing(("mystery-goods",)), 1, **W)
    b = want("y", Thing(("mystery-goods",)), 2, **W)
    assert check_match(a, b, ONT, now=NOW) is None


def test_time_space_and_validity_gates():
    a = give("x", Thing(("vegetable-box",)), 50, **W)
    late = dict(W, service=TimeWindow(200_000, 300_000))
    assert check_match(a, want("y", Thing(("produce",)), 60, **late), ONT, now=NOW) is None
    far = dict(W, where=GeoDisc(48.0, 20.0, 1_000))
    assert check_match(a, want("y", Thing(("produce",)), 60, **far), ONT, now=NOW) is None
    expired = dict(W, valid=TimeWindow(0, 100))
    assert check_match(a, want("y", Thing(("produce",)), 60, **expired), ONT, now=NOW) is None


def test_quantity_and_divisibility():
    whole = give("x", Thing(("vegetable-box",), qty=4), 100, **W)
    part = want("y", Thing(("produce",), qty=2), 60, **W)
    assert check_match(whole, part, ONT, now=NOW) is None      # indivisible
    split = give("x", Thing(("vegetable-box",), qty=4, divisible=True), 100, **W)
    partd = want("y", Thing(("produce",), qty=2, divisible=True), 60, **W)
    assert check_match(split, partd, ONT, now=NOW) is not None


def test_ontology_pin_must_agree():
    a = give("x", Thing(("vegetable-box",)), 50, ontology_root="r1", **W)
    b = want("y", Thing(("produce",)), 60, ontology_root="r2", **W)
    assert check_match(a, b, ONT, now=NOW) is None


def test_registry_and_contract_pins_refuse_major_skew():
    # major skew = the registry's canonical reduction changed order: refuse;
    # minor skew = vocabulary-additive: interoperates (ontodag D10)
    pins = dict(ontology_root="r", contract_version="0.1")
    a = give("x", Thing(("vegetable-box",)), 50, registry_version="4.1", **pins, **W)
    skewed = want("y", Thing(("produce",)), 60, registry_version="5.0", **pins, **W)
    minor = want("y", Thing(("produce",)), 60, registry_version="4.2", **pins, **W)
    assert check_match(a, skewed, ONT, now=NOW) is None
    assert check_match(a, minor, ONT, now=NOW) is not None


def test_mixed_pinning_refuses_even_under_an_unpinned_catalogue():
    # one side declares its semantic ground, the other is silent: agreement
    # cannot be confirmed, so the pair is refused (proof-fabric gate G2) —
    # even when the verifier's own catalogue is a dev-mode in-memory one
    pinned = give("x", Thing(("vegetable-box",)), 50, ontology_root="r",
                 registry_version="4.1", contract_version="0.1", **W)
    unpinned = want("y", Thing(("produce",)), 60, **W)
    assert check_match(pinned, unpinned, ONT, now=NOW) is None


def test_pinned_catalogue_refuses_unpinned_offers():
    # the fail-open '' wildcard dies once there is a persistent root to
    # demand (planned U10): absence refuses, full pins match
    from recordstore import MemoryBytesStore, RecordStore
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({
        "produce": [], "local": [], "weekly": [],
        "vegetable-box": ["produce", "local", "weekly"],
    })
    assert cat.commit()
    unpinned_a = give("x", Thing(("vegetable-box",)), 50, **W)
    unpinned_b = want("y", Thing(("produce",)), 60, **W)
    assert check_match(unpinned_a, unpinned_b, cat, now=NOW) is None
    pinned_a = give("x", Thing(("vegetable-box",)), 50, **cat.pins, **W)
    pinned_b = want("y", Thing(("produce",)), 60, **cat.pins, **W)
    assert check_match(pinned_a, pinned_b, cat, now=NOW) is not None


def test_service_role_terms_reach_matching_without_a_record_change():
    """A give from anywhere in `u2e` serves a want at `u2e4x` when `from`
    is a declared service role (overlap); the same pair under a catalogue
    that declares `from` as a plain geo head is refused (containment) —
    the relation is the catalogue's, pinned by its root, not this code's.
    The offer's `where` disc still gates alongside until the v3 record."""
    from ontodag import OntoDAG
    roles = Ontology(OntoDAG())
    roles.declare_service_roles({"from": "geo"})   # seed line, not core
    roles.load({"ride": []})
    from ontodag.prelude import apply as apply_prelude
    plain = Ontology(OntoDAG())
    apply_prelude(plain.dag)                 # `geo`, but no role marker
    plain.dag.put("from", ["geo"])
    plain.load({"ride": []})
    a = give("bruno", Thing(("ride", "from(u2e)")), 5, **W)
    b = want("amara", Thing(("ride", "from(u2e4x)")), 6, **W)
    assert check_match(a, b, roles, now=NOW) is not None
    assert check_match(a, b, plain, now=NOW) is None
    assert check_match(give("bruno", Thing(("ride", "from(u2e4x)")), 5, **W),
                       want("amara", Thing(("ride", "from(u2e)")), 6, **W),
                       plain, now=NOW) is not None


def test_places_regions_and_floors_match_through_the_graph():
    """ontodag #15/#16 (2026-09-12): a role term may name a *node* of the
    base dimension — a place under a cell, a region above cells, a floor
    under a building — and `satisfies` decides overlap by the graph. A
    give to the region serves a want at a place it covers; a give to the
    building serves its fourth floor; two floors never serve each other;
    a conjunction the catalogue cannot decide fails closed."""
    from ontodag import OntoDAG
    cat = Ontology(OntoDAG())
    cat.declare_service_roles({"where": "geo"})
    cat.load({"ride": [], "delivery": []})
    cat.dag.put("my_home", ["geo(u2e4x)"])
    cat.dag.put("my_home_4th", ["my_home"])
    cat.dag.put("my_home_ground", ["my_home"])
    cat.dag.put("ljubljana", ["geo"])                 # a region: above cells
    cat.dag.put("geo(u2e4)", ["ljubljana"])
    cat.dag.put("geo(u2e5)", ["ljubljana"])
    V = dict(valid=TimeWindow(0, 1_000_000))

    def pair(give_terms, want_terms):
        a = give("bruno", Thing(("delivery", *give_terms)), 5, **V)
        b = want("amara", Thing(("delivery", *want_terms)), 6, **V)
        return check_match(a, b, cat, now=NOW) is not None

    assert pair(["where(ljubljana)"], ["where(my_home)"])       # region ⊒ place
    assert pair(["where(my_home)"], ["where(ljubljana)"])       # and the reverse
    assert pair(["where(my_home)"], ["where(my_home_4th)"])     # building ⊒ floor
    assert pair(["where(my_home_4th)"], ["where(my_home)"])
    assert not pair(["where(my_home_ground)"], ["where(my_home_4th)"])  # siblings
    assert not pair(["where(ljubljana)"], ["where(u2f)"])       # covering: lower bound
    assert pair(["where(u2)"], ["where(ljubljana)"])            # a cell above the covering
    # the stored spelling is the name; ontodag orders it (`known` passes)
    assert cat.known("where(my_home_4th)") and cat.known("where(ljubljana)")
    # a name outside the dimension is refused, never read as a literal cell
    assert not cat.known("where(ride)")
    assert not pair(["where(ride)"], ["where(my_home)"])
    # same-head terms: a place inside a cell meets it as the place; a
    # place and a cell it is provably outside is empty; a meet no single
    # term names fails closed (the maker names a decidable conjunction)
    assert cat.meet("where", ["where(my_home)", "where(u2e)"]) == "where(my_home)"
    assert cat.meet("where", ["where(my_home)", "where(u2f)"]) is None
    assert pair(["where(my_home)", "where(u2e)"], ["where(my_home_4th)"])
    assert not pair(["where(my_home)", "where(u2f)"], ["where(my_home_4th)"])
    # a region and a cell above part of its covering: the covering is a
    # lower bound, so neither contains the other and no term names the
    # meet — ontodag raises, the check fails closed (say `where(ljubljana)`)
    assert not pair(["where(ljubljana)", "where(u2)"], ["where(my_home)"])
