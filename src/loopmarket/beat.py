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

Holds, item claims and registers (2026-09-29: C4, I3, R3b). A submission
also carries what the beat commits beside its fills: the holds its option
legs write (derived from the legs), the item claims its gives write (their
ends are the clearing's `item/` records, `records`), the register roots the
proposal pins, and — hashed into each leg's commitment — the statements
each credential entry needs, chosen by the counterparty gate over the
snapshot (`gate`), each with its `cred/` inclusion proof under the book
root and its `revoked/` and `suspended/` absence proofs under the issuer's
pinned root. Each give's fill names its taker (keccak of the wanter), whose
holds it consumes.
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

OFFER_PROOF_TYPE = "(bytes32,bytes,bytes[])"
LEG_TYPE = f"({OFFER_PROOF_TYPE},{OFFER_PROOF_TYPE}[],(uint256,uint256)[],{OFFER_PROOF_TYPE}[])"
STATEMENTS_TYPE = "(uint32,bool,bytes,bytes[],bytes[],bytes[])[]"
REGISTERS_TYPE = "(bytes,bytes32,uint8)[]"
#: No underlying: a plain give's slot in `Leg.underlying`.
NO_UNDERLYING = (bytes(32), b"", [])


def abi() -> dict:
    """The compiled contract: ABI and creation bytecode, shipped inside the
    package as `loopmarket/contracts/BeatClearing.json` (solc 0.8.24, via
    IR, optimizer 200 runs; rebuilt by `scripts/build_beat.py`) so an
    installed wheel can talk to the deployed contract without a compiler
    or the repository."""
    return _artifact("BeatClearing.json")


def verifier_abi() -> dict:
    """`LegVerifier` (2026-09-23): the leg verification `BeatClearing` calls,
    deployed once beside it — the library outgrew the clearing contract's
    EIP-170 room. Shipped and rebuilt as `abi()` is."""
    return _artifact("LegVerifier.json")


def _artifact(name: str) -> dict:
    from importlib import resources
    with resources.files("loopmarket").joinpath("contracts", name).open(encoding="utf-8") as fh:
        return json.load(fh)


def deploy(w3, bond_wei: int, window_blocks: int, arbiter: str | None = None, *,
           predecessors=(), verifier: str | None = None, statements: str | None = None,
           key: str | None = None) -> tuple[str, str]:
    """Deploy a `BeatClearing` (and, unless `verifier`/`statements` name
    them already on the chain, a `LegVerifier` and a `StatementVerifier` for
    it) and return (clearing, verifier).
    `predecessors` are the earlier clearing contracts whose fills are the new
    one's floor — list every address that has recorded fills, so an offer
    they cleared cannot clear again. `key` signs raw transactions (a remote
    node); without it the node's default account sends (a test chain).
    `arbiter` defaults to the sender."""
    account = w3.eth.account.from_key(key) if key else None
    sender = account.address if account else w3.eth.default_account

    def send(built):
        if account is None:
            tx = built.transact({"from": sender})
        else:
            tx = w3.eth.send_raw_transaction(account.sign_transaction(built.build_transaction({
                "from": sender, "nonce": w3.eth.get_transaction_count(sender)})).raw_transaction)
        return w3.eth.wait_for_transaction_receipt(tx)["contractAddress"]

    if verifier is None:
        art = verifier_abi()
        verifier = send(w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor())
    if statements is None:
        art = _artifact("StatementVerifier.json")
        statements = send(w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor())
    art = abi()
    clearing = send(w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor(
        bond_wei, window_blocks, arbiter or sender, verifier, statements,
        [w3.to_checksum_address(p) for p in predecessors]))
    return clearing, verifier


#: The book root's addressing scheme as the contract numbers it
#: (`LoopVerifier.Beat.addressing`, 2026-09-18): the proof envelope names it.
ADDRESSING = {"sha256": 0, "swarm": 1}
ADDRESSING_NAMES = {v: k for k, v in ADDRESSING.items()}


@dataclass(frozen=True)
class Submission:
    pins: tuple            # (bookRoot, ontologyRoot, registryVersion, contractVersion, addressing)
    legs: list             # LoopVerifier.Leg tuples, in the loop record's order
    leg_hashes: list       # keccak256(abi.encode(leg, statements)) each
    fills: list            # (offer id, n, d, cap n, cap d, taker): a give's cap its quantity, a want's 1/1
    makers: list           # bytes
    potentials: list       # (n, d)
    registers: list = ()   # (register id bytes, root, addressing): the pinned register roots (R3b)
    statements: list = ()  # per leg, its StatementProof tuples (R3b)
    holds: list = ()       # LoopVerifier.Hold tuples (C4)
    claims: list = ()      # LoopVerifier.ItemClaim tuples (I3)


def _rat(x) -> tuple[int, int]:
    f = q(x) if not isinstance(x, Fraction) else x
    return (f.numerator, f.denominator)


def _proof(snapshot: OfferRegistry, offer_id: str):
    p = snapshot.store.prove("offer/" + offer_id)
    if not p["present"]:
        raise ValueError(f"offer {offer_id[:12]} is not under the snapshot's root")
    return (bytes.fromhex(offer_id), bytes.fromhex(p["value"]),
            [bytes.fromhex(n) for n in p["nodes"]])


def _addressing(snapshot: OfferRegistry, offer_id: str) -> int:
    """The scheme the snapshot's proofs name — sha256 for a directory or
    memory store, Swarm's BMT for a book on Swarm or a Swarm-addressed
    mirror — as the contract numbers it. Unknown names refuse: a beat the
    contract cannot verify is never built."""
    name = snapshot.store.prove("offer/" + offer_id).get("addressing")
    if name not in ADDRESSING:
        raise ValueError(f"the book's proofs use {name!r} addressing, which no verifier knows")
    return ADDRESSING[name]


def submission(proposal: LoopProposal, snapshot: OfferRegistry, *,
               potentials: dict | None = None, records: dict | None = None, gate=None,
               ontology=None) -> Submission:
    """Everything `BeatClearing.submit` and a later `challenge` need, from
    the proposal and the frozen book it was solved against (U4: the
    snapshot's root is the beat's book root). `potentials` overrides the
    recomputed ones: a challenger commits to what the *submitter* posted,
    so the contract hears the challenge, and lets the verifier judge them.
    `records` are the clearing's `item/` records of this loop (a fill's
    item claim ends where the clearing said; an option's where its window
    does); `gate` and `ontology` choose the statements a credential entry
    needs, over the snapshot. A leg that needs either and is not given it
    is refused here: a beat the contract would convict is never built."""
    from eth_abi import encode
    from eth_hash.auto import keccak

    from . import items

    if snapshot.store.root != proposal.book_root:
        raise ValueError("the snapshot is not the proposal's book root")
    circ = proposal.circulation
    lid = circ.loop_id
    legs, fills, statements, holds, claims = [], [], [], [], []
    for li, leg in enumerate(sorted(circ.legs, key=lambda l: l.key)):
        want = _proof(snapshot, leg.want.offer_id)
        gives = [_proof(snapshot, g.offer_id) for g in leg.gives]
        taken = [_rat(leg.taken(i)) for i in range(len(leg.gives))]
        taker = keccak(leg.want.maker.encode())
        under = []
        fills.append((bytes.fromhex(leg.want.offer_id), 1, 1, 1, 1, bytes(32)))
        for i, (g, t) in enumerate(zip(leg.gives, taken)):
            fills.append((bytes.fromhex(g.offer_id), *t, *_rat(g.thing.qty), taker))
            subject, until = g, None
            if g.v >= 6 and g.underlying:
                p = snapshot.get(g.underlying)
                under.append(_proof(snapshot, g.underlying))
                holds.append((bytes.fromhex(g.offer_id), bytes.fromhex(g.underlying), t, _rat(p.thing.qty),
                              taker, int(g.exercise.start), int(g.exercise.end), li))
                subject, until = p, int(g.exercise.end)
            else:
                under.append(NO_UNDERLYING)
            for h in items.ids(subject.thing.concepts):
                end = until
                if end is None:
                    rec = (records or {}).get(f"item/{h}/{g.maker}/{lid}")
                    if rec is None:
                        raise ValueError(f"the item claim on {h[:12]} needs the clearing's record of its end")
                    end = int(rec["until"])
                claims.append((bytes.fromhex(h), keccak(g.maker.encode()), bytes.fromhex(subject.offer_id),
                               end, li))
        legs.append((want, gives, taken, under))
        statements.append(_statement_proofs(leg, snapshot, gate, ontology))
    hashes = [keccak(encode([LEG_TYPE, STATEMENTS_TYPE], [leg, st])) for leg, st in zip(legs, statements)]
    if potentials is None:
        potentials = circ.potentials()
    makers = sorted(potentials)
    first = circ.legs[0].want
    pins = (bytes.fromhex(proposal.book_root),
            bytes.fromhex(proposal.ontology_root) if proposal.ontology_root else bytes(32),
            first.registry_version.encode(), first.contract_version.encode(),
            _addressing(snapshot, first.offer_id))
    registers = []
    for rid, root in sorted(proposal.register_roots):
        reg = gate.registers.get(rid) if gate is not None else None
        name = reg.prove(REVOKED_PROBE).get("addressing", "sha256") if reg is not None else "sha256"
        registers.append((rid.encode(), bytes.fromhex(root), ADDRESSING.get(name, 0)))
    return Submission(pins, legs, hashes, fills, [m.encode() for m in makers],
                      [_rat(potentials[m]) for m in makers], registers, statements, holds, claims)


#: A key probed only to learn a register root's addressing scheme.
REVOKED_PROBE = "revoked/"


def _statement_proofs(leg: Leg, snapshot: OfferRegistry, gate, ontology) -> list:
    """The statements leg `leg` needs (R3b): for each give, one per
    credential entry the want requires of it and one per entry it requires
    of the want — the one the gate accepts, as `StatementProof` tuples."""
    out = []
    for i, give in enumerate(leg.gives):
        for mine, other, of_give in ((leg.want, give, True), (give, leg.want, False)):
            entries = mine.requires.counterparty if mine.v >= 6 and mine.requires is not None else ()
            if not entries:
                continue
            if gate is None or ontology is None:
                raise ValueError("a credential requirement needs the gate to choose its statements")
            window = gate.window(leg.want)
            taken = q(leg.want.thing.qty) if of_give and not leg.want.composed else None
            whole = q(give.thing.qty) if of_give else None
            for entry in entries:
                s = gate.chosen(entry, mine, other, ontology, window=window, taken=taken, whole=whole)
                if s is None:
                    raise ValueError(f"no statement of {other.maker} meets {entry.category}")
                out.append(_statement_proof(i, of_give, s, snapshot, gate))
    return out


def _statement_proof(give: int, of_give: bool, s, snapshot: OfferRegistry, gate) -> tuple:
    sid = s.statement_id
    p = snapshot.store.prove(f"cred/{s.subject}/{sid}")
    if not p["present"]:
        raise ValueError(f"statement {sid[:12]} is not presented under the book root")
    revoked = suspended = []
    if s.kind != "self-bonded":
        reg = gate.registers.get(s.issuer)
        if reg is None:
            raise ValueError(f"the register of {s.issuer} is not pinned")
        rp, sp = reg.prove("revoked/" + sid), reg.prove("suspended/" + sid)
        if rp["present"] or sp["present"]:
            raise ValueError(f"statement {sid[:12]} does not stand under its register's pinned root")
        revoked, suspended = ([bytes.fromhex(n) for n in x["nodes"]] for x in (rp, sp))
    return (give, of_give, bytes.fromhex(p["value"]), [bytes.fromhex(n) for n in p["nodes"]],
            revoked, suspended)


def loop_records(book: OfferRegistry, loop_id: str) -> dict:
    """The clearing's `item/` records of one loop, from its book — what a
    rebuilt submission reads its item claims' ends from."""
    return {k: v for k, v in book.store.items("item/") if k.endswith("/" + loop_id)}


def commitment(sub: Submission) -> tuple[bytes, bytes, bytes]:
    """(legsHash, potentialsHash, registersHash) exactly as
    `BeatClearing.submit` stores them: keccak over the ABI encoding of the
    leg hashes, of (makers, potentials), and of the register pins. What a
    rebuilt submission must equal to be the beat's."""
    from eth_abi import encode
    from eth_hash.auto import keccak
    return (keccak(encode(["bytes32[]"], [sub.leg_hashes])),
            keccak(encode(["bytes[]", "(uint256,uint256)[]"], [sub.makers, sub.potentials])),
            keccak(encode([REGISTERS_TYPE], [list(sub.registers)])))


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
    if rec.get("v") not in (1, 2):
        raise ValueError(f"loop record v{rec.get('v')}: not a version this reader knows")
    if (rec["v"] == 2) != ("register_roots" in rec):
        raise ValueError("a loop record v2 carries register_roots, v1 none")
    circ = Circulation(legs_from_record(rec, snapshot))
    if circ.loop_id != rec["loop_id"]:
        raise ValueError("the record's legs do not hash to its loop_id")
    return LoopProposal(circ, rec["book_root"], rec.get("ontology_root", ""),
                        rec.get("solver", ""), int(rec.get("found_at", 0)),
                        tuple(sorted(rec.get("register_roots", {}).items())))


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


def find_evidence(state: dict, books, *, ontology=None, register_at=None, span=None) -> Evidence | None:
    """The `loop/` record behind a beat, from the first of `books` that
    holds one under the beat's book root whose rebuilt submission hashes to
    the committed legs, potentials and register pins — so what is
    re-derived is exactly what was posted, whatever the record claims. None
    when no book has it: the submitter has published no evidence, or not
    where anyone looks. A beat whose legs need statements is rebuilt with
    the gate over the snapshot, the registers read at the record's pins by
    `register_at(id, root)` and the handover windows by `span`, at the
    beat's time; without them such a record is not found."""
    from .gate import CounterpartyGate
    root = state["book_root"]
    for book in books:
        for key, rec in book.store.items("loop/"):
            if not isinstance(rec, dict) or rec.get("book_root") != root:
                continue
            try:
                snapshot = snapshot_of(book, root)
                proposal = proposal_from_record(rec, snapshot)
                potentials = {m: q(e) for m, e in rec.get("potentials", {}).items()} or None
                registers = {rid: register_at(rid, r) for rid, r in proposal.register_roots
                             if r} if register_at is not None else {}
                gate = CounterpartyGate.over(snapshot, registers, now=int(state.get("time", 0)), span=span)
                sub = submission(proposal, snapshot, potentials=potentials,
                                 records=loop_records(book, rec["loop_id"]), gate=gate, ontology=ontology)
            except Exception:                   # noqa: BLE001 — a record that is not this beat's
                continue
            if commitment(sub) == (state["legs_hash"], state["potentials_hash"],
                                   state.get("registers_hash", commitment(sub)[2])):
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
                   index: int | None = None, send: bool = True, register_at=None,
                   span=None) -> Challenge:
    """Verify beat `beat` as a challenger and act on it. `books` are where
    the evidence may be (the submitter's clearing book first); `ontology`
    the pinned catalogue the legs are re-derived under; `now` the moment
    the windows are judged at (the beat's block time by default). With
    `index`, that leg is challenged on chain whatever the dry run says;
    otherwise the first leg the contract would convict is, when `send`.
    Nothing is sent for a fault the contract cannot compute."""
    state = client.beat(beat)
    ev = find_evidence(state, books, ontology=ontology, register_at=register_at, span=span)
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
    mock = MockClearing(ev.snapshot, ontology, clock=lambda: now, register_at=register_at, span=span)
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
        receipt = self._send(c.functions.submit(sub.pins, list(sub.registers), sub.leg_hashes, sub.fills,
                                                list(sub.holds), list(sub.claims), sub.makers,
                                                sub.potentials), value=self.bond())
        beat = c.events.Submitted().process_receipt(receipt)[0]["args"]["beat"]
        return beat, receipt

    def challenge(self, beat: int, index: int, sub: Submission, *, gas: int = 12_000_000) -> str:
        """Re-verify leg `index` on chain; returns the contract's reason."""
        c = self.contract()
        receipt = self._send(c.functions.challenge(beat, index, list(sub.registers), sub.leg_hashes,
                                                   sub.legs[index], sub.statements[index], sub.makers,
                                                   sub.potentials), gas=gas)
        return c.events.Challenged().process_receipt(receipt)[0]["args"]["reason"]

    def finalize(self, beat: int) -> dict:
        return self._send(self.contract().functions.finalize(beat))

    def filled(self, offer_id: str) -> Fraction:
        """What has been taken from the offer: this contract's fills plus its
        predecessors' (since 2026-09-23 the chain of clearing contracts is
        one fill authority)."""
        n, d = self.contract().functions.filled(bytes.fromhex(offer_id)).call()
        return Fraction(n, d)

    def recorded(self, offer_id: str) -> Fraction:
        """What this contract itself recorded as taken from the offer."""
        n, d = self.contract().functions.recorded(bytes.fromhex(offer_id)).call()
        return Fraction(n, d)

    def predecessors(self) -> list[str]:
        c = self.contract().functions
        return [c.predecessors(i).call() for i in range(c.predecessorCount().call())]

    def successor(self) -> str | None:
        s = self.contract().functions.successor().call()
        return None if int(s, 16) == 0 else s

    def retire(self, to: str) -> dict:
        """Hand the fill authority to the contract at `to` (the arbiter's
        key only): no new beat here after this."""
        return self._send(self.contract().functions.retire(self._web3().to_checksum_address(to)))

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
                "addressing": ADDRESSING_NAMES.get(pins[4], str(pins[4])),
                "legs_hash": bytes(b[4]), "potentials_hash": bytes(b[5]), "fills": b[6],
                "finalized": b[7], "cancelled": b[8], "window_end": window_end,
                "time": b[9], "registers_hash": bytes(b[10]),
                "open": not b[7] and not b[8]
                and self._web3().eth.block_number <= window_end}

    def beats(self) -> list[dict]:
        """Every beat posted, first to last."""
        n = self.contract().functions.beatCount().call()
        return [self.beat(i) for i in range(1, n + 1)]

    def pending_fills(self, beat: int) -> list[tuple[str, Fraction, Fraction]]:
        """The fills beat `beat` would record: (offer id, taken, the offer's cap)."""
        return [(f[0].hex(), Fraction(f[1], f[2]), Fraction(f[3], f[4]))
                for f in self.contract().functions.pendingFills(beat).call()]

    def pending_takers(self, beat: int) -> dict[str, bytes]:
        """Each offer's committed taker in beat `beat` (the first fill's, as
        the contract reads)."""
        out: dict = {}
        for f in self.contract().functions.pendingFills(beat).call():
            out.setdefault(f[0].hex(), bytes(f[5]))
        return out

    def pending_holds(self, beat: int) -> list:
        """The holds beat `beat` would record, as the contract's tuples."""
        return [tuple(h) for h in self.contract().functions.pendingHolds(beat).call()]

    def pending_claims(self, beat: int) -> list:
        """The item claims beat `beat` would record, as the contract's tuples."""
        return [tuple(c) for c in self.contract().functions.pendingClaims(beat).call()]

    def held_against(self, offer_id: str, taker: bytes = bytes(32), at: int = 0) -> Fraction:
        """What active holds keep of the offer from `taker` at `at` (C4)."""
        n, d = self.contract().functions.heldAgainst(bytes.fromhex(offer_id), taker, at).call()
        return Fraction(n, d)

    def item_claim(self, item: str, maker: str) -> tuple[str | None, int]:
        """A maker's recorded claim on an item: (offer id or None, until)."""
        from eth_hash.auto import keccak
        offer, until = self.contract().functions.itemClaim(bytes.fromhex(item), keccak(maker.encode())).call()
        return (None if int.from_bytes(offer, "big") == 0 else bytes(offer).hex(), until)

    def timestamp_of(self, block: int) -> int:
        return int(self._web3().eth.get_block(block)["timestamp"])

    def verdict(self, state: dict, index: int, sub: Submission,
                *, gas: int = 12_000_000) -> str | None:
        """What the contract's verifier says about leg `index` of a posted
        beat, without a transaction — see `verdict_of`. First the beat's
        committed fills against the leg's (the checks `challenge` makes
        before verifying, with its reasons): `sub` is rebuilt from the
        record, so it holds the true quantities and caps."""
        fault = self.fill_fault(state["beat"], index, sub)
        if fault:
            return fault
        pins = (bytes.fromhex(state["book_root"]), bytes.fromhex(state["ontology_root"]),
                state["registry_version"].encode(), state["contract_version"].encode(),
                ADDRESSING.get(state["addressing"], 255))
        verdict = self.verdict_of(sub, index, pins=pins, gas=gas, holds=self.pending_holds(state["beat"]),
                                  claims=self.pending_claims(state["beat"]), at=int(state.get("time", 0)))
        if verdict != "leg verifies":
            return verdict
        return self.cap_fault(state["beat"], index, sub) or self.taker_fault(state["beat"], index, sub) \
            or verdict

    def fill_fault(self, beat: int, index: int, sub: Submission) -> str | None:
        """Why beat `beat`'s committed fills are not leg `index`'s — the want
        filled whole against a cap of 1/1, each give by the quantity the leg
        takes — in the contract's words, or None. `sub` is the submission
        rebuilt from the record."""
        committed = self._committed(beat)
        want, gives, taken, _under = sub.legs[index]
        if committed.get(want[0].hex()) != (1, 1):
            return "the want's fill is not whole"
        for g, t in zip(gives, taken):
            got = committed.get(g[0].hex())
            if got is None or got[0] != Fraction(*t):
                return "fill differs from leg"
        return None

    def cap_fault(self, beat: int, index: int, sub: Submission) -> str | None:
        """Why a cap beat `beat` committed for leg `index`'s gives is not the
        give's quantity (the rebuilt submission's), or None."""
        committed = self._committed(beat)
        truth = {f[0].hex(): Fraction(f[3], f[4]) for f in sub.fills}
        for g in sub.legs[index][1]:
            got = committed.get(g[0].hex())
            if got is None or got[1] != truth[g[0].hex()]:
                return "a cap is not its give's quantity"
        return None

    def taker_fault(self, beat: int, index: int, sub: Submission) -> str | None:
        """Why a committed give fill of leg `index` does not name the leg's
        wanter as its taker, or None."""
        committed = self.pending_takers(beat)
        truth = {f[0].hex(): f[5] for f in sub.fills}
        for g in sub.legs[index][1]:
            if committed.get(g[0].hex()) != truth[g[0].hex()]:
                return "a fill's taker is not the leg's wanter"
        return None

    def _committed(self, beat: int) -> dict:
        committed: dict = {}
        for oid, taken, cap in self.pending_fills(beat):
            committed.setdefault(oid, (taken, cap))          # the first, as the contract reads
        return committed

    def verdict_of(self, sub: Submission, index: int, *, pins=None, holds=None, claims=None, at: int = 0,
                   gas: int = 12_000_000) -> str | None:
        """What the contract's verifier says about leg `index` of a
        submission, without a transaction: `verifyLegExternal` run through
        `eth_call` with the contract itself as sender (the only sender it
        accepts), against the chain's current fills, under `pins` (the
        submission's own by default — so a submitter asks *before* paying a
        bond, and a challenger asks under the beat's), with the holds and
        claims given (the submission's; a challenger passes the beat's
        committed ones) at time `at` (0: the chain's now; a challenger: the
        beat's own clock). "leg verifies", or
        the revert reason — the same string a challenge would put in its
        event; None when the node would not run the call (never a
        conviction)."""
        c = self.contract()
        pins = sub.pins if pins is None else pins
        fn = c.functions.verifyLegExternal(pins, list(sub.registers), sub.legs[index], sub.statements[index],
                                           sub.makers, sub.potentials,
                                           list(sub.holds if holds is None else holds),
                                           list(sub.claims if claims is None else claims), index, at)
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
                # a revert with a reason is the verifier's; one without (the
                # gas the call could afford ran out, 2026-09-29: an option
                # leg verifies in ~11 M) is no verdict, like a refused call
                if _is_revert(exc) and _revert_reason(exc):
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
    if text in ("b''", 'b""', "0x"):
        return ""
    return text.strip("'\" ") or "leg fails: reverted without a reason"
