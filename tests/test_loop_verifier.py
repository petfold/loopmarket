"""The on-chain structural verifier of a leg (P2 clearing, step two,
2026-09-15): real proposals from the Python clearing, fed to
`contracts/LoopVerifier.sol` on a local EVM — every offer's canonical bytes
and trie proof, the quantities taken, the potentials — verify; and each
thing the contract can refuse, it refuses: a record that does not hash to
its id, an offer outside the root, a non-v4 record, a pin mismatch, a
quantity off the step or over what is left, potentials that do not
balance. Skips without the `evm` extra."""

import importlib.util
import os
from fractions import Fraction

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, q, want,
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


@pytest.fixture(scope="module")
def face():
    solcx, Web3, EthereumTesterProvider = _evm()
    solcx.install_solc("0.8.24")
    compiled = solcx.compile_files([os.path.join(HERE, "..", "contracts", "LoopVerifier.sol")],
                                   output_values=["abi", "bin"], solc_version="0.8.24",
                                   optimize=True, optimize_runs=200, via_ir=True,
                                   allow_paths=os.path.join(HERE, "..", "contracts"))
    artifact = next(v for k, v in compiled.items() if k.endswith("LoopVerifierFace"))
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    c = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
    receipt = w3.eth.wait_for_transaction_receipt(c.constructor().transact())
    return w3, w3.eth.contract(address=receipt["contractAddress"], abi=artifact["abi"])


def _cleared_book():
    """A book with pins, a cleared triangle including a partial fill of a
    divisible give, and the loop record clearing wrote."""
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": [], "repair": []})
    pins = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [
        give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **pins),        # 2/kg, by 5 kg
        want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
        give("b1", Thing(("lesson",)), 80, **V, **pins),
        want("farm", Thing(("lesson",)), 85, **V, **pins),
    ]
    book.publish_many(offers); book.commit()
    root = book.store.root
    agent = SolverAgent(registry=book, ontology=cat, clearing=MockClearing(book, cat, clock=lambda: NOW),
                        solver_id="t")
    # the proposal is what clearing accepted; verify it against the PRE-clearing root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True]
    rec = book.store.get(f"loop/{receipts[0].loop_id}")
    return snapshot, root, rec, pins


def _rat(text):
    f = Fraction(text)
    return (f.numerator, f.denominator)


def _leg_args(snapshot, rec, leg):
    def proof(oid):
        p = snapshot.store.prove("offer/" + oid)
        return (bytes.fromhex(oid), bytes.fromhex(p["value"]), [bytes.fromhex(n) for n in p["nodes"]])
    return (proof(leg["want"]), [proof(g) for g in leg["gives"]], [_rat(t) for t in leg["taken"]])


def _beat(root, pins):
    return (bytes.fromhex(root), bytes.fromhex(pins["ontology_root"]),
            pins["registry_version"].encode(), pins["contract_version"].encode(), 0)


def test_a_cleared_loop_verifies_leg_by_leg(face):
    w3, verifier = face
    snapshot, root, rec, pins = _cleared_book()
    makers = list(rec["potentials"])
    verifier.functions.setPotentials([m.encode() for m in makers],
                                     [_rat(rec["potentials"][m])[0] for m in makers],
                                     [_rat(rec["potentials"][m])[1] for m in makers]).transact()
    gas = []
    for leg in rec["legs"]:
        args = _leg_args(snapshot, rec, leg)
        want_maker, give_makers = verifier.functions.verifyLeg(_beat(root, pins), args).call()
        assert want_maker.decode() == snapshot.get(leg["want"]).maker
        assert [m.decode() for m in give_makers] == [snapshot.get(g).maker for g in leg["gives"]]
        gas.append(verifier.functions.verifyLeg(_beat(root, pins), args).estimate_gas())
    print("\ngas per leg (one give each):", gas)


