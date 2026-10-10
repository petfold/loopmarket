"""Parsing and resolving an offer line: ontodag's grammar plus the two
conventions (a bare number first is the quantity, a bare number last is
the price). Each token then becomes catalogue vocabulary — a catalogue
name as spelled, a private place as the cell it hangs under, a bare
coordinate or time under the handover head the catalogue marks — and the
line's thing a `Part`, shared by a simple offer, a draft and each part of
a composed want."""

from __future__ import annotations

import re
import shlex
from collections import namedtuple

from ontodag import OntoDAG
from ontodag import dimensions as _dims

from ..ontology import Ontology
from ..schema import WANT, Thing, q
from ..spacetime import cell_for_coords
from .render import _num
from .settings import _configured
from .spellings import (PART_SEP, _INTERPRETED_HEADS, _iso, _looks_like_time, _number, parse_coords,
                        window)
from .stores import Session


#: The quantity token (cli.md §6, v4 since 2026-09-14): `[MIN..]QTY[UNIT][:STEP]`.
#: `10kg` — up to 10 kg, divisible; `3` — three, indivisible; `1000:1` — a
#: thousand by the piece; `50kg..100kg:25` — a hundred kilos in 25 kg sacks,
#: fifty at least (the give-side floor). The colon is the one new symbol:
#: `/` is ontodag's rational (`1/2kg` is half a kilo), `x` its tuple.
_NUM = r"\d+(?:\.\d+)?"
_QTY_RE = re.compile(rf"^({_NUM})([A-Za-z][A-Za-z0-9]*)?(?::({_NUM}))?$")
_BAND_RE = re.compile(
    rf"^({_NUM}(?:[A-Za-z][A-Za-z0-9]*)?)?\.\."
    rf"({_NUM}(?:[A-Za-z][A-Za-z0-9]*)?)?(?::({_NUM}))?$")
_PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")

Parsed = namedtuple("Parsed", "qty unit divisible band concepts heads price step min",
                    defaults=(None, 0))
Composed = namedtuple("Composed", "parts price valid", defaults=(None,))


def parse_want_line(tokens: list[str]) -> "Parsed | Composed":
    """A `want` line: one thing, or parts separated by `+` with one price
    last for the lot. Each part reads as a want line without its price
    (a bare number first is that part's quantity); parts carry no price
    (P2-loop-selection.md §10 pays once) and no validity of their own."""
    toks = _join_terms(list(tokens))
    if PART_SEP not in toks:
        return parse_offer_tokens(toks)
    price = None
    if toks and _PRICE_RE.match(toks[-1]):
        price = _number(toks.pop())
    # the composed want's one validity: a trailing `valid(...)`, after the
    # last part and before the price — where `line_for` writes it; inside a
    # part it is refused (a part has no validity of its own)
    valid = None
    if toks and toks[-1].startswith("valid(") and toks[-1].endswith(")"):
        valid = toks.pop()[len("valid("):-1]
    parts, current = [], []
    for tok in toks + [PART_SEP]:
        if tok == PART_SEP:
            if not current:
                raise ValueError(
                    f"{' '.join(tokens)}: an empty part around `{PART_SEP}` — "
                    f"each part names what is wanted")
            parts.append(parse_part_tokens(current))
            current = []
        else:
            current.append(tok)
    return Composed(tuple(parts), price, valid)


def parse_part_tokens(tokens: list[str]) -> Parsed:
    """One part of a composed want: a want line with no price and no
    validity (the composed want has one of each)."""
    parsed = parse_offer_tokens(tokens)
    if parsed.price is not None:
        raise ValueError(
            f"{' '.join(tokens)}: parts carry no prices — one price, last on "
            f"the line, for the whole (docs/plans/P2-loop-selection.md §10 "
            f"pays once; clearing splits)")
    if "valid" in parsed.heads:
        raise ValueError(
            f"{' '.join(tokens)}: a part has no validity of its own — the "
            f"composed want's is the `valid` setting (or --valid)")
    return parsed


