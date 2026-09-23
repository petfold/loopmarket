"""Deploy contracts/BeatClearing.sol (and the LegVerifier it calls) from the
compiled artifacts.

    pip install 'loopmarket[chain]'
    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=0x... \\
      python scripts/deploy_beat.py BOND_XDAI WINDOW_BLOCKS [ARBITER]
          [--predecessors 0xA,0xB,...] [--verifier 0xV] [--retire 0xOLD]

Prints the clearing and verifier addresses; the setting is then
`loop set beat chain:https://rpc.gnosischain.com@0xCLEARING`. The artifacts
are `loopmarket/contracts/{BeatClearing,LegVerifier}.json` (inside the
package; solc 0.8.24 via IR, optimizer 200 runs), so this needs no compiler.
`BOND_XDAI` is what a submitter locks per beat and a successful challenger
wins; `WINDOW_BLOCKS` the challenge window (Gnosis: ~5 s blocks, 720 ≈ one
hour); `ARBITER` the address that may cancel a beat for what the contract
cannot compute and retire the contract to a successor (default: the
deployer — replace with factbond's adjudication when it exists).

`--predecessors`: every earlier clearing contract that has recorded fills —
their fills are the new contract's floor, so an offer they cleared cannot
clear again (2026-09-23). `--verifier` reuses a deployed LegVerifier.
`--retire`: after deploying, retire that (2026-09-23 or later) contract to the
new one, from the same key (its arbiter): it takes no new beat after that.
"""

import argparse
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.beat import BeatClient, deploy  # noqa: E402


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    ap = argparse.ArgumentParser()
    ap.add_argument("bond")
    ap.add_argument("window", type=int)
    ap.add_argument("arbiter", nargs="?")
    ap.add_argument("--predecessors", default="")
    ap.add_argument("--verifier")
    ap.add_argument("--retire")
    args = ap.parse_args()
    if not rpc or not key:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY")
    w3 = Web3(Web3.HTTPProvider(rpc))
    predecessors = [p for p in args.predecessors.split(",") if p]
    clearing, verifier = deploy(w3, Web3.to_wei(args.bond, "ether"), args.window, args.arbiter,
                                predecessors=predecessors, verifier=args.verifier, key=key)
    print(f"clearing {clearing}")
    print(f"verifier {verifier}")
    if args.retire:
        BeatClient(rpc, args.retire, key=key).retire(clearing)
        print(f"retired {args.retire} -> {clearing}")


if __name__ == "__main__":
    main()
