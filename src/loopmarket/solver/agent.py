"""A baseline solver agent — the first species in the ecology.

The cycle of one `step()`:

    1. snapshot the book        (one root reference — free, isolated)
    2. load active offers       (skip filled, skip expired)
    3. generate matches         (exact pairwise check; see matching.py)
    4. build the exchange graph (best rate per giver->receiver pair)
    5. hunt profitable loops    (Bellman-Ford negative cycles)
    6. propose to clearing    (which re-verifies everything)

The agent is deliberately trust-poor in both directions: it works only
against a pinned book root and pinned ontology root (so its search is
reproducible and auditable), and nothing it computes is believed by
clearing — proposals are re-derived there from the current book.

This is a *baseline*: exact, deterministic, O(gives*wants) matching and
O(V*E) cycle search. Competing agents are expected to beat it with motif
libraries, planners over the idx/{c,t,g} prefixes, learned candidate
generators — anything, as long as the loops they emit survive
re-verification. The interface to beat is `step()`.

The boundary is deliberate (owner doctrine, 2026-08-21): loopmarket
provides the basic mechanisms and the means to express intentions;
the hard combinatorial optimization belongs to professional solvers
*outside* this software — statistical methods, planners, LLMs, whatever
wins — whose internals are not loopmarket's concern and may stay secret
for competitive edge. That is healthy: U3 means cleverness can be
trusted because it is never trusted. This baseline exists to demo the
pipeline and (P2) to floor the auction as its reserve bid.
"""

from __future__ import annotations

from fractions import Fraction

import logging
import time as _time
from dataclasses import dataclass, field

from ..graph import Circulation, ExchangeGraph, Loop, find_circulations, enumerate_cycles
from ..matching import Leg, aggregate_legs, candidate_matches, composed_legs, parts_legs
from ..schema import q
from ..selection import item_of, pack, weight
from ..ontology import Ontology
from ..registry import OfferRegistry
from ..clearing import LoopProposal, Receipt, Clearing

log = logging.getLogger("loopmarket.solver")