def test_every_structural_fault_is_refused(face):
    w3, verifier = face
    snapshot, root, rec, pins = _cleared_book()
    makers = list(rec["potentials"])
    verifier.functions.setPotentials([m.encode() for m in makers],
                                     [_rat(rec["potentials"][m])[0] for m in makers],
                                     [_rat(rec["potentials"][m])[1] for m in makers]).transact()
    leg = next(l for l in rec["legs"] if l["taken"] == ["40"])           # the apples leg
    beat = _beat(root, pins)
    good = _leg_args(snapshot, rec, leg)
    assert verifier.functions.verifyLeg(beat, good).call()

    def refused(args, beat_=beat, match=None):
        with pytest.raises(Exception) as exc:
            verifier.functions.verifyLeg(beat_, args).call()
        if match:
            assert match in str(exc.value), str(exc.value)

    want_p, gives_p, taken = good
    # a record altered by a byte no longer hashes to its id
    gid, grec, gnodes = gives_p[0]
    i = grec.index(b'"nonce":') + 8                                   # a digit inside the record
    tampered = grec[:i] + bytes([grec[i] ^ 1]) + grec[i + 1:]
    refused((want_p, [(gid, tampered, gnodes)], taken), match="hash")
    refused((want_p, [(gid, grec[:-1] + b" ", gnodes)], taken), match="envelope")
    # off the 5 kg step; more than the whole give; below a floor is the same gate
    refused((want_p, gives_p, [(42, 1)]), match="step")
    refused((want_p, gives_p, [(105, 1)]), match="left")
    # the contract has already recorded 70 kg filled: 40 more is too much
    verifier.functions.setFilled(gid, 70, 1).transact()
    refused((want_p, gives_p, taken), match="left")
    verifier.functions.setFilled(gid, 0, 1).transact()
    # pins: the beat names another catalogue root, registry, contract
    refused(good, beat_=(bytes.fromhex(root), bytes(32), b"4.2", b"0.1", 0), match="ontology pin")
    refused(good, beat_=(bytes.fromhex(root), bytes.fromhex("ab" * 32), b"5.0", b"0.1", 0), match="registry pin")
    # another book root: the proof does not hash there
    refused(good, beat_=(bytes(32), bytes.fromhex("ab" * 32), b"4.2", b"0.1", 0))
    # potentials that do not balance: the buyer's potential too small
    verifier.functions.setPotentials([b"b1", b"farm"], [1, 1], [10, 1]).transact()
    refused(good, match="balance")
    # a v3 record is not verifiable on chain
    snap3, root3, rec3, _ = _cleared_book_v3()
    leg3 = next(l for l in rec3["legs"] if len(l["gives"]) == 1)
    refused(_leg_args(snap3, rec3, leg3), beat_=_beat(root3, pins), match="v4")


