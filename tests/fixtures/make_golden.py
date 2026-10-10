"""The golden corpus: book records exactly as loopmarket wrote them.

`golden_records.txt`, beside this script, holds one record per line: its
key in the book, a tab, and the record's canonical bytes, each under a
comment that says what it is. It holds offer records of every version, v1
to v7, under the id each got; `loop/` records of each shape books hold
(the 2026-08 loop record, whose legs name one `give`, and loop record v1
and v2, whose legs name their `gives` and what was `taken`); and the
`fill/` records written with them, of `{"loop"}` alone and with
quantities. Each scenario is written as the code of its time wrote it:
the offers by the constructors, the loops by `BookClearing`, and what
nothing writes any more, the v1 and v2 offers and the 2026-08 loop
record, by the encodings spelled out below. Every book is in memory with
fixed nonces and clocks, so the same code writes the same file.

`tests/test_golden_records.py` reads every record back, recomputes its id
and re-encodes it to the same bytes. If that fails, a change would make
old books unreadable, or move ids that loops, fills, signatures and the
chain already name (U2). **Never regenerate the file to make that test
pass.** Regenerate it only together with a deliberate change of the
record format, a new version or a new record shape, and let the diff be
the review: a record added is the change; a record changed or gone breaks
U2, and is decided as that.

    python3 tests/fixtures/make_golden.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))        # a checkout runs as it is

from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore, canonical_bytes

from loopmarket import (
    Accept, Acceptance, Bond, BookClearing, Credential, Leg, Loop, LoopProposal, Match,
    Offer, OfferRegistry, Ontology, Parts, RequiredLeg, Requires, SolverAgent, Thing,
    TimeWindow, find_circulations, give, want,
)
from loopmarket.matching import candidate_matches, composed_legs

FIXTURE = os.path.join(HERE, "golden_records.txt")
DAY = 86_400
AUG = 1_785_542_400            # 2026-08-01T00:00Z
SEP = 1_788_220_800            # 2026-09-01T00:00Z


class Corpus:
    """The records in the order they are written, each under its label."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.data: dict[str, bytes] = {}

    def section(self, text: str) -> None:
        self.lines += ["", *(f"# {line}".rstrip() for line in text.strip().splitlines())]

    def add(self, key: str, record, label: str) -> None:
        data = canonical_bytes(record)
        if key in self.data:
            if self.data[key] != data:
                raise ValueError(f"two different records under {key}")
            return
        self.data[key] = data
        self.lines += [f"# {label}", f"{key}\t{data.decode('utf-8')}"]

    def book(self, book: OfferRegistry) -> None:
        """Every record of a book: its offers, then each loop and its fills."""
        for key, rec in book.store.items("offer/"):
            self.add(key, rec, _offer_label(book.get(key[len("offer/"):])))
        for key, rec in book.store.items("loop/"):
            shape = f"loop record v{rec['v']}" if "v" in rec else "the 2026-08 loop record"
            self.add(key, rec, f"{shape}: {len(rec['legs'])} legs, {', '.join(rec['nodes'])}")
            for fkey, frec in book.store.items("fill/"):
                if frec.get("loop") == key[len("loop/"):]:
                    oid, _, part = fkey[len("fill/"):].partition("/")
                    what = "partial fill" if part else "fill"
                    self.add(fkey, frec, f"{what}: {_offer_label(book.get(oid))}")

    def write(self, path: str) -> None:
        head = [
            "# The golden corpus of book records: KEY, a tab, the record's canonical bytes.",
            "# Written by tests/fixtures/make_golden.py, read by tests/test_golden_records.py.",
            "# Never regenerate it to make a test pass: the script's docstring says when.",
        ]
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(head + self.lines) + "\n")


def _offer_label(o) -> str:
    what = " + ".join(" ".join(p.concepts) for p in o.parts)
    return f"v{o.v} {o.kind} by {o.maker}: {what}"


def _book(offers) -> OfferRegistry:
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many(offers)
    book.commit()
    return book


def _clear(book, cat, now) -> None:
    """One pass of the baseline solver, every proposal cleared."""
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=BookClearing(book, cat, clock=lambda: now), solver_id="t")
    receipts = agent.step(now=now)
    if not receipts or not all(r.accepted for r in receipts):
        raise RuntimeError(f"the scenario did not clear: {receipts}")