def _join_terms(tokens: list[str]) -> list[str]:
    """An operator's argument may be a conjunction —
    `transport(small-item mass(..8kg))` — and the line splits on spaces,
    so tokens are rejoined while a parenthesis is open (the same line
    quoted, `'transport(small-item mass(..8kg))'`, arrives whole). The
    catalogue then spells it canonically (`_canonical`)."""
    out, depth, cur = [], 0, ""
    for tok in tokens:
        cur = f"{cur} {tok}" if depth else tok
        depth += tok.count("(") - tok.count(")")
        if depth <= 0:
            out.append(cur)
            cur, depth = "", 0
    if cur:
        raise ValueError(f"{cur}: unbalanced parentheses")
    return out


def parse_offer_tokens(tokens: list[str]) -> Parsed:
    """`[10kg] CATEGORY|TERM ... [PRICE]` → the pieces, nothing resolved.

    Every token that is neither convention is passed through as written:
    a bare word is a category, `head(param)` is a term, and the one
    interpreted head (`valid`) is separated so the caller can map it onto
    the offer's field. Band spellings in quantity position are *accepted*
    here and refused at publish (gate G6) — they are the grammar."""
    toks = _join_terms(list(tokens))
    if not toks:
        raise ValueError("what? — give/want [QUANTITY] CATEGORY... [PRICE]")
    if PART_SEP in toks:
        raise ValueError(
            f"`{PART_SEP}` composes parts of a *want* only (docs/plans/cli.md "
            f"§13): a give of several things that go together is one give of "
            f"one thing — the kit is a category")
    qty, unit, divisible, band, step, floor = None, "unit", False, None, None, 0
    m = _QTY_RE.match(toks[0])
    b = _BAND_RE.match(toks[0])
    if b and toks[0] != "..":
        band = toks.pop(0)
        low, high, s = b.groups()
        if low and high:                 # `MIN..QTY[UNIT][:STEP]`: a floor and a quantity
            hm, lm = _QTY_RE.match(high), _QTY_RE.match(low)
            if hm and lm and (lm.group(2) or "unit") == (hm.group(2) or "unit"):
                qty, unit = _number(hm.group(1)), hm.group(2) or "unit"
                floor = _number(lm.group(1))
                step = _number(s) if s else (0 if hm.group(2) else None)
                divisible = q(step if step is not None else qty) != q(qty)
                band = None
    elif m:
        qty = _number(m.group(1))
        unit = m.group(2) or "unit"
        step = _number(m.group(3)) if m.group(3) else (0 if m.group(2) else None)
        divisible = q(step if step is not None else qty) != q(qty)
        toks.pop(0)
    price = None
    if len(toks) > 1 and _PRICE_RE.match(toks[-1]):
        price = _number(toks.pop())
    elif len(toks) == 1 and _PRICE_RE.match(toks[0]) and qty is not None:
        raise ValueError(
            f"{' '.join(tokens)}: a bare number first is the quantity and a "
            f"bare number last is the price — name what is exchanged")
    if not toks:
        raise ValueError(
            f"{' '.join(tokens)}: a bare number first is the quantity — "
            f"name what is exchanged")
    concepts, heads = [], {}
    for tok in toks:
        split = _dims.split_term(tok)
        if split and split[0] in _INTERPRETED_HEADS:
            if split[0] in heads:
                raise ValueError(f"{split[0]}(...) given twice")
            heads[split[0]] = split[1]
        else:
            concepts.append(tok)
    return Parsed(qty, unit, divisible, band, tuple(concepts), heads, price, step, floor)


# Dimension kinds whose values are offer *fields* today: quantities live in
# `Thing.qty` (linear, count). A term of these kinds beside the field would
# be double bookkeeping, so it is refused until ontodag-coupling.md §3 makes
# quantities terms. Every other kind passes through into the conjunction:
# prefix (places), calendar (times — relative spellings elaborated to fixed
# UTC on the way), dominance.
_FIELD_KINDS = frozenset({_dims.KIND_LINEAR, _dims.KIND_COUNT})


