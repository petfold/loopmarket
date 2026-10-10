"""Whose deposit backs a statement, and what it locks (ontodag's review item
24, question 27, decided by Peter 2026-10-10: A). A statement's deposit is
put up by whoever stands behind the statement, its subject or its issuer
(a practice attesting for its dentists), never borrowed from another
maker; step 6 counts only what the escrow has free; and when a leg relies
on the statement, the clearing reserves the floor on that deposit for the
leg's claim period (D1), so a refutation has something to claim."""

import pytest

from loopmarket import Bond, Reads, SolverAgent, Statement, Thing, give
from loopmarket.escrow import reservations_for, statement_slot, to_wei

from test_escrow import _HAVE_EVM
from test_gate import ATTESTER, CHAMBER, D, JUDGE, NOW, P, SPANS, T, V, WINDOW, World, _cat

M, KOVAC = "0x" + "e1" * 20, D          # Mallory, and Dr Kovač, the dentist of the World


def _entry(w):
    return w.patient.requires.counterparty[0]


def test_a_self_bonded_statement_cannot_borrow_another_makers_deposit():
    """Mallory declares herself a dentist, self-bonded, naming Dr Kovač's
    deposit: the deposit is not hers, so step 6 refuses it, whatever is
    free of it."""
    w = World()
    mallory = give(M, Thing(("dentistry", f"time({T})"), 10, "visit", step=1), 300, **V, nonce=7)
    w.book.publish(mallory)
    claim = Statement(subject=M, category="dentist-licensed", issuer=M, kind="self-bonded", as_of=NOW - 10,
                      until=WINDOW[1] + 86_400, evidence="ee" * 32, path=(M,), paid_by="subject",
                      deposit=(w.dentist.offer_id, "0xE"))
    w.book.present(claim)
    w.book.commit()
    faults = w.gate().statement_faults(_entry(w), claim, w.patient, mallory, _cat(), window=WINDOW,
                                       taken=1, whole=10)
    assert f"6 the deposit {w.dentist.offer_id[:12]} is {KOVAC}'s, not the statement's subject's or issuer's" \
        in faults                                     # (and step 2: the entry names a trust root she lacks)
    assert w.faults() == []                                         # Kovač's own statement stands


def test_a_practice_backs_its_dentists_statement_and_a_stranger_cannot():
    """The attester (a practice) attests that Kovač is licensed and backs it
    with its own deposit: it stands behind the statement, so the deposit
    counts. The same statement backed by a third maker's deposit does not."""
    w = World()
    practice = give(ATTESTER, Thing(("licence",), 1, "attestation"), 1, **V, nonce=8,
                    bond=Bond(Thing(("stablecoin-eur",), 500, "EUR"), 500, "0xE"))
    stranger = give(M, Thing(("licence",), 1, "attestation"), 1, **V, nonce=9,
                    bond=Bond(Thing(("stablecoin-eur",), 500, "EUR"), 500, "0xE"))
    w.book.publish_many([practice, stranger])
    backed = {}
    for name, deposit in (("practice", practice), ("stranger", stranger)):
        s = Statement(subject=KOVAC, category="dentist-licensed", issuer=ATTESTER, kind="attested",
                      as_of=NOW - 1_000, until=WINDOW[1] + 86_400, evidence="ef" * 32,
                      path=(ATTESTER, CHAMBER), paid_by="subject", deposit=(deposit.offer_id, "0xE"))
        w.book.present(s)
        w.attester.issue(s.statement_id, NOW - 1_000)
        backed[name] = s
    w.book.commit()
    w.attester.heartbeat(NOW - 100)
    w.attester.commit()
    gate = w.gate()
    assert gate.statement_faults(_entry(w), backed["practice"], w.patient, w.dentist, _cat(),
                                 window=WINDOW, taken=1, whole=10) == []
    assert gate.statement_faults(_entry(w), backed["stranger"], w.patient, w.dentist, _cat(),
                                 window=WINDOW, taken=1, whole=10) == \
        [f"6 the deposit {stranger.offer_id[:12]} is {M}'s, not the statement's subject's or issuer's"]


def test_step_six_counts_only_what_the_escrow_has_free():
    """The escrow holds all 500 of Kovač's deposit, but other loops have
    reserved 440 of it: 60 is free, this fill's own share takes 50, and the
    10 left is less than the floor of 20. Read with `held` alone, every
    reservation already made would be counted again."""
    w = World()
    held = {w.dentist.offer_id: 500}
    assert w.faults(held=held) == []
    assert "6 " in w.faults(held=held, free={w.dentist.offer_id: 60})[0]
    assert w.faults(held=held, free={w.dentist.offer_id: 70}) == []


