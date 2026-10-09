"""Cover stage 2's live gate (D-2, 2026-09-29, Peter's taxi case): a cover
reservation covering a driver's reservation on a deployed `LoopEscrow`,
factbond's `Assertions` as resolver.

    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=$(cat ~/.loopmarket/chain_key) \\
      PYTHONPATH=src python3 scripts/gate_cover.py ESCROW ASSERTIONS

The chain key is the escrow's clearing and the insurer; throwaway keys are
made and funded for the driver, two travellers and a bystander (who calls
`certify`), and swept back at the end. Two rides of 0.002 behind the
driver's deposit, two policies of 0.005 behind the insurer's, each policy
covering its traveller's ride. The driver forgets both; each traveller's
loss is 0.003.

Round 1 (in parallel): the first traveller's claim on the cover is refused
until she assigns her claim on the driver to the insurer; she assigns and
claims 0.003; the second traveller claims the driver's 0.002 herself.
Round 2: the insurer, as the assignee, claims the driver's 0.002; the
second traveller claims the cover, which pays 0.001 (0.003 less the 0.002
the driver's reservation already paid her). Each round waits factbond's
challenge window. Exits non-zero at the first expectation that fails.
"""
import hashlib
import os
import sys
import time

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.escrow import EscrowClient, reservation_key  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from gate_deductible import ASSERTIONS_ABI  # noqa: E402
from gate_escrow import MILLI, ok, reverts, send  # noqa: E402


def fund(w3, source, to, value):
    tx = {"from": source.address, "to": to, "value": value, "gas": 21000, "gasPrice": w3.eth.gas_price,
          "nonce": w3.eth.get_transaction_count(source.address), "chainId": w3.eth.chain_id}
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(source.sign_transaction(tx).raw_transaction))


def sweep(w3, account, to):
    left, price = w3.eth.get_balance(account.address), w3.eth.gas_price
    if left > 21000 * price:
        tx = {"from": account.address, "to": to, "value": left - 21000 * price, "gas": 21000, "gasPrice": price,
              "nonce": w3.eth.get_transaction_count(account.address), "chainId": w3.eth.chain_id}
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction))


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) != 3:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: ESCROW ASSERTIONS")
    escrow_addr, assertions_addr = (Web3.to_checksum_address(a) for a in sys.argv[1:3])
    w3 = Web3(Web3.HTTPProvider(rpc))
    insurer = w3.eth.account.from_key(key)
    driver, first, second, bystander = (w3.eth.account.create() for _ in range(4))
    stamp = str(int(time.time()))
    h = lambda s: hashlib.sha256(f"cover-gate-{s}-{stamp}".encode()).hexdigest()
    ride, cover, loop1, loop2 = h("ride"), h("cover"), h("loop1"), h("loop2")
    fb = w3.eth.contract(address=assertions_addr, abi=ASSERTIONS_ABI)
    fee, floor = fb.functions.feeWei().call(), fb.functions.floorWei().call()
    ruling, window = fb.functions.rulingSeconds().call(), fb.functions.minChallengeSeconds().call()
    stake = fee + floor
    print(f"gate {stamp}: escrow {escrow_addr}; driver {driver.address}, travellers {first.address} "
          f"{second.address}")
    for account, value in ((driver, 10 * MILLI), (first, 20 * MILLI), (second, 35 * MILLI), (bystander, 2 * MILLI)):
        fund(w3, insurer, account.address, value)
    clearing = EscrowClient(rpc, escrow_addr, key=key, client=w3)
    as_ = lambda account: EscrowClient(rpc, escrow_addr, key=account.key.hex(), client=w3)
    as_(driver).deposit(ride, 4 * MILLI)
    clearing.deposit(cover, 10 * MILLI)
    now = w3.eth.get_block("latest")["timestamp"]
    terms = dict(window=(now, now + 60), claim_seconds=3 * 3600, min_challenge=window, min_ruling=ruling)
    for loop, traveller in ((loop1, first), (loop2, second)):
        clearing.reserve(ride, loop, traveller.address, assertions_addr, 2 * MILLI, **terms)
        clearing.reserve(cover, loop, traveller.address, assertions_addr, 5 * MILLI, claim_only=True,
                         covers=reservation_key(ride, loop), **terms)
    ok(clearing.cover_of(cover, loop1)["covers"] == reservation_key(ride, loop1), "each policy covers its ride")

    def assertion(offer, loop, outcome, about):
        return fb.functions.assert_(clearing.subject(offer, loop), escrow_addr, outcome, 990, window, 0, about)

    print("round 1")
    ok("assign the claim on the covered reservation to the insurer first"
       in reverts(assertion(cover, loop1, 3 * MILLI, insurer.address), first.address, stake),
       "the first traveller's cover claim is refused before she assigns")
    as_(first).assign(ride, loop1, insurer.address)
    send(w3, first, assertion(cover, loop1, 3 * MILLI, insurer.address), stake)
    c1 = fb.functions.count().call()
    send(w3, second, assertion(ride, loop2, 2 * MILLI, driver.address), stake)
    r2 = fb.functions.count().call()
    print(f"  waiting {window + 30}s")
    time.sleep(window + 30)
    before = {a: w3.eth.get_balance(a) for a in (first.address, second.address, insurer.address)}
    send(w3, bystander, fb.functions.certify(c1))
    send(w3, bystander, fb.functions.certify(r2))
    delta = {a: w3.eth.get_balance(a) - b for a, b in before.items()}
    ok(delta[first.address] == 3 * MILLI + floor, "the cover paid the first traveller 0.003 (and her bond back)")
    ok(delta[insurer.address] == 2 * MILLI, "the rest of her policy, 0.002, back to the insurer")
    ok(delta[second.address] == 2 * MILLI + floor, "the driver's 0.002 paid the second traveller")

    print("round 2")
    ok("the claim is the wanter's" in reverts(assertion(ride, loop1, 2 * MILLI, driver.address), first.address, stake),
       "the first traveller's claim on the driver is the insurer's now")
    send(w3, insurer, assertion(ride, loop1, 2 * MILLI, driver.address), stake)
    r1 = fb.functions.count().call()
    send(w3, second, assertion(cover, loop2, 3 * MILLI, insurer.address), stake)
    c2 = fb.functions.count().call()
    print(f"  waiting {window + 30}s")
    time.sleep(window + 30)
    before = {a: w3.eth.get_balance(a) for a in (second.address, insurer.address)}
    send(w3, bystander, fb.functions.certify(r1))
    send(w3, bystander, fb.functions.certify(c2))
    delta = {a: w3.eth.get_balance(a) - b for a, b in before.items()}
    ok(delta[second.address] == MILLI + floor, "the cover paid the second traveller 0.001: 0.003 less the 0.002 netted")
    ok(delta[insurer.address] == 2 * MILLI + floor + 4 * MILLI,
       "the insurer recovered the driver's 0.002 as the assignee (its bond back) and 0.004 of the second policy")
    ok(clearing.held(ride) == 0 and clearing.reservation(ride, loop1)["settled"], "the driver's deposit paid out")

    print("sweeping the throwaway keys back")
    for account in (driver, first, second, bystander):
        sweep(w3, account, insurer.address)
    print(f"GATE PASSED. ride {ride}, cover {cover}")


if __name__ == "__main__":
    main()