def _unknown_hint(term: str, dag: OntoDAG) -> str:
    """How to make an unknown concept known. A term of a prelude head the
    catalogue lacks means its prelude predates the head (ontodag 0.30's
    prelude v4 brought `mass`, `in`, `about`, `shared-with`); `weight(...)`
    is no prelude term at all since v4, which says `mass`."""
    from ontodag.prelude import DECLARATIONS
    split = _dims.split_term(term)
    if split is not None and split[0] not in dag.nodes:
        if split[0] == "weight":
            return (f"ontodag's prelude has no `weight` since v4 (weight is a "
                    f"force): spell it mass({split[1]})")
        if split[0] in {name for name, _ in DECLARATIONS}:
            return (f"the catalogue's prelude predates `{split[0]}`: "
                    f"`odag prelude` merges the current one (it moves the "
                    f"catalogue root, so offers pinned to the old root stop "
                    f"matching)")
    return f"`odag put {term} PARENT` adds it to the catalogue"


def _head_kind(dag: OntoDAG, head: str) -> str | None:
    """The dimension kind a declared head belongs to, else None."""
    if head not in dag.nodes or "dimension" not in dag.nodes \
            or _dims.is_kind_node(head) or not dag.is_below(head, "dimension"):
        return None
    for kind in sorted(_dims.KINDS):
        if kind in dag.nodes and dag.is_below(head, kind):
            return kind
    return "dimension"


def _value_of(view: OntoDAG, name: str, kind: str) -> str | None:
    """A *private* name's public value in a dimension of `kind`: the
    parameter of the term it (or an ancestor) hangs under — `my_home`
    under `geo(u2e4x)` yields `u2e4x`. Used only for names the pinned
    catalogue does not hold (the personal layer's places): the same-root
    constraint means a counterparty can interpret `from(my_home)` only if
    `my_home` is in the root the offer pins, so a private place publishes
    as its cell and the name stays private (`cli.md` §12). A catalogue
    name needs none of this since ontodag #15: it stands as spelled."""
    node = view.nodes.get(name)
    if node is None:
        return None
    best = None
    for item in [node, *view.get_ancestors(node)]:
        split = _dims.split_term(item.name)
        if not split or _head_kind(view, split[0]) != kind:
            continue
        # A place hangs under its own cell and, by computed prefix
        # containment, under every coarser cell too; ancestors come as a
        # set. The name's value is the most specific term: the one that
        # fits within all the others.
        if best is None or view.is_below(item.name, best.name):
            best = item
    return _dims.split_term(best.name)[1] if best is not None else None


def _term_of(view: OntoDAG, name: str) -> str | None:
    """The most specific dimension term a name hangs under, whatever its
    kind — `home` under `geo(u2e4x)` yields `geo(u2e4x)`. What a *private*
    place publishes as when typed bare (Peter, 2026-09-13: a bare geo term
    is where the offer holds; no `where` head)."""
    node = view.nodes.get(name)
    if node is None:
        return None
    best = None
    for item in [node, *view.get_ancestors(node)]:
        split = _dims.split_term(item.name)
        if not split or _head_kind(view, split[0]) is None:
            continue
        if best is None or view.is_below(item.name, best.name):
            best = item
    return best.name if best is not None else None


