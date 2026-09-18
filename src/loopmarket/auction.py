"""The sealed-proposal beat: what the solvers submit, what a proposal is
worth, which survive, which win (P2, `docs/plans/P2-batch-auction.md`
§2–§6; built 2026-09-18).

The shape. Beats have a fixed cadence on `SealedBeat` (contracts/): in a
beat's commit phase every solver posts one commitment — keccak256 of its
proposal bytes and a salt — and in the reveal phase opens it; the bytes
are emitted, so the revealed set is the chain's, the same for every
reader. A proposal is a *bundle*: the loop records (`LoopProposal.
to_record`) of the offer-disjoint loops the solver would clear, all
pinning one book root. After the beat closes anyone derives the outcome:

  1. every revealed loop is re-derived against the beat's snapshot with
     the clearing checklist (U3) — the solver is not trusted here either;
  2. the deterministic baseline's loops on the same snapshot enter as the
     reserve bid (§8: a ring never wins with less than the free solution);
  3. the fairness filter (§5, CIP-67 generalized to cycles): an offer's
     reference outcome is the best gain any candidate through it offers —
     the baseline's included — and a loop giving some member less than its
     reference is discarded, so a loop wins only if every member does at
     least as well as it could elsewhere this beat;
  4. selection (§6): offer-disjoint packing maximising the numeraire-free
     score, the product of (1 + gain) over the winning loops — Σ log
     surplus, dimensionless, invariant to any maker's unit (U14) — exact
     over subsets while the survivors are few, greedy by gain otherwise;
     ties break by loop_id then proposal hash, so every replica lands on
     the same winners (U6 extended to the beat).

The winners go to `BeatClearing` loop by loop through `ChainClearing`
(each independently verified, offer-disjoint so never conflicting) and
the submitter records the outcome on `SealedBeat` — the hash of the
revealed set it read and of the winners — so a different derivation is a
visible dispute. The measure of "what an offer gets" is today's clearing
rule — the loop's uniform per-leg gain (`Circulation.surplus`) — until
`P2-clearing-pricing.md`'s split is the rule in force.

Sealing is a protocol with the commit-reveal fallback built (`seal`,
`SealedBeatClient`, `MemorySealedBeat`); Shutter threshold encryption,
the plan's primary, replaces the commitment with an encrypt-to-epoch and
the reveal with the epoch's key behind the same phases, and is not built.
Web3 loads lazily behind the `chain` extra (boundary B2).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations

from .beat import proposal_from_record
from .clearing import LoopProposal, MockClearing
from .registry import OfferRegistry
from .schema import q

try:
    from recordstore import canonical_bytes
except ImportError:  # pragma: no cover
    def canonical_bytes(value) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


COMMIT, REVEAL, CLOSED, PENDING = 0, 1, 2, 3
PHASES = {COMMIT: "commit", REVEAL: "reveal", CLOSED: "closed", PENDING: "pending"}
EXACT_UP_TO = 12       # survivors enumerated exhaustively up to this many


# --------------------------------------------------------------------------- #
# Sealing
# --------------------------------------------------------------------------- #

def bundle_bytes(proposals) -> bytes:
    """The bytes a solver seals: the canonical JSON of its loop records,
    in sorted loop order — the same bytes every reader rebuilds from."""
    records = sorted((p.to_record() for p in proposals), key=lambda r: r["loop_id"])
    return canonical_bytes({"v": 1, "proposals": records})


def seal(proposal_bytes: bytes, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """(commitment, salt): keccak256(proposal || salt), the salt fresh."""
    from eth_hash.auto import keccak
    salt = secrets.token_bytes(32) if salt is None else salt
    return keccak(proposal_bytes + salt), salt


def unbundle(proposal_bytes: bytes, snapshot: OfferRegistry) -> list[LoopProposal]:
    """The loop proposals a revealed bundle holds, rebuilt over the beat's
    snapshot. Raises on bytes that are not a bundle of this reader's version
    or name offers the snapshot lacks."""
    doc = json.loads(proposal_bytes.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("v") != 1 or not isinstance(doc.get("proposals"), list):
        raise ValueError("not a v1 proposal bundle")
    return [proposal_from_record(rec, snapshot) for rec in doc["proposals"]]


# --------------------------------------------------------------------------- #
# Worth, fairness, selection
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Candidate:
    proposal: LoopProposal
    solver: str                  # who revealed it ("baseline" for the reserve bid)
    source: bytes = b""          # the revealed bundle it came from (its hash breaks ties)

    @property
    def loop_id(self) -> str:
        return self.proposal.circulation.loop_id

    @property
    def gain(self) -> Fraction:
        """The uniform per-leg gain every member receives — what an offer
        gets from this loop under today's clearing rule."""
        return self.proposal.circulation.surplus

    @property
    def offers(self) -> frozenset:
        return frozenset(self.proposal.circulation.offer_ids)

    @property
    def key(self) -> tuple:
        """The deterministic order: by loop_id, then the bundle's hash."""
        from eth_hash.auto import keccak
        return (self.loop_id, keccak(self.source).hex() if self.source else "")


