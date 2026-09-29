"""The escrow verbs' live gate (C6, 2026-09-29 night): `loop extend-claim`,
`assign`, `settle SPLIT`, `countersign`, `cancel` and `collect` run as
command lines against a deployed `LoopEscrow`.

    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=$(cat ~/.loopmarket/chain_key) \\
      PYTHONPATH=src python3 scripts/gate_verbs.py ESCROW RESOLVER [OFFER]

The chain key is the escrow's clearing and the deposit's giver, RESOLVER
the reservations' (never a party: factbond's `Assertions`), OFFER an
earlier gate deposit of 0.006 by the chain key to reuse; throwaway
keys are made for the wanter and the heir she assigns to, funded with a
little gas, and swept back at the end. Behind one gate offer id, 0.006
xDAI is deposited and three reservations of 0.002 made (windows a day
ahead, a one-hour claim period):

1. split: the giver lengthens the claim period by an hour (`extend-claim`),
   the wanter assigns the claim to the heir (`assign`), the giver signs a
   split of 25% (`settle OFFER 25%`) and the heir the same in the asset
   (`settle OFFER 0.0005xDAI`) — the second signature pays the heir 0.0005;
2. receipt: the wanter countersigns (`countersign`), the reservation back
   to the giver;
3. cancel: the giver cancels before the window (`cancel`), with no ladder
   nothing to the wanter.

Each step is `loop` itself (`cli.dispatch`), naming the reservation by its
whole offer and loop ids. Exits non-zero at the first expectation that fails.
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
    if not rpc or not key or len(sys.argv) not in (3, 4):
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: ESCROW RESOLVER [OFFER]")
    escrow_addr, resolver = (Web3.to_checksum_address(a) for a in sys.argv[1:3])
    w3 = Web3(Web3.HTTPProvider(rpc))
    giver = w3.eth.account.from_key(key)
    wanter, heir = w3.eth.account.create(), w3.eth.account.create()
    stamp = str(int(time.time()))
    h = lambda s: hashlib.sha256(f"verbs-gate-{s}-{stamp}".encode()).hexdigest()
    offer, split, receipt, cancel = h("offer"), h("split"), h("receipt"), h("cancel")
    reuse = len(sys.argv) == 4
    if reuse:
        offer = sys.argv[3].lower().removeprefix("0x")
    print(f"gate {stamp}: escrow {escrow_addr}; wanter {wanter.address}, heir {heir.address}")
    for account in (wanter, heir):
        fund(w3, giver, account.address, 2 * MILLI)
    clearing = EscrowClient(rpc, escrow_addr, key=key, client=w3)
    if not reuse:
        clearing.deposit(offer, 6 * MILLI)
    ok(clearing.free(offer) >= 6 * MILLI, "0.006 free behind the gate offer")
    now = w3.eth.get_block("latest")["timestamp"]
    for loop in (split, receipt, cancel):
        clearing.reserve(offer, loop, wanter.address, resolver, 2 * MILLI,
                         window=(now + 86_400, now + 90_000), claim_seconds=3600)
    home = tempfile.mkdtemp()
    os.environ.update({"LOOP_HOME": home, "LOOP_BOOK": f"rs:{home}/book", "LOOP_CONFIRM": "off",
                       "LOOP_ESCROW": f"chain:{rpc}@{escrow_addr}"})

    def loop_(who, *argv):
        os.environ["BEE_SIGNER"] = who.key.hex()
        os.environ["LOOP_MAKER"] = who.address
        out, err = io.StringIO(), io.StringIO()
        code = cli.dispatch(list(argv), cli.Session(), out, err)
        text = out.getvalue() + err.getvalue()
        print("  $ loop " + " ".join(a if len(a) < 20 else a[:12] + "…" for a in argv) + "\n    "
              + text.strip().replace("\n", "\n    "))
        return code, text

    print("1. split")
    before = clearing.reservation(offer, split)["claim_until"]
    ok(loop_(giver, "extend-claim", offer, "1h", "--loop", split)[0] == 0
       and clearing.reservation(offer, split)["claim_until"] == before + 3600, "the claim period lengthened by 1h")
    ok(loop_(wanter, "assign", offer, heir.address, "--loop", split)[0] == 0
       and clearing.reservation(offer, split)["wanter"] == heir.address, "the claim assigned to the heir")
    code, text = loop_(giver, "settle", offer, "25%", "--loop", split)
    ok(code == 0 and "waiting for the other party's" in text, "the giver signed a 25% split")
    got = w3.eth.get_balance(heir.address)
    code, text = loop_(heir, "settle", offer, "0.0005xDAI", "--loop", split)
    ok(code == 0 and "both signed, settled" in text, "the heir signed the same split: settled")
    ok(w3.eth.get_balance(heir.address) > got, "the heir was paid (0.0005 less gas)")
    print("2. receipt")
    code, text = loop_(wanter, "countersign", offer, "--loop", receipt)
    ok(code == 0 and clearing.reservation(offer, receipt)["settled"], "the wanter countersigned")
    print("3. cancel")
    code, text = loop_(giver, "cancel", offer, "--loop", cancel)
    ok(code == 0 and clearing.reservation(offer, cancel)["settled"], "the giver cancelled before the window")
    code, text = loop_(wanter, "collect", "--check")
    ok(code == 0 and "nothing owed" in text, "nothing owed to the wanter")
    print("sweeping the throwaway keys back")
    for account in (wanter, heir):
        sweep(w3, account, giver.address)
    ok(clearing.free(offer) == clearing.held(offer) == 0, "every reservation settled and paid out: nothing left held")
    print(f"GATE PASSED. offer {offer}")


if __name__ == "__main__":
    main()
