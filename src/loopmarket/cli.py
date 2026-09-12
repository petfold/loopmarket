"""`loop` — the command line for loopmarket (docs/plans/cli.md, built 2026-09-12).

The CLI is the contract between whatever talks to a human — a person at a
prompt, a shell script, an assistant — and the strict protocol beneath. The
protocol stays strict and dumb (points, bands refused, unknown vocabulary
fails closed); the CLI adds *deterministic* kindness — defaults, the price
memory, the direction rule, the approval block — every one a small tested
rule printed in words. Judgement lives above it, never below it.

Design rules this module obeys (cli.md, settled with Peter 2026-09-11/12):

* **One grammar.** A token after the verb is a bare category, an ontodag
  term `head(param)`, or one of exactly two loopmarket conventions: a bare
  number *first* is the quantity, a bare number *last* is the price.
  Nothing bare is reserved; there is no alias mechanism; `key=value` was
  rejected as a second grammar.
* **Names live in the catalogue.** A place is a node whose metadata carries
  its disc; `place NAME LAT,LON,R` is the dated bridge until odag accepts
  coordinates (cli.md §11.1). Private names are written to odag's *active*
  store (the personal layer) and resolved through the composed view; only
  the `catalogue` store's root is pinned, so a private name never moves a
  root that offers pin.
* **Settings: odag's rule, odag's file, odag's inheritance.** flag > env >
  loop config > odag config > default; `~/.loopmarket/config` in odag's
  `key = value` format, `bee_*` and the default catalogue inherited from
  `~/.ontodag/config`.
* **An omitted price is my last unit price** for the same side and bare
  categories, read from the book, scaled by quantity — and marked in the
  approval block. No earlier offer is an error, never a guess.
* **Nothing publishes unseen.** The approval block is the `show` renderer
  (byte-identical, gate G4). `confirm auto` asks at a terminal and proceeds
  in a batch — except that a *reused* price in a batch refuses the line
  (Peter, 2026-09-12: fail closed; `confirm off` accepts reused prices in
  scripts that mean it).

Lifted from `ontodag/__main__.py` (attribution: the settings table with its
single precedence rule, the 0600 config writer, the stdin batch / REPL
runner, the tty-versus-pipe rendering switch). The one private import is
`_open_catalogue`, which uses odag's `Session` to open a store spec until
ontodag ships a public opener (cli.md §11.3; dated note there).
"""

from __future__ import annotations

import argparse
import contextvars
import json
import os
import re
import shlex
import sys
import time as _time
from collections import namedtuple
from datetime import datetime, timezone
from fractions import Fraction

from ontodag import OntoDAG
from ontodag import dimensions as _dims

from . import __version__
from .clearing import MockClearing
from .graph import Loop
from .matching import candidate_matches
from .ontology import Ontology
from .registry import OfferRegistry
from .schema import GIVE, WANT, GeoDisc, Offer, Thing, TimeWindow, give, want
from .solver.agent import SolverAgent
from .spacetime import cell_for


# --------------------------------------------------------------------------- #
# Settings: one table, one precedence rule (odag's)
# --------------------------------------------------------------------------- #

_Setting = namedtuple("_Setting", "env default flag help secret odag",
                      defaults=(False, None))

_SETTINGS = {
    "book": _Setting(
        "LOOP_BOOK", "", "-f SPEC",
        "my writable book: rs:PATH or swarm:TOPIC (default rs:~/.loopmarket/book)"),
    "catalogue": _Setting(
        "LOOP_CATALOGUE", "", "--catalogue SPEC",
        "the ontodag store offers pin (any odag store spec; default: odag's "
        "active store)", odag="store"),
    "peers": _Setting(
        "LOOP_PEERS", "", "--peer SPECS",
        "read-only books folded into every answer (comma-separated; "
        "swarm:TOPIC@OWNER follows someone else's feed)"),
    "maker": _Setting(
        "LOOP_MAKER", "", "--maker NAME",
        "my identity; the signer's address when bee_signer is set and the "
        "sig extra is installed"),
    "where": _Setting(
        "LOOP_WHERE", "", "--where NAME",
        "default place: a catalogue node carrying coordinates (`place`)"),
    "when": _Setting(
        "LOOP_WHEN", "..+90d", "--when WINDOW",
        "default service window, relative or absolute"),
    "valid": _Setting(
        "LOOP_VALID", "30d", "--valid DURATION",
        "how long my offers stand (a duration, or an absolute window)"),
    "now": _Setting(
        "LOOP_NOW", "", "--now TIME",
        "the clock (unix seconds or ISO-8601), for reproducible runs; "
        "default: wall clock"),
    "confirm": _Setting(
        "LOOP_CONFIRM", "auto", "--confirm MODE",
        "auto / on / off: auto asks at a terminal and proceeds in a batch "
        "unless a price was reused"),
    "render": _Setting(
        "LOOP_RENDER", "auto", "--render / --raw",
        "readable output (auto = on at a terminal, off in a pipe)"),
    "limit": _Setting(
        "LOOP_LIMIT", "auto", "-n N",
        "max result lines (auto = 50 at a terminal, all in a pipe; 0 = all)"),
    "bee_api": _Setting(
        "BEE_API", "http://localhost:1633", "--bee-api URL",
        "Bee node API endpoint, for swarm: stores", odag="bee_api"),
    "bee_batch": _Setting(
        "BEE_BATCH", "", "--bee-batch ID",
        "postage batch to pay for Swarm writes", odag="bee_batch"),
    "bee_signer": _Setting(
        "BEE_SIGNER", "", "--bee-signer KEY",
        "private key: publishes my swarm: book and is my maker identity",
        secret=True, odag="bee_signer"),
}

# Settings given as flags on this invocation (main() fills it): the flag layer
# of the table, applying to every command of a batch.
_OVERRIDES: dict[str, str] = {}

_TTY_LIMIT = 50


def _home_dir() -> str:
    return os.environ.get("LOOP_HOME") or os.path.join(
        os.path.expanduser("~"), ".loopmarket")


def _odag_home_dir() -> str:
    return os.environ.get("ONTODAG_HOME") or os.path.join(
        os.path.expanduser("~"), ".ontodag")


def _config_path() -> str:
    return os.path.join(_home_dir(), "config")


def _read_kv(path: str) -> dict[str, str]:
    """odag's config format: `key = value` lines, `#` comments."""
    cfg: dict[str, str] = {}
    if not os.path.exists(path):
        return cfg
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip()
    return cfg


def _read_config() -> dict[str, str]:
    return _read_kv(_config_path())


