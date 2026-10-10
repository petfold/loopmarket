"""One matching engine (the 2026-10 review's item 2, decided by Peter
2026-10-10, option A): the ontodag index supplies the candidates of the
simple matches, of the aggregation search, and of the parts and composed
searches where they pair gives with wants; the give x want product stays
only as the oracle these tests compare against (`tests/oracle.py`).

Over random books — every record version the matcher serves; categories,
places, regions, routes, times, operators, unknown words and conjunctions
that describe nothing; what fills left of a give, what the escrow holds, a
counterparty gate with holds, withdrawals and item claims — each search
finds exactly what the product finds, in the same order."""

import functools
import random
import zlib
from fractions import Fraction

import pytest
from ontodag import OntoDAG

import oracle
from loopmarket import (Accept, Acceptance, Bond, Credential, Offer, Ontology, Parts, Requires, Thing,
                        TimeWindow, give, want)
from loopmarket.dimensions import DimensionIndex, candidate_matches_indexed
from loopmarket.gate import CounterpartyGate
from loopmarket.items import natural_id
from loopmarket.matching import aggregate_legs, candidate_matches, composed_legs, parts_legs
from loopmarket.reads import Reads
from loopmarket.schema import q

NOW = 5_000
EUR = Acceptance(("stablecoin-eur",), "EUR", 1)
CATEGORIES = {
    "goods": [], "produce": ["goods"], "small-item": ["goods"],
    "vegetable-box": ["produce", "small-item"], "fruit-box": ["produce", "small-item"],
    "apple": ["produce"], "piano": ["goods"], "parcel": ["small-item"],
    "service": [], "lesson": ["service"], "piano-lesson": ["lesson"], "repair": ["service"],
    "lifting": ["service"], "money": [], "stablecoin-eur": ["money"], "venue": [],
}
#: what a give is (narrow), what a want asks for (mostly broad)
GIVE_THINGS = ["vegetable-box", "fruit-box", "apple", "piano", "parcel", "piano-lesson", "repair", "lifting"]
BROAD = ["goods", "produce", "small-item", "service", "lesson"]
WANT_THINGS = GIVE_THINGS + BROAD + ["venue"]
CELLS = ["u2e", "u2e4", "u2e4x", "u2e5", "u2f", "u2f1"]
PLACES = ["my_home", "ljubljana", "market"]
ITEMS = [natural_id("serial", s) for s in ("a-1", "b-2")]
MAKERS = [f"m{i}" for i in range(12)]


def catalogue() -> Ontology:
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo", "depart": "time"})
    cat.declare_handover(["geo", "time"])
    cat.declare_operator({"transport": ("from", "to")})
    cat.declare_argument_operator(["insure"])
    cat.declare_item_heads()
    cat.dag.put("made_in", ["geo"])
    cat.declare_descriptive(["made_in"])
    cat.load(dict(CATEGORIES))
    cat.dag.put("my_home", ["geo(u2e4x)"])         # a place under a cell
    cat.dag.put("ljubljana", ["geo"])              # a region above two cells
    cat.dag.put("geo(u2e4)", ["ljubljana"])
    cat.dag.put("geo(u2e5)", ["ljubljana"])
    cat.dag.put("market", ["geo(u2f1)", "venue"])  # a place filed under a category as well
    return cat


