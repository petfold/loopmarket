"""Statements and registers: `cred` lists the statements presented about a
key and presents mine, `register` runs a register in this session's book,
and `_transfer_faults` asks a title register whether a give was performed
(I4)."""

from __future__ import annotations

import json
import sys

from .clients import _registers
from .settings import _err
from .spellings import _iso, _until


def _statement_state(st, regs) -> str:
    reg = regs.get(st.issuer)
    if st.kind == "self-bonded":
        return "self-bonded"
    if reg is None:
        return "issuer's register not read"
    if reg.revoked(st.statement_id):
        return "revoked"
    if reg.suspended(st.statement_id):
        return "suspended"
    return "issued" if reg.status(st.statement_id) is not None else "no status in the issuer's register"


def cmd_cred(args, session, out):
    """C7 (2026-09-29 night): `cred [SUBJECT]` lists the statements
    presented about SUBJECT — me by default — in the fold, each with its
    validity and its state under the registers I read; `cred present FILE`
    presents a statement about me in my book (R2): an issuer's record as
    `register issue` prints it or hansa's adapters produce it (`-` reads
    stdin), with `--presentation FILE`, the adapter's opaque record."""
    from ..schema import Statement
    if args.action == "present":
        if len(args.rest) != 1:
            raise ValueError("cred present FILE — a statement record (JSON), `-` for stdin")
        text = sys.stdin.read() if args.rest[0] == "-" else open(args.rest[0], encoding="utf-8").read()
        st = Statement.from_record(json.loads(text))
        if st.subject.lower() != session.maker.lower():
            raise ValueError(f"the statement is about {st.subject}, not me ({session.maker}): "
                             f"a statement is presented in its subject's own book")
        presentation = json.loads(open(args.presentation, encoding="utf-8").read()) if args.presentation else None
        sid = session.book.present(st, presentation)
        session.book.commit()
        print(f"presented {sid[:16]}… {st.category} ({st.kind}, by {st.issuer}, until {_iso(st.until)})", file=out)
        return 0
    subject = args.action or session.maker
    regs = _registers(session)
    rows = [st for st, _ in session.fold().statements(subject)]
    for st in sorted(rows, key=lambda x: (x.category, x.statement_id)):
        print(f"{st.statement_id[:16]}… {st.category} {st.kind} by {st.issuer}, {_iso(st.as_of)}.."
              f"{_iso(st.until)}, path {' > '.join(st.path)}: {_statement_state(st, regs)}", file=out)
    if not rows:
        print(f"no statement presented about {subject}", file=out)
    return 0 if rows else 1


def _my_statement(reg, prefix: str) -> str:
    from ..register import STATUS
    found = sorted(k[len(STATUS):] for k, _ in reg.store.items(STATUS) if k[len(STATUS):].startswith(prefix))
    if len(found) != 1:
        raise ValueError(f"{prefix}: {'no statement' if not found else 'several statements'} in my register")
    return found[0]


