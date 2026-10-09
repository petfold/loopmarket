"""Registers (R3a, 2026-09-29; `docs/plans/counterparty-gate.md` §3.3): a
register's own book — `status/`, `revoked/`, `suspended/`, `accredit/` —
announced under the `register` role and never folded into the offer book;
a proposal pins every register its legs' requirements name as a trust root
(`register_roots`, U4), the loop record carrying them as its v2; clearing
refuses a proposal missing one before any leg work (U3, U7). Absence under
a pinned root is a proof anyone verifies without a store."""

import pytest
from ontodag import OntoDAG
from recordstore import ABSENT, MemoryBytesStore, RecordStore, verify_proof

from loopmarket import (
    Aggregator, Credential, BookClearing, OfferRegistry, Ontology, Requires, Thing, TimeWindow, give, want,
)
from loopmarket.announce import REGISTER, open_announcements
from loopmarket.beat import proposal_from_record
from loopmarket.clearing import LoopProposal
from loopmarket.federation import audit_manifest
from loopmarket.graph import Loop
from loopmarket.matching import Match
from loopmarket.register import Register, named_registers

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
SID, OTHER = "5a" * 32, "5b" * 32
ROOT = "0x" + "11" * 20


def test_a_register_holds_statuses_and_accreditations_revocation_is_monotone():
    reg = Register(RecordStore(MemoryBytesStore()))
    reg.issue(SID, 100)
    reg.issue(OTHER, 100)
    reg.suspend(OTHER, 200)
    assert reg.suspended(OTHER) and reg.status(OTHER)["state"] == "suspended"
    reg.reinstate(OTHER, 300)
    assert not reg.suspended(OTHER) and reg.status(OTHER) == {"state": "issued", "at": 300}
    reg.revoke(SID, 400)
    assert reg.revoked(SID) and reg.status(SID)["state"] == "revoked"
    with pytest.raises(ValueError, match="stays revoked"):
        reg.issue(SID, 500)
    with pytest.raises(ValueError, match="stays revoked"):
        reg.reinstate(SID, 500)
    reg.accredit("0xissuer", "dentist-licensed", by=ROOT, since=0, until=10_000, scheme="5c" * 32)
    assert reg.accreditation("0xissuer", "dentist-licensed")["scheme"] == "5c" * 32
    assert list(reg.accreditations("0xissuer")) == [("dentist-licensed", reg.accreditation("0xissuer", "dentist-licensed"))]
    with pytest.raises(ValueError, match="later until"):
        reg.accredit("0xissuer", "c", by=ROOT, since=5, until=5)
    root = reg.commit()
    # "not revoked" is a proof under the pinned root, checkable without the store
    frozen = Register(RecordStore.at(root, reg.store.blobs))
    absent, present = frozen.prove("revoked/" + OTHER), frozen.prove("revoked/" + SID)
    assert verify_proof(absent, root) is ABSENT and verify_proof(present, root) == {"at": 400}


def test_a_register_is_announced_and_never_folded():
    blobs = MemoryBytesStore()
    reg = Register(RecordStore(blobs))
    reg.issue(SID, 100)
    reg.commit()
    maker = OfferRegistry(RecordStore(blobs))
    maker.publish(give("amara", Thing(("apple",), 1), 5, **V, nonce=1))
    maker.commit()
    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce("amara", maker.store)
    agg.announce(ROOT, reg.store, role=REGISTER)
    m = agg.fold()
    book = RecordStore.at(m.book_root, blobs)
    assert not any(k.startswith("status/") for k in book.keys(""))
    announced = RecordStore.at(m.announcement_root, blobs)
    assert announced.get(f"announce/{ROOT}") == {"role": "register", "root": reg.root}
    rejected = list(RecordStore.at(m.provenance_root, blobs).keys("reject/")) if m.provenance_root else []
    assert not any(k.startswith(f"reject/{ROOT}/") for k in rejected)   # a register's keys accuse nobody
    assert audit_manifest(m, blobs) == []
    # the channel carries the role
    channel = open_announcements("memory:r3a")
    channel.announce("rs:/register", REGISTER, owner=ROOT)
    assert [(a.owner, a.role) for a in channel.announced()] == [(ROOT, "register")]


