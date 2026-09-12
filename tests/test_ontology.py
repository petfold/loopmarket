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
