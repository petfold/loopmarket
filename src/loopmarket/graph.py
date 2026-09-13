"""The exchange graph and the hunt for profitable loops.

Nodes are personal tokens (equivalently: makers). Every `Match` is a
directed edge giver -> receiver carrying an exchange rate r = B/A (the
wanting side's quoted price over the giving side's quoted price). A loop
p1 -> p2 -> ... -> pk -> p1 is *profitable* iff the product of rates around
it exceeds 1: with divisible quantities the slack is real surplus that
clearing prices can distribute (see ARCHITECTURE.md, "The arithmetic of
loops").

Take weights w = -log(r) and "product > 1" becomes "sum < 0": profitable
loops are negative cycles, found by Bellman-Ford in O(V*E) — the seventy-
year-old workhorse, chosen here for exactness and auditability. Solver
agents are free to bring anything smarter (this module is the baseline
species, not the ceiling); clearing only ever re-verifies the loop, never
the search.

Indivisible legs: the product condition assumes quantities can scale so
per-node token balances cancel exactly. When any leg is indivisible, a
conservative extra check is offered — per-node surplus (each node's want
unit price >= its give unit price), under which exact cancellation with
qty=1 legs is feasible. `Loop.per_node_ok` reports it; the solver decides
policy.

Circulations (2026-09-13, `docs/plans/P2-loop-selection.md` §10/§11): the
cleared object is a set of legs, some of them composed — one want met by
the give of a thing plus the operator gives that move it (the box at the
shop plus the courier's run). Every maker in the set gives once and wants
once; conservation is of value on each maker's own scale. Feasibility is
the existence of node potentials e > 0 with, for every leg, the buyer's
price times its potential covering the sum of the givers' prices times
theirs — the dual of §11, and for a simple cycle exactly "product of rates
> 1". `Circulation.potentials` finds the least such potentials by the
Bellman–Ford-shaped fixpoint on the hypergraph (Knuth's superior functions:
each head's potential is raised to what its tails demand, n rounds, and a
set that keeps growing has no potentials). `find_circulations` is the
baseline hunt: a deterministic depth-first search for a connected set of
legs in which every maker is head of one leg and tail of one.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Iterable

from .matching import Leg, Match


@dataclass(frozen=True, slots=True)
class Loop:
    """An ordered cycle of matches: matches[i].receiver == matches[i+1].giver."""

    matches: tuple[Match, ...]

    def __post_init__(self) -> None:
        k = len(self.matches)
        if k < 2:
            raise ValueError("a loop needs at least two legs")
        for i, m in enumerate(self.matches):
            if m.receiver != self.matches[(i + 1) % k].giver:
                raise ValueError("matches do not chain into a cycle")

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(m.giver for m in self.matches)

    @property
    def product(self) -> float:
        p = 1.0
        for m in self.matches:
            p *= m.rate
        return p

    @property
    def surplus(self) -> float:
        """Fractional surplus around the loop (0.04 == 4%)."""
        return self.product - 1.0

    @property
    def per_node_ok(self) -> bool:
        """Each node's incoming want unit price >= its outgoing give unit price."""
        k = len(self.matches)
        for i, incoming in enumerate(self.matches):
            outgoing = self.matches[(i + 1) % k]
            if incoming.want.unit_price < outgoing.give.unit_price - 1e-12:
                return False
        return True

    @property
    def all_divisible(self) -> bool:
        return all(m.give.thing.divisible and m.want.thing.divisible
                   for m in self.matches)

    @property
    def offer_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for m in self.matches:
            ids.extend((m.give.offer_id, m.want.offer_id))
        return tuple(ids)

    @property
    def loop_id(self) -> str:
        """Content address of the clearing decision: the cycle of legs.

        Hashes the leg sequence (give>want pairs, cycle order) under its
        lexicographically minimal rotation — invariant to where the search
        entered the cycle, sensitive to how the offers are paired. Hashing
        the sorted offer *set* (the pre-2026-08-20 encoding) would collide
        two different pairings of the same offers onto one `loop/` key,
        silently conflating distinct clearings (ARCHITECTURE.md §2).
        """
        legs = [f"{m.give.offer_id}>{m.want.offer_id}" for m in self.matches]
        start = min(range(len(legs)), key=lambda i: legs[i:] + legs[:i])
        return hashlib.sha256(
            "|".join(legs[start:] + legs[:start]).encode()
        ).hexdigest()


