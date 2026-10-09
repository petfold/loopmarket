"""The guarantee settings as offer fields (v5 to v7): the deposit (`bond`,
`escrow`, `deductible`), what every counterparty must meet (`require_*`),
the cancellation ladder, the claim period and the arbitrator. The assets
a requirement names must be catalogue vocabulary, checked at publish."""

from __future__ import annotations

import dataclasses
import shlex

from ..schema import GIVE, WANT, q
from .grammar import parse_offer_tokens
from .settings import _configured
from .spellings import _calendar_span, duration_s


def _guarantees(now: int, concepts=(), side: str = GIVE) -> dict:
    """The guarantee settings as offer fields (v5, `P3-release-and-reclearing.md`
    §5d): `bond`/`escrow` as a `Bond` deposit — its asset by the offer
    grammar, its worth to me last — and `require_point`, `require_cancel`,
    `ladder`, `require_accepts`, `require_escrows` as a `Requires`. The
    ladder is derived over the lead from `now` to the offer's handover time
    term (the first `time(...)` among `concepts`); an offer with no time term
    gets no ladder — a cancellation costs the point. Nothing set: v4.
    v6 (E2, 2026-09-29): a give's `claim_max`; a want's `require_claim` and
    `require_resolvers` in its `Requires`; `arbitrator` on a give (a field
    every version carries)."""
    from ..schema import Acceptance, Bond, Requires, Thing
    out: dict = {}
    if side == GIVE:
        if _configured("arbitrator"):
            out["arbitrator"] = _configured("arbitrator")
        oracle = (_configured("oracle") or "countersign").strip()
        if oracle != "countersign":
            out["oracle"] = oracle
        if _configured("claim_max"):
            out["claim_max"] = duration_s(_configured("claim_max"))
    claim_period = duration_s(_configured("require_claim")) if side == WANT and _configured("require_claim") else 0
    resolvers = _resolver_acceptance(_configured("require_resolvers") or "")
    credentials = _credential_requirements(_configured("require_credentials") or "") if side == WANT else ()
    def default_asset():
        """My price for the asset a bare amount means — stated, never assumed."""
        spec = _configured("default_asset")
        if not spec:
            raise ValueError("a bare amount on my scale needs my price for an asset: "
                             "`set default_asset 'xdai xDAI PRICE'` (my price per xDAI on my scale), "
                             "or state the deposit by the grammar (`QTY[UNIT] CATEGORY... VALUE`) "
                             "and what I accept by `require_accepts`")
        toks = shlex.split(spec)
        if len(toks) < 3:
            raise ValueError("default_asset is `CATEGORY... UNIT PRICE`")
        return tuple(toks[:-2]), toks[-2], q(toks[-1])
    dep = _configured("bond")
    if dep:
        toks = shlex.split(dep)
        if len(toks) == 1:                         # a bare amount: on MY scale, deposited as the default
            value = q(toks[0])                     # asset at my price for it (value / price units)
            d_cat, d_unit, d_price = default_asset()
            out["bond"] = Bond(Thing(d_cat, value / d_price, d_unit), value, _escrow_address())
        else:
            parsed = parse_offer_tokens(toks)
            if parsed.qty is None or parsed.price is None or not parsed.concepts:
                raise ValueError("bond is an amount of the default asset, or `QTY[UNIT] CATEGORY... VALUE`: "
                                 "the deposit by the grammar, its worth to me last")
            out["bond"] = Bond(Thing(tuple(parsed.concepts), parsed.qty, parsed.unit or "unit"),
                               parsed.price, _escrow_address())
        if _configured("deductible"):
            # C5 (v7): typed on my scale, as every amount I type is, and held in
            # the deposit's asset at the price my deposit states (its worth per
            # unit) — one conversion, at posting, on my own scale (U14)
            bond = out["bond"]
            if not bond.value:
                raise ValueError("a deductible on my scale needs the deposit's worth to me, to convert it")
            out["bond"] = dataclasses.replace(
                bond, deductible=q(_configured("deductible")) * q(bond.asset.qty) / bond.value)
    point = q(_configured("require_point")) if _configured("require_point") else None
    accepts = []
    for entry in (e.strip() for e in (_configured("require_accepts") or "").split(";") if e.strip()):
        toks = shlex.split(entry)
        if len(toks) < 3:
            raise ValueError(f"require_accepts entry {entry!r} is `CATEGORY... UNIT PRICE`")
        accepts.append(Acceptance(tuple(toks[:-2]), toks[-2], q(toks[-1])))
    if point and not accepts:                      # a point with nothing named accepts the default asset
        accepts.append(Acceptance(*default_asset()))
    escrows = tuple(t for t in (_configured("require_escrows") or "").split() if t)
    door = (_configured("require_door") or "").strip() if side == WANT else ""
    # the types a door level stands for, not the level's name: the chain
    # checks a give's witness type against the want's list by exact name
    # (LoopVerifier), so a level name would refuse an honest leg on chain
    # (2026-10-01, Peter: a want lists today's types and lapses with its
    # validity; a new door type joins DOOR_LEVELS and later wants list it)
    from ..witness import DOOR_LEVELS
    oracles = (tuple(DOOR_LEVELS[{"possession": "door-at-least-possession",
                                  "photo": "door-at-least-photo"}[door]]) if door else ())
    if side == WANT:
        oracles += tuple(f"registry-transfer({r})" for r in (_configured("require_transfer") or "").split())
    if ((resolvers is not None and resolvers.min_deposit) or any(c.min_bond for c in credentials)) \
            and not accepts:
        accepts.append(Acceptance(*default_asset()))   # a deposit floor on my scale is priced by an acceptance
    if point is not None or accepts or escrows or claim_period or resolvers is not None or oracles \
            or credentials:
        ladder = ()
        if point is not None and _configured("require_cancel"):
            far = q(_configured("require_cancel"))
            lead = _handover_lead(concepts, now)
            if lead and lead > 0:
                ladder = _ladder(_configured("ladder") or "linear", lead, far, point)
        out["requires"] = Requires(point=point or 0, ladder=ladder, accepts=tuple(accepts), escrows=escrows,
                                   oracles=oracles, claim_period=claim_period,
                                   resolvers=resolvers, counterparty=credentials)
    if "bond" in out and out["bond"].deductible:
        out["v"] = 7                               # a deposit's deductible (C5); v7 carries v6's fields
    elif out.get("claim_max") or claim_period or resolvers is not None or credentials:
        out["v"] = 6
    elif "requires" in out or "bond" in out:
        out["v"] = 5
    return out


