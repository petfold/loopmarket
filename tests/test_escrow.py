"""The crypto escrow (P3 §5a/§5e, 2026-09-19): a giver's deposit behind
an offer id, a share reserved per fill at clearing, settled by timeout or
by the parties' own acts wherever nothing is disputed — quiet after the
window, the wanter's countersignature, the giver's cancellation at the
ladder — and by the resolver's `hold`/`resolve` only for a contested
claim (factbond's, or one key); the giver withdraws only after notice
and only what no fill holds. Native coin and ERC-20. Since 2026-09-28
(E1): cover is never countersigned, `assign`, the two-signature split,
`extendClaim`, the claim read inside `hold` and a retraction reopening,
refused payouts credited. Skips without the `evm` extra."""

import importlib.util
import os
from fractions import Fraction

import pytest

from loopmarket.escrow import EscrowClient, to_wei

_HAVE_EVM = all(importlib.util.find_spec(m) for m in ("solcx", "eth_tester", "web3"))
pytestmark = pytest.mark.skipif(not _HAVE_EVM, reason="needs the evm extra: pip install 'loopmarket[evm]'")

HERE = os.path.dirname(__file__)
NOTICE = 3
OFFER = "ab" * 32
LOOP = "cd" * 32
LOOP2 = "ef" * 32

