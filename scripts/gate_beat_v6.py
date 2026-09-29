"""The clearing trio's live gate (C4 + I3 + R3b, 2026-09-29): holds, item
claims and statements on a deployed `BeatClearing` + `LegVerifier` +
`StatementVerifier`.

    LOOP_CHAIN_RPC=https://rpc.gnosischain.com LOOP_CHAIN_KEY=$(cat ~/.loopmarket/chain_key) \\
      PYTHONPATH=src python3 scripts/gate_beat_v6.py PHASE CLEARING DIR

The chain key submits, challenges and finalizes; every bond comes back to
it (an honest beat's at finalize, a convicted one's to the challenger —
the same key). `DIR` holds the scratch clearing book, the registers and the
gate's state between phases, each phase a fresh process:

1. `post` — a book with an option market (a flat naming its item, an
   option on it, the holder's want of the option) and a credential market
   (a dentist whose licensed statement an attester issued under a chamber,
   a patient requiring it); one `ChainClearing` step posts both loops as
   beats, the option's with its hold and item claim committed, the
   dentist's with the register pins and the statement;
2. `check` — a fresh session finds each beat's evidence in the book and
   the challenger's dry run verifies every leg; the attester revokes the
   statement and a forged copy of the dentist beat pinning the new root is
   posted and convicted by challenge; an offer filled on the 2026-09-23
   contract reads as filled here (the predecessors' floor);
3. `finalize` (after the window) — both beats finalize, the hold and the
   item claim are the chain's; a non-holder's leg on the held flat is
   posted and convicted; the holder's exercise clears through
   `ChainClearing` and its legs verify;
4. `settle` (after the window) — the exercise finalizes: the flat is filled
   once and the hold used up.

Exits non-zero at the first expectation that fails.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from recordstore import DirBytesStore, FilePointer, RecordStore  # noqa: E402

from loopmarket import (  # noqa: E402
    Accept, Acceptance, Bond, Credential, OfferRegistry, Ontology, Requires, SolverAgent, Statement,
    Thing, TimeWindow, give, want,
)
from loopmarket.beat import (  # noqa: E402
    BeatClient, challenge_beat, commitment_of_registers, find_evidence, submission,
)
from loopmarket.clearing import ChainClearing, LoopProposal  # noqa: E402
from loopmarket.graph import Loop  # noqa: E402
from loopmarket.items import term, vin_id  # noqa: E402
from loopmarket.matching import Match  # noqa: E402
from loopmarket.register import Register  # noqa: E402

D, P = "0x" + "d0" * 20, "0x" + "a0" * 20                   # the dentist, the patient
ATTESTER, CHAMBER, JUDGE = "0x" + "a7" * 20, "0x" + "c4" * 20, "0x" + "77" * 20
EUR = Acceptance(("stablecoin-eur",), "EUR", 1)
OLD = "0x8997131ABD1a7A9a11A60cf828D82d6cEAA42913"            # the 2026-09-23 gate's contract
OLD_ABI = [                                                    # its fills, as it answers them
    {"name": "filled", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "offer", "type": "bytes32"}],
     "outputs": [{"name": "n", "type": "uint256"}, {"name": "d", "type": "uint256"}]},
    {"name": "pendingFills", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "beat", "type": "uint256"}],
     "outputs": [{"name": "", "type": "tuple[]", "components": [
         {"name": "offer", "type": "bytes32"}, {"name": "n", "type": "uint256"}, {"name": "d", "type": "uint256"},
         {"name": "capN", "type": "uint256"}, {"name": "capD", "type": "uint256"}]}]},
]


def ok(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        sys.exit(1)


def catalogue() -> Ontology:
    """Rebuilt the same in every phase: a canonical root, so the pins agree."""
    cat = Ontology.persistent(RecordStore(DirBytesStore(os.path.join(DIR, "catalogue"))))
    cat.declare_handover(["geo", "time"])
    cat.declare_item_heads()
    cat.declare_graph_heads(["option"])
    cat.load({"flat": [], "lesson": [], "painting": [], "dentistry": [], "licence": [],
              "dentist-licensed": ["licence"], "stablecoin-eur": []})
    cat.commit()
    return cat


def span(text: str):
    a, b = text.split("..")
    parse = lambda s: int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    return parse(a), parse(b)


def book() -> OfferRegistry:
    return OfferRegistry(RecordStore(BLOBS, pointer=FilePointer(os.path.join(DIR, "book.head"))))


def register_at(rid, root):
    return Register(RecordStore.at(root, BLOBS))


def save(state):
    with open(os.path.join(DIR, "state.json"), "w") as fh:
        json.dump(state, fh, indent=1)


def load():
    with open(os.path.join(DIR, "state.json")) as fh:
        return json.load(fh)


def post(client):
    t = int(time.time())
    cat = catalogue()
    V = dict(valid=TimeWindow(t - 3_600, t + 30 * 86_400), **cat.pins)
    b = book()
    h = vin_id(f"GATE{t:013d}")                                # a fresh item per run
    flat = give("seller", Thing(("flat", term(h)), 1, "flat"), 100, **V, nonce=t)
    option = give("seller", Thing((f"option(flat {term(h)})",), 1, "flat"), 5, **V, nonce=t + 1,
                  underlying=flat.offer_id, exercise=TimeWindow(t - 60, t + 7 * 86_400))
    day = datetime.fromtimestamp(t + 86_400, timezone.utc).strftime("%Y-%m-%d")
    window = f"{day}T10:00:00Z..{day}T11:00:00Z"
    dentist = give(D, Thing(("dentistry", f"time({window})"), 10, "visit", step=1), 300, **V, nonce=t + 2,
                   bond=Bond(Thing(("stablecoin-eur",), 500, "EUR"), 500, "0xE"), arbitrator=JUDGE)
    patient = want(P, Thing(("dentistry", f"time({window})"), 1, "visit"), 40, **V, nonce=t + 3,
                   requires=Requires(accepts=(EUR,), resolvers=Accept(keys=(JUDGE,)),
                                     counterparty=(Credential("dentist-licensed", ("attested", "self-bonded"),
                                                              min_bond=20, roots=(CHAMBER,),
                                                              max_root_age=86_400),)))
    b.publish_many([flat, option,
                    want("holder", Thing(("option(flat)",), 1, "flat"), 12, **V, nonce=t + 4),
                    give("holder", Thing(("lesson",), 1, "hour"), 5, **V, nonce=t + 5),
                    want("seller", Thing(("lesson",), 1, "hour"), 80, **V, nonce=t + 6),
                    # the credential market closes through a painting, not a lesson:
                    # shared goods would let the solver join the two into one loop
                    dentist, patient,
                    give(P, Thing(("painting",), 1, "piece"), 10, **V, nonce=t + 7),
                    want(D, Thing(("painting",), 1, "piece"), 35, **V, nonce=t + 8)])
    statement = Statement(subject=D, category="dentist-licensed", issuer=ATTESTER, kind="attested",
                          as_of=t - 1_000, until=span(window)[1] + 86_400, evidence="ee" * 32,
                          path=(ATTESTER, CHAMBER), paid_by="subject", deposit=(dentist.offer_id, "0xE"))
    b.present(statement)
    b.commit()
    attester, chamber = Register(RecordStore(BLOBS)), Register(RecordStore(BLOBS))
    attester.issue(statement.statement_id, t - 1_000)
    chamber.accredit(ATTESTER, "licence", by=CHAMBER, since=t - 86_400 * 365, until=t + 86_400 * 365,
                     scheme="5c" * 32)
    for reg in (attester, chamber):
        reg.heartbeat(t - 100)
        reg.commit()
    registers = {ATTESTER: attester, CHAMBER: chamber}
    clearing = ChainClearing(b, cat, beat_client=client, clock=lambda: t, span=span, register_at=register_at)
    receipts = SolverAgent(b, cat, clearing=clearing, solver_id="gate", registers=registers,
                           span=span).step(now=t)
    print("receipts:", [(r.accepted, r.reason) for r in receipts])
    ok(len(receipts) == 2 and all(r.accepted for r in receipts), "both loops cleared and posted as beats")
    beats = {}
    for r in receipts:
        rec = b.store.get(f"loop/{r.loop_id}")
        kind = "option" if any(option.offer_id in l.get("gives", [l.get("give")]) for l in rec["legs"]) else "dentist"
        beats[kind] = int(r.reason.split()[1])
    ok(len(client.pending_holds(beats["option"])) == 1, "the option beat committed its hold")
    ok(len(client.pending_claims(beats["option"])) == 1, "and its item claim")
    pins = [(ATTESTER.encode(), bytes.fromhex(attester.root), 0), (CHAMBER.encode(), bytes.fromhex(chamber.root), 0)]
    ok(client.beat(beats["dentist"])["registers_hash"] == commitment_of_registers(sorted(pins)),
       "the dentist beat pins both registers' roots")
    save({"t": t, "item": h, "flat": flat.offer_id, "option": option.offer_id, "window": window,
          "statement": statement.statement_id, "beats": beats,
          "roots": {ATTESTER: attester.root, CHAMBER: chamber.root}, "pins": cat.pins})
    print(f"posted: option beat {beats['option']}, dentist beat {beats['dentist']}")


def check(client):
    s = load()
    cat = catalogue()
    b = book()
    for kind, beat in s["beats"].items():
        result = challenge_beat(client, beat, [b], cat, send=False, register_at=register_at, span=span)
        ok(result.evidence is not None, f"{kind} beat {beat}: the evidence found from a fresh session")
        ok(result.verifies and all(v.local is None for v in result.legs),
           f"{kind} beat {beat} verifies off chain and on: " + str([(v.local, v.chain) for v in result.legs]))
    # the attester revokes; a copy of the dentist beat pinning the new root is convicted
    state = client.beat(s["beats"]["dentist"])
    ev = find_evidence(state, [b], ontology=cat, register_at=register_at, span=span)
    attester = Register(RecordStore(BLOBS, root=s["roots"][ATTESTER]))
    attester.revoke(s["statement"], int(time.time()))
    revoked = attester.commit()
    reg = Register(RecordStore.at(revoked, BLOBS))
    sub = ev.submission
    li = next(i for i, st in enumerate(sub.statements) if st)
    import dataclasses

    from eth_abi import encode
    from eth_hash.auto import keccak

    from loopmarket.beat import LEG_TYPE, STATEMENTS_TYPE
    st = list(sub.statements[li][0])
    st[4] = [bytes.fromhex(n) for n in reg.prove("revoked/" + s["statement"])["nodes"]]
    st[5] = [bytes.fromhex(n) for n in reg.prove("suspended/" + s["statement"])["nodes"]]
    statements = [list(x) for x in sub.statements]
    statements[li] = [tuple(st)]
    registers = [(ATTESTER.encode(), bytes.fromhex(revoked), 0) if r[0] == ATTESTER.encode() else r
                 for r in sub.registers]
    hashes = [keccak(encode([LEG_TYPE, STATEMENTS_TYPE], [leg, x])) for leg, x in zip(sub.legs, statements)]
    forged = dataclasses.replace(sub, registers=registers, statements=statements, leg_hashes=hashes)
    bad, _ = client.submit(forged)
    reason = client.challenge(bad, li, forged)
    ok(reason == "the statement is revoked under its register's pinned root", f"forged beat {bad}: {reason}")
    ok(client.beat(bad)["cancelled"], f"forged beat {bad} cancelled, its bond the challenger's")
    # the predecessors' floor: the 2026-09-23 gate's fills read as filled here
    from fractions import Fraction

    from web3 import Web3
    old = client._web3().eth.contract(address=Web3.to_checksum_address(OLD), abi=OLD_ABI)
    for f in old.functions.pendingFills(1).call():
        n, d = old.functions.filled(f[0]).call()
        oid = bytes(f[0]).hex()
        ok(client.filled(oid) == Fraction(n, d) > 0, f"offer {oid[:12]} filled {Fraction(n, d)} here as on {OLD[:10]}")
    s["forged"] = bad
    save(s)


def finalize(client):
    s = load()
    for kind, beat in s["beats"].items():
        client.finalize(beat)
        ok(client.beat(beat)["finalized"], f"{kind} beat {beat} finalized")
    now = client.timestamp_of(client._web3().eth.block_number)
    ok(client.held_against(s["flat"], at=now) == 1, "the flat is held on chain")
    offer, until = client.item_claim(s["item"], "seller")
    ok(offer == s["flat"], f"the seller's claim on the item is through the flat, until {until}")
    cat = catalogue()
    b = book()
    t = int(time.time())
    V = dict(valid=TimeWindow(t - 3_600, t + 30 * 86_400), **cat.pins)
    flat = b.get(s["flat"])
    other = [want("other", Thing(("flat",), 1, "flat"), 120, **V, nonce=t + 20),
             give("other", Thing(("dentistry",), 1, "visit"), 5, **V, nonce=t + 21),
             want("seller", Thing(("dentistry",), 1, "visit"), 150, **V, nonce=t + 22)]
    mine = [want("holder", Thing(("flat",), 1, "flat"), 120, **V, nonce=t + 23),
            give("holder", Thing(("lesson",), 1, "hour"), 5, **V, nonce=t + 24),
            want("seller", Thing(("lesson",), 1, "hour"), 150, **V, nonce=t + 25)]
    b.publish_many(other + mine)
    b.commit()
    root = b.store.root
    snapshot = OfferRegistry(RecordStore.at(root, BLOBS))
    loop = Loop((Match(give=flat, want=other[0]), Match(give=other[1], want=other[2])))
    proposal = LoopProposal(loop, root, cat.root, "gate", t)
    lid = proposal.circulation.loop_id
    forged = submission(proposal, snapshot, records={f"item/{s['item']}/seller/{lid}": {"until": t + 86_400}})
    bad, _ = client.submit(forged)
    leg = next(i for i, l in enumerate(forged.legs) if l[1][0][0] == bytes.fromhex(flat.offer_id))
    reason = client.challenge(bad, leg, forged)
    ok("more than is left of the give" in reason, f"the non-holder's beat {bad}: {reason}")
    clearing = ChainClearing(b, cat, beat_client=client, clock=lambda: t)
    receipts = SolverAgent(b, cat, clearing=clearing, solver_id="gate").step(now=t)
    ex = [r for r in receipts if r.accepted]
    ok(len(ex) == 1, "the holder's exercise cleared: " + str([(r.accepted, r.reason) for r in receipts]))
    beat = int(ex[0].reason.split()[1])
    result = challenge_beat(client, beat, [b], cat, send=False)
    ok(result.verifies and all(v.local is None for v in result.legs),
       f"exercise beat {beat} verifies off chain and on: " + str([(v.local, v.chain) for v in result.legs]))
    s["exercise"] = beat
    save(s)


def settle(client):
    s = load()
    client.finalize(s["exercise"])
    ok(client.beat(s["exercise"])["finalized"], f"exercise beat {s['exercise']} finalized")
    now = client.timestamp_of(client._web3().eth.block_number)
    ok(client.filled(s["flat"]) == 1, "the flat is filled once")
    ok(client.held_against(s["flat"], at=now) == 0, "and its hold used up")


def main() -> None:
    global DIR, BLOBS
    rpc, key = os.environ.get("LOOP_CHAIN_RPC"), os.environ.get("LOOP_CHAIN_KEY")
    if not rpc or not key or len(sys.argv) != 4:
        sys.exit("set LOOP_CHAIN_RPC and LOOP_CHAIN_KEY; args: post|check|finalize|settle CLEARING DIR")
    phase, clearing, DIR = sys.argv[1:4]
    os.makedirs(DIR, exist_ok=True)
    BLOBS = DirBytesStore(os.path.join(DIR, "blobs"))
    client = BeatClient(rpc, clearing, key=key)
    {"post": post, "check": check, "finalize": finalize, "settle": settle}[phase](client)
    print(f"PHASE {phase} PASSED")


DIR = BLOBS = None

if __name__ == "__main__":
    main()
