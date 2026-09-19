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
from fractions import Fraction
from itertools import product
from typing import Iterable, Iterator

from .ontology import Ontology
from .schema import GIVE, WANT, Offer, Thing, q


@dataclass(frozen=True, slots=True)
class Match:
    give: Offer   # the offer giving the thing
    want: Offer   # the offer receiving it

    @property
    def rate(self) -> Fraction:
        """(the wanter's quoted price) / (the giver's quoted price), exact (U9)."""
        return self.want.unit_price / self.give.unit_price

    @property
    def giver(self) -> str:
        return self.give.maker

    @property
    def receiver(self) -> str:
        return self.want.maker

    @property
    def qty(self) -> Fraction:
        return q(self.want.thing.qty)

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


def meets(mine: Offer, other: Offer, ontology: Ontology, *, taken=None, whole=None) -> bool:
    """Does `other`'s declaration meet `mine`'s requirement (v5; admissibility
    by declaration, `P3-release-and-reclearing.md` §5d)? The witness type and
    the escrow kind must be accepted; and when the neutral point is above
    zero, `other` must carry a deposit whose category falls under one my
    maker accepts (the catalogue decides, one-way: the deposit fits within
    the acceptance), in that entry's unit, whose quantity *reserved for this
    fill* — the deposit × taken / whole for a give, the whole deposit for a
    want — covers my point at my price for that asset. Two conversions each
    inside one maker's scale, one comparison in the asset's unit (U14). A
    point with no acceptance can be met by nothing: fail closed (U7)."""
    req = mine.requires
    if req is None or req.empty:
        return True
    if req.oracles and other.oracle not in req.oracles:
        return False
    if req.point == 0:
        return True
    bond = other.bond if other.v >= 5 else None
    if bond is None:
        return False
    if req.escrows and not bond.escrow:
        return False                    # an escrow is required and none holds the deposit
    share = bond.reserved(taken, whole) if taken is not None else q(bond.asset.qty)
    for acc in req.accepts:
        if acc.unit != bond.asset.unit:
            continue
        if not ontology.satisfies(bond.asset.concepts, acc.concepts):
            continue
        if share >= req.needed(acc):
            return True
    return False


def _gates(give: Offer, want: Offer, ontology: Ontology, *, now: int,
           quantity: bool = True, thing: Thing | None = None,
           available=None, taken=None) -> bool:
    """Everything `check_match` decides before meaning: kinds and makers,
    the record line, validity, the v1/v2 fields, quantity and unit (skipped
    for an operator give, which moves a lot rather than being one), pins.
    `thing` is the wanted thing when the want has parts (one gate per
    part); the want's one thing otherwise."""
    if give.kind != GIVE or want.kind != WANT or give.maker == want.maker:
        return False
    if (give.v >= 3) != (want.v >= 3):
        return False
    # admissibility by declaration (v5, 2026-09-18): each side's requirement
    # of a counterparty — a bond floor, accepted witness types — must be met
    # by the other side's declaration; unmet is refused, fail closed (U7)
    # the give's deposit is reserved per fill: the share for what this leg
    # takes (the wanted quantity, an aggregated share, or — an operator's run,
    # a whole give — everything); the want is taken whole
    wanted = thing if thing is not None else (None if want.composed else want.thing)
    give_taken = taken if taken is not None else \
        (q(wanted.qty) if (quantity and wanted is not None) else q(give.thing.qty))
    if not meets(want, give, ontology, taken=give_taken, whole=q(give.thing.qty)):
        return False
    if not meets(give, want, ontology):
        return False
    if not (give.valid.is_open_at(now) and want.valid.is_open_at(now)):
        return False
    if give.v < 3:
        if not give.service.overlaps(want.service):
            return False
        if not give.where.intersects(want.where):
            return False
    g = give.thing
    w = thing if thing is not None else (None if want.composed else want.thing)
    if w is None:
        return False                    # a composed want is met part by part
    if quantity:
        left = None if available is None else available.get(give.offer_id)
        if not g.takes(w.qty, left):    # within what is left, above the floor, on the step
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
                now: int, available=None) -> Match | None:
    """The exact pairwise check; returns a Match or None. A composed
    want is never met by one give: `check_parts`. `available` maps offer
    ids to what fills have left of them (`OfferRegistry.availability`);
    None means the whole quantity."""
    if want.composed or not _gates(give, want, ontology, now=now, available=available):
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
    #: An aggregated leg's shares (P2-loop-selection.md §10, the six lifters,
    #: 2026-09-14): what each give contributes to one want of one thing, the
    #: shares summing to the want's quantity. None for every other leg, whose
    #: quantities `taken` derives.
    quantities: tuple[Fraction, ...] | None = None

    @classmethod
    def from_match(cls, m: Match) -> "Leg":
        return cls(m.want, (m.give,))

    @property
    def parts(self) -> bool:
        """A leg of a composed want: give i serves part i."""
        return self.want.composed

    def taken(self, i: int) -> Fraction:
        """The quantity this leg takes from give `i`: a part's quantity
        for a composed want, the want's quantity for the thing of a simple
        or operator-composed leg, the whole run for an operator (it moves a
        lot rather than being one). What the fill records."""
        if self.quantities is not None:
            return self.quantities[i]
        if self.parts:
            return q(self.want.parts[i].qty)
        if i == 0:
            return q(self.want.thing.qty)
        return q(self.gives[i].thing.qty)

    def value_given(self, i: int) -> Fraction:
        """What give `i` is owed on its maker's scale: its unit price
        times the quantity taken."""
        return self.gives[i].unit_price * self.taken(i)

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
        """The sort key and the leg's identity under `loop_id`: the gives,
        the want, and for an aggregated leg the shares (the same gives split
        differently are a different clearing decision)."""
        base = f"{'+'.join(g.offer_id for g in self.gives)}>{self.want.offer_id}"
        if self.quantities is None:
            return base
        return base + "@" + ",".join(str(x) for x in self.quantities)


