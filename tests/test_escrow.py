"""The crypto escrow (P3 §5a, 2026-09-19): a giver's deposit behind an
offer id, a share reserved per fill, paid to the wanter on the arbiter's
ruling, returned on the wanter's countersignature, withdrawn by the giver
only after notice and only what no fill holds. Native coin and ERC-20.
Skips without the `evm` extra."""

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
    arbiter = accounts[1]
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=art["abi"], bytecode=art["bin"]).constructor(arbiter, NOTICE).transact())
    escrow = w3.eth.contract(address=receipt["contractAddress"], abi=art["abi"])
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=coin_art["abi"], bytecode=coin_art["bin"]).constructor().transact())
    coin = w3.eth.contract(address=receipt["contractAddress"], abi=coin_art["abi"])
    return w3, escrow, coin, arbiter


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


def test_deposit_reserve_release_refund_in_the_native_coin(chain):
    w3, escrow, coin, arbiter = chain
    giver, wanter = w3.eth.accounts[2], w3.eth.accounts[3]
    offer, loop, loop2 = bytes.fromhex(OFFER), bytes.fromhex(LOOP), bytes.fromhex(LOOP2)
    escrow.functions.deposit(offer).transact({"from": giver, "value": 10 ** 18})
    assert escrow.functions.held(offer).call() == 10 ** 18
    assert escrow.functions.free(offer).call() == 10 ** 18
    # only the arbiter reserves, only within what is free
    assert "not the arbiter" in _reverts(w3, escrow.functions.reserve(offer, loop, 1), giver)
    assert "beyond what is free" in _reverts(w3, escrow.functions.reserve(offer, loop, 2 * 10 ** 18), arbiter)
    escrow.functions.reserve(offer, loop, 4 * 10 ** 17).transact({"from": arbiter})
    escrow.functions.reserve(offer, loop2, 3 * 10 ** 17).transact({"from": arbiter})
    assert escrow.functions.free(offer).call() == 3 * 10 ** 17
    assert "already reserved" in _reverts(w3, escrow.functions.reserve(offer, loop, 1), arbiter)
    # a ruling of failure pays the wanter the ruled amount; the rest of the reservation returns
    before_w, before_g = w3.eth.get_balance(wanter), w3.eth.get_balance(giver)
    escrow.functions.release(offer, loop, wanter, 25 * 10 ** 16, "no-show").transact({"from": arbiter})
    assert w3.eth.get_balance(wanter) - before_w == 25 * 10 ** 16
    assert w3.eth.get_balance(giver) - before_g == 15 * 10 ** 16
    assert escrow.functions.held(offer).call() == 6 * 10 ** 17
    assert "not within the reservation" in _reverts(w3, escrow.functions.release(offer, loop, wanter, 1, ""), arbiter)
    # the wanter's countersignature returns the other reservation to the giver
    assert "not the arbiter or the wanter" in _reverts(w3, escrow.functions.refund(offer, loop2, wanter, ""), giver)
    before_g = w3.eth.get_balance(giver)
    escrow.functions.refund(offer, loop2, wanter, "delivered").transact({"from": wanter})
    assert w3.eth.get_balance(giver) - before_g == 3 * 10 ** 17
    assert escrow.functions.held(offer).call() == escrow.functions.free(offer).call() == 3 * 10 ** 17
    # the giver leaves only after notice, and only with what is free
    assert "notice not served" in _reverts(w3, escrow.functions.withdraw(offer, 1), giver)
    escrow.functions.notice(offer).transact({"from": giver})
    assert "notice not served" in _reverts(w3, escrow.functions.withdraw(offer, 1), giver)
    for _ in range(NOTICE):
        w3.provider.ethereum_tester.mine_block()
    assert "beyond what is free" in _reverts(w3, escrow.functions.withdraw(offer, 4 * 10 ** 17), giver)
    before_g = w3.eth.get_balance(giver)
    receipt = w3.eth.wait_for_transaction_receipt(
        escrow.functions.withdraw(offer, 3 * 10 ** 17).transact({"from": giver}))
    gas = receipt["gasUsed"] * w3.eth.get_transaction(receipt["transactionHash"])["gasPrice"]
    assert w3.eth.get_balance(giver) - before_g == 3 * 10 ** 17 - gas   # the giver pays its own gas
    assert escrow.functions.held(offer).call() == 0
    # another key cannot deposit behind the same offer
    assert "another deposit" in _reverts(w3, escrow.functions.deposit(offer), wanter, value=1)


def test_erc20_deposit_and_release(chain):
    w3, escrow, coin, arbiter = chain
    giver, wanter = w3.eth.accounts[0], w3.eth.accounts[3]
    offer, loop = bytes.fromhex("11" * 32), bytes.fromhex(LOOP)
    coin.functions.approve(escrow.address, 500).transact({"from": giver})
    escrow.functions.depositToken(offer, coin.address, 500).transact({"from": giver})
    assert escrow.functions.held(offer).call() == 500
    assert "a token" in _reverts(w3, escrow.functions.depositToken(offer, "0x" + "00" * 20, 1), giver)
    escrow.functions.reserve(offer, loop, 200).transact({"from": arbiter})
    escrow.functions.release(offer, loop, wanter, 200, "cancelled at the door").transact({"from": arbiter})
    assert coin.functions.balanceOf(wanter).call() == 200
    assert escrow.functions.held(offer).call() == 300


def test_offers_signed_by_state(chain):
    w3, escrow, coin, arbiter = chain
    offer = bytes.fromhex("22" * 32)
    assert not escrow.functions.offers(offer).call()
    assert "not the owner" in _reverts(w3, escrow.functions.registerOffer(offer), arbiter)
    escrow.functions.registerOffer(offer).transact({"from": w3.eth.accounts[0]})
    assert escrow.functions.offers(offer).call()


def test_client_reads_and_the_shipped_artifact_match_the_source(chain):
    from loopmarket.escrow import abi
    w3, escrow, coin, arbiter = chain
    client = EscrowClient("", escrow.address, client=w3)
    assert client.held("11" * 32) == 300
    assert client.reserved("11" * 32, LOOP) == 200
    assert client.deposit_of("11" * 32)["token"] == coin.address
    names = {e["name"] for e in abi()["abi"] if e["type"] == "function"}
    assert {"deposit", "depositToken", "reserve", "release", "refund", "notice", "withdraw", "held", "free"} <= names
    with pytest.raises(ValueError):
        client.deposit(OFFER, 1)
