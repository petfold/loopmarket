"""Candidate generation through ontodag parametric dimensions — one query.

The want's categories and descriptive terms ARE the query (Peter,
2026-09-12: ontodag is intersection; for what a thing is, a want is the
wider cone and a give the narrower). Gives are filed in a derived catalogue
copy under exactly the terms they carry plus a private record-line marker;
a want's candidates are one ``dag.get([line marker, *one-way terms],
items_only=True)``: the gives inside every wanted category cone, ontodag's
planner ordering the cones smallest first, walking or probing from the
exact running result and stopping on empty. loopmarket does no set
arithmetic on the answer (`docs/plans/ontodag-coupling.md` §5, "one
intersection engine"): it iterates the items ontodag returns and runs the
exact pairwise `check_match` on each.

An operator term (`transport(small-item)`) is filed and queried as its
category (`transport`): the category goes give-within-want like any other,
the argument the other way round (`Ontology.satisfies`), so the argument
is the exact check's, like the coordinates below.

Handover coordinates — a bare geo or time term, a route's `from`/`to` —
are NOT in the query. They match when one side contains the other
(`Ontology.satisfies`), and the gives that *contain* the want's coordinate
(the seller who delivers anywhere in the city, for a want at a door) sit
above it, not in its cone; a downward query cannot reach them, and
loopmarket does not stitch a downward and an upward walk together in
Python. So place and time are decided by the exact check, per candidate.
When book sizes make place pruning worth having, the ask upstream is a
query term meaning "comparable to X" — below or above — which is two
containment walks, not overlap (`ontodag-coupling.md` §7).

Why the marker: it is what makes `items_only` return offers and nothing
else. A childless *category* in the wanted cone (`fruit-box` when nobody
offers one) is an item to ontodag, but it is not under the marker. A
retired v1/v2 offer is never filed and gets no candidates, since
`check_match` matches none.

The generator is recall-exact against the baseline give x want product —
and clearing re-verification never depends on it either way (invariant U3).

**The index is derived, local, and never shared.** Filing offers into the
shared catalogue would move its root under every offer that pins it, so
`DimensionIndex` works on a deepcopy: regenerable from book + catalogue,
per-solver, never merged — the same doctrine as every other index in this
stack. (Corollary: nothing here needs the dimensions registry version
pinned; that rule from ontodag's DIMENSIONS.md §10 applies when parametric
terms enter *shared* state, e.g. published region nodes in the catalogue.)

One ontodag adoption rule is load-bearing here: an item sits in the
INTERSECTION of its parents, so two same-head terms on one give mean one
thing meeting both — their meet, which ontodag stores as one value for a
value dimension and, since 0.30.6, as one term per constraint for a
graph-kind head (`option(apartment)` and `option(ljubljana-center)` for
`option(apartment ljubljana-center)`); and ontodag refuses provably
disjoint values.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from .matching import Match, check_match
from .ontology import Ontology
from .schema import GIVE, WANT, Offer

#: The index-private marker category every filed give is under.
_MARKER = "loopmarket:offer"


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
        if _MARKER not in self._dag.nodes:
            self._dag.put(_MARKER, [])

    def file(self, offer: Offer) -> bool:
        """Index a GIVE under its known concepts and the marker. A concept
        the catalogue cannot interpret is left out, not refused: an
        unknown term on the give side only narrows what the give is, and
        the exact check ignores it the same way (U7 fails closed on the
        *want* side — a want naming unknown vocabulary gets no
        candidates). Returns False when ontodag refuses the conjunction
        (provably disjoint same-head terms: it describes nothing), when
        the offer is not a give, and for a retired v1/v2 offer."""
        if offer.kind != GIVE or offer.v < 3:
            return False
        if offer.offer_id in self._filed:
            return True
        known = [self.ontology.operator_of(c) or c
                 for c in offer.thing.concepts if self.ontology.known(c)]
        try:
            self._dag.put(offer.offer_id, [*known, _MARKER])
        except ValueError:
            return False
        self._filed.add(offer.offer_id)
        return True

    def candidates(self, want_offer: Offer) -> set[str]:
        """Give offer-ids inside every wanted category cone: one `get`.
        Handover coordinates (place, time, a route's ends) are left to
        `check_match`, which every candidate still faces (module
        docstring). None for a retired v1/v2 want."""
        if want_offer.composed:
            return set()          # a composed want is met part by part (`parts_legs`)
        if want_offer.v < 3:
            return set()          # retired: read, never matched
        concepts = want_offer.thing.concepts
        if not all(self.ontology.known(c) for c in concepts):
            return set()          # unknown wanted vocabulary matches nothing
        one_way = [self.ontology.operator_of(c) or c for c in concepts
                   if self.ontology.handover_class(c) is None]
        try:
            items = self._dag.get([_MARKER, *one_way], items_only=True)
        except ValueError:        # a conjunction ontodag cannot order
            return set()
        return {item.name for item in items}


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