TOKEN_SRC = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Coin {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    constructor() { balanceOf[msg.sender] = 1e24; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transfer(address to, uint256 a) external returns (bool) {
        balanceOf[msg.sender] -= a; balanceOf[to] += a; return true; }
    function transferFrom(address f, address to, uint256 a) external returns (bool) {
        allowance[f][msg.sender] -= a; balanceOf[f] -= a; balanceOf[to] += a; return true; }
}
"""


@pytest.fixture(scope="module")
def chain():
    import solcx
    from web3 import EthereumTesterProvider, Web3
    solcx.install_solc("0.8.24")
    compiled = solcx.compile_files([os.path.join(HERE, "..", "contracts", "LoopEscrow.sol")],
                                   output_values=["abi", "bin"], solc_version="0.8.24",
                                   optimize=True, optimize_runs=200, via_ir=True,
                                   allow_paths=os.path.join(HERE, "..", "contracts"))
    art = next(v for k, v in compiled.items() if k.endswith(":LoopEscrow"))
    coin_art = solcx.compile_source(TOKEN_SRC, output_values=["abi", "bin"], solc_version="0.8.24")["<stdin>:Coin"]
    w3 = Web3(EthereumTesterProvider())
    accounts = w3.eth.accounts
    w3.eth.default_account = accounts[0]
    clearing = accounts[1]
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art["abi"], bytecode=art["bin"]).constructor(clearing, NOTICE).transact())
    escrow = w3.eth.contract(address=receipt["contractAddress"], abi=art["abi"])
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=coin_art["abi"], bytecode=coin_art["bin"]).constructor().transact())
    coin = w3.eth.contract(address=receipt["contractAddress"], abi=coin_art["abi"])
    return w3, escrow, coin, clearing


def _as(w3, who):
    """The tester accounts have no keys to sign with, so the calls here go
    through the contract directly as `who`; `EscrowClient` is exercised in
    its read path and in the artifact test below."""
    return {"from": who}


def _reverts(w3, fn, who, value=0):
    from eth_tester.exceptions import TransactionFailed
    try:
        fn.transact({"from": who, "value": value})
    except (TransactionFailed, ValueError) as exc:
        return str(exc)
    raise AssertionError("did not revert")


def test_to_wei_is_exact_or_refuses():
    assert to_wei(Fraction(5, 2)) == 25 * 10 ** 17
    assert to_wei("1/1000") == 10 ** 15
    with pytest.raises(ValueError):
        to_wei(Fraction(1, 3))


def _terms(start, end, claim=100, min_challenge=0, min_ruling=0, claim_only=False):
    return (start, end, claim, min_challenge, min_ruling, claim_only)


def _reserve(escrow, clearing, offer, loop, wanter, resolver, amount, start, end, claim=100, ladder=(), **terms):
    leads, amounts = [l for l, _ in ladder], [a for _, a in ladder]
    escrow.functions.reserve(offer, loop, wanter, resolver, amount, _terms(start, end, claim, **terms),
                             leads, amounts).transact({"from": clearing})


def _now(w3):
    return w3.eth.get_block("latest")["timestamp"]


def _advance(w3, seconds):
    w3.provider.ethereum_tester.time_travel(_now(w3) + seconds)
    w3.provider.ethereum_tester.mine_block()


def test_undisputed_paths_settle_without_a_ruling(chain):
    """Quiet after the claim period: anyone settles and the giver gets the
    reservation back; a countersignature returns it now; a cancellation
    pays the ladder's amount at that lead. No resolver involved."""
    w3, escrow, coin, clearing = chain
    giver, wanter, resolver = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[4]
    offer = bytes.fromhex(OFFER)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    assert escrow.functions.free(offer).call() == 10 ** 18
    now = _now(w3)
    quiet, signed, cancelled = (bytes.fromhex(x * 32) for x in ("aa", "bb", "cc"))
    assert "not the clearing" in _reverts(
        w3, escrow.functions.reserve(offer, quiet, wanter, resolver, 1, _terms(now, now, 1), [], []), giver)
    _reserve(escrow, clearing, offer, quiet, wanter, resolver, 2 * 10 ** 17, now + 1000, now + 2000)
    _reserve(escrow, clearing, offer, signed, wanter, resolver, 3 * 10 ** 17, now + 1000, now + 2000)
    # the ladder: 1/10 of the reservation a day out, the whole of it at the door
    _reserve(escrow, clearing, offer, cancelled, wanter, resolver, 4 * 10 ** 17, now + 86_400, now + 90_000,
             ladder=[(86_400, 4 * 10 ** 16), (0, 4 * 10 ** 17)])
    assert escrow.functions.free(offer).call() == 10 ** 17
    assert "beyond what is free" in _reverts(
        w3, escrow.functions.reserve(offer, bytes(32), wanter, resolver, 2 * 10 ** 17, _terms(now, now, 1), [], []),
        clearing)
    # quiet: not before the claim period ends
    assert "claim period open" in _reverts(w3, escrow.functions.settle(offer, quiet), wanter)
    # countersigned: the wanter alone, and now
    assert "not the wanter" in _reverts(w3, escrow.functions.countersign(offer, signed), giver)
    before = w3.eth.get_balance(giver)
    escrow.functions.countersign(offer, signed).transact({"from": wanter})
    assert w3.eth.get_balance(giver) - before == 3 * 10 ** 17
    # cancelled half a day before the window: linear between the two points = 0.22e18
    assert escrow.functions.ladderAt(offer, cancelled, 43_200).call() == 22 * 10 ** 16
    _advance(w3, 43_200)
    before_w, before_g = w3.eth.get_balance(wanter), w3.eth.get_balance(giver)
    receipt = w3.eth.wait_for_transaction_receipt(escrow.functions.cancel(offer, cancelled).transact({"from": giver}))
    gas = receipt["gasUsed"] * w3.eth.get_transaction(receipt["transactionHash"])["gasPrice"]
    paid = w3.eth.get_balance(wanter) - before_w
    assert 21 * 10 ** 16 <= paid <= 23 * 10 ** 16            # a few seconds of block time move the lead
    assert w3.eth.get_balance(giver) - before_g == 4 * 10 ** 17 - paid - gas
    # quiet: after the claim period anyone settles, to the giver
    _advance(w3, 2000)
    before = w3.eth.get_balance(giver)
    escrow.functions.settle(offer, quiet).transact({"from": resolver})
    assert w3.eth.get_balance(giver) - before == 2 * 10 ** 17
    assert "not open" in _reverts(w3, escrow.functions.settle(offer, quiet), wanter)
    assert escrow.functions.held(offer).call() == escrow.functions.free(offer).call() == 10 ** 17
    # the giver leaves only after notice, and only with what is free
    assert "notice not served" in _reverts(w3, escrow.functions.withdraw(offer, 1), giver)
    escrow.functions.notice(offer).transact({"from": giver})
    for _ in range(NOTICE):
        w3.provider.ethereum_tester.mine_block()
    assert "beyond what is free" in _reverts(w3, escrow.functions.withdraw(offer, 2 * 10 ** 17), giver)
    escrow.functions.withdraw(offer, 10 ** 17).transact({"from": giver})
    assert escrow.functions.held(offer).call() == 0
    assert "another deposit" in _reverts(w3, escrow.functions.deposit(offer), wanter, value=1)


def test_a_contested_claim_is_the_resolvers_and_bounded_to_the_fill(chain):
    """`hold` stops the quiet timeout; `resolve` pays what the wanter gets
    and returns the rest — only the reservation's resolver, only within the
    reservation, only to that wanter and giver."""
    w3, escrow, coin, clearing = chain
    giver, wanter, resolver = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[4]
    offer, loop = bytes.fromhex("33" * 32), bytes.fromhex(LOOP)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    _reserve(escrow, clearing, offer, loop, wanter, resolver, 5 * 10 ** 17, now + 10, now + 20, claim=100)
    assert "not the resolver" in _reverts(w3, escrow.functions.hold(offer, loop), clearing)
    assert "no claim held" in _reverts(w3, escrow.functions.resolve(offer, loop, 1), resolver)
    escrow.functions.hold(offer, loop).transact({"from": resolver})
    _advance(w3, 200)
    assert "a claim is open" in _reverts(w3, escrow.functions.settle(offer, loop), giver)
    assert "not open" in _reverts(w3, escrow.functions.cancel(offer, loop), giver)
    assert "beyond the reservation" in _reverts(w3, escrow.functions.resolve(offer, loop, 6 * 10 ** 17), resolver)
    before_w, before_g = w3.eth.get_balance(wanter), w3.eth.get_balance(giver)
    escrow.functions.resolve(offer, loop, 3 * 10 ** 17).transact({"from": resolver})
    assert w3.eth.get_balance(wanter) - before_w == 3 * 10 ** 17
    assert w3.eth.get_balance(giver) - before_g == 2 * 10 ** 17
    assert escrow.functions.free(offer).call() == 5 * 10 ** 17
    assert "claim period over" not in _reverts(w3, escrow.functions.hold(offer, loop), resolver)  # settled: not open


def test_erc20_deposit_and_resolve(chain):
    w3, escrow, coin, clearing = chain
    giver, wanter, resolver = w3.eth.accounts[0], w3.eth.accounts[3], w3.eth.accounts[4]
    offer, loop = bytes.fromhex("11" * 32), bytes.fromhex(LOOP)
    coin.functions.approve(escrow.address, 500).transact({"from": giver})
    escrow.functions.depositToken(offer, coin.address, 500).transact({"from": giver})
    assert escrow.functions.held(offer).call() == 500
    assert "a token" in _reverts(w3, escrow.functions.depositToken(offer, "0x" + "00" * 20, 1), giver)
    now = _now(w3)
    _reserve(escrow, clearing, offer, loop, wanter, resolver, 200, now, now + 10)
    escrow.functions.hold(offer, loop).transact({"from": resolver})
    escrow.functions.resolve(offer, loop, 200).transact({"from": resolver})
    assert coin.functions.balanceOf(wanter).call() == 200
    assert escrow.functions.held(offer).call() == 300


def test_offers_signed_by_state(chain):
    w3, escrow, coin, clearing = chain
    offer = bytes.fromhex("22" * 32)
    assert not escrow.functions.offers(offer).call()
    assert "not the owner" in _reverts(w3, escrow.functions.registerOffer(offer), clearing)
    escrow.functions.registerOffer(offer).transact({"from": w3.eth.accounts[0]})
    assert escrow.functions.offers(offer).call()


def test_client_reads_and_the_shipped_artifact_match_the_source(chain):
    from loopmarket.escrow import abi
    w3, escrow, coin, clearing = chain
    client = EscrowClient("", escrow.address, client=w3)
    assert client.held("11" * 32) == 300
    r = client.reservation("11" * 32, LOOP)
    assert r["amount"] == 200 and r["settled"] and not r["held"] and r["resolver"] == w3.eth.accounts[4]
    assert not r["claim_only"] and r["claim"] == 0
    assert client.deposit_of("11" * 32)["token"] == coin.address
    names = {e["name"] for e in abi()["abi"] if e["type"] == "function"}
    assert {"deposit", "depositToken", "reserve", "cancel", "countersign", "settle", "hold", "resolve",
            "notice", "withdraw", "held", "free", "ladderAt", "assign", "extendClaim", "collect", "owed",
            "terms"} <= names
    shipped = next(e for e in abi()["abi"] if e.get("name") == "reserve")
    assert [i["type"] for i in shipped["inputs"]] == [i["type"] for i in next(
        e for e in escrow.abi if e.get("name") == "reserve")["inputs"]]
    with pytest.raises(ValueError):
        client.deposit(OFFER, 1)


def _factbond(w3, **ladder):
    """factbond's `Assertions` from the sibling checkout, one rung (no arbiter):
    fee 0.001, floor 0.01, the challenge window 100 s by default within
    [10 s, 60 d], the ruling window 100 s at least, the ruling fee half the floor."""
    import solcx
    src = os.path.join(HERE, "..", "..", "factbond", "contracts", "Assertions.sol")
    if not os.path.exists(src):
        pytest.skip("needs ../factbond (contracts/Assertions.sol)")
    compiled = solcx.compile_files([src], output_values=["abi", "bin"], solc_version="0.8.24",
                                   optimize=True, optimize_runs=200, via_ir=True,
                                   allow_paths=os.path.dirname(src))
    art = next(v for k, v in compiled.items() if k.endswith(":Assertions"))
    adjudicator, treasury = w3.eth.accounts[5], w3.eth.accounts[9]
    fee, floor = 10 ** 15, 10 ** 16
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art["abi"], bytecode=art["bin"]).constructor(
            adjudicator, treasury, fee, floor, 100, 10, 60 * 86400, 100, 90 * 86400, floor // 2,
            ("0x" + "00" * 20, 0, 0, 0)).transact())
    return w3.eth.contract(address=receipt["contractAddress"], abi=art["abi"]), adjudicator, fee, floor


