"""Candidate generation through ontodag parametric dimensions (>= 0.4.0).

The 2026-07-30 upgrade of the P1 candidate-generation plan (ARCHITECTURE.md
§3): instead of generated bucket/cell category chains, gives are filed under
*exact* parametric terms — the service window as one linear-interval value,
the service cell as one prefix value — and a want's candidates come from two
native catalogue queries:

- meaning: ``dag.get(wanted_concepts)`` — exact-necessary: an give whose
  concepts satisfy the want is, by fits-within, inside every wanted cone;
- time:    ``dag.get_overlapping(service-time(a..b))`` — *exact* for the
  window-overlap gate, because the filed value IS the offer's window
  (no buckets, no quantization error).

Geo stays with the exact check (``GeoDisc.intersects``), as in the baseline:
sibling geohash cells share no prefix, so a cell filter would lose recall
("cells are hints", ARCHITECTURE.md §3). The generator is therefore
recall-exact against the baseline give x want product — and settlement
re-verification never depends on it either way (invariant U3).

**The index is derived, local, and never shared.** Filing offers into the
shared catalogue would move its root under every offer that pins it, so
`DimensionIndex` works on a deepcopy: regenerable from book + catalogue,
per-solver, never merged — the same doctrine as every other index in this
stack. (Corollary: nothing here needs the dimensions registry version
pinned; that rule from ontodag's DIMENSIONS.md §10 applies when parametric
terms enter *shared* state, e.g. published region nodes in the catalogue.)

Two ontodag adoption rules are load-bearing here: an offer is filed under
exactly ONE value per dimension (an item sits in the INTERSECTION of its
parents — never fan a union of cells or buckets into parents), and the cell
value indexes the disc's *centre* cell only, which is fine because geo is
not used for pruning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from ontodag import dimensions as _dims

from .matching import Match, check_match
from .ontology import Ontology
from .schema import GIVE, WANT, Offer, TimeWindow
from .spacetime import cell_for

TIME_DIMENSION = "service-time"
CELL_DIMENSION = "service-cell"


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def time_term(window: TimeWindow) -> str:
    """The window as one inclusive parametric value.

    `TimeWindow` is half-open [start, end) in whole seconds; dimension
    ranges are inclusive, so [start, end-1] represents exactly the same
    set of service seconds — overlap is preserved exactly.
    """
    return f"{TIME_DIMENSION}({_iso(window.start)}..{_iso(window.end - 1)})"


def cell_term(offer: Offer) -> str:
    """The offer's centre geohash cell as one prefix value (an index fact,
    not a pruning gate — see the module docstring)."""
    return f"{CELL_DIMENSION}({cell_for(offer.where)})"


class DimensionIndex:
    """Files gives into a derived catalogue copy; answers want candidates.

    Build one per solve step, like a snapshot: it is cheap relative to the
    O(gives x wants) product it replaces, and regenerating it is what keeps it
    honest (derived state is never merged, never persisted).
    """

    def __init__(self, ontology: Ontology):
        self.ontology = ontology            # the exact-check ground truth
        self._dag = ontology.dag.deepcopy()  # derived: catalogue + offers
        self._filed: set[str] = set()
        self._declare()

    def _declare(self) -> None:
        for name, supers in [
            (_dims.DIMENSION_ROOT, []),
            (_dims.KIND_LINEAR, [_dims.DIMENSION_ROOT]),
            (_dims.KIND_PREFIX, [_dims.DIMENSION_ROOT]),
            (TIME_DIMENSION, [_dims.KIND_LINEAR]),
            (CELL_DIMENSION, [_dims.KIND_PREFIX]),
        ]:
            if name not in self._dag.nodes:
                self._dag.put(name, supers)

    def file(self, offer: Offer) -> bool:
        """Index an GIVE. Returns False (not filed) when its vocabulary is
        unknown to the catalogue — the same fail-closed outcome the exact
        check would reach (invariant U7)."""
        if offer.kind != GIVE:
            return False
        if offer.offer_id in self._filed:
            return True
        if not all(self.ontology.known(c) for c in offer.thing.concepts):
            return False
        self._dag.put(
            offer.offer_id,
            list(offer.thing.concepts)
            + [time_term(offer.service), cell_term(offer)])
        self._filed.add(offer.offer_id)
        return True

    def candidates(self, want_offer: Offer) -> set[str]:
        """Give offer-ids that can possibly match `want_offer`: inside every
        wanted concept cone AND service windows overlapping. Recall-exact
        for those two gates; every candidate still faces `check_match`."""
        by_concept = {item.name
                      for item in self._dag.get(list(want_offer.thing.concepts))}
        if not by_concept:
            return set()
        by_time = {item.name for item in
                   self._dag.get_overlapping(time_term(want_offer.service))}
        return by_concept & by_time & self._filed


def candidate_matches_indexed(
        offers: Iterable[Offer], ontology: Ontology, *,
        now: int, index: DimensionIndex | None = None) -> Iterator[Match]:
    """Drop-in for `matching.candidate_matches`, generating through a
    `DimensionIndex` instead of the full give x want product. Yields exactly
    the baseline's matches (the recall test in tests/test_dimensions.py is
    the benchmark ARCHITECTURE.md §6 demands of smarter generators)."""
    offers = list(offers)
    index = index if index is not None else DimensionIndex(ontology)
    gives_by_id: dict[str, Offer] = {}
    for offer in offers:
        if offer.kind == GIVE and index.file(offer):
            gives_by_id[offer.offer_id] = offer
    for want_offer in offers:
        if want_offer.kind != WANT:
            continue
        for oid in sorted(index.candidates(want_offer)):
            match = check_match(gives_by_id[oid], want_offer, ontology, now=now)
            if match is not None:
                yield match
