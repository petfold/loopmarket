"""Candidate generation through ontodag parametric dimensions (>= 0.4.0).

The 2026-07-30 upgrade of the P1 candidate-generation plan (ARCHITECTURE.md
§3): instead of generated bucket/cell category chains, gives are filed under
*exact* parametric terms and a want's candidates come from native catalogue
queries:

- meaning: ``dag.get(wanted plain concepts)`` — exact-necessary: a give whose
  concepts satisfy the want is, by fits-within, inside every wanted cone.
  Descriptive spacetime terms (`made_in(u2e)`) are plain concepts here: a
  virtual query term whose cone computed containment fills;
- service roles (since 2026-09-12, `docs/plans/P1-spacetime-terms.md` §5.4):
  for each role head the want names — `from(...)`, `depart(...)`, whatever
  the catalogue hangs under `service-role` — ``dag.get_overlapping(meet)``
  over the gives filed under that head, *plus* every filed give that names
  no term of that head at all (absent = unconstrained, exactly the rule
  `Ontology.satisfies` applies). This is where place prunes: role terms
  carry cells, and cells are the truth for them, so a give `from(u2f)`
  never reaches the exact check for a want `from(u2e4x)`;
- v2 fields: ``dag.get_overlapping(service-time(a..b))`` over the offer's
  `service` window — *exact* for the window-overlap gate, because the
  filed value IS the offer's window (no buckets, no quantization error).
  The `where` disc stays with the exact check (``GeoDisc.intersects``): a
  disc is not a cell, so its centre cell is filed as an index fact only.
  Both private heads (`service-time`, `service-cell`) retire with the v3
  record, when the fields leave and every window and place is a role term.

The generator is recall-exact against the baseline give x want product —
and clearing re-verification never depends on it either way (invariant U3).

**The index is derived, local, and never shared.** Filing offers into the
shared catalogue would move its root under every offer that pins it, so
`DimensionIndex` works on a deepcopy: regenerable from book + catalogue,
per-solver, never merged — the same doctrine as every other index in this
stack. (Corollary: nothing here needs the dimensions registry version
pinned; that rule from ontodag's DIMENSIONS.md §10 applies when parametric
terms enter *shared* state, e.g. published region nodes in the catalogue.)

Two ontodag adoption rules are load-bearing here: an offer is filed under
exactly ONE value per dimension (an item sits in the INTERSECTION of its
parents — two same-head role terms on one give are their meet, and ontodag
refuses provably disjoint ones), and the cell value indexes the disc's
*centre* cell only, which is fine because the disc is not used for pruning.

Still three queries intersected in Python: ontodag #14 asks for overlap
terms inside `get`'s planner, after which `candidates` is one call.
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
        # role head -> the filed gives naming a term of it; the complement
        # is what an overlap query cannot see and a want must still meet
        self._with_role: dict[str, set[str]] = {}
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
        """Index a GIVE. Returns False (not filed) when its vocabulary is
        unknown to the catalogue — the same fail-closed outcome the exact
        check would reach (invariant U7): a role term ontodag cannot
        interpret is unknown vocabulary too."""
        if offer.kind != GIVE:
            return False
        if offer.offer_id in self._filed:
            return True
        if not all(self.ontology.known(c) for c in offer.thing.concepts):
            return False
        roles, _ = self.ontology.split_roles(offer.thing.concepts)
        if roles is None:  # pragma: no cover - `known` above already refused
            return False
        for head, terms in roles.items():
            if self.ontology.meet(head, terms) is None:
                # provably disjoint same-head terms: the conjunction is
                # empty, `satisfies` matches it against nothing, and
                # ontodag's disjoint-parents lint would refuse the put
                return False
        self._dag.put(
            offer.offer_id,
            list(offer.thing.concepts)
            + [time_term(offer.service), cell_term(offer)])
        self._filed.add(offer.offer_id)
        for head in roles:
            self._with_role.setdefault(head, set()).add(offer.offer_id)
        return True

    def candidates(self, want_offer: Offer) -> set[str]:
        """Give offer-ids that can possibly match `want_offer`: inside every
        wanted plain cone, service windows overlapping, and for each role
        head the want names, overlapping it or silent on it. Recall-exact
        for those gates; every candidate still faces `check_match`."""
        concepts = want_offer.thing.concepts
        if not all(self.ontology.known(c) for c in concepts):
            return set()          # unknown wanted vocabulary matches nothing
        roles, plain = self.ontology.split_roles(concepts)
        if roles is None:
            return set()
        result = set(self._filed)
        if plain:
            result &= {item.name for item in self._dag.get(list(plain))}
        if not result:
            return set()
        result &= {item.name for item in
                   self._dag.get_overlapping(time_term(want_offer.service))}
        for head, terms in roles.items():
            if not result:
                break
            try:
                meet = self.ontology.meet(head, terms)
            except ValueError:
                return set()
            if meet is None:      # a provably empty want matches nothing
                return set()
            overlapping = {item.name for item in self._dag.get_overlapping(meet)}
            silent = self._filed - self._with_role.get(head, set())
            result &= overlapping | silent
        return result


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
