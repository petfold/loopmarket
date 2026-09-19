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
from .graph import Circulation, Loop
from .matching import candidate_matches
from .ontology import Ontology
from .registry import OfferRegistry
from .schema import GIVE, WANT, Offer, Parts, Thing, TimeWindow, give, q, want
from .solver.agent import SolverAgent
from .spacetime import cell_for_coords


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
        "swarm:TOPIC@OWNER follows someone else's feed); books you trust "
        "— the announced books come from `registry`"),
    "registry": _Setting(
        "LOOP_REGISTRY", "", "--registry SPEC",
        "the announcement channel: chain:RPC_URL@CONTRACT (the "
        "LoopBookRegistry on the EVM chain Swarm settles on), file:PATH "
        "(sessions on one machine), memory:; several comma-separated are "
        "one channel, the newer chain last; every announced book is folded "
        "into every answer, as its announced owner's"),
    "beat": _Setting(
        "LOOP_BEAT", "", "--beat SPEC",
        "the clearing contract: chain:RPC_URL@CONTRACT (BeatClearing); "
        "`propose` posts each cleared loop as a beat, `challenge BEAT` "
        "re-verifies one from its record, `finalize BEAT` records its fills "
        "after the window"),
    "auction": _Setting(
        "LOOP_AUCTION", "", "--auction SPEC",
        "the sealed-proposal beat: chain:RPC_URL@CONTRACT (SealedBeat) or "
        "memory:; `commit` seals this session's loops for the current beat, "
        "`reveal` opens them, `outcome BEAT` derives a closed beat's winners "
        "and posts them to `beat`"),
    "maker": _Setting(
        "LOOP_MAKER", "", "--maker NAME",
        "my identity; the signer's address when bee_signer is set and the "
        "sig extra is installed"),
    "terms": _Setting(
        "LOOP_TERMS", "", "--terms 'TERM ...'",
        "terms added to every offer whose line does not name that head, "
        "e.g. 'home ..+90d'; unset: anywhere, any time"),
    "valid": _Setting(
        "LOOP_VALID", "30d", "--valid DURATION",
        "how long my offers stand (a duration, or an absolute window)"),
    "bond": _Setting(
        "LOOP_BOND", "", "--bond DEPOSIT",
        "the deposit I hold against my performance, on every give I publish: "
        "an amount on my scale, deposited as default_asset at my price for "
        "it, or `QTY[UNIT] CATEGORY... VALUE` — the asset by the grammar "
        "(quantity first), its worth to me on my scale last (v5; a "
        "declaration until the escrow of `escrow` holds it)"),
    "default_asset": _Setting(
        "LOOP_DEFAULT_ASSET", "xdai xDAI 1", "--default-asset 'CATEGORY UNIT PRICE'",
        "the asset a bare-number `bond` deposits and a `require_point` with "
        "no `require_accepts` accepts, with its price per unit on my scale: "
        "the configured chain's gas token — xDAI at 1 while Swarm settles on "
        "Gnosis (a CLI default; the record names it explicitly, the protocol "
        "names no asset)"),
    "escrow": _Setting(
        "LOOP_ESCROW", "", "--escrow SPEC",
        "the escrow contract holding my deposit: chain:RPC_URL@CONTRACT "
        "(LoopEscrow; the record names the address); `deposit [ID]` funds "
        "a give's declared bond there (empty: a declaration only)"),
    "escrow_claim": _Setting(
        "LOOP_ESCROW_CLAIM", "7d", "--escrow-claim DURATION",
        "how long after a leg's handover window a claim on its deposit may "
        "be opened before the reservation returns to the giver by itself"),
    "require_point": _Setting(
        "LOOP_REQUIRE_POINT", "", "--require-point AMOUNT",
        "my neutral point on a no-show, on my scale: what makes me whole — "
        "payments to the leg's other counterparties, the substitute, the "
        "inconvenience; a counterparty must reserve a deposit covering it "
        "(admissibility by declaration, v5) or the leg is never matched"),
    "require_cancel": _Setting(
        "LOOP_REQUIRE_CANCEL", "", "--require-cancel AMOUNT",
        "what a cancellation costs at the far end of the ladder (at most "
        "require_point); the ladder rises from it to require_point over "
        "the lead to the leg's time term, in the shape of `ladder`"),
    "ladder": _Setting(
        "LOOP_LADDER", "linear", "--ladder SHAPE",
        "the cancellation ladder's shape over the lead at posting: linear "
        "(default), late (flat, then rising over the last quarter), early "
        "(rising over the first quarter, then flat), flat (a step at the "
        "window); the record carries only the points"),
    "require_accepts": _Setting(
        "LOOP_REQUIRE_ACCEPTS", "", "--require-accepts TABLE",
        "the durable assets I accept as compensation, with my price per "
        "unit on my scale: `CATEGORY... UNIT PRICE; ...` (e.g. "
        "`btc sat 1/2000; stablecoin-eur EUR 1`)"),
    "require_escrows": _Setting(
        "LOOP_REQUIRE_ESCROWS", "", "--require-escrows KINDS",
        "escrow kinds I accept for a counterparty's deposit (e.g. contract); "
        "empty: any"),
    "maker": _Setting(
        "LOOP_MAKER", "", "--maker NAME",
        "my identity; the signer's address when bee_signer is set and the "
        "sig extra is installed"),
    "terms": _Setting(
        "LOOP_TERMS", "", "--terms 'TERM ...'",
        "terms added to every offer whose line does not name that head, "
        "e.g. 'home ..+90d'; unset: anywhere, any time"),
    "valid": _Setting(
        "LOOP_VALID", "30d", "--valid DURATION",
        "how long my offers stand (a duration, or an absolute window)"),
    "bond": _Setting(
        "LOOP_BOND", "", "--bond AMOUNT",
        "the bond I declare on every offer I publish (in the bond's asset; "
        "a declaration until P3's escrow holds it)"),
    "require_bond": _Setting(
        "LOOP_REQUIRE_BOND", "", "--require-bond AMOUNT",
        "the least bond a counterparty must reserve for a leg through my "
        "offer — admissibility by declaration (v5 record, 2026-09-18); "
        "unmet, the leg is never matched; on a no-show it is mine"),
    "require_cancel": _Setting(
        "LOOP_REQUIRE_CANCEL", "", "--require-cancel AMOUNT",
        "what a counterparty owes me instead if it cancels the leg before "
        "its window (at most require_bond); a late ride cancels and re-offers"),
    "interval": _Setting(
        "LOOP_INTERVAL", "30s", "--interval DURATION",
        "how often `watch` polls the fold"),
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


# --------------------------------------------------------------------------- #
# The session: book, catalogue, personal names layer, clock, identity
# --------------------------------------------------------------------------- #

# The one head the CLI still interprets onto a field: `valid` is a property
# of the record (while the offer stands), read by the book against the
# clock, never by the catalogue against another offer. Since the v3 record
# (2026-09-12) `when`/`where` are ordinary catalogue terms like any other.
_INTERPRETED_HEADS = ("valid",)


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


def _addressing_of(registry: OfferRegistry) -> str:
    """The scheme the book's roots are in — `sha256` for a directory or
    memory store, `swarm` for a book on Swarm or a Swarm-addressed mirror.
    recordstore names it privately for proof envelopes; the same answer is
    what a fold must be built under (a public accessor is asked upstream)."""
    try:
        from recordstore.recordstore import _addressing_name
        return _addressing_name(registry.store.blobs)
    except Exception:                       # noqa: BLE001 — an unknown store: sha256, the default
        return "sha256"


def _fold_blobs(book: OfferRegistry):
    """The bytes store a fold is computed in: the *book's* addressing, so the
    fold's root is the root the book has once it absorbs the fold — equal
    content, equal reference — and a proposal solved on the fold pins a
    root the clearing book and the chain resolve. A memory store is sha256
    only, so a Swarm-addressed book folds in a scratch directory under
    Swarm addressing (found live 2026-09-18: a sealed proposal pinning the
    memory fold's sha256 root was "solved against another root" beside the
    Swarm clearing book's BMT root of the same content)."""
    from recordstore import DirBytesStore, MemoryBytesStore
    if _addressing_of(book) == "swarm":
        import tempfile
        return DirBytesStore(tempfile.mkdtemp(prefix="loop-fold-"), addressing="swarm")
    return MemoryBytesStore()


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
        """My book plus every announced book plus every peer, as one
        read-only registry — the read path (P1 §2, T14).

        The announced books come from the `registry` channel with their
        owners, so they fold through `Aggregator` under the U8 admission
        rules: each book is read as *its announced owner's*, and speech the
        owner may not make is refused with an attributed rejection. This
        is the solver-self-fold: no aggregator's manifest is trusted, the
        fold is recomputed from the announced set and the makers' own
        books. `peers` are books you trust by spec, without an owner: a
        plain OR-set union (`absorb`) — the shared dev/demo shape. Then the
        U11 check."""
        specs, registry = _peer_specs(), _configured("registry")
        if not specs and not registry:
            return self.book
        from recordstore import MemoryBytesStore, RecordStore

        folded = OfferRegistry(RecordStore(_fold_blobs(self.book)))
        folded.absorb(self.book)
        if registry:
            from .federation import Aggregator
            blobs = MemoryBytesStore()
            agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="loop-cli")
            for ann in self.announcements.announced():
                try:
                    peer = _open_book(ann.spec())
                except Exception as exc:                # the maker's postage, not our omission
                    print(f"loop: {ann.owner}: {exc}", file=_err())
                    continue
                if ann.spec() == _book_spec() or ann.spec() == \
                        f"{_book_spec()}@{ann.owner}":
                    continue                            # my own book is already in
                staged = OfferRegistry(RecordStore(blobs))
                staged.absorb(peer)
                staged.commit()
                agg.announce(ann.owner, staged.store, role=ann.role)
            manifest = agg.fold()
            if manifest.book_root:
                folded.absorb(OfferRegistry(RecordStore.at(manifest.book_root, blobs)))
        for spec in specs:
            folded.absorb(_open_book(spec))
        folded.commit()
        folded.verify_loop_atomicity()
        return folded

    @property
    def announcements(self):
        """The announcement channel named by `registry` (announce.py)."""
        from .announce import open_announcements
        spec = _configured("registry")
        if not spec:
            raise ValueError(
                "no registry: `loop set registry chain:RPC_URL@CONTRACT` (or "
                "file:PATH for sessions on one machine)")
        return open_announcements(spec, key=_configured("bee_signer") or None)

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
        """Gate G5's tripwire: the head this CLI interprets onto a field
        (`valid`) must not be a dimension head the loaded catalogue
        declares — it would silently be shadowed."""
        if "dimension" not in dag.nodes:
            return
        for head in _INTERPRETED_HEADS:
            if head in dag.nodes and dag.is_below(head, "dimension"):
                raise ValueError(
                    f"the catalogue declares `{head}` as a dimension, but "
                    f"`loop` interprets {head}(...) onto the offer's validity "
                    f"field (docs/plans/P1-spacetime-terms.md §2); refusing "
                    f"rather than shadowing it")

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


# --------------------------------------------------------------------------- #
# Parsing an offer line: ontodag's grammar plus the two conventions
# --------------------------------------------------------------------------- #

#: The quantity token (cli.md §6, v4 since 2026-09-14): `[MIN..]QTY[UNIT][:STEP]`.
#: `10kg` — up to 10 kg, divisible; `3` — three, indivisible; `1000:1` — a
#: thousand by the piece; `50kg..100kg:25` — a hundred kilos in 25 kg sacks,
#: fifty at least (the give-side floor). The colon is the one new symbol:
#: `/` is ontodag's rational (`1/2kg` is half a kilo), `x` its tuple.
_NUM = r"\d+(?:\.\d+)?"
_QTY_RE = re.compile(rf"^({_NUM})([A-Za-z][A-Za-z0-9]*)?(?::({_NUM}))?$")
_BAND_RE = re.compile(
    rf"^({_NUM}(?:[A-Za-z][A-Za-z0-9]*)?)?\.\."
    rf"({_NUM}(?:[A-Za-z][A-Za-z0-9]*)?)?(?::({_NUM}))?$")
_PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _number(text: str):
    """A typed number, exact (U9): a whole number an int, a decimal the
    rational it spells (`10.5` → 21/2), so `give apple 100` and
    `give(..., 100)` — or `10.5` and `give(..., 10.5)` — produce the same
    v4 record bytes (gate G1, U2)."""
    return int(text) if "." not in text else Fraction(text)

Parsed = namedtuple("Parsed", "qty unit divisible band concepts heads price step min",
                    defaults=(None, 0))
Composed = namedtuple("Composed", "parts price valid", defaults=(None,))

#: The part separator of a composed want (cli.md §13, confirmed by Peter
#: 2026-09-12): the third loopmarket-only convention, want side only. A
#: token, not a word — no category is shadowed, and `+2h` inside when(...)
#: is a different token.
PART_SEP = "+"


def parse_want_line(tokens: list[str]) -> "Parsed | Composed":
    """A `want` line: one thing, or parts separated by `+` with one price
    last for the lot. Each part reads as a want line without its price
    (a bare number first is that part's quantity); parts carry no price
    (P2-loop-selection.md §10 pays once) and no validity of their own."""
    toks = _join_terms(list(tokens))
    if PART_SEP not in toks:
        return parse_offer_tokens(toks)
    price = None
    if toks and _PRICE_RE.match(toks[-1]):
        price = _number(toks.pop())
    # the composed want's one validity: a trailing `valid(...)`, after the
    # last part and before the price — where `line_for` writes it; inside a
    # part it is refused (a part has no validity of its own)
    valid = None
    if toks and toks[-1].startswith("valid(") and toks[-1].endswith(")"):
        valid = toks.pop()[len("valid("):-1]
    parts, current = [], []
    for tok in toks + [PART_SEP]:
        if tok == PART_SEP:
            if not current:
                raise ValueError(
                    f"{' '.join(tokens)}: an empty part around `{PART_SEP}` — "
                    f"each part names what is wanted")
            parts.append(parse_part_tokens(current))
            current = []
        else:
            current.append(tok)
    return Composed(tuple(parts), price, valid)


def parse_part_tokens(tokens: list[str]) -> Parsed:
    """One part of a composed want: a want line with no price and no
    validity (the composed want has one of each)."""
    parsed = parse_offer_tokens(tokens)
    if parsed.price is not None:
        raise ValueError(
            f"{' '.join(tokens)}: parts carry no prices — one price, last on "
            f"the line, for the whole (docs/plans/P2-loop-selection.md §10 "
            f"pays once; clearing splits)")
    if "valid" in parsed.heads:
        raise ValueError(
            f"{' '.join(tokens)}: a part has no validity of its own — the "
            f"composed want's is the `valid` setting (or --valid)")
    return parsed


def _join_terms(tokens: list[str]) -> list[str]:
    """An operator's argument may be a conjunction —
    `transport(small-item weight(..8kg))` — and the line splits on spaces,
    so tokens are rejoined while a parenthesis is open (the same line
    quoted, `'transport(small-item weight(..8kg))'`, arrives whole). The
    catalogue then spells it canonically (`_canonical`)."""
    out, depth, cur = [], 0, ""
    for tok in tokens:
        cur = f"{cur} {tok}" if depth else tok
        depth += tok.count("(") - tok.count(")")
        if depth <= 0:
            out.append(cur)
            cur, depth = "", 0
    if cur:
        raise ValueError(f"{cur}: unbalanced parentheses")
    return out


def parse_offer_tokens(tokens: list[str]) -> Parsed:
    """`[10kg] CATEGORY|TERM ... [PRICE]` → the pieces, nothing resolved.

    Every token that is neither convention is passed through as written:
    a bare word is a category, `head(param)` is a term, and the three
    interpreted heads are separated so the caller can map them onto the
    offer's fields. Band spellings in quantity position are *accepted*
    here and refused at publish (gate G6) — they are the grammar."""
    toks = _join_terms(list(tokens))
    if not toks:
        raise ValueError("what? — give/want [QUANTITY] CATEGORY... [PRICE]")
    if PART_SEP in toks:
        raise ValueError(
            f"`{PART_SEP}` composes parts of a *want* only (docs/plans/cli.md "
            f"§13): a give of several things that go together is one give of "
            f"one thing — the kit is a category")
    qty, unit, divisible, band, step, floor = None, "unit", False, None, None, 0
    m = _QTY_RE.match(toks[0])
    b = _BAND_RE.match(toks[0])
    if b and toks[0] != "..":
        band = toks.pop(0)
        low, high, s = b.groups()
        if low and high:                 # `MIN..QTY[UNIT][:STEP]`: a floor and a quantity
            hm, lm = _QTY_RE.match(high), _QTY_RE.match(low)
            if hm and lm and (lm.group(2) or "unit") == (hm.group(2) or "unit"):
                qty, unit = _number(hm.group(1)), hm.group(2) or "unit"
                floor = _number(lm.group(1))
                step = _number(s) if s else (0 if hm.group(2) else None)
                divisible = q(step if step is not None else qty) != q(qty)
                band = None
    elif m:
        qty = _number(m.group(1))
        unit = m.group(2) or "unit"
        step = _number(m.group(3)) if m.group(3) else (0 if m.group(2) else None)
        divisible = q(step if step is not None else qty) != q(qty)
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
    return Parsed(qty, unit, divisible, band, tuple(concepts), heads, price, step, floor)


# Dimension kinds whose values are offer *fields* today: quantities live in
# `Thing.qty` (linear, count). A term of these kinds beside the field would
# be double bookkeeping, so it is refused until ontodag-coupling.md §3 makes
# quantities terms. Every other kind passes through into the conjunction:
# prefix (places), calendar (times — relative spellings elaborated to fixed
# UTC on the way), dominance.
_FIELD_KINDS = frozenset({_dims.KIND_LINEAR, _dims.KIND_COUNT})


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
    """A *private* name's public value in a dimension of `kind`: the
    parameter of the term it (or an ancestor) hangs under — `my_home`
    under `geo(u2e4x)` yields `u2e4x`. Used only for names the pinned
    catalogue does not hold (the personal layer's places): the same-root
    constraint means a counterparty can interpret `from(my_home)` only if
    `my_home` is in the root the offer pins, so a private place publishes
    as its cell and the name stays private (`cli.md` §12). A catalogue
    name needs none of this since ontodag #15: it stands as spelled."""
    node = view.nodes.get(name)
    if node is None:
        return None
    best = None
    for item in [node, *view.get_ancestors(node)]:
        split = _dims.split_term(item.name)
        if not split or _head_kind(view, split[0]) != kind:
            continue
        # A place hangs under its own cell and, by computed prefix
        # containment, under every coarser cell too; ancestors come as a
        # set. The name's value is the most specific term: the one that
        # fits within all the others.
        if best is None or view.is_below(item.name, best.name):
            best = item
    return _dims.split_term(best.name)[1] if best is not None else None


def _term_of(view: OntoDAG, name: str) -> str | None:
    """The most specific dimension term a name hangs under, whatever its
    kind — `home` under `geo(u2e4x)` yields `geo(u2e4x)`. What a *private*
    place publishes as when typed bare (Peter, 2026-09-13: a bare geo term
    is where the offer holds; no `where` head)."""
    node = view.nodes.get(name)
    if node is None:
        return None
    best = None
    for item in [node, *view.get_ancestors(node)]:
        split = _dims.split_term(item.name)
        if not split or _head_kind(view, split[0]) is None:
            continue
        if best is None or view.is_below(item.name, best.name):
            best = item
    return best.name if best is not None else None


def _handover_base(ontology: Ontology, kind: str, spelling: str) -> str:
    """The base head of `kind` the catalogue marks as a handover
    coordinate — where a bare coordinate literal or time spelling goes
    (`46.05,14.50,5km` → `geo(u2e4x)`, `today..+7d` → `time(...)`). The
    CLI names no head: it asks the catalogue which head under `handover`
    is a base of that kind, and refuses when there is none."""
    dag = ontology.dag
    bases = [head for head in sorted(ontology.handover_heads())
             if _head_kind(dag, head) == kind
             and any(p.name in _dims.KINDS for p in dag.nodes[head].parents)]
    if len(bases) > 1:
        raise ValueError(
            f"{spelling}: the catalogue marks several {kind} heads as "
            f"handover coordinates ({', '.join(bases)}) — spell the head: "
            f"`{bases[0]}({spelling})`")
    if bases:
        return bases[0]
    raise ValueError(
        f"{spelling}: the catalogue marks no {kind} head as a handover "
        f"coordinate, so a bare {'coordinate' if kind == _dims.KIND_PREFIX else 'time'} "
        f"has no head to go under — `odag put geo prefix-dimension handover`")


def _looks_like_time(token: str) -> bool:
    return ".." in token or token in ("now", "today", "tomorrow") \
        or bool(re.match(r"^\d{4}-\d{2}(-\d{2})?(T|$)", token))


def _elaborate_terms(session: "Session", concepts, ontology: Ontology):
    """Each token: let a catalogue name stand as spelled, publish a
    *private* place as the dimension term it hangs under, turn a bare
    coordinate literal into a cell and a bare time spelling into a fixed-UTC
    window (input vocabulary, cli.md §2) — both under the base head the
    catalogue marks as a handover coordinate — and, for `head(param)`
    tokens, refuse quantity kinds (the field owns them) and check the
    result is vocabulary. Head-agnostic on purpose — the CLI knows kinds,
    never heads (Peter, 2026-09-12); since 2026-09-13 there is no `where`
    or `when` head at all: `give vegetable-box shop` says the box is at the
    shop. Returns (concepts, notes, addresses): the addresses are the
    settlement texts of the named places (`place NAME ... ADDRESS`), kept
    locally and sealed to the counterparty at clearing (handoff.py).

    Names, since ontodag #15 (2026-09-12): a parameter that names a node
    of the *pinned catalogue* — a place under a cell, a region above
    cells, a floor under a building — is stored as spelled
    (`ljubljana`, `my_home_4th`, `from(my_home)`): ontodag orders it by the
    graph, and the counterparty, matching under the same root, can. A
    name only the personal layer holds is one the root does not carry, so
    it publishes as the cell it hangs under (`from(my_home)` →
    `from(u2e4x)`) and the name stays private; a private region or floor
    has no single value and is refused — publish it to the catalogue, or
    name a cell. A name outside the dimension is refused by ontodag in
    its own words, never read as a literal that happens to spell the same
    (a place called `u2e` must not become the cell `u2e`)."""
    dag = ontology.dag
    out, notes, addresses = [], [], []
    for c in concepts:
        if ontology.operator_of(c) is not None:
            out.append(_canonical(c, dag, notes))   # `transport(bicycle)`: `known` decides
            continue
        split = _dims.split_term(c)
        kind = _head_kind(dag, split[0]) if split else None
        if kind is None:
            if c in dag.nodes:          # a catalogue name (a place, a category)
                address = dag.nodes[c].metadata.get("address")
                if address:
                    addresses.append(f"{c}: {address}")
                out.append(c)
                continue
            view = session.view()
            term = None
            if c in view.nodes:         # a private name: publish its term
                term = _term_of(view, c)
                address = view.nodes[c].metadata.get("address")
                if term and address:
                    addresses.append(f"{c}: {address}")
            elif "," in c and c.count(",") == 2:
                lat, lon, radius = parse_coords(c)
                head = _handover_base(ontology, _dims.KIND_PREFIX, c)
                term = f"{head}({cell_for_coords(lat, lon, radius)})"
            elif _looks_like_time(c):
                w = window(c, session.now)
                end = "" if w.end is None else _iso(w.end - 1)
                head = _handover_base(ontology, _dims.KIND_CALENDAR, c)
                term = f"{head}({_iso(w.start)}..{end})"
            if term is None:
                out.append(c)           # unknown: fails closed at `known`
                continue
            notes.append(f"{c} → {term}")
            out.append(term)
            continue
        head, param = split
        if kind in _FIELD_KINDS:
            raise ValueError(
                f"{c}: a quantity term is accepted by the grammar but not "
                f"encodable until quantities become catalogue terms "
                f"(docs/plans/ontodag-coupling.md §3). Encodable today: a "
                f"bare quantity first (`10kg`)")
        view = session.view()
        term = c
        if param in dag.nodes:
            pass                        # a catalogue name: ontodag's to order
        elif param in view.nodes:
            value = _value_of(view, param, kind)
            if value is None:
                raise ValueError(
                    f"{c}: `{param}` is a private name (your personal store, "
                    f"not the catalogue offers pin) with no single {head} "
                    f"value to publish in its place — `loop place {param} "
                    f"LAT,LON,RADIUS` gives a place its cell; a region or a "
                    f"floor must be in the catalogue to be named in an offer")
            term = f"{head}({value})"
        elif kind == _dims.KIND_PREFIX and "," in param:
            lat, lon, radius = parse_coords(param)
            term = f"{head}({cell_for_coords(lat, lon, radius)})"
        elif kind == _dims.KIND_CALENDAR and not ontology.known(c):
            w = window(param, session.now)
            end = "" if w.end is None else _iso(w.end - 1)
            term = f"{head}({_iso(w.start)}..{end})"
        if param in view.nodes:
            address = view.nodes[param].metadata.get("address")
            if address:
                addresses.append(f"{c}: {address}")
        if term != c:
            notes.append(f"{c} → {term}")
            c = term
        if not ontology.known(c):
            try:                        # ontodag's own reason, when it has one
                dag.is_below(c, c)
            except ValueError as e:
                raise ValueError(str(e)) from None
            raise ValueError(
                f"{c}: not a value `{head}` accepts, and not a name the "
                f"catalogue knows in that dimension")
        out.append(_canonical(c, dag, notes))
    return tuple(out), notes, addresses


