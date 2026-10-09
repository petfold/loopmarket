"""The shell: `help` and `set`, the argument parser, dispatch, the batch and
prompt runner, and `main`, in odag's mode: silent on success, errors on
stderr as `loop: ...`, exit codes a script can test."""

from __future__ import annotations

import argparse
import shlex
import sys

from ontodag import dimensions as _dims

from .. import __version__
from ..schema import q
from .beats import cmd_beats, cmd_challenge, cmd_finalize
from .book import (cmd_announce, cmd_announced, cmd_export, cmd_fold, cmd_import, cmd_matches, cmd_mine,
                   cmd_offers, cmd_show, cmd_status)
from .claims import (cmd_answer, cmd_arbitrators, cmd_cases, cmd_claim, cmd_contact_card, cmd_cure,
                     cmd_hold, cmd_notice, cmd_rule)
from .deposits import _escrow_act, cmd_collect, cmd_deposit, cmd_reservations
from .drafts import cmd_discard, cmd_draft, cmd_drafts
from .entry import cmd_exercise, cmd_give, cmd_offer, cmd_option, cmd_place, cmd_want, cmd_withdraw
from .options import _premium_rule, _window_rule, cmd_holds
from .registers import cmd_cred, cmd_register
from .settings import (_ERR, _OUT, _OVERRIDES, _SETTINGS, _book_spec, _configured, _err, _out,
                       _read_config, _want_limit, _write_config)
