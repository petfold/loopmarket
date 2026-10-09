"""Input spellings, and the line's conventions beside ontodag's grammar.

Times: relative spellings elaborate to fixed UTC at entry (cli.md §2),
through the registry's own calendar grammar, so the CLI never grows a
second date parser. Durations, and the offsets of relative times, are
ontodag's (review item 11, decided by Peter 2026-10-10): read by its
duration arithmetic in its units (`90min`, `2h`, `30d`, `1wk`), with no
unit table here, so a spelling means in `loop` what it means in `odag`.
Radii, coordinates and typed numbers are read exactly too (U9). The
line's conventions: `+`, the part separator of a composed want, and
`valid`, the one head the CLI interprets onto a field."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from fractions import Fraction

from ontodag import dimensions as _dims

from ..schema import TimeWindow


_TERM_RE = re.compile(r"^time\((.*)\)$")
_RATIONAL_RE = re.compile(r"^(-?\d+)(?:/(\d+))?([A-Za-z][A-Za-z0-9]*)$")
# A number with a unit after it: what `--until` reads as a duration rather
# than an instant (an ISO date has a dash after its digits, unix seconds no
# unit), so a refused duration says why instead of failing as a bad date.
_QUANTITY_RE = re.compile(r"^\d+(?:\.\d+)?(?:/\d+)?[A-Za-z]")
# The two spellings `loop` read differently from ontodag until review item
# 11: `m` (minutes here, metres there) and `w` (a week here, no unit there).
_OLD_SPELLING_RE = re.compile(r"^(\d+(?:\.\d+)?(?:/\d+)?)([mw])$")


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _local(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M %Z")


def _parse_ts(text: str) -> int:
    return int(datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc).timestamp())


def _calendar_span(text: str) -> tuple[int, int]:
    """[lo, hi) of an absolute ontodag time literal — a year, month, date,
    timestamp or range — via the registry's own calendar grammar, so the
    CLI never grows a second date parser."""
    canonical = _dims.canonicalize(f"time({text})", _dims.KIND_CALENDAR)
    param = _TERM_RE.match(canonical).group(1)
    if ".." in param:
        lo, hi = param.split("..", 1)
        if not lo or not hi:
            raise ValueError(f"time({text}): a window needs both ends")
        return _parse_ts(lo), _parse_ts(hi) + 1   # inclusive end → half-open
    ts = _parse_ts(param)
    return ts, ts


def _side_span(text: str, now: int) -> tuple[int, int]:
    """[lo, hi) of one side of a window expression: `now`, `today`,
    `tomorrow`, `+90d`, `-2h`, or any absolute ontodag time literal. A
    point has lo == hi."""
    text = text.strip()
    if text == "now":
        return now, now
    if text in ("today", "tomorrow"):
        day = now - now % 86_400 + (86_400 if text == "tomorrow" else 0)
        return day, day + 86_400
    if text[:1] in ("+", "-"):
        delta = _seconds(text[1:], shown=text)
        ts = int(now + delta if text[0] == "+" else now - delta)
        return ts, ts
    try:
        return _calendar_span(text)
    except ValueError as exc:
        raise ValueError(
            f"{text!r} is not a time: use now, today, tomorrow, +90d, -2h, "
            f"or an ISO-8601 date / timestamp / range") from exc


def window(text: str, now: int) -> TimeWindow:
    """A service or validity window from `A..B`, `..B`, `A..` or a single
    period (`today`, `2026-10`). Relative spellings are input vocabulary:
    the stored window is absolute UTC."""
    text = text.strip()
    if ".." in text:
        lo_text, hi_text = text.split("..", 1)
        lo = _side_span(lo_text, now)[0] if lo_text else now
        if not hi_text:
            return TimeWindow(lo, None)        # open-ended: until withdrawn
        hi_span = _side_span(hi_text, now)
        hi = hi_span[1] if hi_span[0] != hi_span[1] else hi_span[0]
        return TimeWindow(lo, hi)
    lo, hi = _side_span(text, now)
    if lo == hi:
        raise ValueError(
            f"{text}: an instant is not a window — give two ends (A..B)")
    return TimeWindow(lo, hi)


def duration_s(text: str) -> int:
    """Whole seconds from an ontodag duration spelling: `30d`, `2h`,
    `90min`, `1wk`, `1/2d` (review item 11)."""
    return int(_seconds(text.strip()))


def _seconds(text: str, *, shown: str | None = None) -> Fraction:
    """`text` as one ontodag duration, in seconds, exact: ontodag's own
    canonical form of `duration(TEXT)`, accepted only when its unit family
    is duration. `shown` is the spelling the person typed, for the error
    (`+90m` for a relative time's offset). A bare `m` or `w` is refused with
    the fix named, never read as minutes or a week: ontodag reads `90m` as
    90 metres and has no `w` (`W` is watts)."""
    shown = text if shown is None else shown
    old = _OLD_SPELLING_RE.match(text)
    if old:
        sign = shown[: len(shown) - len(text)]
        number, unit = old.groups()
        if unit == "m":
            raise ValueError(f"{shown} is metres in ontodag; write {sign}{number}min")
        raise ValueError(f"{shown}: ontodag has no unit w (W is watts); a week is wk — "
                         f"write {sign}{number}wk")
    if ".." in text:
        raise ValueError(f"{shown}: a duration is one length of time, not a range")
    try:
        canonical = _dims.canonicalize(f"duration({text})", _dims.KIND_LINEAR)
        family = _dims.family_of(canonical, _dims.KIND_LINEAR)
    except ValueError as exc:
        raise ValueError(f"{shown!r} is not a duration: ontodag's units are s, min, h, d "
                         f"and wk (30d, 2h, 90min, 1wk)") from exc
    if family == "count":
        raise ValueError(f"{shown} is a bare number; a duration needs its unit, as ontodag "
                         f"spells it: {text}s, {text}min, {text}h, {text}d or {text}wk")
    if family != "duration":
        raise ValueError(f"{shown} is {family} in ontodag, not a duration: its units are s, "
                         f"min, h, d and wk")
    return _rational(_dims.split_term(canonical)[1])


def _seconds_or_zero(text: str | None) -> int:
    """A duration setting that may be unset: empty or 0 is no bound."""
    return duration_s(text) if text and text.strip() not in ("0", "0s") else 0


def _rational(text: str) -> Fraction:
    """`7200s`, `1/2kg`, `5000m` → the number (unit suffix dropped)."""
    m = _RATIONAL_RE.match(text)
    if not m:
        raise ValueError(f"not a canonical scalar: {text!r}")
    return Fraction(int(m.group(1)), int(m.group(2) or 1))


def validity(text: str, now: int) -> TimeWindow:
    """`valid(30d)` stands from now; `valid(A..B)` is absolute; `valid(A..)`
    stands until withdrawn (Peter, 2026-09-12; a v3 form)."""
    if ".." in text:
        return window(text, now)
    return TimeWindow(now, now + duration_s(text))


def radius_m(text: str) -> float:
    """`5km`, `500m`, or bare metres, via ontodag's length grammar."""
    text = text.strip()
    if re.match(r"^\d+(?:\.\d+)?$", text):
        return _number(text)
    canonical = _dims.canonicalize(f"length({text})", _dims.KIND_LINEAR)
    value = _rational(re.match(r"^length\((.*)\)$", canonical).group(1))
    return int(value) if value.denominator == 1 else float(value)


def parse_coords(text: str) -> tuple[float, float, float]:
    """`LAT,LON,RADIUS` — the spelling `place` takes, and the literal any
    geo-kind term accepts, bare or as `from(46.05,14.50,5km)`; both become the cell
    of that radius around that point (`spacetime.cell_for_coords`), which
    is what the offer says — no disc anywhere since the v3 record. The day
    odag accepts `geo(LAT,LON,R)` this maps onto it (cli.md §11.1)."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"{text!r}: coordinates are LAT,LON,RADIUS (e.g. 46.05,14.50,5km)")
    lat, lon, radius = float(parts[0]), float(parts[1]), radius_m(parts[2])
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) or radius < 0:
        raise ValueError(f"{text!r}: coordinates out of range")
    return lat, lon, radius


def parse_now(text: str) -> int:
    text = text.strip()
    if re.match(r"^\d{9,}$", text):
        return int(text)
    lo, hi = _calendar_span(text)
    return lo


# The one head the CLI still interprets onto a field: `valid` is a property
# of the record (while the offer stands), read by the book against the
# clock, never by the catalogue against another offer. Where and when are
# ordinary catalogue terms: a bare geo or time term, or a place node.
_INTERPRETED_HEADS = ("valid",)


def _number(text: str):
    """A typed number, exact (U9): a whole number an int, a decimal the
    rational it spells (`10.5` → 21/2), so `give apple 100` and
    `give(..., 100)` — or `10.5` and `give(..., 10.5)` — produce the same
    v4 record bytes (gate G1, U2)."""
    return int(text) if "." not in text else Fraction(text)


#: The part separator of a composed want (cli.md §13, confirmed by Peter
#: 2026-09-12): the third loopmarket-only convention, want side only. A
#: token, not a word — no category is shadowed, and `+2h` inside a time
#: spelling is a different token.
PART_SEP = "+"


def _looks_like_time(token: str) -> bool:
    return ".." in token or token in ("now", "today", "tomorrow") \
        or bool(re.match(r"^\d{4}-\d{2}(-\d{2})?(T|$)", token))


def _until(text: str, now: int) -> int:
    """`--until`: a duration from now (`3d`, `12h`) or an instant (ISO-8601,
    unix seconds). A number with a unit is a duration, so `90m` is refused
    as one, with its fix, rather than as a malformed instant."""
    if _QUANTITY_RE.match(text.strip()):
        return now + duration_s(text)
    return parse_now(text)
