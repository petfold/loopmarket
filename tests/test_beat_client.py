"""The beat from Python (P2 clearing, step four, 2026-09-15): `submission`
builds exactly what the contract commits to — its leg hashes equal the
contract's own `abi.encode` — and `ChainClearing` clears into the book
and posts the beat in one motion; after the window `finalize` records the
fills and the chain answers `filled` exactly. Skips without the `evm` extra."""

import importlib.util
import os

import pytest

from ontodag import OntoDAG
from recordstore import DirBytesStore, MemoryBytesStore, RecordStore

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


# --------------------------------------------------------------------------- #
# The challenger (2026-09-18): evidence rebuilt from the loop record, the
# off-chain re-derivation, the contract's own verdict for free, the challenge
# --------------------------------------------------------------------------- #

from loopmarket.beat import challenge_beat, commitment, find_evidence, proposal_from_record  # noqa: E402


def _posted(chain):
    """A book cleared through `ChainClearing`: the beat on chain, the loop
    record in the book — the shape a challenger meets."""
    w3, address, key = chain
    cat, book = _book()
    client = BeatClient("", address, key=key, client=w3)
    agent = SolverAgent(book, cat, clearing=ChainClearing(book, cat, beat_client=client, clock=lambda: NOW),
                        solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    beat = int(receipts[0].reason.split()[1])
    return cat, book, client, beat, receipts[0].loop_id


def test_an_honest_beat_verifies_from_its_record_and_nothing_is_sent(chain):
    w3, address, key = chain
    cat, book, client, beat, loop_id = _posted(chain)
    state = client.beat(beat)
    assert state["book_root"] == book.store.get(f"loop/{loop_id}")["book_root"] and state["open"]
    # the record alone rebuilds exactly what was committed
    ev = find_evidence(state, [book])
    assert ev is not None and ev.record["loop_id"] == loop_id
    assert commitment(ev.submission) == (state["legs_hash"], state["potentials_hash"])
    assert proposal_from_record(ev.record, ev.snapshot).circulation.loop_id == loop_id
    # every leg holds off chain and on: the contract's verdict costs no transaction
    result = challenge_beat(client, beat, [book], cat, now=NOW)
    assert result.verifies and result.sent is None and not result.cancelled
    assert [v.chain for v in result.legs] == ["leg verifies"] * 2
    assert all(v.local is None for v in result.legs) and result.overall is None
    # a fresh session with no book has nothing to check against
    empty = OfferRegistry(RecordStore(MemoryBytesStore()))
    assert challenge_beat(client, beat, [empty], cat, now=NOW).overall == "no evidence"
    # and a wrong catalogue cannot judge the semantic half, says so, sends nothing
    other = Ontology.persistent(RecordStore(MemoryBytesStore())); other.load({"pear": []}); other.commit()
    off = challenge_beat(client, beat, [book], other, now=NOW)
    assert off.overall == "ontology pin mismatch" and off.sent is None and not off.verifies


def test_a_structural_forgery_is_convicted_and_the_bond_paid(chain):
    """The submitter's record claims 105 kg of a 100 kg give and the beat
    commits to it: the challenger rebuilds that very submission from the
    record, the dry run convicts the leg, the challenge cancels the beat."""
    w3, address, key = chain
    cat, book = _book()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    agent = SolverAgent(book, cat, clearing=None, solver_id="t", min_surplus=0.0)
    _r, loops = agent.find_loops(now=NOW)
    from loopmarket.clearing import LoopProposal
    rec = LoopProposal(loops[0], root, cat.root, "t", NOW).to_record()
    forged = dict(rec, legs=[dict(l, taken=["105"]) if l["taken"] == ["40"] else l for l in rec["legs"]])
    from loopmarket.beat import legs_from_record
    from loopmarket.graph import Circulation
    circ = Circulation(legs_from_record(forged, snapshot))
    forged["loop_id"] = circ.loop_id                                  # the forger is at least consistent
    forgery = LoopProposal(circ, root, cat.root, "t", NOW)
    sub = submission(forgery, snapshot, potentials={m: e for m, e in rec["potentials"].items()})
    submitter = BeatClient("", address, key=key, client=w3)
    beat, _ = submitter.submit(sub)
    # the forger's clearing book: U11 refuses an oversold fill at a registry
    # commit, so the forger writes the record through the store itself
    book.store.put(f"loop/{circ.loop_id}", forged); book.store.commit()
    challenger_key = w3.provider.ethereum_tester.backend.account_keys[1].to_hex()
    challenger = BeatClient("", address, key=challenger_key, client=w3)
    before = w3.eth.get_balance(w3.eth.accounts[1])
    result = challenge_beat(challenger, beat, [book], cat, now=NOW)
    bad = next(v for v in result.legs if v.convicts)
    assert "left" in bad.chain and bad.local and "fails" in bad.local
    assert result.sent == bad.index and "left" in result.reason and result.cancelled
    assert w3.eth.get_balance(w3.eth.accounts[1]) > before
    assert not challenger.beat(beat)["open"]


def test_a_semantic_fault_is_reported_as_the_arbiters_and_nothing_is_sent(chain):
    """Pears offered against a want of apples, priced so the potentials
    balance: the structural half holds, so the contract says the leg
    verifies; the off-chain re-derivation refuses it. The challenger
    reports the fault and keeps its gas — that half is the arbiter's."""
    w3, address, key = chain
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"apple": [], "pear": [], "lesson": []}); cat.commit()
    pins = cat.pins
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("farm", Thing(("pear",), 40, "kg"), 80, **V, **pins),
              want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
              give("b1", Thing(("lesson",)), 80, **V, **pins),
              want("farm", Thing(("lesson",)), 85, **V, **pins)]
    book.publish_many(offers); book.commit()
    root = book.store.root
    snapshot = OfferRegistry(RecordStore.at(root, book.store.blobs))
    from loopmarket.clearing import LoopProposal
    from loopmarket.graph import Circulation
    from loopmarket.matching import Leg
    circ = Circulation((Leg(offers[1], (offers[0],)), Leg(offers[3], (offers[2],))))
    proposal = LoopProposal(circ, root, cat.root, "forger", NOW)
    assert MockClearing(book, cat, clock=lambda: NOW).rehearse(proposal).reason.startswith("leg fails")
    client = BeatClient("", address, key=key, client=w3)
    beat, _ = client.submit(submission(proposal, snapshot))
    book.mark_filled(proposal.fills(), circ.loop_id, proposal.to_record()); book.commit()
    result = challenge_beat(client, beat, [book], cat, now=NOW)
    assert result.evidence is not None and not result.verifies
    assert [v.chain for v in result.legs] == ["leg verifies"] * 2
    assert any(v.local and v.local.startswith("leg fails") for v in result.legs)
    assert result.sent is None and client.beat(beat)["open"]
    # the challenger may still insist on a leg; the contract answers, the beat stands
    forced = challenge_beat(client, beat, [book], cat, now=NOW, index=0)
    assert forced.sent == 0 and forced.reason == "leg verifies" and not forced.cancelled


