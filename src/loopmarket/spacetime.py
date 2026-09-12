"""Geohash cells: the spelling of a place.

A geohash is a fits-within hierarchy — each longer prefix is contained in
every shorter one — and ontodag's prefix kind orders cells by exactly that,
so a cell is a catalogue term (`geo(u2e4x)`) and containment on it is
computed from the name. Since the v3 record (2026-09-12) a place *is* the
finest cell containing the radius the maker names (`cell_for_coords`), or
a region node above cells; the offer stores the name and matching is a
function of stored names. The degree-per-metre approximation below is
input vocabulary only: it never enters the order.

The day-bucket and cell-prefix *chains* this module produced until
2026-09-12 (`idx/t/`, `idx/g/` key prefixes for a recordstore index) are
gone with that index (registry.py): ontodag computes the containment
they spelled out.
"""

from __future__ import annotations

import math

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
    node above the few cells that matter (role heads take nodes since
    ontodag #15, 2026-09-12; the CLI has no verb for regions yet). Input
    vocabulary only: the cell is the stored name, and the degree-per-metre
    approximation here never enters the order."""
    d_lat = radius_m / 111_320.0
    d_lon = radius_m / max(111_320.0 * math.cos(math.radians(lat)), 1e-9)
    for precision in range(max_precision, 0, -1):
        cell = geohash(lat, lon, precision)
        lat_lo, lat_hi, lon_lo, lon_hi = cell_bounds(cell)
        if lat_lo <= lat - d_lat and lat + d_lat <= lat_hi \
                and lon_lo <= lon - d_lon and lon + d_lon <= lon_hi:
            return cell
    return geohash(lat, lon, 1)
