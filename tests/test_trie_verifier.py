"""The Solidity trie-proof verifier against recordstore's real proofs
(docs/plans/proof-fabric.md §1/§5; the P2 clearing contract's evidence
layer, started 2026-09-15). Compiles `contracts/TrieProofVerifier.sol` with
py-solc-x and runs it on a local EVM (eth-tester): inclusion and absence
proofs from a real book root verify, every tampering is refused, and the
gas per proof is printed so the numbers are measured, not estimated.
Skips without the `evm` extra (`pip install 'loopmarket[evm]'`)."""

import importlib.util
import os

import pytest

from recordstore import MemoryBytesStore, RecordStore, verify_proof

from loopmarket import OfferRegistry, Thing, TimeWindow, give


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

SOURCE = os.path.join(os.path.dirname(__file__), "..", "contracts", "TrieProofVerifier.sol")


@pytest.fixture(scope="module")
def face():
    solcx, Web3, EthereumTesterProvider = _evm()
    solcx.install_solc("0.8.24")
    compiled = solcx.compile_files([SOURCE], output_values=["abi", "bin"], solc_version="0.8.24",
                                   optimize=True, optimize_runs=200, via_ir=True)
    artifact = next(v for k, v in compiled.items() if k.endswith("TrieProofVerifierFace"))
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
    receipt = w3.eth.wait_for_transaction_receipt(contract.constructor().transact())
    return w3, w3.eth.contract(address=receipt["contractAddress"], abi=artifact["abi"])


def _book(n=40):
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give(f"m{i}", Thing(("apple",), i + 1), 10 + i, valid=TimeWindow(0), nonce=i)
              for i in range(n)]
    book.publish_many(offers)
    root = book.commit()
    return book, offers, root


def _args(proof):
    return (bytes.fromhex(proof["root"]), proof["key"].encode(),
            [bytes.fromhex(n) for n in proof["nodes"]])


def test_inclusion_and_absence_verify_like_python(face):
    w3, verifier = face
    book, offers, root = _book()
    gas = {}
    for o in offers[:5]:
        proof = book.store.prove("offer/" + o.offer_id)
        assert verify_proof(proof, root)                         # Python agrees
        r, k, nodes = _args(proof)
        value = bytes.fromhex(proof["value"])
        present, ref = verifier.functions.verifyPath(r, k, nodes).call()
        assert present and ref.hex() == __import__("hashlib").sha256(value).hexdigest()
        assert verifier.functions.verifyInclusion(r, k, nodes, value).call()
        gas.setdefault("inclusion", []).append(
            verifier.functions.verifyInclusion(r, k, nodes, value).estimate_gas())
        absent = book.store.prove("fill/" + o.offer_id)
        verify_proof(absent, root)                               # Python agrees it is absent
        ra, ka, na = _args(absent)
        assert verifier.functions.verifyAbsence(ra, ka, na).call()
        gas.setdefault("absence", []).append(verifier.functions.verifyAbsence(ra, ka, na).estimate_gas())
    print("\ngas per proof over a", len(offers), "offer book:",
          {k: (min(v), max(v)) for k, v in gas.items()},
          "nodes per path:", len(proof["nodes"]))


def test_tampering_is_refused(face):
    w3, verifier = face
    book, offers, root = _book()
    proof = book.store.prove("offer/" + offers[0].offer_id)
    r, k, nodes = _args(proof)
    value = bytes.fromhex(proof["value"])
    # a different root
    with pytest.raises(Exception):
        verifier.functions.verifyPath(bytes(32), k, nodes).call()
    # a node altered by one byte
    bad = list(nodes); bad[0] = bad[0][:-1] + bytes([bad[0][-1] ^ 1])
    with pytest.raises(Exception):
        verifier.functions.verifyPath(r, k, bad).call()
    # the wrong value for the right path
    assert not verifier.functions.verifyInclusion(r, k, nodes, value + b" ").call()
    # a truncated proof ends before the walk concludes
    with pytest.raises(Exception):
        verifier.functions.verifyPath(r, k, nodes[:-1]).call()
