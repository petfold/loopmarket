"""The optimistic beat (P2 clearing, step three, 2026-09-15): a real
proposal from the Python clearing is posted with a bond as commitments; a
challenge re-verifies one leg on chain against the committed hash — a good
leg survives, a bad one cancels the beat and pays the challenger; after
the window anyone finalizes and the contract records the fills exactly,
so the chain is the authority on what is filled. Skips without the `evm`
extra."""

import os
from fractions import Fraction

import pytest
from ontodag import OntoDAG

solcx = pytest.importorskip("solcx")
pytest.importorskip("eth_tester")
from eth_abi import encode  # noqa: E402
from web3 import Web3, EthereumTesterProvider  # noqa: E402
from recordstore import MemoryBytesStore, RecordStore  # noqa: E402

from loopmarket import (  # noqa: E402
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want,
)

HERE = os.path.dirname(__file__)
NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
PINS = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
LEG_TYPE = "((bytes32,bytes,bytes[]),(bytes32,bytes,bytes[])[],(uint256,uint256)[])"
BOND = 10 ** 16
WINDOW = 5


@pytest.fixture(scope="module")
def chain():
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
    def proof(oid):
        p = snapshot.store.prove("offer/" + oid)
        return (bytes.fromhex(oid), bytes.fromhex(p["value"]), [bytes.fromhex(n) for n in p["nodes"]])
    legs = [(proof(l["want"]), [proof(g) for g in l["gives"]], [_rat(t) for t in l["taken"]])
            for l in rec["legs"]]
    hashes = [Web3.keccak(encode([LEG_TYPE], [leg])) for leg in legs]
    fills = []
    for l in rec["legs"]:
        fills.append((bytes.fromhex(l["want"]), 1, 1))
        for g, t in zip(l["gives"], l["taken"]):
            fills.append((bytes.fromhex(g), *_rat(t)))
    makers = sorted(rec["potentials"])
    potentials = [_rat(rec["potentials"][m]) for m in makers]
    return legs, hashes, fills, [m.encode() for m in makers], potentials


def _pins(root):
    return (bytes.fromhex(root), bytes.fromhex(PINS["ontology_root"]), b"4.2", b"0.1")


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
    hashes = [Web3.keccak(encode([LEG_TYPE], [leg])) for leg in legs]
    fills = [(f[0], 105, 1) if f[0] == gives_p[0][0] else f for f in fills]
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