def test_the_cli_posts_lists_challenges_and_finalizes(chain, tmp_path, monkeypatch):
    """`loop propose` posts the beat from a pinned rs: catalogue; `beats`
    lists it; `challenge 1` finds the loop record in my own book (the
    clearing book, no registry set), re-derives, asks the contract, sends
    nothing on a sound beat; after the window `finalize 1` records the fills."""
    from ontodag import __main__ as odag
    from ontodag.prelude import apply as apply_prelude
    from loopmarket import cli
    w3, address, key = chain
    monkeypatch.setenv("LOOP_HOME", str(tmp_path / "loop"))
    monkeypatch.setenv("ONTODAG_HOME", str(tmp_path / "odag"))
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    monkeypatch.setenv("LOOP_CONFIRM", "off")
    monkeypatch.setenv("LOOP_NOW", str(NOW))
    monkeypatch.setenv("LOOP_BEAT", f"chain:test@{address}")
    for var in ("LOOP_REGISTRY", "LOOP_PEERS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BEE_SIGNER", key)              # sending a challenge needs a key
    cli._OVERRIDES.clear()
    spec = f"rs:{tmp_path / 'cat'}"
    cat = odag.Session(odag._normalize_spec(spec))
    apply_prelude(cat.dag)
    for name in ("apple", "lesson"):
        cat.dag.put(name, [])
    cat.save()
    monkeypatch.setenv("LOOP_CATALOGUE", spec)
    monkeypatch.setattr(cli, "_beat_client", lambda session: BeatClient("", address, key=key, client=w3))

    def run(*argv):
        import io
        out, err = io.StringIO(), io.StringIO()
        code = cli.dispatch(list(argv), cli.Session(), out, err)
        return code, out.getvalue(), err.getvalue()

    monkeypatch.setenv("LOOP_MAKER", "farm")
    assert run("give", "100kg:5", "apple", "200")[0] == 0
    assert run("want", "lesson", "85")[0] == 0
    monkeypatch.setenv("LOOP_MAKER", "b1")
    assert run("want", "40kg", "apple", "90")[0] == 0
    assert run("give", "lesson", "80")[0] == 0
    code, out, err = run("propose")
    assert code == 0 and "posted beat " in out, (out, err)
    beat = int(out.split("posted beat ")[1].split(":")[0])
    code, out, _ = run("beats", "--open")
    assert code == 0 and f"beat {beat} by" in out and "open until block" in out
    code, out, err = run("challenge", str(beat))
    assert code == 0, (out, err)
    assert out.count("off chain: holds") == 2 and out.count("on chain:  leg verifies") == 2
    assert f"beat {beat} verifies" in out and "challenged" not in out
    # a leg named explicitly is put to the contract even so; the beat stands
    code, out, _ = run("challenge", str(beat), "0")
    assert code == 0 and "challenged leg 0: leg verifies" in out and f"beat {beat} stands" in out
    # a book that never saw the record has no evidence
    code, out, err = run("challenge", str(beat), "--book", f"rs:{tmp_path / 'stranger'}")
    assert code == 2 and "no evidence" in err
    w3.provider.ethereum_tester.mine_blocks(WINDOW + 1)
    code, out, _ = run("challenge", str(beat), "--check")
    assert code == 0 and "window closed" in out
    code, out, _ = run("finalize", str(beat))
    assert code == 0 and f"finalized beat {beat}: 4 fills" in out
    code, out, _ = run("beats")
    assert f"beat {beat} by" in out and "finalized" in out