def _two_leg_book():
    """A two-maker cycle whose want names a trust root: the proposal must
    pin that register."""
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": []})
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    picky = want("b", Thing(("apple",), 3), 15, **V, nonce=1,
                 requires=Requires(counterparty=(Credential("grower", ("attested",), roots=(ROOT,),
                                                            max_root_age=86_400),)))
    offers = [picky, give("a", Thing(("apple",), 3), 9, **V, nonce=2),
              give("b", Thing(("lesson",)), 10, **V, nonce=3), want("a", Thing(("lesson",)), 11, **V, nonce=4)]
    book.publish_many(offers)
    book.commit()
    loop = Loop((Match(give=offers[1], want=offers[0]), Match(give=offers[2], want=offers[3])))
    return cat, book, offers, loop


def test_a_proposal_missing_a_named_registers_root_is_refused():
    cat, book, offers, loop = _two_leg_book()
    assert named_registers(offers) == {ROOT}
    clearing = BookClearing(book, cat, clock=lambda: NOW)
    bare = LoopProposal(loop, book.store.root, cat.root, "t", NOW)
    assert clearing.rehearse(bare).reason == f"unpinned register: {ROOT}"
    empty = LoopProposal(loop, book.store.root, cat.root, "t", NOW, ((ROOT, ""),))
    assert clearing.rehearse(empty).reason == f"unpinned register: {ROOT}"
    pinned = LoopProposal(loop, book.store.root, cat.root, "t", NOW, ((ROOT, "ab" * 32),))
    verdict = clearing.rehearse(pinned)
    assert not verdict.accepted and verdict.reason.startswith("leg fails re-verification")   # the gate is R4's
    # the loop record: v2 carries the pins, v1 (none) is as before
    rec = pinned.to_record()
    assert rec["v"] == 2 and rec["register_roots"] == {ROOT: "ab" * 32}
    back = proposal_from_record(rec, book)
    assert back.register_roots == ((ROOT, "ab" * 32),) and back.circulation.loop_id == loop.loop_id
    plain = bare.to_record()
    assert plain["v"] == 1 and "register_roots" not in plain
    with pytest.raises(ValueError, match="carries register_roots"):
        proposal_from_record(dict(plain, v=2), book)



def test_every_root_names_its_predecessor_and_its_number():
    """R5: `commit` links each root to the one it supersedes; nothing staged,
    no new link."""
    reg = Register(RecordStore(MemoryBytesStore()))
    assert reg.seq == -1 and reg.predecessor is None
    reg.issue(SID, 100)
    first = reg.commit()
    assert (reg.seq, reg.predecessor) == (0, None)
    assert reg.commit() == first and reg.seq == 0
    reg.revoke(SID, 200)
    second = reg.commit()
    assert (reg.seq, reg.predecessor) == (1, first)
    reg.heartbeat(300)
    reg.commit()
    assert (reg.seq, reg.predecessor, reg.as_of) == (2, second, 300)


def test_a_root_that_drops_a_revocation_does_not_extend_its_predecessor():
    from recordstore import verify_extension
    reg = Register(RecordStore(MemoryBytesStore()))
    reg.issue(SID, 100)
    reg.revoke(SID, 200)
    revoked = reg.commit()
    reg.issue(OTHER, 300)
    reg.commit()
    assert reg.extends_predecessor() is True
    # the proof travels: anyone checks it with no store
    assert verify_extension(reg.extension_proof(), revoked, reg.root) == ("revoked/",)
    # an un-revocation, written past Register's own refusal
    reg.store.delete("revoked/" + SID)
    reg.store.put("status/" + SID, {"state": "issued", "at": 400})
    reg.commit()
    assert reg.extends_predecessor() is False and reg.extends(revoked) is False
    with pytest.raises(ValueError, match="absent"):
        reg.extension_proof()
    # a store that cannot say is not a pass
    class Opaque:
        def __init__(self, store):
            self.inner = store

        def __getattr__(self, name):
            if name == "extends":
                raise AttributeError(name)
            return getattr(self.inner, name)
    assert Register(Opaque(reg.store)).extends_predecessor() is None