def test_factbond_as_the_resolver(chain):
    """Custody here, adjudication in factbond (P3 §5e): a reservation whose
    resolver is factbond's `Assertions` contract. The wanter asserts the
    giver failed — factbond holds the reservation through the key-only
    `hold(subject)`; undisputed, the claim certifies by timeout and factbond
    resolves the payout; disputed and refuted, the giver gets the reservation
    back. Skips unless the sibling factbond checkout is beside this one."""
    w3, escrow, coin, clearing = chain
    factbond, adjudicator, fee, floor = _factbond(w3)
    giver, wanter = w3.eth.accounts[2], w3.eth.accounts[3]
    offer = bytes.fromhex("77" * 32)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    quiet, refuted = bytes.fromhex("a1" * 32), bytes.fromhex("a2" * 32)
    for loop in (quiet, refuted):
        _reserve(escrow, clearing, offer, loop, wanter, factbond.address, 4 * 10 ** 17, now, now + 10, claim=1000)
    # a claim on a subject the escrow never gave factbond is refused by the escrow's hold
    subj_q = escrow.functions.key(offer, quiet).call()
    other = escrow.functions.key(offer, bytes.fromhex("a3" * 32)).call()
    assert "not the resolver" in _reverts(w3, factbond.functions.assert_(other, escrow.address, 1, 990, 0, 0, giver), wanter, value=fee + floor)
    # undisputed: the wanter asserts failure claiming the reservation, and after the window factbond pays it out
    factbond.functions.assert_(subj_q, escrow.address, 4 * 10 ** 17, 990, 0, 0, giver).transact({"from": wanter, "value": fee + floor})
    id_q = factbond.functions.count().call()
    assert escrow.functions.reservation(offer, quiet).call()[6]                    # held
    assert escrow.functions.terms(offer, quiet).call()[3] == id_q                  # the claim it holds for
    assert "a claim is open" in _reverts(w3, escrow.functions.settle(offer, quiet), giver)
    _advance(w3, 200)
    before = w3.eth.get_balance(wanter)
    factbond.functions.certify(id_q).transact({"from": w3.eth.accounts[4]})
    assert w3.eth.get_balance(wanter) - before == 4 * 10 ** 17 + floor            # the payout, and her bond back
    assert escrow.functions.reservation(offer, quiet).call()[7]                    # settled
    # disputed and refuted: the giver contests, the adjudicator rules against the claim, the giver is refunded
    subj_r = escrow.functions.key(offer, refuted).call()
    factbond.functions.assert_(subj_r, escrow.address, 4 * 10 ** 17, 990, 0, 0, giver).transact({"from": wanter, "value": fee + floor})
    id_r = factbond.functions.count().call()
    factbond.functions.dispute(id_r).transact({"from": giver, "value": factbond.functions.stakeFor(floor, 990).call()})
    before = w3.eth.get_balance(giver)
    factbond.functions.rule(id_r, False).transact({"from": adjudicator})
    assert w3.eth.get_balance(giver) - before == 4 * 10 ** 17 + 2 * floor - floor // 2  # reservation, stake, her bond less the fee
    assert escrow.functions.free(offer).call() == 2 * 10 ** 17


