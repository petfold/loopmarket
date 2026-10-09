"""Offer entry: `give`, `want`, `offer` (a draft), `withdraw`, `option`,
`exercise` and `place`. Every default and shorthand is resolved, the
approval block shown, the question asked (`confirm`), the offer published
and signed. An omitted price is the maker's last unit price for the same
thing, marked in the block. The named places' settlement texts are kept
for `watch` to seal once the offer clears."""

from __future__ import annotations

import os
import shlex
import sys

from ..ontology import Ontology
from ..schema import GIVE, WANT, Offer, Parts, Thing, TimeWindow, give, want
from ..spacetime import cell_for_coords
from .drafts import _VERBS, _find_draft, _part_from_record, _read_drafts, _write_drafts
from .grammar import (_PRICE_RE, Composed, Parsed, Part, _resolve_part, parse_offer_tokens,
                      parse_want_line, part_line)
from .guarantees import _check_asset_categories, _guarantees
from .options import _option_demand, _option_offer, _option_plan
from .render import _age, _bare_key, _num, _span, render_offer
from .settings import _configured, _err, _home_dir, _isatty, _read_json, _write_json
from .spellings import PART_SEP, _iso, _number, parse_coords, validity
from .stores import Session, _resolve_id


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
                 **_guarantees(now, thing.concepts, side=side))
    _check_asset_categories(offer, ontology)
    return offer, notes, reused


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
                 **_guarantees(session.now, tuple(t for p in parts for t in p.thing.concepts), side=WANT))
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
    return _publish_offers(session, [(offer, notes)], reused, out, addresses)


def _door_notes(offer: Offer) -> list[str]:
    """What a photo at the door gives away, said in the block that approves
    it (THREATS T19, 2026-09-29): possession is the default because it
    proves control of the key and nothing more."""
    notes = []
    if offer.oracle == "photo-match":
        notes.append("photo-match: at the door the counterparty's device receives my attested photo — "
                     "a provable link from my face to my key and every trade it made (T19); "
                     "`set oracle possession` proves control without it")
    req = offer.requires if offer.v >= 5 else None
    from ..witness import PHOTO_MATCH, accepted_types
    if req is not None and accepted_types(req.oracles) == {PHOTO_MATCH}:
        notes.append("requires the counterparty's photo at the door: their face linked to their key (T19); "
                     "`set require_door possession` asks for control of the key only")
    return notes


def _arbitrator_notes(offer: Offer) -> list[str]:
    """Who would rule a claim on a deposit, said in the block that approves
    it (2026-10-01, Peter: the default is one named arbitrator both sides
    accept, final): a give whose deposit names no arbitrator leaves it to
    the clearing's own resolver; a want relying on a deposit and naming no
    acceptance takes whichever the give names."""
    from ..escrow import is_address
    notes = []
    req = offer.requires if offer.v >= 5 else None
    accepts = req is not None and req.resolvers is not None
    if offer.kind == GIVE and offer.v >= 5 and offer.bond is not None \
            and not is_address(offer.arbitrator) and not accepts:
        notes.append("no arbitrator named: a claim on my deposit would be ruled by the clearing's "
                     "own resolver — `set arbitrator KEY` names one both sides can accept, "
                     "whose ruling is final")
    if offer.kind == WANT and req is not None and (req.point or req.ladder) and not accepts:
        notes.append("I accept whichever arbitrator the giver names — `set require_resolvers` "
                     "chooses (keys, or root: for those accredited by a register I trust)")
    return notes


