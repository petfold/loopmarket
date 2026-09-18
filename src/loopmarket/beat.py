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

The challenger's half (2026-09-18). The CLI keeps no copy of what it
posted: the book is the channel, as for handoffs. A challenger reads the
beat from the chain (pins, the committed hashes, the pending fills), finds
the `loop/` record whose rebuilt submission hashes to exactly those
commitments — in the submitter's announced clearing book, under the beat's
book root — rebuilds the proposal (`proposal_from_record`), re-derives
every leg off chain with the same `MockClearing` checklist that cleared it
(U3), asks the contract's own verifier for its verdict on each leg through
`eth_call` sent as the contract itself (free, `BeatClient.verdict`), and
sends the challenge only where the contract would convict. A leg the
contract cannot fault — a give that does not fit the want, an expired
window, a withdrawn offer — is reported as the arbiter's (P3). A beat with
no record behind it anywhere is reported as unverifiable: the contract
cannot convict what nobody has seen, so the bond is the only deterrent
there (`docs/plans/proof-fabric.md`, publication of the anchored root).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction

from .clearing import LoopProposal, MockClearing
from .graph import Circulation
from .matching import Leg
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


def submission(proposal: LoopProposal, snapshot: OfferRegistry, *,
               potentials: dict | None = None) -> Submission:
    """Everything `BeatClearing.submit` and a later `challenge` need, from
    the proposal and the frozen book it was solved against (U4: the
    snapshot's root is the beat's book root). `potentials` overrides the
    recomputed ones: a challenger commits to what the *submitter* posted,
    so the contract hears the challenge, and lets the verifier judge them."""
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
    if potentials is None:
        potentials = circ.potentials()
    makers = sorted(potentials)
    first = circ.legs[0].want
    pins = (bytes.fromhex(proposal.book_root),
            bytes.fromhex(proposal.ontology_root) if proposal.ontology_root else bytes(32),
            first.registry_version.encode(), first.contract_version.encode())
    return Submission(pins, legs, hashes, fills, [m.encode() for m in makers],
                      [_rat(potentials[m]) for m in makers])


def commitment(sub: Submission) -> tuple[bytes, bytes]:
    """(legsHash, potentialsHash) exactly as `BeatClearing.submit` stores
    them: keccak over the ABI encoding of the leg hashes, and of (makers,
    potentials). What a rebuilt submission must equal to be the beat's."""
    from eth_abi import encode
    from eth_hash.auto import keccak
    return (keccak(encode(["bytes32[]"], [sub.leg_hashes])),
            keccak(encode(["bytes[]", "(uint256,uint256)[]"], [sub.makers, sub.potentials])))


def legs_from_record(rec: dict, book: OfferRegistry) -> tuple[Leg, ...]:
    """The `Leg`s a `loop/` record names, with the offers read from `book`.
    The record's `taken` decides the leg's shape: shares that are not what
    `Leg.taken` derives for a simple or operator-composed leg are an
    aggregated leg's explicit quantities (the six lifters), so the rebuilt
    leg clears through the same check the original did."""
    legs = []
    for lr in rec["legs"]:
        want = book.get(lr["want"])
        gives = tuple(book.get(g) for g in lr.get("gives", [lr["give"]]))
        taken = tuple(q(t) for t in lr.get("taken", []))
        leg = Leg(want, gives)
        if taken and taken != tuple(leg.taken(i) for i in range(len(gives))):
            leg = Leg(want, gives, taken)
        legs.append(leg)
    return tuple(legs)


def proposal_from_record(rec: dict, snapshot: OfferRegistry) -> LoopProposal:
    """The proposal a `loop/` record is the trace of, over the snapshot it
    pins — what a challenger re-derives and re-submits, byte for byte."""
    if rec.get("v") != 1:
        raise ValueError(f"loop record v{rec.get('v')}: not a version this reader knows")
    circ = Circulation(legs_from_record(rec, snapshot))
    if circ.loop_id != rec["loop_id"]:
        raise ValueError("the record's legs do not hash to its loop_id")
    return LoopProposal(circ, rec["book_root"], rec.get("ontology_root", ""),
                        rec.get("solver", ""), int(rec.get("found_at", 0)))


def snapshot_of(book: OfferRegistry, root: str) -> OfferRegistry:
    """The book frozen at `root`, from the blobs `book`'s store holds (a
    Swarm store fetches any root ever published; a directory store keeps
    every blob it wrote)."""
    return OfferRegistry(type(book.store).at(root, book.store.blobs))


