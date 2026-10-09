"""Drafts (cli.md §13): values at the edge, offers at the end.

A draft is an unpublished offer or one part of a composed want: resolved
now, exactly as a `want` line resolves, named or numbered, kept in a
local file that is never the book — no id, no matching, no price unless
the person put one there. `draft NAME A + B` composes drafts with the same
`+` the one-line want uses (Peter, 2026-09-12: one operator, not a verb);
`offer NAME [PRICE]` (entry.py) turns a draft into an offer. Draft names
are working memory, never vocabulary: they cannot appear in an offer,
because composition expands them. Settings stay a closed table (`set`),
so a typo cannot quietly become a draft."""

from __future__ import annotations

import json
import os

from ..schema import GIVE, WANT, Thing, q
from .grammar import (_PRICE_RE, Composed, Part, _resolve_part, parse_offer_tokens, parse_want_line,
                      part_line)
from .render import _num
from .settings import _configured, _err, _home_dir
from .spellings import PART_SEP


def _drafts_path() -> str:
    return os.path.join(_home_dir(), "drafts")


def _read_drafts() -> list[dict]:
    path = _drafts_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_drafts(drafts: list[dict]) -> None:
    os.makedirs(_home_dir(), mode=0o700, exist_ok=True)
    with open(_drafts_path(), "w", encoding="utf-8") as fh:
        for d in drafts:
            fh.write(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")


def _part_record(part: Part) -> dict:
    return {"thing": part.thing.to_record(), "notes": list(part.notes),
            "addresses": list(part.addresses)}


def _part_from_record(rec: dict) -> Part:
    t = rec["thing"]
    thing = Thing(tuple(t["concepts"]), q(t["qty"]), t["unit"],
                  step=q(t["step"]), min=q(t["min"])) if "step" in t else \
        Thing(tuple(t["concepts"]), t["qty"], t["unit"], t["divisible"])
    return Part(thing, list(rec["notes"]), list(rec.get("addresses", [])))


def _draft_line(d: dict) -> str:
    """A draft's canonical spelling: the offer line `offer` will speak."""
    body = f" {PART_SEP} ".join(part_line(_part_from_record(r)) for r in d["parts"])
    price = "" if d.get("price") is None else f" {_num(d['price'])}"
    return f"{d['side']} {body}{price}"


def _find_draft(drafts: list[dict], ref: str) -> dict:
    for d in drafts:
        if d["name"] == ref:
            return d
    raise ValueError(f"no such draft: {ref} (`loop drafts` lists them)")


_VERBS = (GIVE, WANT)


def cmd_draft(args, session, out):
    """`draft [NAME] want|give ...` stages a resolved offer or part;
    `draft [NAME] A + B ...` composes drafts. Re-drafting a name replaces
    it; an omitted name is the next number."""
    toks = list(args.tokens)
    if not toks:
        raise ValueError("draft [NAME] want|give ...   or   draft [NAME] A + B ...")
    name = None
    if toks[0] not in _VERBS:
        name = toks.pop(0)
        if name in _VERBS or name == PART_SEP or _PRICE_RE.match(name):
            raise ValueError(f"{name!r} cannot name a draft — verbs, `{PART_SEP}` "
                             f"and numbers are taken (numbers are the unnamed)")
    if not toks:
        raise ValueError(f"draft {name}: then a want/give line, or drafts joined "
                         f"by {PART_SEP}")
    drafts = _read_drafts()
    ontology = session.catalogue
    maker = session.maker
    if toks[0] in _VERBS:
        side = toks.pop(0)
        if side == WANT:
            parsed = parse_want_line(toks)
        else:
            parsed = parse_offer_tokens(toks)
        if isinstance(parsed, Composed):
            parts = [_resolve_part(session, p, ontology) for p in parsed.parts]
            price = parsed.price
        else:
            if "valid" in parsed.heads:
                raise ValueError("a draft has no validity of its own — it gets the "
                                 "`valid` setting when offered")
            parts = [_resolve_part(session, parsed, ontology, side)]
            price = parsed.price
    else:
        # drafts joined by `+`: composition, want side only, flattening
        refs = [t for t in toks if t != PART_SEP]
        if any(t == PART_SEP for t in (toks[0], toks[-1])) or \
                len(refs) != toks.count(PART_SEP) + 1:
            raise ValueError(f"drafts are joined as A {PART_SEP} B {PART_SEP} C")
        side, parts, price = WANT, [], None
        for ref in refs:
            d = _find_draft(drafts, ref)
            if d["side"] != WANT:
                raise ValueError(f"{ref} is a give: composition is want-side only "
                                 f"(docs/plans/cli.md §13) — a kit is one give")
            if d.get("price") is not None and len(refs) > 1:
                raise ValueError(
                    f"{ref} carries a price ({_num(d['price'])}); parts carry no "
                    f"prices — one price for the whole, at `offer` "
                    f"(P2-loop-selection.md §10 pays once). Re-draft it without")
            if d["maker"] != maker:
                raise ValueError(f"{ref} was drafted as {d['maker']}, not {maker}")
            parts.extend(_part_from_record(r) for r in d["parts"])
            if len(refs) == 1:
                price = d.get("price")        # a copy keeps its price
    existing = _find_draft(drafts, name) if name and any(
        d["name"] == name for d in drafts) else None
    n = existing["n"] if existing else max((d["n"] for d in drafts), default=0) + 1
    record = {"name": name or str(n), "n": n, "maker": maker, "side": side,
              "parts": [_part_record(p) for p in parts], "price": price,
              "typed": " ".join(args.tokens), "created": session.now}
    drafts = [d for d in drafts if d["n"] != n] + [record]
    drafts.sort(key=lambda d: d["n"])
    _write_drafts(drafts)
    print(f"{record['name']}  {_draft_line(record)}", file=out)
    return 0


def cmd_drafts(args, session, out):
    """Every draft in its canonical spelling — what `offer` will say —
    with the typed spelling and the name→value notes beneath: the
    approval block's two layers."""
    drafts = _read_drafts()
    for d in drafts:
        print(f"{d['name']}  {_draft_line(d)}", file=out)
        print(f"   typed {d['typed']}", file=out)
        notes = [f"part {i}: {n}" if len(d["parts"]) > 1 else n
                 for i, r in enumerate(d["parts"], 1) for n in r["notes"]]
        for note in notes:
            print(f"   note  {note}", file=out)
        if d["maker"] != _configured("maker"):
            print(f"   maker {d['maker']}", file=out)
    return 0 if drafts else 1


def cmd_discard(args, session, out):
    drafts = _read_drafts()
    if not args.refs:
        _write_drafts([])
        print(f"{len(drafts)} discarded", file=_err())
        return 0
    chosen = [_find_draft(drafts, ref) for ref in args.refs]
    _write_drafts([d for d in drafts if d not in chosen])
    return 0
