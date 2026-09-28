"""The v6 record (2026-09-29, R1 of the development sequence of 2026-09-25;
`docs/plans/counterparty-gate.md` §1–§2 and `options-and-cover.md` §3.1, D7's
one bump): `requires` gains `counterparty` credentials, `legs` the loop must
also contain, the `resolvers` acceptable for the leg's reservation and the
`claim_period` a want asks; a give gains `claim_max`; an option gains
`underlying` and `exercise`; and the one `Statement` shape the gate reads.
The record fixes the shapes; the checks are R4's (and C2's for options), so
until they exist a requirement using them meets nothing and an option
clears nowhere (U7). v5 and v4 re-encode byte for byte (U2)."""

import pytest
from ontodag import OntoDAG

from loopmarket import (
    Accept, Acceptance, Bond, Credential, Offer, Ontology, Parts, RequiredLeg, Requires, Statement, Thing,
    TimeWindow, give, want,
)
from loopmarket.matching import check_match, meets

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
EUR = Acceptance(("stablecoin-eur",), "EUR", 1)
SAT = Acceptance(("btc",), "sat", "1/2000")
H = "ab" * 32


def _cat():
    return Ontology(OntoDAG()).load({"apple": [], "flour": [], "transport": [], "dentistry": [],
                                     "money": [], "stablecoin-eur": ["money"], "btc": ["money"],
                                     "insure": [], "option": []})


def _corpus():
    """v5 and v4 offers whose ids were computed by the code before the bump
    (HEAD of 2026-09-28): the bump must not move a byte of them."""
    return [
        want("amara", Thing(("transport",), 1, "run"), 40, **V, nonce=1,
             requires=Requires(point=50, ladder=((604800, 5), (86400, 20), (0, 50)), accepts=(SAT, EUR),
                               escrows=("contract",))),
        give("driver", Thing(("transport",), 1, "run"), 45, **V, nonce=2,
             bond=Bond(Thing(("stablecoin-eur",), 60, "EUR"), 45, "0xE")),
        give("farm", Thing(("apple", "time(2026-09-20)"), 100, "kg", step=5, min=10), 200, **V, nonce=3,
             arbitrator="0x" + "cc" * 20, requires=Requires(oracles=("countersign", "locker"))),
        want("cook", Parts((Thing(("apple",), 5, "kg"), Thing(("flour",), 2, "kg"))), 30, **V, nonce=4),
        give("a", Thing(("apple",), 3), 9, **V, nonce=7),
    ]


GOLDEN = [
    (5, "e2a07847e69850dea803712b27a60c2816f97f81a85c3ad907f83c656c81a49b"),
    (5, "c1f379a41d893456a0396f72a1244e552ae9cd93826104ef2c8719402b88c5f9"),
    (5, "aafba5615ba516997ba2aec22069d8e0f5b9fb26101de2e75d10b7b7784642a5"),
    (4, "853c3472a3cccd704507861e7cc99756d4bd2667233ad9583698cc990fa8a664"),
    (4, "0d9c420e80047ba87cbaf52ac1dcceaeae9a87119b4ea900322404a54bc5c145"),
]


def test_v5_and_v4_reencode_byte_for_byte():
    for offer, (v, oid) in zip(_corpus(), GOLDEN):
        assert (offer.v, offer.offer_id) == (v, oid)
        rec = offer.to_record()
        assert not any(k in rec for k in ("claim_max", "underlying", "exercise"))
        back = Offer.from_record(rec)
        assert back == offer and back.offer_id == oid


def _dentist_want(**kw):
    return want("amara", Thing(("dentistry",), 1, "visit"), 40, **V, nonce=11,
                requires=Requires(
                    point=30, accepts=(EUR,),
                    counterparty=(Credential("dentist-licensed", ("attested", "self-bonded"), min_bond=20,
                                             roots=("0x" + "11" * 20,), max_root_age=86_400),),
                    legs=(RequiredLeg("insure", Accept(roots=("0x" + "22" * 20,), min_deposit=100)),),
                    resolvers=Accept(keys=("0x" + "33" * 20,), clean_for=365 * 86_400),
                    claim_period=30 * 86_400, **kw))