@dataclass
class ExchangeGraph:
    """Best-rate multigraph reduction: one surviving edge per (giver, receiver)."""

    edges: dict[tuple[str, str], Match] = field(default_factory=dict)

    @classmethod
    def from_matches(cls, matches: Iterable[Match]) -> "ExchangeGraph":
        g = cls()
        for m in matches:
            key = (m.giver, m.receiver)
            if key not in g.edges or m.rate > g.edges[key].rate:
                g.edges[key] = m
        return g

    @property
    def nodes(self) -> list[str]:
        ns = {u for u, _ in self.edges} | {v for _, v in self.edges}
        return sorted(ns)

    # -- negative-cycle detection ------------------------------------------------

    def find_profitable_loop(self, *, min_surplus: float = 0.0) -> Loop | None:
        """Bellman-Ford over w = -log(rate); returns one profitable Loop or None.

        Deterministic: nodes and edges are iterated in sorted order, so the
        same book yields the same loop on every replica — clearing and
        audit can reproduce the search exactly.
        """
        nodes = self.nodes
        if not nodes:
            return None
        # min_surplus folds into the weights: demand product > 1 + min_surplus
        # by taxing every edge with the k-th root is order-dependent; instead
        # tax uniformly per edge using the loop-length-free trick of testing
        # the final product after extraction.
        dist = {n: 0.0 for n in nodes}          # virtual source at 0 to all
        pred: dict[str, tuple[str, Match] | None] = {n: None for n in nodes}
        edge_list = sorted(self.edges.items())  # deterministic relaxation order

        cycle_entry: str | None = None
        for i in range(len(nodes)):
            changed = False
            for (u, v), m in edge_list:
                w = -math.log(m.rate)
                if dist[u] + w < dist[v] - 1e-15:
                    dist[v] = dist[u] + w
                    pred[v] = (u, m)
                    changed = True
                    if i == len(nodes) - 1:
                        cycle_entry = v
            if not changed:
                return None
        if cycle_entry is None:
            return None

        # Walk predecessors n times to guarantee we are inside the cycle.
        x = cycle_entry
        for _ in range(len(nodes)):
            x = pred[x][0]  # type: ignore[index]

        # Collect the cycle's matches.
        cycle: list[Match] = []
        v = x
        while True:
            u, m = pred[v]  # type: ignore[misc]
            cycle.append(m)
            v = u
            if v == x:
                break
        cycle.reverse()
        loop = Loop(tuple(cycle))
        if loop.surplus < min_surplus - 1e-12:
            return None
        return loop

    def find_profitable_loops(self, *, min_surplus: float = 0.0,
                              limit: int = 10) -> list[Loop]:
        """Greedily extract disjoint profitable loops (offers used once)."""
        loops: list[Loop] = []
        g = ExchangeGraph(dict(self.edges))
        used: set[str] = set()
        while len(loops) < limit:
            loop = g.find_profitable_loop(min_surplus=min_surplus)
            if loop is None:
                return loops
            loops.append(loop)
            used.update(loop.offer_ids)
            g = ExchangeGraph({
                k: m for k, m in g.edges.items()
                if m.give.offer_id not in used and m.want.offer_id not in used
            })
        return loops


