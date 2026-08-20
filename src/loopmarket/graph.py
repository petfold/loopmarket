"""The exchange graph and the hunt for profitable loops.

Nodes are personal tokens (equivalently: makers). Every `Match` is a
directed edge giver -> receiver carrying an exchange rate r = B/A (the
receiver's bid unit price over the giver's ask unit price). A loop
p1 -> p2 -> ... -> pk -> p1 is *profitable* iff the product of rates around
it exceeds 1: with divisible quantities the slack is real surplus that
settlement prices can distribute (see ARCHITECTURE.md, "The arithmetic of
loops").

Take weights w = -log(r) and "product > 1" becomes "sum < 0": profitable
loops are negative cycles, found by Bellman-Ford in O(V*E) — the seventy-
year-old workhorse, chosen here for exactness and auditability. Solver
agents are free to bring anything smarter (this module is the baseline
species, not the ceiling); settlement only ever re-verifies the loop, never
the search.

Indivisible legs: the product condition assumes quantities can scale so
per-node token balances cancel exactly. When any leg is indivisible, a
conservative extra check is offered — per-node surplus (each node's bid
unit price >= its ask unit price), under which exact cancellation with
qty=1 legs is feasible. `Loop.per_node_ok` reports it; the solver decides
policy.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Iterable

from .matching import Match


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
        """Each node's incoming bid unit price >= its outgoing ask unit price."""
        k = len(self.matches)
        for i, incoming in enumerate(self.matches):
            outgoing = self.matches[(i + 1) % k]
            if incoming.bid.unit_price < outgoing.ask.unit_price - 1e-12:
                return False
        return True

    @property
    def all_divisible(self) -> bool:
        return all(m.ask.thing.divisible and m.bid.thing.divisible
                   for m in self.matches)

    @property
    def offer_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for m in self.matches:
            ids.extend((m.ask.offer_id, m.bid.offer_id))
        return tuple(ids)

    @property
    def loop_id(self) -> str:
        """Content address of the settlement decision: the cycle of legs.

        Hashes the leg sequence (ask>bid pairs, cycle order) under its
        lexicographically minimal rotation — invariant to where the search
        entered the cycle, sensitive to how the offers are paired. Hashing
        the sorted offer *set* (the pre-2026-08-20 encoding) would collide
        two different pairings of the same offers onto one `loop/` key,
        silently conflating distinct settlements (ARCHITECTURE.md §2).
        """
        legs = [f"{m.ask.offer_id}>{m.bid.offer_id}" for m in self.matches]
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
        same book yields the same loop on every replica — settlement and
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
                if m.ask.offer_id not in used and m.bid.offer_id not in used
            })
        return loops
