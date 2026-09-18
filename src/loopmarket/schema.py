"""The single, uniform offer form.

Every economic intention in the marketplace is one `Offer`: an exchange of a
*thing* (a conjunction of OntoDAG categories — since the v3 record including
the terms that say where and when it changes hands — with quantity) against
an amount of the maker's *personal token*. Exactly one side of every offer is the maker's own token — this is
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

Time and place. The v1/v2 records carried them as fields — a `service`
window and a `where` disc beside the concepts, matched by interval overlap
and disc intersection here. The v3 record (2026-09-12, decided in
`docs/plans/P1-spacetime-terms.md`) carries them *in the conjunction*, as
terms of role heads the catalogue declares under its time and geo
dimensions (`when(a..b)`, `where(cell)`, a route's `from(cell)`/`to(cell)`,
a transport's `depart`/`arrive`), matched by containment like every term;
cells and region nodes are the exact truth, and no v3 record holds a disc.
`GeoDisc` and the haversine survive only to read and match v1/v2 records
among themselves; nothing creates a new one. Only `valid` — a property of
the record, not of the thing — stays a window, and since v3 it may be
open-ended: the offer stands until withdrawn.
"""

from __future__ import annotations

import hashlib
import json
import math
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any


# ------------------------------------------------------------------- numbers

def q(x) -> Fraction:
    """The exact value of a quantity, amount or rate (planned invariant U9,
    riding the v4 record, 2026-09-14): an int or a `Fraction` as it is, a
    string as the decimal or `n/d` it spells (`"10.5"`, `"21/2"` — the v4
    record's spelling), and a float as the shortest decimal that prints it
    (`99.99` is 9999/100, what the person meant, not the binary neighbour
    the machine stored; `float(q(x)) == x` still holds). Everything
    clearing re-verifies goes through this; the solver's search may still
    use floats, since a search is a heuristic and clearing is the truth."""
    if isinstance(x, Fraction):
        return x
    if isinstance(x, bool):
        raise TypeError("a boolean is not a quantity")
    if isinstance(x, float):
        return Fraction(repr(x))
    if isinstance(x, (int, str)):
        return Fraction(x)
    raise TypeError(f"not a number: {x!r}")


