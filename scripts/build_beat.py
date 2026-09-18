"""Compile contracts/BeatClearing.sol into the artifact the package ships,
`src/loopmarket/contracts/BeatClearing.json` ({"abi", "bytecode"}), with
the parameters the tests compile under (solc 0.8.24, via IR, optimizer 200
runs) so the deployed bytecode is reproducible from the sources.

    pip install py-solc-x
    python scripts/build_beat.py
"""
import json
import os

import solcx

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACTS = os.path.join(HERE, "..", "contracts")
OUT = os.path.join(HERE, "..", "src", "loopmarket", "contracts", "BeatClearing.json")


def main() -> None:
    solcx.install_solc("0.8.24")
    compiled = solcx.compile_files([os.path.join(CONTRACTS, "BeatClearing.sol")],
                                   output_values=["abi", "bin"], solc_version="0.8.24",
                                   optimize=True, optimize_runs=200, via_ir=True,
                                   allow_paths=CONTRACTS)
    artifact = next(v for k, v in compiled.items() if k.endswith(":BeatClearing"))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"abi": artifact["abi"], "bytecode": "0x" + artifact["bin"], "solc": "0.8.24",
                   "via_ir": True, "optimize_runs": 200}, fh, indent=1)
        fh.write("\n")
    print(f"{OUT}: {len(artifact['bin']) // 2} bytes of bytecode")


if __name__ == "__main__":
    main()