def _read_odag_config() -> dict[str, str]:
    return _read_kv(os.path.join(_odag_home_dir(), "config"))


def _write_config(cfg: dict[str, str]) -> None:
    """Owner-readable only: the file can hold `bee_signer` (odag's reasoning
    and its explicit chmod, which also repairs a file written before)."""
    os.makedirs(_home_dir(), mode=0o700, exist_ok=True)
    path = _config_path()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for key in sorted(cfg):
            fh.write(f"{key} = {cfg[key]}\n")
    os.chmod(path, 0o600)


def _configured(key: str, flag=None) -> str:
    """flag > global flag > environment > loop config > odag config > default.

    Empty strings count as unset, so `BEE_BATCH=` does not shadow config.
    The odag layer exists for the settings the two tools share: configure
    the Bee node once in odag and `loop` inherits it; odag's active store
    is the default catalogue."""
    if flag:
        return flag
    if _OVERRIDES.get(key):
        return _OVERRIDES[key]
    setting = _SETTINGS[key]
    env = os.environ.get(setting.env)
    if env:
        return env
    cfg = _read_config()
    if cfg.get(key):
        return cfg[key]
    if setting.odag:
        odag_cfg = _read_odag_config()
        if odag_cfg.get(setting.odag):
            return odag_cfg[setting.odag]
    return setting.default


def _default_book_spec() -> str:
    return "rs:" + os.path.join(_home_dir(), "book")


def _book_spec() -> str:
    return _configured("book") or _default_book_spec()


def _peer_specs() -> list[str]:
    value = _configured("peers")
    return [s.strip() for s in value.split(",") if s.strip()] if value else []


# --------------------------------------------------------------------------- #
# Output streams (odag's ContextVars: an embedder captures both)
# --------------------------------------------------------------------------- #

_OUT = contextvars.ContextVar("loop_out", default=None)
_ERR = contextvars.ContextVar("loop_err", default=None)


def _out():
    stream = _OUT.get()
    return sys.stdout if stream is None else stream


def _err():
    stream = _ERR.get()
    return sys.stderr if stream is None else stream


def _isatty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _want_render(args, out) -> bool:
    flag = getattr(args, "render_mode", None)
    if flag is not None:
        return flag
    value = _configured("render").strip().lower()
    if value in ("0", "off", "raw", "false", "no"):
        return False
    if value in ("1", "on", "render", "true", "yes"):
        return True
    return _isatty(out)


def _want_limit(args, out) -> int:
    value = _configured("limit", getattr(args, "limit", None))
    value = value.strip().lower()
    if value in ("auto", ""):
        return _TTY_LIMIT if _isatty(out) else 0
    if value in ("all", "none", "off"):
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        raise ValueError(
            f"limit must be a number, `all` or `auto`, not {value!r}") from None


# --------------------------------------------------------------------------- #
# Time: relative spellings elaborate to fixed UTC at entry (cli.md §2)
# --------------------------------------------------------------------------- #

_REL_RE = re.compile(r"^([+-])(\d+(?:\.\d+)?)([smhdw])$")
_DUR_RE = re.compile(r"^(\d+(?:\.\d+)?)([smhdw])$")
_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86_400, "w": 7 * 86_400}
_TERM_RE = re.compile(r"^time\((.*)\)$")
_RATIONAL_RE = re.compile(r"^(-?\d+)(?:/(\d+))?([A-Za-z][A-Za-z0-9]*)$")


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
    m = _REL_RE.match(text)
    if m:
        delta = float(m.group(2)) * _UNIT_S[m.group(3)]
        ts = int(now + delta if m.group(1) == "+" else now - delta)
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
            raise ValueError(f"{text}: a window needs an end")
        hi_span = _side_span(hi_text, now)
        hi = hi_span[1] if hi_span[0] != hi_span[1] else hi_span[0]
        return TimeWindow(lo, hi)
    lo, hi = _side_span(text, now)
    if lo == hi:
        raise ValueError(
            f"{text}: an instant is not a window — give two ends (A..B)")
    return TimeWindow(lo, hi)


def duration_s(text: str) -> int:
    """Seconds from `30d`, `2h`, `90m`, or any ontodag duration spelling."""
    m = _DUR_RE.match(text.strip())
    if m:
        return int(float(m.group(1)) * _UNIT_S[m.group(2)])
    try:
        canonical = _dims.canonicalize(f"duration({text})", _dims.KIND_LINEAR)
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a duration (30d, 2h, 90m)") from exc
    return int(_rational(re.match(r"^duration\((.*)\)$", canonical).group(1)))


def _rational(text: str) -> Fraction:
    """`7200s`, `1/2kg`, `5000m` → the number (unit suffix dropped)."""
    m = _RATIONAL_RE.match(text)
    if not m:
        raise ValueError(f"not a canonical scalar: {text!r}")
    return Fraction(int(m.group(1)), int(m.group(2) or 1))


def validity(text: str, now: int) -> TimeWindow:
    """`valid(30d)` stands from now; `valid(A..B)` is absolute."""
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


def parse_now(text: str) -> int:
    text = text.strip()
    if re.match(r"^\d{9,}$", text):
        return int(text)
    lo, hi = _calendar_span(text)
    return lo


# --------------------------------------------------------------------------- #
# The session: book, catalogue, personal names layer, clock, identity
# --------------------------------------------------------------------------- #

_INTERPRETED_HEADS = ("when", "where", "valid")


def _open_catalogue(spec: str | None):
    """An odag `Session` for a store spec (`.od` file, `rs:PATH`,
    `swarm:NAME`); `None` opens odag's active store.

    The single private import from ontodag's CLI, isolated here on purpose
    (cli.md §11.3, 2026-09-12): opening a catalogue from an odag store spec
    should be a public ontodag call, and this function is deleted the day it
    is. Copying `_load_native` and the backends would drift; importing them
    keeps the two tools on one store layout. Bee settings loopmarket got as
    flags are pushed into odag's flag layer so the same node is used."""
    from ontodag import __main__ as odag

    for key in ("bee_api", "bee_batch", "bee_signer"):
        if _OVERRIDES.get(key):
            odag._OVERRIDES[key] = _OVERRIDES[key]
    if spec is None:
        return odag.Session(odag._resolve_store())
    return odag.Session(odag._normalize_spec(spec))


