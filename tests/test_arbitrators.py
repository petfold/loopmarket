"""Arbitrators accepted by property (2026-09-29, `docs/plans/counterparty-gate.md`
§7a): a traveller's want accepts the resolver of the ride's reservation not
by name but as "any arbitrator accredited by the association, with at least
this much at stake on a reversal, and no reversal for a year". The
resolver is a factbond-style contract whose adjudicator — the key that
rules — presents an attested `transport-arbitrator` statement in its own
book; the association's register is pinned; the chain's record of the
contract (who rules, what a reversal forfeits, when it was reversed) is
read through `Profile`. The loop solves and clears; each missing property
is refused, named; a give's own acceptance and the want's choose one
resolver both admit, deterministically; and the chain reader is checked
against factbond's `Assertions` on a local EVM.
"""

import os

import pytest
from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Accept, Acceptance, Bond, BookClearing, OfferRegistry, Ontology, Requires, SolverAgent, Statement,
    Thing, TimeWindow, give, want,
)
from loopmarket.arbitrators import Profile, accept_faults, admits, resolver_of
from loopmarket.gate import CounterpartyGate
from loopmarket.matching import check_match
from loopmarket.register import Register, named_registers

HERE = os.path.dirname(__file__)
NOW = 1_790_000_000
YEAR = 365 * 86_400
DRIVER, TRAVELLER = "0x" + "d1" * 20, "0x" + "a1" * 20
RESOLVER, ARB, FINAL = "0x" + "fb" * 20, "0x" + "ad" * 20, "0x" + "f1" * 20   # the contract, its rungs
ASSOC, OTHER = "0x" + "a5" * 20, "0x" + "0e" * 20                            # trust roots
XDAI = Acceptance(("xdai",), "xDAI", 2)          # the traveller's price: 2 on her scale per xDAI
V = dict(valid=TimeWindow(NOW - 10, NOW + 30 * 86_400))


def _cat():
    cat = Ontology(OntoDAG())
    cat.load({"ride": [], "lesson": [], "xdai": [], "arbitrator": [], "transport-arbitrator": ["arbitrator"],
              "dentist-licensed": [], "inspect": [], "vehicle-inspector": ["inspect"]})
    return cat


def _profile(**kw):
    base = dict(rulers=(ARB,), deposit=6, asset=(("xdai",), "xDAI"), reversals=(), since=NOW - 2 * YEAR)
    base.update(kw)
    return Profile(**base)


class World:
    """The ride's book, the association's register, the resolver's record."""

    def __init__(self, accept=None, *, category="transport-arbitrator", kind="attested", statement=True,
                 profile=None, arbitrator=RESOLVER, give_requires=None, subject=ARB):
        self.blobs = MemoryBytesStore()
        self.book = OfferRegistry(RecordStore(self.blobs))
        accept = accept or Accept(roots=(ASSOC,), min_deposit=10, clean_for=YEAR)
        self.ride = give(DRIVER, Thing(("ride",), 1, "trip"), 30, **V, nonce=1, arbitrator=arbitrator,
                         bond=Bond(Thing(("xdai",), 20, "xDAI"), 20, "0xE"), requires=give_requires)
        self.wants_ride = want(TRAVELLER, Thing(("ride",), 1, "trip"), 40, **V, nonce=2,
                               requires=Requires(accepts=(XDAI,), resolvers=accept))
        self.lesson = give(TRAVELLER, Thing(("lesson",), 1, "hour"), 10, **V, nonce=3)
        self.wants_lesson = want(DRIVER, Thing(("lesson",), 1, "hour"), 35, **V, nonce=4)
        self.book.publish_many([self.ride, self.wants_ride, self.lesson, self.wants_lesson])
        own = kind == "self-bonded"                       # its subject's own, backed by the ride's deposit
        self.statement = Statement(subject=subject, category=category, issuer=subject if own else ASSOC,
                                   kind=kind, as_of=NOW - YEAR, until=NOW + YEAR, evidence="ee" * 32,
                                   path=(subject, ASSOC) if own else (ASSOC,), paid_by="subject",
                                   deposit=(self.ride.offer_id, "0xE") if own else None)
        if statement:
            self.book.present(self.statement)
        self.book.commit()
        self.assoc = Register(RecordStore(self.blobs))
        self.assoc.issue(self.statement.statement_id, NOW - YEAR)
        self.assoc.heartbeat(NOW - 100)
        self.assoc.commit()
        self.profiles = {RESOLVER: _profile() if profile is None else profile}

    @property
    def registers(self):
        return {ASSOC: self.assoc}

    def gate(self, registers=None, latest=True):
        regs = self.registers if registers is None else registers
        return CounterpartyGate.over(self.book, regs, now=NOW, latest=regs.get if latest else None,
                                     profile=self.profiles.get)

    def faults(self, key=RESOLVER, **kw):
        return accept_faults(self.wants_ride.requires.resolvers, key, parties=(TRAVELLER, DRIVER),
                             requirer=self.wants_ride, ontology=_cat(), gate=self.gate(**kw))

    def clearing(self):
        return BookClearing(self.book, _cat(), clock=lambda: NOW,
                            register_at=lambda rid, root: Register(RecordStore.at(root, self.blobs)),
                            register_latest=self.registers.get, resolver_profile=self.profiles.get)


