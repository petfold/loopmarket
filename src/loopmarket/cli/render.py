"""The one renderer: the approval block *is* `show` (gate G4). Numbers for
people, exact both ways; a quantity read in words; the tables of `offers`
and `mine`; the lines a loop is printed as."""

from __future__ import annotations

from fractions import Fraction

from ontodag import dimensions as _dims

from ..graph import Circulation
from ..registry import OfferRegistry
from ..schema import GIVE, WANT, Offer, Thing, TimeWindow, q
from .settings import _err, _want_limit, _want_render
from .spellings import PART_SEP, _iso, _local


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


def _bond_text(offer: Offer) -> str:
    b = offer.bond
    if offer.v < 5:
        return f"bond {_num(q(b))}"
    if b is None:
        return "bond -"
    return (f"bond {_num(b.asset.qty)}{b.asset.unit} {' '.join(b.asset.concepts)} "
            f"worth {_num(b.value)}" + (f" in {b.escrow}" if b.escrow else " (not deposited)")
            + (f" deductible {_num(b.deductible)}{b.asset.unit}"
               + (f" worth {_num(b.deductible * b.value / q(b.asset.qty))}" if b.value else "")
               if b.deductible else ""))


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
                     + (f"  oracle {_oracles_text(req.oracles)}" if req.oracles else "")
                     + (f"  escrow {' '.join(req.escrows)}" if req.escrows else "")
                     + (f"  claim {_duration_text(req.claim_period)}" if req.claim_period else "")
                     + (f"  resolvers {_resolvers_text(req.resolvers)}" if req.resolvers is not None else "")
                     + (f"  credentials {_credentials_text(req.counterparty)}" if req.counterparty else "")
                     + (f"  legs {' '.join(l.category for l in req.legs)}" if req.legs else "")
                     + "  (of every counterparty, per fill; unmet is never matched)")
    if offer.v >= 6 and (offer.claim_max or offer.underlying):
        lines.insert(-2, "  v6      "
                     + (f" claim_max {_duration_text(offer.claim_max)}" if offer.claim_max else "")
                     + (f" option on {offer.underlying[:16]}… exercisable {_span(offer.exercise)}"
                        if offer.underlying else ""))
    return "\n".join(lines)


def _duration_text(seconds: int) -> str:
    """Seconds spelled as ontodag spells a duration — its renderer picks the
    largest of its units the value is whole in: `45s`, `90min`, `36h`,
    `30d`, `2wk` (review item 11). What `loop` prints, `odag` and `loop`
    read back to the same seconds."""
    from ontodag.surface import render
    return _dims.split_term(render(f"duration({int(seconds)}s)", kind=_dims.KIND_LINEAR))[1]


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


def _credentials_text(creds) -> str:
    return "; ".join(" ".join([c.category, ",".join(c.kinds), *(f"root:{r}" for r in c.roots),
                               *([f"age:{_duration_text(c.max_root_age)}"] if c.max_root_age else []),
                               *([f"min:{_num(c.min_bond)}"] if c.min_bond else [])]) for c in creds)


def _resolvers_text(acc) -> str:
    return " ".join([*acc.keys, *(f"root:{r}" for r in acc.roots),
                     *([f"min:{_num(acc.min_deposit)}"] if acc.min_deposit else []),
                     *([f"clean:{_duration_text(acc.clean_for)}"] if acc.clean_for else [])])


def _age(seconds: int) -> str:
    """How long ago, rounded down, in ontodag's units."""
    if seconds < 3600:
        return f"{max(seconds, 0) // 60}min"
    if seconds < 86_400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86_400}d"


def _oracles_text(oracles) -> str:
    """The witness types a requirement accepts, a door level named where
    the types are exactly one level's (`door at least possession`)."""
    from ..witness import DOOR_LEVELS
    names = set(oracles)
    for level, types in DOOR_LEVELS.items():
        if set(types) <= names:
            rest = sorted(names - set(types))
            return " ".join([level.replace("door-at-least-", "door at least "), *rest])
    return " ".join(sorted(names))


def _round_amount(x) -> Fraction:
    return Fraction(round(float(x) * 100), 100)


def _duration_approx(seconds: int) -> str:
    """Seconds in the largest of ontodag's units `d`, `h`, `min` they
    reach, rounded: for notes that estimate (an option's window, a demand
    rate). Exact spellings, for what an offer states, are
    `_duration_text`'s; until 2026-10-09 this one had the same name, so it
    silently replaced the exact one in the approval block (a 100 s claim
    period showed rounded)."""
    from .spellings import duration_s
    for unit in ("d", "h", "min"):
        size = duration_s(f"1{unit}")             # the unit's size is ontodag's
        if seconds >= size:
            return f"{_num(_round_amount(Fraction(seconds, size)))}{unit}"
    return f"{seconds}s"


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