def _open_book(spec: str) -> OfferRegistry:
    """`rs:PATH` (odag's on-disk layout: blobs/ + root) or `swarm:TOPIC`
    (mine, signed with bee_signer) / `swarm:TOPIC@OWNER` (someone else's,
    read-only). Swarm imports stay inside this path (boundary B2)."""
    if spec.startswith("rs:"):
        from recordstore import DirBytesStore, FilePointer, RecordStore

        path = os.path.abspath(os.path.expanduser(spec[3:]))
        os.makedirs(path, exist_ok=True)
        return OfferRegistry(RecordStore(
            DirBytesStore(os.path.join(path, "blobs")),
            pointer=FilePointer(os.path.join(path, "root"))))
    if spec.startswith("swarm:"):
        from .registry import swarm_offer_book

        topic, _, owner = spec[6:].partition("@")
        kw = dict(api_url=_configured("bee_api"))
        if _configured("bee_batch"):
            kw["stamp"] = _configured("bee_batch")
        if owner:
            return swarm_offer_book(topic, owner=owner, **kw)
        signer = _configured("bee_signer")
        if not signer:
            raise ValueError(
                f"{spec}: a swarm: book needs bee_signer to publish, or "
                f"swarm:TOPIC@OWNER to follow someone else's")
        return swarm_offer_book(topic, signer=signer, **kw)
    raise ValueError(f"{spec}: a book is rs:PATH or swarm:TOPIC[@OWNER]")


class Session:
    """Everything a command may need, opened lazily (odag's rule: `help`
    and `set` must work with the node down)."""

    def __init__(self):
        self._book = None
        self._personal = None
        self._catalogue = None

    # -- the book ---------------------------------------------------------------

    @property
    def book(self) -> OfferRegistry:
        if self._book is None:
            self._book = _open_book(_book_spec())
        return self._book

    def fold(self) -> OfferRegistry:
        """My book plus every peer, as one read-only registry.

        A plain OR-set union into a memory store (`absorb` = re-assert every
        record), then the U11 check. The U8 admission rules need each book's
        owner, which a bare store spec does not name — they arrive with the
        `fold` command and the announcement channel (cli.md §9); until then
        `peers` are books you trust, the shared dev/demo shape."""
        specs = _peer_specs()
        if not specs:
            return self.book
        from recordstore import MemoryBytesStore, RecordStore

        folded = OfferRegistry(RecordStore(MemoryBytesStore()))
        folded.absorb(self.book)
        for spec in specs:
            folded.absorb(_open_book(spec))
        folded.commit()
        folded.verify_loop_atomicity()
        return folded

    # -- the catalogue and the names layer ---------------------------------------

    def _open(self) -> None:
        self._personal = _open_catalogue(None)
        spec = _configured("catalogue")
        if spec:
            from ontodag import __main__ as odag
            if odag._normalize_spec(spec) != self._personal.spec:
                self._catalogue = _open_catalogue(spec)
                return
        self._catalogue = self._personal

    @property
    def catalogue_session(self):
        if self._catalogue is None:
            self._open()
        return self._catalogue

    @property
    def personal_session(self):
        if self._personal is None:
            self._open()
        return self._personal

    @property
    def catalogue(self) -> Ontology:
        """The pinned ground offers match under (the primary store, never
        the composed view: matching must see exactly what the root names)."""
        ontology = Ontology(self.catalogue_session.dag)
        self._check_heads(ontology.dag)
        return ontology

    def view(self) -> OntoDAG:
        """The resolution view: catalogue + personal layer + odag overlays.
        Read-only, in memory; nothing ever writes the union."""
        if self.catalogue_session is self.personal_session:
            return self.personal_session.view()
        composed = OntoDAG()
        composed.merge(self.catalogue_session.dag)
        composed.merge(self.personal_session.view())
        return composed

    @staticmethod
    def _check_heads(dag: OntoDAG) -> None:
        """Gate G5's tripwire: the heads this CLI interprets onto fields must
        not be dimension heads the loaded catalogue declares — a pack that
        declared `when` as a calendar dimension would silently be shadowed."""
        if "dimension" not in dag.nodes:
            return
        for head in _INTERPRETED_HEADS:
            if head in dag.nodes and dag.is_below(head, "dimension"):
                raise ValueError(
                    f"the catalogue declares `{head}` as a dimension, but "
                    f"`loop` interprets {head}(...) onto an offer field until "
                    f"spacetime terms land (docs/plans/ontodag-coupling.md "
                    f"§2); refusing rather than shadowing it")

    # -- clock and identity --------------------------------------------------------

    @property
    def now(self) -> int:
        value = _configured("now")
        return parse_now(value) if value else int(_time.time())

    @property
    def maker(self) -> str:
        maker = _configured("maker")
        if maker:
            return maker
        signer = _configured("bee_signer")
        if signer:
            try:
                from .sigs import maker_address
                return maker_address(signer)
            except Exception:  # noqa: BLE001 — the sig extra is optional
                pass
        raise ValueError(
            "no maker identity: `loop set maker NAME` (or set bee_signer with "
            "the sig extra installed, and the key's address is your name)")

    # -- names -----------------------------------------------------------------------

    def place(self, name: str) -> GeoDisc:
        node = self.view().nodes.get(name)
        if node is None:
            raise ValueError(
                f"unknown place: {name} (it is a catalogue node — "
                f"`loop place {name} LAT,LON,RADIUS` creates one)")
        disc = node.metadata.get("disc")
        if not disc:
            raise ValueError(
                f"{name} carries no coordinates: "
                f"`loop place {name} LAT,LON,RADIUS`")
        return GeoDisc(*disc)

    def named_window(self, name: str) -> TimeWindow | None:
        """A time name (`evenings`) is a node under a `time(...)` term — the
        containment ontodag already computes; the CLI just reads it."""
        view = self.view()
        node = view.nodes.get(name)
        if node is None:
            return None
        candidates = [node] + list(view.get_ancestors(node))
        for item in candidates:
            if item.name.startswith("time("):
                lo, hi = _calendar_span(_TERM_RE.match(item.name).group(1))
                return TimeWindow(lo, hi) if lo != hi else None
        return None


# --------------------------------------------------------------------------- #
# Parsing an offer line: ontodag's grammar plus the two conventions
# --------------------------------------------------------------------------- #

_QTY_RE = re.compile(r"^(\d+(?:\.\d+)?)([A-Za-z][A-Za-z0-9]*)?$")
_BAND_RE = re.compile(
    r"^(\d+(?:\.\d+)?(?:[A-Za-z][A-Za-z0-9]*)?)?\.\."
    r"(\d+(?:\.\d+)?(?:[A-Za-z][A-Za-z0-9]*)?)?$")
_PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _number(text: str) -> int | float:
    """A whole number stays an int: canonical JSON distinguishes `100` from
    `100.0`, and the API demos write ints — `give apple 100` must produce
    the same record bytes as `give(..., 100)` (gate G1, U2)."""
    return float(text) if "." in text else int(text)

Parsed = namedtuple("Parsed", "qty unit divisible band concepts heads price")


def parse_offer_tokens(tokens: list[str]) -> Parsed:
    """`[10kg] CATEGORY|TERM ... [PRICE]` → the pieces, nothing resolved.

    Every token that is neither convention is passed through as written:
    a bare word is a category, `head(param)` is a term, and the three
    interpreted heads are separated so the caller can map them onto the
    offer's fields. Band spellings in quantity position are *accepted*
    here and refused at publish (gate G6) — they are the grammar."""
    toks = list(tokens)
    if not toks:
        raise ValueError("what? — give/want [QUANTITY] CATEGORY... [PRICE]")
    qty, unit, divisible, band = None, "unit", False, None
    m = _QTY_RE.match(toks[0])
    if _BAND_RE.match(toks[0]) and toks[0] != "..":
        band = toks.pop(0)
    elif m:
        qty = _number(m.group(1))
        unit = m.group(2) or "unit"
        divisible = bool(m.group(2))
        toks.pop(0)
    price = None
    if len(toks) > 1 and _PRICE_RE.match(toks[-1]):
        price = _number(toks.pop())
    elif len(toks) == 1 and _PRICE_RE.match(toks[0]) and qty is not None:
        raise ValueError(
            f"{' '.join(tokens)}: a bare number first is the quantity and a "
            f"bare number last is the price — name what is exchanged")
    if not toks:
        raise ValueError(
            f"{' '.join(tokens)}: a bare number first is the quantity — "
            f"name what is exchanged")
    concepts, heads = [], {}
    for tok in toks:
        split = _dims.split_term(tok)
        if split and split[0] in _INTERPRETED_HEADS:
            if split[0] in heads:
                raise ValueError(f"{split[0]}(...) given twice")
            heads[split[0]] = split[1]
        else:
            concepts.append(tok)
    return Parsed(qty, unit, divisible, band, tuple(concepts), heads, price)


# Dimension kinds whose values are offer *fields* today: quantities live in
# `Thing.qty` (linear, count) and time in `service`/`valid` (calendar). A
# term of these kinds beside the field would be double bookkeeping, so it is
# refused until ontodag-coupling.md §2-3 make the fields terms. Prefix and
# dominance terms (`from`, `to`, `geo`, `size`) have no field: they pass
# through and match by ontodag's computed containment.
_FIELD_KINDS = frozenset({_dims.KIND_LINEAR, _dims.KIND_COUNT,
                          _dims.KIND_CALENDAR})


def _head_kind(dag: OntoDAG, head: str) -> str | None:
    """The dimension kind a declared head belongs to, else None."""
    if head not in dag.nodes or "dimension" not in dag.nodes \
            or not dag.is_below(head, "dimension"):
        return None
    for kind in sorted(_dims.KINDS):
        if kind in dag.nodes and dag.is_below(head, kind):
            return kind
    return "dimension"


def _value_of(view: OntoDAG, name: str, kind: str) -> str | None:
    """A name's public value in a dimension of `kind`: the parameter of the
    term it (or an ancestor) hangs under — `my_home` under `geo(u2e4x)`
    yields `u2e4x`. Ontodag interprets the *name*; the CLI only carries
    the value into the term the person typed (Peter, 2026-09-12)."""
    node = view.nodes.get(name)
    if node is None:
        return None
    for item in [node, *view.get_ancestors(node)]:
        split = _dims.split_term(item.name)
        if split and _head_kind(view, split[0]) == kind:
            return split[1]
    return None


def _elaborate_terms(session: "Session", concepts, ontology: Ontology):
    """Each `head(param)` of a declared head: refuse field kinds, resolve a
    private name in parameter position to its public value, and check the
    result is vocabulary. Returns (concepts, notes)."""
    dag = ontology.dag
    out, notes = [], []
    for c in concepts:
        split = _dims.split_term(c)
        kind = _head_kind(dag, split[0]) if split else None
        if kind is None:
            out.append(c)
            continue
        head, param = split
        if kind in _FIELD_KINDS:
            raise ValueError(
                f"{c}: a quantity or time term is accepted by the grammar but "
                f"not encodable until quantities and spacetime become catalogue "
                f"terms (docs/plans/ontodag-coupling.md §2-3). Encodable "
                f"today: a bare quantity first (`10kg`), when(...), "
                f"where(...), valid(...)")
        view = session.view()
        value = _value_of(view, param, kind)
        if value is None and param in view.nodes:
            # A name is interpreted as a name or refused — never read as a
            # literal value that happens to spell the same (a place called
            # `u2e` must not become the cell `u2e`, nor `ride` a prefix).
            raise ValueError(
                f"{c}: `{param}` is a catalogue name, but nothing places it "
                f"in a {head}-kind dimension ({kind}) — `loop place {param} "
                f"LAT,LON,RADIUS` gives a place its value")
        if value is not None and value != param:
            term = f"{head}({value})"
            notes.append(f"{c} → {term}")
            c = term
        if not ontology.known(c):
            raise ValueError(
                f"{c}: not a value `{head}` accepts, and not a name the "
                f"catalogue knows in that dimension")
        out.append(c)
    return tuple(out), notes


def _bare_key(concepts) -> tuple[str, ...]:
    """The price memory's key: the sorted *non-parametric* concepts. A
    `time(...)` that changes on every offer would otherwise defeat it."""
    return tuple(sorted(c for c in concepts if _dims.split_term(c) is None))


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def reading(offer: Offer) -> str:
    """cli.md §6's direction rule, in words: what the encoded quantity
    means for this side. Printed, never acted on — matching stays exact."""
    t = offer.thing
    q = _num(t.qty)
    if t.unit == "unit":
        return f"{q}, indivisible" if not t.divisible else f"up to {q}, divisible"
    if offer.kind == GIVE:
        return f"up to {q} {t.unit}, divisible"
    return (f"{q} {t.unit} — the point; a floor (`{q}{t.unit}..`) is not "
            f"encodable yet")


# --------------------------------------------------------------------------- #
# The one renderer: the approval block *is* `show` (gate G4)
# --------------------------------------------------------------------------- #