def _resolver_acceptance(text: str):
    """`require_resolvers` as an `Accept` (§7a), or None: bare tokens are
    keys; `root:ID` a trust root the resolver's rungs are accredited under;
    `min:AMOUNT` the least at stake on a reversed ruling, on my scale;
    `clean:DURATION` the look-back with no reversal."""
    from ..schema import Accept
    keys, roots, floor, clean = [], [], 0, 0
    for tok in text.split():
        head, sep, value = tok.partition(":")
        if not sep:
            keys.append(tok)
        elif head == "root" and value:
            roots.append(value)
        elif head == "min" and value:
            floor = q(value)
        elif head == "clean" and value:
            clean = duration_s(value)
        else:
            raise ValueError(f"require_resolvers token {tok!r}: a key, root:ID, min:AMOUNT or clean:DURATION")
    if not (keys or roots or floor or clean):
        return None
    return Accept(keys=tuple(keys), roots=tuple(roots), min_deposit=floor, clean_for=clean)


def _credential_requirements(text: str) -> tuple:
    """`require_credentials` as `Credential` entries (R4): `;`-separated,
    each `CATEGORY KIND[,KIND...] [root:ID]... [age:DURATION] [min:AMOUNT]`."""
    from ..schema import Credential
    out = []
    for entry in (e.strip() for e in text.split(";") if e.strip()):
        toks = entry.split()
        if len(toks) < 2:
            raise ValueError(f"require_credentials entry {entry!r} is `CATEGORY KIND[,KIND...] "
                             f"[root:ID]... [age:DURATION] [min:AMOUNT]`")
        roots, age, floor = [], 0, 0
        for tok in toks[2:]:
            head, sep, value = tok.partition(":")
            if head == "root" and value:
                roots.append(value)
            elif head == "age" and value:
                age = duration_s(value)
            elif head == "min" and value:
                floor = q(value)
            else:
                raise ValueError(f"require_credentials token {tok!r}: root:ID, age:DURATION or min:AMOUNT")
        out.append(Credential(toks[0], tuple(toks[1].split(",")), min_bond=floor, roots=tuple(roots),
                              max_root_age=age))
    return tuple(out)


def _escrow_address() -> str:
    """The address the record names: `chain:RPC@ADDRESS` or a bare address
    — the protocol names no RPC, and the id must not change with one."""
    spec = _configured("escrow") or ""
    return spec.rpartition("@")[2] if spec.startswith("chain:") else spec


def _check_asset_categories(offer, ontology) -> None:
    """The deposit's and the acceptances' categories must be the catalogue's:
    unknown, they would match nothing (U7) and the offer would sit unmatched
    without a word — so refuse at publish with the name to add."""
    names = []
    if offer.v >= 5 and offer.bond is not None:
        names += list(offer.bond.asset.concepts)
    if offer.requires is not None:
        for acc in offer.requires.accepts:
            names += list(acc.concepts)
    for name in names:
        if name not in ontology.dag.nodes:
            raise ValueError(f"asset category {name!r} is not in the catalogue: add it "
                             f"(e.g. `odag put {name} money`), or set default_asset / require_accepts")


def _handover_lead(concepts, now: int) -> int | None:
    """Seconds from `now` to the start of the offer's handover time term."""
    for term in concepts:
        if isinstance(term, str) and term.startswith("time(") and term.endswith(")"):
            try:
                start, _end = _calendar_span(term[5:-1])
            except Exception:                   # noqa: BLE001 — not a span this reader knows
                continue
            return start - now
    return None


def _ladder(shape: str, lead: int, far, point) -> tuple:
    """The cancellation ladder over the lead at posting, in one of a few
    shapes (Peter, 2026-09-19): the points only, on the maker's scale."""
    far, point = q(far), q(point)
    if shape == "linear":
        return ((lead, far), (0, point))
    if shape == "late":                            # flat, then rising over the last quarter
        return ((lead, far), (lead // 4, far), (0, point))
    if shape == "early":                           # rising over the first quarter, then flat
        return ((lead, far), (lead - lead // 4, point), (0, point))
    if shape == "flat":                            # the far amount until the window
        return ((lead, far), (1, far), (0, point))
    raise ValueError("ladder is linear, late, early or flat")