def _canonical(term: str, dag, notes: list[str]) -> str:
    """The catalogue's canonical spelling of a known term — `weight(8000g)`
    → `weight(8kg)`, `transport(weight(..8kg) small-item)` →
    `transport(small-item weight(..8kg))` — so one denotation is one offer
    id (U2). The catalogue's rule, not the CLI's: `surface.elaborate`."""
    from ontodag.surface import elaborate
    canonical = elaborate(term, dag)
    if canonical != term:
        notes.append(f"{term} → {canonical}")
    return canonical


def _bare_key(concepts) -> tuple[str, ...]:
    """The price memory's key: the sorted *non-parametric* concepts. A
    `time(...)` that changes on every offer would otherwise defeat it."""
    return tuple(sorted(c for c in concepts if _dims.split_term(c) is None))


def _num(x) -> str:
    """A number for people: an integer as such, a rational whose
    denominator divides a power of ten as the decimal it is, anything
    else as `n/d` — exact both ways, never a float's approximation."""
    f = q(x)
    if f.denominator == 1:
        return str(f.numerator)
    d = f.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        k = 0
        while (f.denominator * 10 ** k) % 1 or (f.numerator * 10 ** k) % f.denominator:
            k += 1
        return f"{f.numerator * 10 ** k // f.denominator / 10 ** k:.{k}f}"
    return f"{f.numerator}/{f.denominator}"


def reading(offer: Offer) -> str:
    """cli.md §6's direction rule, in words: what the encoded quantity
    means for this side. Printed, never acted on — matching stays exact."""
    return reading_for(offer.thing, offer.kind)


def reading_for(t: Thing, kind: str) -> str:
    n = _num(t.qty)
    unit = "" if t.unit == "unit" else f" {t.unit}"
    step = q(t.step)
    if kind == WANT and t.unit != "unit":
        return f"{n}{unit} — the point"   # what is wanted; a give's step decides fills
    if step == q(t.qty):
        return f"{n}{unit}, indivisible"
    granularity = "divisible" if step == 0 else f"in steps of {_num(step)}{unit}"
    floor = f", at least {_num(t.min)}{unit}" if q(t.min) else ""
    return f"up to {n}{unit}, {granularity}{floor}"


def _concepts(offer: Offer) -> str:
    """The headline: one thing's concepts; for a composed want the parts'
    bare categories joined by `+`, their place and time terms following
    under each part."""
    if offer.composed:
        return f" {PART_SEP} ".join(" ".join(_bare_key(p.concepts)) for p in offer.parts)
    return " ".join(offer.thing.concepts)


# --------------------------------------------------------------------------- #
# The one renderer: the approval block *is* `show` (gate G4)
# --------------------------------------------------------------------------- #

def _bond_text(offer: Offer) -> str:
    b = offer.bond
    if offer.v < 5:
        return f"bond {_num(q(b))}"
    if b is None:
        return "bond -"
    return (f"bond {_num(b.asset.qty)}{b.asset.unit} {' '.join(b.asset.concepts)} "
            f"worth {_num(b.value)}" + (f" in {b.escrow}" if b.escrow else " (not deposited)"))


def render_offer(offer: Offer) -> str:
    pins = (f"catalogue {offer.ontology_root[:16] or '-'}  "
            f"registry {offer.registry_version or '-'}  "
            f"contract {offer.contract_version or '-'}  v{offer.v}")
    lines = [f"{offer.kind:<9}{_concepts(offer)}", f"  maker    {offer.maker}"]
    if offer.composed:
        for i, t in enumerate(offer.parts, 1):
            lines += [f"  part {i}   {' '.join(t.concepts)}",
                      f"           quantity {_num(t.qty)} {t.unit} — {reading_for(t, WANT)}"]
        lines.append(f"  price    {_num(offer.tokens.amount)} (the lot, on "
                     f"{offer.maker}'s scale; split across the parts at clearing)")
    else:
        t = offer.thing
        lines += [
            f"  quantity {_num(t.qty)} {t.unit} — {reading(offer)}",
            f"  price    {_num(offer.tokens.amount)} "
            f"({_num(offer.unit_price)}/{t.unit}, on {offer.maker}'s scale)"]
    lines += [
        f"  valid    {_span(offer.valid)}",
        f"           local {_span(offer.valid, _local)}",
        f"  pins     {pins}",
        f"  terms    {_bond_text(offer)}  oracle {offer.oracle}  "
        f"arbitrator {offer.arbitrator or '-'}",
        f"  nonce    {offer.nonce}",
        f"  offer_id {offer.offer_id}",
    ]
    if offer.requires is not None and not offer.requires.empty:
        req = offer.requires
        lines.insert(-2, f"  requires point {_num(req.point)}"
                     + (f"  ladder {' '.join(f'{lead}s:{_num(a)}' for lead, a in req.ladder)}" if req.ladder else "")
                     + (f"  accepts {'; '.join(' '.join(a.concepts) + f' {a.unit} {_num(a.price)}' for a in req.accepts)}" if req.accepts else "")
                     + (f"  oracle {' '.join(req.oracles)}" if req.oracles else "")
                     + (f"  escrow {' '.join(req.escrows)}" if req.escrows else "")
                     + "  (of every counterparty, per fill; unmet is never matched)")
    return "\n".join(lines)


def _span(w: TimeWindow, fmt=None) -> str:
    """`A .. B`, or `A .. (until withdrawn)` for an open-ended window."""
    fmt = fmt or _iso
    end = "(until withdrawn)" if w.end is None else fmt(w.end)
    return f"{fmt(w.start)} .. {end}"


def _state(book: OfferRegistry, offer: Offer, now: int) -> str:
    if book.is_filled(offer.offer_id):
        return "filled"
    if book.is_withdrawn(offer.offer_id):
        return "withdrawn"
    if not offer.valid.is_open_at(now):
        return "expired"
    taken = book.taken(offer.offer_id) if offer.kind == GIVE else 0
    if taken:
        unit = "" if offer.thing.unit == "unit" else f" {offer.thing.unit}"
        return f"open ({_num(book.available(offer.offer_id))}{unit} left)"
    return "open"


