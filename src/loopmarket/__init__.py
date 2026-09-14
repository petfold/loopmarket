"""loopmarket — a universal combinatorial marketplace over OntoDAG + recordstore + Swarm.

One uniform offer form; a shared OntoDAG catalogue in which meanings, minutes
and map regions are ordered by the same fits-within relation; a distributed,
versioned offer book over recordstore (Swarm-backed via BeeBytesStore +
SwarmFeedPointer); competing solver agents hunting profitable loops as
negative cycles; clearing that re-verifies everything and trusts no one.

Dependency direction (boundary B2, enforced by tests/test_boundaries.py):

    loopmarket  ->  ontodag  ->  recordstore  ->  (Swarm, optional)

The core imports work with no network and no Bee node (boundary B1); Swarm
is a persistence backend chosen at the edges (registry.swarm_offer_book,
Ontology.persistent over a swarm_store), never a requirement of the model.
"""

from .schema import (
    ASK, BID, GIVE, WANT, GeoDisc, Offer, Parts, Thing, TimeWindow, Tokens,
    ask, bid, give, q, rat, want,
)
from .federation import Aggregator, Manifest, Omission, audit_manifest
from .ontology import Ontology
from .registry import OfferRegistry, PartialLoopError, swarm_offer_book
from .matching import Leg, Match, aggregate_legs, candidate_matches, check_aggregate, check_composition, check_match, check_parts, parts_legs
from .sigs import maker_address, recover_maker, sign_offer, verify_offer_sig
from .dimensions import DimensionIndex, candidate_matches_indexed
from .graph import Circulation, ExchangeGraph, Loop, find_circulations
from .clearing import LoopProposal, MockClearing, Receipt, Clearing
from .solver.agent import SolverAgent

__version__ = "0.8.0"

__all__ = [
    "GIVE", "WANT", "ASK", "BID", "GeoDisc", "Offer", "Parts", "Thing", "TimeWindow",
    "Tokens", "give", "want", "ask", "bid", "q", "rat",
    "check_parts", "parts_legs", "check_aggregate", "aggregate_legs",
    "Aggregator", "Manifest", "Omission", "audit_manifest", "Ontology", "OfferRegistry",
    "PartialLoopError", "swarm_offer_book",
    "Match", "candidate_matches", "check_match",
    "maker_address", "recover_maker", "sign_offer", "verify_offer_sig",
    "DimensionIndex", "candidate_matches_indexed", "ExchangeGraph", "Loop",
    "Circulation", "find_circulations", "Leg", "check_composition",
    "LoopProposal", "MockClearing", "Receipt", "Clearing", "SolverAgent",
]
