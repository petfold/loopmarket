"""Deploy contracts/BeatClearing.sol from its compiled artifact.

    pip install 'loopmarket[chain]'
    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=0x... \\
      python scripts/deploy_beat.py BOND_XDAI WINDOW_BLOCKS [ARBITER]

Prints the contract address; the setting is then
`loop set beat chain:https://rpc.gnosischain.com@0xADDRESS`. The artifact
is `loopmarket/contracts/BeatClearing.json` (inside the package) (solc 0.8.24 via IR, optimizer 200
runs), so this needs no compiler. `BOND_XDAI` is what a submitter locks per
beat and a successful challenger wins; `WINDOW_BLOCKS` the challenge
window (Gnosis: ~5 s blocks, 720 ≈ one hour); `ARBITER` the address that
may cancel a beat for what the contract cannot compute (default: the
deployer — replace with factbond's adjudication when it exists).
"""

import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.beat import abi  # noqa: E402


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) < 3:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: BOND_XDAI WINDOW_BLOCKS [ARBITER]")
    bond = Web3.to_wei(sys.argv[1], "ether")
    window = int(sys.argv[2])
    w3 = Web3(Web3.HTTPProvider(rpc))
    account = w3.eth.account.from_key(key)
    arbiter = sys.argv[3] if len(sys.argv) > 3 else account.address
    art = abi()
    contract = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    tx = contract.constructor(bond, window, arbiter).build_transaction({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address)})
    signed = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    print(receipt["contractAddress"])


if __name__ == "__main__":
    main()
