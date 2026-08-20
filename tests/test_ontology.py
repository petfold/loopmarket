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
