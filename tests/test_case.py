"""A case before one named adjudicator (2026-10-01, Peter: the default
resolver of a leg is one adjudicator both sides accept, final). On a local
EVM: a giver's deposit reserved for a wanter with a plain key as resolver;
the adjudicator has no offer, only a key card. The wanter claims — sealed
to the adjudicator and to the giver; the giver sees it and answers; the
adjudicator holds and rules with reasons, the escrow pays the ruling and
the rest back; each party's `watch` reports what was sealed to it. The
wrong party is refused at every act, and a reservation whose resolver is a
contract (a bonded ladder) is claimed there, not here."""

import importlib.util
import os

import pytest

pytest.importorskip("coincurve", reason="sealed case records need the sig extra")

from loopmarket import cli  # noqa: E402
from loopmarket.sigs import maker_address  # noqa: E402
from test_cli import Runner, _od_with_prelude, env  # noqa: E402,F401  (fixture)

HERE = os.path.dirname(__file__)


def test_a_claim_is_answered_and_ruled_through_the_book_and_paid_by_the_escrow(env, tmp_path, monkeypatch):
    if not all(importlib.util.find_spec(m) for m in ("solcx", "eth_tester", "web3")):
        pytest.skip("needs the evm extra")
    import solcx
    from web3 import EthereumTesterProvider, Web3
    from loopmarket.escrow import EscrowClient
    solcx.install_solc("0.8.24")
    contracts = os.path.join(HERE, "..", "contracts")
    compiled = solcx.compile_files([os.path.join(contracts, "LoopEscrow.sol")], output_values=["abi", "bin"],
                                   solc_version="0.8.24", optimize=True, optimize_runs=200, via_ir=True,
                                   allow_paths=contracts)
    art = next(v for k, v in compiled.items() if k.endswith(":LoopEscrow"))
    w3 = Web3(EthereumTesterProvider())
    w3.eth.default_account = w3.eth.accounts[0]
    keys = {n: "0x" + c * 32 for n, c in (("giver", "61"), ("wanter", "62"), ("judge", "63"), ("clearing", "64"))}
    addr = {n: maker_address(k) for n, k in keys.items()}
    for a in addr.values():
        w3.eth.wait_for_transaction_receipt(w3.eth.send_transaction({"to": a, "value": 10 ** 20}))
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art["abi"], bytecode=art["bin"]).constructor(addr["clearing"], 2).transact())
    escrow = receipt["contractAddress"]
    client = lambda who: EscrowClient("", escrow, key=keys[who], client=w3)
    monkeypatch.setattr(cli, "_escrow_client", lambda session: client(os.environ["BEE_ROLE"]))
    monkeypatch.delenv("LOOP_MAKER")                         # identity = the signer's address
    run = Runner()

    def as_(who):
        monkeypatch.setenv("BEE_SIGNER", keys[who])
        monkeypatch.setenv("BEE_ROLE", who)

    for who in ("giver", "wanter", "judge"):                 # the judge has no offer: its card is how to reach it
        as_(who)
        assert "key card" in run.ok("keycard")
    offer, loop = "a1" * 32, "b2" * 32
    client("giver").deposit(offer, 2 * 10 ** 18)
    now = w3.eth.get_block("latest")["timestamp"]
    client("clearing").reserve(offer, loop, addr["wanter"], addr["judge"], 10 ** 18,
                               window=(now + 3600, now + 7200), claim_seconds=86_400)
    ref = [offer, "--loop", loop]

    # the wanter claims 0.6 of the reservation; the giver may not
    as_("giver")
    code, out, err = run("claim", *ref[:1], "0.6xDAI", *ref[1:])
    assert code != 0 and "is " + addr["wanter"] + "'s" in err
    as_("wanter")
    out = run.ok("claim", ref[0], "0.6xDAI", *ref[1:], "--evidence", "ee" * 32, "--text", "never came")
    assert f"sent to {addr['judge']}, {addr['giver']}" in out and "no notice sent first" in out
    sealed = run.session.book.case_record(loop, offer, "claim", addr["judge"])
    assert sealed["from"] == addr["wanter"] and "never came" not in str(sealed)

    # the giver sees the claim and answers, to the judge and the wanter
    as_("giver")
    out = run.ok("watch", "--once")
    assert f"case     {addr['wanter']} claims 0.6 on {offer[:12]}" in out
    assert f"sent to {addr['judge']}, {addr['wanter']}" in run.ok("answer", *ref, "--text", "came, an hour late")

    # the judge sees both, and rules — nobody else can
    as_("wanter")
    code, out, err = run("rule", *ref[:1], "1xDAI", *ref[1:], "--reason", "mine")
    assert code != 0 and "not this reservation's adjudicator" in err
    as_("judge")
    out = run.ok("watch", "--once")
    assert "claims 0.6" in out and "answers the claim" in out
    code, out, err = run("rule", *ref[:1], "0.4xDAI", *ref[1:])
    assert code != 0 and "--reason" in err
    assert "the claim is open" in run.ok("hold", *ref)
    before = {w: w3.eth.get_balance(addr[w]) for w in ("wanter", "giver")}
    out = run.ok("rule", ref[0], "0.4xDAI", *ref[1:], "--reason", "came late: half the claim")
    assert "ruled    0.4 to the wanter" in out and "(final)" in out
    assert w3.eth.get_balance(addr["wanter"]) - before["wanter"] == 4 * 10 ** 17
    assert w3.eth.get_balance(addr["giver"]) - before["giver"] == 6 * 10 ** 17
    assert client("judge").reservation(offer, loop)["settled"]

    # the reasons reach both parties, sealed
    as_("wanter")
    assert "rules 0.4 to the wanter: came late: half the claim" in run.ok("watch", "--once")
    listing = run.ok("cases")
    assert listing.count("claim  ") == 2 and "ruling" in listing and "answer" in listing
    as_("giver")
    assert "came late: half the claim" in run.ok("watch", "--once")

    # the personal view: the giver lost a ruling under the judge; a later fill of the same
    # deposit's offer, posted before that loss, is no new choice
    loop3 = "d4" * 32
    client("clearing").reserve(offer, loop3, addr["wanter"], addr["judge"], 10 ** 17,
                               window=(now + 3600, now + 7200), claim_seconds=86_400)
    as_("wanter")
    out = run.ok("adjudicators", "--trust", addr["giver"])
    assert f"{addr['judge']}: named in 2 leg(s) of my circle (2 mine)" in out
    assert "rulings: 0.4 of 1 to the wanter" in out and "chosen again after losing under it by: nobody" in out

    # a reservation whose resolver is a contract is claimed there, not here
    loop2 = "c3" * 32
    client("clearing").reserve(offer, loop2, addr["wanter"], escrow, 10 ** 17, window=(now + 3600, now + 7200),
                               claim_seconds=86_400)
    as_("wanter")
    code, out, err = run("claim", offer, "all", "--loop", loop2)
    assert code != 0 and "is a contract" in err


