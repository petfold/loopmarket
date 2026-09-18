"""The beat on chain: posting a cleared loop as one beat of `BeatClearing`,
challenging a leg, finalizing (P2, decided with Peter 2026-09-15).

The chain holds commitments and, after the window, the fills; the full
data — offers, proofs, potentials — lives in the clearing book on Swarm
and is rebuilt here from a `LoopProposal` and the snapshot it was solved
against. `submission(proposal, snapshot)` is pure Python: every leg in the
shape `LoopVerifier.Leg` expects (the want's and gives' value blobs and
trie paths under the snapshot's root, the quantities taken as `n/d`), the
keccak of each leg's ABI encoding (what the contract commits to), the
fills, and the potentials. `BeatClient` sends and reads; web3 and eth_abi
load lazily behind the `chain` extra (boundary B2).

Why the leg hash is over the ABI encoding: it is what a challenger must
reproduce byte for byte to be heard, and the contract's own `abi.encode`
is the one canonical form both sides already share.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction

from .clearing import LoopProposal
from .registry import OfferRegistry
from .schema import q

LEG_TYPE = "((bytes32,bytes,bytes[]),(bytes32,bytes,bytes[])[],(uint256,uint256)[])"


def abi() -> dict:
    """The compiled contract: ABI and creation bytecode, shipped inside the
    package as `loopmarket/contracts/BeatClearing.json` (solc 0.8.24, via
    IR, optimizer 200 runs) so an installed wheel can talk to the deployed
    contract without a compiler or the repository."""
    from importlib import resources
    with resources.files("loopmarket").joinpath("contracts", "BeatClearing.json").open(
            encoding="utf-8") as fh:
        return json.load(fh)


@dataclass(frozen=True)
class Submission:
    pins: tuple            # (bookRoot, ontologyRoot, registryVersion, contractVersion)
    legs: list             # LoopVerifier.Leg tuples, in the loop record's order
    leg_hashes: list       # keccak256(abi.encode(leg)) each
    fills: list            # (offer id bytes, n, d)
    makers: list           # bytes
    potentials: list       # (n, d)


def _rat(x) -> tuple[int, int]:
    f = q(x) if not isinstance(x, Fraction) else x
    return (f.numerator, f.denominator)


def _proof(snapshot: OfferRegistry, offer_id: str):
    p = snapshot.store.prove("offer/" + offer_id)
    if not p["present"]:
        raise ValueError(f"offer {offer_id[:12]} is not under the snapshot's root")
    return (bytes.fromhex(offer_id), bytes.fromhex(p["value"]),
            [bytes.fromhex(n) for n in p["nodes"]])


def submission(proposal: LoopProposal, snapshot: OfferRegistry) -> Submission:
    """Everything `BeatClearing.submit` and a later `challenge` need, from
    the proposal and the frozen book it was solved against (U4: the
    snapshot's root is the beat's book root)."""
    from eth_abi import encode
    from eth_hash.auto import keccak

    if snapshot.store.root != proposal.book_root:
        raise ValueError("the snapshot is not the proposal's book root")
    circ = proposal.circulation
    legs, fills = [], []
    for leg in sorted(circ.legs, key=lambda l: l.key):
        want = _proof(snapshot, leg.want.offer_id)
        gives = [_proof(snapshot, g.offer_id) for g in leg.gives]
        taken = [_rat(leg.taken(i)) for i in range(len(leg.gives))]
        legs.append((want, gives, taken))
        fills.append((bytes.fromhex(leg.want.offer_id), 1, 1))
        for g, t in zip(leg.gives, taken):
            fills.append((bytes.fromhex(g.offer_id), *t))
    hashes = [keccak(encode([LEG_TYPE], [leg])) for leg in legs]
    potentials = circ.potentials()
    makers = sorted(potentials)
    first = circ.legs[0].want
    pins = (bytes.fromhex(proposal.book_root),
            bytes.fromhex(proposal.ontology_root) if proposal.ontology_root else bytes(32),
            first.registry_version.encode(), first.contract_version.encode())
    return Submission(pins, legs, hashes, fills, [m.encode() for m in makers],
                      [_rat(potentials[m]) for m in makers])


class BeatClient:
    """`BeatClearing` at `address` on the chain behind `rpc_url`. `key`
    signs transactions (the submitter's or challenger's); reading needs
    none. `client` may be a web3 instance (tests, embedders)."""

    def __init__(self, rpc_url: str, address: str, *, key: str | None = None, client=None):
        self.rpc_url, self.address, self._key, self._client = rpc_url, address, key, client

    def _web3(self):
        if self._client is None:
            try:
                from web3 import Web3
            except ImportError as exc:
                raise RuntimeError("the beat needs web3: pip install 'loopmarket[chain]'") from exc
            self._client = Web3(Web3.HTTPProvider(self.rpc_url))
        return self._client

    def contract(self):
        return self._web3().eth.contract(address=self.address, abi=abi()["abi"])

    def _send(self, fn, value: int = 0, gas: int | None = None):
        w3 = self._web3()
        if not self._key:
            raise ValueError("a transaction needs a key (bee_signer)")
        account = w3.eth.account.from_key(self._key)
        tx = {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address),
              "value": value}
        if gas:
            tx["gas"] = gas
        signed = account.sign_transaction(fn.build_transaction(tx))
        return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    def bond(self) -> int:
        return self.contract().functions.bondWei().call()

    def submit(self, sub: Submission) -> tuple[int, dict]:
        """Post the beat; returns (beat id, receipt)."""
        c = self.contract()
        receipt = self._send(c.functions.submit(sub.pins, sub.leg_hashes, sub.fills,
                                                sub.makers, sub.potentials), value=self.bond())
        beat = c.events.Submitted().process_receipt(receipt)[0]["args"]["beat"]
        return beat, receipt

    def challenge(self, beat: int, index: int, sub: Submission, *, gas: int = 12_000_000) -> str:
        """Re-verify leg `index` on chain; returns the contract's reason."""
        c = self.contract()
        receipt = self._send(c.functions.challenge(beat, index, sub.leg_hashes, sub.legs[index],
                                                   sub.makers, sub.potentials), gas=gas)
        return c.events.Challenged().process_receipt(receipt)[0]["args"]["reason"]

    def finalize(self, beat: int) -> dict:
        return self._send(self.contract().functions.finalize(beat))

    def filled(self, offer_id: str) -> Fraction:
        n, d = self.contract().functions.filled(bytes.fromhex(offer_id)).call()
        return Fraction(n, d)

    def beat(self, beat: int) -> dict:
        b = self.contract().functions.beats(beat).call()
        return {"submitter": b[1], "bond": b[2], "submitted_at": b[3], "fills": b[6],
                "finalized": b[7], "cancelled": b[8]}