def _record_of_2026_08(book, offers, *, solver, found_at) -> None:
    """The triangle cleared as `MockClearing` cleared a simple cycle from
    2026-08-21 to 2026-09-14 (commits e0e996d to 8bbec7c): the loop record
    of that time, without a version, one `give` per leg, the rate and the
    surplus as floats computed from the record's own numbers, the legs in
    the order that solver found them; and a fill of `{"loop"}` alone for
    every offer."""
    amara, amara_w, bruno, bruno_w, chen, chen_w = offers
    matches = [Match(amara, chen_w), Match(chen, bruno_w), Match(bruno, amara_w)]
    loop = Loop(tuple(matches))

    def unit_price(o):
        return o.tokens.amount / o.thing.qty

    rates = [unit_price(m.want) / unit_price(m.give) for m in matches]
    product = 1.0
    for r in rates:
        product *= r
    record = {
        "loop_id": loop.loop_id, "solver": solver, "found_at": found_at,
        "book_root": book.store.root, "ontology_root": "", "surplus": product - 1.0,
        "nodes": list(loop.nodes),
        "legs": [{"give": m.give.offer_id, "want": m.want.offer_id, "rate": r}
                 for m, r in zip(matches, rates)],
    }
    book.mark_filled(loop.offer_ids, loop.loop_id, record)
    book.commit()


# ------------------------------------------------------------------ v1, v2, v3

def old_offer(v, maker, kind, concepts, amount, *, qty=1.0, unit="unit", divisible=False,
              service, where, valid, nonce, ontology_root="", bond=0.0, oracle="countersign",
              arbitrator="", registry_version="", contract_version="") -> Offer:
    """A v1 or v2 offer, which no constructor makes any more (the review's
    item 12): its record as the constructors of 2026-07-29 (v1) and
    2026-08-20 (v2) wrote it, read back as a reader of an old book reads
    it. A thing of those versions carries its quantity and `divisible`;
    `service` and `where` are fields, a window and a disc."""
    thing = {"type": "thing", "concepts": sorted(set(concepts)), "qty": qty, "unit": unit,
             "divisible": divisible}
    tokens = {"type": "tokens", "issuer": maker, "amount": amount}
    rec = {"v": v, "maker": maker, "gives": thing if kind == "give" else tokens,
           "wants": tokens if kind == "give" else thing, "valid": valid,
           "service": service, "where": where, "ontology_root": ontology_root, "bond": bond,
           "oracle": oracle, "arbitrator": arbitrator, "nonce": nonce}
    if v == 2:
        rec.update(registry_version=registry_version, contract_version=contract_version)
    return Offer.from_record(rec)


def triangle(v: int):
    """The demo triangle as `examples/demo_triangle.py` published it in v1
    and v2: the service window and the disc are fields."""
    t = AUG if v == 1 else AUG + 21 * DAY
    town = dict(service=[t, t + 120 * DAY], valid=[t - 3_600, t + 30 * DAY], unit="course")
    flat, farm, shop = [46.05, 14.50, 5_000], [46.10, 14.55, 15_000], [46.06, 14.51, 4_000]
    n = t * 1000
    return [
        old_offer(v, "amara", "give", ["piano-lesson"], 100, where=flat, nonce=n + 1, **town),
        old_offer(v, "amara", "want", ["produce", "local", "weekly"], 104, where=flat, nonce=n + 2, **town),
        old_offer(v, "bruno", "give", ["vegetable-box"], 50, where=farm, nonce=n + 3, **town),
        old_offer(v, "bruno", "want", ["bicycle-repair"], 52, where=farm, nonce=n + 4, **town),
        old_offer(v, "chen", "give", ["bicycle-repair"], 80, where=shop, nonce=n + 5, **town),
        old_offer(v, "chen", "want", ["music-lesson"], 83, where=shop, nonce=n + 6, **town),
    ]