def _handover_base(ontology: Ontology, kind: str, spelling: str) -> str:
    """The base head of `kind` the catalogue marks as a handover
    coordinate — where a bare coordinate literal or time spelling goes
    (`46.05,14.50,5km` → `geo(u2e4x)`, `today..+7d` → `time(...)`). The
    CLI names no head: it asks the catalogue which head under `handover`
    is a base of that kind, and refuses when there is none."""
    dag = ontology.dag
    bases = [head for head in sorted(ontology.handover_heads())
             if _head_kind(dag, head) == kind
             and any(_dims.is_kind_node(p.name) for p in dag.nodes[head].parents)]
    if len(bases) > 1:
        raise ValueError(
            f"{spelling}: the catalogue marks several {kind} heads as "
            f"handover coordinates ({', '.join(bases)}) — spell the head: "
            f"`{bases[0]}({spelling})`")
    if bases:
        return bases[0]
    raise ValueError(
        f"{spelling}: the catalogue marks no {kind} head as a handover "
        f"coordinate, so a bare {'coordinate' if kind == _dims.KIND_PREFIX else 'time'} "
        f"has no head to go under — `odag put geo prefix-dimension handover`")


def _elaborate_terms(session: "Session", concepts, ontology: Ontology):
    """Each token: let a catalogue name stand as spelled, publish a
    *private* place as the dimension term it hangs under, turn a bare
    coordinate literal into a cell and a bare time spelling into a fixed-UTC
    window (input vocabulary, cli.md §2) — both under the base head the
    catalogue marks as a handover coordinate — and, for `head(param)`
    tokens, refuse quantity kinds (the field owns them) and check the
    result is vocabulary. Head-agnostic on purpose — the CLI knows kinds,
    never heads (Peter, 2026-09-12); since 2026-09-13 there is no `where`
    or `when` head at all: `give vegetable-box shop` says the box is at the
    shop. Returns (concepts, notes, addresses): the addresses are the
    settlement texts of the named places (`place NAME ... ADDRESS`), kept
    locally and sealed to the counterparty at clearing (handoff.py).

    Names, since ontodag #15 (2026-09-12): a parameter that names a node
    of the *pinned catalogue* — a place under a cell, a region above
    cells, a floor under a building — is stored as spelled
    (`ljubljana`, `my_home_4th`, `from(my_home)`): ontodag orders it by the
    graph, and the counterparty, matching under the same root, can. A
    name only the personal layer holds is one the root does not carry, so
    it publishes as the cell it hangs under (`from(my_home)` →
    `from(u2e4x)`) and the name stays private; a private region or floor
    has no single value and is refused — publish it to the catalogue, or
    name a cell. A name outside the dimension is refused by ontodag in
    its own words, never read as a literal that happens to spell the same
    (a place called `u2e` must not become the cell `u2e`)."""
    dag = ontology.dag
    out, notes, addresses = [], [], []
    for c in concepts:
        if ontology.operator_of(c) is not None:
            out.append(_canonical(c, dag, notes))   # `transport(bicycle)`: `known` decides
            continue
        split = _dims.split_term(c)
        kind = _head_kind(dag, split[0]) if split else None
        if kind is None:
            if c in dag.nodes:          # a catalogue name (a place, a category)
                address = dag.nodes[c].metadata.get("address")
                if address:
                    addresses.append(f"{c}: {address}")
                out.append(c)
                continue
            view = session.view()
            term = None
            if c in view.nodes:         # a private name: publish its term
                term = _term_of(view, c)
                address = view.nodes[c].metadata.get("address")
                if term and address:
                    addresses.append(f"{c}: {address}")
            elif "," in c and c.count(",") == 2:
                lat, lon, radius = parse_coords(c)
                head = _handover_base(ontology, _dims.KIND_PREFIX, c)
                term = ontology.cell_term(head, cell_for_coords(lat, lon, radius))
            elif _looks_like_time(c):
                w = window(c, session.now)
                end = "" if w.end is None else _iso(w.end - 1)
                head = _handover_base(ontology, _dims.KIND_CALENDAR, c)
                term = f"{head}({_iso(w.start)}..{end})"
            if term is None:
                out.append(c)           # unknown: fails closed at `known`
                continue
            notes.append(f"{c} → {term}")
            out.append(term)
            continue
        head, param = split
        if kind in _FIELD_KINDS:
            raise ValueError(
                f"{c}: a quantity term is accepted by the grammar but not "
                f"encodable until quantities become catalogue terms "
                f"(docs/plans/ontodag-coupling.md §3). Encodable today: a "
                f"bare quantity first (`10kg`)")
        view = session.view()
        term = c
        if param in dag.nodes:
            pass                        # a catalogue name: ontodag's to order
        elif param in view.nodes:
            value = _value_of(view, param, kind)
            if value is None:
                raise ValueError(
                    f"{c}: `{param}` is a private name (your personal store, "
                    f"not the catalogue offers pin) with no single {head} "
                    f"value to publish in its place — `loop place {param} "
                    f"LAT,LON,RADIUS` gives a place its cell; a region or a "
                    f"floor must be in the catalogue to be named in an offer")
            term = ontology.cell_term(head, value) if kind == _dims.KIND_PREFIX \
                else f"{head}({value})"
        elif kind == _dims.KIND_PREFIX and "," in param:
            lat, lon, radius = parse_coords(param)
            term = ontology.cell_term(head, cell_for_coords(lat, lon, radius))
        elif kind == _dims.KIND_PREFIX and "(" not in param \
                and ontology.is_geo_role(head):
            # ontodag 0.31 (its review question 14): in a role of geo a bare
            # word names a place, and a cell is written by its own name.
            # Before, `from(sydney)` was read as a cell in southern Turkey.
            hint = (f", or, for the geohash cell {param!r}, write "
                    f"{head}({_dims.GEO_HEAD}({param}))"
                    if _dims.GEOHASH_RE.match(param) else "")
            raise ValueError(
                f"{c}: {param!r} is no place the catalogue or your names "
                f"know — `loop place {param} LAT,LON,RADIUS` files it under "
                f"its cell{hint}")
        elif kind == _dims.KIND_CALENDAR and not ontology.known(c):
            w = window(param, session.now)
            end = "" if w.end is None else _iso(w.end - 1)
            term = f"{head}({_iso(w.start)}..{end})"
        if param in view.nodes:
            address = view.nodes[param].metadata.get("address")
            if address:
                addresses.append(f"{c}: {address}")
        if term != c:
            notes.append(f"{c} → {term}")
            c = term
        cell = _dims.cell_value(c) if kind == _dims.KIND_PREFIX else None
        if cell is not None and not _dims.GEOHASH_RE.match(cell):
            raise ValueError(
                f"{c}: a geo cell is a geohash, written with digits and the "
                f"lowercase letters other than a, i, l and o, and {cell!r} is "
                f"none — a named place is filed under its cell: `loop place "
                f"{cell} LAT,LON,RADIUS`")
        if not ontology.known(c):
            try:                        # ontodag's own reason, when it has one
                dag.is_below(c, c)
            except ValueError as e:
                raise ValueError(str(e)) from None
            raise ValueError(
                f"{c}: not a value `{head}` accepts, and not a name the "
                f"catalogue knows in that dimension")
        out.append(_canonical(c, dag, notes))
    return tuple(out), notes, addresses


