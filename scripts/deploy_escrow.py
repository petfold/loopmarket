"""Deploy contracts/LoopEscrow.sol from its compiled artifact.

    pip install 'loopmarket[chain]'
    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=0x... \\
      python scripts/deploy_escrow.py CLEARING NOTICE_BLOCKS

Prints the contract address; the setting is then
`loop set escrow chain:https://rpc.gnosischain.com@0xADDRESS`. `CLEARING`
is the key that reserves a share per fill at clearing (the clearing
contract's arbiter key today; `BeatClearing` itself once its finalization
reserves directly) — the resolver of a contested claim is named per
reservation, not here — and `NOTICE_BLOCKS` how long a giver's
withdrawal is announced before it can happen (Gnosis: ~5 s blocks). The
artifact is `loopmarket/contracts/LoopEscrow.json` (solc 0.8.24 via IR,
optimizer 200 runs, `scripts/build_beat.py`), so this needs no compiler.
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.escrow import abi  # noqa: E402


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) < 3:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: CLEARING NOTICE_BLOCKS")
    clearing, notice = Web3.to_checksum_address(sys.argv[1]), int(sys.argv[2])
    w3 = Web3(Web3.HTTPProvider(rpc))
    account = w3.eth.account.from_key(key)
    art = abi()
    contract = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    tx = contract.constructor(clearing, notice).build_transaction({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address)})
    signed = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    print(receipt["contractAddress"])


if __name__ == "__main__":
    main()
