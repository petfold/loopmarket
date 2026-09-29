"""The escrow's live gate (E3, 2026-09-29): E1's acts on a deployed
`LoopEscrow` whose resolver is factbond's `Assertions`.

    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=$(cat ~/.loopmarket/chain_key) \\
      PYTHONPATH=src python3 scripts/gate_escrow.py ESCROW ASSERTIONS

The chain key is the escrow's clearing and the deposit's giver; a throwaway
wanter key is made and funded with 0.02 xDAI, and swept back at the end.
Behind one gate offer id, 0.01 xDAI is deposited and three reservations are
made from it:

1. cover (`claimOnly`, 0.004): the wanter's countersign is refused; the
   giver's own claim is refused at `hold` (T18: only the wanter's claim
   opens); the wanter's claim opens and, retracted, reopens the reservation
   instead of refunding the giver;
2. split (0.003): the wanter and the giver each sign 0.001 to the wanter,
   and the second signature settles it;
3. tail (0.003): the giver lengthens the claim period by an hour.

Refusals are read with `eth_call` (no gas); everything else is a mainnet
transaction. Exits non-zero at the first expectation that fails. The cover
and tail reservations settle by the quiet path after their claim periods
(anyone may call `settle`), returning 0.007 to the giver.
"""
import hashlib
import os
import sys
import time

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.escrow import EscrowClient  # noqa: E402