def test_the_v6_record_round_trips_and_is_chosen_by_its_fields():
    amara = _dentist_want()
    assert amara.v == 6
    rec = amara.to_record()
    assert rec["claim_max"] == 0 and rec["underlying"] == "" and rec["exercise"] is None
    assert rec["requires"]["counterparty"] == [{"category": "dentist-licensed", "kinds": ["attested", "self-bonded"],
                                                "min_bond": "20", "roots": ["0x" + "11" * 20],
                                                "max_root_age": 86_400}]
    assert rec["requires"]["legs"] == [{"category": "insure", "accept": {
        "keys": [], "roots": ["0x" + "22" * 20], "min_deposit": "100", "clean_for": 0, "issuance": []}}]
    assert rec["requires"]["resolvers"]["clean_for"] == 365 * 86_400
    assert rec["requires"]["claim_period"] == 30 * 86_400
    back = Offer.from_record(rec)
    assert back == amara and back.offer_id == amara.offer_id
    # a give's claim_max and an option are v6 too
    dentist = give("0x" + "44" * 20, Thing(("dentistry",), 1, "visit"), 35, **V, nonce=12, claim_max=60 * 86_400,
                   bond=Bond(Thing(("stablecoin-eur",), 50, "EUR"), 50, "0xE"))
    assert dentist.v == 6 and Offer.from_record(dentist.to_record()) == dentist
    hold = give("w", Thing(("option", "apple"), 1, "hold"), 5, **V, nonce=13, underlying=H,
                exercise=TimeWindow(100, 200))
    assert hold.v == 6 and hold.to_record()["exercise"] == [100, 200]
    assert Offer.from_record(hold.to_record()) == hold
    # entries are canonical: order does not change the id
    two = (Credential("b-cat", ("signed",)), Credential("a-cat", ("attested",), roots=("0xr",), max_root_age=1))
    ids = {want("x", Thing(("apple",), 1), 1, **V, nonce=1, requires=Requires(counterparty=c)).offer_id
           for c in (two, two[::-1])}
    assert len(ids) == 1


def test_v6_forms_are_refused_in_earlier_records_and_unknown_versions_raise():
    amara = _dentist_want()
    rec = amara.to_record()
    with pytest.raises(ValueError, match="v6 form"):
        give("a", Thing(("apple",), 3), 9, **V, claim_max=10, v=5)
    with pytest.raises(ValueError, match="v6 form"):
        want("a", Thing(("apple",), 3), 9, **V, requires=Requires(claim_period=5), v=5)
    five = _corpus()[0].to_record()
    for extra in ({"claim_max": 0}, {"underlying": ""}, {"exercise": None}):
        with pytest.raises(ValueError, match="v6 forms"):
            Offer.from_record(dict(five, **extra))
    with pytest.raises(ValueError, match="v6 form"):
        Offer.from_record(dict(five, requires=dict(five["requires"], claim_period=5)))
    with pytest.raises(ValueError, match="carries claim_max, underlying and exercise"):
        Offer.from_record({k: v for k, v in rec.items() if k != "exercise"})
    for v in (7, 0, None, "6"):
        with pytest.raises(ValueError, match="unknown offer record version"):
            Offer.from_record(dict(rec, v=v))


def test_the_v6_shapes_refuse_what_they_cannot_mean():
    with pytest.raises(ValueError, match="names a key, a root or a floor"):
        Accept()
    with pytest.raises(ValueError, match="kind is one of"):
        Credential("c", ("vouched",))
    with pytest.raises(ValueError, match="maximum root age"):
        Credential("c", ("signed",), roots=("0xr",))
    with pytest.raises(ValueError, match="claim_max is a give's"):
        want("a", Thing(("apple",), 3), 9, **V, claim_max=10)
    with pytest.raises(ValueError, match="asked of a giver, by a want"):
        give("a", Thing(("apple",), 3), 9, **V, requires=Requires(claim_period=10))
    with pytest.raises(ValueError, match="together"):
        give("w", Thing(("option",), 1), 5, **V, underlying=H)
    with pytest.raises(ValueError, match="unpriced lock"):
        give("w", Thing(("option",), 1), 5, **V, underlying=H, exercise=TimeWindow(100, None))
    with pytest.raises(ValueError, match="writer's give"):
        want("w", Thing(("option",), 1), 5, **V, underlying=H, exercise=TimeWindow(100, 200))
    with pytest.raises(ValueError, match="64-hex"):
        give("w", Thing(("option",), 1), 5, **V, underlying="P", exercise=TimeWindow(100, 200))