def score(candidates) -> Fraction:
    """The numeraire-free score of an outcome (U14): Π (1 + gain) over its
    loops — Σ log surplus in exact arithmetic, compared as a rational."""
    total = Fraction(1)
    for c in candidates:
        total *= 1 + c.gain
    return total


def references(candidates) -> dict[str, Fraction]:
    """Each offer's reference outcome: the best gain any candidate through
    it offers — the reserve bid among them (§5)."""
    best: dict[str, Fraction] = {}
    for c in candidates:
        for oid in c.offers:
            if oid not in best or c.gain > best[oid]:
                best[oid] = c.gain
    return best


def fairness_filter(candidates) -> tuple[list[Candidate], dict[str, str]]:
    """Discard every candidate that gives some member less than that
    member's reference (§5). Returns (survivors, {loop_id: reason})."""
    ref = references(candidates)
    survivors, dropped = [], {}
    for c in candidates:
        worse = [oid for oid in c.offers if c.gain < ref[oid]]
        if worse:
            dropped[c.loop_id] = (f"offer {worse[0][:12]} does better elsewhere this beat "
                                  f"({float(ref[worse[0]]):.4f} > {float(c.gain):.4f})")
        else:
            survivors.append(c)
    return survivors, dropped


def select(survivors) -> list[Candidate]:
    """The offer-disjoint set of survivors with the highest score (§6):
    every subset while there are at most EXACT_UP_TO survivors, greedy by
    gain beyond that; ties by the candidates' keys. Deterministic."""
    ordered = sorted(survivors, key=lambda c: c.key)
    if len(ordered) <= EXACT_UP_TO:
        best, best_score, best_keys = [], Fraction(0), None
        for r in range(1, len(ordered) + 1):
            for combo in combinations(ordered, r):
                seen: set = set()
                ok = True
                for c in combo:
                    if seen & c.offers:
                        ok = False; break
                    seen |= c.offers
                if not ok:
                    continue
                s = score(combo)
                keys = tuple(c.key for c in combo)
                if s > best_score or (s == best_score and (best_keys is None or keys < best_keys)):
                    best, best_score, best_keys = list(combo), s, keys
        return best
    chosen, taken = [], set()
    for c in sorted(ordered, key=lambda c: (-c.gain, c.key)):
        if not (taken & c.offers):
            chosen.append(c); taken |= c.offers
    return sorted(chosen, key=lambda c: c.key)


# --------------------------------------------------------------------------- #
# The outcome of a beat
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Outcome:
    beat: int
    book_root: str
    revealed_set: bytes                       # keccak over the revealed bundles, sorted by solver
    winners: list                             # Candidates, in selection order
    rejected: dict = field(default_factory=dict)   # loop_id (or solver) -> why it never became a candidate
    dropped: dict = field(default_factory=dict)    # loop_id -> the fairness filter's reason
    candidates: int = 0

    @property
    def winners_hash(self) -> bytes:
        from eth_hash.auto import keccak
        return keccak("|".join(c.loop_id for c in self.winners).encode())

    @property
    def score(self) -> Fraction:
        return score(self.winners)


def revealed_set_hash(revealed) -> bytes:
    """keccak over (solver, proposal bytes) sorted by solver — the set every
    reader of the chain agrees on."""
    from eth_hash.auto import keccak
    h = keccak(b"")
    for solver, data in sorted(revealed, key=lambda r: r[0].lower()):
        h = keccak(h + solver.lower().encode() + keccak(data))
    return h


