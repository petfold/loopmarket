"""Loop selection: which set of candidate loops clears (P2,
`docs/plans/P2-loop-selection.md` §1–§4, §8; built 2026-09-18).

The baseline answered "does a profitable cycle exist?" and took the first
one; selection answers "given many candidates, overlapping in offers,
which feasible set is worth most?" — a packing, not a search (§1). Since
fills take the wants' own quantities (decided 2026-09-14: no rounding,
ever), every candidate is all-or-nothing and the constraints are the
offers' capacities: an indivisible offer, or a want, is used at most once;
a divisible give may serve several loops as long as what they take sums
to no more than what is left of it (U11's oversold rule, seen from the
front). That is the packing ILP of §2 with capacities in place of
disjointness; the flow LP's own regime — quantities that scale — does not
arise while wants are whole, so one formulation covers both sides of §2's
table and the LP relaxation is only a bound.

Exactness is affordable where it matters (§3): up to `exact_up_to`
candidates the packing is solved exactly by depth-first branch and bound
within a deterministic work budget — a function of the instance, never of
the clock, so every replica reaches the same answer (U6) — and beyond
either limit the deterministic greedy takes over: candidates by weight,
each taken if it still fits. Both runs use one total order (§8): higher
score, then fewer legs, then the smaller sorted tuple of loop ids, then
the smaller canonical encoding of the legs.

The objective is §4's failure-aware expected settled surplus,
Σ q(L) · log Π r with q(L) = (1 − p)^|L|. Until U12-compliant loss data
exists the prior is uninformative (gate G3): `prior` is one constant for
every offer, and at its default 0 the objective is plain log surplus,
compared as the exact product of (1 + gain) over the set (U14: no
numeraire, no float). A positive prior is a geometric length penalty and
is evaluated in fixed-precision decimal arithmetic, whose natural
logarithm is correctly rounded by specification, so replicas agree to the
last digit. What each offer gets from a loop is today's clearing rule,
the loop's uniform per-leg gain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, Iterable

from .schema import q

EXACT_UP_TO = 24            # candidates enumerated exactly at most (N*, §3; G2's harness pins it later)
BUDGET = 200_000            # branch-and-bound nodes before the greedy takes over — a size, never a clock
PRECISION = 50              # decimal digits for the prior-weighted objective


@dataclass(frozen=True)
class Item:
    """A candidate loop as the packer sees it: what it takes from each
    offer, its legs, its gain, and its place in the total order."""

    key: tuple                       # (loop_id, canonical legs / source) — §8's rules 3 and 4
    takes: dict                      # offer id -> quantity this loop takes (wants: their whole quantity)
    legs: int
    gain: Fraction                   # the uniform per-leg gain every member receives
    payload: Any = None              # the Loop / Circulation / Candidate behind it

    @property
    def offers(self) -> frozenset:
        return frozenset(self.takes)


@dataclass(frozen=True)
class Packing:
    chosen: list                     # Items, in the total order
    exact: bool                      # solved exactly, or the greedy fallback
    infeasible: dict = field(default_factory=dict)   # key -> why the item alone cannot clear


def item_of(loop, key_extra: str = "") -> Item:
    """The packer's view of a loop or circulation: a want is taken whole
    (its quantity; a composed want counts as one), a give by what the leg
    takes. The payload stays the object given (a `Loop` stays a `Loop`)."""
    from .graph import Circulation
    circulation = loop if isinstance(loop, Circulation) else Circulation.from_loop(loop)
    takes: dict = {}
    for leg in circulation.legs:
        want = leg.want
        takes[want.offer_id] = takes.get(want.offer_id, Fraction(0)) + \
            (Fraction(1) if want.composed else q(want.thing.qty))
        for i, g in enumerate(leg.gives):
            takes[g.offer_id] = takes.get(g.offer_id, Fraction(0)) + leg.taken(i)
    legs_key = "|".join(sorted(leg.key for leg in circulation.legs))
    return Item((circulation.loop_id, legs_key, key_extra), takes, len(circulation.legs),
                circulation.surplus, loop)


def disjoint_capacity(items: Iterable[Item]) -> dict:
    """The capacity that makes packing offer-disjoint: each offer's largest
    take, so no two items through it fit together."""
    cap: dict = {}
    for it in items:
        for oid, t in it.takes.items():
            cap[oid] = max(cap.get(oid, Fraction(0)), t)
    return cap


# --------------------------------------------------------------------------- #
# The objective
# --------------------------------------------------------------------------- #

def weight(item: Item, prior=0):
    """One loop's contribution: (1 + gain) as an exact factor when the
    prior is 0, else q(L) · ln(1 + gain) as a decimal."""
    prior = q(prior)
    if prior == 0:
        return 1 + item.gain
    with localcontext() as ctx:
        ctx.prec = PRECISION
        g = Decimal(item.gain.numerator) / Decimal(item.gain.denominator)
        qf = ((1 - prior) ** item.legs)
        return (Decimal(qf.numerator) / Decimal(qf.denominator)) * (1 + g).ln()


def objective(items: Iterable[Item], prior=0):
    """The score of a set: Π (1 + gain) exactly, or Σ q · ln(1 + gain)."""
    prior = q(prior)
    if prior == 0:
        total = Fraction(1)
        for it in items:
            total *= 1 + it.gain
        return total
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return sum((weight(it, prior) for it in items), Decimal(0))


def order_key(items: Iterable[Item], prior=0) -> tuple:
    """§8's total order, as a key that sorts the best set first: higher
    score, fewer legs, then the smaller sorted tuple of item keys."""
    items = list(items)
    score = objective(items, prior)
    return (-score, sum(it.legs for it in items), tuple(sorted(it.key for it in items)))


# --------------------------------------------------------------------------- #
# Packing
# --------------------------------------------------------------------------- #

def _fits(item: Item, remaining: dict) -> bool:
    return all(remaining.get(oid, Fraction(0)) >= t for oid, t in item.takes.items())


def _take(item: Item, remaining: dict) -> dict:
    out = dict(remaining)
    for oid, t in item.takes.items():
        out[oid] = out[oid] - t
    return out


def greedy(items: list, capacity: dict, prior=0) -> list:
    """The deterministic greedy: by weight (then key), each taken if it
    still fits. What the baseline's disjoint extraction becomes with
    capacities; the fallback above the exact threshold, and the reserve
    bid's floor (§3)."""
    remaining = dict(capacity)
    chosen = []
    for it in sorted(items, key=lambda it: (-weight(it, prior), it.key)):
        if _fits(it, remaining):
            chosen.append(it)
            remaining = _take(it, remaining)
    return sorted(chosen, key=lambda it: it.key)