def test_the_clearing_and_the_solver_read_the_escrows_free_share():
    w = World()
    full = lambda oid: 500                                           # noqa: E731
    receipt = w.clearing(reads=Reads(escrow_held=full, escrow_free=lambda oid: 60)).rehearse(w.proposal())
    assert not receipt.accepted and "6 " in receipt.reason
    assert w.clearing(reads=Reads(escrow_held=full, escrow_free=lambda oid: 70)).rehearse(w.proposal()).accepted
    starved = SolverAgent(w.book, _cat(), None, solver_id="t", registers=w.registers, span=SPANS.get,
                          reads=Reads(escrow_held=full, escrow_free=lambda oid: 60))
    assert starved.find_loops(now=NOW)[1] == []


def test_the_clearing_reserves_the_floor_per_relying_leg():
    """Kovač's give reserves its own share of his deposit for the fill (50
    of 500 for one visit of ten), and the patient relies on his statement,
    which his deposit backs: the floor, 20, is reserved too, for her, in a
    slot of its own (the escrow keeps one reservation per offer and loop)."""
    w = World()
    proposal = w.proposal()
    loop_id = proposal.circulation.loop_id
    rs = reservations_for(proposal, escrow="0xE", resolver=JUDGE, claim_seconds=86_400, now=NOW,
                          span=SPANS.get, gate=w.gate(), ontology=_cat())
    by_slot = {r["loop_id"]: r for r in rs}
    slot = statement_slot(loop_id, w.patient.offer_id, w.statement.statement_id)
    assert set(by_slot) == {loop_id, slot} and slot != loop_id
    share, floor = by_slot[loop_id], by_slot[slot]
    assert (share["offer_id"], share["amount"]) == (w.dentist.offer_id, to_wei(50))
    assert (floor["offer_id"], floor["amount"], floor["wanter"], floor["resolver"]) == \
        (w.dentist.offer_id, to_wei(20), P, JUDGE)
    assert floor["statement"] == w.statement.statement_id and floor["relied_in"] == loop_id
    assert floor["window"] == WINDOW and floor["claim_seconds"] == share["claim_seconds"]
    assert not floor["claim_only"] and floor["ladder"] == [] and floor["deductible"] == 0


def test_a_floor_on_another_escrow_is_not_this_escrows_to_reserve():
    w = World()
    rs = reservations_for(w.proposal(), escrow="0xF", resolver=JUDGE, claim_seconds=86_400, now=NOW,
                          span=SPANS.get, gate=w.gate(), ontology=_cat())
    assert rs == []


def test_without_a_gate_a_relied_on_statement_cannot_be_chosen():
    w = World()
    with pytest.raises(ValueError, match="needs the gate"):
        reservations_for(w.proposal(), escrow="0xE", resolver=JUDGE, claim_seconds=86_400, now=NOW,
                         span=SPANS.get)


def test_the_slot_is_one_per_loop_leg_and_statement():
    a, b, c = "a1" * 32, "b2" * 32, "c3" * 32
    slots = {statement_slot(a, b, c), statement_slot(b, a, c), statement_slot(a, b, b), statement_slot(a, c, c)}
    assert len(slots) == 4 and all(len(s) == 64 for s in slots)


@pytest.mark.skipif(not _HAVE_EVM, reason="needs the evm extra: pip install 'loopmarket[evm]'")
def test_the_escrow_takes_the_share_and_the_floor_and_frees_neither_twice(chain):
    """On a local EVM: Kovač deposits his 500, and the clearing reserves
    what `reservations_for` lists — his fill's share, 50, under the loop,
    and the patient's floor, 20, under its slot. Both stand, for their own
    wanter, and 430 is left free: what the next leg's step 6 reads."""
    from web3 import Web3
    w3, escrow, _coin, clearing = chain
    w = World()
    rs = reservations_for(w.proposal(), escrow="0xE", resolver=JUDGE, claim_seconds=86_400, now=NOW,
                          span=SPANS.get, gate=w.gate(), ontology=_cat())
    offer = bytes.fromhex(w.dentist.offer_id)
    escrow.functions.deposit(offer).transact({"from": w3.eth.accounts[2], "value": 500 * 10 ** 18})
    for r in rs:
        terms = (*r["window"], r["claim_seconds"], r["min_challenge"], r["min_ruling"], r["claim_only"],
                 r["deductible"], bytes(32))
        escrow.functions.reserve(bytes.fromhex(r["offer_id"]), bytes.fromhex(r["loop_id"]),
                                 Web3.to_checksum_address(r["wanter"]), Web3.to_checksum_address(r["resolver"]),
                                 r["amount"], terms, [], []).transact({"from": clearing})
    assert escrow.functions.free(offer).call() == 430 * 10 ** 18
    slot = statement_slot(w.proposal().circulation.loop_id, w.patient.offer_id, w.statement.statement_id)
    wanter, resolver, amount = escrow.functions.reservation(offer, bytes.fromhex(slot)).call()[:3]
    assert (wanter.lower(), resolver.lower(), amount) == (P, JUDGE, 20 * 10 ** 18)