def _cleared_book_v3():
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": []})
    pins = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("farm", Thing(("apple",), 40, "kg"), 80, v=3, **V, **pins),
              want("b1", Thing(("apple",), 40, "kg"), 90, v=3, **V, **pins),
              give("b1", Thing(("lesson",)), 80, v=3, **V, **pins),
              want("farm", Thing(("lesson",)), 85, v=3, **V, **pins)]
    book.publish_many(offers); book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    agent = SolverAgent(registry=book, ontology=cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t")
    receipts = agent.step(now=NOW)
    assert receipts and receipts[0].accepted
    return snapshot, root, book.store.get(f"loop/{receipts[0].loop_id}"), pins


# --------------------------------------------------------------------------- #
# Composed wants on chain (2026-09-18): give i serves part i, whole
# --------------------------------------------------------------------------- #

def _cleared_composed():
    """The v4 record test's evening: a want of two tickets and a transport,
    the theatre's tickets by the piece and the driver's run, the ring closing
    through two lessons — cleared, with the pre-clearing snapshot."""
    from loopmarket import Parts
    cat = Ontology(OntoDAG()).load({"ticket": [], "transport": [], "lesson": []})
    pins = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [
        want("buyer", Parts((Thing(("ticket",), 2), Thing(("transport",), 1, "run"))), 60, **V, **pins),
        give("theatre", Thing(("ticket",), 10, step=1), 200, **V, **pins),        # 20 a ticket
        give("driver", Thing(("transport",), 1, "run"), 15, **V, **pins),
        give("buyer", Thing(("lesson",)), 30, nonce=1, **V, **pins),
        give("buyer", Thing(("lesson",)), 30, nonce=2, **V, **pins),
        want("theatre", Thing(("lesson",)), 42, **V, **pins),
        want("driver", Thing(("lesson",)), 31, **V, **pins),
    ]
    book.publish_many(offers); book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    agent = SolverAgent(registry=book, ontology=cat, clearing=MockClearing(book, cat, clock=lambda: NOW),
                        solver_id="t")
    receipts = agent.step(now=NOW)
    assert [r.accepted for r in receipts] == [True], receipts
    return snapshot, root, book.store.get(f"loop/{receipts[0].loop_id}"), pins, offers


def test_a_composed_want_verifies_leg_by_leg(face):
    w3, verifier = face
    snapshot, root, rec, pins, offers = _cleared_composed()
    makers = list(rec["potentials"])
    verifier.functions.setPotentials([m.encode() for m in makers],
                                     [_rat(rec["potentials"][m])[0] for m in makers],
                                     [_rat(rec["potentials"][m])[1] for m in makers]).transact()
    composed = next(l for l in rec["legs"] if len(l["gives"]) == 2)
    assert composed["taken"] == ["2", "1"]
    beat = _beat(root, pins)
    for leg in rec["legs"]:
        args = _leg_args(snapshot, rec, leg)
        want_maker, give_makers = verifier.functions.verifyLeg(beat, args).call()
        assert want_maker.decode() == snapshot.get(leg["want"]).maker
    args = _leg_args(snapshot, rec, composed)
    print("\ngas for the composed leg (two parts):", verifier.functions.verifyLeg(beat, args).estimate_gas())
    want_p, gives_p, taken = args

    def refused(a, match):
        with pytest.raises(Exception, match=match):
            verifier.functions.verifyLeg(beat, a).call()

    refused((want_p, gives_p, [(1, 1), (1, 1)]), "not the part's quantity")     # one ticket for a part of two
    refused((want_p, gives_p, [(2, 1), (2, 1)]), "left|not the part")           # two runs of one
    refused((want_p, gives_p[:1], taken[:1]), "one give per part")              # the transport missing
    refused((want_p, [gives_p[1], gives_p[0]], [taken[1], taken[0]]), "left|unit|part")  # gives swapped
    # the want-quantity rule on a plain leg: the driver's want of one lesson
    # "served" by two of the theatre's tickets — the give allows two (by the
    # piece), the want is for one; what the tickets are is the semantic half's
    driver_want = next(l for l in rec["legs"] if len(l["gives"]) == 1
                       and snapshot.get(l["want"]).maker == "driver")
    w2, _g2, _t2 = _leg_args(snapshot, rec, driver_want)
    refused((w2, [gives_p[0]], [(2, 1)]), "not the want's quantity")
    theatre_want = next(l for l in rec["legs"] if len(l["gives"]) == 1
                        and snapshot.get(l["want"]).maker == "theatre")
    w3_, _g3, _t3 = _leg_args(snapshot, rec, theatre_want)
    refused((w3_, [gives_p[1]], [(1, 1)]), "the want's unit")                   # the driver's run for a lesson


# --------------------------------------------------------------------------- #
# Admissibility by declaration on chain (v5, 2026-09-18)
# --------------------------------------------------------------------------- #

def test_a_v5_leg_verifies_and_an_unmet_requirement_is_convicted(face):
    """The buyer requires a bond of 1 and settles by countersign; the bonded
    seller's leg verifies on chain; a leg through an under-bonded seller, or
    a seller that accepts only lockers, is convicted structurally."""
    from loopmarket import Requires
    w3, verifier = face
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": []})
    pins = dict(ontology_root="ab" * 32, registry_version="4.2", contract_version="0.1")
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    buyer = want("b", Thing(("apple",), 3), 15, **V, **pins, bond=1, requires=Requires(bond=1))
    bonded = give("s", Thing(("apple",), 3), 12, **V, **pins, bond=1, v=5)
    poor = give("p", Thing(("apple",), 3), 12, **V, **pins, bond="1/2", v=5)
    fussy = give("f", Thing(("apple",), 3), 12, **V, **pins, bond=1, requires=Requires(oracles=("locker",)))
    legacy = give("l", Thing(("apple",), 3), 12, **V, **pins)                 # v4: a float bond, so none
    ret = [give("b", Thing(("lesson",)), 10, **V, **pins, bond=1, v=5), want("s", Thing(("lesson",)), 11, **V, **pins, v=5)]
    book.publish_many([buyer, bonded, poor, fussy, legacy, *ret]); book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    verifier.functions.setPotentials([b"b", b"s", b"p", b"f", b"l"], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1]).transact()

    def leg(g):
        return _leg_args(snapshot, None, {"want": buyer.offer_id, "gives": [g.offer_id], "taken": ["3"]})
    beat = _beat(root, pins)
    want_maker, gives = verifier.functions.verifyLeg(beat, leg(bonded)).call()
    assert want_maker == b"b" and gives == [b"s"]
    for g, why in ((poor, "bond below"), (legacy, "bond below"), (fussy, "witness type not accepted")):
        with pytest.raises(Exception, match=why):
            verifier.functions.verifyLeg(beat, leg(g)).call()
    print("\ngas for a v5 leg with a requirement:", verifier.functions.verifyLeg(beat, leg(bonded)).estimate_gas())