def test_the_escrow_opens_only_the_wanters_claim_and_a_retraction_reopens(chain):
    """factbond's `assert_` is open to anyone and its `retract` closes with
    outcome 0, so the escrow reads the claim inside `hold` (2026-09-28).
    Before, a stranger's assert-and-retract refunded the giver for the fee,
    and a claim above the reservation could never certify. Now: only the
    wanter's claim, naming the giver, a payout within the reservation, the
    reservation's least windows, one at a time; a retraction reopens."""
    w3, escrow, coin, clearing = chain
    factbond, adjudicator, fee, floor = _factbond(w3)
    giver, wanter, stranger = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[7]
    offer, loop = bytes.fromhex("78" * 32), bytes.fromhex("b1" * 32)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    _reserve(escrow, clearing, offer, loop, wanter, factbond.address, 4 * 10 ** 17, now, now + 10, claim=10_000,
             min_challenge=500, min_ruling=300)
    subj = escrow.functions.key(offer, loop).call()
    stake = fee + floor

    def claim(who, outcome=4 * 10 ** 17, window=600, ruling=300, about=giver):
        return factbond.functions.assert_(subj, escrow.address, outcome, 990, window, ruling, about)

    assert "the claim is the wanter's" in _reverts(w3, claim(stranger), stranger, value=stake)
    assert "the claim is the wanter's" in _reverts(w3, claim(giver, outcome=1), giver, value=stake)
    assert "names the giver" in _reverts(w3, claim(wanter, about="0x" + "00" * 20), wanter, value=stake)
    assert "within the reservation" in _reverts(w3, claim(wanter, outcome=5 * 10 ** 17), wanter, value=stake)
    assert "within the reservation" in _reverts(w3, claim(wanter, outcome=0), wanter, value=stake)
    assert "challenge window too short" in _reverts(w3, claim(wanter, window=100), wanter, value=stake)
    assert "ruling window too short" in _reverts(w3, claim(wanter, ruling=200), wanter, value=stake)
    assert not escrow.functions.reservation(offer, loop).call()[6]                 # none of them opened
    # the wanter's claim opens; a second one waits for it to close
    claim(wanter).transact({"from": wanter, "value": stake})
    first = factbond.functions.count().call()
    assert "a claim is open" in _reverts(w3, claim(wanter), wanter, value=stake)
    # the wanter withdraws it: nobody ruled, so the reservation reopens instead of refunding the giver
    before = w3.eth.get_balance(giver)
    factbond.functions.retract(first).transact({"from": wanter})
    r = escrow.functions.reservation(offer, loop).call()
    assert not r[6] and not r[7] and w3.eth.get_balance(giver) == before
    assert escrow.functions.free(offer).call() == 6 * 10 ** 17
    # a claim may open again within the claim period, and certifies to the payout
    claim(wanter, outcome=10 ** 17).transact({"from": wanter, "value": stake})
    second = factbond.functions.count().call()
    _advance(w3, 700)
    before_w, before_g = w3.eth.get_balance(wanter), w3.eth.get_balance(giver)
    factbond.functions.certify(second).transact({"from": stranger})
    assert w3.eth.get_balance(wanter) - before_w == 10 ** 17 + floor
    assert w3.eth.get_balance(giver) - before_g == 3 * 10 ** 17


