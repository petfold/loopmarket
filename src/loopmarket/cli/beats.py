"""A posted beat, after: `beats` lists them, `challenge` re-verifies one from
its loop record, off chain and by the contract's own verifier, and
`finalize` records its fills and reserves the deposits behind them."""

from __future__ import annotations

from fractions import Fraction

from ..registry import LegRecord
from ..schema import q
from . import clients, stores
from .clients import _register_at, _registers, _resolver_profiles
from .render import _leg_line, _num
from .settings import _configured, _err
from .spellings import _calendar_span, _seconds_or_zero, duration_s


def cmd_finalize(args, session, out):
    """Record a beat's fills on chain once its challenge window has closed
    — and, with an escrow set, reserve on it the share of every deposit the
    loop's legs rely on (2026-09-19): the fills becoming the chain's
    authority is the moment the deposits behind them are locked per fill;
    the loop record is found as `challenge` finds it, the reservation built
    by `escrow.reservations_for`, `claim` the period after the window in
    which a claim may be opened (`escrow_claim`), the resolver the give's
    arbitrator, else the `resolver` setting (factbond's `Assertions`), else
    my own key, or, when either side constrains it, the first candidate both
    accept. A beat whose fills no longer fit what
    the chain recorded since it was posted (another beat took the same
    offers first) is cancelled by the contract instead, its bond returned
    to the submitter — nothing is recorded and nothing reserved (exit 1)."""
    from ..beat import find_evidence, proposal_from_record
    from ..escrow import cover_predicate, reservations_for
    client = clients._beat_client(session)
    receipt = client.finalize(int(args.beat))
    state = client.beat(int(args.beat))
    if state["cancelled"]:
        print(f"beat {args.beat} cancelled at finalize: its fills no longer fit what the chain "
              f"has recorded since (another beat took the offers first); the bond went back "
              f"to the submitter, gas {receipt['gasUsed']}", file=out)
        return 1
    print(f"finalized beat {args.beat}: {state['fills']} fills, gas {receipt['gasUsed']}", file=out)
    if not (_configured("escrow") or "").startswith("chain:"):
        return 0
    ev = find_evidence(state, _evidence_books(session, state, None), ontology=session.catalogue)
    if ev is None:
        print(f"loop: beat {args.beat}: no loop record found, nothing reserved on the escrow", file=_err())
        return 2
    escrow = clients._escrow_client(session)
    proposal = proposal_from_record(ev.record, ev.snapshot)
    from ..gate import CounterpartyGate
    at = _register_at(session)
    pinned = {rid: at(rid, root) for rid, root in (ev.record.get("register_roots") or {}).items()}
    gate = CounterpartyGate.over(ev.snapshot, {r: g for r, g in pinned.items() if g is not None},
                                 now=session.now, span=_calendar_span, latest=_registers(session).get,
                                 profile=_resolver_profiles(session))
    try:
        reservations = reservations_for(
            proposal, escrow=escrow.address, resolver=_configured("resolver") or escrow.account().address,
            claim_seconds=duration_s(_configured("escrow_claim") or "7d"), now=session.now,
            span=_calendar_span, claim_only=cover_predicate(session.catalogue),
            min_challenge=_seconds_or_zero(_configured("claim_min_challenge")),
            min_ruling=_seconds_or_zero(_configured("claim_min_ruling")),
            gate=gate, ontology=session.catalogue)
    except ValueError as exc:                  # a party as resolver, an unaccepted one: nothing reserved
        print(f"loop: beat {args.beat}: nothing reserved on the escrow: {exc}", file=_err())
        return 2
    for r in reservations:
        try:
            escrow.reserve(r["offer_id"], r["loop_id"], r["wanter"], r["resolver"], r["amount"],
                           window=r["window"], claim_seconds=r["claim_seconds"], ladder=r["ladder"],
                           claim_only=r["claim_only"], min_challenge=r["min_challenge"],
                           deductible=r["deductible"], covers=r["covers"],
                           min_ruling=r["min_ruling"])
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
    client = clients._beat_client(session)
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
        return [stores._open_book(spec)]
    books = []
    if _configured("registry"):
        mine = sorted((ann for ann in session.announcements.announced()
                       if ann.owner.lower() == state["submitter"].lower()),
                      key=lambda ann: ann.role != "clearing")
        for ann in mine:
            try:
                books.append(stores._open_book(ann.spec()))
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
    from ..beat import challenge_beat
    client = clients._beat_client(session)
    state = client.beat(int(args.beat))
    print(_beat_state_line(state), file=out)
    books = _evidence_books(session, state, args.book)
    now = session.now if _configured("now") else None
    index = int(args.leg) if args.leg is not None else None
    can_send = bool(_configured("bee_signer"))
    result = challenge_beat(client, int(args.beat), books, session.catalogue, now=now,
                            index=index, send=not args.check and can_send,
                            register_at=_register_at(session), span=_calendar_span)
    if result.evidence is None:
        print(f"no evidence: no loop record under root {state['book_root'][:16]}… hashes to "
              f"the beat's commitments in {len(books)} book(s) — the contract cannot "
              f"convict what nobody has seen; do not rely on this beat", file=_err())
        return 2
    rec, book = result.evidence.record, result.evidence.snapshot
    print(f"loop {rec['loop_id'][:16]}… surplus {100 * float(q(rec['surplus'])):.2f}%, "
          f"solver {rec.get('solver', '?')}", file=out)
    for verdict, leg in zip(result.legs, LegRecord.of_loop(rec)):
        gives = [book.get(g) for g in leg.gives]
        off = "holds" if verdict.local is None else verdict.local
        on = verdict.chain or "no verdict (the node would not run the call)"
        print(f"  [{verdict.index}] {_leg_line(gives, book.get(leg.want))}", file=out)
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