def check_composition(want: Offer, gives: Iterable[Offer], ontology: Ontology,
                      *, now: int, available=None) -> Leg | None:
    """The exact check of a composed leg (`P2-loop-selection.md` §10, the
    discovered form): the first give is the thing, every further give an
    operator — a give naming a category under `operator` (`transport`) and
    the two ends of a dimension it moves the thing along (`from`/`to` over
    geo). The thing must fit what the operator accepts — its argument, the
    operator's own want (`transport(small-item)`: the box goes, the piano
    does not; `Ontology.accepts`). Each operator's input must be comparable
    with the thing's coordinate as it stands (one contains the other, the
    handover rule), and its output replaces that coordinate; the thing so
    moved must then satisfy the want like any give. Every give passes
    `check_match`'s gates against the want (an operator without the
    quantity gate: it moves a lot rather than being one). Clearing re-runs
    this; nothing is trusted (U3)."""
    gives = tuple(gives)
    if not gives:
        return None
    thing, operators = gives[0], gives[1:]
    if not _gates(thing, want, ontology, now=now, available=available):
        return None
    derived = list(thing.thing.concepts)
    for op in operators:
        if not _gates(op, want, ontology, now=now, quantity=False):
            return None
        terms = [c for c in op.thing.concepts if ontology.operator_of(c)]
        moves = ontology.ends(op.thing.concepts)
        if not terms or not moves:
            return None                # not an operator give, or one that moves nothing
        if not ontology.accepts(thing.thing.concepts, terms):
            return None                # the operator does not take this thing
        for base, in_term, out_term in moves:
            here = ontology.coordinate(derived, base)
            if here is None:
                return None            # the thing states no such coordinate
            start = ontology.bare(in_term)
            if not (ontology.covers(start, here) or ontology.covers(here, start)):
                return None            # the operator cannot pick it up there
            derived.remove(here)
            derived.append(ontology.bare(out_term))
    if not ontology.satisfies(derived, want.thing.concepts):
        return None
    return Leg(want, gives)


def check_parts(want: Offer, gives: Iterable[Offer], ontology: Ontology,
                *, now: int, available=None) -> Leg | None:
    """The exact check of a composed want's leg (v4, `P2-loop-selection.md`
    §10's declared form): give `i` serves part `i` — the gates against
    that part (quantity on the give's step and floor, units, pins) and
    the containment `satisfies` — every give distinct, all or nothing.
    Clearing re-runs this (U3)."""
    gives = tuple(gives)
    if not want.composed or len(gives) != len(want.parts):
        return None
    if len({g.offer_id for g in gives}) != len(gives):
        return None
    for g, part in zip(gives, want.parts):
        if not _gates(g, want, ontology, now=now, thing=part, available=available):
            return None
        if not ontology.satisfies(g.thing.concepts, part.concepts):
            return None
    return Leg(want, gives)


