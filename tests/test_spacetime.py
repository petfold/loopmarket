"""Geohash cells: the containment hierarchy ontodag's prefix kind orders."""

from loopmarket.spacetime import cell_bounds, cell_for_coords, geohash


def test_geohash_known_value():
    # well-known reference point (57.64911, 10.40744) -> u4pruydqqvj
    assert geohash(57.64911, 10.40744, 6) == "u4pruy"


def test_cell_prefix_is_containment():
    fine = cell_for_coords(46.05, 14.50, 200)
    coarse = cell_for_coords(46.05, 14.50, 20_000)
    assert fine.startswith(coarse) and len(fine) > len(coarse)
    lat_lo, lat_hi, lon_lo, lon_hi = cell_bounds(fine)
    assert lat_lo <= 46.05 <= lat_hi and lon_lo <= 14.50 <= lon_hi
