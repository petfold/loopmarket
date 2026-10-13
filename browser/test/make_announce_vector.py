"""An announcement transaction signed by eth_account (web3's signer, as
`loop announce` sends it), for test_announce.mjs: announce.js must encode
the call and sign the transaction byte for byte the same, so the page's
announcement is the one loop would send. The key is a published test key,
not anyone's.

    python3 browser/test/make_announce_vector.py > browser/test/announce_vector.json
"""

import json
import sys

from eth_account import Account
from web3 import Web3

from loopmarket.announce import ABI

KEY = "0x" + "11" * 32                 # a test key (it owns nothing)
CONTRACT = "0xD4379E494a488411D964BebDb210C0bf628d97af"
BOOK = "swarm:loop-19e7e376"
TX = {"chainId": 100, "nonce": 7, "gas": 90_000, "maxFeePerGas": 3_000_000_014,
      "maxPriorityFeePerGas": 1_000_000_000, "to": CONTRACT, "value": 0}

data = Web3().eth.contract(address=CONTRACT, abi=ABI).encode_abi("announce", [BOOK, 0])
signed = Account.from_key(KEY).sign_transaction({**TX, "data": data, "type": 2})
json.dump({"key": KEY, "book": BOOK, "role": 0, "tx": TX, "data": data,
           "raw": "0x" + signed.raw_transaction.hex().removeprefix("0x"),
           "hash": "0x" + signed.hash.hex().removeprefix("0x")}, sys.stdout, indent=1)
print()
