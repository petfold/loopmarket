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


def cell_for(disc: GeoDisc, max_precision: int = 6) -> str:
    """The finest geohash cell that is not smaller than the disc.

    Coarse-side-safe for indexing the disc's *centre*; boundary-crossing
    discs may also touch neighbour cells, which is why cells are an index
    hint, never a correctness dependency.
    """
    for precision in range(max_precision, 0, -1):
        if _CELL_M[precision] >= 2 * disc.radius_m:
            return geohash(disc.lat, disc.lon, precision)
    return geohash(disc.lat, disc.lon, 1)


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