def test_the_fold_admits_a_case_record_only_as_its_writers_speech_to_its_named_recipient():
    from recordstore import MemoryBytesStore, RecordStore
    from loopmarket import OfferRegistry
    from loopmarket.case import claim_record, read, sealed
    from loopmarket.federation import MAKER, Aggregator
    from loopmarket.handoff import public_key_of
    kw, kj, kg = "0x" + "71" * 32, "0x" + "72" * 32, "0x" + "73" * 32
    W, J, G = (maker_address(k) for k in (kw, kj, kg))
    offer, loop = "a1" * 32, "b2" * 32
    side, opening = sealed(claim_record(W, G, offer, loop, 5, sent_at=1), sender=W, recipient=J,
                           recipient_public_key=public_key_of(kj))
    assert read(side, kj)["amount"] == 5 and opening["record"]["claimant"] == W
    blobs = MemoryBytesStore()
    mine, other = OfferRegistry(RecordStore(blobs)), OfferRegistry(RecordStore(blobs))
    mine.write_case(loop, offer, "claim", side)
    # a book does not know its owner, so whose speech a record is the fold decides
    other.store.put(f"case/{loop}/{offer}/claim/{J.lower()}", side)          # a copy of W's claim in G's book
    other.store.put(f"case/{loop}/{offer}/claim/{G.lower()}", dict(side, **{"from": G}))   # to J, keyed to G
    for b in (mine, other):
        b.commit()
    agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="agg")
    agg.announce(W, mine.store, role=MAKER)
    agg.announce(G, other.store, role=MAKER)
    m = agg.fold()
    folded = OfferRegistry(RecordStore(blobs, root=m.book_root))
    assert [(k, r["from"]) for _l, _o, k, r in folded.cases()] == [("claim", W)]
    rejected = {k: v["reason"] for k, v in RecordStore(blobs, root=m.provenance_root).items("reject/")}
    assert rejected[f"reject/{G}/case/{loop}/{offer}/claim/{J.lower()}"] == \
        "a case record from a key other than the book's owner"
    assert rejected[f"reject/{G}/case/{loop}/{offer}/claim/{G.lower()}"] == \
        "a case record addressed otherwise than its key says"
