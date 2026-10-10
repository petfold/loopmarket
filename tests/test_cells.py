"""Cells in roles of geo by their own name (ontodag 0.31, its review
question 14, decided by Peter 2026-10-10).

Under ontodag 0.31 a bare word in a role of geo (`from`, `to`) names a
place and a cell is written `from(geo(u2e4x))`. An offer made before keeps
its spelling (its id hashes it) and still matches, read as the cell while
no place has that name: the index files its bare cell under the current
spelling, since 0.31 refuses to file a bare cell as a new name. Under an
older ontodag nothing is respelled. Tests for the half the installed
ontodag has run; the other half skips."""

import pytest
from ontodag import dimensions as odims

from loopmarket import Thing, give, want
from loopmarket.dimensions import DimensionIndex, candidate_matches_indexed
from loopmarket.matching import candidate_matches

from test_dimensions import NOW, roles_ontology, wide

CELLS_BY_NAME = hasattr(odims, "GEO_HEAD")
needs_031 = pytest.mark.skipif(not CELLS_BY_NAME, reason="needs ontodag 0.31")
before_031 = pytest.mark.skipif(CELLS_BY_NAME, reason="ontodag 0.31 respells")


def matches(ontology, offers, engine):
    return {(m.give.maker, m.want.maker)
            for m in engine(offers, ontology, now=NOW)}


@needs_031
def test_an_old_offer_with_a_bare_cell_matches_a_new_one():
    ontology = roles_ontology()
    old = give("bruno", Thing(("vegetable-box", "from(u2e4x)")), 50, **wide())
    new = want("amara", Thing(("produce", "from(geo(u2e4))")), 104, **wide())
    elsewhere = want("dora", Thing(("produce", "from(geo(u2f))")), 104, **wide())
    index = DimensionIndex(ontology)
    assert index.file(old)                       # filed under from(geo(u2e4x))
    assert old.offer_id in index.candidates(new)
    for engine in (candidate_matches, candidate_matches_indexed):
        assert matches(ontology, [old, new, elsewhere], engine) == {("bruno", "amara")}


@needs_031
def test_a_new_offer_matches_an_old_want():
    ontology = roles_ontology()
    new = give("bruno", Thing(("vegetable-box", "from(geo(u2e4x))")), 50, **wide())
    old = want("amara", Thing(("produce", "from(u2e4)")), 104, **wide())
    for engine in (candidate_matches, candidate_matches_indexed):
        assert matches(ontology, [new, old], engine) == {("bruno", "amara")}


@needs_031
def test_the_helpers_spell_cells_by_their_name():
    ont = roles_ontology()
    assert ont.is_geo_role("from") and not ont.is_geo_role("geo")
    assert not ont.is_geo_role("depart")                 # a role of time
    assert ont.cell_term("from", "u2e4") == "from(geo(u2e4))"
    assert ont.cell_term("geo", "u2e4") == "geo(u2e4)"
    assert ont.current_spelling("from(u2e4x)") == "from(geo(u2e4x))"
    assert ont.current_spelling("from(my_home)") == "from(my_home)"   # a place
    assert ont.current_spelling("depart(2026-10-05)") == "depart(2026-10-05)"


@before_031
def test_an_older_ontodag_respells_nothing():
    ont = roles_ontology()
    assert not ont.is_geo_role("from")
    assert ont.cell_term("from", "u2e4") == "from(u2e4)"
    assert ont.current_spelling("from(u2e4x)") == "from(u2e4x)"


def test_bare_reads_both_spellings():
    ont = roles_ontology()
    assert ont.bare("to(geo(u2e4))") == "geo(u2e4)"
    assert ont.bare("to(u2e4)") == "geo(u2e4)"
    assert ont.bare("from(my_home)") == "my_home"
