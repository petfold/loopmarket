"""The default arbitrator's live gate (2026-10-01, Peter: one named
arbitrator both sides accept, final): a case run through `loop` against a
deployed `LoopEscrow`, the arbitrator a plain key.

    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=$(cat ~/.loopmarket/chain_key) \\
      PYTHONPATH=src python3 scripts/gate_arbitrator.py ESCROW

The chain key is the escrow's clearing and the deposit's giver; throwaway
keys are made for the wanter and the arbitrator (funded with a little gas
for the arbitrator's two acts), and swept back at the end. A scratch book
(a temporary `rs:` home) is the channel. Behind one gate offer id 0.002 xDAI
is deposited and reserved for the wanter, the arbitrator as its resolver:

1. the three write contact cards — the arbitrator has no offer, so its card
   is how the claim reaches it;
2. the wanter claims 0.0015 (`loop claim`), sealed to the arbitrator and the
   giver; the giver's `watch` sees it and it answers (`loop answer`);
3. the arbitrator's `watch` sees both; it holds (`loop hold`) and rules 0.001
   (`loop rule --reason`): the escrow pays the wanter 0.001 and returns 0.001;
4. the wanter's `watch` opens the reasons, and `loop arbitrators` reads the
   ruling from the escrow's log.

Each step is `loop` itself (`cli.dispatch`). Exits non-zero at the first
expectation that fails.
"""
import hashlib
import io
import os
import sys
import tempfile
import time

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from loopmarket import cli  # noqa: E402
from loopmarket.escrow import EscrowClient  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from gate_cover import fund, sweep  # noqa: E402
from gate_escrow import MILLI, ok  # noqa: E402


def main() -> None:
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) != 2:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: ESCROW")
    escrow_addr = Web3.to_checksum_address(sys.argv[1])
    w3 = Web3(Web3.HTTPProvider(rpc))
    giver = w3.eth.account.from_key(key)
    wanter, judge = w3.eth.account.create(), w3.eth.account.create()
    stamp = str(int(time.time()))
    h = lambda s: hashlib.sha256(f"arbitrator-gate-{s}-{stamp}".encode()).hexdigest()
    offer, loop = h("offer"), h("loop")
    print(f"gate {stamp}: escrow {escrow_addr}; wanter {wanter.address}, arbitrator {judge.address}")
    fund(w3, giver, judge.address, 2 * MILLI)
    clearing = EscrowClient(rpc, escrow_addr, key=key, client=w3)
    clearing.deposit(offer, 2 * MILLI)
    now = w3.eth.get_block("latest")["timestamp"]
    clearing.reserve(offer, loop, wanter.address, judge.address, 2 * MILLI,
                     window=(now + 86_400, now + 90_000), claim_seconds=3600)
    home = tempfile.mkdtemp()
    os.environ.update({"LOOP_HOME": home, "LOOP_BOOK": f"rs:{home}/book", "LOOP_CONFIRM": "off",
                       "LOOP_ESCROW": f"chain:{rpc}@{escrow_addr}"})
    os.environ.pop("LOOP_MAKER", None)

    def loop_(who, *argv):
        os.environ["BEE_SIGNER"] = who.key.hex()
        out, err = io.StringIO(), io.StringIO()
        code = cli.dispatch(list(argv), cli.Session(), out, err)
        text = out.getvalue() + err.getvalue()
        print("  $ loop " + " ".join(a if len(a) < 20 else a[:12] + "…" for a in argv) + "\n    "
              + text.strip().replace("\n", "\n    "))
        return code, text

    ref = [offer, "--loop", loop]
    print("1. contact cards")
    for who in (giver, wanter, judge):
        ok(loop_(who, "contact-card")[0] == 0, f"{who.address[:10]}… wrote its contact card")
    print("2. claim and answer")
    code, text = loop_(wanter, "claim", offer, "0.0015xDAI", "--loop", loop, "--text", "the gate's claim")
    ok(code == 0 and judge.address in text, "the wanter claimed 0.0015, sealed to the arbitrator and the giver")
    code, text = loop_(giver, "watch", "--once")
    ok("claims 0.0015" in text, "the giver's watch opened the claim")
    ok(loop_(giver, "answer", *ref, "--text", "the gate's answer")[0] == 0, "the giver answered")
    print("3. hold and rule")
    code, text = loop_(judge, "watch", "--once")
    ok("claims 0.0015" in text and "answers the claim" in text, "the arbitrator's watch opened both")
    ok(loop_(judge, "hold", *ref)[0] == 0 and clearing.reservation(offer, loop)["held"], "held: the timeout stops")
    before = {a: w3.eth.get_balance(a) for a in (wanter.address, giver.address)}
    code, text = loop_(judge, "rule", offer, "0.001xDAI", "--loop", loop, "--reason", "half of the reservation")
    ok(code == 0 and clearing.reservation(offer, loop)["settled"], "ruled, final: the reservation settled")
    ok(w3.eth.get_balance(wanter.address) - before[wanter.address] == MILLI, "the wanter was paid 0.001")
    ok(w3.eth.get_balance(giver.address) - before[giver.address] == MILLI, "0.001 returned to the giver")
    print("4. the reasons, and the personal view")
    code, text = loop_(wanter, "watch", "--once")
    ok("rules 0.001 to the wanter: half of the reservation" in text, "the wanter's watch opened the reasons")
    code, text = loop_(wanter, "arbitrators")
    ok(judge.address in text and "0.001 of 0.002 to the wanter" in text, "loop arbitrators read the ruling")
    print("sweeping the throwaway keys back")
    for account in (wanter, judge):
        sweep(w3, account, giver.address)
    print(f"GATE PASSED. offer {offer}")


if __name__ == "__main__":
    main()
