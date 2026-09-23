"""The optimistic beat (P2 clearing, step three, 2026-09-15): a real
proposal from the Python clearing is posted with a bond as commitments; a
challenge re-verifies one leg on chain against the committed hash — a good
leg survives, a bad one cancels the beat and pays the challenger; after
the window anyone finalizes and the contract records the fills exactly,
so the chain is the authority on what is filled. Skips without the `evm`
extra."""

import importlib.util
import os
from fractions import Fraction

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want,
)


# The contract tests need the `evm` extra (py-solc-x, eth-tester, web3). They
# skip PER TEST when it is absent, so every environment collects the same
# number of tests and the README's count holds in CI and on a laptop alike.
_HAVE_EVM = all(importlib.util.find_spec(m) for m in ("solcx", "eth_tester", "web3"))
pytestmark = pytest.mark.skipif(not _HAVE_EVM, reason="needs the evm extra: pip install 'loopmarket[evm]'")


def _evm():
    """The optional toolchain, imported only inside a running test."""
    import solcx
    from web3 import EthereumTesterProvider, Web3
    return solcx, Web3, EthereumTesterProvider

HERE = os.path.dirname(__file__)
NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
PINS = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
LEG_TYPE = "((bytes32,bytes,bytes[]),(bytes32,bytes,bytes[])[],(uint256,uint256)[])"
BOND = 10 ** 16
WINDOW = 5


@pytest.fixture(scope="module")
def chain():
    solcx, Web3, EthereumTesterProvider = _evm()
    solcx.install_solc("0.8.24")
    compiled = solcx.compile_files([os.path.join(HERE, "..", "contracts", "BeatClearing.sol")],
                                   output_values=["abi", "bin"], solc_version="0.8.24",
                                   optimize=True, optimize_runs=200, via_ir=True,
                                   allow_paths=os.path.join(HERE, "..", "contracts"))
    artifact = next(v for k, v in compiled.items() if k.endswith(":BeatClearing"))
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    c = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
    receipt = w3.eth.wait_for_transaction_receipt(
        c.constructor(BOND, WINDOW, w3.eth.accounts[2]).transact())
    return w3, w3.eth.contract(address=receipt["contractAddress"], abi=artifact["abi"])


