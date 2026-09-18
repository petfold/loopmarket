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

from recordstore import DirBytesStore, MemoryBytesStore, RecordStore, verify_proof

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


ADDRESSING = {"sha256": 0, "swarm": 1}


def _args(proof):
    return (bytes.fromhex(proof["root"]), proof["key"].encode(),
            [bytes.fromhex(n) for n in proof["nodes"]])


def _scheme(proof):
    return ADDRESSING[proof["addressing"]]


def test_inclusion_and_absence_verify_like_python(face):
    w3, verifier = face
    book, offers, root = _book()
    gas = {}
    for o in offers[:5]:
        proof = book.store.prove("offer/" + o.offer_id)
        assert verify_proof(proof, root)                         # Python agrees
        r, k, nodes = _args(proof)
        value = bytes.fromhex(proof["value"])
        present, ref = verifier.functions.verifyPath(r, k, nodes, 0).call()
        assert present and ref.hex() == __import__("hashlib").sha256(value).hexdigest()
        assert verifier.functions.verifyInclusion(r, k, nodes, value, 0).call()
        gas.setdefault("inclusion", []).append(
            verifier.functions.verifyInclusion(r, k, nodes, value, 0).estimate_gas())
        absent = book.store.prove("fill/" + o.offer_id)
        verify_proof(absent, root)                               # Python agrees it is absent
        ra, ka, na = _args(absent)
        assert verifier.functions.verifyAbsence(ra, ka, na, 0).call()
        gas.setdefault("absence", []).append(verifier.functions.verifyAbsence(ra, ka, na, 0).estimate_gas())
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
        verifier.functions.verifyPath(bytes(32), k, nodes, 0).call()
    # a node altered by one byte
    bad = list(nodes); bad[0] = bad[0][:-1] + bytes([bad[0][-1] ^ 1])
    with pytest.raises(Exception):
        verifier.functions.verifyPath(r, k, bad, 0).call()
    # the wrong value for the right path
    assert not verifier.functions.verifyInclusion(r, k, nodes, value + b" ", 0).call()
    # a truncated proof ends before the walk concludes
    with pytest.raises(Exception):
        verifier.functions.verifyPath(r, k, nodes[:-1], 0).call()


# --------------------------------------------------------------------------- #
# Swarm addressing (2026-09-18): a book whose roots are Swarm references
# --------------------------------------------------------------------------- #

def test_swarm_address_matches_swarmfs_at_every_tree_shape(face):
    """`SwarmAddress.addressOf` against swarmfs's `content_address` (itself
    verified byte for byte against Bee): one segment, a partial tail
    segment, exactly one chunk, two leaves under an intermediate, and a
    tail chunk of one byte."""
    from swarmfs.splitter import content_address
    w3, verifier = face
    for data in (b"", b"x", b"y" * 31, b"z" * 32, b"w" * 33, bytes(range(256)) * 16,
                 b"v" * 4095, b"u" * 4096, b"t" * 4097, b"s" * (2 * 4096 + 1)):
        expected = content_address(data)
        assert verifier.functions.swarmReference(data).call() == expected, len(data)
    print("\nswarm address gas (400 B / 4096 B / 4097 B):",
          verifier.functions.swarmReference(b"a" * 400).estimate_gas(),
          verifier.functions.swarmReference(b"a" * 4096).estimate_gas(),
          verifier.functions.swarmReference(b"a" * 4097).estimate_gas())


def test_swarm_addressed_book_proves_under_its_swarm_root(face, tmp_path):
    """A book in a Swarm-addressed store (recordstore `addressing="swarm"`:
    its root is the reference Bee would return) proves inclusion and
    absence on chain under addressing 1 — what the 2026-09-18 live gate
    lacked — and the same proofs are refused under sha256, and vice versa."""
    w3, verifier = face
    book = OfferRegistry(RecordStore(DirBytesStore(str(tmp_path / "blobs"), addressing="swarm")))
    offers = [give(f"m{i}", Thing(("apple",), i + 1), 10 + i, valid=TimeWindow(0), nonce=i)
              for i in range(12)]
    book.publish_many(offers)
    root = book.commit()
    gas = []
    for o in offers[:4]:
        proof = book.store.prove("offer/" + o.offer_id)
        assert proof["addressing"] == "swarm" and _scheme(proof) == 1
        r, k, nodes = _args(proof)
        value = bytes.fromhex(proof["value"])
        assert verifier.functions.verifyInclusion(r, k, nodes, value, 1).call()
        gas.append(verifier.functions.verifyInclusion(r, k, nodes, value, 1).estimate_gas())
        with pytest.raises(Exception, match="node hash mismatch"):
            verifier.functions.verifyPath(r, k, nodes, 0).call()             # not a sha256 root
        absent = book.store.prove("fill/" + o.offer_id)
        ra, ka, na = _args(absent)
        assert verifier.functions.verifyAbsence(ra, ka, na, 1).call()
    print("\nswarm-addressed inclusion gas:", gas)
    sha = _book(12)[0]
    p2 = sha.store.prove("offer/" + offers[0].offer_id)
    with pytest.raises(Exception, match="node hash mismatch"):
        verifier.functions.verifyPath(*_args(p2), 1).call()                   # not a Swarm root
    with pytest.raises(Exception, match="unknown addressing"):
        verifier.functions.verifyPath(*_args(p2), 7).call()
