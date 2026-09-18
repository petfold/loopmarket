"""The sealed-proposal beat (P2, `docs/plans/P2-batch-auction.md` §2–§6,
built 2026-09-18): commitments and reveals on a fixed cadence, the
numeraire-free score, the fairness filter with the baseline as reserve bid,
deterministic offer-disjoint selection, and the outcome posted to
`BeatClearing` and recorded. The logic runs in memory; the contract half
skips without the `evm` extra."""

import importlib.util

import pytest
from ontodag import OntoDAG

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import MockClearing, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.auction import (
    CLOSED, COMMIT, REVEAL, Candidate, MemorySealedBeat, baseline_proposals, bundle_bytes,
    fairness_filter, outcome, references, score, seal, select, unbundle,
)
from loopmarket.clearing import LoopProposal

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def _pinned():
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"apple": [], "lesson": [], "repair": []})
    cat.commit()
    return cat


def _book(cat):
    """Two loops competing for the farm's apples: b1's (gain ~19.5%) and b2's
    (~6.3%, through the same give), each closing through the farm's wants."""
    pins = cat.pins
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    offers = [give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, **pins),   # 2/kg
              want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
              give("b1", Thing(("lesson",)), 80, **V, **pins),
              want("farm", Thing(("lesson",)), 85, **V, **pins),
              want("b2", Thing(("apple",), 40, "kg"), 84, **V, **pins),          # gain 6%, clearable
              give("b2", Thing(("repair",)), 80, **V, **pins),
              want("farm", Thing(("repair",)), 81, **V, **pins)]
    book.publish_many(offers); book.commit()
    return book, offers


def _loops(book, cat):
    """Every profitable loop on the book, as proposals, better first."""
    root, snapshot = book.snapshot()
    agent = SolverAgent(snapshot, cat, clearing=None, solver_id="s", min_surplus=0.0, max_loops_per_step=10)
    _r, loops = agent.find_loops(now=NOW)
    props = [LoopProposal(l, root, cat.root, "s", NOW) for l in loops]
    return root, snapshot, sorted(props, key=lambda p: -p.circulation.surplus)


def _two_loops(cat, book):
    """The good loop (b1) and the worse one (b2), built explicitly since the
    baseline's disjoint hunt returns only one of two loops sharing a give."""
    from loopmarket.graph import Loop
    from loopmarket.matching import Match
    root, snapshot = book.snapshot()
    o = {(x.maker, x.kind, x.thing.concepts[0] if not x.composed else "parts"): x
         for x in snapshot.offers(include_filled=True)}
    good = Loop((Match(give=o[("farm", "give", "apple")], want=o[("b1", "want", "apple")]),
                 Match(give=o[("b1", "give", "lesson")], want=o[("farm", "want", "lesson")])))
    worse = Loop((Match(give=o[("farm", "give", "apple")], want=o[("b2", "want", "apple")]),
                  Match(give=o[("b2", "give", "repair")], want=o[("farm", "want", "repair")])))
    assert good.surplus > worse.surplus > 0
    return root, snapshot, LoopProposal(good, root, cat.root, "a", NOW), LoopProposal(worse, root, cat.root, "b", NOW)


def test_score_references_filter_and_selection_are_exact_and_deterministic():
    cat = _pinned(); book, _ = _book(cat)
    root, snapshot, good, worse = _two_loops(cat, book)
    a, b = Candidate(good, "a", b"A"), Candidate(worse, "b", b"B")
    assert score([a]) == 1 + good.circulation.surplus and score([a, b]) == score([a]) * score([b])
    ref = references([a, b])
    farm_apples = next(iter(a.offers & b.offers))
    assert ref[farm_apples] == a.gain                       # the shared give's reference is the better loop
    survivors, dropped = fairness_filter([a, b])
    assert survivors == [a] and worse.circulation.loop_id in dropped and "does better" in dropped[worse.circulation.loop_id]
    assert select([a, b]) == [a]                            # exact: the two overlap, the better wins
    assert select([b, a]) == [a]                            # order of arrival is irrelevant
    # a bundle seals and opens to the same proposals
    data = bundle_bytes([good])
    commitment, salt = seal(data)
    assert seal(data, salt)[0] == commitment and len(commitment) == 32
    assert [p.circulation.loop_id for p in unbundle(data, snapshot)] == [good.circulation.loop_id]


