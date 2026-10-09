"""The counterparty gate, the dentist case in memory (R4, 2026-09-29;
`docs/plans/counterparty-gate.md` §4, plan D7). A patient's want requires a
licensed dentist: a statement of `dentist-licensed`, attested, reaching the
chamber as trust root, its registers no older than a day, valid through the
appointment, backed by a deposit whose free share covers her floor; and a
resolver she accepts. The dentist presents an attested statement in his own
book (R2), the attester's and the chamber's registers are pinned (R3a).
The licensed case solves and clears; revoked, suspended, expired before the
appointment, unaccredited, a silent or stale register, a floor not free, an
unpinned register on the path and an unaccepted resolver are each refused,
the failing steps listed (plan E4).

Here the dentist is his own maker (the solo form; a practice attesting for
its dentists is the same statement with the practice as subject, the
person at the door bound by R7's witness)."""

from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Accept, Acceptance, Bond, Credential, MockClearing, OfferRegistry, Ontology, Requires, SolverAgent,
    Statement, Thing, TimeWindow, give, want,
)
from loopmarket.clearing import LoopProposal
from loopmarket.gate import CounterpartyGate
from loopmarket.graph import Loop
from loopmarket.matching import Match, check_match
from loopmarket.register import Register

NOW = 1_790_000_000
T = "2026-10-01T10:00:00Z..2026-10-01T11:00:00Z"
WINDOW = (1_790_848_800, 1_790_852_400)
SPANS = {T: WINDOW}
D, P = "0x" + "d0" * 20, "0x" + "a0" * 20           # the dentist, the patient
ATTESTER, CHAMBER, JUDGE = "0x" + "a7" * 20, "0x" + "c4" * 20, "0x" + "77" * 20
EUR = Acceptance(("stablecoin-eur",), "EUR", 1)
V = dict(valid=TimeWindow(NOW - 10, NOW + 30 * 86_400))


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_handover(["geo", "time"])
    cat.load({"dentistry": [], "lesson": [], "licence": [], "dentist-licensed": ["licence"],
              "stablecoin-eur": []})
    return cat


class World:
    """The dentist's book, the two registers, and the offers of the loop."""

    def __init__(self, *, until=WINDOW[1] + 86_400, accredit=True, heartbeat=NOW - 100, arbitrator=JUDGE,
                 pins=None):
        V = dict(valid=TimeWindow(NOW - 10, NOW + 30 * 86_400), **(pins or {}))
        self.blobs = MemoryBytesStore()
        self.book = OfferRegistry(RecordStore(self.blobs))
        # ten visits, a 500 EUR deposit: this fill reserves 50, the rest backs the statement
        self.dentist = give(D, Thing(("dentistry", f"time({T})"), 10, "visit", step=1), 300, **V, nonce=1,
                            bond=Bond(Thing(("stablecoin-eur",), 500, "EUR"), 500, "0xE"), arbitrator=arbitrator)
        self.patient = want(P, Thing(("dentistry", f"time({T})"), 1, "visit"), 40, **V, nonce=2,
                            requires=Requires(accepts=(EUR,), resolvers=Accept(keys=(JUDGE,)),
                                              counterparty=(Credential("dentist-licensed", ("attested", "self-bonded"),
                                                                       min_bond=20, roots=(CHAMBER,),
                                                                       max_root_age=86_400),)))
        self.lesson = give(P, Thing(("lesson",), 1, "hour"), 10, **V, nonce=3)
        self.wants_lesson = want(D, Thing(("lesson",), 1, "hour"), 35, **V, nonce=4)   # worth more than a visit to him
        self.book.publish_many([self.dentist, self.patient, self.lesson, self.wants_lesson])
        self.statement = Statement(subject=D, category="dentist-licensed", issuer=ATTESTER, kind="attested",
                                   as_of=NOW - 1_000, until=until, evidence="ee" * 32, path=(ATTESTER, CHAMBER),
                                   paid_by="subject", deposit=(self.dentist.offer_id, "0xE"))
        self.book.present(self.statement)
        self.book.commit()
        self.attester = Register(RecordStore(self.blobs))
        self.attester.issue(self.statement.statement_id, NOW - 1_000)
        self.chamber = Register(RecordStore(self.blobs))
        if accredit:
            self.chamber.accredit(ATTESTER, "licence", by=CHAMBER, since=NOW - 86_400 * 365,
                                  until=NOW + 86_400 * 365, scheme="5c" * 32)
        for reg in (self.attester, self.chamber):
            if heartbeat is not None:
                reg.heartbeat(heartbeat)
            reg.commit()

    @property
    def registers(self):
        return {ATTESTER: self.attester, CHAMBER: self.chamber}

    def gate(self, registers=None, held=None):
        return CounterpartyGate.over(self.book, self.registers if registers is None else registers, now=NOW,
                                     span=SPANS.get, held=held)

    def faults(self, **kw):
        return self.gate(**kw).faults(self.patient, self.dentist, _cat(), window=WINDOW, taken=1, whole=10)

    def clearing(self, held=None):
        return MockClearing(self.book, _cat(), clock=lambda: NOW, span=SPANS.get,
                            escrow_held=held, register_at=lambda rid, root: Register(RecordStore.at(root, self.blobs)))

    def proposal(self, roots=None):
        loop = Loop((Match(give=self.dentist, want=self.patient), Match(give=self.lesson, want=self.wants_lesson)))
        pins = tuple(sorted((r, reg.root) for r, reg in self.registers.items())) if roots is None else roots
        return LoopProposal(loop, self.book.store.root, "", "t", NOW, pins)


