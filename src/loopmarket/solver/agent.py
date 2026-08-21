"""A baseline solver agent — the first species in the ecology.

The cycle of one `step()`:

    1. snapshot the book        (one root reference — free, isolated)
    2. load active offers       (skip filled, skip expired)
    3. generate matches         (exact pairwise check; see matching.py)
    4. build the exchange graph (best rate per giver->receiver pair)
    5. hunt profitable loops    (Bellman-Ford negative cycles)
    6. propose to settlement    (which re-verifies everything)

The agent is deliberately trust-poor in both directions: it works only
against a pinned book root and pinned ontology root (so its search is
reproducible and auditable), and nothing it computes is believed by
settlement — proposals are re-derived there from the current book.

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

import logging
import time as _time
from dataclasses import dataclass, field

from ..graph import ExchangeGraph, Loop
from ..matching import candidate_matches
from ..ontology import Ontology
from ..registry import OfferRegistry
from ..settlement import LoopProposal, Receipt, Settlement

log = logging.getLogger("loopmarket.solver")


@dataclass
class SolverAgent:
    registry: OfferRegistry
    ontology: Ontology
    settlement: Settlement
    solver_id: str = "solver-0"
    min_surplus: float = 0.005       # don't bother below half a percent
    max_loops_per_step: int = 10
    receipts: list[Receipt] = field(default_factory=list)

    def find_loops(self, *, now: int | None = None) -> tuple[str, list[Loop]]:
        """Steps 1-5: returns (book_root, profitable disjoint loops)."""
        now = int(_time.time()) if now is None else now
        root, book = self.registry.snapshot()
        offers = list(book.offers(now=now))
        matches = list(candidate_matches(offers, self.ontology, now=now))
        graph = ExchangeGraph.from_matches(matches)
        loops = graph.find_profitable_loops(
            min_surplus=self.min_surplus, limit=self.max_loops_per_step
        )
        log.info(
            "root=%s offers=%d matches=%d loops=%d",
            root[:12] if root else "-", len(offers), len(matches), len(loops),
        )
        return root, loops

    def step(self, *, now: int | None = None) -> list[Receipt]:
        """One full solve-and-propose pass; returns settlement receipts."""
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
            receipt = self.settlement.submit(proposal)
            log.info(
                "loop %s surplus=%.2f%% -> %s%s",
                loop.loop_id[:12], 100 * loop.surplus,
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