def test_a_split_while_a_claim_is_open_lets_the_resolvers_case_end(chain):
    """B2 on a held reservation: the parties settle at a split while
    factbond's claim is contested; the ruling then arrives, the escrow
    acknowledges it without moving anything, and factbond's stakes pay."""
    w3, escrow, coin, clearing = chain
    factbond, adjudicator, fee, floor = _factbond(w3)
    giver, wanter = w3.eth.accounts[2], w3.eth.accounts[3]
    offer, loop = bytes.fromhex("79" * 32), bytes.fromhex("b2" * 32)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    _reserve(escrow, clearing, offer, loop, wanter, factbond.address, 4 * 10 ** 17, now, now + 10, claim=10_000,
             claim_only=True)
    subj = escrow.functions.key(offer, loop).call()
    factbond.functions.assert_(subj, escrow.address, 4 * 10 ** 17, 990, 0, 0, giver).transact(
        {"from": wanter, "value": fee + floor})
    i = factbond.functions.count().call()
    factbond.functions.dispute(i).transact({"from": giver, "value": factbond.functions.stakeFor(floor, 990).call()})
    escrow.functions.settle(offer, loop, 25 * 10 ** 16).transact({"from": wanter})
    before = w3.eth.get_balance(wanter)
    escrow.functions.settle(offer, loop, 25 * 10 ** 16).transact({"from": giver})
    assert w3.eth.get_balance(wanter) - before == 25 * 10 ** 16
    assert escrow.functions.reservation(offer, loop).call()[6:8] == [True, True]   # settled, the claim still open
    before = w3.eth.get_balance(wanter)
    factbond.functions.rule(i, True).transact({"from": adjudicator})
    assert w3.eth.get_balance(wanter) - before == 2 * floor - floor // 2           # factbond's stakes, nothing more
    assert escrow.functions.reservation(offer, loop).call()[6:8] == [False, True]


