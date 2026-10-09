"""Fixtures that more than one test module uses. Pytest finds a fixture
here; imported from another test module instead, it looks unused to a
linter, and the test parameter that receives it shadows the import (the
CI lint, 2026-10-09)."""

import os

import pytest

from loopmarket import cli
from test_cli import CATALOGUE, NOW, write_od
from test_escrow import NOTICE

HERE = os.path.dirname(__file__)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A scratch home for both tools, an unpinned `.od` catalogue, a fixed
    clock, no confirmation prompts."""
    monkeypatch.setenv("LOOP_HOME", str(tmp_path / "loop"))
    monkeypatch.setenv("ONTODAG_HOME", str(tmp_path / "odag"))
    od = tmp_path / "cat.od"
    write_od(od, CATALOGUE)
    monkeypatch.setenv("LOOP_CATALOGUE", str(od))
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    monkeypatch.setenv("LOOP_CONFIRM", "off")
    monkeypatch.setenv("LOOP_NOW", str(NOW))
    monkeypatch.setenv("LOOP_MAKER", "amara")
    for var in ("LOOP_WHERE", "LOOP_PEERS", "BEE_SIGNER"):
        monkeypatch.delenv(var, raising=False)
    cli._OVERRIDES.clear()
    return tmp_path


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
