"""Settlement: where a proposed loop becomes a bundle of commitments.

Trust model (the one non-negotiable): settlement *never trusts the solver*.
A `LoopProposal` names the book root and ontology root it was solved
against; the settlement layer re-derives every leg with `check_match`, the
chaining, the product, and the not-already-filled status — cheap, linear in
the loop — before atomically marking every offer filled. Discovery is
expensive and competitive; verification is cheap and neutral.

`MockSettlement` is the in-process stand-in: its "atomic stroke" is one
recordstore commit (all fills + the loop record land under a single new
root, or none do). The on-chain path it stands in for (roadmap P2) keeps
the same interface: a contract receives the loop plus *inclusion proofs*
that each offer is present under the pinned book root — which is exactly
what the Proximity Order Trie's ForkPathProof + on-chain POTProofVerifier
provide once the book's index lives in a POT. Batch auctions across
competing proposals (rank by participant surplus, rebate it) are P2 as
well; the mock is first-valid-wins.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from typing import Protocol

from .graph import Loop
from .matching import check_match
from .ontology import Ontology
from .registry import OfferRegistry


@dataclass(frozen=True, slots=True)
class LoopProposal:
    loop: Loop
    book_root: str        # the registry version the loop was solved against
    ontology_root: str    # the catalogue version subsumption was checked under
    solver: str           # who found it (fee/reputation address)
    found_at: int

    def to_record(self) -> dict:
        return {
            "loop_id": self.loop.loop_id,
            "solver": self.solver,
            "found_at": self.found_at,
            "book_root": self.book_root,
            "ontology_root": self.ontology_root,
            "surplus": self.loop.surplus,
            "nodes": list(self.loop.nodes),
            "legs": [
                {"ask": m.ask.offer_id, "bid": m.bid.offer_id, "rate": m.rate}
                for m in self.loop.matches
            ],
        }


@dataclass(frozen=True, slots=True)
class Receipt:
    accepted: bool
    loop_id: str
    reason: str = ""
    book_root: str = ""   # the new root, if accepted


class Settlement(Protocol):
    def submit(self, proposal: LoopProposal) -> Receipt: ...


class MockSettlement:
    """In-process settlement over the shared registry."""

    def __init__(self, registry: OfferRegistry, ontology: Ontology, *,
                 min_surplus: float = 0.0, require_per_node: bool = True,
                 clock=_time.time):
        self.registry = registry
        self.ontology = ontology
        self.min_surplus = min_surplus
        self.require_per_node = require_per_node
        self.clock = clock  # injectable for tests / deterministic replay

    def submit(self, proposal: LoopProposal) -> Receipt:
        loop = proposal.loop
        lid = loop.loop_id
        now = int(self.clock())

        def reject(reason: str) -> Receipt:
            return Receipt(False, lid, reason)

        # 0. pins — the rehearsal of U10's settlement half (full enforcement,
        #    with proofs and refusal on absence, lands with P2): a proposal
        #    solved under a different catalogue than the one this settlement
        #    verifies under is refused before any leg work.
        if proposal.ontology_root and self.ontology.root and \
                proposal.ontology_root != self.ontology.root:
            return reject("ontology pin mismatch")

        # 1. every offer must exist in the *current* book and be unfilled
        seen: set[str] = set()
        for oid in loop.offer_ids:
            if oid in seen:
                return reject(f"offer used twice: {oid[:12]}")
            seen.add(oid)
            try:
                self.registry.get(oid)
            except KeyError:
                return reject(f"unknown offer: {oid[:12]}")
            if self.registry.is_filled(oid):
                return reject(f"already filled: {oid[:12]}")

        # 2. re-derive every leg — never trust the solver's matches
        for m in loop.matches:
            fresh_ask = self.registry.get(m.ask.offer_id)
            fresh_bid = self.registry.get(m.bid.offer_id)
            if check_match(fresh_ask, fresh_bid, self.ontology, now=now) is None:
                return reject(
                    f"leg fails re-verification: {m.ask.offer_id[:8]}"
                    f" -> {m.bid.offer_id[:8]}"
                )

        # 3. the arithmetic
        if loop.surplus < self.min_surplus - 1e-12:
            return reject(f"surplus {loop.surplus:.4f} below minimum")
        if self.require_per_node and not loop.all_divisible \
                and not loop.per_node_ok:
            return reject("indivisible legs without per-node surplus")

        # 4. atomic commitment: all fills land under one new root, or none
        self.registry.mark_filled(loop.offer_ids, lid, proposal.to_record())
        root = self.registry.commit()
        return Receipt(True, lid, book_root=root)
