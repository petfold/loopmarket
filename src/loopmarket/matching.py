"""Pairwise matching: does this GIVE satisfy that WANT?

A `Match` is one feasible handoff — the atom that loops are made of. The
check is exact and self-contained so that clearing can re-run it
independently of whatever index or heuristic produced the candidate
("verification cheap and neutral; discovery someone else's expensive
problem").

Conditions, in cheap-to-expensive order:

1. kinds:      one GIVE, one WANT, different makers
2. record:     both sides on the same side of the v2/v3 line — a v2
               offer's place is a disc, a v3 offer's a cell, and a view
               of one as the other would say what the maker never said
               (decided 2026-09-12: refuse; repost instead)
3. validity:   both offers open at `now`
4. time:       v1/v2 only — the service windows intersect (a delivery
               instant exists); v3 says it with a bare `time(...)` in step 7
5. space:      v1/v2 only — the service discs intersect (a handover point
               exists); v3 says it with a bare geo term or `from(...)`/`to(...)`
6. quantity:   wanted quantity within given quantity (equal, unless
               divisible), identical units
7. meaning:    the given conjunction satisfies the wanted one under the
               pinned ontology — containment, term by term: what the thing
               is and where and when it changes hands alike; the want is
               the wider cone, the give the narrower (`Ontology.satisfies`)
8. version:    pinned semantic ground must not move between the two sides:
               ontology roots must agree, registry/contract versions must
               not diverge on their major component (ontodag D10: minor
               skew is vocabulary-additive and interoperates) — and once
               the verifier's own catalogue is pinned, absence refuses too
               (planned U10: the fail-open '' wildcard dies when there is
               a persistent root to demand; docs/plans/proof-fabric.md §3)

The match's `rate` is the exchange this handoff implies between the two
personal scales: the receiver's quoted price over the giver's quoted
price — the number whose product around a cycle decides profitability.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Iterator

from .ontology import Ontology
from .schema import GIVE, WANT, Offer


@dataclass(frozen=True, slots=True)
class Match:
    give: Offer   # the offer giving the thing
    want: Offer   # the offer receiving it

    @property
    def rate(self) -> float:
        """(the wanter's quoted price) / (the giver's quoted price)."""
        return self.want.unit_price / self.give.unit_price

    @property
    def giver(self) -> str:
        return self.give.maker

    @property
    def receiver(self) -> str:
        return self.want.maker

    @property
    def qty(self) -> float:
        return self.want.thing.qty

    # order-book synonyms
    @property
    def ask(self) -> Offer:
        return self.give

    @property
    def bid(self) -> Offer:
        return self.want


def _major_skew(a: str, b: str) -> bool:
    """Both sides pin a version and the majors differ (refuse, per D10)."""
    return bool(a) and bool(b) and a.split(".")[0] != b.split(".")[0]


def _gates(give: Offer, want: Offer, ontology: Ontology, *, now: int,
           quantity: bool = True) -> bool:
    """Everything `check_match` decides before meaning: kinds and makers,
    the record line, validity, the v1/v2 fields, quantity and unit (skipped
    for an operator give, which moves a lot rather than being one), pins."""
    if give.kind != GIVE or want.kind != WANT or give.maker == want.maker:
        return False
    if (give.v >= 3) != (want.v >= 3):
        return False
    if not (give.valid.is_open_at(now) and want.valid.is_open_at(now)):
        return False
    if give.v < 3:
        if not give.service.overlaps(want.service):
            return False
        if not give.where.intersects(want.where):
            return False
    g, w = give.thing, want.thing
    if quantity:
        if w.qty > g.qty or (not g.divisible and w.qty != g.qty):
            return False
        if g.unit != w.unit:
            return False
    if ontology.root:  # a pinned catalogue refuses unpinned offers (U10)
        for o in (give, want):
            if not (o.ontology_root and o.registry_version
                    and o.contract_version):
                return False
    for g_pin, w_pin in ((give.ontology_root, want.ontology_root),
                         (give.registry_version, want.registry_version),
                         (give.contract_version, want.contract_version)):
        if bool(g_pin) != bool(w_pin):
            # mixed pinning: one side declares its ground, the other is
            # silent — agreement cannot be confirmed, so it is refused
            # (proof-fabric gate G2). Both-silent survives only under an
            # unpinned (development) catalogue, per the check above.
            return False
    if give.ontology_root and want.ontology_root and \
            give.ontology_root != want.ontology_root:
        return False
    if _major_skew(give.registry_version, want.registry_version) or \
            _major_skew(give.contract_version, want.contract_version):
        return False
    return True


def check_match(give: Offer, want: Offer, ontology: Ontology, *,
                now: int) -> Match | None:
    """The exact pairwise check; returns a Match or None."""
    if not _gates(give, want, ontology, now=now):
        return None
    if not ontology.satisfies(give.thing.concepts, want.thing.concepts):
        return None
    return Match(give=give, want=want)


@dataclass(frozen=True, slots=True)
class Leg:
    """One want satisfied by one or more gives — the hyperedge of
    `docs/plans/P2-loop-selection.md` §10/§11. A simple leg has one give
    (a `Match`); a composed leg has the give of the thing plus the
    operator gives that move it to the want's coordinates (the box at
    the shop plus the courier's run). One fill decision: all or none."""

    want: Offer
    gives: tuple[Offer, ...]

    @classmethod
    def from_match(cls, m: Match) -> "Leg":
        return cls(m.want, (m.give,))

    @property
    def head(self) -> str:
        return self.want.maker

    @property
    def tails(self) -> tuple[str, ...]:
        return tuple(g.maker for g in self.gives)

    @property
    def offer_ids(self) -> tuple[str, ...]:
        return (*(g.offer_id for g in self.gives), self.want.offer_id)

    @property
    def simple(self) -> bool:
        return len(self.gives) == 1

    @property
    def key(self) -> str:
        return f"{'+'.join(g.offer_id for g in self.gives)}>{self.want.offer_id}"


