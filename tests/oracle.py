"""The give x want product: the oracle the one matching engine is tested
against (the 2026-10 review's item 2, decided by Peter 2026-10-10).

These are the four searches as loopmarket ran them before the ontodag
index became their candidate generator, kept verbatim: every give against
every want, the exact checks doing the pruning. Nothing in loopmarket
calls them; `tests/test_one_engine.py` checks that `candidate_matches`,
`aggregate_legs`, `parts_legs` and `composed_legs` find exactly what these
find, and `scripts/perf_matching.py` measures the two against each other
(gate G3)."""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Iterable, Iterator

from loopmarket.matching import (Leg, Match, _gates, check_aggregate, check_composition, check_match,
                                 check_parts)
from loopmarket.ontology import Ontology
from loopmarket.reads import Reads, reads_of
from loopmarket.schema import GIVE, WANT, Offer, q


def aggregate_legs(offers: Iterable[Offer], ontology: Ontology, *, now: int,
                   reads: Reads | None = None, available=None, held=None, gate=None,
                   max_gives: int = 6, max_alternatives: int = 8) -> Iterator[Leg]:
    """Baseline aggregation search: for every simple want no single give
    serves, the gives of its thing in id order, each contributing a share it
    may give — the most first (its whole remainder, or the largest multiple
    of its step within what the want still needs), then smaller multiples,
    never below its floor — depth-first until the shares sum to the want's
    quantity: the first such set, at most `max_gives` gives, checked
    exactly. Deterministic (U6); polynomial only because the pool and the
    alternatives per give are bounded — the recall benchmark a smarter
    aggregating species must beat."""
    reads = reads_of(reads, available=available, held=held, gate=gate)
    available = reads.available
    offers = list(offers)
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    for w in sorted((o for o in offers if o.kind == WANT and not o.composed),
                    key=lambda o: o.offer_id):
        if any(check_match(g, w, ontology, now=now, reads=reads) for g in gives):
            continue                   # one give reaches: nothing to add up
        pool = [g for g in gives
                if _gates(g, w, ontology, now=now, quantity=False, reads=reads)
                and g.thing.unit == w.thing.unit
                and ontology.satisfies(g.thing.concepts, w.thing.concepts)]
        need = q(w.thing.qty)

        def shares(g: Offer, r: Fraction) -> list[Fraction]:
            """What `g` may contribute towards `r`, largest first: its whole
            remainder or the multiples of its step within `r` (at most
            `max_alternatives`), each above its floor."""
            left = q(g.thing.qty) if available is None else \
                min(q(g.thing.qty), available.get(g.offer_id, q(g.thing.qty)))
            cap = min(left, r)
            s = q(g.thing.step)
            if s == 0:
                return [cap] if cap > 0 and g.thing.takes(cap, left) else []
            out, t, n = [], (cap // s) * s, 0
            while t > 0 and n < max_alternatives:
                if g.thing.takes(t, left):
                    out.append(t)
                    n += 1
                t -= s
            return out

        def dfs(start: int, r: Fraction, chosen: list, taken: list):
            if r == 0:
                return chosen, taken
            if len(chosen) >= max_gives:
                return None
            for i in range(start, len(pool)):
                for t in shares(pool[i], r):
                    found = dfs(i + 1, r - t, chosen + [pool[i]], taken + [t])
                    if found is not None:
                        return found
            return None

        found = dfs(0, need, [], [])
        if found is not None and len(found[0]) >= 2:
            leg = check_aggregate(w, found[0], found[1], ontology, now=now, reads=reads)
            if leg is not None:
                yield leg


def parts_legs(offers: Iterable[Offer], ontology: Ontology, *, now: int, limit: int = 64,
               reads: Reads | None = None, available=None, held=None, gate=None) -> Iterator[Leg]:
    """Baseline search for composed wants: per part the gives that serve
    it, then every combination of distinct gives (at most `limit` per
    want, deterministic order) checked exactly."""
    from itertools import product as _product
    reads = reads_of(reads, available=available, held=held, gate=gate)
    offers = list(offers)
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    for w in sorted((o for o in offers if o.kind == WANT and o.composed),
                    key=lambda o: o.offer_id):
        per_part = [[g for g in gives
                     if _gates(g, w, ontology, now=now, thing=part, reads=reads)
                     and ontology.satisfies(g.thing.concepts, part.concepts)]
                    for part in w.parts]
        found = 0
        for combo in _product(*per_part):
            if len({g.offer_id for g in combo}) != len(combo):
                continue
            leg = check_parts(w, combo, ontology, now=now, reads=reads)
            if leg is not None:
                yield leg
                found += 1
                if found >= limit:
                    break


def composed_legs(offers: Iterable[Offer], ontology: Ontology, *, now: int, max_hops: int = 2,
                  reads: Reads | None = None, available=None, held=None, gate=None) -> Iterator[Leg]:
    """Baseline composition search: every want × every thing-give that does
    not already satisfy it × every chain of up to `max_hops` distinct
    operator gives, checked exactly — an operator is composed only where it
    is needed (a lesson at the door already serves a want anywhere in the
    city; moving it is not a leg), and a chain only where a shorter one
    does not reach (one courier who goes the whole way is not also
    proposed as two). Two couriers of one packet — shop to hub, hub to
    door — are a two-hop leg; the intermediate coordinate is where the
    first operator puts the thing down and the second picks it up
    (`P2-loop-selection.md` §10's open problem, closed for fixed hops).
    Polynomial in the book with the exponent `max_hops`, which the baseline
    accepts as the recall benchmark composing species must beat.
    Deterministic order."""
    from itertools import permutations
    reads = reads_of(reads, available=available, held=held, gate=gate)
    offers = list(offers)
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    wants = sorted((o for o in offers if o.kind == WANT and not o.composed),
                   key=lambda o: o.offer_id)
    ops = [g for g in gives
           if any(ontology.operator_of(c) for c in g.thing.concepts)
           and (ontology.ends(g.thing.concepts)
                or all(ontology.argument_only(ontology.operator_of(c))
                       for c in g.thing.concepts if ontology.operator_of(c)))]
    if not ops:
        return
    things = [g for g in gives if g not in ops]
    for w in wants:
        for thing in things:
            if check_match(thing, w, ontology, now=now, reads=reads) is not None:
                continue           # the thing already reaches: no operator needed
            reached = False
            for hops in range(1, max_hops + 1):
                if reached:
                    break          # a shorter chain reaches: no longer one
                for chain in permutations(ops, hops):
                    leg = check_composition(w, (thing, *chain), ontology, now=now, reads=reads)
                    if leg is not None:
                        reached = True
                        yield leg


def candidate_matches(offers: Iterable[Offer], ontology: Ontology, *, now: int,
                      reads: Reads | None = None, available=None, held=None,
                      gate=None) -> Iterator[Match]:
    """All feasible handoffs among `offers`.

    Prototype strategy: exact check over the give x want product, with the
    cheap constant-time conditions doing the pruning. This is
    O(gives*wants) and entirely adequate for books that fit in memory; the
    scaling path is `dimensions.candidate_matches_indexed` (the want's
    conjunction as one catalogue query), refined by this same exact
    check.
    """
    reads = reads_of(reads, available=available, held=held, gate=gate)
    gives = [o for o in offers if o.kind == GIVE]
    wants = [o for o in offers if o.kind == WANT and not o.composed]
    for g, w in product(gives, wants):
        m = check_match(g, w, ontology, now=now, reads=reads)
        if m is not None:
            yield m
