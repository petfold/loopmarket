"""Claims before an arbitrator, and the notices before them: contact cards,
`notice` and `cure` (R6), `claim`, `answer`, `hold` and `rule` (a case
before one named arbitrator), `cases`, and `arbitrators`, a personal view
that is never a gate."""

from __future__ import annotations

import os
from fractions import Fraction

from ..registry import LegRecord
from . import clients
from .clients import _registers
from .deposits import _asset_amount, _reservation_ref
from .registers import _statement_state
from .render import _num
from .settings import _configured, _home_dir, _write_json
from .spellings import _iso, duration_s


def _notices_path(loop: str, oid: str, kind: str) -> str:
    folder = os.path.join(_home_dir(), "notices")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return os.path.join(folder, f"{kind}-{loop[:16]}-{oid[:16]}.json")


def _public_key_of(fold, offer_id: str) -> bytes:
    """The public key of an offer's maker: the offer's own signature, else
    the maker's contact card."""
    from ..sigs import recover_public_key
    sig = fold.signature(offer_id)
    if sig is not None:
        return recover_public_key(offer_id, sig)
    return _public_key_for(fold, fold.get(offer_id).maker)


def _public_key_for(fold, address: str) -> bytes:
    """A key's public key, to seal to it: its contact card (`loop contact-card`),
    else a signature on any of its offers in the fold."""
    from ..sigs import contact_card_public_key, recover_public_key
    card = fold.contact_card(address)
    if card is not None:
        return contact_card_public_key(address, card)
    for o in fold.offers(include_filled=True):
        if o.maker.lower() == address.lower():
            sig = fold.signature(o.offer_id)
            if sig is not None:
                return recover_public_key(o.offer_id, sig)
    raise ValueError(f"{address} has no public key here: no contact card (`loop contact-card` in its book) "
                     f"and no signed offer")


def cmd_contact_card(args, session, out):
    """Write my contact card into my book (2026-10-01): a signature over a fixed
    message naming my address, so anyone may seal to me — a claim to me as
    an arbitrator, a notice when I have no signed offer — with no key
    registry. Needs bee_signer."""
    from ..sigs import sign_contact_card
    signer = _configured("bee_signer")
    if not signer:
        raise ValueError("a contact card is signed with my key: set bee_signer")
    address, sig = sign_contact_card(signer)
    session.book.publish_contact_card(address, sig)
    session.book.commit()
    print(f"contact card for {address} in my book", file=out)
    return 0


def _leg_with(fold, loop: str, give_id: str) -> LegRecord:
    for leg in fold.loop_legs(loop):
        if give_id in leg.gives:
            return leg
    raise ValueError(f"loop {loop[:16]}… is not in the fold, or took nothing from {give_id[:12]}")


# ---------------------------------------------------------------- a case before one arbitrator

def _cases_path(loop: str, oid: str, kind: str, to: str) -> str:
    folder = os.path.join(_home_dir(), "cases")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return os.path.join(folder, f"{kind}-{loop[:16]}-{oid[:16]}-{to[2:10].lower()}.json")


def _case_to(session, fold, loop: str, oid: str, kind: str, record: dict, recipients) -> list[str]:
    """Seal `record` to each recipient and write it into my book; keep the
    openings. Returns the recipients written to."""
    from ..case import sealed
    me = session.maker
    sent = []
    for to in recipients:
        if not to or to.lower() == me.lower() or to.lower() in {x.lower() for x in sent}:
            continue
        side, opening = sealed(record, sender=me, recipient=to, recipient_public_key=_public_key_for(fold, to))
        session.book.write_case(loop, oid, kind, side)
        _write_json(_cases_path(loop, oid, kind, to), opening)
        sent.append(to)
    session.book.commit()
    return sent


def _resolver_is_key(client, resolver: str) -> bool:
    try:
        return not client._web3().eth.get_code(resolver)
    except Exception:  # noqa: BLE001 — unknown: treat as a contract, the claim goes to its own channel
        return False


