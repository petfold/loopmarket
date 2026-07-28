"""Pairwise matching: does this ASK satisfy that BID?

A `Match` is one feasible handoff — the atom that loops are made of. The
check is exact and self-contained so that settlement can re-run it
independently of whatever index or heuristic produced the candidate
("verification cheap and neutral; discovery someone else's expensive
problem").

Conditions, in cheap-to-expensive order:

1. kinds:      ask is an ASK, bid is a BID, different makers
2. validity:   both offers open at `now`
3. time:       the service windows intersect (a delivery instant exists)
4. space:      the service discs intersect (a handover point exists)
5. quantity:   bid quantity within ask quantity (equal, unless divisible)
6. meaning:    the ask's concepts satisfy the bid's wanted categories,
               under the pinned ontology
7. version:    if both offers pin an ontology root, the pins must agree —
               semantic ground must not move between the two sides

The match's `rate` is the exchange this handoff implies between the two
personal tokens: unit price the receiver bids, over unit price the giver
asks — the number whose product around a cycle decides profitability.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Iterator

from .ontology import Ontology
from .schema import ASK, BID, Offer


@dataclass(frozen=True, slots=True)
class Match:
    ask: Offer   # giver of the thing
    bid: Offer   # receiver of the thing

    @property
    def rate(self) -> float:
        """(bid unit price in receiver-tokens) / (ask unit price in giver-tokens)."""
        return self.bid.unit_price / self.ask.unit_price

    @property
    def giver(self) -> str:
        return self.ask.maker

    @property
    def receiver(self) -> str:
        return self.bid.maker

    @property
    def qty(self) -> float:
        return self.bid.thing.qty


def check_match(ask: Offer, bid: Offer, ontology: Ontology, *,
                now: int) -> Match | None:
    """The exact pairwise check; returns a Match or None."""
    if ask.kind != ASK or bid.kind != BID or ask.maker == bid.maker:
        return None
    if not (ask.valid.is_open_at(now) and bid.valid.is_open_at(now)):
        return None
    if not ask.service.overlaps(bid.service):
        return None
    if not ask.where.intersects(bid.where):
        return None
    a, b = ask.thing, bid.thing
    if b.qty > a.qty or (not a.divisible and b.qty != a.qty):
        return None
    if a.unit != b.unit:
        return None
    if ask.ontology_root and bid.ontology_root and \
            ask.ontology_root != bid.ontology_root:
        return None
    if not ontology.satisfies(a.concepts, b.concepts):
        return None
    return Match(ask=ask, bid=bid)


def candidate_matches(offers: Iterable[Offer], ontology: Ontology, *,
                      now: int) -> Iterator[Match]:
    """All feasible handoffs among `offers`.

    Prototype strategy: exact check over the ask x bid product, with the
    cheap constant-time conditions doing the pruning. This is O(asks*bids)
    and entirely adequate for books that fit in memory; the scaling path is
    candidate generation from the registry's idx/{c,t,g} prefixes (or, on
    the roadmap, one OntoDAG intersection query over concept x cell x
    bucket), refined by this same exact check.
    """
    asks = [o for o in offers if o.kind == ASK]
    bids = [o for o in offers if o.kind == BID]
    for a, b in product(asks, bids):
        m = check_match(a, b, ontology, now=now)
        if m is not None:
            yield m