# --------------------------------------------------------------------------- #
# Circulations: legs, some composed, balanced at every maker
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class Circulation:
    """A set of legs in which every maker both gives and receives.

    Each offer is used once; a maker may take part through several offers
    (the buyer who pays for the box and its delivery with two lessons). A
    simple cycle is the case where every leg has one give and every maker
    one offer each way; `from_loop` lifts a `Loop`, and `loop_id`/`surplus`
    agree with it there, so a circulation of simple legs clears under the
    same id and arithmetic the P0 solver always produced.
    """

    legs: tuple[Leg, ...]

    def __post_init__(self) -> None:
        if len(self.legs) < 2:
            raise ValueError("a circulation needs at least two legs")
        ids = [oid for leg in self.legs for oid in leg.offer_ids]
        if len(set(ids)) != len(ids):
            raise ValueError("an offer is used once in a circulation")
        heads = {leg.head for leg in self.legs}
        tails = {m for leg in self.legs for m in leg.tails}
        if heads != tails:
            raise ValueError("legs do not balance: some maker gives without "
                             "receiving, or receives without giving")

    @classmethod
    def from_loop(cls, loop: Loop) -> "Circulation":
        return cls(tuple(Leg.from_match(m) for m in loop.matches))

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(sorted(leg.head for leg in self.legs))

    @property
    def offer_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for leg in self.legs:
            ids.extend(leg.offer_ids)
        return tuple(ids)

    @property
    def simple(self) -> bool:
        return all(leg.simple for leg in self.legs)

    def as_loop(self) -> Loop | None:
        """The `Loop` this is, when every leg is simple, every maker takes
        part once each way, and the legs chain."""
        if not self.simple:
            return None
        if len({leg.gives[0].maker for leg in self.legs}) != len(self.legs) \
                or len({leg.head for leg in self.legs}) != len(self.legs):
            return None
        by_giver = {leg.gives[0].maker: leg for leg in self.legs}
        order = [self.legs[0]]
        while len(order) < len(self.legs):
            nxt = by_giver.get(order[-1].head)
            if nxt is None or nxt in order:
                return None
            order.append(nxt)
        if order[-1].head != order[0].gives[0].maker:
            return None
        return Loop(tuple(Match(give=leg.gives[0], want=leg.want) for leg in order))

    def potentials(self, gain: float = 1.0) -> dict[str, float] | None:
        """The least node potentials e >= 1 with, for every leg,
        want.price * e[buyer] >= gain * sum(give.price * e[giver]); None
        when no potentials exist (the set cannot clear at that gain).
        Legs are visited in sorted order (U6)."""
        legs = sorted(self.legs, key=lambda leg: leg.key)
        e = {m: 1.0 for m in self.nodes}
        for _ in range(len(e) + 1):
            changed = False
            for leg in legs:
                need = gain * sum(g.unit_price * e[g.maker] for g in leg.gives) \
                    / leg.want.unit_price
                if need > e[leg.head] * (1 + 1e-12):
                    e[leg.head] = need
                    changed = True
            if not changed:
                return e
        return None

    @property
    def feasible(self) -> bool:
        return self.potentials() is not None

    @property
    def surplus(self) -> float:
        """The uniform per-leg gain the set can bear, compounded over its
        legs: (1 + t)^k - 1 for the largest t with potentials — which for a
        simple cycle is exactly the product of rates minus one, the P0
        figure. Negative (below -1e-9) when infeasible."""
        loop = self.as_loop()
        if loop is not None:
            return loop.surplus
        if self.potentials() is None:
            return -1.0
        lo, hi = 0.0, 1.0
        while self.potentials(1.0 + hi) is not None and hi < 1e6:
            hi *= 2
        for _ in range(60):
            mid = (lo + hi) / 2
            if self.potentials(1.0 + mid) is not None:
                lo = mid
            else:
                hi = mid
        return (1.0 + lo) ** len(self.legs) - 1.0

    @property
    def per_node_ok(self) -> bool:
        """Each maker's wants, priced on its own scale, cover its gives —
        `Loop.per_node_ok` over any shape (one want and one give each in a
        simple cycle)."""
        wants: dict[str, float] = {}
        gives: dict[str, float] = {}
        for leg in self.legs:
            wants[leg.head] = wants.get(leg.head, 0.0) + leg.want.unit_price
            for g in leg.gives:
                gives[g.maker] = gives.get(g.maker, 0.0) + g.unit_price
        return all(wants.get(m, 0.0) >= gives[m] - 1e-12 for m in gives)

    @property
    def all_divisible(self) -> bool:
        return all(leg.want.thing.divisible and all(g.thing.divisible for g in leg.gives)
                   for leg in self.legs)

    @property
    def loop_id(self) -> str:
        """Content address of the clearing decision. A simple cycle keeps
        `Loop.loop_id` (rotation-invariant, pairing-sensitive); a composed
        set hashes its legs — give ids joined by `+`, `>` the want — in
        sorted order, which is invariant to the search order and sensitive
        to how offers are grouped into legs."""
        loop = self.as_loop()
        if loop is not None:
            return loop.loop_id
        return hashlib.sha256(
            "|".join(sorted(leg.key for leg in self.legs)).encode()).hexdigest()