def cmd_claim(args, session, out):
    """As the wanter of a reservation whose resolver is one named arbitrator
    (a key, the default since 2026-10-01): claim AMOUNT of it — `all`, `N%`,
    `NxDAI`, or an amount on my scale — sealed to the arbitrator and to
    the giver (due process: the accused sees the claim), with `--evidence`
    and `--text`; the notice it follows is named when my book holds one.
    The arbitrator then holds the reservation and rules. A reservation
    whose resolver is a contract (factbond's ladder) is claimed there."""
    from ..case import claim_record, ref
    client = clients._escrow_client(session)
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    r = client.reservation(oid, loop)
    if not r["amount"]:
        raise ValueError(f"{oid[:16]}… loop {loop[:16]}…: no reservation on this escrow")
    me = client.account().address
    if r["wanter"].lower() != me.lower():
        raise ValueError(f"the claim on this reservation is {r['wanter']}'s, not mine")
    if r["settled"]:
        raise ValueError("the reservation is settled: nothing to claim")
    if not _resolver_is_key(client, r["resolver"]):
        raise ValueError(f"this reservation's resolver {r['resolver']} is a contract (a bonded ladder): "
                         f"claim there (factbond's assert), not with `loop claim`")
    amount = _asset_amount(args.amount, r["amount"])
    if not 0 < amount <= r["amount"]:
        raise ValueError(f"a claim is more than nothing and at most the reservation "
                         f"({_num(Fraction(r['amount'], 10 ** 18))})")
    fold = session.fold()
    giver = client.deposit_of(oid)["giver"]
    side = fold.notice(loop, oid)
    notice_ref = side["commitment"] if side is not None and str(side.get("from", "")).lower() == me.lower() else ""
    record = claim_record(me, giver, oid, loop, amount, sent_at=session.now, evidence_ref=args.evidence or "",
                          notice_ref=notice_ref, text=args.text or "")
    sent = _case_to(session, fold, loop, oid, "claim", record, [r["resolver"], giver])
    print(f"claim    {_num(Fraction(amount, 10 ** 18))} on {oid[:12]} in loop {loop[:16]}… sent to "
          f"{', '.join(sent)} (ref {ref(record)[:12]}); the arbitrator {r['resolver']} holds and rules"
          + ("" if notice_ref else " — no notice sent first: the arbitrator may refuse a claim the "
             "giver had no chance to cure (`loop notice`)"), file=out)
    return 0


def _claim_to_me(session, fold, loop: str, oid: str) -> dict:
    """The claim on (offer, loop) sealed to me, opened with bee_signer."""
    from ..case import read
    signer = _configured("bee_signer")
    if not signer:
        raise ValueError("opening a case record needs my key: set bee_signer")
    me = session.maker
    for loop_id, offer_id, kind, rec in fold.cases():
        if (loop_id, offer_id, kind) == (loop, oid, "claim") and str(rec.get("to", "")).lower() == me.lower():
            return read(rec, signer)
    raise ValueError(f"no claim to me on {oid[:12]} in loop {loop[:16]}…")


def cmd_answer(args, session, out):
    """As the giver: answer the claim on my reservation — `--evidence`,
    `--text` — sealed to the arbitrator and to the claimant."""
    from ..case import answer_record, ref
    client = clients._escrow_client(session)
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    r = client.reservation(oid, loop)
    fold = session.fold()
    claim = _claim_to_me(session, fold, loop, oid)
    record = answer_record(session.maker, ref(claim), time=session.now, evidence_ref=args.evidence or "",
                           text=args.text or "")
    sent = _case_to(session, fold, loop, oid, "answer", record, [r["resolver"], claim["claimant"]])
    print(f"answer   on {oid[:12]} in loop {loop[:16]}… sent to {', '.join(sent)}", file=out)
    return 0


def cmd_hold(args, session, out):
    """As the arbitrator named on a reservation: a claim is open, the quiet
    timeout stops (the escrow's `hold`, my key's own act)."""
    client = clients._escrow_client(session)
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    r = client.reservation(oid, loop)
    if r["resolver"].lower() != client.account().address.lower():
        raise ValueError(f"I am not this reservation's arbitrator ({r['resolver']})")
    receipt = client.hold(oid, loop)
    print(f"held     {oid[:12]} in loop {loop[:16]}…: the claim is open, gas {receipt['gasUsed']}", file=out)
    return 0


