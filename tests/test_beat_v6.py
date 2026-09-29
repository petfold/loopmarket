"""Holds, item claims and statements on chain (2026-09-29: C4, I3, R3b;
`docs/plans/options-and-cover.md` §6.2, `items-and-ownership.md` §2,
`counterparty-gate.md` §3.3). A beat commits the holds its option legs
write, the item claims its gives write and the register roots it pins
beside its fills; a challenge checks them against the leg, and `finalize`
records them, so the chain is the authority on holds as on fills.

C4: an option cleared through `ChainClearing` posts its hold, which
verifies and is recorded at finalize; a non-holder's leg taking the held
flat is convicted by challenge (*more than is left of the give*), the
holder's own exercise verifies and consumes the hold. I3: two beats sound
at one root selling one maker's car through two offers — the second is
cancelled at finalize; a beat that omits a give's item claim is convicted.
R3b: the dentist's licensed statement verifies under the pinned registers;
a beat pinning the attester's root after the revocation is convicted by
challenge (Milestone M2's chain half). Skips without the `evm` extra."""

import dataclasses
import importlib.util

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want,
)
from loopmarket.clearing import ChainClearing, LoopProposal
from loopmarket.graph import Loop
from loopmarket.items import term, vin_id
from loopmarket.matching import Match

_HAVE_EVM = all(importlib.util.find_spec(m) for m in ("solcx", "eth_tester", "web3"))
pytestmark = pytest.mark.skipif(not _HAVE_EVM, reason="needs the evm extra: pip install 'loopmarket[evm]'")

BOND, WINDOW = 10 ** 16, 3
H = vin_id("1HGCM82633A004352")             # the flat's item (the option test)
CAR = vin_id("1HGCM82633A004353")           # the car's (the race test; the chain is shared)


@pytest.fixture(scope="module")
def chain():
    from web3 import EthereumTesterProvider, Web3

    from loopmarket.beat import deploy
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    address, _verifier = deploy(w3, BOND, WINDOW, w3.eth.accounts[2])
    key = w3.provider.ethereum_tester.backend.account_keys[0].to_hex()
    return w3, address, key


def _client(chain, account=0):
    from loopmarket.beat import BeatClient
    w3, address, _key = chain
    key = w3.provider.ethereum_tester.backend.account_keys[account].to_hex()
    return BeatClient("", address, key=key, client=w3)


def _catalogue():
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.declare_item_heads()
    cat.declare_graph_heads(["option"])
    cat.load({"flat": [], "car": [], "lesson": []})
    cat.commit()
    return cat


def _now(chain) -> int:
    return int(chain[0].eth.get_block("latest")["timestamp"])


def _mine(chain):
    chain[0].provider.ethereum_tester.mine_blocks(WINDOW + 1)