def _canonical(term: str, dag, notes: list[str]) -> str:
    """The catalogue's canonical spelling of a known term — `mass(8000g)`
    → `mass(8kg)`, `transport(small-item mass(..8kg))` →
    `transport(mass(..8kg) small-item)` — so one denotation is one offer
    id (U2). The catalogue's rule, not the CLI's: `surface.elaborate`."""
    from ontodag.surface import elaborate
    canonical = elaborate(term, dag)
    if canonical != term:
        notes.append(f"{term} → {canonical}")
    return canonical


Part = namedtuple("Part", "thing notes addresses")


def _term_class(session: "Session", token: str) -> str:
    """What a default term and a line's token compete on: the head of a
    `head(param)` token, the dimension head a bare name hangs under in the
    view (`home` → `geo`), else the token itself."""
    split = _dims.split_term(token)
    if split is not None:
        return split[0]
    term = _term_of(session.view(), token)
    if term is not None:
        return _dims.split_term(term)[0]
    kind = _dims.KIND_PREFIX if "," in token and token.count(",") == 2 \
        else _dims.KIND_CALENDAR if _looks_like_time(token) else None
    if kind is not None:
        try:                        # the base head a bare literal goes under
            return _handover_base(session.catalogue, kind, token)
        except ValueError:
            return kind
    return token


