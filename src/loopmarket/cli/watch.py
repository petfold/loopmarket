"""Settlement: handoffs and `watch` (P1-spacetime-terms.md §4).

The address reaches the courier through the book: after a loop clears,
the place-owner's client seals the text to the leg counterparty's public
key (recovered from the signature on their offer) and writes it beside
its own filled offer; the counterparty's `watch` reads the fold it already
follows and opens it with bee_signer. No side channel. `watch` is also
how anyone learns they cleared: the fill record is the notification. Each
pass also reports the demand for options on my gives, the statements a
leg relied on that have lapsed since, notices and cures, a title
register's transfers and the case records sealed to me."""

from __future__ import annotations

import os
import time as _time
from fractions import Fraction

from ..registry import LegRecord, OfferRegistry
from ..schema import GIVE, WANT
from .clients import _registers
from .entry import _handoffs_path, _remember_handoff
from .options import _option_demand
from .registers import _transfer_faults
from .render import _bare_key, _num
from .settings import _configured, _err, _home_dir, _read_json, _write_json
from .spellings import _iso, duration_s
from .stores import Session, _resolve_id


def _seen_path() -> str:
    return os.path.join(_home_dir(), "seen")


def _leg_of(fold: OfferRegistry, offer_id: str):
    """(loop_id, leg, my side) for a filled offer, else None; the leg a
    `LegRecord`. A composed or aggregated leg has several gives, any of them
    the give side."""
    loop_id = fold.loop_of(offer_id)
    if not loop_id:
        return None
    for leg in LegRecord.of_loop(fold.store.get(f"loop/{loop_id}")):
        if offer_id in leg.gives:
            return loop_id, leg, "give"
        if offer_id == leg.want:
            return loop_id, leg, "want"
    return None


def _gives_of(leg: dict) -> list:
    """Every give of a raw `loop/` leg, read as `LegRecord` reads it."""
    return list(LegRecord.from_record(leg).gives)


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


def _finalized_beats(session) -> list[tuple[str, set]]:
    """(book root, the offers its fills took) for every finalized beat of
    the clearing contract."""
    from .clients import _beat_client
    client = _beat_client(session)
    return [(state["book_root"], {oid for oid, _taken, _cap in client.pending_fills(state["beat"])})
            for state in client.beats() if state["finalized"]]


def _finalized_leg(session: Session, fold: OfferRegistry, oid: str, found, beats):
    """Under a chain: (loop id, leg, my side) for the loop a finalized beat
    recorded taking `oid` — the book's loop for it or one of its rivals
    (question 25) — else None. A loop is a beat's when the beat pinned the
    loop's book root and its fills took every offer of the loop."""
    candidates = [found[0]] + sorted(rec["rival"] for rec in session.rivals
                                     if rec.get("loop") == found[0] and oid in rec.get("offers", ()))
    for lid in candidates:
        key = f"loop/{lid}"
        if not fold.store.contains(key):
            continue
        rec = fold.store.get(key)
        legs = LegRecord.of_loop(rec)
        offers = {o for leg in legs for o in leg.offer_ids}
        if not any(root == rec.get("book_root") and offers <= taken for root, taken in beats):
            continue
        for leg in legs:
            if oid in leg.gives:
                return lid, leg, "give"
            if oid == leg.want:
                return lid, leg, "want"
    return None


def _seal_pending(session: Session, fold: OfferRegistry, out, *, only=None) -> bool:
    """Seal every remembered text whose offer has cleared and whose
    counterparty left a public key; returns whether anything was sealed.
    Where a chain decides what is filled, an offer has cleared only when a
    finalized beat recorded its loop (question 25, decided by Peter
    2026-10-10): a fill in the book is a pending beat's, or a rival's that
    the chain may never record, and a door code is not handed over on it."""
    from ..handoff import seal
    from ..sigs import recover_public_key

    pending = _read_json(_handoffs_path(), {})
    me = session.maker
    sealed = False
    beats = None
    for oid, text in sorted(pending.items()):
        if only is not None and oid not in only:
            continue
        found = _leg_of(fold, oid)
        if found is None:
            continue
        if fold.chain_fills is not None:
            if beats is None:
                beats = _finalized_beats(session)
            found = _finalized_leg(session, fold, oid, found, beats)
            if found is None:
                print(f"handoff  {oid[:12]} waits for a finalized beat to record its loop", file=_err())
                continue
        loop_id, leg, side = found
        if session.book.handoff(loop_id, oid) is not None \
                or fold.handoff(loop_id, oid) is not None:
            continue
        other = fold.get(leg.want if side == "give" else leg.gives[0])
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
        other_id = leg.want if side == "give" else leg.gives[0]
        record = fold.handoff(loop_id, other_id)
        if record is not None and record.get("to") == me:
            yield f"{loop_id}/{other_id}", loop_id, fold.get(other_id).maker, record


