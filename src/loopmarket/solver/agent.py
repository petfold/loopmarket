"""A baseline solver agent — the first species in the ecology.

The cycle of one `step()`:

    1. snapshot the book        (one root reference — free, isolated)
    2. load active offers       (skip filled, skip expired)
    3. generate matches         (candidates from ontodag's index, one
                                 per pass; the exact check on each)
    4. build the exchange graph (best rate per giver->receiver pair)
    5. hunt profitable loops    (Bellman-Ford negative cycles)
    6. propose to clearing    (which re-verifies everything)

The agent is deliberately trust-poor in both directions: it works only
against a pinned book root and pinned ontology root (so its search is
reproducible and auditable), and nothing it computes is believed by
clearing — proposals are re-derived there from the current book.

This is a *baseline*: exact and deterministic, its matches and legs found
through one `dimensions.DimensionIndex` per pass (a want's candidates are
the gives inside its cones, each checked exactly; review item 2), its
loops by bounded cycle search (`find_loops`). Competing agents are
expected to beat it with motif libraries, planners over ontodag's cones,
learned candidate generators — anything, as long as the loops they emit
survive re-verification. The interface to beat is `step()`.

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
from ..dimensions import DimensionIndex
from ..gate import CounterpartyGate
from ..matching import Leg, aggregate_legs, candidate_matches, composed_legs, independence_faults, parts_legs
from ..schema import q
from ..selection import item_of, pack, weight
from ..ontology import Ontology
from ..reads import NO_READS, Reads, authorities
from ..registry import OfferRegistry, taken_on_chain
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
    #: The older spelling of `reads.chain_fills` and `reads.escrow_held`
    #: (below), still accepted and kept equal to them.
    chain_fills: object = None
    escrow_held: object = None
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
    #: The counterparty gate's reads (R4, 2026-09-29): register id ->
    #: `Register` at the root this solver pins, and a reader of a `time(...)`
    #: term's span for the handover window. Statements come from the
    #: snapshot's `cred/` records; every register given is pinned in the
    #: proposals' `register_roots`, the clearing re-reading them there (U3).
    registers: dict = field(default_factory=dict)
    span: object = None
    #: R5's reader of each register's newest root, and a resolver's chain
    #: record (§7a) — the same reads the clearing's gate is given
    register_latest: object = None
    resolver_profile: object = None
    #: What the hunt reads beyond the snapshot (`reads.Reads`): the chain's
    #: fills (offer id -> quantity `BeatClearing.filled` has recorded as
    #: taken: a spent offer is not hunted through) and the escrow's holdings
    #: (offer id -> what it holds behind the offer, in the asset's unit: a
    #: deposit naming an escrow counts only up to what is held). Each pass
    #: derives `available`, `held` and the gate from them and its snapshot.
    reads: Reads = NO_READS

    def __post_init__(self) -> None:
        self.reads = authorities(self.reads, chain_fills=self.chain_fills,
                                 escrow_held=self.escrow_held, taker="a solver")
        self.chain_fills, self.escrow_held = self.reads.chain_fills, self.reads.escrow_held

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
        chain_fills, escrow_held = self.reads.chain_fills, self.reads.escrow_held
        root, book = self.registry.snapshot()
        offers = list(book.offers(now=now))
        available = book.availability(offers, now)  # partial fills leave remainders, holds keep theirs
        if chain_fills is not None:                # and the chain's fills are the authority
            kept = []
            for o in offers:
                on_chain = taken_on_chain(o, chain_fills)   # a want filled whole
                if o.composed:
                    if on_chain > 0:
                        continue
                else:
                    available[o.offer_id] = min(available[o.offer_id],
                                                q(o.thing.qty) - on_chain - book.held(o.offer_id, now))
                    if o.thing.exhausted(available[o.offer_id] + book.exercisable(o.offer_id, now)):
                        continue                   # spent; a held offer stays for its holder
                kept.append(o)
            offers = kept
        held = None
        if escrow_held is not None:
            held = {o.offer_id: q(escrow_held(o.offer_id)) for o in offers
                    if o.v >= 5 and o.bond is not None and o.bond.escrow}
        gate = self.gate(book, now=now, held=held)
        reads = self.reads.replace(available=available, held=held, gate=gate)
        # one index for the pass: every search below asks it for the gives
        # inside a want's cones instead of trying every give (review item 2)
        index = DimensionIndex(self.ontology)
        matches = list(candidate_matches(offers, self.ontology, now=now, reads=reads, index=index))
        cycles, complete = enumerate_cycles(matches, max_legs=self.max_legs,
                                            limit=self.cycle_limit, min_surplus=self.min_surplus)
        candidates: dict[str, Loop | Circulation] = {c.loop_id: c for c in cycles}
        if not complete:
            # the enumeration was cut: what Bellman-Ford certifies is added
            graph = ExchangeGraph.from_matches(matches)
            for loop in graph.find_profitable_loops(min_surplus=self.min_surplus,
                                                    limit=self.max_loops_per_step):
                candidates.setdefault(loop.loop_id, loop)
        composed = list(composed_legs(offers, self.ontology, now=now, reads=reads, index=index)) \
            + list(parts_legs(offers, self.ontology, now=now, reads=reads, index=index)) \
            + list(aggregate_legs(offers, self.ontology, now=now, reads=reads, index=index))
        if composed:
            legs = composed + [Leg.from_match(m) for m in matches]
            for circ in find_circulations(legs, min_surplus=self.min_surplus,
                                          limit=self.max_loops_per_step):
                if not independence_faults(circ.legs, self.ontology):     # E2: clearing refuses it
                    candidates.setdefault(circ.loop_id, circ)
        # a held offer's capacity includes what its holders may exercise now:
        # only a holder's leg reaches that part (the gate adds its own hold),
        # and clearing re-verifies every loop against the book it commits to
        capacity = {o.offer_id: (Fraction(1) if o.composed
                                 else available[o.offer_id] + book.exercisable(o.offer_id, now))
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

    def gate(self, book, *, now: int, held=None) -> CounterpartyGate:
        """The counterparty gate over the snapshot: its presented statements,
        this solver's registers, the clock."""
        return CounterpartyGate.over(book, self.registers, now=now, span=self.span, held=held,
                                     latest=self.register_latest, profile=self.resolver_profile)

    @property
    def register_roots(self) -> tuple:
        return tuple(sorted((rid, reg.root) for rid, reg in self.registers.items() if reg.root))

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
                register_roots=self.register_roots,
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