def _default_terms(session: "Session", parsed: Parsed) -> list[str]:
    """The `terms` setting's defaults whose coordinate the line does not
    already state (cli.md §3): `set terms home` puts every offer at home
    unless the line names a place. Place and time are optional since the
    v3 record — unset, an offer is anywhere, any time — and the CLI knows
    no head by name."""
    named = {_term_class(session, c) for c in parsed.concepts}
    return [term for term in shlex.split(_configured("terms") or "")
            if _term_class(session, term) not in named]


def _resolve_part(session: Session, parsed: Parsed, ontology: Ontology,
                  side: str = WANT) -> Part:
    """The thing — every default and shorthand expanded, every name resolved
    to its value — plus the notes that carry the surface spellings. Shared
    by a simple offer, a draft and each part of a composed want. Refusals
    here are the loud kind."""
    notes: list[str] = []
    if parsed.band:
        point = parsed.band.split("..")[-1].split(":")[0] or parsed.band.split("..")[0] or "10kg"
        raise ValueError(
            f"{parsed.band}: a floor alone or a ceiling alone names no quantity "
            f"— a give says how much and, before `..`, the least one fill may "
            f"take (`50kg..100kg`, cli.md §6); a want names the point "
            f"(`{point}`), its floor being a partial-fill matter (P2)")
    if side == WANT and (parsed.min or (parsed.step is not None and parsed.qty is not None
                                        and q(parsed.step) not in (0, q(parsed.qty)))):
        raise ValueError(
            "a floor or a step is the give's: a want names what it wants "
            "(the give's `step` and `min` decide the fill, cli.md §6)")
    defaults = _default_terms(session, parsed)
    for term in defaults:
        notes.append(f"default {term}")
    concepts, term_notes, addresses = _elaborate_terms(
        session, tuple(parsed.concepts) + tuple(defaults), ontology)
    notes.extend(term_notes)
    for c in concepts:
        if not ontology.known(c):
            raise ValueError(
                f"unknown category: {c} — vocabulary fails closed (U7); "
                + _unknown_hint(c, ontology.dag))

    # An omitted quantity is the schema's own default, not a typed `1`:
    # canonical JSON tells 1 from 1.0, and `Thing(("x",))` from the API
    # must produce the same record bytes as `give x 100` (gate G1, U2).
    if parsed.qty is None:
        thing = Thing(concepts, unit=parsed.unit, divisible=parsed.divisible)
    else:
        thing = Thing(concepts, parsed.qty, parsed.unit, step=parsed.step,
                      min=parsed.min)
    return Part(thing, notes, addresses)


def part_line(part: Part) -> str:
    """The canonical one-line spelling of a resolved part: what `compose`
    encodes, re-parseable as typed (cli.md §13 — `drafts` prints it, and a
    composed want's `+` line is these joined)."""
    t = part.thing
    toks = []
    unit = "" if t.unit == "unit" else t.unit
    default_step = 0 if unit else q(t.qty)          # what the bare spelling means
    if unit or q(t.qty) != 1 or q(t.step) != default_step or q(t.min):
        spelling = f"{_num(t.qty)}{unit}"
        if q(t.step) != default_step:
            spelling += f":{_num(t.step)}"
        if q(t.min):
            spelling = f"{_num(t.min)}{unit}..{spelling}"
        toks.append(spelling)
    toks.extend(t.concepts)
    return " ".join(toks)