def check_aggregate(want: Offer, gives: Iterable[Offer], quantities: Iterable,
                    ontology: Ontology, *, now: int, available=None) -> Leg | None:
    """The exact check of an aggregated leg (`P2-loop-selection.md` §10, the
    six lifters, 2026-09-14): one want of one thing met by several gives of
    it, each contributing a share — every give passes the gates against the
    want but for quantity, satisfies its concepts, has its unit, and may
    give its share (`Thing.takes`, within what is left of it); the shares
    sum to the want's quantity. Clearing re-runs this (U3)."""
    gives, quantities = tuple(gives), tuple(q(x) for x in quantities)
    if want.composed or len(gives) < 2 or len(gives) != len(quantities):
        return None
    if len({g.offer_id for g in gives}) != len(gives):
        return None
    if sum(quantities, Fraction(0)) != q(want.thing.qty):
        return None
    for g, share in zip(gives, quantities):
        if not _gates(g, want, ontology, now=now, quantity=False, taken=share):
            return None
        left = None if available is None else available.get(g.offer_id)
        if g.thing.unit != want.thing.unit or not g.thing.takes(share, left):
            return None
        if not ontology.satisfies(g.thing.concepts, want.thing.concepts):
            return None
    return Leg(want, gives, quantities)


def aggregate_legs(offers: Iterable[Offer], ontology: Ontology, *, now: int,
                   available=None, max_gives: int = 6,
                   max_alternatives: int = 8) -> Iterator[Leg]:
    """Baseline aggregation search: for every simple want no single give
    serves, the gives of its thing in id order, each contributing a share it
    may give — the most first (its whole remainder, or the largest multiple
    of its step within what the want still needs), then smaller multiples,
    never below its floor — depth-first until the shares sum to the want's
    quantity: the first such set, at most `max_gives` gives, checked
    exactly. Deterministic (U6); polynomial only because the pool and the
    alternatives per give are bounded — the recall benchmark a smarter
    aggregating species must beat."""
    offers = list(offers)
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    for w in sorted((o for o in offers if o.kind == WANT and not o.composed),
                    key=lambda o: o.offer_id):
        if any(check_match(g, w, ontology, now=now, available=available) for g in gives):
            continue                   # one give reaches: nothing to add up
        pool = [g for g in gives
                if _gates(g, w, ontology, now=now, quantity=False)
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
            leg = check_aggregate(w, found[0], found[1], ontology, now=now, available=available)
            if leg is not None:
                yield leg


def parts_legs(offers: Iterable[Offer], ontology: Ontology, *, now: int,
               limit: int = 64, available=None) -> Iterator[Leg]:
    """Baseline search for composed wants: per part the gives that serve
    it, then every combination of distinct gives (at most `limit` per
    want, deterministic order) checked exactly."""
    from itertools import product as _product
    offers = list(offers)
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    for w in sorted((o for o in offers if o.kind == WANT and o.composed),
                    key=lambda o: o.offer_id):
        per_part = [[g for g in gives
                     if _gates(g, w, ontology, now=now, thing=part, available=available)
                     and ontology.satisfies(g.thing.concepts, part.concepts)]
                    for part in w.parts]
        found = 0
        for combo in _product(*per_part):
            if len({g.offer_id for g in combo}) != len(combo):
                continue
            leg = check_parts(w, combo, ontology, now=now, available=available)
            if leg is not None:
                yield leg
                found += 1
                if found >= limit:
                    break


def composed_legs(offers: Iterable[Offer], ontology: Ontology, *,
                  now: int, max_hops: int = 2, available=None) -> Iterator[Leg]:
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
    offers = list(offers)
    gives = sorted((o for o in offers if o.kind == GIVE), key=lambda o: o.offer_id)
    wants = sorted((o for o in offers if o.kind == WANT and not o.composed),
                   key=lambda o: o.offer_id)
    ops = [g for g in gives
           if any(ontology.operator_of(c) for c in g.thing.concepts)
           and ontology.ends(g.thing.concepts)]
    if not ops:
        return
    things = [g for g in gives if g not in ops]
    for w in wants:
        for thing in things:
            if check_match(thing, w, ontology, now=now, available=available) is not None:
                continue           # the thing already reaches: no operator needed
            reached = False
            for hops in range(1, max_hops + 1):
                if reached:
                    break          # a shorter chain reaches: no longer one
                for chain in permutations(ops, hops):
                    leg = check_composition(w, (thing, *chain), ontology, now=now,
                                            available=available)
                    if leg is not None:
                        reached = True
                        yield leg


def candidate_matches(offers: Iterable[Offer], ontology: Ontology, *,
                      now: int, available=None) -> Iterator[Match]:
    """All feasible handoffs among `offers`.

    Prototype strategy: exact check over the give x want product, with the
    cheap constant-time conditions doing the pruning. This is
    O(gives*wants) and entirely adequate for books that fit in memory; the
    scaling path is `dimensions.candidate_matches_indexed` (the want's
    conjunction as one catalogue query), refined by this same exact
    check.
    """
    gives = [o for o in offers if o.kind == GIVE]
    wants = [o for o in offers if o.kind == WANT and not o.composed]
    for g, w in product(gives, wants):
        m = check_match(g, w, ontology, now=now, available=available)
        if m is not None:
            yield m
