"""The deductible's live gate (C5, 2026-09-29): a deposit's deductible on a
deployed `LoopEscrow` whose resolver is factbond's `Assertions`, and a v7
record through the deployed clearing contracts.

    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=$(cat ~/.loopmarket/chain_key) \\
      PYTHONPATH=src python3 scripts/gate_deductible.py ESCROW ASSERTIONS CLEARING

The chain key is the escrow's clearing, the deposit's giver and the beat's
submitter; a throwaway claimant key is funded with 0.03 xDAI and swept back.

1. A deposit of 0.01 xDAI behind a gate offer; 0.006 reserved as cover
   (`claimOnly`) with a deductible of 0.002, factbond as resolver, windows
   at factbond's least.
2. A claim of 0.002 — within the deductible — is refused at `hold`
   (eth_call); the claimant's claim of 0.005 holds the reservation.
3. After factbond's challenge window, `certify`: the escrow pays the
   claimant 0.003 (0.005 less the deductible) and the giver 0.003.
4. A v7 give (a bonded, deductible deposit on this escrow) clears in a loop
   through `ChainClearing` on CLEARING — the contract's own dry run
   verifying the v7 leg before the bond — and the posted beat verifies
   from the challenger's side.

Exits non-zero at the first expectation that fails.
"""
import hashlib
import os
import sys
import time

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket.escrow import EscrowClient  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from gate_escrow import ASSERTIONS_ABI, MILLI, ok, reverts, send  # noqa: E402

ASSERTIONS_ABI = ASSERTIONS_ABI + [
    {"name": "certify", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "id", "type": "uint256"}], "outputs": []},
]


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) != 4:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: ESCROW ASSERTIONS CLEARING")
    escrow_addr, assertions_addr, clearing_addr = (Web3.to_checksum_address(a) for a in sys.argv[1:4])
    w3 = Web3(Web3.HTTPProvider(rpc))
    giver = w3.eth.account.from_key(key)
    claimant = w3.eth.account.create()
    stamp = str(int(time.time()))
    offer = hashlib.sha256(f"deductible-gate-offer-{stamp}".encode()).hexdigest()
    loop = hashlib.sha256(f"deductible-gate-loop-{stamp}".encode()).hexdigest()
    escrow = EscrowClient(rpc, escrow_addr, key=key, client=w3)
    esc = escrow.contract()
    fb = w3.eth.contract(address=assertions_addr, abi=ASSERTIONS_ABI)
    fee, floor = fb.functions.feeWei().call(), fb.functions.floorWei().call()
    ruling, min_window = fb.functions.rulingSeconds().call(), fb.functions.minChallengeSeconds().call()
    print(f"gate {stamp}: escrow {escrow_addr}, resolver {assertions_addr}, claimant {claimant.address}")

    print("1. deposit and reserve with a deductible")
    tx = {"from": giver.address, "to": claimant.address, "value": 30 * MILLI, "gas": 21000,
          "gasPrice": w3.eth.gas_price, "nonce": w3.eth.get_transaction_count(giver.address),
          "chainId": w3.eth.chain_id}
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(giver.sign_transaction(tx).raw_transaction))
    escrow.deposit(offer, 10 * MILLI)
    now = w3.eth.get_block("latest")["timestamp"]
    escrow.reserve(offer, loop, claimant.address, assertions_addr, 6 * MILLI, window=(now, now + 60),
                   claim_seconds=3 * 3600, claim_only=True, min_challenge=min_window, min_ruling=ruling,
                   deductible=2 * MILLI)
    r = escrow.reservation(offer, loop)
    ok(r["deductible"] == 2 * MILLI and r["claim_only"] and r["amount"] == 6 * MILLI,
       "0.006 reserved as cover with a deductible of 0.002")

    print("2. claims")
    subject = escrow.subject(offer, loop)
    small = fb.functions.assert_(subject, escrow_addr, 2 * MILLI, 990, min_window, 0, giver.address)
    ok("within the deductible" in reverts(small, claimant.address, fee + floor),
       "a claim of 0.002, within the deductible, is refused at hold")
    send(w3, claimant, fb.functions.assert_(subject, escrow_addr, 5 * MILLI, 990, min_window, 0, giver.address),
         fee + floor)
    claim = fb.functions.count().call()
    ok(escrow.reservation(offer, loop)["held"], f"the claim of 0.005 ({claim}) holds the reservation")

    print(f"3. waiting {min_window + 30}s for factbond's challenge window, then certify")
    time.sleep(min_window + 30)
    c_before, g_before = w3.eth.get_balance(claimant.address), w3.eth.get_balance(giver.address)
    receipt = send(w3, giver, fb.functions.certify(claim))
    spent = receipt["gasUsed"] * receipt["effectiveGasPrice"]
    ok(escrow.reservation(offer, loop)["settled"], "certified: the reservation settled")
    ok(w3.eth.get_balance(claimant.address) - c_before == 3 * MILLI + floor,
       "the claimant received 0.003 (0.005 less the deductible) and her bond back")
    ok(w3.eth.get_balance(giver.address) - g_before + spent == 3 * MILLI,
       "the giver received the 0.003 left, the deductible in it")

    print("4. a v7 record through the clearing contracts")
    from ontodag import OntoDAG
    from recordstore import MemoryBytesStore, RecordStore

    from loopmarket import Bond, OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
    from loopmarket.beat import BeatClient, challenge_beat
    from loopmarket.clearing import ChainClearing
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"apple": [], "lesson": [], "xdai": []})
    cat.commit()
    t = int(time.time())
    V = dict(valid=TimeWindow(t - 600, t + 86_400), **cat.pins)
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    farm = give("farm", Thing(("apple",), 100, "kg", step=5), 200, **V, nonce=t,
                bond=Bond(Thing(("xdai",), "1/100", "xDAI"), 10, escrow_addr, deductible="1/500"))
    ok(farm.v == 7, "the bonded give with a deductible is a v7 record")
    book.publish_many([farm, want("b1", Thing(("apple",), 40, "kg"), 90, **V, nonce=t + 1),
                       give("b1", Thing(("lesson",)), 80, **V, nonce=t + 2),
                       want("farm", Thing(("lesson",)), 85, **V, nonce=t + 3)])
    book.commit()
    beats = BeatClient(rpc, clearing_addr, key=key, client=w3)
    (r,) = SolverAgent(book, cat, clearing=ChainClearing(book, cat, beat_client=beats, clock=lambda: t),
                       solver_id="gate", min_surplus=0.0).step(now=t)
    ok(r.accepted and r.reason.startswith("beat "), f"posted after the contract's dry run: {r.reason}")
    beat = int(r.reason.split()[1])
    result = challenge_beat(beats, beat, [book], cat, send=False)
    ok(result.verifies, f"beat {beat} verifies: " + str([(v.local, v.chain) for v in result.legs]))

    print("sweeping the claimant's balance back")
    left = w3.eth.get_balance(claimant.address)
    price = w3.eth.gas_price
    if left > 21000 * price:
        tx = {"from": claimant.address, "to": giver.address, "value": left - 21000 * price, "gas": 21000,
              "gasPrice": price, "nonce": w3.eth.get_transaction_count(claimant.address), "chainId": w3.eth.chain_id}
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(claimant.sign_transaction(tx).raw_transaction))
    print(f"GATE PASSED. offer {offer}, loop {loop}; beat {beat} on {clearing_addr} (finalize after its window)")


if __name__ == "__main__":
    main()