def render_offer(offer: Offer) -> str:
    t = offer.thing
    pins = (f"catalogue {offer.ontology_root[:16] or '-'}  "
            f"registry {offer.registry_version or '-'}  "
            f"contract {offer.contract_version or '-'}  v{offer.v}")
    lines = [
        f"{offer.kind:<9}{' '.join(t.concepts)}",
        f"  maker    {offer.maker}",
        f"  quantity {_num(t.qty)} {t.unit} — {reading(offer)}",
        f"  price    {_num(offer.tokens.amount)} "
        f"({_num(offer.unit_price)}/{t.unit}, on {offer.maker}'s scale)",
        f"  service  {_iso(offer.service.start)} .. {_iso(offer.service.end)}",
        f"           local {_local(offer.service.start)} .. "
        f"{_local(offer.service.end)}",
        f"  valid    {_iso(offer.valid.start)} .. {_iso(offer.valid.end)}",
        f"           local {_local(offer.valid.start)} .. "
        f"{_local(offer.valid.end)}",
        f"  where    {offer.where.lat},{offer.where.lon} "
        f"radius {_num(offer.where.radius_m)}m",
        f"  pins     {pins}",
        f"  terms    bond {_num(offer.bond)}  oracle {offer.oracle}  "
        f"arbitrator {offer.arbitrator or '-'}",
        f"  nonce    {offer.nonce}",
        f"  offer_id {offer.offer_id}",
    ]
    return "\n".join(lines)


def _state(book: OfferRegistry, offer: Offer, now: int) -> str:
    if book.is_filled(offer.offer_id):
        return "filled"
    if book.is_withdrawn(offer.offer_id):
        return "withdrawn"
    return "open" if offer.valid.is_open_at(now) else "expired"


def _row(offer: Offer, now: int, book: OfferRegistry) -> list[str]:
    t = offer.thing
    return [offer.offer_id[:12], offer.kind, offer.maker,
            f"{_num(t.qty)} {t.unit}", " ".join(t.concepts),
            _num(offer.tokens.amount), _state(book, offer, now)]


_COLUMNS = ("id", "side", "maker", "qty", "thing", "price", "state")


def _print_table(rows: list[list[str]], args, out) -> None:
    """A table at a terminal, tab-separated lines in a pipe (odag's §7)."""
    limit = _want_limit(args, out)
    shown = rows[:limit] if limit else rows
    if _want_render(args, out):
        widths = [max(len(c), *(len(r[i]) for r in shown)) if shown else len(c)
                  for i, c in enumerate(_COLUMNS)]
        print("  ".join(c.ljust(w) for c, w in zip(_COLUMNS, widths)), file=out)
        for r in shown:
            print("  ".join(v.ljust(w) for v, w in zip(r, widths)), file=out)
    else:
        for r in shown:
            print("\t".join(r), file=out)
    if limit and len(rows) > limit:
        print(f"({len(rows) - limit} more; -n 0 shows all)", file=_err())


# --------------------------------------------------------------------------- #
# Commands: maker
# --------------------------------------------------------------------------- #

def _resolve_offer(session: Session, side: str, parsed: Parsed,
                   ontology: Ontology):
    """Every default and shorthand expanded into one Offer, plus the notes
    the approval block prints beside it. Refusals here are the loud kind."""
    now = session.now
    notes: list[str] = []
    if parsed.band:
        point = parsed.band.replace("..", "").strip() or "10kg"
        raise ValueError(
            f"{parsed.band}: bands, floors and ceilings are the grammar but "
            f"not encodable until quantities become catalogue terms "
            f"(docs/plans/ontodag-coupling.md §3). Encodable today: the point "
            f"`{point}` — declare in the direction you know")
    concepts, term_notes = _elaborate_terms(session, parsed.concepts, ontology)
    notes.extend(term_notes)
    for c in concepts:
        if not ontology.known(c):
            raise ValueError(
                f"unknown category: {c} — vocabulary fails closed (U7); "
                f"`odag put {c} PARENT` adds it to the catalogue")
    maker = session.maker

    place_name = parsed.heads.get("where") or _configured("where")
    if not place_name:
        raise ValueError(
            "no place: where(NAME) on the line, or `loop set where NAME` "
            "(NAME is a catalogue node — `loop place NAME LAT,LON,RADIUS`)")
    disc = session.place(place_name)
    notes.append(f"place {place_name}")

    when_text = parsed.heads.get("when") or _configured("when")
    service = session.named_window(when_text)
    if service is None:
        service = window(when_text, now)
    else:
        notes.append(f"when {when_text}")
    valid = validity(parsed.heads.get("valid") or _configured("valid"), now)

    # An omitted quantity is the schema's own default, not a typed `1`:
    # canonical JSON tells 1 from 1.0, and `Thing(("x",))` from the API
    # must produce the same record bytes as `give x 100` (gate G1, U2).
    thing = Thing(concepts, unit=parsed.unit, divisible=parsed.divisible) \
        if parsed.qty is None else \
        Thing(concepts, parsed.qty, parsed.unit, parsed.divisible)
    qty = thing.qty

    reused = False
    price = parsed.price
    if price is None:
        found = _last_unit_price(session, maker, side, parsed.concepts, now)
        if found is None:
            raise ValueError(
                f"no price, and no earlier {side} of "
                f"{' '.join(_bare_key(parsed.concepts))} by {maker} to reuse — "
                f"a bare number last is the price")
        unit_price, source = found
        if source.thing.unit != parsed.unit:
            raise ValueError(
                f"the last {side} of {' '.join(_bare_key(parsed.concepts))} "
                f"was priced per {source.thing.unit}, this one is per "
                f"{parsed.unit} — type the price")
        price = unit_price * qty
        reused = True
        age = now - source.nonce // 1000
        notes.append(
            f"price {_num(price)} reused: unit price {_num(unit_price)}/"
            f"{source.thing.unit} from offer {source.offer_id[:12]} "
            f"({_age(age)} ago)")

    nonce = now * 1000 + sum(1 for o in session.book.offers(include_filled=True)
                             if o.maker == maker)
    make = give if side == GIVE else want
    offer = make(maker, thing, price, service=service, where=disc,
                 valid=valid, nonce=nonce, **ontology.pins)
    return offer, notes, reused


def _age(seconds: int) -> str:
    if seconds < 3600:
        return f"{max(seconds, 0) // 60}m"
    if seconds < 86_400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86_400}d"


def _last_unit_price(session: Session, maker: str, side: str, concepts,
                     now: int):
    """The maker's own latest offer with the same side and bare categories
    — live, filled or withdrawn — by nonce. The book is the memory: no
    price file, nothing from peers' scales."""
    key = _bare_key(concepts)
    best = None
    for o in session.book.offers(include_filled=True):
        if o.maker != maker or o.kind != side:
            continue
        if _bare_key(o.thing.concepts) != key:
            continue
        if best is None or o.nonce > best.nonce:
            best = o
    if best is None:
        return None
    return best.unit_price, best