def test_an_option_holds_on_chain_and_only_its_holder_exercises(chain):
    t = _now(chain)
    cat = _catalogue()
    pins = cat.pins
    V = dict(valid=TimeWindow(t - 10_000, t + 10 ** 7), **pins)
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    flat = give("seller", Thing(("flat", term(H)), 1, "flat"), 100, **V, nonce=1)
    option = give("seller", Thing((f"option(flat {term(H)})",), 1, "flat"), 5, **V, nonce=2,
                  underlying=flat.offer_id, exercise=TimeWindow(t - 100, t + 10 ** 6))
    book.publish_many([flat, option,
                       want("holder", Thing(("option(flat)",), 1, "flat"), 12, **V, nonce=3),
                       give("holder", Thing(("lesson",), 1, "hour"), 5, **V, nonce=4),
                       want("seller", Thing(("lesson",), 1, "hour"), 80, **V, nonce=5)])
    book.commit()
    client = _client(chain)
    clearing = ChainClearing(book, cat, beat_client=client, clock=lambda: t)
    (r,) = SolverAgent(book, cat, clearing=clearing, solver_id="t").step(now=t)
    assert r.accepted and r.reason.startswith("beat "), r.reason
    beat = int(r.reason.split()[1])
    (hold,) = client.pending_holds(beat)
    assert hold[0] == bytes.fromhex(option.offer_id) and hold[1] == bytes.fromhex(flat.offer_id)
    (claim,) = client.pending_claims(beat)                  # the option's claim on the car's item
    assert claim[0] == bytes.fromhex(H) and claim[2] == bytes.fromhex(flat.offer_id)
    from loopmarket.beat import challenge_beat
    result = challenge_beat(client, beat, [book], cat, now=t, send=False)
    assert result.verifies, [(v.local, v.chain) for v in result.legs]
    _mine(chain)
    client.finalize(beat)
    assert client.held_against(flat.offer_id, at=_now(chain)) == 1
    assert client.item_claim(H, "seller") == (flat.offer_id, t + 10 ** 6)

    # a non-holder's leg on the held flat: posted anyway, convicted
    other = [want("other", Thing(("flat",), 1, "flat"), 120, **V, nonce=6),
             give("other", Thing(("lesson",), 1, "hour"), 5, **V, nonce=7),
             want("seller", Thing(("lesson",), 1, "hour"), 80, **V, nonce=8)]
    book.publish_many(other)
    book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    loop = Loop((Match(give=flat, want=other[0]), Match(give=other[1], want=other[2])))
    proposal = LoopProposal(loop, root, cat.root, "t", t)
    from loopmarket.beat import submission
    lid = proposal.circulation.loop_id
    forged = submission(proposal, snapshot, records={f"item/{H}/seller/{lid}": {"until": t + 10 ** 6}})
    bad, _ = client.submit(forged)
    leg = next(i for i, l in enumerate(forged.legs) if l[1][0][0] == bytes.fromhex(flat.offer_id))
    reason = _client(chain, 1).challenge(bad, leg, forged)
    assert "more than is left of the give" in reason and client.beat(bad)["cancelled"]

    # the holder's own exercise clears in memory, verifies on chain, and uses the hold
    mine = [want("holder", Thing(("flat",), 1, "flat"), 120, **V, nonce=9),
            give("holder", Thing(("lesson",), 1, "hour"), 5, **V, nonce=10),
            want("seller", Thing(("lesson",), 1, "hour"), 150, **V, nonce=11)]   # at least the flat's ask
    book.publish_many(mine)
    book.commit()
    t2 = _now(chain)
    clearing = ChainClearing(book, cat, beat_client=client, clock=lambda: t2)
    receipts = SolverAgent(book, cat, clearing=clearing, solver_id="t").step(now=t2)
    exercise = next((r for r in receipts if r.accepted), None)
    assert exercise is not None, [(r.accepted, r.reason) for r in receipts]
    beat2 = int(exercise.reason.split()[1])
    assert challenge_beat(client, beat2, [book], cat, now=t2, send=False).verifies
    _mine(chain)
    client.finalize(beat2)
    assert client.beat(beat2)["finalized"] and client.filled(flat.offer_id) == 1
    assert client.held_against(flat.offer_id, at=_now(chain)) == 0      # the hold is used up


def _car_sale(t, pins, seller_nonce, buyer):
    V = dict(valid=TimeWindow(t - 10_000, t + 10 ** 7), **pins)
    return [give("seller", Thing(("car", term(CAR)), 1, "car"), 50, **V, nonce=seller_nonce),
            want(buyer, Thing(("car", term(CAR)), 1, "car"), 100, **V, nonce=seller_nonce + 1),
            give(buyer, Thing(("lesson",), 1, "hour"), 5, **V, nonce=seller_nonce + 2),
            want("seller", Thing(("lesson",), 1, "hour"), 80, **V, nonce=seller_nonce + 3)]