def test_cover_is_never_countersigned_and_a_held_reservation_never_quiet_settles(chain):
    """D3 and C1: a `claimOnly` reservation settles by a ruling, a split or
    the quiet path, never by countersignature; `cancel` stays (an insurer's
    cancel in the window pays the insured the whole reservation). Once a
    claim is held, neither the quiet path nor a cancel releases it."""
    w3, escrow, coin, clearing = chain
    giver, wanter, resolver = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[4]
    offer = bytes.fromhex("44" * 32)
    cover, held = bytes.fromhex("c1" * 32), bytes.fromhex("c2" * 32)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    for loop in (cover, held):
        _reserve(escrow, clearing, offer, loop, wanter, resolver, 3 * 10 ** 17, now, now + 10, claim=100,
                 claim_only=loop == cover)
    assert escrow.functions.terms(offer, cover).call()[0]
    assert "never countersigned" in _reverts(w3, escrow.functions.countersign(offer, cover), wanter)
    escrow.functions.hold(offer, held).transact({"from": resolver})
    assert "a claim is open" in _reverts(w3, escrow.functions.hold(offer, held), resolver)
    _advance(w3, 500)
    assert "a claim is open" in _reverts(w3, escrow.functions.settle(offer, held), giver)
    assert "not open" in _reverts(w3, escrow.functions.cancel(offer, held), giver)
    before = w3.eth.get_balance(giver)
    escrow.functions.settle(offer, cover).transact({"from": resolver})             # no claim: quiet, to the insurer
    assert w3.eth.get_balance(giver) - before == 3 * 10 ** 17
    escrow.functions.resolve(offer, held, 10 ** 17).transact({"from": resolver})
    assert escrow.functions.free(offer).call() == 10 ** 18 - 6 * 10 ** 17