def rat(x) -> str:
    """The v4 record's one spelling of an exact number: the reduced
    fraction `n/d`, or `n` alone when the denominator is 1 (`Fraction`
    reduces; `str` renders exactly so). What `q` reads back."""
    f = q(x)
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"

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
    """A half-open interval [start, end) in unix seconds (UTC).

    `end=None` is open-ended: the window stands until something else closes
    it — an offer's `valid` until its tombstone (Peter, 2026-09-12; a v3
    form, since it is record-visible). v1/v2 windows are always finite.
    """

    start: int
    end: int | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")

    @classmethod
    def from_iso(cls, start: str, end: str | None = None) -> "TimeWindow":
        def _parse(s: str) -> int:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())

        return cls(_parse(start), None if end is None else _parse(end))

    @property
    def open_ended(self) -> bool:
        return self.end is None

    def _hi(self) -> float:
        return math.inf if self.end is None else self.end

    def contains(self, other: "TimeWindow") -> bool:
        """fits-within for time: `other` lies entirely inside `self`."""
        return self.start <= other.start and other._hi() <= self._hi()

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other._hi() and other.start < self._hi()

    def intersection(self, other: "TimeWindow") -> "TimeWindow | None":
        s, e = max(self.start, other.start), min(self._hi(), other._hi())
        if e == math.inf:
            return TimeWindow(s, None)
        return TimeWindow(s, int(e)) if s < e else None

    def is_open_at(self, t: int) -> bool:
        return self.start <= t < self._hi()

    def to_record(self) -> list[int | None]:
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
    """A disc on the sphere: radius (meters) around a lat/lon centre.

    v1/v2 records only. Since the v3 record (2026-09-12) a place is a cell
    or region term in the conjunction and this class exists to read and
    match the old records among themselves; nothing creates a new disc.
    """

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
    qty: float | int | Fraction = 1.0
    unit: str = "unit"
    #: `divisible` is the v1–v3 field and the constructor's shorthand:
    #: True is `step == 0`, False is `step == qty`. The v4 record carries
    #: `step` (decided 2026-09-14, `P2-loop-selection.md`): the granularity
    #: a fill must be a multiple of — 0 continuous, the whole quantity
    #: indivisible, 1 whole apples out of a thousand, 25 kg sacks. One
    #: field says all three; `divisible` is derived from it.
    divisible: bool | None = None
    step: float | int | Fraction | None = None
    #: The give-side floor (v4): the least quantity one fill may take —
    #: the chartered bus that runs only if thirty seats sell, a minimum
    #: order. 0 is no floor. A flow lower bound, never parts on a give.
    min: float | int | Fraction = 0

    def __post_init__(self) -> None:
        if not self.concepts:
            raise ValueError("Thing needs at least one concept")
        for name in ("qty", "step", "min"):        # a spelled number is its value
            if isinstance(getattr(self, name), str):
                object.__setattr__(self, name, q(getattr(self, name)))
        if q(self.qty) <= 0:
            raise ValueError("Thing qty must be positive")
        object.__setattr__(self, "concepts", tuple(sorted(set(self.concepts))))
        if self.step is None:
            object.__setattr__(self, "step", 0 if self.divisible else self.qty)
        elif self.divisible is not None and self.divisible != (q(self.step) != q(self.qty)):
            raise ValueError("divisible and step disagree: give one of them")
        object.__setattr__(self, "divisible", q(self.step) != q(self.qty))
        if q(self.step) < 0 or q(self.step) > q(self.qty):
            raise ValueError("step must lie between 0 (continuous) and qty (indivisible)")
        if q(self.min) < 0 or q(self.min) > q(self.qty):
            raise ValueError("min must lie between 0 (no floor) and qty")
        if self.min and q(self.step) and q(self.min) % q(self.step):
            raise ValueError("min must be a multiple of step")

    def takes(self, qty, available=None) -> bool:
        """May one fill take `qty` of this thing? Within what is left of
        the quantity (`available`, the whole quantity when None — partial
        fills of a divisible give leave a remainder, 2026-09-14), not below
        the floor, and a positive multiple of the step (any positive amount
        when the step is 0). For a v3 thing this is exactly the old rule:
        all of it, or any part of a divisible one."""
        w, g, s, m = q(qty), q(self.qty), q(self.step), q(self.min)
        if available is not None:
            g = min(g, q(available))
        if w <= 0 or w > g or w < m:
            return False
        return s == 0 or w % s == 0

    def exhausted(self, available) -> bool:
        """Is what is left too little for any fill — nothing, less than the
        floor, or less than one step? (The remainder is dust: it stays
        unfilled, the U13 rule.)"""
        a = q(available)
        return a <= 0 or a < q(self.min) or (q(self.step) > 0 and a < q(self.step))

    def to_record(self, v: int = 4) -> dict[str, Any]:
        if v < 4:
            return {
                "concepts": list(self.concepts),
                "qty": self.qty,
                "unit": self.unit,
                "divisible": self.divisible,
            }
        return {
            "concepts": list(self.concepts),
            "qty": rat(self.qty),
            "unit": self.unit,
            "step": rat(self.step),
            "min": rat(self.min),
        }


@dataclass(frozen=True, slots=True)
class Parts:
    """A composed want: several things wanted together, all or nothing,
    one price for the lot (`P2-loop-selection.md` §10, `cli.md` §13; the
    v4 record, 2026-09-14). The theatre ticket and the transport to the
    theatre. Want side only — a give of several things is one give of one
    thing, the kit is a category. Each part is satisfied by its own give,
    and the fill names which give served which part."""

    parts: tuple[Thing, ...]

    def __post_init__(self) -> None:
        if len(self.parts) < 2:
            raise ValueError("a composed want has at least two parts; one part is a Thing")
        object.__setattr__(self, "parts", tuple(self.parts))

    def to_record(self, v: int = 4) -> dict[str, Any]:
        if v < 4:
            raise ValueError("parts are a v4 form")
        return {"parts": [p.to_record(v) for p in self.parts]}


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
    amount: float | int | Fraction

    def __post_init__(self) -> None:
        if isinstance(self.amount, str):           # a spelled number is its value
            object.__setattr__(self, "amount", q(self.amount))
        if q(self.amount) <= 0:
            raise ValueError("Token amount must be positive")

    def to_record(self, v: int = 4) -> dict[str, Any]:
        return {"issuer": self.issuer,
                "amount": self.amount if v < 4 else rat(self.amount)}


GIVE = "give"
WANT = "want"
ASK = GIVE     # order-book synonyms, kept for familiarity
BID = WANT


# --------------------------------------------------------------- requirements

