"""The single, uniform offer form.

Every economic intention in the marketplace is one `Offer`: an exchange of a
*thing* (a conjunction of OntoDAG categories, with quantity, a service time
window and a service region) against an amount of the maker's *personal
token*. Exactly one side of every offer is the maker's own token — this is
enforced, not conventional. Two flavours follow:

- GIVE — gives a thing, wants scale-units ("I perform X, priced N on my scale")
- WANT — gives scale-units, wants a thing ("I want X, priced N on my scale")

(Order-book readers: a give is the ask, a want is the bid; `ask`/`bid`
remain as synonyms. The plain words won — in everyday English "ask" reads
as requesting, the exact opposite of its trading sense.)

Offers are immutable values. `canonical_bytes()` is deterministic (sorted
keys, minimal separators — recordstore's canonical JSON), and `offer_id` is
the SHA-256 of those bytes: the offer's logical content address. When the
record is stored on Swarm the storage layer assigns its own (BMT) reference;
the logical id stays the key at the application layer.

Time and place are given here as explicit fields, but conceptually they are
OntoDAG dimensions: interval containment and region containment are the same
*fits-within* partial order as category subsumption. `spacetime.py` provides
the discretised bucket/cell names under which offers are indexed in the DAG;
the exact geometry in this module is the refinement step.
"""

from __future__ import annotations

import hashlib
import json
import math
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:  # canonical encoding shared with the persistence layer when available
    from recordstore import canonical_bytes as _canonical_bytes
except Exception:  # pragma: no cover - fallback keeps the core dependency-light
    def _canonical_bytes(value: Any) -> bytes:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")


# --------------------------------------------------------------------------- time

@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A half-open interval [start, end) in unix seconds (UTC)."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")

    @classmethod
    def from_iso(cls, start: str, end: str) -> "TimeWindow":
        def _parse(s: str) -> int:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())

        return cls(_parse(start), _parse(end))

    def contains(self, other: "TimeWindow") -> bool:
        """fits-within for time: `other` lies entirely inside `self`."""
        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other.end and other.start < self.end

    def intersection(self, other: "TimeWindow") -> "TimeWindow | None":
        s, e = max(self.start, other.start), min(self.end, other.end)
        return TimeWindow(s, e) if s < e else None

    def is_open_at(self, t: int) -> bool:
        return self.start <= t < self.end

    def to_record(self) -> list[int]:
        return [self.start, self.end]


# ---------------------------------------------------------------------------- geo

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True, slots=True)
class GeoDisc:
    """A disc on the sphere: radius (meters) around a lat/lon centre."""

    lat: float
    lon: float
    radius_m: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0 and -180.0 <= self.lon <= 180.0):
            raise ValueError("GeoDisc centre out of range")
        if self.radius_m < 0:
            raise ValueError("GeoDisc radius must be non-negative")

    def contains(self, other: "GeoDisc") -> bool:
        """fits-within for space: `other` lies entirely inside `self`."""
        d = haversine_m(self.lat, self.lon, other.lat, other.lon)
        return d + other.radius_m <= self.radius_m + 1e-9

    def intersects(self, other: "GeoDisc") -> bool:
        """A handover point exists that both parties can reach."""
        d = haversine_m(self.lat, self.lon, other.lat, other.lon)
        return d <= self.radius_m + other.radius_m + 1e-9

    def to_record(self) -> list[float]:
        return [self.lat, self.lon, self.radius_m]


# -------------------------------------------------------------------------- sides

