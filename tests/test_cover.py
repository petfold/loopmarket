"""Cover paid by the escrow, end to end (C5 stage 1, 2026-09-29;
`docs/plans/options-and-cover.md` §4). An insurer gives
`insure(vehicle theft time(<period>))` with its deposit — the limit — in the
escrow; an insured wants `insure(car theft time(<her period>))` and pays the
premium in a loop. Matching reads the argument want-within-give: her car and
her dates must lie within what the insurer covers. At finalize the
reservation is cover (`claimOnly`) and its window is **her** covered period,
the claim period running from its end. A countersignature is refused; the
insured asserts the trigger on factbond, the insurer disputes, the ruling
for the insured pays her claim out of the reservation and returns the rest
to the insurer; a policy with no claim settles back to the insurer after
its claim period. The deductible (v7, the same day) is an amount of the
deposit's asset: a ruled payout is the claim less it, and a deposit counts
against a wanter's neutral point only up to what it can pay. Skips
without the `evm` extra or the sibling factbond."""

from datetime import datetime, timezone

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Acceptance, Bond, BookClearing, OfferRegistry, Offer, Ontology, Requires, SolverAgent, Thing, TimeWindow,
    give, want,
)
from loopmarket.beat import proposal_from_record, snapshot_of
from loopmarket.escrow import cover_predicate, reservations_for, to_wei
from loopmarket.matching import check_match

from test_escrow import _HAVE_EVM, _advance, _factbond, _now, _reverts, _terms

pytestmark = pytest.mark.skipif(not _HAVE_EVM, reason="needs the evm extra: pip install 'loopmarket[evm]'")

CLAIM = 3_600


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _span(text: str):
    a, b = text.split("..")
    parse = lambda s: int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    return parse(a), parse(b)


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_handover(["geo", "time"])
    cat.declare_argument_operator(["insure"])
    cat.load({"vehicle": [], "car": ["vehicle"], "theft": [], "lesson": [], "xdai": []})
    return cat


def _market(escrow, factbond, insurer, insureds, t):
    """The insurer's cover of vehicles against theft for a day, two policies
    backed by 1 xDAI (0.5 per policy: the limit) with a deductible of 0.1
    (0.05 per policy), and each insured's want of cover for her car for an
    hour of it, paid for with a lesson."""
    cat = _cat()
    V = dict(valid=TimeWindow(t - 3_600, t + 86_400))
    day = f"{_iso(t - 600)}..{_iso(t + 86_400)}"
    cover = give(insurer, Thing((f"insure(vehicle theft time({day}))",), 2, "policy", step=1), 10, **V, nonce=1,
                 bond=Bond(Thing(("xdai",), 1, "xDAI"), 10, escrow.address, deductible="1/10"),
                 arbitrator=factbond.address,
                 claim_max=CLAIM)
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [cover]
    for n, insured in enumerate(insureds):
        hour = f"{_iso(t + 60)}..{_iso(t + 3_660)}"
        offers += [want(insured, Thing((f"insure(car theft time({hour}))",), 1, "policy"), 12, **V, nonce=10 + n),
                   give(insured, Thing(("lesson",), 1, "hour"), 5, **V, nonce=20 + n),
                   want(insurer, Thing(("lesson",), 1, "hour"), 20, **V, nonce=30 + n)]
    book.publish_many(offers)
    book.commit()
    return cat, book, cover, hour


def test_matching_reads_the_covered_period_want_within_give():
    cat = _cat()
    V = dict(valid=TimeWindow(0, 10 ** 10))
    cover = give("i", Thing(("insure(vehicle theft time(2026-10-01..2026-10-31))",), 1, "policy"), 10, **V)
    wanted = lambda term: want("w", Thing((term,), 1, "policy"), 12, **V)
    assert check_match(cover, wanted("insure(car theft time(2026-10-03..2026-10-10))"), cat, now=1) is not None
    assert check_match(cover, wanted("insure(car theft time(2026-11-03..2026-11-10))"), cat, now=1) is None
    assert check_match(cover, wanted("insure(car time(2026-10-03..2026-10-10))"), cat, now=1) is None  # no peril named


