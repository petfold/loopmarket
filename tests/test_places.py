"""Places as rectangles (ontodag's questions 29 and 30, decided by Peter
2026-10-11): a geo value is a rectangle in degrees, typed as bounds, as a
position (the rectangle its written precision covers) or as a square
around one (`46.05,14.50±5km`), and in a role of geo it is written by geo's
name, `from(geo(47..48,13..14))`, while a bare word there names a place."""

import re

import pytest

from loopmarket import Thing, give, want
from loopmarket.cli.spellings import coords, looks_like_coords
from loopmarket.dimensions import DimensionIndex, candidate_matches_indexed
from loopmarket.matching import candidate_matches

from places import square
from test_dimensions import NOW, roles_ontology, wide

INSIDE = "geo(48.2..48.25,16.2..16.25)"     # where my_home is
AROUND = "geo(48.1..48.3,16.1..16.3)"       # holds it, under ljubljana
ELSEWHERE = "geo(49.5..50.5,14..15)"


def matches(ontology, offers, engine):
    return {(m.give.maker, m.want.maker)
            for m in engine(offers, ontology, now=NOW)}


def test_a_route_inside_the_wanted_rectangle_matches_by_containment():
    ontology = roles_ontology()
    inside = give("bruno", Thing(("vegetable-box", f"from({INSIDE})")), 50, **wide())
    wanted = want("amara", Thing(("produce", f"from({AROUND})")), 104, **wide())
    elsewhere = want("dora", Thing(("produce", f"from({ELSEWHERE})")), 104, **wide())
    index = DimensionIndex(ontology)
    assert index.file(inside)
    assert inside.offer_id in index.candidates(wanted)
    for engine in (candidate_matches, candidate_matches_indexed):
        assert matches(ontology, [inside, wanted, elsewhere], engine) == {("bruno", "amara")}


def test_the_helpers_write_a_value_by_geos_name_in_a_role():
    ont = roles_ontology()
    assert ont.is_geo_role("from") and not ont.is_geo_role("geo")
    assert not ont.is_geo_role("depart")                 # a role of time
    assert ont.geo_term("from", "48.1..48.3,16.1..16.3") == f"from({AROUND})"
    assert ont.geo_term("geo", "48.1..48.3,16.1..16.3") == AROUND


def test_bare_reads_a_role_term_as_its_coordinate():
    ont = roles_ontology()
    assert ont.bare(f"to({AROUND})") == AROUND
    assert ont.bare("from(my_home)") == "my_home"
    assert ont.bare("depart(2026-10-05)") == "time(2026-10-05)"


def test_a_geohash_cell_is_no_vocabulary_and_fails_closed():
    """A term an offer made under ontodag's registry 4 may carry: a cell,
    bare in a role or by geo's name. Neither is vocabulary now (U7), and
    such an offer is refused anyway for its registry major (review item 4)."""
    ont = roles_ontology()
    for term in ("geo(u2e4x)", "from(geo(u2e4x))", "from(u2e4x)"):
        assert not ont.known(term)


def test_a_square_around_a_point_is_ontodags_bounds():
    assert square('46.05,14.50±5km') == "46.005033..46.094967,14.435157..14.564843"
    assert square('46.05,14.50+-5km') == square('46.05,14.50±5000m')
    assert square('46.05,14.50') == "46.045..46.055,14.495..14.505"   # its precision


@pytest.mark.parametrize("text", ["46.05,14.50", "46.05,14.50±5km", "46.05,14.50+-500m",
                                  "46.0..46.1,14.4..14.6", "-33.9,151.2±1km"])
def test_coordinate_literals_are_ontodags_geo_typed_bare(text):
    assert looks_like_coords(text) and coords(text) == text


@pytest.mark.parametrize("text, fix", [("46.05,14.50,5km", "46.05,14.50+-5km"),
                                       ("46.05,14.50,250", "46.05,14.50+-250m")])
def test_the_old_radius_spelling_is_refused_with_the_fix(text, fix):
    assert looks_like_coords(text)
    with pytest.raises(ValueError, match=re.escape(f"`{fix}`")):
        coords(text)


@pytest.mark.parametrize("text", ["95,14±1km", "46.05,14.50±5", "46.05,14.50±5kg"])
def test_ontodag_refuses_what_a_place_cannot_be(text):
    with pytest.raises(ValueError):
        coords(text)


@pytest.mark.parametrize("text", ["home", "2026-10-11", "10kg", "today..+7d", "1"])
def test_other_tokens_are_not_coordinates(text):
    assert not looks_like_coords(text)