def outcome(beat: int, revealed, snapshot: OfferRegistry, ontology, *, now: int,
            baseline=None, min_surplus=0, chain_fills=None) -> Outcome:
    """Derive a closed beat's outcome from `revealed` ([(solver, bytes)]) over
    the beat's snapshot: rebuild and re-derive every loop (U3, the chain's
    fills subtracted when `chain_fills` answers them), add the baseline's
    loops as the reserve bid, filter, select."""
    root = snapshot.store.root
    clearing = MockClearing(snapshot, ontology, min_surplus=min_surplus, clock=lambda: now,
                            chain_fills=chain_fills)
    candidates, rejected = [], {}
    for solver, data in sorted(revealed, key=lambda r: r[0].lower()):
        try:
            proposals = unbundle(data, snapshot)
        except Exception as exc:              # noqa: BLE001 — a bundle this reader cannot read
            rejected[solver] = f"unreadable bundle: {exc}"
            continue
        for p in proposals:
            if p.book_root != root:
                rejected[p.circulation.loop_id] = f"solved against root {p.book_root[:12]}, not the beat's"
                continue
            verdict = clearing.rehearse(p)
            if not verdict.accepted:
                rejected[p.circulation.loop_id] = verdict.reason
                continue
            candidates.append(Candidate(p, solver, data))
    for p in (baseline or []):
        if clearing.rehearse(p).accepted:
            candidates.append(Candidate(p, "baseline"))
    # one entry per loop: the same loop revealed by two solvers is one candidate
    # (first key wins), and a solver's revealed loop outranks the reserve bid's copy
    # — the baseline claims only what nobody proposed
    unique: dict[str, Candidate] = {}
    for c in sorted(candidates, key=lambda c: (c.solver == "baseline", c.key)):
        unique.setdefault(c.loop_id, c)
    survivors, dropped = fairness_filter(list(unique.values()))
    winners = select(survivors)
    return Outcome(beat, root, revealed_set_hash(revealed), winners, rejected, dropped, len(unique))


def baseline_proposals(snapshot: OfferRegistry, ontology, *, now: int, solver="baseline",
                       min_surplus=0, chain_fills=None) -> list[LoopProposal]:
    """The deterministic baseline's loops on the snapshot — the reserve bid
    every replica can compute (U6) — past what the chain has filled."""
    from .solver.agent import SolverAgent
    agent = SolverAgent(snapshot, ontology, clearing=None, solver_id=solver, min_surplus=min_surplus,
                        chain_fills=chain_fills)
    root, loops = agent.find_loops(now=now)
    return [LoopProposal(loop, root, ontology.root, solver, now) for loop in loops]


# --------------------------------------------------------------------------- #
# The beat on chain, and in memory
# --------------------------------------------------------------------------- #

def abi() -> dict:
    """The compiled `SealedBeat` (solc 0.8.24, via IR, optimizer 200 runs),
    shipped as `loopmarket/contracts/SealedBeat.json` by `scripts/build_beat.py`."""
    from importlib import resources
    with resources.files("loopmarket").joinpath("contracts", "SealedBeat.json").open(
            encoding="utf-8") as fh:
        return json.load(fh)


class SealedBeatClient:
    """`SealedBeat` at `address` on the chain behind `rpc_url`; `key` signs
    (a solver's or a submitter's), reading needs none."""

    def __init__(self, rpc_url: str, address: str, *, key: str | None = None, client=None):
        self.rpc_url, self.address, self._key, self._client = rpc_url, address, key, client

    def _web3(self):
        if self._client is None:
            try:
                from web3 import Web3
            except ImportError as exc:
                raise RuntimeError("the sealed beat needs web3: pip install 'loopmarket[chain]'") from exc
            self._client = Web3(Web3.HTTPProvider(self.rpc_url))
        return self._client

    def contract(self):
        return self._web3().eth.contract(address=self.address, abi=abi()["abi"])

    @property
    def solver(self) -> str:
        """The address that signs: how the chain names this solver."""
        if not self._key:
            raise ValueError("a transaction needs a key (bee_signer)")
        return self._web3().eth.account.from_key(self._key).address

    def _send(self, fn):
        w3 = self._web3()
        account = w3.eth.account.from_key(self._key) if self._key else None
        if account is None:
            raise ValueError("a transaction needs a key (bee_signer)")
        tx = fn.build_transaction({"from": account.address,
                                   "nonce": w3.eth.get_transaction_count(account.address)})
        signed = account.sign_transaction(tx)
        return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    def current(self) -> int:
        return self.contract().functions.current().call()

    def phase(self, beat: int) -> int:
        return self.contract().functions.phase(beat).call()

    def window(self, beat: int) -> tuple[int, int, int]:
        return tuple(self.contract().functions.window(beat).call())

    def block(self) -> int:
        return self._web3().eth.block_number

    def commit(self, commitment: bytes) -> int:
        """Commit for the current beat; returns the beat."""
        c = self.contract()
        receipt = self._send(c.functions.commit(commitment))
        return c.events.Committed().process_receipt(receipt)[0]["args"]["beat"]

    def reveal(self, beat: int, proposal: bytes, salt: bytes) -> None:
        self._send(self.contract().functions.reveal(beat, proposal, salt))

    def committers(self, beat: int) -> list[str]:
        return list(self.contract().functions.committers(beat).call())

    def revealed(self, beat: int) -> list[tuple[str, bytes]]:
        """[(solver, proposal bytes)] from the beat's `Revealed` events."""
        c = self.contract()
        start = c.functions.window(beat).call()[0]
        logs = c.events.Revealed().get_logs(from_block=start, argument_filters={"beat": beat})
        return [(log["args"]["solver"], bytes(log["args"]["proposal"])) for log in logs]

    def record(self, beat: int, revealed_set: bytes, winners: bytes) -> None:
        self._send(self.contract().functions.record(beat, revealed_set, winners))

    def outcome(self, beat: int) -> dict | None:
        o = self.contract().functions.outcomes(beat).call()
        if int(o[0], 16) == 0:
            return None
        return {"submitter": o[0], "revealed_set": bytes(o[1]), "winners": bytes(o[2])}


