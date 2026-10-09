"""Options on my gives (options-and-cover.md §3): an option's window and
premium (`option_window`, `option_premium`, the premium suggested from the
book's demand), the option give itself, the wants of an option that one
would meet (the demand `show` and `watch` report), and `holds`. The
`option` and `exercise` commands are entry.py's."""

from __future__ import annotations

import re
from fractions import Fraction

from ..schema import GIVE, WANT, Offer, Thing, TimeWindow, give, q
from .grammar import _canonical
from .guarantees import _guarantees, _handover_lead
from .render import _duration_approx, _num, _round_amount
from .settings import _configured
from .spellings import _iso, _number, _until, duration_s


#: How far back the book's demand is read for a suggested premium.
DEMAND_LOOKBACK = 30 * 86_400


def _window_rule(text: str):
    """`option_window`: a fraction in (0, 1) of the lead, or a duration."""
    if re.match(r"^\d+/\d+$", text.strip()):
        f = q(text.strip())
        if not 0 < f < 1:
            raise ValueError("option_window as a fraction of the lead is between 0 and 1")
        return f
    return duration_s(text)


def _premium_rule(text: str):
    """`option_premium`: `suggest`, a percentage of the price, or an amount."""
    t = text.strip()
    if t == "suggest":
        return t
    if t.endswith("%"):
        pct = q(t[:-1])
        if pct <= 0:
            raise ValueError("option_premium as a percentage is above 0")
        return ("%", pct)
    amount = q(t)
    if amount <= 0:
        raise ValueError("option_premium is suggest, N% or an amount above 0")
    return amount


def _option_lead(p: Offer, now: int) -> tuple[int | None, str]:
    """The lead an option's window is a fraction of: to the offer's handover
    time term, else to its validity's end; None when it has neither."""
    lead = _handover_lead(p.thing.concepts, now)
    if lead is not None:
        return lead, "the lead to the handover"
    if p.valid.end is not None:
        return p.valid.end - now, "the offer's remaining validity"
    return None, ""


def _demand_rate(fold, p: Offer, ontology, now: int) -> int:
    """How many wants the offer could have served appeared in the book over
    the lookback — filled ones too: demand that came, whoever met it."""
    n = 0
    for w in fold.offers(include_filled=True):
        if w.kind != WANT or w.composed or w.maker == p.maker:
            continue
        if not now - DEMAND_LOOKBACK <= w.valid.start <= now:
            continue
        if w.thing.unit == p.thing.unit and ontology.satisfies(p.thing.concepts, w.thing.concepts):
            n += 1
    return n


def _option_plan(session, p: Offer, now: int, until_text: str | None = None,
                 premium_text: str | None = None) -> tuple[int, Fraction, list[str]]:
    """The window and premium of an option on `p`: what was typed, else the
    settings (`option_window`, `option_premium`), the premium `suggest`ed
    from the book's demand — the maker approves what is shown, as with the
    price memory. A default in the protocol would be wrong: what a hold
    costs is the maker's own risk judgement (Peter, 2026-09-29)."""
    notes: list[str] = []
    lead, lead_name = _option_lead(p, now)
    if until_text:
        until = _until(until_text, now)
    else:
        text = (_configured("option_window") or "1/4").strip()
        rule = _window_rule(text)
        if isinstance(rule, Fraction):
            if lead is None or lead <= 0:
                raise ValueError(f"{p.offer_id[:12]} has no handover time and stands until withdrawn: "
                                 f"no lead to take {rule} of — pass --until, or set option_window "
                                 f"to a duration")
            until = now + int(lead * rule)
            notes.append(f"window {text} of {lead_name} ({_duration_approx(until - now)}), "
                         f"until {_iso(until)}")
        else:
            until = now + rule
            notes.append(f"window {_duration_approx(rule)}, until {_iso(until)}")
    if until <= now:
        raise ValueError("the exercise window ends after now")
    if p.valid.end is not None and until > p.valid.end:
        raise ValueError(f"{p.offer_id[:12]} stands only until {_iso(p.valid.end)}: the window must end by then")
    handover = _handover_lead(p.thing.concepts, now)
    if handover is not None and until > now + handover:
        raise ValueError(f"the window must close before the handover begins ({_iso(now + handover)})")
    if premium_text:
        return until, _number(premium_text), notes
    rule = _premium_rule(_configured("option_premium") or "suggest")
    price = q(p.tokens.amount)
    if isinstance(rule, tuple):
        premium = _round_amount(price * rule[1] / 100)
        notes.append(f"premium {_num(rule[1])}% of the price")
    elif rule != "suggest":
        premium = rule
    else:
        import math
        w = until - now
        span = lead if lead and lead > 0 else w
        n = _demand_rate(session.fold(), p, session.catalogue, now)
        if n == 0:
            premium = _round_amount(price * Fraction(w, span) / 2)
            notes.append("premium suggested: no demand for this in the book in 30 days — a guess, "
                         "price × window/lead × ½")
        else:
            rate = n / DEMAND_LOOKBACK
            loss = math.exp(-rate * max(span - w, 0)) - math.exp(-rate * span)
            premium = _round_amount(float(price) * 0.5 * loss)
            notes.append(f"premium suggested: {n} want(s) for this in 30 days, a buyer every "
                         f"~{_duration_approx(int(DEMAND_LOOKBACK / n))}; the chance one comes during the "
                         f"hold and none after it, the holder exercising half the time")
    floor = _round_amount(max(price / 100, Fraction(1, 100)))
    if premium < floor:
        notes.append(f"premium raised to the floor {_num(floor)} (1% of the price): a hold is never free")
        premium = floor
    return until, premium, notes


