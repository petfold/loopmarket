"""Deploy contracts/SealedBeat.sol from its compiled artifact.

    pip install 'loopmarket[chain]'
    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=0x... \\
      python scripts/deploy_sealed.py PERIOD_BLOCKS COMMIT_BLOCKS BEAT_CLEARING

Prints the contract address; the setting is then
`loop set auction chain:https://rpc.gnosischain.com@0xADDRESS`. `PERIOD_BLOCKS`
is one beat (Gnosis: ~5 s blocks), `COMMIT_BLOCKS` its commit phase from
the start (the rest is the reveal phase), `BEAT_CLEARING` the clearing
contract the outcomes go to. The artifact is
`loopmarket/contracts/SealedBeat.json` (solc 0.8.24 via IR, optimizer 200
runs, `scripts/build_beat.py`), so this needs no compiler.
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.auction import abi  # noqa: E402


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) < 4:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: PERIOD_BLOCKS COMMIT_BLOCKS BEAT_CLEARING")
    period, commit_blocks, clearing = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    w3 = Web3(Web3.HTTPProvider(rpc))
    account = w3.eth.account.from_key(key)
    art = abi()
    contract = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    tx = contract.constructor(period, commit_blocks, Web3.to_checksum_address(clearing)).build_transaction({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address)})
    signed = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    print(receipt["contractAddress"])


if __name__ == "__main__":
    main()