@dataclass(frozen=True, slots=True)
class Requires:
    """What a maker requires of any counterparty on a leg through this
    offer — admissibility by declaration (decided by Peter 2026-09-18,
    `docs/plans/P2-loop-selection.md` §4a): a floor on the counterparty's
    `bond` (in the bond's asset, compared in that asset, so no numeraire
    enters — U14), and the witness types it accepts (`oracle`; empty means
    any). Matching refuses a leg that does not meet the requirement,
    fail-closed like vocabulary (U7), so every admissible loop is
    acceptable to each member by its own word and the beat's selection
    needs no risk weight to protect anyone. Until P3's escrow a
    counterparty's `bond` is its declaration; the gate compares what the
    records say, and the escrow will make the declaration true. A v5
    form: the record bump that carries it also spells `bond` as `n/d`."""

    bond: Fraction = Fraction(0)        # the floor on a no-show: the wanter's whole reliance
    oracles: tuple[str, ...] = ()       # witness types accepted; () accepts any
    #: The floor owed when the counterparty *cancels* the leg before its
    #: handover window instead of not showing (Peter, 2026-09-18: a
    #: cancellation is cheaper than a no-show, so the giver is motivated to
    #: cancel as early as it knows; a ride that will be late cancels and
    #: re-offers with the new time). None: the no-show floor applies.
    cancel: Fraction | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bond", q(self.bond))
        object.__setattr__(self, "oracles", tuple(sorted(set(self.oracles))))
        if self.cancel is not None:
            object.__setattr__(self, "cancel", q(self.cancel))
            if not 0 <= self.cancel <= self.bond:
                raise ValueError("the cancellation floor lies between 0 and the no-show floor")
        if self.bond < 0:
            raise ValueError("a bond floor is non-negative")

    @property
    def empty(self) -> bool:
        return self.bond == 0 and not self.oracles and self.cancel is None

    def met_by(self, other: "Offer", *, taken=None) -> bool:
        """Does `other`'s declaration satisfy this requirement? A bond backs
        every fill of its offer and is *reserved per fill* in proportion to
        the quantity taken (Peter, 2026-09-18): the share compared is
        bond × taken / quantity — the whole bond for a want, an
        indivisible give or an operator's whole run."""
        share = q(other.bond)
        if taken is not None and not other.composed:
            whole = q(other.thing.qty)
            if whole > 0:
                share = share * q(taken) / whole
        if share < self.bond:
            return False
        return not self.oracles or other.oracle in self.oracles

    def to_record(self) -> dict[str, Any]:
        rec = {"bond": rat(self.bond), "oracles": list(self.oracles)}
        if self.cancel is not None:
            rec["cancel"] = rat(self.cancel)
        return rec

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> "Requires":
        return cls(q(rec["bond"]), tuple(rec["oracles"]),
                   q(rec["cancel"]) if "cancel" in rec else None)


# -------------------------------------------------------------------------- offer