ASSERTIONS_ABI = [
    {"name": "assert_", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "subject", "type": "bytes32"}, {"name": "consumer", "type": "address"},
                {"name": "outcome", "type": "uint256"}, {"name": "confidence", "type": "uint16"},
                {"name": "window", "type": "uint64"}, {"name": "rulingWindow", "type": "uint64"},
                {"name": "about", "type": "address"}],
     "outputs": [{"name": "id", "type": "uint256"}]},
    {"name": "retract", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "id", "type": "uint256"}], "outputs": []},
    {"name": "count", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "feeWei", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "floorWei", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "rulingSeconds", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint64"}]},
    {"name": "minChallengeSeconds", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint64"}]},
]

MILLI = 10 ** 15


def ok(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        sys.exit(1)


def reverts(fn, sender, value=0):
    try:
        fn.call({"from": sender, "value": value})
    except Exception as exc:  # noqa: BLE001 — the reason is in the message
        return str(exc)
    return ""


def send(w3, account, fn, value=0):
    tx = fn.build_transaction({"from": account.address, "value": value,
                               "nonce": w3.eth.get_transaction_count(account.address)})
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction))
    if receipt["status"] != 1:
        raise RuntimeError(f"transaction failed: {receipt['transactionHash'].hex()}")
    return receipt


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) != 3:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: ESCROW ASSERTIONS")
    escrow_addr, assertions_addr = (Web3.to_checksum_address(a) for a in sys.argv[1:3])
    w3 = Web3(Web3.HTTPProvider(rpc))
    giver = w3.eth.account.from_key(key)
    wanter = w3.eth.account.create()
    stamp = str(int(time.time()))
    offer = hashlib.sha256(f"e3-gate-offer-{stamp}".encode()).hexdigest()
    loops = {n: hashlib.sha256(f"e3-gate-{n}-{stamp}".encode()).hexdigest() for n in ("cover", "split", "tail")}
    clearing = EscrowClient(rpc, escrow_addr, key=key, client=w3)
    as_wanter = EscrowClient(rpc, escrow_addr, key=wanter.key.hex(), client=w3)
    esc = clearing.contract()
    fb = w3.eth.contract(address=assertions_addr, abi=ASSERTIONS_ABI)
    fee, floor = fb.functions.feeWei().call(), fb.functions.floorWei().call()
    ruling, min_window = fb.functions.rulingSeconds().call(), fb.functions.minChallengeSeconds().call()
    print(f"gate {stamp}: escrow {escrow_addr}, resolver {assertions_addr}, wanter {wanter.address}")

    print("funding the wanter and depositing")
    tx = {"from": giver.address, "to": wanter.address, "value": 20 * MILLI, "gas": 21000,
          "gasPrice": w3.eth.gas_price, "nonce": w3.eth.get_transaction_count(giver.address),
          "chainId": w3.eth.chain_id}
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(giver.sign_transaction(tx).raw_transaction))
    clearing.deposit(offer, 10 * MILLI)
    ok(clearing.held(offer) == 10 * MILLI, "0.01 xDAI held behind the gate offer")

    now = w3.eth.get_block("latest")["timestamp"]
    window = (now, now + 60)
    clearing.reserve(offer, loops["cover"], wanter.address, assertions_addr, 4 * MILLI, window=window,
                     claim_seconds=3600, claim_only=True, min_challenge=min_window, min_ruling=ruling)
    clearing.reserve(offer, loops["split"], wanter.address, assertions_addr, 3 * MILLI, window=window,
                     claim_seconds=3600)
    clearing.reserve(offer, loops["tail"], wanter.address, assertions_addr, 3 * MILLI, window=window,
                     claim_seconds=3600)
    ok(clearing.free(offer) == 0, "three reservations take the whole deposit")
    ok(clearing.reservation(offer, loops["cover"])["claim_only"], "the cover reservation is claimOnly")

    print("1. cover")
    why = reverts(esc.functions.countersign(bytes.fromhex(offer), bytes.fromhex(loops["cover"])), wanter.address)
    ok("never countersigned" in why, "the wanter's countersign is refused")
    subject = clearing.subject(offer, loops["cover"])
    claim = fb.functions.assert_(subject, escrow_addr, 4 * MILLI, 990, min_window, 0, giver.address)
    why = reverts(claim, giver.address, fee + floor)
    ok("the claim is the wanter's" in why, "the giver's own claim is refused at hold")
    send(w3, wanter, claim, fee + floor)
    claim_id = fb.functions.count().call()
    r = clearing.reservation(offer, loops["cover"])
    ok(r["held"] and r["claim"] == claim_id, f"the wanter's claim {claim_id} holds the reservation")
    send(w3, wanter, fb.functions.retract(claim_id))
    r = clearing.reservation(offer, loops["cover"])
    ok(not r["held"] and not r["settled"] and clearing.free(offer) == 0,
       "the retraction reopens the reservation; nothing went to the giver")

    print("2. split")
    before = w3.eth.get_balance(wanter.address)
    receipt = as_wanter.settle(offer, loops["split"], to_wanter=MILLI)
    spent = receipt["gasUsed"] * receipt["effectiveGasPrice"]
    ok(not clearing.reservation(offer, loops["split"])["settled"], "one signature does not settle")
    clearing.settle(offer, loops["split"], to_wanter=MILLI)
    ok(clearing.reservation(offer, loops["split"])["settled"], "the giver's matching signature settles it")
    ok(w3.eth.get_balance(wanter.address) - before + spent == MILLI, "the wanter received 0.001 xDAI")

    print("3. tail")
    until = clearing.reservation(offer, loops["tail"])["claim_until"]
    why = reverts(esc.functions.extendClaim(bytes.fromhex(offer), bytes.fromhex(loops["tail"]), 3600),
                  wanter.address)
    ok("not the giver" in why, "the wanter cannot lengthen the claim period")
    clearing.extend_claim(offer, loops["tail"], 3600)
    ok(clearing.reservation(offer, loops["tail"])["claim_until"] == until + 3600, "the giver lengthened it by 1h")

    print("sweeping the wanter's balance back")
    left = w3.eth.get_balance(wanter.address)
    price = w3.eth.gas_price
    if left > 21000 * price:
        tx = {"from": wanter.address, "to": giver.address, "value": left - 21000 * price, "gas": 21000,
              "gasPrice": price, "nonce": w3.eth.get_transaction_count(wanter.address), "chainId": w3.eth.chain_id}
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(wanter.sign_transaction(tx).raw_transaction))
    print(f"GATE PASSED. offer {offer}; cover {loops['cover']}, tail {loops['tail']} settle quietly after "
          f"their claim periods")


if __name__ == "__main__":
    main()
