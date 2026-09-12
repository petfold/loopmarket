"""Candidate generation through ontodag parametric dimensions — one query.

The want's conjunction IS the query (Peter, 2026-09-12: ontodag is
intersection; a want is the wider cone, a give the narrower). Gives are
filed in a derived catalogue copy under exactly the terms they carry —
categories, descriptive terms, and the place and time terms of the roles
the catalogue declares (`where(u2e4x)`, `from(my_home)`, `when(...)`) —
plus a private record-line marker; a want's candidates are one
``dag.get([line marker, *want.concepts], items_only=True)``: the gives
inside every wanted cone, ontodag's planner ordering the cones smallest
first, walking or probing from the exact running result and stopping on
empty. Place and time prune like categories, because they are terms like
categories. loopmarket does no set arithmetic on the answer
(`docs/plans/ontodag-coupling.md` §5, "one intersection engine"): it
iterates the items ontodag returns and runs the exact pairwise
`check_match` on each — whose meaning half, `Ontology.satisfies`, is the
same containment test term by term.

Why the marker: `check_match` refuses pairs across the v2/v3 record line
(a disc is not a cell), so v1/v2 gives and v3 gives are filed under two
private marker categories and a want names its own. The marker is also
what makes `items_only` return offers and nothing else: a childless
*category* in the wanted cone (`fruit-box` when nobody offers one) is an
item to ontodag, but it is not under the marker.

Nothing else is filed. A give silent on a head is in no cone of that
head, which is the containment reading of silence; the v1/v2 window and
disc are fields the exact check gates, not terms (an index fact for them
would be a second machine). There was, for one day, an overlap mode —
role terms matched by "a handover point exists", three queries intersected
in Python, then ontodag #14's `overlapping=` planner argument, then a
whole-space value for silence — all withdrawn 2026-09-12 night when the
question was asked properly (`docs/plans/P1-spacetime-terms.md` §3).

The generator is recall-exact against the baseline give x want product —
and clearing re-verification never depends on it either way (invariant U3).

**The index is derived, local, and never shared.** Filing offers into the
shared catalogue would move its root under every offer that pins it, so
`DimensionIndex` works on a deepcopy: regenerable from book + catalogue,
per-solver, never merged — the same doctrine as every other index in this
stack. (Corollary: nothing here needs the dimensions registry version
pinned; that rule from ontodag's DIMENSIONS.md §10 applies when parametric
terms enter *shared* state, e.g. published region nodes in the catalogue.)

One ontodag adoption rule is load-bearing here: an offer is filed under
exactly ONE value per dimension (an item sits in the INTERSECTION of its
parents — two same-head terms on one give are their meet, and ontodag
refuses provably disjoint ones).
"""

from __future__ import annotations

from typing import Iterable, Iterator

from .matching import Match, check_match
from .ontology import Ontology
from .schema import GIVE, WANT, Offer

#: Index-private marker categories: which record line a filed give is on.
_LINE = {2: "loopmarket:record-line-2", 3: "loopmarket:record-line-3"}



def _line(offer: Offer) -> int:
    return 3 if offer.v >= 3 else 2


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
        for marker in _LINE.values():
            if marker not in self._dag.nodes:
                self._dag.put(marker, [])

    def file(self, offer: Offer) -> bool:
        """Index a GIVE under its concepts and its record-line marker.
        Returns False (not filed) when its vocabulary is unknown to the
        catalogue — the same fail-closed outcome the exact check would
        reach (invariant U7) — or when ontodag refuses the conjunction
        (provably disjoint same-head terms: it matches nothing)."""
        if offer.kind != GIVE:
            return False
        if offer.offer_id in self._filed:
            return True
        if not all(self.ontology.known(c) for c in offer.thing.concepts):
            return False
        try:
            self._dag.put(offer.offer_id,
                          [*offer.thing.concepts, _LINE[_line(offer)]])
        except ValueError:
            return False
        self._filed.add(offer.offer_id)
        return True

    def candidates(self, want_offer: Offer) -> set[str]:
        """Give offer-ids inside every wanted cone, on the want's record
        line: one `get`. Recall-exact for the meaning gate; every candidate
        still faces `check_match` (rates, quantities, pins, the v1/v2 field
        gates)."""
        concepts = want_offer.thing.concepts
        if not all(self.ontology.known(c) for c in concepts):
            return set()          # unknown wanted vocabulary matches nothing
        try:
            items = self._dag.get([_LINE[_line(want_offer)], *concepts],
                                  items_only=True)
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