def v1_and_v2(corpus: Corpus) -> None:
    corpus.section("""
v1 (2026-07-29): the demo triangle, and an offer using every other v1 field.
The loop records of that time named their legs `ask` and `bid`, a shape
nothing has read since 2026-08-21, so none is here.""")
    t = AUG + 5 * DAY
    odd = old_offer(1, "dora", "want", ["produce", "fruit-box"], 37.5, qty=2.5, unit="kg",
                    divisible=True, service=[t, t + 7 * DAY], where=[-33.87, 151.21, 2_500.5],
                    valid=[t - DAY, t + 14 * DAY], bond=5.0, oracle="photo", arbitrator="arb-1",
                    ontology_root="ab" * 32, nonce=t * 1000 + 7)
    corpus.book(_book([*triangle(1), odd]))

    corpus.section("""
v2 (2026-08-20): the demo triangle, cleared under the 2026-08 loop record
(no version, one `give` per leg, floats) with fills of `{"loop"}` alone;
and an offer that pins the registry and the contract.""")
    offers = triangle(2)
    book = _book(offers)
    _record_of_2026_08(book, offers, solver="demo-solver", found_at=AUG + 21 * DAY + 60)
    corpus.book(book)
    t = AUG + 25 * DAY
    pinned = old_offer(2, "emil", "give", ["bicycle-repair", "local"], 120, qty=2, unit="visit",
                       service=[t, t + 30 * DAY], where=[46.05, 14.5, 12_000],
                       valid=[t, t + 30 * DAY], ontology_root="cd" * 32,
                       registry_version="1.0", contract_version="0.1", nonce=t * 1000 + 1)
    corpus.book(_book([pinned]))


def v3(corpus: Corpus) -> None:
    corpus.section("""
v3 (2026-09-12): where and when are terms in the conjunction, and `valid`
may be open-ended. The triangle again, under the 2026-08 loop record, which
a simple cycle was cleared under until 2026-09-14; and a divisible give.""")
    town = dict(valid=TimeWindow(SEP + 11 * DAY), v=3)
    season = "time(2026-09-12..2026-12-31)"
    flat, area = "geo(u2e4x)", "geo(u2e4)"
    n = (SEP + 12 * DAY) * 1000
    offers = [
        give("amara", Thing(("piano-lesson", flat, season), unit="course"), 100, nonce=n + 1, **town),
        want("amara", Thing(("produce", "local", "weekly", flat, season), unit="course"), 104, nonce=n + 2, **town),
        give("bruno", Thing(("vegetable-box", flat, season), unit="course"), 50, nonce=n + 3, **town),
        want("bruno", Thing(("bicycle-repair", area, season), unit="course"), 52, nonce=n + 4, **town),
        give("chen", Thing(("bicycle-repair", flat, season), unit="course"), 80, nonce=n + 5, **town),
        want("chen", Thing(("music-lesson", flat, season), unit="course"), 83, nonce=n + 6, **town),
    ]
    book = _book(offers)
    _record_of_2026_08(book, offers, solver="t", found_at=SEP + 12 * DAY + 60)
    corpus.book(book)
    t = SEP + 13 * DAY
    corpus.book(_book([give("fern", Thing(("apple", "geo(u2e4)"), 2.0, "kg", divisible=True), 5,
                            valid=TimeWindow(t, t + 10 * DAY), nonce=t * 1000 + 1, v=3)]))


# ------------------------------------------------------------------------- v4