def test_the_reserve_bid_beats_a_ring_that_withholds_the_good_loop():
    """Only the worse loop is revealed; the baseline's reserve bid brings
    the better one, the fairness filter drops the revealed one for giving
    the farm less than its reference, and the reserve wins."""
    cat = _pinned(); book, _ = _book(cat)
    root, snapshot, good, worse = _two_loops(cat, book)
    result = outcome(7, [("0xring", bundle_bytes([worse]))], snapshot, cat, now=NOW,
                     baseline=baseline_proposals(snapshot, cat, now=NOW))
    assert [c.loop_id for c in result.winners] == [good.circulation.loop_id]
    assert result.winners[0].solver == "baseline" and worse.circulation.loop_id in result.dropped
    # a proposal for another root, or one that fails re-derivation, is rejected with its reason
    stale = LoopProposal(worse.loop, "00" * 32, cat.root, "b", NOW)
    r2 = outcome(8, [("0xb", bundle_bytes([stale]))], snapshot, cat, now=NOW)
    assert "not the beat's" in r2.rejected[stale.circulation.loop_id]
    r3 = outcome(9, [("0xb", b"garbage")], snapshot, cat, now=NOW)
    assert "unreadable" in r3.rejected["0xb"] and r3.winners == []


def test_the_memory_beat_keeps_the_phases():
    cat = _pinned(); book, _ = _book(cat)
    root, snapshot, good, worse = _two_loops(cat, book)
    beat = MemorySealedBeat(period=10, commit_blocks=4)
    a, b = beat.for_solver("0xa"), beat.for_solver("0xb")
    da, db = bundle_bytes([good]), bundle_bytes([worse])
    ca, sa = seal(da); cb, sb = seal(db)
    assert beat.phase(0) == COMMIT and a.commit(ca) == 0 and b.commit(cb) == 0
    with pytest.raises(ValueError, match="already committed"):
        a.commit(ca)
    with pytest.raises(ValueError, match="not the reveal phase"):
        a.reveal(0, da, sa)
    beat.mine(4)
    assert beat.phase(0) == REVEAL
    with pytest.raises(ValueError, match="not the committed"):
        a.reveal(0, da, sb)
    a.reveal(0, da, sa); b.reveal(0, db, sb)
    with pytest.raises(ValueError, match="already revealed"):
        a.reveal(0, da, sa)
    assert sorted(s for s, _ in beat.revealed(0)) == ["0xa", "0xb"] and set(beat.committers(0)) == {"0xa", "0xb"}
    beat.mine(6)
    assert beat.phase(0) == CLOSED and beat.current() == 1
    result = outcome(0, beat.revealed(0), snapshot, cat, now=NOW,
                     baseline=baseline_proposals(snapshot, cat, now=NOW))
    assert [c.loop_id for c in result.winners] == [good.circulation.loop_id] and result.winners[0].solver == "0xa"
    a.record(0, result.revealed_set, result.winners_hash)
    b.record(0, result.revealed_set, result.winners_hash)            # the same derivation: no dispute
    assert beat.outcome(0)["submitter"] == "0xa" and beat.disputes == []
    b.record(0, result.revealed_set, b"\x00" * 32)
    assert beat.disputes and beat.disputes[0][1] == "0xb"


# --------------------------------------------------------------------------- #
# The contract, on a local EVM
# --------------------------------------------------------------------------- #

_HAVE_EVM = all(importlib.util.find_spec(m) for m in ("solcx", "eth_tester", "web3"))
needs_evm = pytest.mark.skipif(not _HAVE_EVM, reason="needs the evm extra: pip install 'loopmarket[evm]'")