def _confirm(reused: bool, out) -> bool:
    """cli.md §7 plus the 2026-09-12 ruling: `auto` asks at a terminal,
    proceeds in a batch unless a price was reused; `on` always asks (via
    the controlling terminal when stdin is the script); `off` never."""
    mode = _configured("confirm").strip().lower()
    if mode == "off":
        return True
    interactive = _isatty(sys.stdin)
    if mode == "auto" and not interactive:
        if reused:
            raise ValueError(
                "refused: the price was reused from an earlier offer and "
                "nobody saw it — in a batch, type the price, or "
                "`set confirm off` to accept reused prices")
        return True
    if mode not in ("auto", "on"):
        raise ValueError(f"confirm must be auto, on or off, not {mode!r}")
    try:
        if interactive:
            answer = input("publish? [y/N] ")
        else:
            with open("/dev/tty", "r+", encoding="utf-8") as tty:
                tty.write("publish? [y/N] ")
                tty.flush()
                answer = tty.readline()
    except (EOFError, OSError):
        raise ValueError(
            "confirm on: no terminal to ask on — `set confirm off` for "
            "unattended runs") from None
    return answer.strip().lower() in ("y", "yes")


def _publish(args, session: Session, out, side: str) -> int:
    parsed = parse_offer_tokens(args.tokens)
    ontology = session.catalogue
    offer, notes, reused = _resolve_offer(session, side, parsed, ontology)
    print(render_offer(offer), file=out)
    for note in notes:
        print(f"  note     {note}", file=out)
    if not _confirm(reused, out):
        print("not published", file=_err())
        return 1
    oid = session.book.publish(offer)
    signer = _configured("bee_signer")
    if signer:
        try:
            from .sigs import maker_address, sign_offer
            if maker_address(signer) == offer.maker:
                session.book.attach_signature(oid, sign_offer(offer, signer))
        except Exception:  # noqa: BLE001 — signing is the optional layer
            pass
    session.book.commit()
    # By exception to odag's silent-on-success rule: publishing is a
    # commitment, and the id is what `withdraw` needs.
    print(oid, file=out)
    return 0


def cmd_give(args, session, out):
    return _publish(args, session, out, GIVE)


def cmd_want(args, session, out):
    return _publish(args, session, out, WANT)


def _resolve_id(session: Session, prefix: str, *, mine_only: bool) -> str:
    book = session.book if mine_only else session.fold()
    matches = sorted({o.offer_id for o in book.offers(include_filled=True)
                      if o.offer_id.startswith(prefix)
                      and (not mine_only or o.maker == session.maker)})
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"{prefix}: no such offer"
                         + (" of yours" if mine_only else ""))
    raise ValueError(f"{prefix}: ambiguous — "
                     + ", ".join(m[:16] for m in matches))


def cmd_withdraw(args, session, out):
    oid = _resolve_id(session, args.id, mine_only=True)
    if session.book.is_filled(oid):
        raise ValueError(f"{oid[:12]} is filled: a cleared leg is an obligation")
    if session.book.is_withdrawn(oid):
        raise ValueError(f"{oid[:12]} is already withdrawn")
    session.book.withdraw(oid)
    session.book.commit()
    return 0


def cmd_mine(args, session, out):
    now = session.now
    rows = [_row(o, now, session.book)
            for o in session.book.offers(include_filled=True)
            if o.maker == session.maker]
    rows.sort(key=lambda r: r[0])
    _print_table(rows, args, out)
    return 0


def cmd_place(args, session, out):
    """The dated bridge (cli.md §4, §11.1): a place node with its disc as
    metadata, written to the personal layer. Deleted the day odag accepts
    `geo(LAT,LON,R)` as input vocabulary."""
    parts = [p.strip() for p in args.coords.split(",")]
    if len(parts) != 3:
        raise ValueError("coordinates are LAT,LON,RADIUS (e.g. 46.05,14.50,5km)")
    lat, lon = float(parts[0]), float(parts[1])
    disc = GeoDisc(lat, lon, radius_m(parts[2]))
    personal = session.personal_session
    dag = personal.dag
    if not ("geo" in dag.nodes and "prefix-dimension" in dag.nodes
            and dag.is_below("geo", "prefix-dimension")):
        # The cell edge is what lets ontodag interpret the name (`my_home`
        # under `geo(u2e4x)` is how `from(my_home)` gets its value), and
        # `geo` comes from the prelude — adopted by merge, idempotent,
        # canonical, exactly what `odag prelude` does.
        from ontodag.prelude import apply as apply_prelude
        apply_prelude(dag)
        print("loop: adopted ontodag's prelude into the personal store "
              f"({personal.describe()}) so places hang under geo cells",
              file=_err())
    dag.put(args.name, [f"geo({cell_for(disc)})"])
    dag.nodes[args.name].metadata["disc"] = [lat, lon, disc.radius_m]
    personal.save()
    return 0


# --------------------------------------------------------------------------- #
# Commands: anyone reading
# --------------------------------------------------------------------------- #

def cmd_offers(args, session, out):
    now = session.now
    fold = session.fold()
    rows = []
    ontology = session.catalogue if args.categories else None
    for o in fold.offers(now=now):
        if ontology is not None and \
                not ontology.satisfies(o.thing.concepts, args.categories):
            continue
        rows.append(_row(o, now, fold))
    rows.sort(key=lambda r: r[0])
    _print_table(rows, args, out)
    return 0


def cmd_show(args, session, out):
    oid = _resolve_id(session, args.id, mine_only=False)
    fold = session.fold()
    offer = fold.get(oid)
    print(render_offer(offer), file=out)
    print(f"  state    {_state(fold, offer, session.now)}", file=out)
    return 0


def _matches(session: Session):
    now = session.now
    fold = session.fold()
    return list(candidate_matches(list(fold.offers(now=now)),
                                  session.catalogue, now=now))


def cmd_matches(args, session, out):
    rows = [f"{m.giver} gives {' '.join(m.give.thing.concepts)} to "
            f"{m.receiver} (wants {' '.join(m.want.thing.concepts)}) "
            f"rate {m.rate:.4g}  {m.give.offer_id[:12]}>{m.want.offer_id[:12]}"
            for m in _matches(session)]
    rows.sort()
    for r in rows:
        print(r, file=out)
    return 0 if rows else 1


