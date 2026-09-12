"""Candidate generation through ontodag parametric dimensions — one query.

The 2026-07-30 upgrade of the P1 candidate-generation plan (ARCHITECTURE.md
§3), completed 2026-09-12 when ontodag #14/#15/#16 landed: gives are filed
under *exact* parametric terms in a derived catalogue copy, and a want's
candidates are **one** ``dag.get(terms, overlapping=[...], items_only=True)``
— ontodag's planner orders every cone (concept cones, the record-line
marker, each service-role overlap term) smallest-first, walks or probes
from the exact running result and stops on empty, so a category offered in
few places or windows cuts the search short across dimensions. loopmarket
does no set arithmetic on the answer (`docs/plans/ontodag-coupling.md` §5,
"one intersection engine"): it iterates the items ontodag returns and runs
the exact pairwise `check_match` on each.

What the one query says:

- meaning: the wanted plain concepts — exact-necessary: a give whose
  concepts satisfy the want is, by fits-within, inside every wanted cone.
  Descriptive spacetime terms (`made_in(u2e)`) are plain concepts here: a
  virtual query term whose cone computed containment fills;
- the record line: v1/v2 gives and v3 gives are filed under two private
  marker categories, and a want names its own — `check_match` refuses
  pairs across the line (a disc is not a cell), so a want only ever sees
  gives of its own record line. The marker is also what makes
  `items_only` return offers and nothing else: a childless *category* in
  the wanted cone (`fruit-box` when nobody offers one) is an item to
  ontodag, but it is not under the marker;
- service roles (`docs/plans/P1-spacetime-terms.md` §5.4): for each role
  head the want names — `from(...)`, `depart(...)`, whatever the catalogue
  hangs under `service-role` — the meet of its terms as an *overlap* term.
  Role terms may name nodes (a place, a region, a floor — ontodag #15) and
  the graph decides their overlap (#16), so place prunes exactly: a give
  `from(u2f)` never reaches the exact check for a want `from(my_home)`.
  **Absent = unconstrained** is `Ontology.satisfies`' rule — a give that
  names no `from(...)` serves a want anywhere — and an overlap term cannot
  see a give filed under no value of its head. So the index files every
  give under a *whole-space* value for each role head it is silent on:
  `from(loopmarket:anywhere:geo)`, a region node in the base dimension
  above the one-character cells (every prefix value begins with one, so
  by ontodag's §14 rule the region overlaps every cell, place and region;
  one region per base head, shared by every role over it, so the role
  stars stay small — a region under each role head cost twenty times
  more per put), or the full calendar range for a time role. Index-
  private vocabulary in a derived copy; nothing of it is ever shared. The
  cleaner spelling — an item under the bare role head means
  "unconstrained" — is the next upstream ask (`ontodag-coupling.md` §7);
- v1/v2 fields: ``service-time(a..b)`` over the offer's `service` window
  as one more overlap term — *exact* for the window-overlap gate, because
  the filed value IS the offer's window. The `where` disc stays with the
  exact check (``GeoDisc.intersects``): a disc is not a cell, so it is not
  filed at all (the 2026-07-30 centre-cell index fact was read by nothing
  and went with the one-query rewrite).

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
parents — two same-head role terms on one give are their meet, and ontodag
refuses provably disjoint ones); a give whose same-head terms have no
nameable meet is not filed, as `satisfies` matches it against nothing.
"""

from __future__ import annotations

import string
from datetime import datetime, timezone
from typing import Iterable, Iterator

from ontodag import dimensions as _dims

from .matching import Match, check_match
from .ontology import SERVICE_ROLE, Ontology
from .schema import GIVE, WANT, Offer, TimeWindow

TIME_DIMENSION = "service-time"

#: Index-private marker categories: which record line a filed give is on.
_LINE = {2: "loopmarket:record-line-2", 3: "loopmarket:record-line-3"}

#: The whole calendar as one inclusive range — what a time role is silent
#: about. ISO 8601 has four-digit years; every want window lies inside.
_ALL_TIME = "0001-01-01T00:00:00Z..9999-12-31T23:59:59Z"