def test_the_statement_is_one_content_addressed_shape():
    s = Statement(subject="0x" + "44" * 20, category="dentist-licensed", issuer="0x" + "55" * 20, kind="attested",
                  as_of=1_000, until=1_000 + 28 * 86_400, evidence="ee" * 32,
                  path=("0x" + "55" * 20, "0x" + "11" * 20), paid_by="subject",
                  deposit=("dd" * 32, "0x" + "66" * 20), scheme="5c" * 32, issuance="issued-by-attester-in-person")
    rec = s.to_record()
    assert rec["deposit"] == {"offer": "dd" * 32, "escrow": "0x" + "66" * 20} and rec["v"] == 1
    back = Statement.from_record(rec)
    assert back == s and back.statement_id == s.statement_id and len(s.statement_id) == 64
    solo = Statement(subject="0xk", category="dentist-licensed", issuer="0xk", kind="self-bonded", as_of=1, until=2,
                     evidence="ee" * 32, path=("0xk",), paid_by="subject", deposit=("dd" * 32, "0xE"))
    assert Statement.from_record(solo.to_record()) == solo
    base = dict(subject="0xk", category="c", issuer="0xi", kind="attested", as_of=1, until=2, evidence="ee" * 32,
                path=("0xi",), paid_by="relier")
    for bad, match in ((dict(kind="insured"), "kind is one of"), (dict(paid_by="nobody"), "paid_by"),
                       (dict(until=1), "later until"), (dict(evidence="short"), "64-hex"),
                       (dict(path=("0xroot", "0xi")), "starts at its issuer"),
                       (dict(kind="self-bonded"), "its subject's own"), (dict(scheme="x"), "64-hex")):
        with pytest.raises(ValueError, match=match):
            Statement(**dict(base, **bad))
    with pytest.raises(ValueError, match="unknown statement record version"):
        Statement.from_record(dict(rec, v=2))


def test_requirements_this_build_cannot_check_meet_nothing_and_options_clear_nowhere():
    """Fail closed (U7): a credential meets nothing without the gate's
    reads (R4, `test_gate.py`), a required leg nothing until D4's operators,
    an option nothing without the gate that sees its underlying (C2,
    `test_options.py`); an empty v6 requirement
    changes nothing; a claim period is met by a give whose claim_max
    reaches it."""
    ont = _cat()
    bond = Bond(Thing(("stablecoin-eur",), 50, "EUR"), 50, "0xE")
    dentist = give("0x" + "44" * 20, Thing(("dentistry",), 1, "visit"), 35, **V, nonce=12, claim_max=60 * 86_400,
                   bond=bond)
    plain = want("amara", Thing(("dentistry",), 1, "visit"), 40, **V, nonce=21)
    assert check_match(dentist, plain, ont, now=NOW) is not None
    # each v6 entry alone refuses the leg without its reads
    for req in (Requires(counterparty=(Credential("dentist-licensed", ("signed",)),)),
                Requires(legs=(RequiredLeg("insure", Accept(keys=("0xi",))),)),
                Requires(resolvers=Accept(keys=("0xr",)))):
        w = want("amara", Thing(("dentistry",), 1, "visit"), 40, **V, nonce=22, requires=req)
        assert w.v == 6 and not meets(w, dentist, ont)
        assert check_match(dentist, w, ont, now=NOW) is None
    # the claim period: met when the give's claim_max reaches it, not otherwise
    asks = lambda s: want("amara", Thing(("dentistry",), 1, "visit"), 40, **V, nonce=23,
                          requires=Requires(claim_period=s))
    assert check_match(dentist, asks(30 * 86_400), ont, now=NOW) is not None
    assert check_match(dentist, asks(90 * 86_400), ont, now=NOW) is None
    v5_dentist = give("0x" + "44" * 20, Thing(("dentistry",), 1, "visit"), 35, **V, nonce=12, bond=bond)
    assert check_match(v5_dentist, asks(1), ont, now=NOW) is None      # no claim_max declared: reaches nothing
    # an option clears nowhere without the gate that reads its underlying
    hold = give("w", Thing(("apple",), 1, "kg"), 5, **V, nonce=13, underlying=H, exercise=TimeWindow(100, 200))
    assert check_match(hold, want("b", Thing(("apple",), 1, "kg"), 9, **V, nonce=24), ont, now=NOW) is None
    # an empty requirement on a v6 offer changes nothing
    assert Requires().empty and not Requires().v6
    assert check_match(dentist, want("amara", Thing(("dentistry",), 1, "visit"), 40, **V, nonce=25,
                                     requires=Requires()), ont, now=NOW) is not None


