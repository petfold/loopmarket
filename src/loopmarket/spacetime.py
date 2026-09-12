"""Discretised space and time as fits-within hierarchies.

Time buckets ("2026" ⊐ "2026-08" ⊐ "2026-08-14") and geohash cells (each
longer prefix is contained in every shorter prefix) are containment
hierarchies — exactly the shape OntoDAG stores. These helpers produce the
bucket/cell *names* under which offers are indexed, both as recordstore key
prefixes (`registry.py`) and, on the roadmap, as generated category nodes in
the shared OntoDAG itself, so that one `dag.get({...})` intersects concept,
place and time in a single query.

Candidate generation from these names is deliberately approximate (a disc
near a cell boundary also touches neighbouring cells; a window touches many
buckets). Matching correctness never depends on it: `matching.py` refines
every candidate with exact interval and disc geometry from `schema.py`.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from .schema import GeoDisc, TimeWindow

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

# Approximate max cell dimension (meters) per geohash precision, equator-worst.
_CELL_M = {1: 5_000_000, 2: 1_250_000, 3: 156_000, 4: 39_100,
           5: 4_890, 6: 1_220, 7: 153, 8: 38}


def geohash(lat: float, lon: float, precision: int = 6) -> str:
    """Plain geohash encoding (no dependencies)."""
    lat_lo, lat_hi = -90.0, 90.0
    lon_lo, lon_hi = -180.0, 180.0
    out: list[str] = []
    bits, ch, even = 0, 0, True
    while len(out) < precision:
        if even:
            mid = (lon_lo + lon_hi) / 2
            if lon >= mid:
                ch = (ch << 1) | 1
                lon_lo = mid
            else:
                ch <<= 1
                lon_hi = mid
        else:
            mid = (lat_lo + lat_hi) / 2
            if lat >= mid:
                ch = (ch << 1) | 1
                lat_lo = mid
            else:
                ch <<= 1
                lat_hi = mid
        even = not even
        bits += 1
        if bits == 5:
            out.append(_BASE32[ch])
            bits, ch = 0, 0
    return "".join(out)


def cell_bounds(cell: str) -> tuple[float, float, float, float]:
    """(lat_lo, lat_hi, lon_lo, lon_hi) of a geohash cell — the bit
    interleaving run backwards; exact on the same binary splits."""
    lat_lo, lat_hi = -90.0, 90.0
    lon_lo, lon_hi = -180.0, 180.0
    even = True
    for ch in cell:
        bits = _BASE32.index(ch)
        for shift in (4, 3, 2, 1, 0):
            bit = (bits >> shift) & 1
            if even:
                mid = (lon_lo + lon_hi) / 2
                lon_lo, lon_hi = (mid, lon_hi) if bit else (lon_lo, mid)
            else:
                mid = (lat_lo + lat_hi) / 2
                lat_lo, lat_hi = (mid, lat_hi) if bit else (lat_lo, mid)
            even = not even
    return lat_lo, lat_hi, lon_lo, lon_hi


def cell_for_coords(lat: float, lon: float, radius_m: float,
                    max_precision: int = 6) -> str:
    """The finest geohash cell that *contains* the whole radius around the
    point — the v3 spelling of a place: `where(LAT,LON,R)` at the prompt
    becomes `where(cell)`, and the cell is what the offer says (the truth
    since 2026-09-12, `docs/plans/P1-spacetime-terms.md` §4). Containing,
    not centred: a point near a cell edge names the coarser cell that
    covers what the maker meant, so a want across the edge still meets it.
    The price is coarseness near edges — the exact covering is a region
    node above the few cells that matter, once role heads accept nodes
    (ontodag #15). Input vocabulary only: the cell is the stored name, and
    the degree-per-metre approximation here never enters the order."""
    d_lat = radius_m / 111_320.0
    d_lon = radius_m / max(111_320.0 * math.cos(math.radians(lat)), 1e-9)
    for precision in range(max_precision, 0, -1):
        cell = geohash(lat, lon, precision)
        lat_lo, lat_hi, lon_lo, lon_hi = cell_bounds(cell)
        if lat_lo <= lat - d_lat and lat + d_lat <= lat_hi \
                and lon_lo <= lon - d_lon and lon + d_lon <= lon_hi:
            return cell
    return geohash(lat, lon, 1)


def cell_for(disc: GeoDisc, max_precision: int = 6) -> str:
    """The cell containing a v1/v2 disc, an index hint only: for a disc the
    exact check stays `GeoDisc.intersects` (two discs in sibling cells can
    still touch), so this never prunes — it files."""
    return cell_for_coords(disc.lat, disc.lon, disc.radius_m, max_precision)


def cell_chain(cell: str) -> list[str]:
    """All prefixes of a cell, coarsest first — its fits-within ancestors."""
    return [cell[: i + 1] for i in range(len(cell))]


def day_buckets(window: TimeWindow, max_buckets: int = 400) -> list[str]:
    """The UTC day names a window touches, e.g. ['2026-08-14', ...]."""
    out: list[str] = []
    t = window.start - (window.start % 86_400)
    while t < window.end and len(out) < max_buckets:
        out.append(
            datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        )
        t += 86_400
    return out


def bucket_chain(day: str) -> list[str]:
    """['2026', '2026-08', '2026-08-14'] — the day's fits-within ancestors."""
    return [day[:4], day[:7], day]