def v4(corpus: Corpus) -> None:
    corpus.section("""
v4 (2026-09-14): exact numbers as n/d strings, `step` and `min` in place of
`divisible`, and a want of several parts. Loop record v1: the composed
want's leg takes two of the theatre's ten tickets (a partial fill), and
the fills name every give and its quantity.""")
    now = SEP + 15 * DAY
    v = dict(valid=TimeWindow(now - DAY, now + 30 * DAY))
    cat = Ontology(OntoDAG()).load({"ticket": [], "transport": [], "lesson": []})
    evening = want("buyer", Parts((Thing(("ticket",), 2), Thing(("transport",), 1))), 60, nonce=1, **v)
    book = _book([
        evening,
        give("theatre", Thing(("ticket",), 10, step=1), 200, nonce=2, **v),
        give("driver", Thing(("transport",)), 15, nonce=3, **v),
        give("buyer", Thing(("lesson",)), 30, nonce=4, **v),
        give("buyer", Thing(("lesson",)), 30, nonce=5, **v),
        want("theatre", Thing(("lesson",)), 42, nonce=6, **v),
        want("driver", Thing(("lesson",)), 31, nonce=7, **v),
    ])
    _clear(book, cat, now)
    corpus.book(book)

    corpus.section("""
Loop record v1: a composed leg, the courier's run moving the box from the
shop to the door; the run is taken whole.""")
    cat = Ontology(OntoDAG())
    cat.declare_roles({"from": "geo", "to": "geo"})
    cat.declare_handover(["geo", "time"])
    cat.declare_operator({"transport": ("from", "to")})
    cat.load({"vegetable-box": [], "transport": [], "bicycle-repair": [], "piano-lesson": []})
    cat.dag.put("barcelona", ["geo"])
    cat.dag.put("geo(sp3e)", ["barcelona"])
    cat.dag.put("geo(sp3g)", ["barcelona"])
    cat.dag.put("shop", ["geo(sp3e3)"])
    cat.dag.put("door", ["geo(sp3g7)"])
    s = dict(valid=TimeWindow(SEP + 14 * DAY))
    offers = [
        give("grocer", Thing(("vegetable-box", "shop")), 5, nonce=11, **s),
        want("grocer", Thing(("bicycle-repair", "shop")), 6, nonce=12, **s),
        give("courier", Thing(("transport", "from(barcelona)", "to(barcelona)")), 2, nonce=13, **s),
        want("courier", Thing(("piano-lesson", "barcelona")), 5, nonce=14, **s),
        want("buyer", Thing(("vegetable-box", "door")), 8, nonce=15, **s),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=16, **s),
        give("buyer", Thing(("piano-lesson", "door")), 4, nonce=17, **s),
        give("mechanic", Thing(("bicycle-repair", "barcelona")), 5, nonce=18, **s),
        want("mechanic", Thing(("piano-lesson", "barcelona")), 5, nonce=19, **s),
    ]
    book = _book(offers)
    legs = [Leg.from_match(m) for m in candidate_matches(offers, cat, now=now)] + \
        list(composed_legs(offers, cat, now=now))
    receipt = BookClearing(book, cat, clock=lambda: now).submit(
        LoopProposal(find_circulations(legs)[0], book.store.root, cat.root, "t", now))
    if not receipt.accepted:
        raise RuntimeError(receipt.reason)
    corpus.book(book)

    corpus.section("""
Loop record v1: an aggregated leg, six lifters from two of three gives,
each give's share recorded as taken.""")
    cat = Ontology(OntoDAG()).load({"lifting": [], "lesson": []})
    book = _book([
        want("mover", Thing(("lifting",), 6), 160, nonce=21, **v),
        give("lift-a", Thing(("lifting",), 2), 30, nonce=22, **v),
        give("lift-b", Thing(("lifting",), 3), 45, nonce=23, **v),
        give("lift-c", Thing(("lifting",), 4, step=1), 60, nonce=24, **v),
        give("mover", Thing(("lesson",)), 50, nonce=25, **v),
        give("mover", Thing(("lesson",)), 50, nonce=26, **v),
        give("mover", Thing(("lesson",)), 50, nonce=27, **v),
        want("lift-a", Thing(("lesson",)), 31, nonce=28, **v),
        want("lift-b", Thing(("lesson",)), 46, nonce=29, **v),
        want("lift-c", Thing(("lesson",)), 61, nonce=30, **v),
    ])
    _clear(book, cat, now)
    corpus.book(book)

    corpus.section("""
More v4: the composed want and the plain give whose ids
tests/test_v6_record.py pins, and a decimal price for a unit beyond ASCII.""")
    v6_era = dict(valid=TimeWindow(0, 1_000_000))
    corpus.book(_book([
        want("cook", Parts((Thing(("apple",), 5, "kg"), Thing(("flour",), 2, "kg"))), 30, nonce=4, **v6_era),
        give("a", Thing(("apple",), 3), 9, nonce=7, **v6_era),
        give("tiler", Thing(("tiling",), 12, "m²", step="1/2", min=2), "99.99", nonce=31, **v),
    ]))


# ---------------------------------------------------------------- v5, v6, v7

EUR = Acceptance(("stablecoin-eur",), "EUR", 1)
SAT = Acceptance(("btc",), "sat", "1/2000")


