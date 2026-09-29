"""Item identity (I1, 2026-09-29; `docs/plans/items-and-ownership.md` §1): a
unique thing named by `item(h)`, where h is the content address of what
identifies it and nothing else.

Where the item has a natural identifier — a VIN, a land-register or
cadastral number, a maker and a serial — h is derived from it, so anyone
computes the same id and re-registration cannot defeat double-sale
detection (ontodag's stranger test passes). Where it has none — a watch
without papers, an artwork — h is the tagging record's hash, as strong as
the tagger who signed it. Everything that changes about the item
(condition, reports, owners) names h and is never part of it.

The term: `item(h)` with h 64 lowercase hex. ontodag's identifier kind
(equality only, K1, an upstream ask) is the term's proper home; until it
ships the head sits on the **prefix kind** (`Ontology.declare_item_heads`)
and loopmarket refuses any item term whose value is not a whole id
(`well_formed`, read by the matching gates) — so prefix containment, the
only order the stopgap kind knows, reduces to equality: a want naming an
item takes only that item, and a shortened id matches nothing.
"""

from __future__ import annotations

import hashlib
import json
import re

ITEM_HEADS = ("item",)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")          # no I, O or Q


def _h(record: dict) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def natural_id(scheme: str, identifier: str) -> str:
    """h of a natural identifier under a scheme: the genesis record holds
    only the scheme and the normalised identifier, so everyone derives the
    same h."""
    if not scheme or not identifier:
        raise ValueError("a natural id names a scheme and an identifier")
    return _h({"scheme": scheme, "identifier": identifier})


def vin_id(vin: str) -> str:
    """A vehicle's h from its VIN (ISO 3779): upper case, spaces and hyphens
    dropped, 17 characters without I, O or Q."""
    v = re.sub(r"[\s\-]", "", vin).upper()
    if not _VIN.match(v):
        raise ValueError(f"{vin!r} is not a VIN")
    return natural_id("vin", v)


def land_register_id(country: str, number: str) -> str:
    """A parcel's h from its country and cadastral or land-register number."""
    c, n = country.strip().upper(), re.sub(r"\s+", "", number)
    if len(c) != 2 or not n:
        raise ValueError("a land-register id is an ISO country code and a number")
    return natural_id("land-register", f"{c}:{n}")


def serial_id(maker: str, serial: str) -> str:
    """A manufactured item's h from its maker and serial number."""
    m, s = maker.strip().lower(), serial.strip().upper()
    if not m or not s:
        raise ValueError("a serial id names a maker and a serial")
    return natural_id("serial", f"{m}:{s}")


def tagged_id(fingerprint: str, tagger: str, binding_evidence: str = "") -> str:
    """An item without a natural identifier: h of the tagging record — the
    fingerprint's digest, the tagger who applied and signed it, the binding
    evidence. Not canonical: two taggers of one watch make two ids, which is
    the honest statement of an attested identity."""
    if not fingerprint or not tagger:
        raise ValueError("a tagged id names a fingerprint and its tagger")
    return _h({"scheme": "tagged", "fingerprint": fingerprint, "tagger": tagger,
               "binding_evidence": binding_evidence})


def term(h: str, head: str = "item") -> str:
    if not _HEX64.match(h):
        raise ValueError(f"{h!r} is not an item id (64 lowercase hex)")
    return f"{head}({h})"


def ids(concepts, heads=ITEM_HEADS) -> list[str]:
    """The item ids an offer's concepts name."""
    out = []
    for c in concepts:
        for head in heads:
            if isinstance(c, str) and c.startswith(head + "(") and c.endswith(")"):
                out.append(c[len(head) + 1:-1])
    return out


def well_formed(concepts, heads=ITEM_HEADS) -> bool:
    """Every item term names a whole id — the stopgap's guard that makes the
    prefix kind an equality (a shortened id would contain every item it
    prefixes)."""
    return all(_HEX64.match(h) for h in ids(concepts, heads))