def test_an_accredited_bonded_clean_resolver_is_accepted_and_the_loop_clears():
    w = World()
    assert w.faults() == []
    assert check_match(w.ride, w.wants_ride, _cat(), now=NOW, gate=w.gate()) is not None
    assert check_match(w.ride, w.wants_ride, _cat(), now=NOW) is None            # no reads, no pass (U7)
    assert named_registers([w.wants_ride]) == {ASSOC}                            # the root the proposal pins
    agent = SolverAgent(w.book, _cat(), clearing=w.clearing(), solver_id="t", registers=w.registers,
                        register_latest=w.registers.get, resolver_profile=w.profiles.get)
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True]
    assert w.book.store.get(f"loop/{receipts[0].loop_id}")["register_roots"] == {ASSOC: w.assoc.root}
    # a solver without the association's register proposes nothing (its gate refuses) ...
    w = World()
    assert SolverAgent(w.book, _cat(), clearing=w.clearing(), solver_id="t",
                       resolver_profile=w.profiles.get).step(now=NOW) == []
    # ... and a hand-built proposal leaving the named root unpinned is refused at clearing (R3a, U3)
    from loopmarket.clearing import LoopProposal
    from loopmarket.graph import Loop
    from loopmarket.matching import Match
    loop = Loop((Match(give=w.ride, want=w.wants_ride), Match(give=w.lesson, want=w.wants_lesson)))
    r = w.clearing().submit(LoopProposal(loop, w.book.store.root, "", "t", NOW, ()))
    assert not r.accepted and ASSOC in r.reason
    r = w.clearing().submit(LoopProposal(loop, w.book.store.root, "", "t", NOW, ((ASSOC, w.assoc.root),)))
    assert r.accepted


def test_each_missing_property_is_refused_with_its_reason():
    # who: no statement; a category outside arbitrator; a self-bonded "accreditation"
    assert "no arbitrator statement presented" in World(statement=False).faults()[0]
    assert "1 category dentist-licensed is not under arbitrator" in World(category="dentist-licensed").faults()[0]
    assert "does not accredit" in World(kind="self-bonded").faults()[0]
    # revoked under the association's root; the root unpinned; no newest-root reader
    w = World()
    w.assoc.revoke(w.statement.statement_id, NOW - 10)
    w.assoc.commit()
    assert "3 revoked" in w.faults()[0]
    assert "on the path is not pinned" in World().faults(registers={})[0]
    assert "no reader of the registers' newest roots" in World().faults(latest=False)[0]
    # an accreditation under a root the traveller did not name
    assert "not a trust root named" in World(Accept(roots=(OTHER,))).faults()[0]
    # the deposit: 10 on her scale at 2 per xDAI is 5 xDAI; 4 at stake is short
    assert "less than 5 for the floor 10" in World(profile=_profile(deposit=4)).faults()[0]
    assert World(profile=_profile(deposit=5)).faults() == []
    assert "no deposit at stake" in World(profile=_profile(deposit=None)).faults()[0]
    assert "to price the deposit floor" in World(profile=_profile(asset=(("eur",), "EUR"))).faults()[0]
    # the record: a reversal within the year; a record that starts inside it; no appeal ledger
    assert "reversed within the last" in World(profile=_profile(reversals=(NOW - 30 * 86_400,))).faults()[0]
    assert World(profile=_profile(reversals=(NOW - 2 * YEAR + 10,))).faults() == []   # outside the look-back
    assert "starts inside" in World(profile=_profile(since=NOW - 30 * 86_400)).faults()[0]
    assert "no appeal ledger" in World(profile=_profile(reversals=None)).faults()[0]
    # every rung that can rule must be accredited: an unaccredited final arbiter refuses
    assert any(FINAL in f for f in World(profile=_profile(rulers=(ARB, FINAL))).faults())
    # never a party, nor a contract ruling through one
    w = World(profile=_profile(rulers=(TRAVELLER,)))
    assert "a party to the leg" in w.faults()[0]
    # issuance (D8) is not read yet: it admits nothing
    assert "issuance" in World(Accept(keys=(RESOLVER,), issuance=("eu-lotl",))).faults()[0]
    # the gate refuses the leg on any of them
    w = World(profile=_profile(deposit=1))
    assert check_match(w.ride, w.wants_ride, _cat(), now=NOW, gate=w.gate()) is None