def _open_incoming(session: Session, fold: OfferRegistry, out, seen) -> bool:
    from ..handoff import open_

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
        other = fold.get(leg.want if side == "give" else leg.gives[0])
        concepts = tuple(c for p in (offer if side == "give" else other).parts for c in p.concepts)
        # the bare categories, as the price memory keys them; an operator's give
        # (a courier's transport(...) and its ends) has none, and is named by its terms
        thing = " ".join(_bare_key(concepts) or concepts)
        verb = f"gives {thing} to" if side == "give" else f"receives {thing} from"
        counterparties = other.maker if side == "give" else ", ".join(
            sorted({fold.get(g).maker for g in leg.gives}))
        print(f"filled   {oid[:12]} in loop {loop_id[:16]}…: {me} {verb} "
              f"{counterparties}", file=out)
        seen["fills"].append(oid)
        news = True
    # the demand signal (2026-09-29): someone would pay to hold what I give
    seen.setdefault("demand", [])
    now = session.now
    for offer in fold.offers(now=now):
        if offer.maker != me or offer.kind != GIVE:
            continue
        for w in _option_demand(session, fold, offer, now):
            key = f"{offer.offer_id}/{w.offer_id}"
            if key in seen["demand"]:
                continue
            print(f"hold?    {w.maker} wants to hold a thing like your {offer.offer_id[:12]} "
                  f"(bids {_num(w.tokens.amount)} on their scale): "
                  f"loop option {offer.offer_id[:12]} --for {w.offer_id[:12]}", file=out)
            seen["demand"].append(key)
            news = True
    news = _seal_pending(session, fold, out) or news
    news = _open_incoming(session, fold, out, seen["handoffs"]) or news
    news = _check_lapsed(session, fold, out, seen.setdefault("lapsed", [])) or news
    news = _notices_in(session, fold, out, seen.setdefault("notices", [])) or news
    news = _transfers_shown(session, fold, out, seen.setdefault("transfers", [])) or news
    news = _cases_in(session, fold, out, seen.setdefault("cases", [])) or news
    _write_json(_seen_path(), seen)
    return news


def _transfers_shown(session, fold, out, seen: list) -> bool:
    """A leg I receive on whose give declared `registry-transfer(ID)` (I4):
    reported once when the register shows the item held by me — the moment
    to countersign."""
    from ..witness import transfer_register
    news = False
    for loop, leg, want_ in _my_legs(session, fold, "want"):
        for g in leg.gives:
            rid = transfer_register(fold.get(g).oracle)
            key = f"{loop}/{g}"
            if not rid or key in seen or _transfer_faults(session, g, loop, want_.maker):
                continue
            seen.append(key)
            news = True
            print(f"transfer {g[:12]} in loop {loop[:16]}…: the register {rid} shows it held by me — "
                  f"`loop countersign {g[:12]}` returns the giver's reservation", file=out)
    return news


# ---------------------------------------------------------------- R6: notices before claims

def _my_legs(session, fold, side: str):
    """(loop id, leg record, my offer) for every leg of a loop in the fold
    where my offer is the want (`side` "want") or one of the gives."""
    me = session.maker
    for o in fold.offers(include_filled=True):
        if o.maker != me or (o.kind == WANT) != (side == "want"):
            continue
        for loop in fold.loops_of(o.offer_id):
            for leg in fold.loop_legs(loop):
                if (side == "want" and leg.want == o.offer_id) or \
                        (side != "want" and o.offer_id in leg.gives):
                    yield loop, leg, o


def _check_lapsed(session, fold, out, seen: list) -> bool:
    """The watch's re-check (R6, §6): a statement a leg I receive on relied
    on — the giver's, of a category my want's credential requirement names
    — that its issuer's register now marks revoked or suspended, read at
    the heads of the registers I read. Reported once, with the notice to
    send: the moment a notice is due is before the window."""
    from ..notice import lapsed
    regs = _registers(session)
    if not regs:
        return False
    ontology, news = session.catalogue, False
    for loop, leg, want_ in _my_legs(session, fold, "want"):
        req = want_.requires if want_.v >= 6 else None
        cats = [c.category for c in req.counterparty] if req is not None else []
        if not cats:
            continue
        gives = [(g, fold.get(g).maker) for g in leg.gives]
        statements = lambda m: [st for st, _ in fold.statements(m)]
        for oid, st, change in lapsed(gives, statements, regs):
            if not any(ontology.satisfies((st.category,), (c,)) for c in cats):
                continue
            key = f"{loop}/{oid}/{st.statement_id}/{change}"
            if key in seen:
                continue
            seen.append(key)
            news = True
            print(f"lapsed   {st.category} of {st.subject} ({st.statement_id[:12]}), relied on in loop "
                  f"{loop[:16]}…: {change} — `loop notice {oid[:12]} --loop {loop[:12]} --fact "
                  f"{st.statement_id[:12]} --cure DURATION` tells the giver", file=out)
    return news