def _iso(t: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _where(rng) -> str:
    """A handover place: a bare cell, a place under one, or a region."""
    pick = rng.choice(CELLS + PLACES)
    return pick if pick in PLACES else f"geo({pick})"


def _concepts(rng, wanted: bool) -> list[str]:
    """What a thing is, and maybe where and when it changes hands, what it
    is made of, which item it is, a word nobody knows; a want asks for
    less than a give says."""
    if wanted:
        terms = [rng.choice(BROAD) if rng.random() < 0.6 else rng.choice(WANT_THINGS)]
        if rng.random() < 0.1:
            terms.append(rng.choice(WANT_THINGS))  # two things at once: met only by one under both
    else:
        terms = [rng.choice(GIVE_THINGS)]
    if rng.random() < (0.35 if wanted else 0.6):
        terms.append(_where(rng))
        if rng.random() < 0.08:                    # a second place, often disjoint: describes nothing
            terms.append(_where(rng))
    for head in ("from", "to"):
        if rng.random() < (0.05 if wanted else 0.15):
            terms.append(f"{head}({rng.choice(CELLS + PLACES)})")
    if rng.random() < (0.04 if wanted else 0.12):
        a = 1_800_000_000 + rng.randrange(0, 3600)
        terms.append(f"depart({_iso(a)}..{_iso(a + rng.randrange(60, 3600))})")
    if rng.random() < (0.04 if wanted else 0.15):
        terms.append(f"made_in({rng.choice(CELLS)})")
    if rng.random() < 0.04:
        terms.append(f"item({rng.choice(ITEMS)})")
    if rng.random() < 0.04:
        terms.append("mystery-goods")              # unknown: narrows a give, closes a want (U7)
    return terms


def _operator(rng, wanted: bool) -> list[str]:
    """A courier's run (`transport`, maybe an argument, from and to: mostly
    out of the u2e area into the u2f one), cover (`insure(...)`), or a want
    of either; an argument may be one the catalogue cannot read."""
    if rng.random() < 0.2:
        return [rng.choice(["insure(produce)", "insure(small-item)", "insure(piano)"])]
    terms = [rng.choice(["transport", "transport", "transport(small-item)", "transport(goods)",
                         "transport(produce)", "transport(piano)", "transport(mystery-goods)"])]
    if not wanted or rng.random() < 0.5:
        terms += [f"from({rng.choice(['u2e', 'u2e4', 'my_home', 'ljubljana', 'u2f'])})",
                  f"to({rng.choice(['u2f', 'u2f1', 'market', 'u2e', 'u2e5'])})"]
    return terms


def _thing(rng, concepts, v, wanted: bool) -> Thing:
    qty = rng.choice([1, 1, 1, 2, 4, 6]) if wanted else rng.choice([1, 2, 3, 3, 4])
    unit = "unit" if rng.random() < 0.94 else "kg"
    if v == 3:
        return Thing(tuple(concepts), qty, unit, divisible=rng.random() < 0.5)
    step = rng.choice([None, 0, 1, 1])
    floor = 1 if step == 1 and qty > 1 and rng.random() < 0.3 else 0
    return Thing(tuple(concepts), qty, unit, step=step, min=floor)


def _guarantees(rng, v, giving: bool, gives_so_far, maker) -> dict:
    """The fields that make an offer v5, v6 or v7: deposits, requirements of
    a counterparty, claim periods, options, a deductible."""
    kw: dict = {}
    if v == 5:
        if giving:
            if rng.random() < 0.7:
                kw["bond"] = Bond(Thing(("stablecoin-eur",), rng.choice([10, 40]), "EUR"),
                                  rng.choice([10, 40]), rng.choice(["0xE", ""]))
            else:
                kw["requires"] = Requires(oracles=("countersign",))
        else:
            kw["requires"] = Requires(point=rng.choice([0, 0, 5]), accepts=(EUR,),
                                      escrows=rng.choice([(), (), ("contract",)]))
    elif v == 6:
        if giving:
            kw["claim_max"] = rng.choice([3600, 3600, 1])
            mine = [g for g in gives_so_far if g.maker == maker and not g.underlying]
            if mine and rng.random() < 0.4:      # an option on one of my gives
                kw.update(underlying=mine[-1].offer_id, exercise=TimeWindow(NOW, NOW + 100))
        else:
            kw["requires"] = rng.choice([
                Requires(claim_period=1800), Requires(claim_period=1800),
                Requires(resolvers=Accept(keys=(rng.choice(MAKERS),))),
                Requires(resolvers=Accept(keys=(rng.choice(MAKERS),))),
                Requires(counterparty=(Credential("licence", ("attested",)),)),   # no statements: fails closed
            ])
    elif v == 7 and giving:
        kw["bond"] = Bond(Thing(("stablecoin-eur",), 40, "EUR"), 40, "0xE", deductible=rng.choice([1, 5]))
    return kw


def _pins(rng) -> dict:
    """Mostly none (the test catalogue is unpinned); sometimes this
    ontodag's versions, sometimes another major's (refused, review item 4)."""
    import ontodag
    from ontodag import dimensions
    r = rng.random()
    if r < 0.92:
        return {}
    if r < 0.97:
        return dict(registry_version=dimensions.REGISTRY_VERSION, contract_version=ontodag.CONTRACT_VERSION)
    return dict(registry_version="99.0", contract_version=ontodag.CONTRACT_VERSION)


def random_book(seed: int, n: int = 60) -> list[Offer]:
    rng = random.Random(seed)
    offers: list[Offer] = []
    gives: list[Offer] = []
    for i in range(n):
        maker = rng.choice(MAKERS)
        giving = rng.random() < 0.55
        v = rng.choices([3, 4, 5, 6, 7], weights=[15, 35, 25, 15, 10])[0]
        if v == 7 and not giving:
            v = 4                                # a deductible is a give's
        concepts = _operator(rng, not giving) if rng.random() < 0.15 else _concepts(rng, not giving)
        valid = TimeWindow(0, 1_000_000) if rng.random() < 0.95 else TimeWindow(0, NOW - 1)
        kw = dict(valid=valid, nonce=i, v=v, **_pins(rng), **_guarantees(rng, v, giving, gives, maker))
        price = 10 + rng.randrange(90)
        if giving:
            offer = give(maker, _thing(rng, concepts, v, False), price, **kw)
            gives.append(offer)
        elif v >= 4 and rng.random() < 0.15:     # a composed want: two things together
            offer = want(maker, Parts((_thing(rng, _concepts(rng, True), v, True),
                                       _thing(rng, _concepts(rng, True), v, True))), price, **kw)
        else:
            offer = want(maker, _thing(rng, concepts, v, True), price, **kw)
        offers.append(offer)
    return offers


def _h(*parts) -> int:
    return zlib.crc32("|".join(parts).encode())


def random_reads(offers, seed: int) -> Reads:
    """What fills left of some gives, what the escrow holds behind some
    deposits, and a gate over the book whose holds, withdrawals and item
    claims fall where a hash puts them — so the filters are pair by pair."""
    rng = random.Random(seed)
    by_id = {o.offer_id: o for o in offers}
    available = {o.offer_id: q(rng.choice([0, 1, 2, 3, o.thing.qty])) for o in offers
                 if o.kind == "give" and rng.random() < 0.4}
    held = {o.offer_id: q(rng.choice([0, 20, 40])) for o in offers
            if o.v >= 5 and o.bond is not None and o.bond.escrow and rng.random() < 0.7}

    def capacity(oid):
        o = by_id.get(oid)
        if o is None or o.composed:
            return None
        return available.get(oid, q(o.thing.qty))

    gate = CounterpartyGate(statements=lambda subject: [], registers={}, now=NOW, offer=by_id.get, held=held,
                            held_by=lambda oid, holder: Fraction(_h(oid, holder) % 5 == 0),
                            capacity=capacity, withdrawn=lambda oid: _h(oid) % 13 == 0,
                            item_claimed=lambda h, maker, oid: _h(h, maker) % 3 == 0)
    return Reads(available=available, held=held, gate=gate)


def _keys(legs) -> list[str]:
    return [leg.key for leg in legs]


def _pairs(matches) -> list[tuple[str, str]]:
    return [(m.give.offer_id, m.want.offer_id) for m in matches]


SEEDS = range(6)


def _book(seed: int, with_reads: bool):
    offers = random_book(seed)
    return catalogue(), offers, random_reads(offers, seed) if with_reads else None


@functools.lru_cache(maxsize=None)
def expected(seed: int, with_reads: bool) -> dict:
    """What the give x want product finds in one book, computed once."""
    cat, offers, reads = _book(seed, with_reads)
    matches = list(oracle.candidate_matches(offers, cat, now=NOW, reads=reads))
    return {"matches": _pairs(matches),
            "versions": {m.give.v for m in matches} | {m.want.v for m in matches},
            "aggregate": _keys(oracle.aggregate_legs(offers, cat, now=NOW, reads=reads)),
            "parts": _keys(oracle.parts_legs(offers, cat, now=NOW, reads=reads)),
            "composed": _keys(oracle.composed_legs(offers, cat, now=NOW, reads=reads))}


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("with_reads", [False, True])
def test_every_search_finds_what_the_product_finds(seed, with_reads):
    """One index for the four searches, as a solver's pass shares it."""
    cat, offers, reads = _book(seed, with_reads)
    product = expected(seed, with_reads)
    index = DimensionIndex(cat)
    assert _pairs(candidate_matches(offers, cat, now=NOW, reads=reads, index=index)) == product["matches"]
    assert _keys(aggregate_legs(offers, cat, now=NOW, reads=reads, index=index)) == product["aggregate"]
    assert _keys(parts_legs(offers, cat, now=NOW, reads=reads, index=index)) == product["parts"]
    assert _keys(composed_legs(offers, cat, now=NOW, reads=reads, index=index)) == product["composed"]
    if reads is None:          # the index's own generator, compared as sets: it once had its own order
        assert sorted(_pairs(candidate_matches_indexed(offers, cat, now=NOW))) == sorted(product["matches"])


def test_the_books_exercise_every_search():
    """The comparisons above mean something only if the books are not
    trivial: across the seeds the product finds matches of every record
    version the matcher serves and legs of every kind, and the reads take
    some matches away."""
    found = {kind: sum(len(expected(seed, False)[kind]) for seed in SEEDS)
             for kind in ("matches", "aggregate", "parts", "composed")}
    found["taken away by the reads"] = sum(len(set(expected(seed, False)["matches"])
                                               - set(expected(seed, True)["matches"])) for seed in SEEDS)
    assert all(found.values()), found
    versions = set().union(*(expected(seed, False)["versions"] for seed in SEEDS))
    assert versions == {3, 4, 5, 6, 7}, versions


def test_the_cases_where_the_index_and_the_product_once_differed():
    """A book of the cases the random ones meet too rarely to be relied on.
    A want of `transport(mystery-goods)` names a word nobody knows: the
    index never gave it a candidate, while the product let a courier who
    takes anything meet it, until U7 closed that. A box at two places that
    share no point is never filed, and the product composed it with two
    couriers until the composition refused a thing that describes nothing.
    A want of a `venue` is answered by a move to `market`, a place filed
    under a cell and under `venue`: the thing is not inside `venue`, so the
    composed search leaves that term out of the want's query. And an offer
    listed twice is met twice, as the product meets it."""
    cat = catalogue()
    v = dict(valid=TimeWindow(0, 1_000_000))
    anything = give("c1", Thing(("transport", "from(u2e)", "to(market)")), 2, **v)
    east = give("c2", Thing(("transport", "from(u2e4)", "to(u2f1)")), 2, **v)
    west = give("c3", Thing(("transport", "from(u2e5)", "to(u2f1)")), 2, **v)
    unknown_word = want("w1", Thing(("transport(mystery-goods)",)), 5, **v)
    nowhere = give("g1", Thing(("vegetable-box", "geo(u2e4)", "geo(u2e5)")), 5, **v)
    at_cell = want("w2", Thing(("produce", "geo(u2f1)")), 9, **v)
    piano = give("g2", Thing(("piano", "geo(u2e4x)")), 50, **v)
    at_venue = want("w3", Thing(("piano", "venue")), 70, **v)
    box = give("g3", Thing(("vegetable-box",)), 5, **v)
    produce = want("w4", Thing(("produce",)), 9, **v)
    offers = [anything, east, west, unknown_word, nowhere, at_cell, piano, at_venue, box, produce, box]
    matched = _pairs(candidate_matches(offers, cat, now=NOW))
    assert matched == _pairs(oracle.candidate_matches(offers, cat, now=NOW))
    for engine, product in ((aggregate_legs, oracle.aggregate_legs), (parts_legs, oracle.parts_legs),
                            (composed_legs, oracle.composed_legs)):
        assert _keys(engine(offers, cat, now=NOW)) == _keys(product(offers, cat, now=NOW))
    assert matched == [(box.offer_id, produce.offer_id)] * 2
    composed = [(leg.gives, leg.want) for leg in composed_legs(offers, cat, now=NOW)]
    assert ((piano, anything), at_venue) in composed
    assert not any(gives[0] == nowhere for gives, _ in composed)


def _record(v: int, maker: str, kind: str, concepts, qty, amount, nonce: int, service, where) -> Offer:
    """A v1 or v2 offer as an old book holds it — its window and disc are
    fields, not terms — read back from its record."""
    thing = {"type": "thing", "concepts": sorted(concepts), "qty": qty, "unit": "unit", "divisible": qty > 1}
    tokens = {"type": "tokens", "issuer": maker, "amount": amount}
    rec = {"v": v, "maker": maker, "gives": thing if kind == "give" else tokens,
           "wants": tokens if kind == "give" else thing, "valid": [0, 1_000_000], "ontology_root": "",
           "bond": 0.0, "oracle": "countersign", "arbitrator": "", "nonce": nonce,
           "service": list(service), "where": list(where)}
    if v == 2:
        rec.update(registry_version="", contract_version="")
    return Offer.from_record(rec)


def old_book(seed: int, n: int = 36) -> list[Offer]:
    rng = random.Random(seed)
    offers = []
    for i in range(n):
        kind = "give" if rng.random() < 0.55 else "want"
        concepts = [rng.choice(GIVE_THINGS if kind == "give" else WANT_THINGS)]
        start = rng.randrange(0, 150_000)
        offers.append(_record(rng.choice([1, 2]), rng.choice(MAKERS), kind, concepts, rng.choice([1, 2, 4]),
                              10 + rng.randrange(90), 50_000 + i, (start, start + rng.randrange(600, 90_000)),
                              (45 + rng.random() * 2, 13 + rng.random() * 2, rng.choice([2_000, 20_000, 80_000]))))
    return offers


@pytest.mark.parametrize("seed", range(3))
def test_v1_and_v2_records_too(seed):
    """v1 and v2 records, read back as old books hold them, are retired:
    never filed and never asked, as the exact checks match none of them; on
    a book mixing them with v3 and later every search finds what the
    product finds."""
    cat = catalogue()
    offers = old_book(seed) + random_book(seed, n=24)
    product = _pairs(oracle.candidate_matches(offers, cat, now=NOW))
    assert _pairs(candidate_matches(offers, cat, now=NOW)) == product
    for engine, search in ((aggregate_legs, oracle.aggregate_legs), (parts_legs, oracle.parts_legs),
                           (composed_legs, oracle.composed_legs)):
        assert _keys(engine(offers, cat, now=NOW)) == _keys(search(offers, cat, now=NOW))