def test_a_resolver_acceptance_admits_the_named_key_and_never_a_party():
    """E2 (C4): `requires.resolvers` is met by a give whose arbitrator the
    acceptance admits — by key today; never the want's or the give's maker
    (the cheap formality); an acceptance whose admission needs the
    registers or the ledger (roots, a deposit floor, a look-back) admits
    nothing until those reads exist (U7)."""
    from loopmarket.matching import admits
    ont = _cat()
    judge, giver = "0x" + "77" * 20, "0x" + "44" * 20
    acc = Accept(keys=(judge,))
    assert admits(acc, judge) and admits(acc, judge.upper().replace("0X", "0x"))
    assert not admits(acc, "") and not admits(acc, "0x" + "78" * 20)
    assert not admits(acc, judge, parties=(judge,))
    assert not admits(Accept(keys=(judge,), clean_for=86_400), judge)
    assert not admits(Accept(roots=("0xroot",)), judge)
    w = want("amara", Thing(("dentistry",), 1, "visit"), 40, **V, nonce=31, requires=Requires(resolvers=acc))
    named = give(giver, Thing(("dentistry",), 1, "visit"), 35, **V, nonce=32, arbitrator=judge)
    assert check_match(named, w, ont, now=NOW) is not None
    assert check_match(give(giver, Thing(("dentistry",), 1, "visit"), 35, **V, nonce=33), w, ont, now=NOW) is None
    self_judged = want(judge, Thing(("dentistry",), 1, "visit"), 40, **V, nonce=34, requires=Requires(resolvers=acc))
    assert check_match(named, self_judged, ont, now=NOW) is None           # the wanter would judge her own claim


def test_reservations_take_the_legs_claim_period_and_refuse_a_party_as_resolver():
    """E2: the reservation's claim period is the want's ask, else the
    default, and never beyond the give's claim_max; the resolver is never a
    party; `cover_predicate` marks a give under the catalogue's `insure`."""
    from types import SimpleNamespace
    from loopmarket.escrow import cover_predicate, reservations_for
    from loopmarket.matching import Leg
    W, D, J = "0x" + "aa" * 20, "0x" + "bb" * 20, "0x" + "cc" * 20
    bond = Bond(Thing(("stablecoin-eur",), 10, "EUR"), 8, "0xE")

    def loop(w, g):
        return SimpleNamespace(circulation=SimpleNamespace(legs=(Leg(w, (g,)),), loop_id="ab" * 32))

    def res(w, g, **kw):
        return reservations_for(loop(w, g), escrow="0xE", resolver=J, claim_seconds=7 * 86_400, now=NOW, **kw)[0]

    asks = want(W, Thing(("apple",), 1, "kg"), 9, **V, nonce=41, requires=Requires(claim_period=30 * 86_400))
    plain = want(W, Thing(("apple",), 1, "kg"), 9, **V, nonce=42)
    carries = give(D, Thing(("apple",), 1, "kg"), 5, **V, nonce=43, bond=bond, claim_max=60 * 86_400)
    short = give(D, Thing(("apple",), 1, "kg"), 5, **V, nonce=44, bond=bond, claim_max=3 * 86_400)
    v5 = give(D, Thing(("apple",), 1, "kg"), 5, **V, nonce=45, bond=bond)
    assert res(asks, carries)["claim_seconds"] == 30 * 86_400           # the want's ask
    assert res(plain, carries)["claim_seconds"] == 7 * 86_400           # the default, within claim_max
    assert res(plain, short)["claim_seconds"] == 3 * 86_400             # never beyond what the giver carries
    assert res(plain, v5)["claim_seconds"] == 7 * 86_400
    with pytest.raises(ValueError, match="a party to the leg"):
        reservations_for(loop(plain, v5), escrow="0xE", resolver=D, claim_seconds=1, now=NOW)
    judged = give(D, Thing(("apple",), 1, "kg"), 5, **V, nonce=46, bond=bond, arbitrator=W)
    with pytest.raises(ValueError, match="a party to the leg"):
        res(plain, judged)
    picky = want(W, Thing(("apple",), 1, "kg"), 9, **V, nonce=47, requires=Requires(resolvers=Accept(keys=(J,))))
    assert res(picky, v5)["resolver"] == J
    with pytest.raises(ValueError, match="not one"):
        reservations_for(loop(picky, v5), escrow="0xE", resolver="0x" + "dd" * 20, claim_seconds=1, now=NOW)
    # cover: a give under `insure` is claim-only; a catalogue without it marks nothing
    ont = Ontology(OntoDAG()).load({"insure": [], "theft-cover": ["insure"], "apple": [],
                                    "stablecoin-eur": []})
    cover = give(D, Thing(("theft-cover",), 1, "policy"), 5, **V, nonce=48, bond=bond)
    wants_cover = want(W, Thing(("theft-cover",), 1, "policy"), 9, **V, nonce=49)
    assert res(wants_cover, cover, claim_only=cover_predicate(ont))["claim_only"]
    assert not res(plain, v5, claim_only=cover_predicate(ont))["claim_only"]
    assert not res(wants_cover, cover, claim_only=cover_predicate(_cat()))["claim_only"]