def test_a_named_key_still_admits_without_reads_and_roots_are_an_alternative():
    assert admits(Accept(keys=(RESOLVER,)), RESOLVER, parties=(TRAVELLER, DRIVER))
    w = World(Accept(keys=("0x" + "99" * 20,), roots=(ASSOC,)))
    assert w.faults() == []                                  # not named, but accredited: the alternative
    assert "not a named key" in World(Accept(keys=("0x" + "99" * 20,))).faults()[0]


def test_both_sides_accept_and_one_resolver_is_chosen_deterministically():
    """A give naming no arbitrator states its own acceptance; the resolver
    is the first key, in sorted order, both sides admit — the same in the
    solver's gate and in the reservation."""
    from types import SimpleNamespace
    from loopmarket.escrow import reservations_for
    from loopmarket.matching import Leg
    J1, J2, J3 = ("0x" + c * 40 for c in "123")
    none = {k: Profile(rulers=(k,)) for k in (J1, J2, J3)}
    w = World(Accept(keys=(J3, J2)), arbitrator="", give_requires=Requires(resolvers=Accept(keys=(J1, J2))))
    w.profiles.update(none)
    assert resolver_of(w.wants_ride, w.ride, gate=w.gate(), ontology=_cat()) == J2
    assert check_match(w.ride, w.wants_ride, _cat(), now=NOW, gate=w.gate()) is not None
    loop = SimpleNamespace(circulation=SimpleNamespace(legs=(Leg(w.wants_ride, (w.ride,)),), loop_id="ab" * 32))
    (r,) = reservations_for(loop, escrow="0xE", resolver=J1, claim_seconds=86_400, now=NOW, gate=w.gate(),
                            ontology=_cat())
    assert r["resolver"] == J2                               # not the clearing's J1: the want does not take it
    # no key both admit: refused in the gate, raised at the reservation
    w = World(Accept(keys=(J3,)), arbitrator="", give_requires=Requires(resolvers=Accept(keys=(J1,))))
    assert check_match(w.ride, w.wants_ride, _cat(), now=NOW, gate=w.gate()) is None
    # by property on both sides with no name anywhere: no candidate, refused (U7)
    w = World(arbitrator="", give_requires=Requires(resolvers=Accept(roots=(ASSOC,))))
    assert resolver_of(w.wants_ride, w.ride, gate=w.gate(), ontology=_cat()) is None
    # the give's own arbitrator comes first when the want admits it
    w = World(give_requires=Requires(resolvers=Accept(keys=(J1,))))
    assert resolver_of(w.wants_ride, w.ride, gate=w.gate(), ontology=_cat()) == RESOLVER