def cmd_status(args, session, out):
    print(f"book = {_book_spec()}", file=out)
    book = session.book
    print(f"book root = {book.store.root or '(empty)'}", file=out)
    every = list(book.offers(include_filled=True))
    print(f"offers = {len(every)} "
          f"(filled {sum(book.is_filled(o.offer_id) for o in every)}, "
          f"withdrawn {sum(book.is_withdrawn(o.offer_id) for o in every)})",
          file=out)
    print(f"catalogue = {session.catalogue_session.describe()}", file=out)
    ontology = session.catalogue
    print(f"catalogue root = {ontology.root or '(unpinned)'}", file=out)
    print(f"categories = {len(ontology.dag.nodes)}", file=out)
    print(f"peers = {', '.join(_peer_specs()) or '(none)'}", file=out)
    for key in ("maker", "where", "when", "valid", "confirm"):
        print(f"{key} = {_configured(key) or '(unset)'}", file=out)
    print(f"now = {_iso(session.now)}"
          + ("" if _configured("now") else " (wall clock)"), file=out)
    return 0


# --------------------------------------------------------------------------- #
# Commands: solver and clearing
# --------------------------------------------------------------------------- #

def _print_loop(loop: Loop, fold: OfferRegistry, out, *, prefix="") -> None:
    print(f"{prefix}loop {loop.loop_id[:16]}… surplus {100 * loop.surplus:.2f}%",
          file=out)
    for m in loop.matches:
        print(f"  {m.giver} gives {' '.join(m.give.thing.concepts)} to "
              f"{m.receiver} (rate {m.rate:.4g})", file=out)


def cmd_loops(args, session, out):
    """Find on a pinned snapshot, print, never clear. Exit 1 when nothing
    is profitable, so `loop loops && loop clear` reads naturally."""
    fold = session.fold()
    agent = SolverAgent(fold, session.catalogue, clearing=None,
                        solver_id="loop-cli", min_surplus=0.0)
    root, loops = agent.find_loops(now=session.now)
    for loop in loops:
        _print_loop(loop, fold, out)
    return 0 if loops else 1


def cmd_clear(args, session, out):
    """Run the clearing house locally: MockClearing over the fold, fills
    committed to my book. With peers, my book first absorbs the fold — a
    clearing book legitimately contains what it cleared on (P1 §1)."""
    now = session.now
    if _peer_specs():
        session.book.absorb(session.fold())
        session.book.commit()
        print("book re-based on the fold", file=_err())
    book = session.book
    ontology = session.catalogue
    agent = SolverAgent(book, ontology,
                        MockClearing(book, ontology, clock=lambda: now),
                        solver_id="loop-cli", min_surplus=0.0)
    receipts = agent.step(now=now)
    cleared = 0
    for r in receipts:
        if r.accepted:
            cleared += 1
            rec = book.store.get(f"loop/{r.loop_id}")
            print(f"cleared {r.loop_id[:16]}… surplus "
                  f"{100 * rec['surplus']:.2f}%", file=out)
            for leg in rec["legs"]:
                a, b = book.get(leg["give"]), book.get(leg["want"])
                print(f"  {a.maker} gives {' '.join(a.thing.concepts)} to "
                      f"{b.maker} (rate {leg['rate']:.4g})", file=out)
        else:
            print(f"rejected {r.loop_id[:16]}…: {r.reason}", file=_err())
    if cleared:
        print(f"book root {book.store.root}", file=out)
    return 0 if cleared else 1


# --------------------------------------------------------------------------- #
# Commands: plumbing
# --------------------------------------------------------------------------- #

def cmd_export(args, session, out):
    for o in session.book.offers(include_filled=True):
        print(json.dumps(o.to_record(), sort_keys=True,
                         separators=(",", ":")), file=out)
    return 0


def cmd_import(args, session, out):
    stream = open(args.file, encoding="utf-8") if args.file else sys.stdin
    try:
        n = 0
        for line in stream:
            line = line.strip()
            if not line:
                continue
            session.book.publish(Offer.from_record(json.loads(line)))
            n += 1
    finally:
        if args.file:
            stream.close()
    if n:
        session.book.commit()
    print(n, file=_err())
    return 0


def _shown_setting(key: str) -> str:
    value = _configured(key) if key != "book" else _book_spec()
    if _SETTINGS[key].secret and value:
        return f"<hidden, ends {value[-4:]}>"
    return value


def cmd_set(args, session, out):
    """No key: every setting. Key: that one. Key and value: change it,
    durably. Unknown keys are errors — fails closed; no aliases hide here."""
    if not args.key:
        for key in sorted(_SETTINGS):
            print(f"{key} = {_shown_setting(key)}", file=out)
        return 0
    if args.key not in _SETTINGS:
        raise ValueError(f"unknown setting: {args.key} "
                         f"(known: {', '.join(sorted(_SETTINGS))})")
    if args.value is None:
        print(f"{args.key} = {_shown_setting(args.key)}", file=out)
        return 0
    value = args.value
    # Validate now, not at the next command that reads it.
    if args.key == "confirm" and value.lower() not in ("auto", "on", "off"):
        raise ValueError("confirm is auto, on or off")
    if args.key == "now":
        parse_now(value)
    if args.key == "valid":
        validity(value, 0)
    if args.key == "when":
        window(value, int(_time.time()))
    if args.key == "limit":
        _want_limit(argparse.Namespace(limit=value), out)
    if args.key in ("book", "peers"):
        for spec in value.split(","):
            if spec.strip() and not spec.strip().startswith(("rs:", "swarm:")):
                raise ValueError(f"{spec.strip()}: a book is rs:PATH or "
                                 f"swarm:TOPIC[@OWNER]")
    cfg = _read_config()
    cfg[args.key] = value
    _write_config(cfg)
    if args.key == "book":
        session._book = None
    if args.key == "catalogue":
        session._catalogue = session._personal = None
    return 0