@dataclass(frozen=True)
class Evidence:
    """A beat's data, found: the record, the snapshot it pins and the
    submission that hashes to the beat's commitments."""
    record: dict
    snapshot: OfferRegistry
    submission: Submission
    book: OfferRegistry


def find_evidence(state: dict, books) -> Evidence | None:
    """The `loop/` record behind a beat, from the first of `books` that
    holds one under the beat's book root whose rebuilt submission hashes to
    the committed legs and potentials — so what is re-derived is exactly
    what was posted, whatever the record claims. None when no book has it:
    the submitter has published no evidence, or not where anyone looks."""
    root = state["book_root"]
    for book in books:
        for key, rec in book.store.items("loop/"):
            if not isinstance(rec, dict) or rec.get("book_root") != root:
                continue
            try:
                snapshot = snapshot_of(book, root)
                proposal = proposal_from_record(rec, snapshot)
                potentials = {m: q(e) for m, e in rec.get("potentials", {}).items()} or None
                sub = submission(proposal, snapshot, potentials=potentials)
            except Exception:                   # noqa: BLE001 — a record that is not this beat's
                continue
            if commitment(sub) == (state["legs_hash"], state["potentials_hash"]):
                return Evidence(rec, snapshot, sub, book)
    return None


@dataclass(frozen=True)
class LegVerdict:
    index: int
    local: str | None        # the off-chain re-derivation's reason, None when the leg holds
    chain: str | None        # the contract's own verdict from a dry run ("leg verifies" or a reason)

    @property
    def convicts(self) -> bool:
        return self.chain is not None and self.chain != "leg verifies"


@dataclass(frozen=True)
class Challenge:
    """What `challenge_beat` found and did."""
    beat: int
    state: dict
    evidence: Evidence | None
    overall: str | None                  # the whole checklist's reason off chain, None when it clears
    legs: tuple[LegVerdict, ...]
    sent: int | None = None              # the leg index challenged on chain, if any
    reason: str | None = None            # the contract's answer to that challenge
    cancelled: bool = False

    @property
    def verifies(self) -> bool:
        return self.evidence is not None and self.overall is None \
            and not any(v.convicts for v in self.legs)


