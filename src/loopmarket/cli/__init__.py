"""`loop` — the command line for loopmarket (docs/plans/cli.md, built 2026-09-12).

The CLI is the contract between whatever talks to a human — a person at a
prompt, a shell script, an assistant — and the strict protocol beneath. The
protocol stays strict and dumb (points, bands refused, unknown vocabulary
fails closed); the CLI adds *deterministic* kindness — defaults, the price
memory, the direction rule, the approval block — every one a small tested
rule printed in words. Judgement lives above it, never below it.

Design rules this module obeys (cli.md, settled with Peter 2026-09-11/12):

* **One grammar.** A token after the verb is a bare category, an ontodag
  term `head(param)`, or one of three loopmarket conventions: a bare
  number *first* is the quantity, a bare number *last* is the price, and
  `+` separates the parts of a composed want. Nothing else bare is
  reserved; there is no alias mechanism; `key=value` was rejected as a
  second grammar.
* **Names live in the catalogue.** A place is a node under the geo cell its
  radius fits in; `place NAME LAT,LON,R [ADDRESS]` is the bridge until odag
  accepts coordinates (cli.md §11.1). Private names are written to odag's *active*
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
runner, the tty-versus-pipe rendering switch). Two places still reach into
odag's CLI module: `_open_catalogue` (odag's `Session` opens a store spec)
and `Session._open` (`_normalize_spec`), both in `stores`, until ontodag
ships a public opener (cli.md §11.3).

The package has one module per area: `settings` (the settings table, the
config files, the output streams), `stores` (the session and the stores
it opens), `spellings` (input) and `render` (output), `grammar` (the offer
line), `guarantees`, `entry` (publishing offers), `drafts`, `options`,
`book` (reading the book and the announcements), `clients` (the
contracts and registers beyond the book), `solving`, `beats`, `deposits`,
`registers`, `claims`, `watch`, and `shell` (help, set, the parser,
dispatch, the prompt, `main`). This module re-exports the public pieces
and the internals the tests read. A test replaces a function on the
module that defines it, where every caller looks it up
(`cli.stores._open_book`, `cli.clients._beat_client`, `_escrow_client`,
`_MEMORY_SEALED`); replaced on this package it would reach no caller.
"""

from .. import __version__
from .claims import _public_key_for
from .clients import _register_at, _registers
from .entry import line_for, offer_from_line
from .grammar import (Composed, Parsed, Part, _unknown_hint, parse_offer_tokens, parse_part_tokens,
                      parse_want_line, part_line)
from .options import DEMAND_LOOKBACK
from .registers import _transfer_faults
from .render import reading, reading_for, render_offer
from .settings import (_ERR, _OUT, _OVERRIDES, _SETTINGS, _config_path, _configured, _read_config,
                       _write_config)
from .shell import _GLOBAL_FLAGS, HELP_TEXT, PARSER, build_parser, dispatch, main, run_stream
from .spellings import (PART_SEP, _INTERPRETED_HEADS, _iso, duration_s, parse_coords, parse_now,
                        radius_m, validity, window)
from .stores import Session, _addressing_of, _open_book
from .watch import _gives_of, _leg_of

__all__ = [
    # the public pieces (docs/REFERENCE.md §17)
    "dispatch", "run_stream", "main", "Session", "offer_from_line", "line_for",
    "parse_offer_tokens", "parse_want_line", "parse_part_tokens", "Parsed", "Composed", "Part",
    "part_line", "PART_SEP", "window", "validity", "duration_s", "radius_m", "parse_coords",
    "parse_now", "reading", "reading_for", "render_offer", "DEMAND_LOOKBACK", "HELP_TEXT",
    "build_parser", "PARSER", "__version__",
    # internals the tests read
    "_ERR", "_OUT", "_OVERRIDES", "_SETTINGS", "_GLOBAL_FLAGS", "_INTERPRETED_HEADS",
    "_config_path", "_configured", "_read_config", "_write_config", "_iso", "_unknown_hint",
    "_open_book", "_addressing_of", "_registers", "_register_at", "_transfer_faults",
    "_public_key_for", "_leg_of", "_gives_of",
]