class MemorySealedBeat:
    """The same protocol in memory, with an injectable block counter —
    for tests and for `auction memory:` sessions on one machine."""

    def __init__(self, period: int = 10, commit_blocks: int = 5, *, solver: str = "me"):
        self.period, self.commit_blocks, self.solver = period, commit_blocks, solver
        self._block = 0
        self._commitments: dict[tuple[int, str], bytes] = {}
        self._revealed: dict[int, list[tuple[str, bytes]]] = {}
        self._outcomes: dict[int, dict] = {}
        self.disputes: list[tuple[int, str, bytes, bytes]] = []

    def for_solver(self, name: str) -> "MemorySealedBeat":
        """The same beat as another solver sees it: shared state, its name."""
        return _SolverView(self, name)

    def mine(self, n: int = 1) -> None:
        self._block += n

    def block(self) -> int:
        return self._block

    def current(self) -> int:
        return self._block // self.period

    def window(self, beat: int) -> tuple[int, int, int]:
        start = beat * self.period
        return start, start + self.commit_blocks, start + self.period

    def phase(self, beat: int) -> int:
        start, commit_end, end = self.window(beat)
        if self._block < start:
            return PENDING
        if self._block < commit_end:
            return COMMIT
        return REVEAL if self._block < end else CLOSED

    def commit(self, commitment: bytes) -> int:
        beat = self.current()
        if self.phase(beat) != COMMIT:
            raise ValueError("not the commit phase")
        if (beat, self.solver) in self._commitments:
            raise ValueError("already committed this beat")
        self._commitments[(beat, self.solver)] = commitment
        return beat

    def reveal(self, beat: int, proposal: bytes, salt: bytes) -> None:
        from eth_hash.auto import keccak
        if self.phase(beat) != REVEAL:
            raise ValueError("not the reveal phase")
        sealed = self._commitments.get((beat, self.solver))
        if sealed is None:
            raise ValueError("nothing committed")
        if any(s == self.solver for s, _ in self._revealed.get(beat, [])):
            raise ValueError("already revealed")
        if keccak(proposal + salt) != sealed:
            raise ValueError("not the committed proposal")
        self._revealed.setdefault(beat, []).append((self.solver, proposal))

    def committers(self, beat: int) -> list[str]:
        return [s for (b, s) in self._commitments if b == beat]

    def revealed(self, beat: int) -> list[tuple[str, bytes]]:
        return list(self._revealed.get(beat, []))

    def record(self, beat: int, revealed_set: bytes, winners: bytes) -> None:
        if self.phase(beat) != CLOSED:
            raise ValueError("beat not closed")
        prior = self._outcomes.get(beat)
        if prior is None:
            self._outcomes[beat] = {"submitter": self.solver, "revealed_set": revealed_set,
                                    "winners": winners}
        elif (prior["revealed_set"], prior["winners"]) != (revealed_set, winners):
            self.disputes.append((beat, self.solver, revealed_set, winners))

    def outcome(self, beat: int) -> dict | None:
        return self._outcomes.get(beat)


class _SolverView:
    """`MemorySealedBeat` under another solver's name, sharing its state."""

    def __init__(self, beat: MemorySealedBeat, solver: str):
        self._beat, self.solver = beat, solver

    def __getattr__(self, name):
        attr = getattr(self._beat, name)
        if callable(attr) and name in ("commit", "reveal", "record"):
            def as_me(*a, **k):
                was, self._beat.solver = self._beat.solver, self.solver
                try:
                    return attr(*a, **k)
                finally:
                    self._beat.solver = was
            return as_me
        return attr


def open_sealed(spec: str, *, key: str | None = None, memory=None):
    """`chain:RPC_URL@CONTRACT`, or `memory:` (one in-process instance per
    session, passed in as `memory`)."""
    if spec.startswith("chain:"):
        rpc, _, address = spec[6:].rpartition("@")
        return SealedBeatClient(rpc, address, key=key)
    if spec.startswith("memory"):
        return memory if memory is not None else MemorySealedBeat()
    raise ValueError(f"{spec}: a sealed beat is chain:RPC_URL@CONTRACT or memory:")