@dataclass
class SolverAgent:
    registry: OfferRegistry
    ontology: Ontology
    clearing: Clearing
    solver_id: str = "solver-0"
    min_surplus: float = 0.005       # don't bother below half a percent
    max_loops_per_step: int = 10
    receipts: list[Receipt] = field(default_factory=list)
    #: offer id -> quantity the chain has recorded as taken (`BeatClearing.
    #: filled`), or None: a spent offer is not hunted through (2026-09-18).
    chain_fills: object = None
    #: Selection (P2-loop-selection.md, 2026-09-18): every simple cycle up
    #: to `max_legs` legs is a candidate (`graph.enumerate_cycles`, at most
    #: `cycle_limit` of them), the composed sets beside them, and the packer
    #: chooses the set worth most under the offers' capacities — exactly up
    #: to `exact_up_to` candidates within `pack_budget` nodes, greedily
    #: beyond; `failure_prior` is §4's uninformative prior (0: log surplus).
    max_legs: int = 5
    cycle_limit: int = 2000
    exact_up_to: int = 24
    pack_budget: int = 200_000
    failure_prior: object = 0

    def find_loops(self, *, now: int | None = None
                   ) -> tuple[str, list[Loop | Circulation]]:
        """Steps 1-5: returns (book_root, the loops and circulations
        selected). Candidates first: every simple cycle over the match
        multigraph up to `max_legs` (`graph.enumerate_cycles` — recall
        complete up to its caps, the fix of `P2-loop-selection.md` §6;
        Bellman–Ford's extraction only tops it up when the enumeration was
        cut), and, when the catalogue declares operators and the book
        composes any leg, the circulation hunt (`graph.find_circulations`)
        over simple legs, operator-composed legs, the legs of composed
        wants (`parts_legs`, v4) and aggregated legs (`aggregate_legs`).
        Then selection (`selection.pack`): the set worth most under what is
        left of every offer — an indivisible offer or a want once, a
        divisible give shared up to its remainder — exactly while the
        candidates are few, greedily beyond, in §8's total order (U6)."""
        now = int(_time.time()) if now is None else now
        root, book = self.registry.snapshot()
        offers = list(book.offers(now=now))
        available = book.availability(offers)      # partial fills leave remainders
        if self.chain_fills is not None:           # and the chain's fills are the authority
            kept = []
            for o in offers:
                on_chain = q(self.chain_fills(o.offer_id))
                if o.composed:
                    if on_chain > 0:
                        continue
                else:
                    available[o.offer_id] = min(available[o.offer_id], q(o.thing.qty) - on_chain)
                    if o.thing.exhausted(available[o.offer_id]):
                        continue
                kept.append(o)
            offers = kept
        matches = list(candidate_matches(offers, self.ontology, now=now,
                                         available=available))
        cycles, complete = enumerate_cycles(matches, max_legs=self.max_legs,
                                            limit=self.cycle_limit, min_surplus=self.min_surplus)
        candidates: dict[str, Loop | Circulation] = {c.loop_id: c for c in cycles}
        if not complete:
            # the enumeration was cut: what Bellman-Ford certifies is added
            graph = ExchangeGraph.from_matches(matches)
            for loop in graph.find_profitable_loops(min_surplus=self.min_surplus,
                                                    limit=self.max_loops_per_step):
                candidates.setdefault(loop.loop_id, loop)
        composed = list(composed_legs(offers, self.ontology, now=now, available=available)) \
            + list(parts_legs(offers, self.ontology, now=now, available=available)) \
            + list(aggregate_legs(offers, self.ontology, now=now, available=available))
        if composed:
            legs = composed + [Leg.from_match(m) for m in matches]
            for circ in find_circulations(legs, min_surplus=self.min_surplus,
                                          limit=self.max_loops_per_step):
                candidates.setdefault(circ.loop_id, circ)
        capacity = {o.offer_id: (Fraction(1) if o.composed else available[o.offer_id])
                    for o in offers}
        packing = pack([item_of(c) for c in candidates.values()], capacity,
                       prior=self.failure_prior, exact_up_to=self.exact_up_to,
                       budget=self.pack_budget)
        chosen = sorted(packing.chosen, key=lambda it: (-weight(it, self.failure_prior), it.key))
        loops: list[Loop | Circulation] = [it.payload for it in chosen[: self.max_loops_per_step]]
        log.info(
            "root=%s offers=%d matches=%d cycles=%d%s composed=%d candidates=%d selected=%d%s",
            root[:12] if root else "-", len(offers), len(matches), len(cycles),
            "" if complete else "(cut)", len(composed), len(candidates), len(loops),
            "" if packing.exact else " (greedy)",
        )
        return root, loops

    def step(self, *, now: int | None = None) -> list[Receipt]:
        """One full solve-and-propose pass; returns clearing receipts."""
        found_at = int(_time.time()) if now is None else now
        root, loops = self.find_loops(now=now)
        receipts: list[Receipt] = []
        for loop in loops:
            proposal = LoopProposal(
                loop=loop,
                book_root=root or "",
                ontology_root=self.ontology.root,
                solver=self.solver_id,
                found_at=found_at,
            )
            receipt = self.clearing.submit(proposal)
            log.info(
                "loop %s surplus=%.2f%% -> %s%s",
                loop.loop_id[:12], 100 * float(loop.surplus),
                "ACCEPTED" if receipt.accepted else "rejected",
                "" if receipt.accepted else f" ({receipt.reason})",
            )
            receipts.append(receipt)
        self.receipts.extend(receipts)
        return receipts

    def run(self, *, interval_s: float = 5.0, max_steps: int | None = None) -> None:
        """Poll loop for long-running operation against a live book."""
        steps = 0
        while max_steps is None or steps < max_steps:
            self.step()
            steps += 1
            _time.sleep(interval_s)
