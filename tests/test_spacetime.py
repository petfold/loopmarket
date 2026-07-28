"""Bucket/cell names: containment chains an OntoDAG can host."""

from loopmarket.schema import GeoDisc, TimeWindow
from loopmarket.spacetime import (
    bucket_chain, cell_chain, cell_for, day_buckets, geohash,
)


def test_geohash_known_value():
    # well-known reference point (57.64911, 10.40744) -> u4pruydqqvj
    assert geohash(57.64911, 10.40744, 6) == "u4pruy"


def test_cell_prefix_is_containment():
    cell = cell_for(GeoDisc(46.05, 14.50, 2_000))
    chain = cell_chain(cell)
    assert chain[-1] == cell
    for coarser, finer in zip(chain, chain[1:]):
        assert finer.startswith(coarser)  # fits-within, spelled as a prefix


def test_day_buckets_and_chain():
    w = TimeWindow.from_iso("2026-08-14T06:00+00:00", "2026-08-16T01:00+00:00")
    days = day_buckets(w)
    assert days == ["2026-08-14", "2026-08-15", "2026-08-16"]
    assert bucket_chain("2026-08-14") == ["2026", "2026-08", "2026-08-14"]