def cmd_rule(args, session, out):
    """As the arbitrator: rule AMOUNT of the reservation to the wanter —
    `all`, `N%`, `NxDAI`, `0`, or an amount on my scale — final; the escrow
    pays it less any deductible and the rest to the giver, and my reasons
    (`--reason`, required) go sealed to both parties. Holds first if no
    claim is held yet."""
    from ..case import ref, ruling_record
    if not args.reason:
        raise ValueError("a ruling gives its reasons: --reason TEXT")
    client = clients._escrow_client(session)
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    r = client.reservation(oid, loop)
    if r["resolver"].lower() != client.account().address.lower():
        raise ValueError(f"I am not this reservation's arbitrator ({r['resolver']})")
    if r["settled"]:
        raise ValueError("the reservation is settled: nothing to rule on")
    amount = 0 if args.amount.strip() == "0" else _asset_amount(args.amount, r["amount"])
    if amount > r["amount"]:
        raise ValueError(f"a ruling is at most the reservation ({_num(Fraction(r['amount'], 10 ** 18))})")
    fold = session.fold()
    try:
        claim_ref = ref(_claim_to_me(session, fold, loop, oid))
    except ValueError:
        claim_ref = ""                       # a claim made outside the book: rule on it all the same
    if not r["held"]:
        client.hold(oid, loop)
    receipt = client.resolve(oid, loop, amount)
    giver = client.deposit_of(oid)["giver"]
    record = ruling_record(session.maker, claim_ref, amount, time=session.now, reason=args.reason)
    sent = _case_to(session, fold, loop, oid, "ruling", record, [r["wanter"], giver])
    print(f"ruled    {_num(Fraction(amount, 10 ** 18))} to the wanter on {oid[:12]} in loop {loop[:16]}… "
          f"(final), reasons sealed to {', '.join(sent)}, gas {receipt['gasUsed']}", file=out)
    return 0


def cmd_cases(args, session, out):
    """The case records involving me in the fold — written by me or sealed to me."""
    me = session.maker.lower()
    rows = [(loop, oid, kind, rec) for loop, oid, kind, rec in session.fold().cases()
            if str(rec.get("to", "")).lower() == me or str(rec.get("from", "")).lower() == me]
    for loop, oid, kind, rec in sorted(rows, key=lambda r: (r[0], r[1], ("claim", "answer", "ruling").index(r[2]))):
        print(f"{kind:7} {rec['from']} → {rec['to']} on {oid[:12]} in loop {loop[:16]}…", file=out)
    if not rows:
        print("no case involving me", file=out)
    return 0 if rows else 1


def cmd_arbitrators(args, session, out):
    """A personal view of arbitrators (2026-10-01, `counterparty-gate.md`
    §7a): every arbitrator named on an escrow reservation where I or a
    maker I trust (`--trust KEYS`, else the `trust` setting) was a party —
    the legs, its rulings, who among us lost a ruling under it and chose it
    again (the one choice a loser makes that a winner cannot fake for them),
    and the accreditation it presents under the registers I read. For my
    own judgement: nothing here is a gate, and nothing outside my circle is
    counted (puppet trades manufacture counts)."""
    from ..reputation import view
    client = clients._escrow_client(session)
    me = client.account().address if _configured("bee_signer") else session.maker
    trusted = (args.trust or _configured("trust") or "").replace(",", " ").split()
    fold = session.fold()

    def posted(maker: str, offer: str, loop: str):
        """When `maker`'s offer on this leg was posted (its validity start):
        the give itself, or the want the loop record says it served."""
        try:
            give_ = fold.get(offer)
        except KeyError:
            return None
        if give_.maker.lower() == maker.lower():
            return give_.valid.start
        for leg in fold.loop_legs(loop):
            if offer in leg.gives:
                try:
                    want_ = fold.get(leg.want)
                except KeyError:
                    return None
                return want_.valid.start if want_.maker.lower() == maker.lower() else None
        return None
    rows = view(client.events("Reserved"), client.events("Settled"), client.events("Deposited"),
                me=me, trusted=trusted, posted=posted)
    regs = _registers(session)
    circle = {me.lower(), *(t.lower() for t in trusted)}
    for a in rows:
        mine = sum(1 for w, g, _ in a.legs if me.lower() in (w.lower(), g.lower()))
        ruled = ", ".join(f"{_num(Fraction(t, 10 ** 18))} of {_num(Fraction(m, 10 ** 18))} to the wanter"
                          for _w, _g, t, m, _ in a.rulings) or "none"
        again = ", ".join("me" if k.lower() == me.lower() else k for k in a.chosen_again) or "nobody"
        print(f"{a.key}: named in {len(a.legs)} leg(s) of my circle ({mine} mine); rulings: {ruled}; "
              f"chosen again after losing under it by: {again}", file=out)
        for st, _ in fold.statements(a.key):
            print(f"  presents {st.category} ({st.kind}, by {st.issuer}): {_statement_state(st, regs)}", file=out)
    if not rows:
        print(f"no arbitrator named on a reservation of mine or of {len(circle) - 1} maker(s) I trust", file=out)
    return 0 if rows else 1


