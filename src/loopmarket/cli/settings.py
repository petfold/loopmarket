"""Settings: one table, one precedence rule (odag's), and the files kept in
the loop home.

flag > global flag > environment > loop config > odag config > default:
`~/.loopmarket/config` in odag's `key = value` format, and the settings the
two tools share (`bee_*`, the default catalogue) inherited from
`~/.ontodag/config`. The flag layer is `_OVERRIDES`, which `shell.main`
fills for one invocation. Output goes through two ContextVars, so an
embedder captures both streams (`shell.dispatch`)."""

from __future__ import annotations

import contextvars
import json
import os
import sys
from collections import namedtuple


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
        "LOOP_DEFAULT_ASSET", "", "--default-asset 'CATEGORY UNIT PRICE'",
        "the asset a bare-number `bond` deposits and a `require_point` with "
        "no `require_accepts` accepts, with MY price per unit on my scale — "
        "e.g. `xdai xDAI 1.2` for the chain's gas token. No default "
        "(2026-09-29, Peter): the price is my own judgement, so a bare amount "
        "that needs it is refused until I state it; the record names the asset "
        "explicitly, and the protocol names none"),
    "escrow": _Setting(
        "LOOP_ESCROW", "", "--escrow SPEC",
        "the escrow contract holding my deposit: chain:RPC_URL@CONTRACT "
        "(LoopEscrow; the record names the address); `deposit [ID]` funds "
        "a give's declared bond there (empty: a declaration only)"),
    "trust": _Setting(
        "LOOP_TRUST", "", "--trust KEYS",
        "makers whose choices of arbitrators I count beside my own in "
        "`loop arbitrators` (a personal view: never a gate)"),
    "registers": _Setting(
        "LOOP_REGISTERS", "", "--registers ID=SPEC...",
        "registers I read (R3a) beyond those announced under the register "
        "role: ID=SPEC pairs, a register's book by spec (`rs:PATH`, "
        "`swarm:TOPIC@OWNER`); each is read at its head, pinned in my "
        "proposals, and consulted for credentials, accredited resolvers and "
        "watch's lapsed statements"),
    "resolver": _Setting(
        "LOOP_RESOLVER", "", "--resolver ADDRESS",
        "who resolves a contested claim on a deposit my clearing reserves: "
        "factbond's Assertions contract (a give's declared arbitrator wins); "
        "empty: my own key rules directly. The deployed Assertions "
        "0x3c1B…e270 is for test amounts only: its adjudicator and final "
        "rung are the operator's own keys, a stand-in until a named, "
        "independent final rung exists"),
    "escrow_claim": _Setting(
        "LOOP_ESCROW_CLAIM", "7d", "--escrow-claim DURATION",
        "how long after a leg's handover window a claim on its deposit may "
        "be opened before the reservation returns to the giver by itself, "
        "when the want asks none (never beyond the give's claim_max)"),
    "claim_min_challenge": _Setting(
        "LOOP_CLAIM_MIN_CHALLENGE", "", "--claim-min-challenge DURATION",
        "the least dispute window a claim on a reservation my clearing makes "
        "must leave the giver (the escrow refuses a shorter one at `hold`); "
        "0: the resolver's own bound"),
    "claim_min_ruling": _Setting(
        "LOOP_CLAIM_MIN_RULING", "", "--claim-min-ruling DURATION",
        "the least ruling window such a claim must name: the claim class's "
        "evidence period plus its rung's ruling period; 0: the resolver's own"),
    "arbitrator": _Setting(
        "LOOP_ARBITRATOR", "", "--arbitrator ADDRESS",
        "the arbitrator my gives name for claims on their deposit — by "
        "default one key both sides accept, whose ruling is final (chosen by "
        "reputation or accreditation); factbond's Assertions, a bonded "
        "ladder, is the option for higher stakes among strangers; never "
        "mine; a want requiring resolvers matches only a give naming one it "
        "accepts; empty: the clearing's `resolver`"),
    "deductible": _Setting(
        "LOOP_DEDUCTIBLE", "", "--deductible AMOUNT",
        "what a ruled claim on my deposit leaves with me, on my scale like "
        "`bond`: held as the deposit's asset at the price my deposit states "
        "(its worth per unit), for the give's whole quantity like the deposit "
        "(a fill takes its share); a claim pays what it is, at most the "
        "reservation, less it (C5, a v7 record). A deposit counts against a "
        "wanter's neutral point only up to what it can pay"),
    "claim_max": _Setting(
        "LOOP_CLAIM_MAX", "", "--claim-max DURATION",
        "the longest claim period my give's deposit carries after the "
        "handover window (v6, plan A1); a want asking longer is not matched. "
        "The clearing contracts read v6 records since their 2026-09-29 redeploy"),
    "options": _Setting(
        "LOOP_OPTIONS", "off", "--options on|off",
        "on: every plain give I publish also writes its option — the right "
        "to hold it, for `option_window` at `option_premium` — both shown in "
        "one approval block (2026-09-29); off by default"),
    "option_window": _Setting(
        "LOOP_OPTION_WINDOW", "1/4", "--option-window FRACTION|DURATION",
        "how long an option on my offer may be held: a fraction of the lead "
        "to the offer's handover time (its validity's end without one), or a "
        "duration; the window closes before the handover, so a lapsed hold "
        "leaves time to sell again"),
    "option_premium": _Setting(
        "LOOP_OPTION_PREMIUM", "suggest", "--option-premium suggest|N%|AMOUNT",
        "what an option on my offer costs, on my scale: `suggest` (the "
        "chance a buyer comes during the hold and none after it, from the "
        "book's demand for the thing, times the price, the holder assumed to "
        "exercise half the time), a percentage of the offer's price, or an "
        "amount"),
    "require_claim": _Setting(
        "LOOP_REQUIRE_CLAIM", "", "--require-claim DURATION",
        "the claim period I ask of a giver's deposit (v6): only gives whose "
        "claim_max reaches it are matched"),
    "require_resolvers": _Setting(
        "LOOP_REQUIRE_RESOLVERS", "", "--require-resolvers ACCEPT",
        "the resolvers I accept for a claim on a deposit — the giver's, and on "
        "my gives my own (v6, E2; §7a): keys, and/or by property — `root:ID` "
        "(its rungs accredited as arbitrators under a register I trust), "
        "`min:AMOUNT` (at least that at stake on a reversed ruling, on my "
        "scale, priced by my acceptances), `clean:DURATION` (no ruling "
        "reversed within it, on a record at least that long); a leg's "
        "resolver is the first both sides accept, never a party to it"),
    "require_credentials": _Setting(
        "LOOP_REQUIRE_CREDENTIALS", "", "--require-credentials ENTRIES",
        "what my wants require the giver to present (v6, R4): entries "
        "separated by `;`, each `CATEGORY KIND[,KIND...] [root:ID]... "
        "[age:DURATION] [min:AMOUNT]` — a statement of a category under "
        "CATEGORY, of one of the kinds (attested, signed, self-bonded), "
        "reaching a named root through registers no older than age, its "
        "deposit's free share at least min on my scale; unmet is never "
        "matched"),
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
    "require_door": _Setting(
        "LOOP_REQUIRE_DOOR", "", "--require-door possession|photo",
        "the door witness my wants require of the person at the handover: "
        "`possession` (the default meaning: a fresh challenge signed with "
        "their key — they control it, nothing else is learned) or `photo` "
        "(possession plus the attested photo, which hands the counterparty a "
        "provable link from their face to their key: ask it only where the "
        "stakes need it, THREATS T19); empty: none"),
    "require_transfer": _Setting(
        "LOOP_REQUIRE_TRANSFER", "", "--require-transfer REGISTERS",
        "for registered goods (land, vehicles; I4): the title registers whose "
        "transfer of the item to me my wants accept as the handover witness "
        "— a give declaring `registry-transfer(ID)` for one of them; the leg "
        "is performed when that register shows the item held by me"),
    "oracle": _Setting(
        "LOOP_ORACLE", "countersign", "--oracle TYPE",
        "the witness my gives settle against: countersign (default), "
        "possession (I sign a fresh challenge at the door) or photo-match "
        "(possession plus my attested photo — the counterparty's device "
        "receives it and can link my face to my key, THREATS T19), or, for a "
        "registered item, registry-transfer(REGISTER) (the title register's "
        "transfer to the wanter is the performance, I4)"),
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
# Files in the loop home
# --------------------------------------------------------------------------- #

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