def test_cover_is_reserved_for_the_covered_period_and_pays_a_ruled_claim(chain):
    w3, escrow, coin, clearing = chain
    factbond, adjudicator, fee, floor = _factbond(w3)
    insurer, claimant, quiet = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[6]
    t = _now(w3)
    cat, book, cover, hour = _market(escrow, factbond, insurer, [claimant, quiet], t)
    root = book.store.root
    receipts = SolverAgent(book, cat, clearing=BookClearing(book, cat, clock=lambda: t),
                           solver_id="t").step(now=t)
    assert len(receipts) == 2 and all(r.accepted for r in receipts), [(r.accepted, r.reason) for r in receipts]
    reservations = []
    for r in receipts:
        proposal = proposal_from_record(book.store.get(f"loop/{r.loop_id}"), snapshot_of(book, root))
        reservations += reservations_for(proposal, escrow=escrow.address, resolver=insurer, claim_seconds=86_400,
                                         now=t, span=_span, claim_only=cover_predicate(cat))
    assert len(reservations) == 2
    for res in reservations:
        assert res["claim_only"] and res["window"] == _span(hour)            # her hour, not the insurer's day
        assert res["amount"] == to_wei("1/2") and res["claim_seconds"] == CLAIM   # the limit; claim_max caps it
        assert res["deductible"] == to_wei("1/20")                          # the deductible's share
        assert res["resolver"] == factbond.address
    offer = bytes.fromhex(cover.offer_id)
    escrow.functions.deposit(offer).transact({"from": insurer, "value": to_wei(1)})
    for res in reservations:
        escrow.functions.reserve(offer, bytes.fromhex(res["loop_id"]), res["wanter"], res["resolver"], res["amount"],
                                 _terms(*res["window"], res["claim_seconds"], claim_only=True,
                                        deductible=res["deductible"]), [], []
                                 ).transact({"from": clearing})
    assert escrow.functions.free(offer).call() == 0
    by = {res["wanter"]: bytes.fromhex(res["loop_id"]) for res in reservations}
    # cover is never countersigned: that would void it
    assert "never countersigned" in _reverts(w3, escrow.functions.countersign(offer, by[claimant]), claimant)
    # the car is stolen: the claimant asserts a loss of 0.3 xDAI, the insurer disputes, the ruling is hers
    subject = escrow.functions.key(offer, by[claimant]).call()
    factbond.functions.assert_(subject, escrow.address, to_wei("3/10"), 990, 0, 0, insurer).transact(
        {"from": claimant, "value": fee + floor})
    claim = factbond.functions.count().call()
    assert escrow.functions.reservation(offer, by[claimant]).call()[6]                # held
    factbond.functions.dispute(claim).transact({"from": insurer, "value": factbond.functions.stakeFor(floor, 990).call()})
    before_claimant, before_insurer = w3.eth.get_balance(claimant), w3.eth.get_balance(insurer)
    factbond.functions.rule(claim, True).transact({"from": adjudicator})
    assert escrow.functions.reservation(offer, by[claimant]).call()[7]                # settled
    assert w3.eth.get_balance(insurer) - before_insurer == to_wei("1/4")             # the rest, the deductible in it
    assert w3.eth.get_balance(claimant) - before_claimant >= to_wei("1/4")           # 0.3 less 0.05 (and her bond back)
    # the other policy: no claim; after her hour and the claim period anyone settles it back to the insurer
    assert "claim period" in _reverts(w3, escrow.functions.settle(offer, by[quiet]), quiet)
    _advance(w3, 3_700 + CLAIM + 10)
    before = w3.eth.get_balance(insurer)
    escrow.functions.settle(offer, by[quiet]).transact({"from": quiet})
    assert w3.eth.get_balance(insurer) - before == to_wei("1/2")


PINNED = {   # computed before the v7 bump: a deductible is the only v7 form, so these stay as they were
    "2a77de3797b0e5fb5c5a05e3cdcece1365c8d844b27221a90cb45bda0748ffef": 5,
    "f78fa5ddd9f56f57cdc14141b83d8a5d729237d20197b016f24d394ffca25660": 6,
    "bd8c3813aec65080206c96870ce68434085c2492ad1edc77f05181f660d3640b": 6,
}