def _option_offer(session, p: Offer, until: int, premium, notes: list[str]) -> Offer:
    """The option on my plain give `p`: a give of `option(<its concepts>)`
    for its quantity at `premium` on my scale, naming `p` as its
    `underlying`, exercisable from now until `until` (v6)."""
    if p.kind != GIVE or p.composed:
        raise ValueError("an option holds a give: a want is met, not held")
    if p.v >= 6 and p.underlying:
        raise ValueError("an option on an option is a transfer of the right (§3.8), not built")
    now = session.now
    ontology = session.catalogue
    term = _canonical(f"option({' '.join(p.thing.concepts)})", ontology.dag, notes)
    window = TimeWindow(now, until)
    kw = _guarantees(now, p.thing.concepts, side=GIVE)
    kw.pop("v", None)                                  # the underlying makes it v6
    nonce = now * 1000 + sum(1 for o in session.book.offers(include_filled=True) if o.maker == session.maker) + 1
    return give(session.maker, Thing((term,), p.thing.qty, p.thing.unit), premium,
                valid=window, nonce=nonce, underlying=p.offer_id, exercise=window, **ontology.pins, **kw)


def _option_demand(session, fold, p: Offer, now: int) -> list[Offer]:
    """The open wants of an option that an option on `p` would meet — the
    demand signal (2026-09-29): someone would pay to hold a thing like it."""
    if p.kind != GIVE or p.composed or (p.v >= 6 and p.underlying):
        return []
    try:
        term = _canonical(f"option({' '.join(p.thing.concepts)})", session.catalogue.dag, [])
    except Exception:                                  # noqa: BLE001 — no option head in this catalogue
        return []
    out = []
    for w in fold.offers(now=now):
        if w.kind != WANT or w.composed or w.maker == p.maker:
            continue
        if not any(isinstance(c, str) and c.startswith("option(") for c in w.thing.concepts):
            continue
        if w.thing.unit == p.thing.unit and q(w.thing.qty) <= q(p.thing.qty) \
                and session.catalogue.satisfies((term,), w.thing.concepts):
            out.append(w)
    return sorted(out, key=lambda w: w.offer_id)


def _options_on(fold, p: Offer, now: int) -> list[Offer]:
    """The open options written on `p`."""
    return sorted((o for o in fold.offers(now=now)
                   if o.v >= 6 and o.underlying == p.offer_id and o.kind == GIVE),
                  key=lambda o: o.offer_id)


def cmd_holds(args, session, out):
    """`holds`: every hold in the fold — the offer held, the option, its
    holder, until when, what is left of it, and whether it is active now.
    Named for what it lists (renamed from `options` 2026-09-29, Peter: the
    plural of `option` read as "the options I wrote" — which appear here
    only once they clear — and, at a command line, as settings)."""
    fold = session.fold()
    now = session.now
    rows = []
    for o in fold.offers(include_filled=True):
        for lid, rec in fold.holds(o.offer_id):
            rows.append({"offer": o.offer_id[:16], "option": rec["option"][:16], "holder": rec["holder"],
                         "until": _iso(int(rec["until"])), "left": _num(fold.hold_left(o.offer_id, lid)),
                         "active": "yes" if now < int(rec["until"]) else "no"})
    if not rows:
        print("no holds", file=out)
        return 0
    for r in sorted(rows, key=lambda r: (r["offer"], r["option"])):
        print(f"{r['offer']}  option {r['option']}  holder {r['holder']}  until {r['until']}  "
              f"left {r['left']}  active {r['active']}", file=out)
    return 0