def test_assign_hands_the_claim_to_any_key(chain):
    """B4 and D-2: only the wanter assigns, to anyone; from then on the
    payout and the wanter's acts are the assignee's, and splits signed
    before are void; not while a claim is open."""
    w3, escrow, coin, clearing = chain
    giver, wanter, resolver, buyer = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[4], w3.eth.accounts[8]
    offer, loop = bytes.fromhex("55" * 32), bytes.fromhex(LOOP)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    _reserve(escrow, clearing, offer, loop, wanter, resolver, 5 * 10 ** 17, now, now + 10, claim=1000)
    assert "not the wanter" in _reverts(w3, escrow.functions.assign(offer, loop, buyer), giver)
    assert "a key" in _reverts(w3, escrow.functions.assign(offer, loop, "0x" + "00" * 20), wanter)
    assert "no party" in _reverts(w3, escrow.functions.assign(offer, loop, resolver), wanter)
    # C4 at reserve: the resolver is neither the wanter nor the depositor
    now = _now(w3)
    for judge in (wanter, giver):
        assert "no party" in _reverts(w3, escrow.functions.reserve(
            offer, bytes.fromhex("5a" * 32), wanter, judge, 1, _terms(now, now), [], []), clearing)
    escrow.functions.settle(offer, loop, 10 ** 17).transact({"from": giver})       # the giver's offer to the old wanter
    escrow.functions.assign(offer, loop, buyer).transact({"from": wanter})
    assert escrow.functions.reservation(offer, loop).call()[0] == buyer
    assert "not a party" in _reverts(w3, escrow.functions.settle(offer, loop, 10 ** 17), wanter)
    assert "not the wanter" in _reverts(w3, escrow.functions.countersign(offer, loop), wanter)
    escrow.functions.settle(offer, loop, 10 ** 17).transact({"from": buyer})       # void: the giver must sign anew
    assert not escrow.functions.reservation(offer, loop).call()[7]
    # back and forth: a split the old holder signed does not survive its return
    escrow.functions.assign(offer, loop, wanter).transact({"from": buyer})
    escrow.functions.settle(offer, loop, 10 ** 17).transact({"from": wanter})
    escrow.functions.assign(offer, loop, buyer).transact({"from": wanter})
    escrow.functions.assign(offer, loop, wanter).transact({"from": buyer})
    escrow.functions.settle(offer, loop, 10 ** 17).transact({"from": giver})
    assert not escrow.functions.reservation(offer, loop).call()[7]
    escrow.functions.assign(offer, loop, buyer).transact({"from": wanter})
    escrow.functions.hold(offer, loop).transact({"from": resolver})
    assert "a claim is open" in _reverts(w3, escrow.functions.assign(offer, loop, wanter), buyer)
    before_b, before_w = w3.eth.get_balance(buyer), w3.eth.get_balance(wanter)
    escrow.functions.resolve(offer, loop, 5 * 10 ** 17).transact({"from": resolver})
    assert w3.eth.get_balance(buyer) - before_b == 5 * 10 ** 17
    assert w3.eth.get_balance(wanter) == before_w