def pack(items: Iterable[Item], capacity: dict, *, prior=0, exact_up_to: int = EXACT_UP_TO,
         budget: int = BUDGET) -> Packing:
    """The feasible set of `items` worth most under `capacity` (offer id ->
    quantity available; an offer absent from it has none). Exact by branch
    and bound while there are at most `exact_up_to` items and within
    `budget` search nodes; the deterministic greedy otherwise. Items that
    cannot clear alone are set aside with the reason."""
    prior = q(prior)
    ordered = sorted(items, key=lambda it: it.key)
    feasible, infeasible = [], {}
    for it in ordered:
        short = [oid for oid, t in it.takes.items() if capacity.get(oid, Fraction(0)) < t]
        if short:
            infeasible[it.key] = f"takes more of offer {short[0][:12]} than is left"
        else:
            feasible.append(it)
    fallback = greedy(feasible, capacity, prior)
    if len(feasible) > exact_up_to:
        return Packing(fallback, False, infeasible)
    # branch and bound, depth-first in the total order; the bound is the
    # score with every remaining item added (each weight is positive)
    if prior == 0:
        suffix = [Fraction(1)] * (len(feasible) + 1)
        for i in range(len(feasible) - 1, -1, -1):
            suffix[i] = suffix[i + 1] * (1 + feasible[i].gain)
    else:
        with localcontext() as ctx:
            ctx.prec = PRECISION
            suffix = [Decimal(0)] * (len(feasible) + 1)
            for i in range(len(feasible) - 1, -1, -1):
                suffix[i] = suffix[i + 1] + weight(feasible[i], prior)
    best = [fallback, order_key(fallback, prior)]
    nodes = [0]
    exhausted = [False]

    def bound(score, i):
        return score * suffix[i] if prior == 0 else score + suffix[i]

    def dfs(i: int, chosen: list, remaining: dict, score):
        nodes[0] += 1
        if nodes[0] > budget:
            exhausted[0] = True
            return
        if i == len(feasible):
            key = order_key(chosen, prior)
            if key < best[1]:
                best[0], best[1] = list(chosen), key
            return
        if -bound(score, i) > best[1][0]:          # cannot beat the best even taking everything
            return
        it = feasible[i]
        if _fits(it, remaining):
            dfs(i + 1, chosen + [it], _take(it, remaining),
                score * (1 + it.gain) if prior == 0 else score + weight(it, prior))
            if exhausted[0]:
                return
        dfs(i + 1, chosen, remaining, score)

    dfs(0, [], dict(capacity), Fraction(1) if prior == 0 else Decimal(0))
    if exhausted[0]:
        return Packing(fallback, False, infeasible)
    return Packing(sorted(best[0], key=lambda it: it.key), True, infeasible)