def v5_v6_v7(corpus: Corpus) -> None:
    corpus.section("""
v5 (2026-09-19): what a maker requires of a counterparty, and the deposit:
the three v5 offers whose ids tests/test_v6_record.py pins.""")
    v = dict(valid=TimeWindow(0, 1_000_000))
    corpus.book(_book([
        want("amara", Thing(("transport",), 1, "run"), 40, **v, nonce=1,
             requires=Requires(point=50, ladder=((604800, 5), (86400, 20), (0, 50)), accepts=(SAT, EUR),
                               escrows=("contract",))),
        give("driver", Thing(("transport",), 1, "run"), 45, **v, nonce=2,
             bond=Bond(Thing(("stablecoin-eur",), 60, "EUR"), 45, "0xE")),
        give("farm", Thing(("apple", "time(2026-09-20)"), 100, "kg", step=5, min=10), 200, **v, nonce=3,
             arbitrator="0x" + "cc" * 20, requires=Requires(oracles=("countersign", "locker"))),
    ]))

    corpus.section("""
v6 and v7 (2026-09-29): the counterparty gate's requirements, `claim_max`,
an option, and a deposit's deductible. Loop record v2 adds the register
roots the proposal pinned.""")
    now = SEP + 29 * DAY
    v = dict(valid=TimeWindow(now - DAY, now + 60 * DAY))
    cat = Ontology(OntoDAG()).load({"dentistry": [], "lesson": [], "money": [],
                                    "stablecoin-eur": ["money"], "btc": ["money"]})
    visit = give("clinic", Thing(("dentistry",), 1, "visit"), 40, nonce=41, claim_max=30 * DAY, v=7,
                 bond=Bond(Thing(("stablecoin-eur",), 60, "EUR"), 45, "0x" + "ee" * 20, deductible=5), **v)
    book = _book([
        visit,
        want("pat", Thing(("dentistry",), 1, "visit"), 21, nonce=42,
             requires=Requires(point=30, accepts=(EUR,), claim_period=30 * DAY), **v),
        give("pat", Thing(("lesson",)), 20, nonce=43, requires=Requires(oracles=("countersign",)), **v),
        want("clinic", Thing(("lesson",)), 42, nonce=44, v=7, **v),
    ])
    agent = SolverAgent(registry=book, ontology=cat,
                        clearing=BookClearing(book, cat, clock=lambda: now), solver_id="t")
    root, loops = agent.find_loops(now=now)
    if len(loops) != 1:
        raise RuntimeError(f"expected one loop, found {len(loops)}")
    register = ("0x" + "11" * 20, "22" * 32)
    receipt = BookClearing(book, cat, clock=lambda: now).submit(
        LoopProposal(loops[0], root, cat.root, "t", now, register_roots=(register,)))
    if not receipt.accepted:
        raise RuntimeError(receipt.reason)
    corpus.book(book)

    corpus.section("""
More v6 and v7: the dentist's want with every v6 requirement, an option on
the clinic's visit, and a v7 want.""")
    dentist = want("amara", Thing(("dentistry",), 1, "visit"), 40, valid=TimeWindow(0, 1_000_000), nonce=11,
                   requires=Requires(
                       point=30, accepts=(EUR,),
                       counterparty=(Credential("dentist-licensed", ("attested", "self-bonded"), min_bond=20,
                                                roots=("0x" + "11" * 20,), max_root_age=86_400),),
                       legs=(RequiredLeg("insure", Accept(roots=("0x" + "22" * 20,), min_deposit=100)),),
                       resolvers=Accept(keys=("0x" + "33" * 20,), clean_for=365 * 86_400),
                       claim_period=30 * 86_400))
    option = give("clinic", Thing(("dentistry",), 1, "visit"), 3, nonce=45, underlying=visit.offer_id,
                  exercise=TimeWindow(now, now + 14 * DAY), **v)
    later = want("pat", Thing(("dentistry", "time(2026-10)"), 1, "visit"), 25, nonce=46, v=7,
                 requires=Requires(resolvers=Accept(keys=("0x" + "33" * 20,))), **v)
    corpus.book(_book([dentist, option, later]))


def main() -> None:
    corpus = Corpus()
    v1_and_v2(corpus)
    v3(corpus)
    v4(corpus)
    v5_v6_v7(corpus)
    corpus.write(FIXTURE)
    print(f"{FIXTURE}: {len(corpus.data)} records")


if __name__ == "__main__":
    main()