@dataclass(frozen=True, slots=True)
class Thing:
    """A conjunction of OntoDAG category names, with quantity.

    `concepts` is the *most specific* description the maker asserts; matching
    asks the ontology whether these concepts cover a counterparty's wanted
    categories (see `matching.py`). `divisible` marks whether the quantity can
    be partially filled — the loop arithmetic's product condition assumes
    divisibility; unit goods additionally require per-node surplus (see
    ARCHITECTURE.md, "The arithmetic of loops").
    """

    concepts: tuple[str, ...]
    qty: float = 1.0
    unit: str = "unit"
    divisible: bool = False

    def __post_init__(self) -> None:
        if not self.concepts:
            raise ValueError("Thing needs at least one concept")
        if self.qty <= 0:
            raise ValueError("Thing qty must be positive")
        object.__setattr__(self, "concepts", tuple(sorted(set(self.concepts))))

    def to_record(self) -> dict[str, Any]:
        return {
            "concepts": list(self.concepts),
            "qty": self.qty,
            "unit": self.unit,
            "divisible": self.divisible,
        }


@dataclass(frozen=True, slots=True)
class Tokens:
    """An amount on the maker's personal scale (a personal numeraire).

    Pure bookkeeping, not money: "token" survives as the record encoding's
    name, but nothing is ever held or transferred — the amounts exist to
    cancel inside the loop that passes through the maker (owner
    clarification 2026-08-21). One scale per maker turns n×m pairwise
    rates into n+m prices and makes the maker's quotes transitive by
    construction.
    """

    issuer: str
    amount: float

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("Token amount must be positive")

    def to_record(self) -> dict[str, Any]:
        return {"issuer": self.issuer, "amount": self.amount}


GIVE = "give"
WANT = "want"
ASK = GIVE     # order-book synonyms, kept for familiarity
BID = WANT


# -------------------------------------------------------------------------- offer