def test_a_deductible_is_the_only_v7_form_and_counts_against_the_point():
    V = dict(valid=TimeWindow(1_790_000_000, 1_790_086_400), nonce=7)
    bond = Bond(Thing(("xdai",), "1/2", "xDAI"), 5, "0x" + "e5" * 20)
    old = [give("0x" + "a1" * 20, Thing(("car",), 1, "car"), 50, bond=bond, **V),
           give("0x" + "a2" * 20, Thing(("insure(vehicle theft time(2026-10-01T00:00:00Z..2026-10-31T23:59:59Z))",),
                                  2, "policy", step=1), 10, bond=bond, claim_max=3600, arbitrator="0x" + "f1" * 20, **V),
           give("0x" + "a3" * 20, Thing(("option(flat)",), 1, "lease"), 5, underlying="ab" * 32,
                exercise=TimeWindow(1_790_000_000, 1_790_050_000), **V)]
    assert {o.offer_id: o.v for o in old} == PINNED
    d = give("0x" + "a1" * 20, Thing(("car",), 1, "car"), 50, **V,
             bond=Bond(Thing(("xdai",), "1/2", "xDAI"), 5, "0x" + "e5" * 20, "1/10"))
    assert d.v == 7 and Offer.from_record(d.to_record()) == d and d.to_record()["bond"]["deductible"] == "1/10"
    with pytest.raises(ValueError, match="below the deposit"):
        Bond(Thing(("xdai",), "1/2", "xDAI"), 5, "", "1/2")
    with pytest.raises(ValueError, match="v7 form"):
        give("0x" + "a1" * 20, Thing(("car",), 1, "car"), 50, **V, v=6,
             bond=Bond(Thing(("xdai",), "1/2", "xDAI"), 5, "", "1/10"))
    # a wanter's point of 4 at 1 per 1/10 xDAI needs 0.4: the deposit's 0.5 covers it, less a 0.2 deductible not
    cat = _cat()
    buyer = want("0x" + "b1" * 20, Thing(("car",), 1, "car"), 60, **V,
                 requires=Requires(point=4, accepts=(Acceptance(("xdai",), "xDAI", 10),)))
    plain = give("0x" + "a1" * 20, Thing(("car",), 1, "car"), 50, **V, bond=bond)
    deducted = give("0x" + "a1" * 20, Thing(("car",), 1, "car"), 50, **dict(V, nonce=8),
                    bond=Bond(Thing(("xdai",), "1/2", "xDAI"), 5, "0x" + "e5" * 20, "1/5"))
    assert check_match(plain, buyer, cat, now=1_790_000_001) is not None
    assert check_match(deducted, buyer, cat, now=1_790_000_001) is None


