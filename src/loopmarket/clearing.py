"""Clearing: where a proposed loop becomes a bundle of commitments.

Trust model (the one non-negotiable): clearing *never trusts the solver*.
A `LoopProposal` names the book root and ontology root it was solved
against; the clearing layer re-derives every leg with `check_match`, the
chaining, the product, and the not-already-filled status — cheap, linear in
the loop — before atomically marking every offer filled. Discovery is
expensive and competitive; verification is cheap and neutral.

`MockClearing` is the in-process stand-in: its "atomic stroke" is one
recordstore commit (all fills + the loop record land under a single new
root, or none do). The on-chain path it stands in for (roadmap P2) keeps
the same interface: a contract receives the loop plus *inclusion proofs*
that each offer is present under the pinned book root — recordstore's
canonical-trie `prove`/`verify_proof` (>= 0.16.0) is the primary route;
POT ForkPathProof is the conditional fallback only if the on-chain
verifier demands BMT-native proofs (docs/plans/proof-fabric.md). Batch
auctions across competing sealed proposals are P2 as well
(docs/plans/P2-batch-auction.md); the mock is first-valid-wins.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from typing import Protocol

from .graph import Circulation, Loop
from .matching import check_composition, check_match
from .ontology import Ontology
from .registry import OfferRegistry


@dataclass(frozen=True, slots=True)
class LoopProposal:
    loop: Loop | Circulation
    book_root: str        # the registry version the loop was solved against
    ontology_root: str    # the catalogue version subsumption was checked under
    solver: str           # who found it (fee/reputation address)
    found_at: int

    @property
    def circulation(self) -> Circulation:
        return self.loop if isinstance(self.loop, Circulation) \
            else Circulation.from_loop(self.loop)

    def to_record(self) -> dict:
        """The `loop/` record. Every leg names its want and its gives —
        `give` is the first (the thing; the only one of a simple leg, kept
        for readers of the 2026-08 shape) and `gives` all of them, so a
        fill of a composed want names every give it consumed (§10). A
        simple leg carries its rate; a composed set carries the node
        potentials — the clearing prices as the dual of §11."""
        circ = self.circulation
        legs = []
        for leg in sorted(circ.legs, key=lambda leg: leg.key):
            rec = {"give": leg.gives[0].offer_id,
                   "gives": [g.offer_id for g in leg.gives],
                   "want": leg.want.offer_id}
            if leg.simple:
                rec["rate"] = leg.want.unit_price / leg.gives[0].unit_price
            legs.append(rec)
        record = {
            "loop_id": circ.loop_id,
            "solver": self.solver,
            "found_at": self.found_at,
            "book_root": self.book_root,
            "ontology_root": self.ontology_root,
            "surplus": circ.surplus,
            "nodes": list(circ.nodes),
            "legs": legs,
        }
        loop = circ.as_loop()
        if loop is not None:          # the P0 shape, byte for byte
            record["nodes"] = list(loop.nodes)
            record["legs"] = [
                {"give": m.give.offer_id, "want": m.want.offer_id, "rate": m.rate}
                for m in loop.matches]
        else:
            record["potentials"] = circ.potentials()
        return record


@dataclass(frozen=True, slots=True)
class Receipt:
    accepted: bool
    loop_id: str
    reason: str = ""
    book_root: str = ""   # the new root, if accepted


class Clearing(Protocol):
    def submit(self, proposal: LoopProposal) -> Receipt: ...


class MockClearing:
    """In-process clearing over the shared registry."""

    #: Oracle types this clearing knows how to verify — the P3 refusal
    #: gate (docs/plans/P3-guarantee-coupling.md, enforcement rule 1): a leg
    #: naming a witness type outside this set never clears here, in U7's
    #: shape — unknown fails closed rather than silently clearing with a
    #: guarantee nobody can check. The mock declares exactly the P0
    #: countersign semantics.
    VERIFIABLE_ORACLES = frozenset({"countersign"})

    def __init__(self, registry: OfferRegistry, ontology: Ontology, *,
                 min_surplus: float = 0.0, require_per_node: bool = True,
                 clock=_time.time, verifiable_oracles=VERIFIABLE_ORACLES):
        self.registry = registry
        self.ontology = ontology
        self.min_surplus = min_surplus
        self.require_per_node = require_per_node
        self.clock = clock  # injectable for tests / deterministic replay
        self.verifiable_oracles = frozenset(verifiable_oracles)

    def submit(self, proposal: LoopProposal) -> Receipt:
        loop = proposal.circulation
        lid = loop.loop_id
        now = int(self.clock())

        def reject(reason: str) -> Receipt:
            return Receipt(False, lid, reason)

        # 0. pins — the rehearsal of U10's clearing half (full enforcement,
        #    with proofs, lands with P2): the proposal's catalogue pin must
        #    *equal* this clearing's own, refused before any leg work.
        #    Plain equality covers mismatch and absence in both directions:
        #    a pinned clearing refuses unpinned proposals, an unpinned
        #    (development) one refuses proposals claiming ground it cannot
        #    confirm; '' == '' keeps the in-memory flow working.
        if proposal.ontology_root != self.ontology.root:
            return reject("ontology pin mismatch")

        # 1. every offer must exist in the *current* book, be unfilled, and
        #    name a witness type this clearing can actually verify
        seen: set[str] = set()
        for oid in loop.offer_ids:
            if oid in seen:
                return reject(f"offer used twice: {oid[:12]}")
            seen.add(oid)
            try:
                offer = self.registry.get(oid)
            except KeyError:
                return reject(f"unknown offer: {oid[:12]}")
            if self.registry.is_filled(oid):
                return reject(f"already filled: {oid[:12]}")
            if self.registry.is_withdrawn(oid):
                return reject(f"withdrawn: {oid[:12]}")
            if offer.oracle not in self.verifiable_oracles:
                return reject(f"unverifiable oracle type: {offer.oracle}")

        # 2. re-derive every leg — never trust the solver's matches; a
        #    composed leg is re-composed (`check_composition`) from the
        #    current book, operators included
        for leg in loop.legs:
            fresh_want = self.registry.get(leg.want.offer_id)
            fresh_gives = [self.registry.get(g.offer_id) for g in leg.gives]
            ok = check_match(fresh_gives[0], fresh_want, self.ontology, now=now) \
                if leg.simple else \
                check_composition(fresh_want, fresh_gives, self.ontology, now=now)
            if ok is None:
                return reject(
                    f"leg fails re-verification: "
                    f"{'+'.join(g.offer_id[:8] for g in leg.gives)}"
                    f" -> {leg.want.offer_id[:8]}"
                )

        # 3. the arithmetic: potentials exist (a simple cycle: product > 1)
        #    with the required uniform gain, and the indivisible gate
        if not loop.feasible:
            return reject("no node potentials: the legs do not balance")
        if loop.surplus < self.min_surplus - 1e-12:
            return reject(f"surplus {loop.surplus:.4f} below minimum")
        if self.require_per_node and not loop.all_divisible \
                and not loop.per_node_ok:
            return reject("indivisible legs without per-node surplus")

        # 4. atomic commitment: all fills land under one new root, or none
        self.registry.mark_filled(loop.offer_ids, lid, proposal.to_record())
        root = self.registry.commit()
        return Receipt(True, lid, book_root=root)