@dataclass(frozen=True, slots=True)
class Offer:
    """One uniform offer. Exactly one side is the maker's personal token.

    Fields `bond`, `oracle` and `arbitrator` are carried in the canonical
    encoding from day one (they are part of the offer's identity and of what
    a settlement layer will verify) but are not yet acted on by the mock
    settlement — see ARCHITECTURE.md, roadmap P3.
    """

    maker: str                    # key/address; also the personal-token issuer
    gives: Thing | Tokens
    wants: Thing | Tokens
    service: TimeWindow           # when the thing is performed / delivered
    where: GeoDisc                # region where the maker performs / accepts
    valid: TimeWindow             # while the offer itself stands
    ontology_root: str = ""       # pinned catalogue version (recordstore root)
    bond: float = 0.0
    oracle: str = "countersign"   # witness type the leg will settle against
    arbitrator: str = ""          # named in advance, like a jurisdiction clause
    nonce: int = field(default_factory=lambda: int(_time.time() * 1000))
    # v2 widens the pins (planned U10): the dimension registry participates
    # in canonical reduction, so an ontology root without its REGISTRY_VERSION
    # is an incomplete pointer, and CONTRACT_VERSION names the guarantee set
    # the writer assumed (docs/plans/proof-fabric.md §3). Splat
    # `**ontology.pins` into give/want to fill all three at once.
    registry_version: str = ""    # ontodag dimension-registry version
    contract_version: str = ""    # ontodag contract version (G1-G6 guarantees)
    v: int = 2                    # record version; identity includes it

    def __post_init__(self) -> None:
        thing_sides = [s for s in (self.gives, self.wants) if isinstance(s, Thing)]
        token_sides = [s for s in (self.gives, self.wants) if isinstance(s, Tokens)]
        if len(thing_sides) != 1 or len(token_sides) != 1:
            raise ValueError(
                "uniform offer form: exactly one side is a Thing, one is Tokens"
            )
        if token_sides[0].issuer != self.maker:
            raise ValueError(
                "uniform offer form: the token side must be the maker's own token"
            )
        if self.bond < 0:
            raise ValueError("bond must be non-negative")
        if self.v not in (1, 2):
            raise ValueError(f"unknown offer record version: {self.v!r}")
        if self.v < 2 and (self.registry_version or self.contract_version):
            raise ValueError("registry/contract pins are v2 fields")

    # -- derived ------------------------------------------------------------

    @property
    def kind(self) -> str:
        return GIVE if isinstance(self.gives, Thing) else WANT

    @property
    def thing(self) -> Thing:
        side = self.gives if isinstance(self.gives, Thing) else self.wants
        assert isinstance(side, Thing)
        return side

    @property
    def tokens(self) -> Tokens:
        side = self.gives if isinstance(self.gives, Tokens) else self.wants
        assert isinstance(side, Tokens)
        return side

    @property
    def unit_price(self) -> float:
        """Maker-tokens per unit of the thing."""
        return self.tokens.amount / self.thing.qty

    # -- encoding -----------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """The record in its *native* version: a v1 offer re-encodes as v1.

        Version is identity — the record's bytes are what `offer_id` hashes,
        so an offer read back from an old book must reproduce its original
        id exactly (invariant U2), never silently re-encode as the current
        version.
        """
        def side(s: Thing | Tokens) -> dict[str, Any]:
            rec = s.to_record()
            rec["type"] = "thing" if isinstance(s, Thing) else "tokens"
            return rec

        rec = {
            "v": self.v,
            "maker": self.maker,
            "gives": side(self.gives),
            "wants": side(self.wants),
            "service": self.service.to_record(),
            "where": self.where.to_record(),
            "valid": self.valid.to_record(),
            "ontology_root": self.ontology_root,
            "bond": self.bond,
            "oracle": self.oracle,
            "arbitrator": self.arbitrator,
            "nonce": self.nonce,
        }
        if self.v >= 2:
            rec["registry_version"] = self.registry_version
            rec["contract_version"] = self.contract_version
        return rec

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> "Offer":
        """Read any known record version; *raise* on unknown ones (U2).

        Fail closed, never best-effort: a future version may carry fields
        this code cannot interpret, and matching an offer while ignoring
        part of its meaning is exactly the silent drift U7 forbids for
        vocabulary.
        """
        v = rec.get("v")
        if v not in (1, 2):
            raise ValueError(f"unknown offer record version: {v!r}")

        def side(r: dict[str, Any]) -> Thing | Tokens:
            if r["type"] == "thing":
                return Thing(
                    tuple(r["concepts"]), r["qty"], r["unit"], r["divisible"]
                )
            return Tokens(r["issuer"], r["amount"])

        return cls(
            maker=rec["maker"],
            gives=side(rec["gives"]),
            wants=side(rec["wants"]),
            service=TimeWindow(*rec["service"]),
            where=GeoDisc(*rec["where"]),
            valid=TimeWindow(*rec["valid"]),
            ontology_root=rec.get("ontology_root", ""),
            bond=rec.get("bond", 0.0),
            oracle=rec.get("oracle", "countersign"),
            arbitrator=rec.get("arbitrator", ""),
            nonce=rec["nonce"],
            registry_version=rec.get("registry_version", ""),
            contract_version=rec.get("contract_version", ""),
            v=v,
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_record())

    @property
    def offer_id(self) -> str:
        """Logical content address: SHA-256 of the canonical encoding."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# ---------------------------------------------------------------- convenience

def give(maker: str, thing: Thing, amount: float, *, service: TimeWindow,
         where: GeoDisc, valid: TimeWindow, **kw: Any) -> Offer:
    """I give `thing`, priced `amount` on my own scale."""
    return Offer(maker=maker, gives=thing, wants=Tokens(maker, amount),
                 service=service, where=where, valid=valid, **kw)


def want(maker: str, thing: Thing, amount: float, *, service: TimeWindow,
         where: GeoDisc, valid: TimeWindow, **kw: Any) -> Offer:
    """I want `thing`, priced `amount` on my own scale."""
    return Offer(maker=maker, gives=Tokens(maker, amount), wants=thing,
                 service=service, where=where, valid=valid, **kw)


ask = give     # order-book synonyms, kept for familiarity
bid = want