def test_a_split_needs_both_signatures_and_the_giver_alone_extends(chain):
    """B2: the wanter and the giver each sign the same split, nobody else
    can; a different amount replaces the signer's own. D-4: the giver alone
    lengthens the claim period, and a claim may then open after the
    original end."""
    w3, escrow, coin, clearing = chain
    giver, wanter, resolver, other = w3.eth.accounts[2], w3.eth.accounts[3], w3.eth.accounts[4], w3.eth.accounts[7]
    offer = bytes.fromhex("66" * 32)
    split, tail = bytes.fromhex("d1" * 32), bytes.fromhex("d2" * 32)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    now = _now(w3)
    for loop in (split, tail):
        _reserve(escrow, clearing, offer, loop, wanter, resolver, 4 * 10 ** 17, now, now + 10, claim=100)
    assert "not a party" in _reverts(w3, escrow.functions.settle(offer, split, 1), other)
    assert "beyond the reservation" in _reverts(w3, escrow.functions.settle(offer, split, 5 * 10 ** 17), wanter)
    escrow.functions.settle(offer, split, 3 * 10 ** 17).transact({"from": wanter})
    escrow.functions.settle(offer, split, 2 * 10 ** 17).transact({"from": giver})  # a different split: no settlement
    assert not escrow.functions.reservation(offer, split).call()[7]
    escrow.functions.settle(offer, split, 2 * 10 ** 17).transact({"from": wanter})
    r = escrow.functions.reservation(offer, split).call()
    assert r[7]
    # the tail: only the giver, only longer
    until = escrow.functions.reservation(offer, tail).call()[5]
    assert "not the giver" in _reverts(w3, escrow.functions.extendClaim(offer, tail, 1000), wanter)
    assert "only longer" in _reverts(w3, escrow.functions.extendClaim(offer, tail, 0), giver)
    escrow.functions.extendClaim(offer, tail, 1000).transact({"from": giver})
    assert escrow.functions.reservation(offer, tail).call()[5] == until + 1000
    _advance(w3, 300)
    assert "claim period open" in _reverts(w3, escrow.functions.settle(offer, tail), other)
    escrow.functions.hold(offer, tail).transact({"from": resolver})


REFUSER_SRC = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
interface IEscrow { function deposit(bytes32) external payable; function collect(address) external; }
contract Refuser {
    uint8 public mode;   // 1: revert on receipt, 2: burn the gas
    function setMode(uint8 m) external { mode = m; }
    receive() external payable {
        if (mode == 1) revert("refused");
        if (mode == 2) while (true) {}
    }
    function deposit(address escrow, bytes32 offer) external payable { IEscrow(escrow).deposit{value: msg.value}(offer); }
    function collect(address escrow) external { IEscrow(escrow).collect(address(0)); }
}
"""


def test_a_refused_payout_is_credited_and_never_blocks_the_ruling(chain):
    """A giver whose address refuses payment (or burns the gas) cannot
    block a ruling that pays its wanter: its share is credited to `owed`
    and it collects it itself."""
    import solcx
    w3, escrow, coin, clearing = chain
    art = solcx.compile_source(REFUSER_SRC, output_values=["abi", "bin"], solc_version="0.8.24")["<stdin>:Refuser"]
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art["abi"], bytecode=art["bin"]).constructor().transact())
    refuser = w3.eth.contract(address=receipt["contractAddress"], abi=art["abi"])
    wanter, resolver = w3.eth.accounts[3], w3.eth.accounts[4]
    offer = bytes.fromhex("88" * 32)
    refuser.functions.deposit(escrow.address, offer).transact({"value": 10 ** 18})
    now = _now(w3)
    for mode, loop in ((1, bytes.fromhex("e1" * 32)), (2, bytes.fromhex("e2" * 32))):
        refuser.functions.setMode(mode).transact()
        _reserve(escrow, clearing, offer, loop, wanter, resolver, 4 * 10 ** 17, now, now + 10, claim=1000)
        escrow.functions.hold(offer, loop).transact({"from": resolver})
        before = w3.eth.get_balance(wanter)
        escrow.functions.resolve(offer, loop, 10 ** 17).transact({"from": resolver, "gas": 1_000_000})
        assert w3.eth.get_balance(wanter) - before == 10 ** 17
    assert escrow.functions.owed("0x" + "00" * 20, refuser.address).call() == 6 * 10 ** 17
    assert "nothing owed" in _reverts(w3, escrow.functions.collect("0x" + "00" * 20), wanter)
    refuser.functions.setMode(0).transact()
    refuser.functions.collect(escrow.address).transact()
    assert w3.eth.get_balance(refuser.address) == 6 * 10 ** 17
    assert escrow.functions.owed("0x" + "00" * 20, refuser.address).call() == 0