@dataclass(frozen=True, slots=True)
class Offer:
    """One uniform offer. Exactly one side is the maker's personal token.

    Fields `bond`, `oracle` and `arbitrator` are carried in the canonical
    encoding from day one (they are part of the offer's identity and of what
    a clearing layer will verify) but are not yet acted on by the mock
    clearing — see ARCHITECTURE.md, roadmap P3.
    """

    maker: str                    # key/address; also the personal-token issuer
    gives: Thing | Tokens
    wants: Thing | Parts | Tokens
    valid: TimeWindow             # while the offer itself stands (v3: may be open)
    # v1/v2 only — when and where the thing changes hands. v3 carries both
    # as bare geo/time terms in the conjunction (`geo(...)`, `time(...)`, a place);
    # the constructor refuses them on a v3 record and requires them below.
    service: TimeWindow | None = None
    where: GeoDisc | None = None
    ontology_root: str = ""       # pinned catalogue version (recordstore root)
    bond: Any = 0.0               # the maker's own bond (v1–v4 a float; v5 an exact rational, U9)
    oracle: str = "countersign"   # witness type the leg will settle against
    arbitrator: str = ""          # named in advance, like a jurisdiction clause
    # v5 (2026-09-18): what the maker requires of a counterparty — a bond
    # floor and the witness types it accepts; None on every earlier record.
    requires: Requires | None = None
    nonce: int = field(default_factory=lambda: int(_time.time() * 1000))
    # v2 widens the pins (planned U10): the dimension registry participates
    # in canonical reduction, so an ontology root without its REGISTRY_VERSION
    # is an incomplete pointer, and CONTRACT_VERSION names the guarantee set
    # the writer assumed (docs/plans/proof-fabric.md §3). Splat
    # `**ontology.pins` into give/want to fill all three at once.
    registry_version: str = ""    # ontodag dimension-registry version
    contract_version: str = ""    # ontodag contract version (G1-G6 guarantees)
    # v3 (2026-09-12): `service`/`where` leave the record — spacetime lives
    # in the conjunction as role terms — and `valid` may be open-ended.
    # v4 (2026-09-14): exact numbers as `n/d` strings (U9), `step` and
    # `min` on a thing in place of `divisible`, and a want may be `Parts`.
    # v5 (2026-09-18): `requires` — admissibility by declaration — and the
    # maker's `bond` as an exact rational. A v4 offer re-encodes as v4.
    v: int = 4                    # record version; identity includes it

    def __post_init__(self) -> None:
        thing_sides = [s for s in (self.gives, self.wants) if isinstance(s, (Thing, Parts))]
        token_sides = [s for s in (self.gives, self.wants) if isinstance(s, Tokens)]
        if len(thing_sides) != 1 or len(token_sides) != 1:
            raise ValueError(
                "uniform offer form: exactly one side is a Thing, one is Tokens"
            )
        if token_sides[0].issuer != self.maker:
            raise ValueError(
                "uniform offer form: the token side must be the maker's own token"
            )
        if q(self.bond) < 0:
            raise ValueError("bond must be non-negative")
        if self.v not in (1, 2, 3, 4, 5):
            raise ValueError(f"unknown offer record version: {self.v!r}")
        if self.v < 5 and self.requires is not None:
            raise ValueError("a counterparty requirement is a v5 form")
        if self.v >= 5:
            object.__setattr__(self, "bond", q(self.bond))
            if self.requires is None:
                object.__setattr__(self, "requires", Requires())
        if self.v < 2 and (self.registry_version or self.contract_version):
            raise ValueError("registry/contract pins are v2 fields")
        if isinstance(self.gives, Parts):
            raise ValueError("a give of several things is one give of one thing: parts are a want's")
        if self.v < 4:
            if isinstance(self.wants, Parts):
                raise ValueError("a composed want is a v4 form")
            for side in thing_sides:
                if q(side.min):
                    raise ValueError("a minimum fill is a v4 form")
                if q(side.step) not in (0, q(side.qty)):
                    raise ValueError("a step other than 0 or the whole quantity is a v4 form")
        if self.v >= 3:
            if self.service is not None or self.where is not None:
                raise ValueError(
                    "a v3 offer carries no service/where fields: put when(...) "
                    "and place as bare terms in the conjunction, or pass v=2 "
                    "for the field form")
        else:
            if self.service is None or self.where is None:
                raise ValueError("v1/v2 offers require service and where")
            if self.valid.open_ended or self.service.open_ended:
                raise ValueError("an open-ended window is a v3 form")

    # -- derived ------------------------------------------------------------

    @property
    def kind(self) -> str:
        return GIVE if isinstance(self.gives, Thing) else WANT

    @property
    def composed(self) -> bool:
        """A want of several parts (v4)."""
        return isinstance(self.wants, Parts)

    @property
    def parts(self) -> tuple[Thing, ...]:
        """The things this offer is about: one for a give or a simple want,
        several for a composed want."""
        side = self.gives if isinstance(self.gives, Thing) else self.wants
        return side.parts if isinstance(side, Parts) else (side,)

    @property
    def thing(self) -> Thing:
        """The one thing — a composed want has `parts` instead."""
        side = self.gives if isinstance(self.gives, Thing) else self.wants
        if isinstance(side, Parts):
            raise ValueError("a composed want has parts, not one thing")
        return side

    @property
    def tokens(self) -> Tokens:
        side = self.gives if isinstance(self.gives, Tokens) else self.wants
        assert isinstance(side, Tokens)
        return side

    @property
    def amount(self) -> Fraction:
        """The price of the lot, exact."""
        return q(self.tokens.amount)

    @property
    def unit_price(self) -> Fraction:
        """Maker-tokens per unit of the thing, exact (U9). A composed want
        has a price for the lot, not per unit: use `amount`."""
        return q(self.tokens.amount) / q(self.thing.qty)

    # -- encoding -----------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """The record in its *native* version: a v1 offer re-encodes as v1.

        Version is identity — the record's bytes are what `offer_id` hashes,
        so an offer read back from an old book must reproduce its original
        id exactly (invariant U2), never silently re-encode as the current
        version.
        """
        def side(s: Thing | Parts | Tokens) -> dict[str, Any]:
            rec = s.to_record(self.v)
            rec["type"] = "thing" if isinstance(s, Thing) else \
                "parts" if isinstance(s, Parts) else "tokens"
            return rec

        rec = {
            "v": self.v,
            "maker": self.maker,
            "gives": side(self.gives),
            "wants": side(self.wants),
            "valid": self.valid.to_record(),
            "ontology_root": self.ontology_root,
            "bond": rat(self.bond) if self.v >= 5 else self.bond,
            "oracle": self.oracle,
            "arbitrator": self.arbitrator,
            "nonce": self.nonce,
        }
        if self.v >= 5:
            rec["requires"] = self.requires.to_record()
        if self.v < 3:
            rec["service"] = self.service.to_record()
            rec["where"] = self.where.to_record()
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
        if v not in (1, 2, 3, 4, 5):
            raise ValueError(f"unknown offer record version: {v!r}")
        if v < 5 and "requires" in rec:
            raise ValueError("a counterparty requirement is a v5 form")
        if v >= 5 and "requires" not in rec:
            raise ValueError("a v5 offer record carries requires")
        if v >= 3 and ("service" in rec or "where" in rec):
            # a field this version does not define is meaning we cannot
            # read: refuse, as for an unknown version — never drop it
            raise ValueError("a v3 offer record carries no service/where")

        def thing(r: dict[str, Any]) -> Thing:
            if v < 4:
                return Thing(tuple(r["concepts"]), r["qty"], r["unit"], r["divisible"])
            if "divisible" in r or "step" not in r or "min" not in r:
                raise ValueError("a v4 thing carries step and min, not divisible")
            return Thing(tuple(r["concepts"]), q(r["qty"]), r["unit"],
                         step=q(r["step"]), min=q(r["min"]))

        def side(r: dict[str, Any]) -> Thing | Parts | Tokens:
            if r["type"] == "thing":
                return thing(r)
            if r["type"] == "parts":
                if v < 4:
                    raise ValueError("parts are a v4 form")
                return Parts(tuple(thing(p) for p in r["parts"]))
            if r["type"] != "tokens":
                raise ValueError(f"unknown offer side: {r['type']!r}")
            return Tokens(r["issuer"], q(r["amount"]) if v >= 4 else r["amount"])

        return cls(
            maker=rec["maker"],
            gives=side(rec["gives"]),
            wants=side(rec["wants"]),
            valid=TimeWindow(*rec["valid"]),
            service=TimeWindow(*rec["service"]) if v < 3 else None,
            where=GeoDisc(*rec["where"]) if v < 3 else None,
            ontology_root=rec.get("ontology_root", ""),
            bond=q(rec["bond"]) if v >= 5 else rec.get("bond", 0.0),
            oracle=rec.get("oracle", "countersign"),
            arbitrator=rec.get("arbitrator", ""),
            requires=Requires.from_record(rec["requires"]) if v >= 5 else None,
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

def _field_form(service, where, kw: dict[str, Any]) -> dict[str, Any]:
    """`service`/`where` passed ⇒ the v2 field form unless `v` says
    otherwise (the fields exist in no later record); nothing passed ⇒ the
    current record, whose spacetime is in the conjunction."""
    if (service is not None or where is not None) and "v" not in kw:
        kw = dict(kw, v=2)
    if kw.get("requires") is not None and "v" not in kw:
        kw = dict(kw, v=5)              # a requirement is a v5 form
    return dict(kw, service=service, where=where)


def give(maker: str, thing: Thing, amount, *, valid: TimeWindow,
         service: TimeWindow | None = None, where: GeoDisc | None = None,
         **kw: Any) -> Offer:
    """I give `thing`, priced `amount` on my own scale."""
    return Offer(maker=maker, gives=thing, wants=Tokens(maker, amount),
                 valid=valid, **_field_form(service, where, kw))


def want(maker: str, thing: Thing | Parts, amount, *, valid: TimeWindow,
         service: TimeWindow | None = None, where: GeoDisc | None = None,
         **kw: Any) -> Offer:
    """I want `thing` — or several things together, `Parts` — priced
    `amount` on my own scale for the lot."""
    return Offer(maker=maker, gives=Tokens(maker, amount), wants=thing,
                 valid=valid, **_field_form(service, where, kw))


ask = give     # order-book synonyms, kept for familiarity
bid = want