def test_the_taxi_no_show_is_paid_once_the_drivers_deposit_first(chain):
    """C5 stage 2 (D-2, 2026-09-29, Peter's taxi case). A traveller wants a
    ride with cover (`requires.legs`: an `insure` leg from the insurer); the
    driver posts a small deposit of his own, the insurer's deposit is the
    limit, and the cover's reservation covers the driver's. The driver
    forgets; the traveller's loss is 0.3 (the missed ferry). Two ways, the
    same result — she is made whole once, the insurer's net cost is the loss
    less the driver's deposit, and the driver's own fault costs him his:

    - assignment: she cannot claim the cover until her claim on the driver's
      reservation belongs to the insurer; she assigns it, the cover pays her
      0.3, and the insurer recovers the driver's 0.05 as the assignee;
    - netting: she claims the driver's 0.05 herself first, and the cover
      then pays 0.25 — what the driver's reservation paid her is not paid
      again."""
    from loopmarket import Accept, RequiredLeg
    from loopmarket.escrow import reservation_key
    w3, escrow, coin, clearing = chain
    factbond, adjudicator, fee, floor = _factbond(w3)
    insurer, driver, bystander = w3.eth.accounts[2], w3.eth.accounts[7], w3.eth.accounts[8]
    travellers = [w3.eth.accounts[3], w3.eth.accounts[6]]
    t = _now(w3)
    cat = Ontology(OntoDAG())
    cat.declare_handover(["geo", "time"])
    cat.declare_argument_operator(["insure"])
    cat.load({"ride": [], "lesson": [], "painting": [], "xdai": []})
    V = dict(valid=TimeWindow(t - 3_600, t + 86_400))
    hour, day = f"{_iso(t + 60)}..{_iso(t + 3_660)}", f"{_iso(t - 600)}..{_iso(t + 86_400)}"
    ride = give(driver, Thing(("ride", f"time({hour})"), 2, "ride", step=1), 30, **V, nonce=1,
                bond=Bond(Thing(("xdai",), "1/10", "xDAI"), 50, escrow.address))              # 0.05 a ride
    # one policy per offer: an operator's give is taken whole by the leg it
    # serves (a courier's run moves a lot), so an insurer sells a policy an offer
    covers = [give(insurer, Thing((f"insure(ride time({day}))",), 1, "policy"), 10, **V, nonce=2 + n,
                   bond=Bond(Thing(("xdai",), "1/2", "xDAI"), 5, escrow.address), arbitrator=factbond.address)
              for n in range(2)]
    offers = [ride, *covers]
    for n, traveller in enumerate(travellers):
        offers += [want(traveller, Thing(("ride", f"time({hour})"), 1, "ride"), 100, **V, nonce=10 + n,
                        requires=Requires(legs=(RequiredLeg("insure", Accept(keys=(insurer,))),))),
                   give(traveller, Thing(("lesson",), 1, "hour"), 5, **V, nonce=20 + n),
                   want(driver, Thing(("lesson",), 1, "hour"), 60, **V, nonce=30 + n),
                   give(traveller, Thing(("painting",), 1, "piece"), 5, **V, nonce=40 + n),
                   want(insurer, Thing(("painting",), 1, "piece"), 30, **V, nonce=50 + n)]
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many(offers)
    book.commit()
    root = book.store.root
    agent = SolverAgent(book, cat, clearing=BookClearing(book, cat, clock=lambda: t), solver_id="t")
    receipts = []
    for _ in range(3):                      # a composed circulation per pass: step until the book is quiet
        receipts += [r for r in agent.step(now=t) if r.accepted]
    assert len(receipts) == 2, [(r.accepted, r.reason) for r in receipts]
    escrow.functions.deposit(bytes.fromhex(ride.offer_id)).transact({"from": driver, "value": to_wei("1/10")})
    for cover in covers:
        escrow.functions.deposit(bytes.fromhex(cover.offer_id)).transact({"from": insurer, "value": to_wei("1/2")})
    loops, cover_of = {}, {}
    for r in receipts:
        proposal = proposal_from_record(book.store.get(f"loop/{r.loop_id}"), snapshot_of(book, root))
        res = reservations_for(proposal, escrow=escrow.address, resolver=factbond.address, claim_seconds=86_400,
                               now=t, span=_span, claim_only=cover_predicate(cat))
        by = {x["offer_id"]: x for x in res}
        cover = next(c for c in covers if c.offer_id in by)
        assert by[cover.offer_id]["claim_only"] and not by[ride.offer_id]["claim_only"]
        assert by[cover.offer_id]["covers"] == reservation_key(ride.offer_id, r.loop_id)
        for x in res:
            escrow.functions.reserve(bytes.fromhex(x["offer_id"]), bytes.fromhex(x["loop_id"]), x["wanter"],
                                     x["resolver"], x["amount"],
                                     _terms(*x["window"], x["claim_seconds"], claim_only=x["claim_only"],
                                            covers=bytes.fromhex(x["covers"]) if x["covers"] else bytes(32)),
                                     [], []).transact({"from": clearing})
        loops[by[ride.offer_id]["wanter"]] = bytes.fromhex(r.loop_id)
        cover_of[by[ride.offer_id]["wanter"]] = bytes.fromhex(cover.offer_id)
    r_off = bytes.fromhex(ride.offer_id)

    def claim(who, offer, loop, outcome, about):
        factbond.functions.assert_(escrow.functions.key(offer, loop).call(), escrow.address, outcome, 990, 0, 0,
                                   about).transact({"from": who, "value": fee + floor})
        return factbond.functions.count().call()

    def certify(claim_id, *watch):
        _advance(w3, 200)
        before = [w3.eth.get_balance(a) for a in watch]
        factbond.functions.certify(claim_id).transact({"from": bystander})
        return [w3.eth.get_balance(a) - b for a, b in zip(watch, before)]

    # assignment: the first traveller
    first, loop = travellers[0], loops[travellers[0]]
    c_off = cover_of[first]
    cover_claim = factbond.functions.assert_(escrow.functions.key(c_off, loop).call(), escrow.address,
                                             to_wei("3/10"), 990, 0, 0, insurer)
    assert "assign the claim on the covered reservation to the insurer first" in _reverts(
        w3, cover_claim, first, value=fee + floor)
    escrow.functions.assign(r_off, loop, insurer).transact({"from": first})
    got, back = certify(claim(first, c_off, loop, to_wei("3/10"), insurer), first, insurer)
    assert got == to_wei("3/10") + floor and back == to_wei("1/5")          # she is made whole; 0.2 of the limit back
    assert "the claim is the wanter's" in _reverts(                         # her claim on the driver is the insurer's now
        w3, factbond.functions.assert_(escrow.functions.key(r_off, loop).call(), escrow.address, to_wei("1/20"),
                                       990, 0, 0, driver), first, value=fee + floor)
    recovered, lost = certify(claim(insurer, r_off, loop, to_wei("1/20"), driver), insurer, driver)
    assert recovered == to_wei("1/20") + floor and lost == 0                 # the insurer recovers the driver's 0.05

    # netting: the second traveller claims the driver's deposit herself, then the cover
    second, loop = travellers[1], loops[travellers[1]]
    c_off = cover_of[second]
    got_driver, = certify(claim(second, r_off, loop, to_wei("1/20"), driver), second)
    got_cover, back = certify(claim(second, c_off, loop, to_wei("3/10"), insurer), second, insurer)
    assert got_driver == to_wei("1/20") + floor and got_cover == to_wei("1/4") + floor   # 0.05 + 0.25: 0.3, once
    assert back == to_wei("1/4")
    assert escrow.functions.coverOf(c_off, loop).call()[0] == bytes.fromhex(reservation_key(ride.offer_id, loop.hex()))