def check_composition(want: Offer, gives: Iterable[Offer], ontology: Ontology,
                      *, now: int) -> Leg | None:
    """The exact check of a composed leg (`P2-loop-selection.md` §10, the
    discovered form): the first give is the thing, every further give an
    operator that moves it along a dimension the catalogue declares an
    operator for — transport moves place (`from`/`to` over geo). Each
    operator's input must be comparable with the thing's coordinate as it
    stands (one contains the other, the handover rule), and its output
    replaces that coordinate; the thing so moved must then satisfy the
    want like any give. Every give passes `check_match`'s gates against
    the want (an operator without the quantity gate: it moves a lot rather
    than being one). Clearing re-runs this; nothing is trusted (U3)."""
    gives = tuple(gives)
    if not gives:
        return None
    thing, operators = gives[0], gives[1:]
    if not _gates(thing, want, ontology, now=now):
        return None
    declared = ontology.operators()
    derived = list(thing.thing.concepts)
    for op in operators:
        if not _gates(op, want, ontology, now=now, quantity=False):
            return None
        moved = False
        for base, (inp, out) in sorted(declared.items()):
            in_term = next((c for c in op.thing.concepts
                            if ontology.handover_class(c) == inp), None)
            out_term = next((c for c in op.thing.concepts
                             if ontology.handover_class(c) == out), None)
            if in_term is None or out_term is None:
                continue
            here = ontology.coordinate(derived, base)
            if here is None:
                return None            # the thing states no such coordinate
            start = ontology.bare(in_term)
            if not (ontology.covers(start, here) or ontology.covers(here, start)):
                return None            # the operator cannot pick it up there
            derived.remove(here)
            derived.append(ontology.bare(out_term))
            moved = True
        if not moved:
            return None                # not an operator give
    if not ontology.satisfies(derived, want.thing.concepts):
        return None
    return Leg(want, gives)


def composed_legs(offers: Iterable[Offer], ontology: Ontology, *,
                  now: int) -> Iterator[Leg]:
    """Baseline composition search: every want × every thing-give × every
    single operator give, checked exactly. One hop only (the open problem
    of §10); cubic in the book, which the baseline accepts as the recall
    benchmark composing species must beat. Deterministic order."""
    offers = list(offers)
    declared = ontology.operators()
    if not declared:
        return
    inputs = {inp for inp, _ in declared.values()}
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    wants = sorted((o for o in offers if o.kind == WANT), key=lambda o: o.offer_id)
    ops = [g for g in gives
           if any(ontology.handover_class(c) in inputs for c in g.thing.concepts)]
    things = [g for g in gives if g not in ops]
    for w in wants:
        for thing in things:
            for op in ops:
                leg = check_composition(w, (thing, op), ontology, now=now)
                if leg is not None:
                    yield leg


def candidate_matches(offers: Iterable[Offer], ontology: Ontology, *,
                      now: int) -> Iterator[Match]:
    """All feasible handoffs among `offers`.

    Prototype strategy: exact check over the give x want product, with the
    cheap constant-time conditions doing the pruning. This is
    O(gives*wants) and entirely adequate for books that fit in memory; the
    scaling path is `dimensions.candidate_matches_indexed` (the want's
    conjunction as one catalogue query), refined by this same exact
    check.
    """
    gives = [o for o in offers if o.kind == GIVE]
    wants = [o for o in offers if o.kind == WANT]
    for g, w in product(gives, wants):
        m = check_match(g, w, ontology, now=now)
        if m is not None:
            yield m
