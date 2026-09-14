"""Compile and deploy contracts/LoopBookRegistry.sol.

    pip install 'loopmarket[chain]' py-solc-x
    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=0x... python scripts/deploy_registry.py

Prints the contract address; the setting is then
`loop set registry chain:https://rpc.gnosischain.com@0xADDRESS`. The
ABI readers use is `loopmarket.announce.ABI`, kept beside the source so
no reader needs a compiler. Gnosis: ~5 s blocks, gas ~0.2 gwei in xDAI —
deployment is well under a cent; one announcement is about the same.
"""

import os
import sys

from solcx import compile_source, install_solc
from web3 import Web3


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY")
    source = open(os.path.join(os.path.dirname(__file__), "..", "contracts",
                               "LoopBookRegistry.sol"), encoding="utf-8").read()
    install_solc("0.8.24")
    compiled = compile_source(source, output_values=["abi", "bin"], solc_version="0.8.24")
    _, artifact = next(iter(compiled.items()))
    w3 = Web3(Web3.HTTPProvider(rpc))
    account = w3.eth.account.from_key(key)
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
    tx = contract.constructor().build_transaction({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address)})
    signed = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction))
    print(receipt["contractAddress"])


if __name__ == "__main__":
    main()