PERIOD, COMMIT_BLOCKS, BOND, WINDOW = 12, 5, 10 ** 16, 3


@pytest.fixture(scope="module")
def chain():
    from web3 import EthereumTesterProvider, Web3
    from loopmarket.auction import abi as sealed_abi
    from loopmarket.beat import abi as beat_abi
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    art = beat_abi()
    r = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor(BOND, WINDOW, w3.eth.accounts[2]).transact())
    clearing = r["contractAddress"]
    art2 = sealed_abi()
    r2 = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art2["abi"], bytecode=art2["bytecode"]).constructor(PERIOD, COMMIT_BLOCKS, clearing).transact())
    keys = [w3.provider.ethereum_tester.backend.account_keys[i].to_hex() for i in range(3)]
    return w3, clearing, r2["contractAddress"], keys


@needs_evm
def test_commit_reveal_outcome_and_record_on_chain(chain):
    from loopmarket.auction import SealedBeatClient
    from loopmarket.beat import BeatClient, challenge_beat
    from loopmarket.clearing import ChainClearing
    w3, clearing_addr, sealed_addr, keys = chain
    cat = _pinned(); book, _ = _book(cat)
    root, snapshot, good, worse = _two_loops(cat, book)
    a = SealedBeatClient("", sealed_addr, key=keys[0], client=w3)
    b = SealedBeatClient("", sealed_addr, key=keys[1], client=w3)
    tester = w3.provider.ethereum_tester
    # to the start of a fresh beat's commit phase
    beat = a.current() + 1
    tester.mine_blocks(a.window(beat)[0] - a.block())
    assert a.phase(beat) == COMMIT
    da, db = bundle_bytes([good]), bundle_bytes([worse])
    ca, sa = seal(da); cb, sb = seal(db)
    assert a.commit(ca) == beat and b.commit(cb) == beat
    with pytest.raises(Exception, match="already committed"):
        a.commit(ca)
    with pytest.raises(Exception, match="not the reveal phase"):
        a.contract().functions.reveal(beat, da, sa).call({"from": a.solver})
    tester.mine_blocks(a.window(beat)[1] - a.block())
    assert a.phase(beat) == REVEAL
    with pytest.raises(Exception, match="not the committed"):
        a.contract().functions.reveal(beat, da, sb).call({"from": a.solver})
    a.reveal(beat, da, sa); b.reveal(beat, db, sb)
    revealed = a.revealed(beat)
    assert sorted(s.lower() for s, _ in revealed) == sorted(x.lower() for x in (a.solver, b.solver))
    assert dict(revealed)[a.solver] == da
    tester.mine_blocks(a.window(beat)[2] - a.block())
    assert a.phase(beat) == CLOSED
    # the outcome: a's good loop wins, b's is dropped; posted to BeatClearing, recorded
    result = outcome(beat, revealed, snapshot, cat, now=NOW, baseline=baseline_proposals(snapshot, cat, now=NOW))
    assert [c.loop_id for c in result.winners] == [good.circulation.loop_id]
    assert worse.circulation.loop_id in result.dropped
    beats = BeatClient("", clearing_addr, key=keys[0], client=w3)
    clearing = ChainClearing(book, cat, beat_client=beats, clock=lambda: NOW)
    receipt = clearing.submit(result.winners[0].proposal)
    assert receipt.accepted and receipt.reason.startswith("beat ")
    posted = int(receipt.reason.split()[1])
    assert challenge_beat(beats, posted, [book], cat, now=NOW).verifies
    a.record(beat, result.revealed_set, result.winners_hash)
    assert a.outcome(beat)["submitter"] == a.solver and a.outcome(beat)["winners"] == result.winners_hash
    # a second submitter deriving the same records nothing new; a different derivation is a dispute
    b.record(beat, result.revealed_set, result.winners_hash)
    assert a.outcome(beat)["submitter"] == a.solver
    rc = b._send(b.contract().functions.record(beat, result.revealed_set, b"\x01" * 32))
    assert b.contract().events.Disputed().process_receipt(rc)[0]["args"]["submitter"] == b.solver
    assert a.outcome(beat + 5) is None


