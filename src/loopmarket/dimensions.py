"""The one candidate engine: ontodag's index of the gives, one query per
wanted thing.

Every search that pairs gives with wants asks it — `candidate_matches`,
`aggregate_legs`, `parts_legs` part by part and `composed_legs`
(`matching.py`) — whatever the size of the book: the 2026-10 review's item
2, decided by Peter 2026-10-10, one engine and no threshold. The give x
want product they ran before survives only as the oracle the tests compare
them against (`tests/oracle.py`).

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

Why the marker: `check_match` refuses pairs across the v2/v3 record line
(a disc is not a cell), so v1/v2 gives and v3 gives are filed under two
private marker categories and a want names its own. The marker is also
what makes `items_only` return offers and nothing else: a childless
*category* in the wanted cone (`fruit-box` when nobody offers one) is an
item to ontodag, but it is not under the marker.

The index is recall-exact — a give outside a wanted cone cannot satisfy the
want, so every candidate the product would check and pass is in the
answer — and clearing re-verification never depends on it either way
(invariant U3).

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

from typing import Iterable

from .matching import candidate_matches
from .ontology import Ontology
from .schema import GIVE, Offer, Thing

#: Index-private marker categories: which record line a filed give is on.
_LINE = {2: "loopmarket:record-line-2", 3: "loopmarket:record-line-3"}



def _line(offer: Offer) -> int:
    return 3 if offer.v >= 3 else 2


class DimensionIndex:
    """Files gives into a derived catalogue copy; answers want candidates.

    Build one per solve step, like a snapshot, and hand it to every search
    of the step (their `index=`): building it is its fixed cost (a copy of
    the catalogue), and regenerating it is what keeps it honest (derived
    state is never merged, never persisted).
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
        """Index a GIVE under its known concepts and its record-line
        marker. A concept the catalogue cannot interpret is left out, not
        refused: an unknown term on the give side only narrows what the
        give is, and the exact check ignores it the same way (U7 fails
        closed on the *want* side — a want naming unknown vocabulary gets
        no candidates). Returns False when ontodag refuses the conjunction
        (provably disjoint same-head terms: it describes nothing) or when
        the offer is not a give."""
        if offer.kind != GIVE:
            return False
        if offer.offer_id in self._filed:
            return True
        known = [self.ontology.operator_of(c) or c
                 for c in offer.thing.concepts if self.ontology.known(c)]
        try:
            self._dag.put(offer.offer_id, [*known, _LINE[_line(offer)]])
        except ValueError:
            return False
        self._filed.add(offer.offer_id)
        return True

    def query(self, thing: Thing) -> list[str] | None:
        """The terms the index asks for a wanted `thing`: its categories and
        descriptive terms, an operator term as its category (its argument
        is the exact check's). Handover coordinates — place, time, a
        route's ends — are not asked: a give that contains the want's
        coordinate sits above it, not in its cone, so they are left to the
        exact check, which every candidate still faces (module docstring).
        None when the catalogue does not know one of the concepts: unknown
        wanted vocabulary matches nothing (U7)."""
        if not all(self.ontology.known(c) for c in thing.concepts):
            return None
        return [self.ontology.operator_of(c) or c for c in thing.concepts
                if self.ontology.handover_class(c) is None]

    def cone(self, want_offer: Offer, terms: Iterable[str]) -> set[str]:
        """Give offer-ids on `want_offer`'s record line inside every cone of
        `terms`: one `get`, ontodag's planner ordering the cones smallest
        first and stopping on empty, no set arithmetic on the answer."""
        try:
            items = self._dag.get([_LINE[_line(want_offer)], *terms],
                                  items_only=True)
        except ValueError:        # a conjunction ontodag cannot order
            return set()
        return {item.name for item in items}

    def candidates(self, want_offer: Offer, thing: Thing | None = None) -> set[str]:
        """Give offer-ids that may serve `thing` — the want's own thing, or
        one part of a composed want — on the want's record line: the gives
        inside every cone `query` asks for, one `get`."""
        if thing is None:
            if want_offer.composed:
                return set()      # a composed want is met part by part: name the part
            thing = want_offer.thing
        terms = self.query(thing)
        return set() if terms is None else self.cone(want_offer, terms)


#: The older name of `matching.candidate_matches`, from when the index was
#: the alternative to the give x want product rather than the engine.
candidate_matches_indexed = candidate_matches