def cmd_register(args, session, out):
    """C7 (2026-09-29 night): run a register (R3a) in this session's book —
    `loop -f SPEC register ...`, the register's own book, announced with
    `announce --role register`; its id is my key. `issue SUBJECT CATEGORY
    --until T --evidence HASH --paid-by subject|relier [--kind attested]
    [--path ROOT]... [--deposit OFFER@ESCROW] [--scheme HASH]` issues a
    statement and prints its record for the subject to present;
    `revoke|suspend|reinstate STATEMENT`; `accredit ISSUER CATEGORY --until
    T [--since T] [--scheme HASH]`; `heartbeat`; `status`. Every write
    heartbeats and commits: a root is a link naming its predecessor (R5)."""
    from ..register import ACCREDIT, STATUS, Register
    from ..schema import Statement
    reg, me, now = Register(session.book.store), session.maker, session.now
    act, rest = args.action, args.rest
    if act == "issue":
        if len(rest) != 2 or not args.until or not args.evidence or not args.paid_by:
            raise ValueError("register issue SUBJECT CATEGORY --until T --evidence HASH --paid-by subject|relier")
        deposit = tuple(args.deposit.split("@", 1)) if args.deposit else None
        st = Statement(subject=rest[0], category=rest[1], issuer=me, kind=args.kind or "attested",
                       as_of=_until(args.as_of, now) if args.as_of else now, until=_until(args.until, now),
                       evidence=args.evidence, path=(me, *(args.path or ())), paid_by=args.paid_by,
                       deposit=deposit, scheme=args.scheme or "")
        reg.issue(st.statement_id, now)
        said, printed = f"issued {st.statement_id[:16]}… about {st.subject}", json.dumps(st.to_record(), sort_keys=True)
    elif act in ("revoke", "suspend", "reinstate"):
        if len(rest) != 1:
            raise ValueError(f"register {act} STATEMENT")
        sid = _my_statement(reg, rest[0])
        getattr(reg, act)(sid, now)
        past = {"revoke": "revoked", "suspend": "suspended", "reinstate": "reinstated"}[act]
        said, printed = f"{past} {sid[:16]}…", None
    elif act == "accredit":
        if len(rest) != 2 or not args.until:
            raise ValueError("register accredit ISSUER CATEGORY --until T [--since T] [--scheme HASH]")
        reg.accredit(rest[0], rest[1], by=me, since=_until(args.since, now) if args.since else now,
                     until=_until(args.until, now), scheme=args.scheme or "")
        said, printed = f"accredited {rest[0]} for {rest[1]}", None
    elif act == "transfer":
        if len(rest) != 2:
            raise ValueError("register transfer ITEM TO — the item's 64-hex id (or item(h)), the new holder's key")
        h = rest[0][5:-1] if rest[0].startswith("item(") and rest[0].endswith(")") else rest[0]
        from ..items import well_formed
        if not well_formed((f"item({h})",)):
            raise ValueError(f"{rest[0]}: an item is its whole 64-hex id")
        reg.transfer(h.lower(), rest[1], now)
        said, printed = f"item {h[:12]} held by {rest[1]}", None
    elif act == "heartbeat":
        said, printed = "heartbeat", None
    elif act == "status":
        for key, rec in sorted(reg.store.items(STATUS)):
            print(f"{key[len(STATUS):][:16]}… {rec['state']} at {_iso(rec['at'])}", file=out)
        for key, rec in sorted(reg.store.items(ACCREDIT)):
            issuer, _, cat = key[len(ACCREDIT):].partition("/")
            print(f"accredit {issuer} for {cat}: {_iso(rec['since'])}..{_iso(rec['until'])}", file=out)
        from ..register import TITLE
        for key, rec in sorted(reg.store.items(TITLE)):
            print(f"title    {key[len(TITLE):][:16]}… held by {rec['holder']} since {_iso(rec['at'])}", file=out)
        at = reg.as_of
        print(f"root {reg.root or '(empty)'}, seq {reg.seq}, heartbeat {_iso(at) if at else 'none'}", file=out)
        return 0
    else:
        raise ValueError("register issue|revoke|suspend|reinstate|accredit|transfer|heartbeat|status")
    reg.heartbeat(now)
    root = reg.commit()
    if printed:
        print(printed, file=out)
    print(f"{said}; root {root[:16]}…, seq {reg.seq}", file=_err())
    return 0


def _transfer_faults(session, oid: str, loop: str, wanter: str) -> list[str]:
    """For a give declaring `registry-transfer(ID)` (I4): why the register
    ID, as I read it, does not show the give performed to `wanter` since the
    loop cleared; [] for any other witness type (the door's is the device's
    to check)."""
    from ..witness import transfer_faults, transfer_register
    fold = session.fold()
    try:
        give_ = fold.get(oid)
    except KeyError:                     # not in my fold: no declared witness I could read
        return []
    rid = transfer_register(give_.oracle)
    if not rid:
        return []
    key = f"loop/{loop}"
    since = int(fold.store.get(key).get("found_at", 0)) if fold.store.contains(key) else 0
    return transfer_faults(give_, wanter, _registers(session).get(rid), since=since)