def _publish_offers(session: Session, items, reused: bool, out, addresses=()) -> int:
    """`_publish_offer` for offers approved together — a give and the
    option `options on` writes with it: every block shown, one question,
    every id printed in order. `addresses` belong to the first."""
    for i, (offer, notes) in enumerate(items):
        if i:
            print("and", file=out)
        print(render_offer(offer), file=out)
        for note in notes + _door_notes(offer) + _arbitrator_notes(offer):
            print(f"  note     {note}", file=out)
    for address in addresses:
        print(f"  note     handoff {address} — sealed to the counterparty "
              f"at clearing", file=out)
    if not _confirm(reused, out):
        print("not published", file=_err())
        return 1
    ids = []
    for offer, _notes in items:
        oid = session.book.publish(offer)
        signer = _configured("bee_signer")
        if signer:
            try:
                from ..sigs import maker_address, sign_offer
                if maker_address(signer) == offer.maker:
                    session.book.attach_signature(oid, sign_offer(offer, signer))
            except Exception:  # noqa: BLE001 — signing is the optional layer
                pass
        ids.append(oid)
    session.book.commit()
    if addresses:
        _remember_handoff(ids[0], "\n".join(addresses))
    # By exception to odag's silent-on-success rule: publishing is a
    # commitment, and the id is what `withdraw` needs.
    for oid in ids:
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
    session's settings (maker, defaults, catalogue), not published; a
    composed line (`+` between parts) is one v4 want."""
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
    items = [(offer, notes)]
    if side == GIVE and (_configured("options") or "off").strip().lower() == "on":
        # `options on` (2026-09-29): the give and its option, approved
        # together; a give that cannot carry one says why and goes alone
        try:
            until, premium, onotes = _option_plan(session, offer, session.now)
            items.append((_option_offer(session, offer, until, premium, onotes), onotes))
        except ValueError as exc:
            notes.append(f"no option (options on): {exc}")
    return _publish_offers(session, items, reused, out, addresses=part.addresses)


def cmd_give(args, session, out):
    return _publish(args, session, out, GIVE)


def cmd_want(args, session, out):
    return _publish(args, session, out, WANT)


def cmd_withdraw(args, session, out):
    oid = _resolve_id(session, args.id, mine_only=True)
    if session.book.is_filled(oid):
        raise ValueError(f"{oid[:12]} is filled: a cleared leg is an obligation")
    if session.book.is_withdrawn(oid):
        raise ValueError(f"{oid[:12]} is already withdrawn")
    session.book.withdraw(oid)
    session.book.commit()
    return 0


def cmd_option(args, session, out):
    """`option ID [--until T] [--premium X] [--for WANT]` (C7, 2026-09-29;
    options-and-cover.md §3.1): write an option on my own plain give — a give
    of `option(<its concepts>)` for its quantity, priced at the premium on my
    scale, naming the offer as its `underlying` and exercisable from now
    until T. When it clears the offer is held for the option's holder until
    T (a hold, C2); my exit meanwhile is a priced cancellation of the option
    leg, never a free withdrawal. The guarantee settings apply as to any give.

    Both numbers may be left out (the same day, Peter: options are used only
    if they are easy to write): the window is `option_window` of the lead,
    the premium `option_premium` — suggested from the book's demand by
    default — shown with their reasons in the approval block. `--for WANT`
    answers someone's want of an option on a thing like mine (the demand
    `show` and `watch` report): the option is checked to meet it."""
    oid = _resolve_id(session, args.id, mine_only=True)
    p = session.book.get(oid)
    if session.book.is_filled(oid) or session.book.is_withdrawn(oid):
        raise ValueError(f"{oid[:12]} is no longer open")
    now = session.now
    until, premium, notes = _option_plan(session, p, now, args.until, args.premium)
    offer = _option_offer(session, p, until, premium, notes)
    if args.for_want:
        fold = session.fold()
        wid = _resolve_id(session, args.for_want, mine_only=False)
        if wid not in {w.offer_id for w in _option_demand(session, fold, p, now)}:
            raise ValueError(f"{wid[:12]} is not an open want of an option this offer's would meet")
        w = fold.get(wid)
        notes.append(f"for {w.maker}'s want {wid[:12]} (bids {_num(w.tokens.amount)} on their scale)")
    return _publish_offer(session, offer, notes, False, out)


def cmd_exercise(args, session, out):
    """`exercise OPTION [OPTION...] PRICE` (C7): as the options' holder, want
    their underlyings — the same things, the quantities held — at PRICE on my
    scale, while every exercise window is open. An exercise is a clearing
    (§3.5): the want needs a closing loop like any other, and the holds let
    only me take the offers meanwhile.

    Several options (2026-09-29, Peter: a trip's components held one by one,
    then committed together) are exercised as **one composed want**, a part
    per underlying under the one price, open until the first window closes:
    all or nothing, like any composed want — the holds are what made the
    parts sure to be there, so the commitment can wait until the last one is
    found. Two options on one offer are refused: exercising either takes
    everything I hold of it."""
    if len(args.args) < 2:
        raise ValueError("exercise OPTION [OPTION...] PRICE")
    *refs, price = args.args
    fold = session.fold()
    now = session.now
    things, concepts, ends, notes, underlyings = [], [], [], [], set()
    for ref in refs:
        oid = _resolve_id(session, ref, mine_only=False)
        o = fold.get(oid)
        if not (o.v >= 6 and o.underlying):
            raise ValueError(f"{oid[:12]} is not an option")
        if o.underlying in underlyings:
            raise ValueError(f"{oid[:12]}: another option named holds the same offer — exercise one")
        underlyings.add(o.underlying)
        mine = [(lid, rec) for lid, rec in fold.holds(o.underlying)
                if rec["option"] == oid and rec["holder"] == session.maker]
        if not mine:
            raise ValueError(f"{oid[:12]}: you hold no such option")
        left = fold.held_by(o.underlying, session.maker, now)
        if left <= 0:
            raise ValueError(f"{oid[:12]}: not exercisable now (window {_span(o.exercise)})")
        p = fold.get(o.underlying)
        things.append(Thing(p.thing.concepts, left, p.thing.unit))
        concepts.extend(p.thing.concepts)
        ends.append(int(o.exercise.end))
        notes.append(f"exercising {oid[:12]} on {o.underlying[:12]}")
    kw = _guarantees(now, tuple(concepts), side=WANT)
    nonce = now * 1000 + sum(1 for x in session.book.offers(include_filled=True) if x.maker == session.maker)
    lot = things[0] if len(things) == 1 else Parts(tuple(things))
    if len(things) > 1:
        notes.append(f"one composed want of {len(things)} parts: all or nothing, "
                     f"until the first window closes ({_iso(min(ends))})")
    offer = want(session.maker, lot, _number(price), valid=TimeWindow(now, min(ends)),
                 nonce=nonce, **session.catalogue.pins, **kw)
    return _publish_offer(session, offer, notes, False, out)


def cmd_place(args, session, out):
    """The dated bridge (cli.md §4, §11.1): a place node under the cell of
    that radius around that point, written to the personal layer through
    the catalogue facade (`Ontology.declare_place`) — the cell is the
    place (no disc anywhere since the v3 record). Deleted the day odag
    accepts `geo(LAT,LON,R)` as input vocabulary. When the
    personal store *is* the catalogue the name is vocabulary and offers
    say `NAME` bare (ontodag #15 orders the name); under a separate
    pinned catalogue the place is private and offers say its cell. The
    optional ADDRESS is settlement text on the node (P1-spacetime-terms.md
    §4): never vocabulary, never in a record — shown in the approval block
    of an offer naming the place and sealed to the cleared counterparty."""
    lat, lon, radius = parse_coords(args.coords)
    personal = session.personal_session

    def adopted():
        print("loop: adopted ontodag's prelude into the personal store "
              f"({personal.describe()}) so places hang under geo cells",
              file=_err())
    Ontology(personal.dag).declare_place(args.name, cell_for_coords(lat, lon, radius),
                                         address=" ".join(args.address).strip(), adopted=adopted)
    personal.save()
    return 0


# The named places' settlement texts, kept in the loop home until the offer
# clears; `watch` seals each to the counterparty then (watch.py).

def _handoffs_path() -> str:
    return os.path.join(_home_dir(), "handoffs")


def _remember_handoff(offer_id: str, text: str) -> None:
    pending = _read_json(_handoffs_path(), {})
    pending[offer_id] = text
    _write_json(_handoffs_path(), pending)