from .solving import cmd_clearing, cmd_commit, cmd_loops, cmd_outcome, cmd_propose, cmd_reveal, cmd_sealed
from .spellings import _looks_like_time, parse_coords, parse_now, validity, window
from .stores import Session
from .watch import cmd_handoff, cmd_handoffs, cmd_watch


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
    if args.key == "deductible" and value:
        try:
            amount = q(value)
        except Exception as exc:              # noqa: BLE001
            raise ValueError(f"deductible is an amount: {exc}") from None
        if amount < 0:
            raise ValueError("deductible is a non-negative amount")
    if args.key == "require_door" and value and value not in ("possession", "photo"):
        raise ValueError("require_door is possession or photo")
    if args.key == "oracle" and value and value not in ("countersign", "possession", "photo-match"):
        from ..witness import transfer_register
        if not transfer_register(value):
            raise ValueError("oracle is countersign, possession, photo-match or registry-transfer(REGISTER)")
    if args.key == "options" and value and value not in ("on", "off"):
        raise ValueError("options is on or off")
    if args.key == "option_window" and value:
        _window_rule(value)
    if args.key == "option_premium" and value:
        _premium_rule(value)
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
  loop option ID [--until T] [--premium X] [--for WANT]  an option on my give: held for its holder until T;
                             left out, the window and premium are option_window/option_premium's (v6)
  loop exercise OPTION... PRICE  want the options' offers as their holder, while the windows are open;
                             several: one composed want, all or nothing
  loop holds                 every hold in the fold, its holder and what is left of it
  loop mine                  my offers, all states
  loop place NAME LAT,LON,R [ADDRESS...]  a place node under its cell; the address
                             is settlement text, sealed to the cleared counterparty
  loop handoff ID TEXT...    what my offer's cleared counterparty may read
  loop watch [--once]        poll the fold: my fills, seal handoffs, open incoming
  loop handoffs              what counterparties sealed to me (opened with bee_signer)
  loop offers [CATEGORY...]  open offers in the fold (filtered by satisfies)
  loop show ID               one offer, fully — the approval block
  loop matches               every feasible handoff in the fold
  loop announce [--role maker|clearing|register]  say "my book is here" on the registry
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
  loop reservations [--all]  the escrow's reservations behind my legs, and their state
  loop countersign OFFER [--loop L]   as the wanter: delivered, return the reservation
  loop cancel OFFER [--loop L]        as the giver: cancel the leg, the ladder's amount to the wanter
  loop assign OFFER KEY [--loop L]    as the wanter: assign my claim on it to KEY
  loop settle OFFER [SPLIT] [--loop L]  quiet after the claim period; with SPLIT (all, N%,
                             NxDAI, or on my scale) my signature of a split, the second settling
  loop extend-claim OFFER DURATION [--loop L]  as the giver: lengthen the claim period
  loop collect [--check]     payouts my address refused, waiting for me
  loop contact-card          write my contact card (my public key) into my book: anyone may seal to me
  loop claim OFFER AMOUNT [--evidence R] [--text T] [--loop L]
                             as the wanter: claim on a reservation before its named arbitrator
  loop answer OFFER [--evidence R] [--text T] [--loop L]   as the giver: answer the claim
  loop hold OFFER [--loop L]   as the arbitrator: the claim is open, the timeout stops
  loop rule OFFER AMOUNT --reason TEXT [--loop L]   as the arbitrator: rule, final
  loop cases                 the claims, answers and rulings involving me
  loop arbitrators [--trust KEYS]   a personal view: arbitrators my circle chose,
                             their rulings, who lost under one and chose it again
  loop cred [SUBJECT]        statements presented about SUBJECT (me), with their state
  loop cred present FILE     present a statement about me in my book
  loop register issue|revoke|suspend|reinstate|accredit|transfer|heartbeat|status ...
                             run a register in this session's book (`-f SPEC`)
  loop notice OFFER --cure DURATION [--fact STATEMENT] [--loop L]
                             as the wanter: tell the giver which fact is wrong, sealed
  loop cure OFFER [--evidence REF] [--loop L]  as the giver: answer a notice, sealed back
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
A composed want (`+` between parts, one price last) is one v4 offer: all
the parts or nothing, one price (docs/plans/cli.md §13).
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

    p = sub.add_parser("option", add_help=False)
    p.add_argument("id")
    p.add_argument("--until", default=None)
    p.add_argument("--premium", default=None)
    p.add_argument("--for", dest="for_want", default=None)
    p.set_defaults(func=cmd_option)
    p = sub.add_parser("exercise", add_help=False)
    p.add_argument("args", nargs="*")               # OPTION [OPTION...] PRICE
    p.set_defaults(func=cmd_exercise)
    p = sub.add_parser("holds", add_help=False)
    p.set_defaults(func=cmd_holds)

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
    p = sub.add_parser("reservations", add_help=False)
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_reservations)
    for verb, extra in (("countersign", ()), ("cancel", ()), ("assign", ("to",)),
                        ("extend-claim", ("duration",)), ("settle", ("split?",))):
        p = sub.add_parser(verb, add_help=False)
        p.add_argument("offer")
        for name in extra:
            if name.endswith("?"):
                p.add_argument(name[:-1], nargs="?", default=None)
            else:
                p.add_argument(name)
        p.add_argument("--loop", default=None)
        p.set_defaults(func=lambda a, s, o, _v=verb: _escrow_act(a, s, o, _v))
    p = sub.add_parser("collect", add_help=False)
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_collect)
    p = sub.add_parser("contact-card", add_help=False)
    p.set_defaults(func=cmd_contact_card)
    p = sub.add_parser("claim", add_help=False)
    p.add_argument("offer"); p.add_argument("amount")
    for flag in ("--loop", "--evidence", "--text"):
        p.add_argument(flag, default=None)
    p.set_defaults(func=cmd_claim)
    p = sub.add_parser("answer", add_help=False)
    p.add_argument("offer")
    for flag in ("--loop", "--evidence", "--text"):
        p.add_argument(flag, default=None)
    p.set_defaults(func=cmd_answer)
    p = sub.add_parser("hold", add_help=False)
    p.add_argument("offer"); p.add_argument("--loop", default=None)
    p.set_defaults(func=cmd_hold)
    p = sub.add_parser("rule", add_help=False)
    p.add_argument("offer"); p.add_argument("amount")
    p.add_argument("--loop", default=None); p.add_argument("--reason", default=None)
    p.set_defaults(func=cmd_rule)
    p = sub.add_parser("cases", add_help=False)
    p.set_defaults(func=cmd_cases)
    p = sub.add_parser("arbitrators", add_help=False)
    p.add_argument("--trust", default=None)
    p.set_defaults(func=cmd_arbitrators)
    p = sub.add_parser("cred", add_help=False)
    p.add_argument("action", nargs="?", default=None)
    p.add_argument("rest", nargs="*")
    p.add_argument("--presentation", default=None)
    p.set_defaults(func=cmd_cred)
    p = sub.add_parser("register", add_help=False)
    p.add_argument("action")
    p.add_argument("rest", nargs="*")
    for flag in ("--until", "--since", "--as-of", "--evidence", "--kind", "--paid-by", "--deposit", "--scheme"):
        p.add_argument(flag, default=None)
    p.add_argument("--path", action="append", default=None)
    p.set_defaults(func=cmd_register)
    p = sub.add_parser("notice", add_help=False)
    p.add_argument("offer")
    p.add_argument("--loop", default=None)
    p.add_argument("--fact", default=None)
    p.add_argument("--cure", required=True)
    p.set_defaults(func=cmd_notice)
    p = sub.add_parser("cure", add_help=False)
    p.add_argument("offer")
    p.add_argument("--loop", default=None)
    p.add_argument("--evidence", default=None)
    p.set_defaults(func=cmd_cure)
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
    p.add_argument("--role", choices=("maker", "clearing", "register"), default=None)
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

    for name in ("clearing", "clear"):          # `clear`: a silent alias
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
    session._registers = None           # each command reads the registers' heads afresh
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
# Every setting's documented flag is a real one: `loop help` prints each
# setting's flag, and until 2026-10-09 thirty of them were not accepted
# (`loop --registry memory: status` was an argparse error).
for _key, _setting in _SETTINGS.items():
    if _setting.flag and _setting.flag.startswith("--") and "/" not in _setting.flag:
        _GLOBAL_FLAGS.setdefault(_setting.flag.split()[0], _key)


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