def test_a_second_claim_on_an_item_in_a_concurrent_beat_is_caught_at_finalize(chain):
    from loopmarket.beat import submission
    t = _now(chain)
    cat = _catalogue()
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    first, second = _car_sale(t, cat.pins, 100, "b1"), _car_sale(t, cat.pins, 200, "b2")
    book.publish_many(first + second)
    book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    client = _client(chain)
    subs, beats = [], []
    for sale in (first, second):          # each sound at the same root, as two racing solvers
        loop = Loop((Match(give=sale[0], want=sale[1]), Match(give=sale[2], want=sale[3])))
        proposal = LoopProposal(loop, root, cat.root, "t", t)
        lid = proposal.circulation.loop_id
        sub = submission(proposal, snapshot, records={f"item/{CAR}/seller/{lid}": {"until": t + 5_000}})
        subs.append(sub)
        beats.append(client.submit(sub)[0])
        for i in range(len(sub.legs)):
            assert client.verdict(client.beat(beats[-1]), i, sub) == "leg verifies"
    # a beat that leaves out the give's item claim is convicted
    sub = dataclasses.replace(subs[0], claims=[])
    naked, _ = client.submit(sub)
    leg = next(i for i, l in enumerate(sub.legs) if l[1][0][0] == bytes.fromhex(first[0].offer_id))
    assert _client(chain, 1).challenge(naked, leg, sub) == "a give naming an item without its claim"
    _mine(chain)
    client.finalize(beats[0])
    assert client.item_claim(CAR, "seller") == (first[0].offer_id, t + 5_000)
    client.finalize(beats[1])
    state = client.beat(beats[1])
    assert state["cancelled"] and not state["finalized"]
    assert client.filled(second[0].offer_id) == 0


def test_a_revoked_statement_is_convicted_on_chain(chain):
    """Milestone M2's chain half: the dentist's licensed statement stands
    under the pinned registers and the leg verifies; the same beat pinning
    the attester's root after the revocation carries an inclusion where an
    absence was due, and a challenge convicts it."""
    from eth_abi import encode
    from eth_hash.auto import keccak
    from test_gate import ATTESTER, CHAMBER, NOW, SPANS, World, _cat

    from loopmarket.beat import LEG_TYPE, STATEMENTS_TYPE, submission
    from loopmarket.gate import CounterpartyGate
    from loopmarket.register import Register

    pins = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
    w = World(pins=pins)
    roots = tuple(sorted((r, reg.root) for r, reg in w.registers.items()))
    loop = Loop((Match(give=w.dentist, want=w.patient), Match(give=w.lesson, want=w.wants_lesson)))
    root = w.book.store.root
    proposal = LoopProposal(loop, root, pins["ontology_root"], "t", NOW, roots)
    snapshot = OfferRegistry(RecordStore.at(root, w.blobs))
    gate = CounterpartyGate.over(snapshot, w.registers, now=NOW, span=SPANS.get)
    sub = submission(proposal, snapshot, gate=gate, ontology=_cat())
    dentist_leg = next(i for i, st in enumerate(sub.statements) if st)
    assert len(sub.statements[dentist_leg]) == 1 and [r[0] for r in sub.registers] == [ATTESTER.encode(),
                                                                                       CHAMBER.encode()]
    client = _client(chain)
    honest, _ = client.submit(sub)
    assert _client(chain, 1).challenge(honest, dentist_leg, sub) == "leg verifies"
    # revoked after the pin: the forger pins the new root, showing its inclusion as the "absence"
    sid = w.statement.statement_id
    w.attester.revoke(sid, NOW - 5)
    revoked_root = w.attester.commit()
    reg = Register(RecordStore.at(revoked_root, w.blobs))
    registers = [(ATTESTER.encode(), bytes.fromhex(revoked_root), 0) if r[0] == ATTESTER.encode() else r
                 for r in sub.registers]
    st = list(sub.statements[dentist_leg][0])
    st[4] = [bytes.fromhex(n) for n in reg.prove("revoked/" + sid)["nodes"]]
    st[5] = [bytes.fromhex(n) for n in reg.prove("suspended/" + sid)["nodes"]]
    statements = [list(s) for s in sub.statements]
    statements[dentist_leg] = [tuple(st)]
    hashes = [keccak(encode([LEG_TYPE, STATEMENTS_TYPE], [leg, s])) for leg, s in zip(sub.legs, statements)]
    forged = dataclasses.replace(sub, registers=registers, statements=statements, leg_hashes=hashes)
    bad, _ = client.submit(forged)
    reason = _client(chain, 1).challenge(bad, dentist_leg, forged)
    assert reason == "the statement is revoked under its register's pinned root"
    assert client.beat(bad)["cancelled"]
    # and a statement whose register the beat does not pin at all
    unpinned = dataclasses.replace(sub, registers=[r for r in sub.registers if r[0] != ATTESTER.encode()])
    bid, _ = client.submit(unpinned)
    assert _client(chain, 1).challenge(bid, dentist_leg, unpinned) == "the statement's register is not pinned"