#: Every character a prefix value may begin with (ontodag's grammar,
#: `[0-9A-Za-z]` first) — the one-character cells a whole-space region
#: node covers. Geohash uses 32 of them; the region covers the grammar,
#: so a want naming any cell ontodag accepts meets it.
_PREFIX_ALPHABET = string.digits + string.ascii_letters


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
        # role head -> the whole-space term a give silent on it is filed
        # under, one per service role the catalogue declares
        self._anywhere: dict[str, str] = {}
        self._regions: dict[str, str] = {}   # base head -> its region node
        self._declare()

    def _declare(self) -> None:
        for name, supers in [
            (_dims.DIMENSION_ROOT, []),
            (_dims.KIND_LINEAR, [_dims.DIMENSION_ROOT]),
            (TIME_DIMENSION, [_dims.KIND_LINEAR]),
            *((marker, []) for marker in _LINE.values()),
        ]:
            if name not in self._dag.nodes:
                self._dag.put(name, supers)
        for head in self._role_heads():
            self._anywhere[head] = self._declare_anywhere(head)

    def _role_heads(self) -> list[str]:
        """The service-role heads the catalogue declares (the marker's
        cone, heads only: a role term or item that happens to sit under a
        role in the catalogue is not a head)."""
        if SERVICE_ROLE not in self.ontology.dag.nodes:
            return []
        return sorted(
            item.name for item in self.ontology.dag.get([SERVICE_ROLE])
            if item.name != SERVICE_ROLE and _dims.split_term(item.name) is None
            and self.ontology.head_kind(item.name) is not None)

    def _base_of(self, head: str) -> str:
        """The base head of a role: the head directly under the kind node
        (`from` → `geo`), whose nodes a role term may name (ontodag #15)."""
        for item in [self._dag.nodes[head], *self._dag.get_ancestors(head)]:
            if any(p.name in _dims.KINDS for p in item.parents):
                return item.name
        raise ValueError(f"{head!r} has no base dimension head")

    def _declare_anywhere(self, head: str) -> str:
        """The whole-space value of a role head, filed once in the derived
        copy: a region node in the base dimension covering every
        one-character prefix (prefix kinds) or the full calendar (calendar
        kinds). Loud for a kind without a whole-space spelling — silently
        dropping recall for gives silent on such a role would break the
        recall-exactness guard."""
        kind = self.ontology.head_kind(head)
        if kind == _dims.KIND_PREFIX:
            base = self._base_of(head)
            region = self._regions.get(base)
            if region is None:
                region = self._regions[base] = f"loopmarket:anywhere:{base}"
                self._dag.put(region, [base])
                for ch in _PREFIX_ALPHABET:
                    self._dag.put(f"{base}({ch})", [region])
            return f"{head}({region})"
        if kind == _dims.KIND_CALENDAR:
            return f"{head}({_ALL_TIME})"
        raise NotImplementedError(
            f"service role {head!r} is a {kind}: the index has no "
            f"whole-space value to file gives silent on it under "
            f"(docs/plans/ontodag-coupling.md §7, the unconstrained-role ask)")

    def file(self, offer: Offer) -> bool:
        """Index a GIVE. Returns False (not filed) when its vocabulary is
        unknown to the catalogue — the same fail-closed outcome the exact
        check would reach (invariant U7): a role term ontodag cannot
        interpret is unknown vocabulary too, and so is a same-head
        conjunction it cannot decide."""
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
            try:
                empty = self.ontology.meet(head, terms) is None
            except ValueError:   # no single term names the meet
                return False
            if empty:
                # provably disjoint same-head terms: the conjunction is
                # empty, `satisfies` matches it against nothing, and
                # ontodag's disjoint-parents lint would refuse the put
                return False
        parents = [*offer.thing.concepts, _LINE[_line(offer)]]
        if offer.v < 3:
            parents.append(time_term(offer.service))
        parents += [term for head, term in self._anywhere.items()
                    if head not in roles]
        self._dag.put(offer.offer_id, parents)
        self._filed.add(offer.offer_id)
        return True

    def candidates(self, want_offer: Offer) -> set[str]:
        """Give offer-ids that can possibly match `want_offer`: inside every
        wanted plain cone, on the want's record line, service windows
        overlapping (v1/v2), and for each role head the want names,
        overlapping its meet — gives silent on the head are filed under its
        whole space, so they are in. One `get`; recall-exact for those
        gates; every candidate still faces `check_match`."""
        concepts = want_offer.thing.concepts
        if not all(self.ontology.known(c) for c in concepts):
            return set()          # unknown wanted vocabulary matches nothing
        roles, plain = self.ontology.split_roles(concepts)
        if roles is None:
            return set()
        overlapping = []
        if want_offer.v < 3:
            overlapping.append(time_term(want_offer.service))
        for head, terms in roles.items():
            try:
                meet = self.ontology.meet(head, terms)
            except ValueError:    # an undecidable want matches nothing
                return set()
            if meet is None:      # a provably empty want matches nothing
                return set()
            overlapping.append(meet)
        items = self._dag.get([_LINE[_line(want_offer)], *plain],
                              overlapping=overlapping, items_only=True)
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