def find_circulations(legs: Iterable[Leg], *, min_surplus: float = 0.0,
                      limit: int = 10, max_legs: int = 6,
                      budget: int = 50_000) -> list[Circulation]:
    """The baseline hunt for circulations among `legs` (simple and
    composed): depth-first from each leg in sorted order, always extending
    at the smallest unbalanced maker — one that has given and not received
    takes a leg it heads, one that has received and not given takes a leg
    it tails — so the set stays connected and every maker gives once and
    wants once. The first balanced set with surplus >= `min_surplus` is
    taken, its offers retired, and the search repeats up to `limit`
    times. Exponential in the worst case and bounded by `max_legs` and a
    node `budget`; deterministic throughout (U6). Simple cycles are found
    first by Bellman-Ford in the agent; this is the hunt for what has a
    composed leg in it. The recall benchmark for composing species, not
    the ceiling."""
    legs = sorted(legs, key=lambda leg: leg.key)
    found: list[Circulation] = []
    used: set[str] = set()
    while len(found) < limit:
        pool = [leg for leg in legs if not (set(leg.offer_ids) & used)]
        circ = _search(pool, min_surplus, max_legs, [budget])
        if circ is None:
            break
        found.append(circ)
        used.update(circ.offer_ids)
    return found


def _search(pool: list[Leg], min_surplus: float, max_legs: int,
            budget: list[int]) -> Circulation | None:
    by_head: dict[str, list[Leg]] = {}
    by_tail: dict[str, list[Leg]] = {}
    for leg in pool:
        by_head.setdefault(leg.head, []).append(leg)
        for m in leg.tails:
            by_tail.setdefault(m, []).append(leg)

    def compatible(leg: Leg, offers: set[str]) -> bool:
        # each offer once; a maker may return through another offer
        return leg.head not in leg.tails and not (set(leg.offer_ids) & offers)

    def dfs(chosen: list[Leg], heads: set[str], tails: set[str],
            offers: set[str]) -> Circulation | None:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        if heads == tails:
            circ = Circulation(tuple(chosen))
            return circ if circ.surplus >= min_surplus - 1e-12 else None
        if len(chosen) >= max_legs:
            return None
        gave_not_received = sorted(tails - heads)
        if gave_not_received:
            candidates = by_head.get(gave_not_received[0], [])
        else:
            candidates = by_tail.get(sorted(heads - tails)[0], [])
        for leg in candidates:
            if not compatible(leg, offers):
                continue
            found = dfs(chosen + [leg], heads | {leg.head}, tails | set(leg.tails),
                        offers | set(leg.offer_ids))
            if found is not None:
                return found
        return None

    for start in pool:
        if start.head in start.tails:
            continue
        found = dfs([start], {start.head}, set(start.tails), set(start.offer_ids))
        if found is not None:
            return found
    return None