def challenge_beat(client: "BeatClient", beat: int, books, ontology, *, now: int | None = None,
                   index: int | None = None, send: bool = True) -> Challenge:
    """Verify beat `beat` as a challenger and act on it. `books` are where
    the evidence may be (the submitter's clearing book first); `ontology`
    the pinned catalogue the legs are re-derived under; `now` the moment
    the windows are judged at (the beat's block time by default). With
    `index`, that leg is challenged on chain whatever the dry run says;
    otherwise the first leg the contract would convict is, when `send`.
    Nothing is sent for a fault the contract cannot compute."""
    state = client.beat(beat)
    ev = find_evidence(state, books)
    if ev is None:
        return Challenge(beat, state, None, "no evidence", ())
    if now is None:
        now = client.timestamp_of(state["submitted_at"])
    proposal = proposal_from_record(ev.record, ev.snapshot)
    # the chain's fills are the authority on what is left of a give (the
    # snapshot precedes the beat; the contract's set may not)
    available = {}
    for oid in proposal.circulation.offer_ids:
        offer = ev.snapshot.get(oid)
        left = ev.snapshot.available(oid)
        if not offer.composed:
            left = min(left, q(offer.thing.qty) - client.filled(oid))
        available[oid] = left
    mock = MockClearing(ev.snapshot, ontology, clock=lambda: now)
    overall = mock.rehearse(proposal)
    legs = []
    for i, leg in enumerate(sorted(proposal.circulation.legs, key=lambda l: l.key)):
        if proposal.ontology_root != ontology.root:
            local = "ontology pin mismatch"
        else:
            try:
                local = mock.verify_leg(leg, now=now, available=available)
            except KeyError as exc:
                local = f"unknown offer: {exc}"
        legs.append(LegVerdict(i, local, client.verdict(state, i, ev.submission)))
    result = Challenge(beat, state, ev, None if overall.accepted else overall.reason, tuple(legs))
    target = index if index is not None else \
        next((v.index for v in legs if v.convicts), None)
    if target is None or not send or not state["open"]:
        return result
    reason = client.challenge(beat, target, ev.submission)
    return Challenge(beat, state, ev, result.overall, tuple(legs), target, reason,
                     client.beat(beat)["cancelled"])


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
        """The beat's record on chain: the pins, the submitter, the two
        commitments (as bytes), the fill count, its state and window."""
        c = self.contract()
        b = c.functions.beats(beat).call()
        if b[3] == 0:
            raise ValueError(f"no beat {beat}")
        pins = b[0]
        window_end = b[3] + c.functions.windowBlocks().call()
        return {"beat": beat, "submitter": b[1], "bond": b[2], "submitted_at": b[3],
                "book_root": pins[0].hex(), "ontology_root": pins[1].hex(),
                "registry_version": bytes(pins[2]).decode(),
                "contract_version": bytes(pins[3]).decode(),
                "legs_hash": bytes(b[4]), "potentials_hash": bytes(b[5]), "fills": b[6],
                "finalized": b[7], "cancelled": b[8], "window_end": window_end,
                "open": not b[7] and not b[8]
                and self._web3().eth.block_number <= window_end}

    def beats(self) -> list[dict]:
        """Every beat posted, first to last."""
        n = self.contract().functions.beatCount().call()
        return [self.beat(i) for i in range(1, n + 1)]

    def pending_fills(self, beat: int) -> list[tuple[str, Fraction]]:
        return [(f[0].hex(), Fraction(f[1], f[2]))
                for f in self.contract().functions.pendingFills(beat).call()]

    def timestamp_of(self, block: int) -> int:
        return int(self._web3().eth.get_block(block)["timestamp"])

    def verdict(self, state: dict, index: int, sub: Submission,
                *, gas: int = 12_000_000) -> str | None:
        """What the contract's verifier says about leg `index` of a posted
        beat, without a transaction — see `verdict_of`."""
        pins = (bytes.fromhex(state["book_root"]), bytes.fromhex(state["ontology_root"]),
                state["registry_version"].encode(), state["contract_version"].encode())
        return self.verdict_of(sub, index, pins=pins, gas=gas)

    def verdict_of(self, sub: Submission, index: int, *, pins=None,
                   gas: int = 12_000_000) -> str | None:
        """What the contract's verifier says about leg `index` of a
        submission, without a transaction: `verifyLegExternal` run through
        `eth_call` with the contract itself as sender (the only sender it
        accepts), against the chain's current fills, under `pins` (the
        submission's own by default — so a submitter asks *before* paying a
        bond, and a challenger asks under the beat's). "leg verifies", or
        the revert reason — the same string a challenge would put in its
        event; None when the node would not run the call (never a
        conviction)."""
        c = self.contract()
        pins = sub.pins if pins is None else pins
        fn = c.functions.verifyLegExternal(pins, sub.legs[index], sub.makers, sub.potentials)
        w3 = self._web3()
        params = {"from": self.address, "gas": gas}
        # The contract's balance is only the bonds it holds, and some nodes
        # charge even a call's gas against the sender. In order: the sender
        # funded by the call's state override (geth, nethermind, erigon); a
        # free call (gas price zero, which those nodes also take); a plain
        # call at the going price with as much gas as the bonds afford (the
        # test node) — abandoned below the gas one leg's verification needs.
        price = w3.eth.gas_price or 1
        affordable = min(gas, w3.eth.get_balance(self.address) // price)
        attempts = [lambda: fn.call(params, "latest", {self.address: {"balance": 10 ** 24}}),
                    lambda: fn.call({**params, "gasPrice": 0})]
        if affordable >= 4_000_000:
            attempts.append(lambda: fn.call({**params, "gas": affordable, "gasPrice": price}))
        for attempt in attempts:
            try:
                attempt()
            except Exception as exc:            # noqa: BLE001
                if _is_revert(exc):             # a revert: the verifier's reason
                    return _revert_reason(exc)
                continue                        # the node refused the call itself
            return "leg verifies"
        return None


def _is_revert(exc: Exception) -> bool:
    """A contract revert, as web3 (`ContractLogicError`) or the test node
    (`TransactionFailed`) raises it — as opposed to the node refusing to
    run the call at all (fees, balance, an unsupported parameter)."""
    try:
        from web3.exceptions import ContractLogicError
        if isinstance(exc, ContractLogicError):
            return True
    except ImportError:
        pass
    return "execution reverted" in str(exc)


def _revert_reason(exc: Exception) -> str:
    """The reason string out of web3's ContractLogicError (`execution
    reverted: <reason>`, or the raw message on older providers)."""
    text = str(getattr(exc, "message", None) or exc)
    if ":" in text and text.startswith("execution reverted"):
        text = text.split(":", 1)[1].strip()
    return text.strip("'\" ") or "leg fails: reverted without a reason"