def test_a_licensed_dentist_passes_the_gate_and_the_loop_clears():
    w = World()
    assert w.faults() == []
    assert check_match(w.dentist, w.patient, _cat(), now=NOW, gate=w.gate()) is not None
    assert check_match(w.dentist, w.patient, _cat(), now=NOW) is None             # no gate, no pass (U7)
    clearing = w.clearing()
    agent = SolverAgent(w.book, _cat(), clearing=clearing, solver_id="t", registers=w.registers, span=SPANS.get)
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True]
    rec = w.book.store.get(f"loop/{receipts[0].loop_id}")
    assert rec["v"] == 2 and rec["register_roots"] == {ATTESTER: w.attester.root, CHAMBER: w.chamber.root}


def test_each_failure_is_refused_with_its_step_named():
    # revoked, and suspended, under the attester's pinned root
    w = World()
    w.attester.revoke(w.statement.statement_id, NOW - 10)
    w.attester.commit()
    assert any(f.startswith("dentist-licensed: ") and "3 revoked" in f for f in w.faults())
    w = World()
    w.attester.suspend(w.statement.statement_id, NOW - 10)
    w.attester.commit()
    assert "7 suspended" in w.faults()[0]
    # expired before the appointment
    assert "5 valid" in World(until=WINDOW[0] - 1).faults()[0]
    # the attester not accredited by the chamber
    assert "2 " + ATTESTER + " is not accredited by " + CHAMBER in World(accredit=False).faults()[0]
    # a silent register, and one whose root is older than the requirer's bound
    assert "4 register" in World(heartbeat=None).faults()[0] and "silent" in World(heartbeat=None).faults()[0]
    assert "more than 86400s" in World(heartbeat=NOW - 2 * 86_400).faults()[0]
    # the floor not free: the escrow holds 60 of the 500; this fill reserves 50, leaving 10 of the 20 needed
    w = World()
    assert "6 " in w.faults(held={w.dentist.offer_id: 60})[0]
    assert w.faults(held={w.dentist.offer_id: 70}) == []
    # a register on the path the proposal did not pin
    assert "2 register " + ATTESTER + " on the path is not pinned" in w.faults(registers={CHAMBER: w.chamber})[0]
    # an unaccepted resolver: the dentist names someone the patient does not accept
    w = World(arbitrator="0x" + "78" * 20)
    assert w.faults() == [] and check_match(w.dentist, w.patient, _cat(), now=NOW, gate=w.gate()) is None


def test_clearing_lists_every_failing_step_in_one_refusal():
    """Plan E4: the refusal enumerates every discrepancy, so one
    re-presentation cures them all."""
    w = World(until=WINDOW[0] - 1, heartbeat=NOW - 2 * 86_400)
    receipt = w.clearing().rehearse(w.proposal())
    assert not receipt.accepted and "the counterparty gate:" in receipt.reason
    assert "4 register" in receipt.reason and "5 valid" in receipt.reason
    # a proposal pinning none of the registers is refused before any leg work
    assert w.clearing().rehearse(w.proposal(roots=())).reason == f"unpinned register: {CHAMBER}"
    # the licensed world rehearses clean, and a self-bonded dentist needs no register
    assert World().clearing().rehearse(World().proposal()).accepted