def _cleared():
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": []})
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **PINS),
              want("b1", Thing(("apple",), 40, "kg"), 90, **V, **PINS),
              give("b1", Thing(("lesson",)), 80, **V, **PINS),
              want("farm", Thing(("lesson",)), 85, **V, **PINS)]
    book.publish_many(offers); book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    agent = SolverAgent(registry=book, ontology=cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert receipts and receipts[0].accepted
    return snapshot, root, book.store.get(f"loop/{receipts[0].loop_id}"), offers


def _rat(text):
    f = Fraction(text); return (f.numerator, f.denominator)


def _legs(snapshot, rec):
    from eth_abi import encode
    from web3 import Web3
    def proof(oid):
        p = snapshot.store.prove("offer/" + oid)
        return (bytes.fromhex(oid), bytes.fromhex(p["value"]), [bytes.fromhex(n) for n in p["nodes"]])
    legs = [(proof(l["want"]), [proof(g) for g in l["gives"]], [_rat(t) for t in l["taken"]])
            for l in rec["legs"]]
    hashes = [Web3.keccak(encode([LEG_TYPE], [leg])) for leg in legs]
    fills = []                                  # (offer, n, d, cap n, cap d)
    for l in rec["legs"]:
        fills.append((bytes.fromhex(l["want"]), 1, 1, 1, 1))
        for g, t in zip(l["gives"], l["taken"]):
            cap = snapshot.get(g).thing.qty
            fills.append((bytes.fromhex(g), *_rat(t), cap.numerator, cap.denominator))
    makers = sorted(rec["potentials"])
    potentials = [_rat(rec["potentials"][m]) for m in makers]
    return legs, hashes, fills, [m.encode() for m in makers], potentials


def _pins(root):
    return (bytes.fromhex(root), bytes.fromhex(PINS["ontology_root"]), b"4.2", b"0.1", 0)


def test_submit_challenge_and_finalize(chain):
    w3, beat = chain
    snapshot, root, rec, offers = _cleared()
    legs, hashes, fills, makers, potentials = _legs(snapshot, rec)
    tx = beat.functions.submit(_pins(root), hashes, fills, makers, potentials).transact({"value": BOND})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    bid = beat.events.Submitted().process_receipt(receipt)[0]["args"]["beat"]
    print("\nsubmit gas:", receipt["gasUsed"])
    # a challenge on a sound leg changes nothing; the challenger paid. (An
    # explicit gas limit: estimate_gas on a try/catch finds the cheap path
    # where the inner verification runs out of gas and is caught.)
    challenger = w3.eth.accounts[1]
    rc = w3.eth.wait_for_transaction_receipt(
        beat.functions.challenge(bid, 0, hashes, legs[0], makers, potentials).transact({"from": challenger, "gas": 12_000_000}))
    ev = beat.events.Challenged().process_receipt(rc)[0]["args"]
    assert ev["reason"] == "leg verifies" and not beat.functions.beats(bid).call()[8]
    print("challenge gas (leg verifies):", rc["gasUsed"])
    # data that is not what was committed is refused outright
    with pytest.raises(Exception, match="committed"):
        beat.functions.challenge(bid, 1, hashes, legs[0], makers, potentials).call({"from": challenger})
    # finalizing inside the window is refused
    with pytest.raises(Exception, match="window open"):
        beat.functions.finalize(bid).call()
    w3.provider.ethereum_tester.mine_blocks(WINDOW + 1)
    rf = w3.eth.wait_for_transaction_receipt(beat.functions.finalize(bid).transact())
    print("finalize gas:", rf["gasUsed"])
    farm_apples = offers[0].offer_id
    assert tuple(beat.functions.filled(bytes.fromhex(farm_apples)).call()) == (40, 1)
    assert tuple(beat.functions.filled(bytes.fromhex(offers[2].offer_id)).call()) == (1, 1)
    assert beat.functions.beats(bid).call()[7]                       # finalized
    with pytest.raises(Exception, match="no open beat"):
        beat.functions.finalize(bid).call()


def test_a_bad_leg_is_challenged_and_the_bond_goes_to_the_challenger(chain):
    """A fresh book's loop posted with one leg forged to take 105 kg of a
    100 kg give: the submitter commits to it, the challenger re-verifies
    that leg on chain and convicts it — the beat is cancelled and the bond
    is the challenger's."""
    w3, beat = chain
    snapshot, root, rec, offers = _cleared()
    legs, hashes, fills, makers, potentials = _legs(snapshot, rec)
    apples = next(i for i, l in enumerate(rec["legs"]) if l["taken"] == ["40"])
    want_p, gives_p, _ = legs[apples]
    legs[apples] = (want_p, gives_p, [(105, 1)])                    # forged: 105 kg of a 100 kg give
    from eth_abi import encode
    from web3 import Web3
    hashes = [Web3.keccak(encode([LEG_TYPE], [leg])) for leg in legs]
    fills = [(f[0], 105, 1, 105, 1) if f[0] == gives_p[0][0] else f for f in fills]
    tx = beat.functions.submit(_pins(root), hashes, fills, makers, potentials).transact({"value": BOND})
    bid = beat.events.Submitted().process_receipt(w3.eth.wait_for_transaction_receipt(tx))[0]["args"]["beat"]
    challenger = w3.eth.accounts[1]
    before = w3.eth.get_balance(challenger)
    rc = w3.eth.wait_for_transaction_receipt(
        beat.functions.challenge(bid, apples, hashes, legs[apples], makers, potentials).transact({"from": challenger, "gas": 12_000_000}))
    ev = beat.events.Challenged().process_receipt(rc)[0]["args"]
    assert "left" in ev["reason"], ev["reason"]
    assert beat.functions.beats(bid).call()[8]                       # cancelled
    assert w3.eth.get_balance(challenger) > before                  # the bond, less gas
    w3.provider.ethereum_tester.mine_blocks(WINDOW + 1)
    with pytest.raises(Exception, match="no open beat"):
        beat.functions.finalize(bid).call()
    # the arbiter may cancel what the contract cannot compute
    tx = beat.functions.submit(_pins(root), hashes, fills, makers, potentials).transact({"value": BOND})
    bid2 = beat.events.Submitted().process_receipt(w3.eth.wait_for_transaction_receipt(tx))[0]["args"]["beat"]
    with pytest.raises(Exception, match="not the arbiter"):
        beat.functions.cancelByArbiter(bid2, "x").call({"from": challenger})
    w3.eth.wait_for_transaction_receipt(
        beat.functions.cancelByArbiter(bid2, "the give does not fit the want").transact({"from": w3.eth.accounts[2]}))
    assert beat.functions.beats(bid2).call()[8]


def _submit(w3, beat, root, hashes, fills, makers, potentials):
    tx = beat.functions.submit(_pins(root), hashes, fills, makers, potentials).transact({"value": BOND})
    return beat.events.Submitted().process_receipt(w3.eth.wait_for_transaction_receipt(tx))[0]["args"]["beat"]


def test_two_beats_racing_over_one_book_cannot_overfill(chain):
    """The finalize gap (2026-09-23): the same loop posted twice against
    one book — each beat sound at its pinned root, both open at once. The
    first to finalize records its fills; the second finds its wants already
    filled whole, is cancelled at finalize rather than recorded, and its
    submitter gets the bond back (a race, not a fraud). Before the fix
    `finalize` summed the fills blindly and the second beat filled every
    offer twice."""
    w3, beat = chain
    snapshot, root, rec, offers = _cleared()
    legs, hashes, fills, makers, potentials = _legs(snapshot, rec)
    first = _submit(w3, beat, root, hashes, fills, makers, potentials)
    racer = w3.eth.accounts[3]
    tx = beat.functions.submit(_pins(root), hashes, fills, makers, potentials).transact({"value": BOND, "from": racer})
    second = beat.events.Submitted().process_receipt(w3.eth.wait_for_transaction_receipt(tx))[0]["args"]["beat"]
    w3.provider.ethereum_tester.mine_blocks(WINDOW + 1)
    w3.eth.wait_for_transaction_receipt(beat.functions.finalize(first).transact())
    before = w3.eth.get_balance(racer)
    rc = w3.eth.wait_for_transaction_receipt(beat.functions.finalize(second).transact({"from": w3.eth.accounts[4]}))
    ev = beat.events.Cancelled().process_receipt(rc)[0]["args"]
    assert ev["beat"] == second and "exceeds" in ev["reason"]
    state = beat.functions.beats(second).call()
    assert state[8] and not state[7]                                 # cancelled, not finalized
    assert w3.eth.get_balance(racer) == before + BOND                # the bond back, whole
    assert tuple(beat.functions.filled(bytes.fromhex(offers[0].offer_id)).call()) == (40, 1)
    assert tuple(beat.functions.filled(bytes.fromhex(offers[1].offer_id)).call()) == (1, 1)


def test_a_give_is_never_recorded_past_its_quantity(chain):
    """Two different loops over one 100 kg give, 60 kg each, both open: the
    second finalize would record 120 kg of 100 — it cancels instead."""
    w3, beat = chain
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": []})
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **PINS),
              want("b1", Thing(("apple",), 60, "kg"), 130, **V, **PINS),
              give("b1", Thing(("lesson",)), 80, **V, **PINS),
              want("farm", Thing(("lesson",)), 125, **V, **PINS),
              want("b2", Thing(("apple",), 60, "kg"), 131, **V, **PINS),
              give("b2", Thing(("lesson",)), 81, **V, **PINS),
              want("farm", Thing(("lesson",)), 126, **V, **PINS)]
    book.publish_many(offers); book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    # each loop solved alone against the same root, as two racing solvers would
    beats = []
    for keep in ({0, 1, 2, 3}, {0, 4, 5, 6}):
        solo = OfferRegistry(RecordStore(MemoryBytesStore()))
        solo.publish_many([o for i, o in enumerate(offers) if i in keep]); solo.commit()
        agent = SolverAgent(registry=solo, ontology=cat, clearing=MockClearing(solo, cat, clock=lambda: NOW), solver_id="t")
        receipts = agent.step(now=NOW)
        assert receipts and receipts[0].accepted
        rec = solo.store.get(f"loop/{receipts[0].loop_id}")
        legs, hashes, fills, makers, potentials = _legs(snapshot, rec)
        beats.append(_submit(w3, beat, root, hashes, fills, makers, potentials))
    w3.provider.ethereum_tester.mine_blocks(WINDOW + 1)
    w3.eth.wait_for_transaction_receipt(beat.functions.finalize(beats[0]).transact())
    rc = w3.eth.wait_for_transaction_receipt(beat.functions.finalize(beats[1]).transact())
    assert beat.events.Cancelled().process_receipt(rc)[0]["args"]["beat"] == beats[1]
    assert tuple(beat.functions.filled(bytes.fromhex(offers[0].offer_id)).call()) == (60, 1)