def test_a_beat_the_contract_would_convict_is_never_posted(chain):
    """The submitter asks the contract's verifier before paying the bond
    (live finding 2026-09-18: a Swarm-addressed clearing book's honest beat
    was convictable under the sha256 verifier). Here the catalogue is
    unpinned: the local checklist accepts ('' == ''), the contract's pin
    check does not — so the receipt names the conviction and no beat exists."""
    w3, address, key = chain
    cat = Ontology(OntoDAG()).load({"apple": [], "lesson": []})
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    pins = dict(ontology_root="", registry_version="4.2", contract_version="0.1")
    book.publish_many([give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **pins),
                       want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
                       give("b1", Thing(("lesson",)), 80, **V, **pins),
                       want("farm", Thing(("lesson",)), 85, **V, **pins)])
    book.commit()
    client = BeatClient("", address, key=key, client=w3)
    before = len(client.beats())
    agent = SolverAgent(book, cat, clearing=ChainClearing(book, cat, beat_client=client, clock=lambda: NOW),
                        solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and not receipts[0].accepted
    assert receipts[0].reason.startswith("the contract would convict leg 0: "), receipts[0].reason
    assert len(client.beats()) == before                        # nothing posted, no bond spent
    assert not any(book.is_filled(o.offer_id) for o in book.offers(include_filled=True))


def test_a_beat_from_a_swarm_addressed_book_posts_and_verifies(chain, tmp_path):
    """The gap the 2026-09-18 live gate found, closed: a clearing book whose
    roots are Swarm references (recordstore `addressing="swarm"`) posts a
    beat the contract verifies under BMT addressing — the pre-bond dry run
    passes, the challenger's dry run says every leg verifies."""
    w3, address, key = chain
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"apple": [], "lesson": []}); cat.commit()
    pins = cat.pins
    book = OfferRegistry(RecordStore(DirBytesStore(str(tmp_path / "blobs"), addressing="swarm")))
    book.publish_many([give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **pins),
                       want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
                       give("b1", Thing(("lesson",)), 80, **V, **pins),
                       want("farm", Thing(("lesson",)), 85, **V, **pins)])
    book.commit()
    client = BeatClient("", address, key=key, client=w3)
    agent = SolverAgent(book, cat, clearing=ChainClearing(book, cat, beat_client=client, clock=lambda: NOW),
                        solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert receipts and receipts[0].accepted, receipts[0].reason
    beat = int(receipts[0].reason.split()[1])
    state = client.beat(beat)
    assert state["addressing"] == "swarm"
    result = challenge_beat(client, beat, [book], cat, now=NOW)
    assert result.verifies and [v.chain for v in result.legs] == ["leg verifies"] * 2


def test_a_beat_with_a_composed_want_posts_and_verifies(chain):
    """Composed wants on chain (2026-09-18): the evening — two tickets and a
    transport as one want — clears through `ChainClearing`, the pre-bond
    dry run passes (the contract checks give i hands over part i), and the
    challenger's dry run says every leg verifies."""
    from loopmarket import Parts
    w3, address, key = chain
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"ticket": [], "transport": [], "lesson": []}); cat.commit()
    pins = cat.pins
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many([
        want("buyer", Parts((Thing(("ticket",), 2), Thing(("transport",), 1, "run"))), 60, **V, **pins),
        give("theatre", Thing(("ticket",), 10, step=1), 200, **V, **pins),
        give("driver", Thing(("transport",), 1, "run"), 15, **V, **pins),
        give("buyer", Thing(("lesson",)), 30, nonce=1, **V, **pins),
        give("buyer", Thing(("lesson",)), 30, nonce=2, **V, **pins),
        want("theatre", Thing(("lesson",)), 42, **V, **pins),
        want("driver", Thing(("lesson",)), 31, **V, **pins)])
    book.commit()
    client = BeatClient("", address, key=key, client=w3)
    agent = SolverAgent(book, cat, clearing=ChainClearing(book, cat, beat_client=client, clock=lambda: NOW),
                        solver_id="t", min_surplus=0.0)
    receipts = agent.step(now=NOW)
    assert receipts and receipts[0].accepted, receipts[0].reason
    beat = int(receipts[0].reason.split()[1])
    assert client.beat(beat)["fills"] == 7                       # 3 wants + 4 gives, tickets in part
    result = challenge_beat(client, beat, [book], cat, now=NOW)
    assert result.verifies and [v.chain for v in result.legs] == ["leg verifies"] * 3