# ---------------------------------------------------------------- R6: notices before claims

def cmd_notice(args, session, out):
    """R6 (§6, rung zero of every claim): as the wanter of a cleared leg,
    tell the giver which fact is wrong and until when it may cure —
    factbond's `Notice`, sealed to the giver's key (recovered from its
    offer's signature) beside a salted commitment, written into my book.
    The fact is the lapsed statement's id (`--fact`, a prefix of one the
    giver presented), else the give itself; the policy the reservation's
    escrow key. The cure period is mine to state (`--cure`, no default: the
    class's minimum is factbond's to enforce). The opening stays with me,
    for the claim's case file."""
    from ..escrow import reservation_key
    from ..notice import notice_record, sealed
    fold, me, now = session.fold(), session.maker, session.now
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    leg = _leg_with(fold, loop, oid)
    if fold.get(leg.want).maker != me:
        raise ValueError(f"{oid[:12]} in loop {loop[:16]}… is not a leg I receive on")
    giver = fold.get(oid).maker
    fact = oid
    if args.fact:
        found = sorted({st.statement_id for st, _ in fold.statements(giver) if st.statement_id.startswith(args.fact)})
        if len(found) != 1:
            raise ValueError(f"--fact {args.fact}: {'no' if not found else 'several'} statements of {giver} match")
        fact = found[0]
    notice = notice_record(me, giver, fact, policy_ref=reservation_key(oid, loop), sent_at=now,
                           cure_period=duration_s(args.cure))
    side, opening = sealed(notice, sender=me, recipient=giver, recipient_public_key=_public_key_of(fold, oid))
    session.book.send_notice(loop, oid, side)
    session.book.commit()
    path = _notices_path(loop, oid, "notice")
    _write_json(path, opening)
    print(f"notice   sent to {giver} on {oid[:12]} in loop {loop[:16]}…: cure by "
          f"{_iso(notice['cure_deadline'])}; the opening a claim cites is at {path}", file=out)
    return 0


def cmd_cure(args, session, out):
    """R6: as the giver, answer a notice on my give — factbond's `Cure`,
    naming the notice by its reference and what I did (`--evidence`, a
    reference: the refund's transaction, the corrected statement), sealed
    back to the claimant beside a commitment, written into my book."""
    from ..notice import cure_record, read, ref, sealed
    fold, me = session.fold(), session.maker
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    side = fold.notice(loop, oid)
    if side is None or side.get("to") != me:
        raise ValueError(f"no notice to me on {oid[:12]} in loop {loop[:16]}…")
    signer = _configured("bee_signer")
    if not signer:
        raise ValueError("opening the notice needs my key: set bee_signer")
    notice = read(side, signer)
    leg = _leg_with(fold, loop, oid)
    cure = cure_record(ref(notice), me, session.now, args.evidence or "")
    back, opening = sealed(cure, sender=me, recipient=notice["notifier"],
                           recipient_public_key=_public_key_of(fold, leg.want))
    session.book.send_cure(loop, oid, back)
    session.book.commit()
    _write_json(_notices_path(loop, oid, "cure"), opening)
    print(f"cure     sent to {notice['notifier']} on {oid[:12]} in loop {loop[:16]}…", file=out)
    return 0