@needs_evm
def test_the_cli_commits_reveals_and_derives_the_outcome(chain, tmp_path, monkeypatch):
    """`loop commit` seals this session's loops for the memory beat and keeps
    the opening in its home; `loop reveal` opens it in the reveal phase;
    `loop outcome` derives the winners once the beat closes and posts them
    to the clearing contract; `loop sealed` shows the phases throughout."""
    import io
    from ontodag import __main__ as odag
    from ontodag.prelude import apply as apply_prelude
    from loopmarket import cli
    from loopmarket.auction import MemorySealedBeat
    from loopmarket.beat import BeatClient
    w3, clearing_addr, _sealed_addr, keys = chain
    monkeypatch.setenv("LOOP_HOME", str(tmp_path / "loop"))
    monkeypatch.setenv("ONTODAG_HOME", str(tmp_path / "odag"))
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    monkeypatch.setenv("LOOP_CONFIRM", "off")
    monkeypatch.setenv("LOOP_NOW", str(NOW))
    monkeypatch.setenv("LOOP_AUCTION", "memory:")
    monkeypatch.setenv("LOOP_BEAT", f"chain:test@{clearing_addr}")
    monkeypatch.setenv("BEE_SIGNER", keys[0])
    for var in ("LOOP_REGISTRY", "LOOP_PEERS"):
        monkeypatch.delenv(var, raising=False)
    cli._OVERRIDES.clear()
    spec = f"rs:{tmp_path / 'cat'}"
    cat = odag.Session(odag._normalize_spec(spec))
    apply_prelude(cat.dag)
    for name in ("apple", "lesson"):
        cat.dag.put(name, [])
    cat.save()
    monkeypatch.setenv("LOOP_CATALOGUE", spec)
    monkeypatch.setattr(cli, "_beat_client", lambda session: BeatClient("", clearing_addr, key=keys[0], client=w3))
    memory = MemorySealedBeat(period=10, commit_blocks=4, solver="loop-cli")
    monkeypatch.setattr(cli, "_MEMORY_SEALED", memory)

    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        code = cli.dispatch(list(argv), cli.Session(), out, err)
        return code, out.getvalue(), err.getvalue()

    monkeypatch.setenv("LOOP_MAKER", "farm")
    assert run("give", "100kg:5", "apple", "200")[0] == 0 and run("want", "lesson", "85")[0] == 0
    monkeypatch.setenv("LOOP_MAKER", "b1")
    assert run("want", "40kg", "apple", "90")[0] == 0 and run("give", "lesson", "80")[0] == 0
    code, out, err = run("commit")
    assert code == 0 and "committed beat 0: 1 loop(s)" in out, (out, err)
    code, out, _ = run("sealed")
    assert "beat 0: commit" in out and "loop-cli committed" in out
    code, out, err = run("reveal")
    assert code != 0 and "commit" in err                              # too early
    memory.mine(4)
    code, out, err = run("reveal")
    assert code == 0 and "revealed beat 0: 1 loop(s)" in out, (out, err)
    code, out, _ = run("sealed", "0")
    assert "beat 0: reveal" in out and "loop-cli revealed" in out
    code, out, err = run("outcome", "0")
    assert code == 2 and "closes at block 10" in err
    memory.mine(6)
    code, out, err = run("outcome", "0", "--check")
    assert code == 0 and "1 revealed, 1 candidate loop(s), 1 winner(s)" in out and "wins (loop-cli)" in out, (out, err)
    code, out, err = run("outcome", "0")
    assert code == 0 and "posted beat " in out and "recorded beat 0: 1 loop(s) posted" in out, (out, err)
    assert memory.outcome(0)["submitter"] == "loop-cli"
    code, out, _ = run("sealed", "0")
    assert "outcome recorded by loop-cli" in out
    code, out, _ = run("beats")
    assert "open until block" in out