HELP_TEXT = """\
loop — the loopmarket command line (docs/plans/cli.md)

  loop give  [QTY] CATEGORY|TERM... [PRICE]   I give this, priced on my scale
  loop want  [QTY] CATEGORY|TERM... [PRICE]   I want this, priced on my scale
  loop withdraw ID           tombstone one of my offers (id or unique prefix)
  loop mine                  my offers, all states
  loop place NAME LAT,LON,R  a place node with coordinates (temporary bridge)
  loop offers [CATEGORY...]  open offers in the fold (filtered by satisfies)
  loop show ID               one offer, fully — the approval block
  loop matches               every feasible handoff in the fold
  loop loops                 profitable loops on a snapshot (exit 1: none)
  loop clear                 run clearing locally over the fold (exit 1: none)
  loop status                roots, counts, settings in force
  loop set [KEY [VALUE]]     show / change a durable setting
  loop export | import [FILE]   offers as JSON lines of canonical records
  loop help | --version

Grammar (ontodag's, plus two conventions): a bare word is a category; a
term is head(param) in ontodag's spelling — quote the parentheses in a
shell; a bare number FIRST is the quantity (10kg = up to 10 kg divisible,
3 = three indivisible), a bare number LAST is the price. An omitted price
is your last unit price for the same thing, scaled, and marked.
Interpreted heads: when(WINDOW) where(PLACE) valid(DURATION|WINDOW).
Time: now, today, tomorrow, +90d, -2h, ISO dates, A..B.

  loop give 10kg apple 100
  loop want ride 'where(my_home)' 'when(today..+7d)' 5
  loop give piano-lesson 'valid(2h)'

Settings (flag > $LOOP_* > ~/.loopmarket/config > ~/.ontodag/config > default):
"""


def cmd_help(args, session, out):
    out.write(HELP_TEXT)
    for key in sorted(_SETTINGS):
        s = _SETTINGS[key]
        out.write(f"  {key:<11}{s.flag:<18}{s.help}\n")
    return 0


# --------------------------------------------------------------------------- #
# Parser and dispatch
# --------------------------------------------------------------------------- #

class _Parser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if not message:
            return
        stream = _err() if file in (None, sys.stderr) else _out()
        stream.write(message)


def _add_output_flags(p):
    group = p.add_mutually_exclusive_group()
    group.add_argument("--render", dest="render_mode", action="store_const",
                       const=True)
    group.add_argument("--raw", dest="render_mode", action="store_const",
                       const=False)
    p.set_defaults(render_mode=None)
    p.add_argument("-n", "--limit", metavar="N")
    p.add_argument("-o", "--output", metavar="FILE",
                   help="write output to FILE (the REPL has no redirect)")


def build_parser():
    parser = _Parser(prog="loop", add_help=False)
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    for verb, fn in (("give", cmd_give), ("want", cmd_want)):
        p = sub.add_parser(verb, add_help=False)
        p.add_argument("tokens", nargs=argparse.REMAINDER)
        p.set_defaults(func=fn)

    p = sub.add_parser("withdraw", add_help=False)
    p.add_argument("id")
    p.set_defaults(func=cmd_withdraw)

    p = sub.add_parser("mine", add_help=False)
    _add_output_flags(p)
    p.set_defaults(func=cmd_mine)

    p = sub.add_parser("place", add_help=False)
    p.add_argument("name")
    p.add_argument("coords")
    p.set_defaults(func=cmd_place)

    p = sub.add_parser("offers", add_help=False)
    p.add_argument("categories", nargs="*")
    _add_output_flags(p)
    p.set_defaults(func=cmd_offers)

    p = sub.add_parser("show", add_help=False)
    p.add_argument("id")
    _add_output_flags(p)
    p.set_defaults(func=cmd_show)

    for name, fn in (("matches", cmd_matches), ("loops", cmd_loops),
                     ("status", cmd_status), ("export", cmd_export)):
        p = sub.add_parser(name, add_help=False)
        _add_output_flags(p)
        p.set_defaults(func=fn)

    p = sub.add_parser("clear", add_help=False)
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser("import", add_help=False)
    p.add_argument("file", nargs="?")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("set", add_help=False)
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("help", add_help=False)
    p.set_defaults(func=cmd_help)
    return parser


PARSER = build_parser()


def dispatch(argv, session, out=None, err=None) -> int:
    """Parse one command line and run it; a process-style exit code.
    `out`/`err` let an embedder (and the tests) capture both streams."""
    tokens = [var.set(stream) for var, stream in
              ((_OUT, out), (_ERR, err)) if stream is not None]
    try:
        return _dispatch(argv, session)
    finally:
        for token in reversed(tokens):
            token.var.reset(token)


def _dispatch(argv, session) -> int:
    try:
        args = PARSER.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 0
    out = _out()
    handle = None
    outpath = getattr(args, "output", None)
    try:
        if outpath:
            handle = open(outpath, "w", encoding="utf-8")
            out = handle
        return args.func(args, session, out) or 0
    except (ValueError, KeyError, OSError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(f"loop: {message}", file=_err())
        return 1
    finally:
        if handle is not None:
            handle.close()


def run_stream(session, stream, interactive: bool) -> int:
    """Batch on stdin, or a prompt on a tty (odag's mode). The exit code is
    the last command's, so a script's final `loops`/`clear` is a predicate."""
    code = 0
    if interactive:
        print(f"loop {__version__} - type help for help")
    while True:
        if interactive:
            try:
                line = input("> ")
            except EOFError:
                print()
                break
        else:
            line = stream.readline()
            if not line:
                break
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            print(f"loop: {exc}", file=_err())
            code = 1
            continue
        if tokens[0] in ("quit", "exit"):
            break
        code = dispatch(tokens, session)
    return code


_GLOBAL_FLAGS = {
    "-f": "book", "--book": "book", "--catalogue": "catalogue",
    "--peer": "peers", "--peers": "peers", "--maker": "maker",
    "--where": "where", "--when": "when", "--valid": "valid",
    "--now": "now", "--confirm": "confirm", "-n": "limit", "--limit": "limit",
    "--bee-api": "bee_api", "--bee-batch": "bee_batch",
    "--bee-signer": "bee_signer",
}


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    _OVERRIDES.clear()
    while argv and (argv[0] in _GLOBAL_FLAGS or argv[0] in ("--raw", "--render")):
        if argv[0] in ("--raw", "--render"):
            _OVERRIDES["render"] = "on" if argv[0] == "--render" else "off"
            argv = argv[1:]
            continue
        if len(argv) < 2:
            print(f"loop: {argv[0]} requires a value", file=_err())
            sys.exit(2)
        _OVERRIDES[_GLOBAL_FLAGS[argv[0]]] = argv[1]
        argv = argv[2:]
    if argv and argv[0] in ("-V", "--version"):
        print(__version__)
        sys.exit(0)
    if argv and argv[0] in ("-h", "--help"):
        cmd_help(None, None, sys.stdout)
        sys.exit(0)
    session = Session()
    if not argv:
        sys.exit(run_stream(session, sys.stdin, interactive=sys.stdin.isatty()))
    sys.exit(dispatch(argv, session))


if __name__ == "__main__":
    main()