def _row(offer: Offer, now: int, book: OfferRegistry) -> list[str]:
    qty = f"{len(offer.parts)} parts" if offer.composed else \
        f"{_num(offer.thing.qty)} {offer.thing.unit}"
    return [offer.offer_id[:12], offer.kind, offer.maker, qty, _concepts(offer),
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

Part = namedtuple("Part", "thing notes addresses")


def _term_class(session: "Session", token: str) -> str:
    """What a default term and a line's token compete on: the head of a
    `head(param)` token, the dimension head a bare name hangs under in the
    view (`home` → `geo`), else the token itself."""
    split = _dims.split_term(token)
    if split is not None:
        return split[0]
    term = _term_of(session.view(), token)
    if term is not None:
        return _dims.split_term(term)[0]
    kind = _dims.KIND_PREFIX if "," in token and token.count(",") == 2 \
        else _dims.KIND_CALENDAR if _looks_like_time(token) else None
    if kind is not None:
        try:                        # the base head a bare literal goes under
            return _handover_base(session.catalogue, kind, token)
        except ValueError:
            return kind
    return token


def _default_terms(session: "Session", parsed: Parsed) -> list[str]:
    """The `terms` setting's defaults whose coordinate the line does not
    already state (cli.md §3): `set terms home` puts every offer at home
    unless the line names a place. Place and time are optional since the
    v3 record — unset, an offer is anywhere, any time — and the CLI knows
    no head by name."""
    named = {_term_class(session, c) for c in parsed.concepts}
    return [term for term in shlex.split(_configured("terms") or "")
            if _term_class(session, term) not in named]


def _resolve_part(session: Session, parsed: Parsed, ontology: Ontology,
                  side: str = WANT) -> Part:
    """The thing — every default and shorthand expanded, every name resolved
    to its value — plus the notes that carry the surface spellings. Shared
    by a simple offer, a draft and each part of a composed want. Refusals
    here are the loud kind."""
    now = session.now
    notes: list[str] = []
    if parsed.band:
        point = parsed.band.split("..")[-1].split(":")[0] or parsed.band.split("..")[0] or "10kg"
        raise ValueError(
            f"{parsed.band}: a floor alone or a ceiling alone names no quantity "
            f"— a give says how much and, before `..`, the least one fill may "
            f"take (`50kg..100kg`, cli.md §6); a want names the point "
            f"(`{point}`), its floor being a partial-fill matter (P2)")
    if side == WANT and (parsed.min or (parsed.step is not None and parsed.qty is not None
                                        and q(parsed.step) not in (0, q(parsed.qty)))):
        raise ValueError(
            f"a floor or a step is the give's: a want names what it wants "
            f"(the give's `step` and `min` decide the fill, cli.md §6)")
    defaults = _default_terms(session, parsed)
    for term in defaults:
        notes.append(f"default {term}")
    concepts, term_notes, addresses = _elaborate_terms(
        session, tuple(parsed.concepts) + tuple(defaults), ontology)
    notes.extend(term_notes)
    for c in concepts:
        if not ontology.known(c):
            raise ValueError(
                f"unknown category: {c} — vocabulary fails closed (U7); "
                f"`odag put {c} PARENT` adds it to the catalogue")

    # An omitted quantity is the schema's own default, not a typed `1`:
    # canonical JSON tells 1 from 1.0, and `Thing(("x",))` from the API
    # must produce the same record bytes as `give x 100` (gate G1, U2).
    if parsed.qty is None:
        thing = Thing(concepts, unit=parsed.unit, divisible=parsed.divisible)
    else:
        thing = Thing(concepts, parsed.qty, parsed.unit, step=parsed.step,
                      min=parsed.min)
    return Part(thing, notes, addresses)


def part_line(part: Part) -> str:
    """The canonical one-line spelling of a resolved part: what `compose`
    encodes, re-parseable as typed (cli.md §13 — `drafts` prints it, and a
    composed want's `+` line is these joined)."""
    t = part.thing
    toks = []
    unit = "" if t.unit == "unit" else t.unit
    default_step = 0 if unit else q(t.qty)          # what the bare spelling means
    if unit or q(t.qty) != 1 or q(t.step) != default_step or q(t.min):
        spelling = f"{_num(t.qty)}{unit}"
        if q(t.step) != default_step:
            spelling += f":{_num(t.step)}"
        if q(t.min):
            spelling = f"{_num(t.min)}{unit}..{spelling}"
        toks.append(spelling)
    toks.extend(t.concepts)
    return " ".join(toks)


def _resolve_offer(session: Session, side: str, parsed: Parsed,
                   ontology: Ontology):
    """Every default and shorthand expanded into one Offer, plus the notes
    the approval block prints beside it."""
    part = _resolve_part(session, parsed, ontology, side)
    return _offer_from_part(session, side, part, parsed.price, ontology,
                            valid_text=parsed.heads.get("valid"))


def _offer_from_part(session: Session, side: str, part: Part, price,
                     ontology: Ontology, *, valid_text: str | None = None):
    """A resolved part plus a price (or the price memory) → one Offer with
    its notes; the step a `want` line and `offer NAME` share."""
    now = session.now
    thing = part.thing
    notes = list(part.notes)
    maker = session.maker
    valid = validity(valid_text or _configured("valid"), now)
    qty = thing.qty

    reused = False
    if price is None:
        found = _last_unit_price(session, maker, side, thing.concepts, now)
        if found is None:
            raise ValueError(
                f"no price, and no earlier {side} of "
                f"{' '.join(_bare_key(thing.concepts))} by {maker} to reuse — "
                f"a bare number last is the price")
        unit_price, source = found
        if source.thing.unit != thing.unit:
            raise ValueError(
                f"the last {side} of {' '.join(_bare_key(thing.concepts))} "
                f"was priced per {source.thing.unit}, this one is per "
                f"{thing.unit} — type the price")
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
    offer = make(maker, thing, price, valid=valid, nonce=nonce, **ontology.pins,
                 **_guarantees(now, thing.concepts))
    _check_asset_categories(offer, ontology)
    return offer, notes, reused


def _guarantees(now: int, concepts=()) -> dict:
    """The guarantee settings as offer fields (v5, `P3-release-and-reclearing.md`
    §5d): `bond`/`escrow` as a `Bond` deposit — its asset by the offer
    grammar, its worth to me last — and `require_point`, `require_cancel`,
    `ladder`, `require_accepts`, `require_escrows` as a `Requires`. The
    ladder is derived over the lead from `now` to the offer's handover time
    term (the first `time(...)` among `concepts`); an offer with no time term
    gets no ladder — a cancellation costs the point. Nothing set: v4."""
    from .schema import Acceptance, Bond, Requires, Thing
    out: dict = {}
    default = shlex.split(_configured("default_asset") or "xdai xDAI 1")
    if len(default) < 3:
        raise ValueError("default_asset is `CATEGORY... UNIT PRICE`")
    d_cat, d_unit, d_price = tuple(default[:-2]), default[-2], q(default[-1])
    dep = _configured("bond")
    if dep:
        toks = shlex.split(dep)
        if len(toks) == 1:                         # a bare amount: on MY scale, deposited as the default
            value = q(toks[0])                     # asset at my price for it (value / price units)
            out["bond"] = Bond(Thing(d_cat, value / d_price, d_unit), value, _escrow_address())
        else:
            parsed = parse_offer_tokens(toks)
            if parsed.qty is None or parsed.price is None or not parsed.concepts:
                raise ValueError("bond is an amount of the default asset, or `QTY[UNIT] CATEGORY... VALUE`: "
                                 "the deposit by the grammar, its worth to me last")
            out["bond"] = Bond(Thing(tuple(parsed.concepts), parsed.qty, parsed.unit or "unit"),
                               parsed.price, _escrow_address())
    point = q(_configured("require_point")) if _configured("require_point") else None
    accepts = []
    for entry in (e.strip() for e in (_configured("require_accepts") or "").split(";") if e.strip()):
        toks = shlex.split(entry)
        if len(toks) < 3:
            raise ValueError(f"require_accepts entry {entry!r} is `CATEGORY... UNIT PRICE`")
        accepts.append(Acceptance(tuple(toks[:-2]), toks[-2], q(toks[-1])))
    if point and not accepts:                      # a point with nothing named accepts the default asset
        accepts.append(Acceptance(d_cat, d_unit, d_price))
    escrows = tuple(t for t in (_configured("require_escrows") or "").split() if t)
    if point is not None or accepts or escrows:
        ladder = ()
        if point is not None and _configured("require_cancel"):
            far = q(_configured("require_cancel"))
            lead = _handover_lead(concepts, now)
            if lead and lead > 0:
                ladder = _ladder(_configured("ladder") or "linear", lead, far, point)
        out["requires"] = Requires(point=point or 0, ladder=ladder, accepts=tuple(accepts), escrows=escrows)
    if "requires" in out or "bond" in out:
        out["v"] = 5
    return out


def _escrow_address() -> str:
    """The address the record names: `chain:RPC@ADDRESS` or a bare address
    — the protocol names no RPC, and the id must not change with one."""
    spec = _configured("escrow") or ""
    return spec.rpartition("@")[2] if spec.startswith("chain:") else spec


def _check_asset_categories(offer, ontology) -> None:
    """The deposit's and the acceptances' categories must be the catalogue's:
    unknown, they would match nothing (U7) and the offer would sit unmatched
    without a word — so refuse at publish with the name to add."""
    names = []
    if offer.v >= 5 and offer.bond is not None:
        names += list(offer.bond.asset.concepts)
    if offer.requires is not None:
        for acc in offer.requires.accepts:
            names += list(acc.concepts)
    for name in names:
        if name not in ontology.dag.nodes:
            raise ValueError(f"asset category {name!r} is not in the catalogue: add it "
                             f"(e.g. `odag put {name} money`), or set default_asset / require_accepts")


def _handover_lead(concepts, now: int) -> int | None:
    """Seconds from `now` to the start of the offer's handover time term."""
    for term in concepts:
        if isinstance(term, str) and term.startswith("time(") and term.endswith(")"):
            try:
                start, _end = _calendar_span(term[5:-1])
            except Exception:                   # noqa: BLE001 — not a span this reader knows
                continue
            return start - now
    return None


def _ladder(shape: str, lead: int, far, point) -> tuple:
    """The cancellation ladder over the lead at posting, in one of a few
    shapes (Peter, 2026-09-19): the points only, on the maker's scale."""
    far, point = q(far), q(point)
    if shape == "linear":
        return ((lead, far), (0, point))
    if shape == "late":                            # flat, then rising over the last quarter
        return ((lead, far), (lead // 4, far), (0, point))
    if shape == "early":                           # rising over the first quarter, then flat
        return ((lead, far), (lead - lead // 4, point), (0, point))
    if shape == "flat":                            # the far amount until the window
        return ((lead, far), (1, far), (0, point))
    raise ValueError("ladder is linear, late, early or flat")


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
        if o.composed or _bare_key(o.thing.concepts) != key:
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


# --------------------------------------------------------------------------- #
# Drafts (cli.md §13): values at the edge, offers at the end
# --------------------------------------------------------------------------- #
#
# A draft is an unpublished offer or one part of a composed want: resolved
# now, exactly as a `want` line resolves, named or numbered, kept in a
# local file that is never the book — no id, no matching, no price unless
# the person put one there. `draft NAME A + B` composes drafts with the same
# `+` the one-line want uses (Peter, 2026-09-12: one operator, not a verb);
# `offer NAME [PRICE]` turns a draft into an offer. Draft names are working
# memory, never vocabulary: they cannot appear in an offer, because
# composition expands them. Settings stay a closed table (`set`), so a typo
# cannot quietly become a draft.

def _drafts_path() -> str:
    return os.path.join(_home_dir(), "drafts")


def _read_drafts() -> list[dict]:
    path = _drafts_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_drafts(drafts: list[dict]) -> None:
    os.makedirs(_home_dir(), mode=0o700, exist_ok=True)
    with open(_drafts_path(), "w", encoding="utf-8") as fh:
        for d in drafts:
            fh.write(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")


def _part_record(part: Part) -> dict:
    return {"thing": part.thing.to_record(), "notes": list(part.notes),
            "addresses": list(part.addresses)}


def _part_from_record(rec: dict) -> Part:
    t = rec["thing"]
    thing = Thing(tuple(t["concepts"]), q(t["qty"]), t["unit"],
                  step=q(t["step"]), min=q(t["min"])) if "step" in t else \
        Thing(tuple(t["concepts"]), t["qty"], t["unit"], t["divisible"])
    return Part(thing, list(rec["notes"]), list(rec.get("addresses", [])))


def _draft_line(d: dict) -> str:
    """A draft's canonical spelling: the offer line `offer` will speak."""
    body = f" {PART_SEP} ".join(part_line(_part_from_record(r)) for r in d["parts"])
    price = "" if d.get("price") is None else f" {_num(d['price'])}"
    return f"{d['side']} {body}{price}"


def _find_draft(drafts: list[dict], ref: str) -> dict:
    for d in drafts:
        if d["name"] == ref:
            return d
    raise ValueError(f"no such draft: {ref} (`loop drafts` lists them)")


_VERBS = (GIVE, WANT)


def cmd_draft(args, session, out):
    """`draft [NAME] want|give ...` stages a resolved offer or part;
    `draft [NAME] A + B ...` composes drafts. Re-drafting a name replaces
    it; an omitted name is the next number."""
    toks = list(args.tokens)
    if not toks:
        raise ValueError("draft [NAME] want|give ...   or   draft [NAME] A + B ...")
    name = None
    if toks[0] not in _VERBS:
        name = toks.pop(0)
        if name in _VERBS or name == PART_SEP or _PRICE_RE.match(name):
            raise ValueError(f"{name!r} cannot name a draft — verbs, `{PART_SEP}` "
                             f"and numbers are taken (numbers are the unnamed)")
    if not toks:
        raise ValueError(f"draft {name}: then a want/give line, or drafts joined "
                         f"by {PART_SEP}")
    drafts = _read_drafts()
    ontology = session.catalogue
    maker = session.maker
    if toks[0] in _VERBS:
        side = toks.pop(0)
        if side == WANT:
            parsed = parse_want_line(toks)
        else:
            parsed = parse_offer_tokens(toks)
        if isinstance(parsed, Composed):
            parts = [_resolve_part(session, p, ontology) for p in parsed.parts]
            price = parsed.price
        else:
            if "valid" in parsed.heads:
                raise ValueError("a draft has no validity of its own — it gets the "
                                 "`valid` setting when offered")
            parts = [_resolve_part(session, parsed, ontology, side)]
            price = parsed.price
    else:
        # drafts joined by `+`: composition, want side only, flattening
        refs = [t for t in toks if t != PART_SEP]
        if any(t == PART_SEP for t in (toks[0], toks[-1])) or \
                len(refs) != toks.count(PART_SEP) + 1:
            raise ValueError(f"drafts are joined as A {PART_SEP} B {PART_SEP} C")
        side, parts, price = WANT, [], None
        for ref in refs:
            d = _find_draft(drafts, ref)
            if d["side"] != WANT:
                raise ValueError(f"{ref} is a give: composition is want-side only "
                                 f"(docs/plans/cli.md §13) — a kit is one give")
            if d.get("price") is not None and len(refs) > 1:
                raise ValueError(
                    f"{ref} carries a price ({_num(d['price'])}); parts carry no "
                    f"prices — one price for the whole, at `offer` "
                    f"(P2-loop-selection.md §10 pays once). Re-draft it without")
            if d["maker"] != maker:
                raise ValueError(f"{ref} was drafted as {d['maker']}, not {maker}")
            parts.extend(_part_from_record(r) for r in d["parts"])
            if len(refs) == 1:
                price = d.get("price")        # a copy keeps its price
    existing = _find_draft(drafts, name) if name and any(
        d["name"] == name for d in drafts) else None
    n = existing["n"] if existing else max((d["n"] for d in drafts), default=0) + 1
    record = {"name": name or str(n), "n": n, "maker": maker, "side": side,
              "parts": [_part_record(p) for p in parts], "price": price,
              "typed": " ".join(args.tokens), "created": session.now}
    drafts = [d for d in drafts if d["n"] != n] + [record]
    drafts.sort(key=lambda d: d["n"])
    _write_drafts(drafts)
    print(f"{record['name']}  {_draft_line(record)}", file=out)
    return 0


def cmd_drafts(args, session, out):
    """Every draft in its canonical spelling — what `offer` will say —
    with the typed spelling and the name→value notes beneath: the
    approval block's two layers."""
    drafts = _read_drafts()
    for d in drafts:
        print(f"{d['name']}  {_draft_line(d)}", file=out)
        print(f"   typed {d['typed']}", file=out)
        notes = [f"part {i}: {n}" if len(d["parts"]) > 1 else n
                 for i, r in enumerate(d["parts"], 1) for n in r["notes"]]
        for note in notes:
            print(f"   note  {note}", file=out)
        if d["maker"] != _configured("maker"):
            print(f"   maker {d['maker']}", file=out)
    return 0 if drafts else 1


def cmd_discard(args, session, out):
    drafts = _read_drafts()
    if not args.refs:
        _write_drafts([])
        print(f"{len(drafts)} discarded", file=_err())
        return 0
    chosen = [_find_draft(drafts, ref) for ref in args.refs]
    _write_drafts([d for d in drafts if d not in chosen])
    return 0


def _composed_offer(session: Session, parts: list[Part], price,
                    valid_text: str | None = None) -> tuple[Offer, list[str]]:
    """The composed want as one v4 offer: `Parts`, one price for the lot,
    the session's validity and pins (cli.md §13, since 2026-09-14)."""
    if len(parts) < 2:
        raise ValueError("a composed want has at least two parts")
    if price is None:
        raise ValueError("a composed want needs its price, last on the line "
                         "(there is no price memory for a composition)")
    valid = validity(valid_text or _configured("valid"), session.now)
    offer = want(session.maker, Parts(tuple(p.thing for p in parts)), price,
                 valid=valid, **session.catalogue.pins,
                 **_guarantees(session.now, tuple(t for p in parts for t in p.thing.concepts)))
    _check_asset_categories(offer, session.catalogue)
    notes = [f"part {i}: {note}" for i, p in enumerate(parts, 1) for note in p.notes]
    return offer, notes


def _offer_composed(session: Session, parts: list[Part], price, out,
                    valid_text: str | None = None) -> int:
    """Publish a composed want: the same block, question and id as a
    simple one, every part under the one price."""
    offer, notes = _composed_offer(session, parts, price, valid_text)
    addresses = [a for p in parts for a in p.addresses]
    return _publish_offer(session, offer, notes, False, out, addresses=addresses)


def _publish_offer(session: Session, offer: Offer, notes: list[str],
                   reused: bool, out, addresses=()) -> int:
    """Show, ask, publish, commit, print the id — the tail every publishing
    verb shares. `addresses` are the named places' settlement texts: shown
    here (this is what the counterparty will read), kept in
    `$LOOP_HOME/handoffs`, sealed by `watch` once the offer clears."""
    print(render_offer(offer), file=out)
    for note in notes:
        print(f"  note     {note}", file=out)
    for address in addresses:
        print(f"  note     handoff {address} — sealed to the counterparty "
              f"at clearing", file=out)
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
    if addresses:
        _remember_handoff(oid, "\n".join(addresses))
    # By exception to odag's silent-on-success rule: publishing is a
    # commitment, and the id is what `withdraw` needs.
    print(oid, file=out)
    return 0


def cmd_offer(args, session, out):
    """`offer NAME [PRICE]`: a draft becomes an offer. The draft's own
    price if it has one, the given price otherwise (or over it, shown in
    the block), the price memory for a simple draft with neither."""
    toks = list(args.tokens)
    if not toks or len(toks) > 2 or (len(toks) == 2 and not _PRICE_RE.match(toks[1])):
        raise ValueError("offer NAME [PRICE]")
    drafts = _read_drafts()
    d = _find_draft(drafts, toks[0])
    if d["maker"] != session.maker:
        raise ValueError(f"{toks[0]} was drafted as {d['maker']}, not "
                         f"{session.maker}")
    price = _number(toks[1]) if len(toks) == 2 else d.get("price")
    parts = [_part_from_record(r) for r in d["parts"]]
    if len(parts) > 1:
        code = _offer_composed(session, parts, price, out)
        if code == 0:
            _write_drafts([x for x in drafts if x is not d])
        return code
    offer, notes, reused = _offer_from_part(session, d["side"], parts[0], price,
                                            session.catalogue)
    code = _publish_offer(session, offer, notes, reused, out,
                          addresses=parts[0].addresses)
    if code == 0:
        _write_drafts([x for x in drafts if x is not d])
    return code


# --------------------------------------------------------------------------- #
# The line as Python's offer literal (cli.md §13): one grammar for the shell,
# the API and the assistant — a program builds offers as objects or as lines,
# and both end at the same approval block.
# --------------------------------------------------------------------------- #

def offer_from_line(line: str, session: "Session | None" = None) -> Offer:
    """`"want 10kg apple home 100"` → the resolved `Offer`, under the
    session's settings (maker, defaults, catalogue), not published. A
    composed line raises with the v4 refusal."""
    session = session or Session()
    toks = shlex.split(line)
    if not toks or toks[0] not in _VERBS:
        raise ValueError("an offer line starts with give or want")
    side = toks.pop(0)
    parsed = parse_want_line(toks) if side == WANT else parse_offer_tokens(toks)
    if isinstance(parsed, Composed):
        parts = [_resolve_part(session, p, session.catalogue) for p in parsed.parts]
        return _composed_offer(session, parts, parsed.price, parsed.valid)[0]
    offer, _notes, _reused = _resolve_offer(session, side, parsed, session.catalogue)
    return offer


def line_for(offer: Offer) -> str:
    """The canonical offer line of an `Offer`: everything the maker typed or
    defaulted, in re-parseable spelling; maker, nonce and pins come from
    the session that speaks it."""
    body = f" {PART_SEP} ".join(part_line(Part(t, [], [])) for t in offer.parts)
    end = "" if offer.valid.end is None else _iso(offer.valid.end)
    valid = f"valid({_iso(offer.valid.start)}..{end})"
    return f"{offer.kind} {body} {valid} {_num(offer.tokens.amount)}"


def _publish(args, session: Session, out, side: str) -> int:
    if side == WANT:
        parsed = parse_want_line(args.tokens)
        if isinstance(parsed, Composed):
            ontology = session.catalogue
            parts = [_resolve_part(session, p, ontology) for p in parsed.parts]
            return _offer_composed(session, parts, parsed.price, out, parsed.valid)
    else:
        parsed = parse_offer_tokens(args.tokens)
    part = _resolve_part(session, parsed, session.catalogue, side)
    offer, notes, reused = _offer_from_part(
        session, side, part, parsed.price, session.catalogue,
        valid_text=parsed.heads.get("valid"))
    return _publish_offer(session, offer, notes, reused, out,
                          addresses=part.addresses)


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
    """The dated bridge (cli.md §4, §11.1): a place node under the cell of
    that radius around that point, written to the personal layer — the
    cell is the place (no disc anywhere since the v3 record). Deleted the
    day odag accepts `geo(LAT,LON,R)` as input vocabulary. When the
    personal store *is* the catalogue the name is vocabulary and offers
    say `NAME` bare (ontodag #15 orders the name); under a separate
    pinned catalogue the place is private and offers say its cell. The
    optional ADDRESS is settlement text on the node (P1-spacetime-terms.md
    §4): never vocabulary, never in a record — shown in the approval block
    of an offer naming the place and sealed to the cleared counterparty."""
    lat, lon, radius = parse_coords(args.coords)
    personal = session.personal_session
    dag = personal.dag
    if not ("geo" in dag.nodes and "prefix-dimension" in dag.nodes
            and dag.is_below("geo", "prefix-dimension")):
        # The cell edge is what lets ontodag interpret the name (`my_home`
        # under `geo(u2e4x)` is how `from(my_home)` is ordered, or how a
        # private place gets the cell it publishes as), and `geo` comes
        # from the prelude — adopted by merge, idempotent, canonical,
        # exactly what `odag prelude` does.
        from ontodag.prelude import apply as apply_prelude
        apply_prelude(dag)
        print("loop: adopted ontodag's prelude into the personal store "
              f"({personal.describe()}) so places hang under geo cells",
              file=_err())
    dag.put(args.name, [f"geo({cell_for_coords(lat, lon, radius)})"])
    address = " ".join(args.address).strip()
    if address:
        dag.nodes[args.name].metadata["address"] = address
    personal.save()
    return 0


# --------------------------------------------------------------------------- #
# Commands: settlement — handoffs and watch (P1-spacetime-terms.md §4)
#
# The address reaches the courier through the book: after a loop clears,
# the place-owner's client seals the text to the leg counterparty's public
# key (recovered from the signature on their offer) and writes it beside
# its own filled offer; the counterparty's `watch` reads the fold it already
# follows and opens it with bee_signer. No side channel. `watch` is also
# how anyone learns they cleared: the fill record is the notification.
# --------------------------------------------------------------------------- #

def _handoffs_path() -> str:
    return os.path.join(_home_dir(), "handoffs")


def _seen_path() -> str:
    return os.path.join(_home_dir(), "seen")


def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: str, value) -> None:
    os.makedirs(_home_dir(), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh, sort_keys=True)
    os.chmod(path, 0o600)


def _remember_handoff(offer_id: str, text: str) -> None:
    pending = _read_json(_handoffs_path(), {})
    pending[offer_id] = text
    _write_json(_handoffs_path(), pending)


def _leg_of(fold: OfferRegistry, offer_id: str):
    """(loop_id, leg, my side) for a filled offer, else None."""
    loop_id = fold.loop_of(offer_id)
    if not loop_id:
        return None
    rec = fold.store.get(f"loop/{loop_id}")
    for leg in rec.get("legs", []):
        if offer_id in (leg["give"], leg["want"]):
            return loop_id, leg, ("give" if leg["give"] == offer_id else "want")
    return None


def cmd_handoff(args, session, out):
    """`handoff ID TEXT...`: what the cleared counterparty of my offer ID
    may read — a door, a gate code, "ring twice". Kept locally; sealed and
    published by `watch` once the offer is filled (now, if it already is).
    Replaces the place's address text for this offer."""
    text = " ".join(args.text).strip()
    if not text:
        raise ValueError("handoff ID TEXT — the text the cleared counterparty may read")
    oid = _resolve_id(session, args.id, mine_only=True)
    _remember_handoff(oid, text)
    fold = session.fold()
    if fold.is_filled(oid):
        _seal_pending(session, fold, out, only={oid})
    return 0


def _seal_pending(session: Session, fold: OfferRegistry, out, *, only=None) -> bool:
    """Seal every remembered text whose offer has cleared and whose
    counterparty left a public key; returns whether anything was sealed."""
    from .handoff import seal
    from .sigs import recover_public_key

    pending = _read_json(_handoffs_path(), {})
    me = session.maker
    sealed = False
    for oid, text in sorted(pending.items()):
        if only is not None and oid not in only:
            continue
        found = _leg_of(fold, oid)
        if found is None:
            continue
        loop_id, leg, side = found
        if session.book.handoff(loop_id, oid) is not None \
                or fold.handoff(loop_id, oid) is not None:
            continue
        other = fold.get(leg["want"] if side == "give" else leg["give"])
        sig = fold.signature(other.offer_id)
        if sig is None:
            print(f"handoff  {oid[:12]} waits: no public key for {other.maker} "
                  f"(their offer carries no signature)", file=_err())
            continue
        record = dict(seal(text, recover_public_key(other.offer_id, sig)),
                      **{"from": me, "to": other.maker})
        session.book.attach_handoff(loop_id, oid, record, fold=fold)
        session.book.commit()
        print(f"handoff  {oid[:12]} sealed to {other.maker} for loop "
              f"{loop_id[:16]}…", file=out)
        sealed = True
    return sealed


def _incoming(session: Session, fold: OfferRegistry):
    """(key, loop_id, other maker, sealed record) for every handoff a
    counterparty sealed to me on a loop that filled one of my offers."""
    me = session.maker
    for offer in fold.offers(include_filled=True):
        if offer.maker != me:
            continue
        found = _leg_of(fold, offer.offer_id)
        if found is None:
            continue
        loop_id, leg, side = found
        other_id = leg["want"] if side == "give" else leg["give"]
        record = fold.handoff(loop_id, other_id)
        if record is not None and record.get("to") == me:
            yield f"{loop_id}/{other_id}", loop_id, fold.get(other_id).maker, record


def _open_incoming(session: Session, fold: OfferRegistry, out, seen) -> bool:
    from .handoff import open_

    signer = _configured("bee_signer")
    news = False
    for key, loop_id, other, record in _incoming(session, fold):
        if key in seen:
            continue
        if not signer:
            print(f"handoff  from {other} for loop {loop_id[:16]}…: sealed to me, "
                  f"but bee_signer is unset — cannot open", file=_err())
            continue
        try:
            text = open_(record, signer)
        except Exception as exc:  # noqa: BLE001 — a bad key or a tampered record
            print(f"handoff  from {other} for loop {loop_id[:16]}…: cannot open "
                  f"({exc.__class__.__name__})", file=_err())
            continue
        print(f"handoff  from {other} for loop {loop_id[:16]}…: {text}", file=out)
        seen.append(key)
        news = True
    return news


def _watch_pass(session: Session, out) -> bool:
    """One pass: report my new fills, seal what is pending, open what
    arrived. Returns whether anything new was reported."""
    fold = session.fold()
    me = session.maker
    seen = _read_json(_seen_path(), {"fills": [], "handoffs": []})
    news = False
    for offer in fold.offers(include_filled=True):
        oid = offer.offer_id
        if offer.maker != me or oid in seen["fills"]:
            continue
        found = _leg_of(fold, oid)
        if found is None:
            continue
        loop_id, leg, side = found
        other = fold.get(leg["want"] if side == "give" else leg["give"])
        thing = " ".join(_bare_key(tuple(c for p in (offer if side == "give" else other).parts for c in p.concepts)))
        verb = f"gives {thing} to" if side == "give" else f"receives {thing} from"
        print(f"filled   {oid[:12]} in loop {loop_id[:16]}…: {me} {verb} "
              f"{other.maker}", file=out)
        seen["fills"].append(oid)
        news = True
    news = _seal_pending(session, fold, out) or news
    news = _open_incoming(session, fold, out, seen["handoffs"]) or news
    _write_json(_seen_path(), seen)
    return news


def cmd_watch(args, session, out):
    """`watch [--once]`: poll the fold every `interval`; report my fills,
    seal pending handoffs, open incoming ones. `--once` is one pass and a
    predicate: exit 0 when something new was reported."""
    interval = duration_s(_configured("interval"))
    while True:
        news = _watch_pass(session, out)
        if args.once:
            return 0 if news else 1
        out.flush()
        session._book = None          # re-open: another writer may have committed
        _time.sleep(interval)


def cmd_handoffs(args, session, out):
    """Every handoff sealed to me, opened with bee_signer. Exit 1 if none."""
    from .handoff import open_

    fold = session.fold()
    signer = _configured("bee_signer")
    rows = list(_incoming(session, fold))
    for _key, loop_id, other, record in rows:
        try:
            text = open_(record, signer) if signer else "(sealed; set bee_signer to open)"
        except Exception as exc:  # noqa: BLE001
            text = f"(cannot open: {exc.__class__.__name__})"
        print(f"{loop_id[:16]}…  from {other}: {text}", file=out)
    return 0 if rows else 1


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
                not any(ontology.satisfies(p.concepts, args.categories) for p in o.parts):
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


def _owner_for_announcing(session) -> str:
    """Who announces: on chain the transaction's sender, i.e. bee_signer's
    address; on the file and memory channels the configured maker."""
    key = _configured("bee_signer")
    if key:
        try:
            from .sigs import maker_address
            return maker_address(key)
        except Exception:
            pass
    maker = _configured("maker")
    if not maker:
        raise ValueError("announcing needs an identity: set bee_signer (or maker)")
    return maker


def cmd_announce(args, session, out):
    """Say "my book is here" on the announcement channel: the book spec
    without its owner (`swarm:TOPIC`, or `rs:PATH` on a file channel), so
    every reader of the channel folds it as mine."""
    spec = _book_spec()
    if spec.startswith("swarm:") and "@" in spec:
        raise ValueError(f"{spec}: announce a book you write, not one you follow")
    role = args.role or "maker"
    ann = session.announcements.announce(spec, role, owner=_owner_for_announcing(session))
    print(f"announced {ann.owner} {ann.book} ({ann.role})", file=out)
    return 0


def cmd_announced(args, session, out):
    """The standing announcements: owner, book, role."""
    for ann in session.announcements.announced():
        print(f"{ann.owner} {ann.book} {ann.role}", file=out)
    return 0


def cmd_fold(args, session, out):
    """Fold the announced books and my peers myself and print the root —
    the number any aggregator's manifest must agree with (T14)."""
    fold = session.fold()
    every = list(fold.offers(include_filled=True))
    print(f"book root {fold.store.root or '(empty)'}", file=out)
    print(f"offers {len(every)}", file=_err())
    return 0


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
    print(f"registry = {_configured('registry') or '(none)'}", file=out)
    print(f"peers = {', '.join(_peer_specs()) or '(none)'}", file=out)
    for key in ("maker", "terms", "valid", "confirm"):
        print(f"{key} = {_configured(key) or '(unset)'}", file=out)
    print(f"now = {_iso(session.now)}"
          + ("" if _configured("now") else " (wall clock)"), file=out)
    return 0


# --------------------------------------------------------------------------- #
# Commands: solver and clearing
# --------------------------------------------------------------------------- #

def _print_loop(loop, fold: OfferRegistry, out, *, prefix="") -> None:
    circ = loop if isinstance(loop, Circulation) else Circulation.from_loop(loop)
    print(f"{prefix}loop {circ.loop_id[:16]}… surplus {100 * float(circ.surplus):.2f}%",
          file=out)
    for leg in sorted(circ.legs, key=lambda leg: leg.key):
        print("  " + _leg_line(leg.gives, leg.want), file=out)


def _leg_line(gives, want) -> str:
    """`grocer gives vegetable-box shop + courier gives transport ... to buyer`
    — a composed leg names every give it consumes; a simple one its rate."""
    parts = " + ".join(f"{g.maker} gives {' '.join(g.thing.concepts)}" for g in gives)
    tail = f"(rate {float(want.unit_price / gives[0].unit_price):.4g})" \
        if len(gives) == 1 and not want.composed else "(composed)"
    return f"{parts} to {want.maker} {tail}"


def cmd_loops(args, session, out):
    """Find on a pinned snapshot, print, never clear. Exit 1 when nothing
    is profitable, so `loop loops && loop clear` reads naturally."""
    fold = session.fold()
    agent = SolverAgent(fold, session.catalogue, clearing=None,
                        solver_id="loop-cli", min_surplus=0.0, chain_fills=_chain_fills(session),
                        escrow_held=_escrow_held(session))
    root, loops = agent.find_loops(now=session.now)
    for loop in loops:
        _print_loop(loop, fold, out)
    return 0 if loops else 1


def _beat_client(session):
    from .beat import BeatClient
    spec = _configured("beat")
    if not spec or not spec.startswith("chain:"):
        raise ValueError("no clearing contract: `loop set beat chain:RPC_URL@CONTRACT`")
    rpc, _, address = spec[6:].rpartition("@")
    return BeatClient(rpc, address, key=_configured("bee_signer") or None)


def _chain_fills(session):
    """`BeatClearing.filled` when a clearing contract is set — the fill
    authority the hunt and the checklist subtract from what the book says
    is left — else None (2026-09-18: a fold that never saw a clearing's
    fills proposed a loop through an offer the chain had already filled)."""
    if not (_configured("beat") or "").startswith("chain:"):
        return None
    return _beat_client(session).filled


def cmd_propose(args, session, out):
    """Clear locally as `clearing` does and post every accepted loop as one
    beat on the clearing contract (P2, 2026-09-15): the book keeps the data,
    the chain the commitments and — after `finalize` — the fills. The
    bee_signer key pays the bond and is the submitter."""
    from .clearing import ChainClearing
    now = session.now
    if _peer_specs() or _configured("registry"):
        session.book.absorb(session.fold())
        session.book.commit()
    book, ontology = session.book, session.catalogue
    client = _beat_client(session)
    held = _escrow_held(session)
    agent = SolverAgent(book, ontology,
                        ChainClearing(book, ontology, beat_client=client, clock=lambda: now,
                                      escrow_held=held),
                        solver_id="loop-cli", min_surplus=0.0, chain_fills=client.filled,
                        escrow_held=held)
    receipts = agent.step(now=now)
    posted = 0
    for r in receipts:
        if r.accepted:
            posted += 1
            print(f"posted {r.reason}: loop {r.loop_id[:16]}…", file=out)
        else:
            print(f"rejected {r.loop_id[:16]}…: {r.reason}", file=_err())
    if posted:
        print(f"book root {book.store.root}", file=out)
    return 0 if posted else 1


def _escrow_client(session):
    from .escrow import EscrowClient
    spec = _configured("escrow")
    if not spec or not spec.startswith("chain:"):
        raise ValueError("no escrow contract: `loop set escrow chain:RPC_URL@CONTRACT`")
    rpc, _, address = spec[6:].rpartition("@")
    return EscrowClient(rpc, address, key=_configured("bee_signer") or None)


def _escrow_held(session):
    """`EscrowClient.held` in asset units when an escrow contract is set —
    the authority on every deposit the hunt and the checklist weigh — else
    None (the declaration stands)."""
    if not (_configured("escrow") or "").startswith("chain:"):
        return None
    from .escrow import held_units
    return held_units(_escrow_client(session))


def cmd_deposit(args, session, out):
    """Fund the declared bond of my gives on the escrow contract (P3 §5a,
    2026-09-19): for the offer named, or every unfilled give of mine whose
    `bond` names the `escrow` contract and is not yet held there, deposit
    the bond's quantity in the chain's native coin — the default asset,
    xDAI on Gnosis — from the bee_signer key. `--check` reports what the
    contract holds against each and sends nothing. An ERC-20 deposit is
    the client's `deposit(token=)`; the CLI funds the gas token only, as
    the one asset every maker on the chain already holds."""
    from .escrow import to_wei
    client = _escrow_client(session)
    mine = [o for o in session.book.offers(include_filled=False)
            if o.maker == session.maker and o.kind == GIVE and o.v >= 5 and o.bond is not None]
    if args.id:
        mine = [o for o in mine if o.offer_id.startswith(args.id)]
        if not mine:
            raise ValueError(f"{args.id}: not an unfilled give of mine with a bond")
    escrow = client.address.lower()
    mine = [o for o in mine if o.bond.escrow.lower() == escrow]
    if not mine:
        print("nothing to deposit: no give of mine names this escrow", file=_err())
        return 1
    sent = 0
    for o in mine:
        need, held = to_wei(o.bond.asset.qty), client.held(o.offer_id)
        asset = f"{_num(o.bond.asset.qty)}{o.bond.asset.unit} {' '.join(o.bond.asset.concepts)}"
        if held >= need:
            print(f"{o.offer_id[:16]}… {asset}: held", file=out)
            continue
        if args.check:
            print(f"{o.offer_id[:16]}… {asset}: {_num(Fraction(need - held, 10 ** 18))} to deposit", file=out)
            continue
        receipt = client.deposit(o.offer_id, need - held)
        sent += 1
        print(f"{o.offer_id[:16]}… {asset}: deposited, gas {receipt['gasUsed']}", file=out)
    return 0


def cmd_finalize(args, session, out):
    """Record a beat's fills on chain once its challenge window has closed
    — and, with an escrow set, reserve on it the share of every deposit the
    loop's legs rely on (2026-09-19): the fills becoming the chain's
    authority is the moment the deposits behind them are locked per fill;
    the loop record is found as `challenge` finds it, the reservation built
    by `escrow.reservations_for`, `claim` the period after the window in
    which a claim may be opened (`escrow_claim`), the resolver my own key
    until factbond's contract exists."""
    from .beat import find_evidence, proposal_from_record
    from .escrow import reservations_for
    client = _beat_client(session)
    receipt = client.finalize(int(args.beat))
    state = client.beat(int(args.beat))
    print(f"finalized beat {args.beat}: {state['fills']} fills, gas {receipt['gasUsed']}", file=out)
    if not (_configured("escrow") or "").startswith("chain:"):
        return 0
    ev = find_evidence(state, _evidence_books(session, state, None))
    if ev is None:
        print(f"loop: beat {args.beat}: no loop record found, nothing reserved on the escrow", file=_err())
        return 2
    escrow = _escrow_client(session)
    proposal = proposal_from_record(ev.record, ev.snapshot)
    reservations = reservations_for(proposal, escrow=escrow.address, resolver=escrow.account().address,
                                    claim_seconds=duration_s(_configured("escrow_claim") or "7d"),
                                    now=session.now, span=_calendar_span)
    for r in reservations:
        try:
            escrow.reserve(r["offer_id"], r["loop_id"], r["wanter"], r["resolver"], r["amount"],
                           window=r["window"], claim_seconds=r["claim_seconds"], ladder=r["ladder"])
            print(f"reserved {_num(Fraction(r['amount'], 10 ** 18))} behind {r['offer_id'][:16]}… "
                  f"for {r['wanter']}", file=out)
        except Exception as exc:  # noqa: BLE001 — a reservation the contract refuses is reported, not fatal
            print(f"loop: {r['offer_id'][:16]}…: not reserved: {exc}", file=_err())
    if not reservations:
        print("no deposit of this escrow behind the loop's legs", file=out)
    return 0


def _beat_state_line(state: dict) -> str:
    if state["cancelled"]:
        phase = "cancelled"
    elif state["finalized"]:
        phase = "finalized"
    elif state["open"]:
        phase = f"open until block {state['window_end']}"
    else:
        phase = "window closed, not finalized"
    return (f"beat {state['beat']} by {state['submitter']} root {state['book_root'][:16]}… "
            f"{state['fills']} fills, {phase}")


def cmd_beats(args, session, out):
    """Every beat on the clearing contract, first to last: who posted it,
    under which book root, how many fills, and where it stands — what a
    challenger reads before choosing one."""
    client = _beat_client(session)
    beats = client.beats()
    for state in beats:
        if args.open and not state["open"]:
            continue
        print(_beat_state_line(state), file=out)
    return 0 if beats else 1


def _evidence_books(session, state: dict, spec: str | None):
    """Where a beat's loop record may be: the book named, else the
    submitter's announced books (the clearing role first — `msg.sender` of
    the beat is the feed-signing key that announces, U8) and then my own
    (I may be the submitter, or hold its fold)."""
    if spec:
        return [_open_book(spec)]
    books = []
    if _configured("registry"):
        mine = sorted((ann for ann in session.announcements.announced()
                       if ann.owner.lower() == state["submitter"].lower()),
                      key=lambda ann: ann.role != "clearing")
        for ann in mine:
            try:
                books.append(_open_book(ann.spec()))
            except Exception as exc:            # noqa: BLE001 — their postage, not our omission
                print(f"loop: {ann.owner}: {exc}", file=_err())
    books.append(session.book)
    return books


def cmd_challenge(args, session, out):
    """Verify a beat as a challenger and act on it (P2, 2026-09-18). The
    loop record behind the beat is found in the submitter's clearing book
    (or `--book SPEC`) by hashing to the beat's commitments; every leg is
    re-derived off chain under my catalogue (U3, the same checklist that
    cleared it) and put to the contract's own verifier for free; a leg the
    contract would convict is challenged — the beat cancelled, the bond
    mine — unless `--check`. A fault only the off-chain check sees is
    reported as the arbiter's: the contract does not compute it. With LEG,
    that leg is challenged whatever the dry run says. Exit 0: the beat
    verifies, or was cancelled by this challenge; 1: a fault stands that
    was not acted on; 2: no evidence."""
    from .beat import challenge_beat
    client = _beat_client(session)
    state = client.beat(int(args.beat))
    print(_beat_state_line(state), file=out)
    books = _evidence_books(session, state, args.book)
    now = session.now if _configured("now") else None
    index = int(args.leg) if args.leg is not None else None
    can_send = bool(_configured("bee_signer"))
    result = challenge_beat(client, int(args.beat), books, session.catalogue, now=now,
                            index=index, send=not args.check and can_send)
    if result.evidence is None:
        print(f"no evidence: no loop record under root {state['book_root'][:16]}… hashes to "
              f"the beat's commitments in {len(books)} book(s) — the contract cannot "
              f"convict what nobody has seen; do not rely on this beat", file=_err())
        return 2
    rec, book = result.evidence.record, result.evidence.snapshot
    print(f"loop {rec['loop_id'][:16]}… surplus {100 * float(q(rec['surplus'])):.2f}%, "
          f"solver {rec.get('solver', '?')}", file=out)
    for verdict, leg in zip(result.legs, rec["legs"]):
        gives = [book.get(g) for g in leg.get("gives", [leg["give"]])]
        off = "holds" if verdict.local is None else verdict.local
        on = verdict.chain or "no verdict (the node would not run the call)"
        print(f"  [{verdict.index}] {_leg_line(gives, book.get(leg['want']))}", file=out)
        print(f"      off chain: {off}", file=out)
        print(f"      on chain:  {on}", file=out)
    if result.overall and result.overall != "no evidence" \
            and not any(v.local for v in result.legs):
        print(f"  the set: {result.overall}", file=out)
    if result.sent is not None:
        print(f"challenged leg {result.sent}: {result.reason}", file=out)
        if result.cancelled:
            print(f"beat {args.beat} cancelled; the bond is the challenger's", file=out)
            return 0
        print(f"beat {args.beat} stands", file=out)
        return 0 if result.verifies else 1
    if result.verifies:
        print(f"beat {args.beat} verifies", file=out)
        return 0
    if any(v.convicts for v in result.legs):
        why = "not sent (--check)" if args.check else \
            "not sent: the window is closed" if not result.state["open"] else \
            "not sent: sending needs a key (set bee_signer)"
        print(f"a leg the contract would convict — {why}", file=out)
        return 1
    print("a fault the contract does not compute — the arbiter's (P3), not a challenge",
          file=out)
    return 1


_MEMORY_SEALED = None


def _sealed_client(session):
    """The sealed beat named by `auction` (auction.py): a chain contract, or
    one in-process instance per process for `memory:`."""
    global _MEMORY_SEALED
    from .auction import MemorySealedBeat, open_sealed
    spec = _configured("auction")
    if not spec:
        raise ValueError("no sealed beat: `loop set auction chain:RPC_URL@CONTRACT` (or memory:)")
    if spec.startswith("memory") and _MEMORY_SEALED is None:
        _MEMORY_SEALED = MemorySealedBeat(solver=_configured("maker") or "me")
    return open_sealed(spec, key=_configured("bee_signer") or None, memory=_MEMORY_SEALED)


def _sealed_path(beat: int) -> str:
    return os.path.join(_home_dir(), "sealed", f"{beat}.json")


def cmd_commit(args, session, out):
    """Solve on the fold and seal the loops for the current beat (P2, the
    sealed-proposal beat, 2026-09-18): the bundle's bytes and salt stay in
    this home (`sealed/BEAT.json`, mine to reveal), the commitment goes to
    the sealed beat. One commitment per solver per beat. Exit 1: nothing to
    propose."""
    from .auction import COMMIT, PHASES, bundle_bytes, seal
    from .clearing import LoopProposal
    sealed = _sealed_client(session)
    beat = sealed.current()
    if sealed.phase(beat) != COMMIT:
        raise ValueError(f"beat {beat} is in its {PHASES[sealed.phase(beat)]} phase; commits open "
                         f"at block {sealed.window(beat + 1)[0]}")
    fold = session.fold()
    agent = SolverAgent(fold, session.catalogue, clearing=None, solver_id="loop-cli", min_surplus=0.0,
                        chain_fills=_chain_fills(session))
    root, loops = agent.find_loops(now=session.now)
    if not loops:
        print(f"beat {beat}: nothing to propose on root {root[:16]}…", file=_err())
        return 1
    proposals = [LoopProposal(loop, root, session.catalogue.root, "loop-cli", session.now)
                 for loop in loops]
    data = bundle_bytes(proposals)
    commitment, salt = seal(data)
    os.makedirs(os.path.dirname(_sealed_path(beat)), exist_ok=True)
    _write_json(_sealed_path(beat), {"beat": beat, "root": root, "proposal": data.hex(),
                                     "salt": salt.hex(), "loops": [p.circulation.loop_id for p in proposals]})
    sealed.commit(commitment)
    for loop in loops:
        _print_loop(loop, fold, out)
    print(f"committed beat {beat}: {len(loops)} loop(s) on root {root[:16]}…, "
          f"reveal from block {sealed.window(beat)[1]}", file=out)
    return 0


def cmd_reveal(args, session, out):
    """Open this session's sealed bundle for a beat in its reveal phase (the
    latest committed one unless BEAT is given)."""
    from .auction import PHASES, REVEAL
    sealed = _sealed_client(session)
    if args.beat is not None:
        beat = int(args.beat)
    else:
        home = os.path.join(_home_dir(), "sealed")
        mine = sorted(int(f[:-5]) for f in os.listdir(home) if f.endswith(".json")) \
            if os.path.isdir(home) else []
        if not mine:
            raise ValueError("nothing committed from this home")
        beat = mine[-1]
    kept = _read_json(_sealed_path(beat), None)
    if not kept:
        raise ValueError(f"no sealed bundle for beat {beat} in this home")
    if sealed.phase(beat) != REVEAL:
        raise ValueError(f"beat {beat} is {PHASES[sealed.phase(beat)]}; reveals run from block "
                         f"{sealed.window(beat)[1]} to {sealed.window(beat)[2]}")
    sealed.reveal(beat, bytes.fromhex(kept["proposal"]), bytes.fromhex(kept["salt"]))
    print(f"revealed beat {beat}: {len(kept['loops'])} loop(s)", file=out)
    return 0


def cmd_sealed(args, session, out):
    """Where the sealed beat stands: the current beat, its phase and window,
    who committed and who revealed."""
    from .auction import PHASES
    sealed = _sealed_client(session)
    beat = int(args.beat) if args.beat is not None else sealed.current()
    start, commit_end, end = sealed.window(beat)
    print(f"beat {beat}: {PHASES[sealed.phase(beat)]} (block {sealed.block()}; commits "
          f"{start}..{commit_end - 1}, reveals {commit_end}..{end - 1})", file=out)
    revealed = {s.lower() for s, _ in sealed.revealed(beat)} if sealed.phase(beat) >= 1 else set()
    for solver in sealed.committers(beat):
        print(f"  {solver} {'revealed' if solver.lower() in revealed else 'committed'}", file=out)
    o = sealed.outcome(beat)
    if o:
        print(f"  outcome recorded by {o['submitter']}: winners {o['winners'].hex()[:16]}…", file=out)
    return 0


def cmd_outcome(args, session, out):
    """Derive a closed beat's outcome and, unless `--check`, post the winners
    to the clearing contract and record it on the sealed beat: every
    revealed loop re-derived (U3), the baseline's loops as the reserve bid,
    the fairness filter, deterministic selection. The beat's snapshot is
    this session's fold. Exit 0 with winners, 1 with none, 2 when the beat
    is still open."""
    from .auction import CLOSED, PHASES, baseline_proposals, outcome
    from .clearing import ChainClearing
    sealed = _sealed_client(session)
    beat = int(args.beat) if args.beat is not None else max(sealed.current() - 1, 0)
    if sealed.phase(beat) != CLOSED:
        print(f"beat {beat} is {PHASES[sealed.phase(beat)]}: closes at block {sealed.window(beat)[2]}",
              file=_err())
        return 2
    now = session.now
    if _peer_specs() or _configured("registry"):
        session.book.absorb(session.fold())
        session.book.commit()
    book, ontology = session.book, session.catalogue
    root, snapshot = book.snapshot()
    revealed = sealed.revealed(beat)
    fills = _chain_fills(session)
    result = outcome(beat, revealed, snapshot, ontology, now=now, chain_fills=fills,
                     baseline=baseline_proposals(snapshot, ontology, now=now, chain_fills=fills))
    print(f"beat {beat}: {len(revealed)} revealed, {result.candidates} candidate loop(s), "
          f"{len(result.winners)} winner(s), score {float(result.score):.4f}", file=out)
    for lid, why in sorted(result.rejected.items()):
        print(f"  rejected {lid[:16]}…: {why}", file=out)
    for lid, why in sorted(result.dropped.items()):
        print(f"  dropped  {lid[:16]}…: {why}", file=out)
    for c in result.winners:
        _print_loop(c.proposal.loop, snapshot, out, prefix=f"  wins ({c.solver}) ")
    if args.check or not result.winners:
        return 0 if result.winners else 1
    clearing = ChainClearing(book, ontology, beat_client=_beat_client(session), clock=lambda: now)
    posted = []
    for c in result.winners:
        receipt = clearing.submit(c.proposal)
        if receipt.accepted:
            posted.append((c.loop_id, receipt.reason))
            print(f"  posted {receipt.reason}: loop {c.loop_id[:16]}…", file=out)
        else:
            print(f"  refused {c.loop_id[:16]}…: {receipt.reason}", file=_err())
    sealed.record(beat, result.revealed_set, result.winners_hash)
    book.store.put(f"auction/{beat}", {"v": 1, "beat": beat, "book_root": root,
                                       "revealed_set": result.revealed_set.hex(),
                                       "winners": [{"loop": lid, "beat": r} for lid, r in posted],
                                       "solver": "loop-cli"})
    book.commit()
    print(f"recorded beat {beat}: {len(posted)} loop(s) posted, book root {book.store.root}", file=out)
    return 0 if posted else 1


def cmd_clearing(args, session, out):
    """Run the clearing house locally: MockClearing over the fold, fills
    committed to my book. Named for what it does; `clear` means delete on
    every terminal, and publishing is not clearing (Peter, 2026-09-12) —
    it stays as a silent alias for one release. With peers, my book first absorbs the fold — a
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
                  f"{100 * float(q(rec['surplus'])):.2f}%", file=out)
            for leg in rec["legs"]:
                gives = [book.get(g) for g in leg.get("gives", [leg["give"]])]
                print("  " + _leg_line(gives, book.get(leg["want"])), file=out)
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
    if args.key in ("require_point", "require_cancel") and value:
        try:
            amount = q(value)
        except Exception as exc:              # noqa: BLE001
            raise ValueError(f"{args.key} is an amount: {exc}") from None
        if amount < 0:
            raise ValueError(f"{args.key} is a non-negative amount")
    if args.key == "ladder" and value and value not in ("linear", "late", "early", "flat"):
        raise ValueError("ladder is linear, late, early or flat")
    if args.key == "terms":
        for term in shlex.split(value):
            # a name is checked when an offer uses it (fails closed, U7);
            # what can be checked now is the spelling of what is not a name
            if "(" in term and _dims.split_term(term) is None:
                raise ValueError(f"{term!r} is not a term head(param) — "
                                 f"terms are e.g. 'home ..+90d'")
            if "," in term:
                parse_coords(term)
            elif _looks_like_time(term):
                window(term, session.now)
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
  loop want PART + PART... PRICE   a composed want: parts that clear together
  loop draft [NAME] want|give ...  stage a resolved offer or part (a local file, not the book)
  loop draft [NAME] A + B ...      compose drafts into one (want side only)
  loop drafts | discard [NAME...]  list drafts / drop them (all, if none named)
  loop offer NAME [PRICE]          a draft becomes an offer: block, question, publish
  loop withdraw ID           tombstone one of my offers (id or unique prefix)
  loop mine                  my offers, all states
  loop place NAME LAT,LON,R [ADDRESS...]  a place node under its cell; the address
                             is settlement text, sealed to the cleared counterparty
  loop handoff ID TEXT...    what my offer's cleared counterparty may read
  loop watch [--once]        poll the fold: my fills, seal handoffs, open incoming
  loop handoffs              what counterparties sealed to me (opened with bee_signer)
  loop offers [CATEGORY...]  open offers in the fold (filtered by satisfies)
  loop show ID               one offer, fully — the approval block
  loop matches               every feasible handoff in the fold
  loop announce [--role maker|clearing]  say "my book is here" on the registry
  loop announced             the standing announcements: owner, book, role
  loop fold                  fold the announced books and peers myself; print the root
  loop loops                 profitable loops on a snapshot (exit 1: none)
  loop clearing              run the clearing house locally over the fold (exit 1: none)
  loop propose               clear locally and post each loop as a beat on the clearing contract
  loop beats [--open]        the beats on the contract: submitter, root, fills, state
  loop challenge BEAT [LEG] [--check] [--book SPEC]
                             re-verify a beat from its loop record, off chain and by the
                             contract's own verifier; convict a leg it would fail
  loop finalize BEAT         record a beat's fills on chain after its window
  loop deposit [ID] [--check]  fund my gives' declared bonds on the escrow contract
  loop commit                seal this session's loops for the current sealed beat
  loop reveal [BEAT]         open the sealed bundle in the beat's reveal phase
  loop outcome [BEAT] [--check]  derive a closed beat's winners (reserve bid, fairness
                             filter, deterministic selection); post them to the clearing contract
  loop sealed [BEAT]         the sealed beat's phase, window, committers and reveals
  loop status                roots, counts, settings in force
  loop set [KEY [VALUE]]     show / change a durable setting
  loop export | import [FILE]   offers as JSON lines of canonical records
  loop help | --version

Grammar (ontodag's, plus two conventions): a bare word is a category; a
term is head(param) in ontodag's spelling — quote the parentheses in a
shell; a bare number FIRST is the quantity — [MIN..]QTY[UNIT][:STEP]:
10kg = up to 10 kg divisible, 3 = three indivisible, 1000:1 = a thousand by
the piece, 50kg..100kg:25 = a hundred kilos in 25 kg sacks, fifty at least
(a give's floor) — and a bare number LAST is the price. An omitted price
is your last unit price for the same thing, scaled, and marked.
Every term is the catalogue's. A bare place (PLACE, or LAT,LON,R) is where
the offer holds and a bare window (A..B, today..+7d) is when; from(), to(),
depart(), arrive() are a route's or a transport's two ends. Place and time
match when one side contains the other (a seller delivering anywhere in the
city serves a want at a door); omit them on a want and it does not care,
omit them on a give and it says nothing. The one head the
CLI interprets is valid(DURATION|A..B|A..) — how long the offer stands
(A.. is until withdrawn). Relative time and LAT,LON,R are input spellings.
A composed want (`+` between parts, one price last) renders and is refused
until the v4 record carries parts (docs/plans/cli.md §13).
Time: now, today, tomorrow, +90d, -2h, ISO dates, A..B.

  loop give 10kg apple 100
  loop want ride my_home 'today..+7d' 5
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

    for verb, fn in (("give", cmd_give), ("want", cmd_want),
                     ("draft", cmd_draft), ("offer", cmd_offer)):
        p = sub.add_parser(verb, add_help=False)
        p.add_argument("tokens", nargs=argparse.REMAINDER)
        p.set_defaults(func=fn)

    p = sub.add_parser("drafts", add_help=False)
    p.set_defaults(func=cmd_drafts)

    p = sub.add_parser("discard", add_help=False)
    p.add_argument("refs", nargs="*")
    p.set_defaults(func=cmd_discard)

    p = sub.add_parser("withdraw", add_help=False)
    p.add_argument("id")
    p.set_defaults(func=cmd_withdraw)

    p = sub.add_parser("mine", add_help=False)
    _add_output_flags(p)
    p.set_defaults(func=cmd_mine)

    p = sub.add_parser("place", add_help=False)
    p.add_argument("name")
    p.add_argument("coords")
    p.add_argument("address", nargs="*")
    p.set_defaults(func=cmd_place)

    p = sub.add_parser("handoff", add_help=False)
    p.add_argument("id")
    p.add_argument("text", nargs="*")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("handoffs", add_help=False)
    _add_output_flags(p)
    p.set_defaults(func=cmd_handoffs)

    p = sub.add_parser("watch", add_help=False)
    p.add_argument("--once", action="store_true")
    _add_output_flags(p)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("propose", add_help=False)
    p.set_defaults(func=cmd_propose)
    p = sub.add_parser("finalize", add_help=False)
    p.add_argument("beat")
    p.set_defaults(func=cmd_finalize)
    p = sub.add_parser("deposit", add_help=False)
    p.add_argument("id", nargs="?", default=None)
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_deposit)
    p = sub.add_parser("commit", add_help=False)
    p.set_defaults(func=cmd_commit)
    p = sub.add_parser("reveal", add_help=False)
    p.add_argument("beat", nargs="?", default=None)
    p.set_defaults(func=cmd_reveal)
    p = sub.add_parser("outcome", add_help=False)
    p.add_argument("beat", nargs="?", default=None)
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_outcome)
    p = sub.add_parser("sealed", add_help=False)
    p.add_argument("beat", nargs="?", default=None)
    p.set_defaults(func=cmd_sealed)
    p = sub.add_parser("beats", add_help=False)
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_beats)
    p = sub.add_parser("challenge", add_help=False)
    p.add_argument("beat")
    p.add_argument("leg", nargs="?", default=None)
    p.add_argument("--check", action="store_true")
    p.add_argument("--book", default=None)
    p.set_defaults(func=cmd_challenge)
    p = sub.add_parser("announce", add_help=False)
    p.add_argument("--role", choices=("maker", "clearing"), default=None)
    p.set_defaults(func=cmd_announce)
    p = sub.add_parser("announced", add_help=False)
    p.set_defaults(func=cmd_announced)
    p = sub.add_parser("fold", add_help=False)
    p.set_defaults(func=cmd_fold)
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

    for name in ("clearing", "clear"):          # `clear`: alias, one release
        p = sub.add_parser(name, add_help=False)
        p.set_defaults(func=cmd_clearing)

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
    "--terms": "terms", "--valid": "valid",
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
