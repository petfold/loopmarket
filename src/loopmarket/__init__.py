"""loopmarket — a universal combinatorial marketplace over OntoDAG + recordstore + Swarm.

One uniform offer form; a shared OntoDAG catalogue in which meanings, minutes
and map regions are ordered by the same fits-within relation; a distributed,
versioned offer book over recordstore (Swarm-backed via BeeBytesStore +
SwarmFeedPointer); competing solver agents hunting profitable loops as
negative cycles; settlement that re-verifies everything and trusts no one.

Dependency direction (boundary B2, enforced by tests/test_boundaries.py):

    loopmarket  ->  ontodag  ->  recordstore  ->  (Swarm, optional)

The core imports work with no network and no Bee node (boundary B1); Swarm
is a persistence backend chosen at the edges (registry.swarm_offer_book,
Ontology.persistent over a swarm_store), never a requirement of the model.
"""

from .schema import (
    ASK, BID, GeoDisc, Offer, Thing, TimeWindow, Tokens, ask, bid,
)
from .ontology import Ontology
from .registry import OfferRegistry, swarm_offer_book
from .matching import Match, candidate_matches, check_match
from .graph import ExchangeGraph, Loop
from .settlement import LoopProposal, MockSettlement, Receipt, Settlement
from .solver.agent import SolverAgent

__version__ = "0.1.0"

__all__ = [
    "ASK", "BID", "GeoDisc", "Offer", "Thing", "TimeWindow", "Tokens",
    "ask", "bid", "Ontology", "OfferRegistry", "swarm_offer_book",
    "Match", "candidate_matches", "check_match", "ExchangeGraph", "Loop",
    "LoopProposal", "MockSettlement", "Receipt", "Settlement", "SolverAgent",
]