def test_a_self_bonded_statement_is_backed_by_its_deposit_alone():
    """The degenerate case: the dentist's own declaration, backed by his
    deposit, meets an entry that names no trust root."""
    cat = _cat()
    blobs = MemoryBytesStore()
    book = OfferRegistry(RecordStore(blobs))
    dentist = give(D, Thing(("dentistry",), 10, "visit", step=1), 300, **V, nonce=1,
                   bond=Bond(Thing(("stablecoin-eur",), 500, "EUR"), 500, "0xE"))
    patient = want(P, Thing(("dentistry",), 1, "visit"), 40, **V, nonce=2,
                   requires=Requires(accepts=(EUR,), counterparty=(
                       Credential("dentist-licensed", ("self-bonded",), min_bond=20),)))
    book.publish_many([dentist, patient])
    book.present(Statement(subject=D, category="dentist-licensed", issuer=D, kind="self-bonded", as_of=NOW - 10,
                           until=NOW + 86_400, evidence="ee" * 32, path=(D,), paid_by="subject",
                           deposit=(dentist.offer_id, "0xE")))
    book.commit()
    gate = CounterpartyGate.over(book, {}, now=NOW)
    assert check_match(dentist, patient, cat, now=NOW, gate=gate) is not None
    assert check_match(dentist, patient, cat, now=NOW,
                       gate=CounterpartyGate.over(book, {}, now=NOW, held={dentist.offer_id: 60})) is None



def test_a_stale_pin_cannot_hide_a_revocation_and_a_root_cannot_drop_one():
    """R5 (option A, 2026-09-29). The proposal pins the attester's root from
    before the revocation: with the register's feed read (`latest`), the
    newer root published by the clearing's clock refuses the leg; one
    published after it does not count; without a reader, the age bound is
    all there is. A register root that un-revokes anything is refused
    whoever pins it."""
    w = World()
    pinned = {r: Register(RecordStore.at(reg.root, w.blobs)) for r, reg in w.registers.items()}
    w.attester.revoke(w.statement.statement_id, NOW - 60)
    w.attester.heartbeat(NOW - 50)
    w.attester.commit()

    def faults(latest):
        gate = CounterpartyGate.over(w.book, pinned, now=NOW, span=SPANS.get, latest=latest)
        return gate.faults(w.patient, w.dentist, _cat(), window=WINDOW, taken=1, whole=10)

    newest = {ATTESTER: w.attester, CHAMBER: pinned[CHAMBER]}.get
    assert faults(None) == []
    assert any("3 revoked under " + ATTESTER + "'s newest root" in f for f in faults(newest))
    later = World()
    later_pinned = {r: Register(RecordStore.at(reg.root, later.blobs)) for r, reg in later.registers.items()}
    later.attester.revoke(later.statement.statement_id, NOW + 5)
    later.attester.heartbeat(NOW + 10)                  # after the clearing's clock: not yet said
    later.attester.commit()
    gate = CounterpartyGate.over(later.book, later_pinned, now=NOW, span=SPANS.get,
                                 latest={ATTESTER: later.attester}.get)
    assert gate.faults(later.patient, later.dentist, _cat(), window=WINDOW, taken=1, whole=10) == []
    # clearing reads the feed too: the stale proposal is refused (U3)
    clearing = MockClearing(w.book, _cat(), clock=lambda: NOW, span=SPANS.get,
                            register_at=lambda rid, root: Register(RecordStore.at(root, w.blobs)),
                            register_latest=newest)
    receipt = clearing.rehearse(w.proposal(roots=tuple(sorted((r, reg.root) for r, reg in pinned.items()))))
    assert not receipt.accepted and "newest root" in receipt.reason
    # a root that drops another statement's revocation is refused at its own pin
    w = World()
    w.attester.revoke("5e" * 32, NOW - 70)
    w.attester.commit()
    w.attester.store.delete("revoked/" + "5e" * 32)
    w.attester.heartbeat(NOW - 40)
    w.attester.commit()
    assert any("drops a revocation its predecessor held" in f for f in w.faults())