def _notices_in(session, fold, out, seen: list) -> bool:
    """Notices sealed to me on my gives, and cures sealed to me on my
    notices, opened with bee_signer and reported once. A notice counts only
    from the leg's wanter, a cure only from its giver (R6), so only their
    keys are read: anyone else's record is stored in its writer's book and
    never read. One that does not open with my key, or whose plaintext is
    not the record its kind names, is reported as unreadable and the pass
    goes on; one whose `from` is not the key's writer (a raw write into a
    shared book) is set aside, said once on stderr."""
    from ..notice import read
    signer, me, news = _configured("bee_signer"), session.maker, False
    rows = []
    for loop, leg, give_ in _my_legs(session, fold, "give"):
        wanter = _maker_of(fold, leg.want)
        side = fold.notice(loop, give_.offer_id, wanter) if wanter else None
        if side is not None and side.get("to") == me:
            rows.append(("notice", loop, give_.offer_id, side, "wanter", wanter))
    for loop, leg, _want in _my_legs(session, fold, "want"):
        for g in leg.gives:
            giver = _maker_of(fold, g)
            side = fold.cure(loop, g, giver) if giver else None
            if side is not None and side.get("to") == me:
                rows.append(("cure", loop, g, side, "giver", giver))
    for kind, loop, oid, side, role, party in rows:
        key = f"{kind}/{loop}/{oid}/{side['commitment']}"
        if key in seen:
            continue
        seen.append(key)
        if side.get("from") != party:
            print(f"{kind:8} from {side.get('from')} on {oid[:12]} in loop {loop[:16]}…: set aside, "
                  f"not this leg's {role} ({party})", file=_err())
            continue
        news = True
        hint = f" — `loop cure {oid[:12]} --loop {loop[:12]}` answers it" if kind == "notice" else ""
        if not signer:
            text = "(sealed; set bee_signer to open)"
        else:
            try:
                text = _sealed_text(kind, read(side, signer))
            except Exception as exc:  # noqa: BLE001 — sealed to another key, or not a record of its kind
                text, hint = f"cannot be read ({exc.__class__.__name__})", ""
        who = f"notice   from {side['from']}" if kind == "notice" else f"cured    by {side['from']}"
        print(f"{who} on {oid[:12]} in loop {loop[:16]}…: {text}{hint}", file=out)
    return news


def _maker_of(fold, offer_id: str) -> str | None:
    """The maker of an offer in the fold, or None when the fold lacks it."""
    try:
        return fold.get(offer_id).maker
    except KeyError:
        return None


def _sealed_text(kind: str, rec: dict) -> str:
    """What an opened notice or cure says; raises when its plaintext is not
    the record its kind names."""
    if kind == "notice":
        return f"cure by {_iso(rec['cure_deadline'])}, fact {rec['referred_fact'][:16]}"
    evidence = f", evidence {rec['evidence_ref'][:16]}" if rec["evidence_ref"] else ""
    return f"at {_iso(rec['time'])}{evidence}"


def _cases_in(session, fold, out, seen: list) -> bool:
    """Claims, answers and rulings sealed to me, opened and reported once;
    one that does not open with my key, or whose plaintext is not the
    record its kind names, is reported as unreadable and the pass goes on."""
    from ..case import read
    signer, me, news = _configured("bee_signer"), session.maker, False
    for loop, oid, kind, rec in fold.cases():
        if str(rec.get("to", "")).lower() != me.lower():
            continue
        k = f"{kind}/{loop}/{oid}/{rec['commitment']}"
        if k in seen:
            continue
        seen.append(k)
        news = True
        frm, where = rec.get("from"), f"on {oid[:12]} in loop {loop[:16]}…"
        try:
            what, hint = _case_text(kind, read(rec, signer) if signer else None)
        except Exception as exc:  # noqa: BLE001 — sealed to another key, or not a record of its kind
            print(f"case     {frm} {kind} {where}: cannot be read ({exc.__class__.__name__})", file=out)
            continue
        print(f"case     {frm} {what} {where}{hint}", file=out)
    return news


def _case_text(kind: str, body: dict | None) -> tuple[str, str]:
    """What a case record says, and the hint after it; `body` is None when
    no key is set to open it. Raises when the plaintext is not the record
    its kind names."""
    if kind == "claim":
        what = f"claims {_num(Fraction(body['amount'], 10 ** 18))}" if body is not None \
            else "claims (sealed; set bee_signer)"
        return what, " — `loop answer` if I am the giver, `loop hold`/`loop rule` if I am the arbitrator"
    if kind == "answer":
        return "answers the claim", ""
    what = (f"rules {_num(Fraction(body['to_wanter'], 10 ** 18))} to the wanter: {body['reason']}"
            if body is not None else "rules (sealed; set bee_signer)")
    return what, ""


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
        session._registers = None     # and a register may have published a newer root
        _time.sleep(interval)


def cmd_handoffs(args, session, out):
    """Every handoff sealed to me, opened with bee_signer. Exit 1 if none."""
    from ..handoff import open_

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