def test_a_false_cap_or_a_partial_want_fill_is_convicted(chain):
    """The caps are commitments: a submitter who inflates a give's cap (to
    slip an overfill past finalize) or commits a want as less than whole
    (so it could be filled again) is convicted by a challenge on the leg,
    and the bond is the challenger's."""
    w3, beat = chain
    snapshot, root, rec, offers = _cleared()
    legs, hashes, fills, makers, potentials = _legs(snapshot, rec)
    apples = next(i for i, l in enumerate(rec["legs"]) if l["taken"] == ["40"])
    farm = bytes.fromhex(offers[0].offer_id)
    challenger = w3.eth.accounts[1]
    inflated = [(f[0], f[1], f[2], 1000, 1) if f[0] == farm else f for f in fills]
    bid = _submit(w3, beat, root, hashes, inflated, makers, potentials)
    rc = w3.eth.wait_for_transaction_receipt(beat.functions.challenge(
        bid, apples, hashes, legs[apples], makers, potentials).transact({"from": challenger, "gas": 12_000_000}))
    assert beat.events.Challenged().process_receipt(rc)[0]["args"]["reason"] == "a cap is not its give's quantity"
    assert beat.functions.beats(bid).call()[8]
    b1 = bytes.fromhex(rec["legs"][apples]["want"])
    halved = [(f[0], 1, 2, 1, 1) if f[0] == b1 else f for f in fills]
    bid = _submit(w3, beat, root, hashes, halved, makers, potentials)
    rc = w3.eth.wait_for_transaction_receipt(beat.functions.challenge(
        bid, apples, hashes, legs[apples], makers, potentials).transact({"from": challenger, "gas": 12_000_000}))
    assert beat.events.Challenged().process_receipt(rc)[0]["args"]["reason"] == "the want's fill is not whole"
    # and a fill beyond its own cap is refused at submit
    with pytest.raises(Exception, match="beyond its cap"):
        beat.functions.submit(_pins(root), hashes, [(f[0], f[1], f[2], 1, 1) if f[0] == farm else f
                                                    for f in fills], makers, potentials).call({"value": BOND})