def test_a_required_legs_giver_is_admitted_by_accreditation_for_the_legs_category():
    w = World(category="vehicle-inspector", subject=DRIVER)
    faults = accept_faults(Accept(roots=(ASSOC,)), DRIVER, parties=(TRAVELLER,), requirer=w.wants_ride,
                           ontology=_cat(), gate=w.gate(), category="inspect")
    assert faults == []
    faults = accept_faults(Accept(roots=(ASSOC,)), DRIVER, parties=(TRAVELLER,), requirer=w.wants_ride,
                           ontology=_cat(), gate=w.gate(), category="arbitrator")
    assert "is not under arbitrator" in faults[0]            # an inspector is not an arbitrator


# -- the chain's record, on a local EVM ------------------------------------------------

def test_the_chain_profile_reads_factbonds_rungs_deposit_and_reversals():
    """`chain_profile` against factbond's `Assertions` (the sibling
    checkout): a key with no code rules itself; a one-rung contract has
    nothing at stake (its rulings are final); with an arbiter, what a
    reversal forfeits is the rung's deposit up to `depositWei`, and a
    reversal appears in the record."""
    pytest.importorskip("solcx")
    import solcx
    from web3 import EthereumTesterProvider, Web3
    from loopmarket.arbitrators import chain_profile
    src = os.path.join(HERE, "..", "..", "factbond", "contracts", "Assertions.sol")
    if not os.path.exists(src):
        pytest.skip("needs ../factbond (contracts/Assertions.sol)")
    solcx.install_solc("0.8.24")
    compiled = solcx.compile_files([src], output_values=["abi", "bin"], solc_version="0.8.24", optimize=True,
                                   optimize_runs=200, via_ir=True, allow_paths=os.path.dirname(src))
    art = next(v for k, v in compiled.items() if k.endswith(":Assertions"))
    w3 = Web3(EthereumTesterProvider())
    acct = w3.eth.accounts
    w3.eth.default_account = acct[0]
    adjudicator, arbiter, treasury, asserter, challenger = acct[5], acct[6], acct[9], acct[2], acct[3]
    fee, floor, deposit_wei = 10 ** 15, 10 ** 16, 3 * 10 ** 16

    def deploy(ladder):
        r = w3.eth.wait_for_transaction_receipt(w3.eth.contract(abi=art["abi"], bytecode=art["bin"]).constructor(
            adjudicator, treasury, fee, floor, 100, 10, 60 * 86400, 100, 90 * 86400, 4 * 10 ** 15,
            ladder).transact())
        return w3.eth.contract(address=r["contractAddress"], abi=art["abi"])

    assert chain_profile(acct[7], client=w3) == Profile(rulers=(acct[7],))
    one = deploy(("0x" + "00" * 20, 0, 0, 0))
    one.functions.postDeposit().transact({"from": adjudicator, "value": deposit_wei})
    p = chain_profile(one.address, client=w3)
    assert p.rulers == (adjudicator,) and p.deposit == 0 and p.reversals == () and p.since is not None
    two = deploy((arbiter, 2 * 10 ** 15, 50, deposit_wei))
    two.functions.postDeposit().transact({"from": adjudicator, "value": 2 * deposit_wei})
    p = chain_profile(two.address, client=w3)
    assert p.rulers == (adjudicator, arbiter) and p.deposit * 10 ** 18 == deposit_wei and p.reversals == ()
    assert p.asset == (("xdai",), "xDAI")
    # a ruling reversed on appeal enters the record
    two.functions.assert_(b"\xa4" * 32, "0x" + "00" * 20, 5, 990, 0, 0, challenger).transact(
        {"from": asserter, "value": fee + floor})
    id_ = two.functions.count().call()
    stake = two.functions.stakeFor(floor, 990).call()
    two.functions.dispute(id_).transact({"from": challenger, "value": stake})
    two.functions.rule(id_, True).transact({"from": adjudicator})
    two.functions.appeal(id_).transact({"from": challenger, "value": 2 * stake + 2 * 10 ** 15})
    two.functions.ruleAppeal(id_, False).transact({"from": arbiter})
    p = chain_profile(two.address, client=w3)
    assert len(p.reversals) == 1 and p.deposit * 10 ** 18 == deposit_wei     # a second deposit's worth left
    assert chain_profile(w3.eth.wait_for_transaction_receipt(w3.eth.contract(
        abi=[], bytecode="0x6001600c60003960016000f300").constructor().transact())["contractAddress"],
        client=w3) is None                                                       # not a contract it knows
