"""Pairwise matching: does this GIVE satisfy that WANT?

A `Match` is one feasible handoff — the atom that loops are made of. The
check is exact and self-contained so that settlement can re-run it
independently of whatever index or heuristic produced the candidate
("verification cheap and neutral; discovery someone else's expensive
problem").

Conditions, in cheap-to-expensive order:

1. kinds:      one GIVE, one WANT, different makers
2. validity:   both offers open at `now`
3. time:       the service windows intersect (a delivery instant exists)
4. space:      the service discs intersect (a handover point exists)
5. quantity:   wanted quantity within given quantity (equal, unless
               divisible), identical units
6. meaning:    the given thing's concepts satisfy the wanted categories,
               under the pinned ontology
7. version:    pinned semantic ground must not move between the two sides:
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


def check_match(give: Offer, want: Offer, ontology: Ontology, *,
                now: int) -> Match | None:
    """The exact pairwise check; returns a Match or None."""
    if give.kind != GIVE or want.kind != WANT or give.maker == want.maker:
        return None
    if not (give.valid.is_open_at(now) and want.valid.is_open_at(now)):
        return None
    if not give.service.overlaps(want.service):
        return None
    if not give.where.intersects(want.where):
        return None
    g, w = give.thing, want.thing
    if w.qty > g.qty or (not g.divisible and w.qty != g.qty):
        return None
    if g.unit != w.unit:
        return None
    if ontology.root:  # a pinned catalogue refuses unpinned offers (U10)
        for o in (give, want):
            if not (o.ontology_root and o.registry_version
                    and o.contract_version):
                return None
    for g_pin, w_pin in ((give.ontology_root, want.ontology_root),
                         (give.registry_version, want.registry_version),
                         (give.contract_version, want.contract_version)):
        if bool(g_pin) != bool(w_pin):
            # mixed pinning: one side declares its ground, the other is
            # silent — agreement cannot be confirmed, so it is refused
            # (proof-fabric gate G2). Both-silent survives only under an
            # unpinned (development) catalogue, per the check above.
            return None
    if give.ontology_root and want.ontology_root and \
            give.ontology_root != want.ontology_root:
        return None
    if _major_skew(give.registry_version, want.registry_version) or \
            _major_skew(give.contract_version, want.contract_version):
        return None
    if not ontology.satisfies(g.concepts, w.concepts):
        return None
    return Match(give=give, want=want)


def candidate_matches(offers: Iterable[Offer], ontology: Ontology, *,
                      now: int) -> Iterator[Match]:
    """All feasible handoffs among `offers`.

    Prototype strategy: exact check over the give x want product, with the
    cheap constant-time conditions doing the pruning. This is
    O(gives*wants) and entirely adequate for books that fit in memory; the
    scaling path is `dimensions.candidate_matches_indexed` (concept cones
    and exact window overlap through the catalogue), refined by this same
    exact check.
    """
    gives = [o for o in offers if o.kind == GIVE]
    wants = [o for o in offers if o.kind == WANT]
    for g, w in product(gives, wants):
        m = check_match(g, w, ontology, now=now)
        if m is not None:
            yield m
