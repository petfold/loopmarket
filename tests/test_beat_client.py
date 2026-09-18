"""The beat from Python (P2 clearing, step four, 2026-09-15): `submission`
builds exactly what the contract commits to — its leg hashes equal the
contract's own `abi.encode` — and `ChainClearing` clears into the book
and posts the beat in one motion; after the window `finalize` records the
fills and the chain answers `filled` exactly. Skips without the `evm` extra."""

import importlib.util
import os

import pytest

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want,
)
from loopmarket.beat import BeatClient, abi, submission
from loopmarket.clearing import ChainClearing


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

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
BOND, WINDOW = 10 ** 16, 3


@pytest.fixture(scope="module")
def chain():
    _solcx, Web3, EthereumTesterProvider = _evm()
    art = abi()
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    c = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    receipt = w3.eth.wait_for_transaction_receipt(c.constructor(BOND, WINDOW, w3.eth.accounts[2]).transact())
    # a funded key for the client: eth-tester's first account, exported
    key = w3.provider.ethereum_tester.backend.account_keys[0].to_hex()
    return w3, receipt["contractAddress"], key


def _book():
    """A pinned catalogue (a persistent root, as a deployment has) and offers
    pinning it: the contract refuses an unpinned proposal (U10)."""
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"apple": [], "lesson": []})
    cat.commit()
    pins = cat.pins
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many([give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **pins),
                       want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
                       give("b1", Thing(("lesson",)), 80, **V, **pins),
                       want("farm", Thing(("lesson",)), 85, **V, **pins)])
    book.commit()
    return cat, book


def test_submission_matches_the_contracts_commitment(chain):
    w3, address, key = chain
    cat, book = _book()
    root = book.store.root
    agent = SolverAgent(book, cat, clearing=None, solver_id="t", min_surplus=0.0)
    _root, loops = agent.find_loops(now=NOW)
    from loopmarket.clearing import LoopProposal
    proposal = LoopProposal(loops[0], root, cat.root, "t", NOW)
    sub = submission(proposal, OfferRegistry(RecordStore.at(root, book.store.blobs)))
    assert len(sub.legs) == 2 and len(sub.fills) == 4 and sub.pins[0] == bytes.fromhex(root)
    # the contract's own hashing of the same leg agrees with ours
    client = BeatClient("", address, key=key, client=w3)
    beat, _ = client.submit(sub)
    reason = client.challenge(beat, 0, sub)                     # a sound leg: the challenge fails
    assert reason == "leg verifies"
    assert client.beat(beat)["fills"] == 4 and not client.beat(beat)["cancelled"]
    # the live book is the snapshot only while nothing has been committed since
    assert submission(proposal, book).leg_hashes == sub.leg_hashes
    book.publish(give("z", Thing(("apple",), 1), 1, **V)); book.commit()
    with pytest.raises(ValueError, match="not the proposal's book root"):
        submission(proposal, book)


def test_chain_clearing_posts_and_finalize_records_fills(chain):
    w3, address, key = chain
    cat, book = _book()
    client = BeatClient("", address, key=key, client=w3)
    agent = SolverAgent(book, cat, clearing=ChainClearing(book, cat, beat_client=client, clock=lambda: NOW),
                        solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and receipts[0].accepted and receipts[0].reason.startswith("beat ")
    beat = int(receipts[0].reason.split()[1])
    apples = next(o for o in book.offers(include_filled=True) if o.maker == "farm" and o.kind == "give")
    assert book.taken(apples.offer_id) == 40                    # the book has the fill now
    assert client.filled(apples.offer_id) == 0                  # the chain only after the window
    w3.provider.ethereum_tester.mine_blocks(WINDOW + 1)
    client.finalize(beat)
    assert client.filled(apples.offer_id) == 40 and client.beat(beat)["finalized"]
    assert agent.step(now=NOW) == []
