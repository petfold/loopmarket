"""Clearing: where a proposed loop becomes a bundle of commitments.

Trust model (the one non-negotiable): clearing *never trusts the solver*.
A `LoopProposal` names the book root and ontology root it was solved
against; the clearing layer re-derives every leg with `check_match`, the
chaining, the product, and the not-already-filled status — cheap, linear in
the loop — before atomically marking every offer filled. Discovery is
expensive and competitive; verification is cheap and neutral.

`MockClearing` is the in-process stand-in: its "atomic stroke" is one
recordstore commit (all fills + the loop record land under a single new
root, or none do). The on-chain path it stands in for (roadmap P2) keeps
the same interface: a contract receives the loop plus *inclusion proofs*
that each offer is present under the pinned book root — recordstore's
canonical-trie `prove`/`verify_proof` (>= 0.16.0) is the primary route;
POT ForkPathProof is the conditional fallback only if the on-chain
verifier demands BMT-native proofs (docs/plans/proof-fabric.md). Batch
auctions across competing sealed proposals are P2 as well
(docs/plans/P2-batch-auction.md); the mock is first-valid-wins.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from typing import Protocol

from .graph import Circulation, Loop
from fractions import Fraction

from .schema import q, rat
from .matching import check_aggregate, check_composition, check_match, check_parts
from .ontology import Ontology
from .registry import OfferRegistry
from .register import named_registers
from .gate import CounterpartyGate
from . import items
from .schema import Offer


@dataclass(frozen=True, slots=True)
class LoopProposal:
    loop: Loop | Circulation
    book_root: str        # the registry version the loop was solved against
    ontology_root: str    # the catalogue version subsumption was checked under
    solver: str           # who found it (fee/reputation address)
    found_at: int
    # R3a (2026-09-29): the registers the proposal read statements' status
    # under, as sorted (register id, root) pairs — U4's pin for everything
    # the counterparty gate reads outside the book (counterparty-gate.md §3.3)
    register_roots: tuple = ()

    @property
    def circulation(self) -> Circulation:
        return self.loop if isinstance(self.loop, Circulation) \
            else Circulation.from_loop(self.loop)

    def to_record(self) -> dict:
        """The `loop/` record, version 1 (v4 day, 2026-09-14): every leg
        names its want, its gives and the quantity `taken` from each, in
        sorted leg order; a simple leg carries its exact rate; the record
        carries the node potentials — the clearing prices as the dual of
        §11, public while offers are plaintext (P4 §5 item 4, ruled
        2026-09-14) and outside `loop_id`, which hashes the legs alone. All
        numbers are `n/d` strings (U9). `give` is the first give, kept for
        readers of the 2026-08 shape."""
        circ = self.circulation
        legs = []
        for leg in sorted(circ.legs, key=lambda leg: leg.key):
            rec = {"give": leg.gives[0].offer_id,
                   "gives": [g.offer_id for g in leg.gives],
                   "taken": [rat(leg.taken(i)) for i in range(len(leg.gives))],
                   "want": leg.want.offer_id}
            if leg.simple and not leg.parts:
                rec["rate"] = rat(leg.want.unit_price / leg.gives[0].unit_price)
            legs.append(rec)
        rec = {
            "v": 2 if self.register_roots else 1,
            "loop_id": circ.loop_id,
            "solver": self.solver,
            "found_at": self.found_at,
            "book_root": self.book_root,
            "ontology_root": self.ontology_root,
            "surplus": rat(circ.surplus),
            "nodes": list(circ.nodes),
            "legs": legs,
            "potentials": {m: rat(e) for m, e in sorted(circ.potentials().items())},
        }
        if self.register_roots:
            # loop record v2 (R3a): the register pins; a proposal with none
            # writes v1, byte for byte as before
            rec["register_roots"] = {r: root for r, root in sorted(self.register_roots)}
        return rec

    def fills(self) -> dict[str, dict]:
        """The `fill/` records, keyed under `fill/`: a want's, `<offer>`,
        names the loop and every give that served it with its quantity; a
        give taken whole, `<offer>`, the loop and the quantity; a give taken
        in part — a divisible give with a remainder — `<offer>/<loop>`, so
        several loops may each take their share and the sum is checked at
        the fold (U11). Nothing else, ever (P4 §5 item 4: no prices in fills)."""
        circ = self.circulation
        out: dict[str, dict] = {}
        for leg in circ.legs:
            out[leg.want.offer_id] = {
                "loop": circ.loop_id,
                "gives": [{"offer": g.offer_id, "qty": rat(leg.taken(i))}
                          for i, g in enumerate(leg.gives)]}
            for i, g in enumerate(leg.gives):
                taken = leg.taken(i)
                key = g.offer_id if taken == q(g.thing.qty) else f"{g.offer_id}/{circ.loop_id}"
                out[key] = {"loop": circ.loop_id, "qty": rat(taken)}
        return out


@dataclass(frozen=True, slots=True)
class Receipt:
    accepted: bool
    loop_id: str
    reason: str = ""
    book_root: str = ""   # the new root, if accepted


class Clearing(Protocol):
    def submit(self, proposal: LoopProposal) -> Receipt: ...


class MockClearing:
    """In-process clearing over the shared registry."""

    #: Oracle types this clearing knows how to verify — the P3 refusal
    #: gate (docs/plans/P3-guarantee-coupling.md, enforcement rule 1): a leg
    #: naming a witness type outside this set never clears here, in U7's
    #: shape — unknown fails closed rather than silently clearing with a
    #: guarantee nobody can check. The mock declares the P0 countersign
    #: semantics and, since R7 (2026-09-29), the door's two witness types,
    #: whose settlement check is `witness.countersign_ready`.
    VERIFIABLE_ORACLES = frozenset({"countersign", "possession", "photo-match"})

    def __init__(self, registry: OfferRegistry, ontology: Ontology, *,
                 min_surplus: float = 0.0, require_per_node: bool = True,
                 clock=_time.time, verifiable_oracles=VERIFIABLE_ORACLES,
                 chain_fills=None, escrow_held=None, register_at=None, span=None, register_latest=None):
        self.registry = registry
        self.ontology = ontology
        self.min_surplus = min_surplus
        self.require_per_node = require_per_node
        self.clock = clock  # injectable for tests / deterministic replay
        self.verifiable_oracles = frozenset(verifiable_oracles)
        #: offer id -> quantity the chain has recorded as taken (`BeatClearing.
        #: filled`), or None. The chain is the fill authority once a beat is
        #: finalized, and a book that never folded that clearing's fills does
        #: not know (live 2026-09-18: a fold of twelve offers, six spent on chain,
        #: proposed a loop through a spent one) — so what the chain has taken is
        #: subtracted from what the book says is left, everywhere the checklist
        #: asks.
        self.chain_fills = chain_fills
        #: offer id -> quantity the escrow contract holds behind it, in the
        #: asset's unit (`EscrowClient.held` scaled), or None: with it, a
        #: deposit that names an escrow counts only up to what is held
        #: (`matching.meets`, 2026-09-19) — the chain is the authority on
        #: the deposit as on the fills.
        self.escrow_held = escrow_held
        #: (register id, root) -> the `Register` read at that root, or None
        #: (R4, 2026-09-29): the counterparty gate re-reads every register
        #: the proposal pinned, here, never the solver's copy (U3); without
        #: it only a self-bonded statement can meet a credential.
        self.register_at = register_at
        #: a `time(...)` term's text -> (start, end), for the leg's handover
        #: window the gate checks validity through; None: the clock's instant
        self.span = span
        #: register id -> (root, published at) of its newest published root,
        #: read from its feed (R5): a pinned root a newer one precedes is
        #: refused; None: no feed reader, the heartbeat age bound alone
        self.register_latest = register_latest

    def gate(self, register_roots=(), *, now: int) -> CounterpartyGate:
        """The counterparty gate over this clearing's own book, the
        registers read at the pinned roots, what the escrow holds."""
        registers = {}
        if self.register_at is not None:
            for rid, root in register_roots:
                if root:
                    registers[rid] = self.register_at(rid, root)
        held = None if self.escrow_held is None else _Held(self.escrow_held)

        def capacity(oid: str):
            try:
                return self.available([oid], now)[oid]
            except KeyError:
                return None
        return CounterpartyGate.over(self.registry, registers, now=now, span=self.span, held=held,
                                     capacity=capacity, latest=self.register_latest)

    def deposits(self, offer_ids) -> dict | None:
        """What the escrow holds behind each offer, or None when no escrow
        is consulted (the declaration then stands, as before)."""
        if self.escrow_held is None:
            return None
        return {oid: q(self.escrow_held(oid)) for oid in offer_ids}

    def available(self, offer_ids, now: int | None = None) -> dict:
        """What may still be taken from each offer: the book's remainder,
        less what the chain has recorded (a composed want is whole or gone),
        and, given `now`, less what active holds keep (C2) — a holder's own
        exercise adds its hold back at the gate."""
        out = {}
        for oid in offer_ids:
            left = self.registry.available(oid)
            if self.chain_fills is not None:
                offer = self.registry.get(oid)
                on_chain = q(self.chain_fills(oid))
                if offer.composed:
                    left = Fraction(0) if on_chain > 0 else left
                else:
                    left = min(left, q(offer.thing.qty) - on_chain)
            if now is not None:
                left -= self.registry.held(oid, now)
            out[oid] = left
        return out

    def filled_on_chain(self, offer) -> bool:
        """Has the chain recorded this offer as taken whole, or down to dust?"""
        if self.chain_fills is None:
            return False
        on_chain = q(self.chain_fills(offer.offer_id))
        if offer.composed:
            return on_chain > 0
        return offer.thing.exhausted(q(offer.thing.qty) - on_chain)

    def submit(self, proposal: LoopProposal) -> Receipt:
        loop = proposal.circulation
        lid = loop.loop_id
        now = int(self.clock())

        def reject(reason: str) -> Receipt:
            return Receipt(False, lid, reason)

        # 0. pins — the rehearsal of U10's clearing half (full enforcement,
        #    with proofs, lands with P2): the proposal's catalogue pin must
        #    *equal* this clearing's own, refused before any leg work.
        #    Plain equality covers mismatch and absence in both directions:
        #    a pinned clearing refuses unpinned proposals, an unpinned
        #    (development) one refuses proposals claiming ground it cannot
        #    confirm; '' == '' keeps the in-memory flow working.
        if proposal.ontology_root != self.ontology.root:
            return reject("ontology pin mismatch")
        #    and every register a leg's requirement names as a trust root is
        #    pinned (R3a): a statement's status is read under a root the
        #    proposal fixed, never a live lookup, or not at all (U4, U7)
        pinned = dict(proposal.register_roots)
        for name in sorted(named_registers(leg.want for leg in loop.legs)
                           | named_registers(g for leg in loop.legs for g in leg.gives)):
            if not pinned.get(name):
                return reject(f"unpinned register: {name}")

        # 1. every offer must exist in the *current* book, be unfilled, and
        #    name a witness type this clearing can actually verify
        seen: set[str] = set()
        for oid in loop.offer_ids:
            if oid in seen:
                return reject(f"offer used twice: {oid[:12]}")
            seen.add(oid)
            try:
                offer = self.registry.get(oid)
            except KeyError:
                return reject(f"unknown offer: {oid[:12]}")
            if self.registry.is_filled(oid):
                return reject(f"already filled: {oid[:12]}")
            if self.filled_on_chain(offer):
                return reject(f"filled on chain: {oid[:12]}")
            if self.registry.is_withdrawn(oid):
                return reject(f"withdrawn: {oid[:12]}")
            if offer.oracle not in self.verifiable_oracles:
                return reject(f"unverifiable oracle type: {offer.oracle}")

        # 2. re-derive every leg — never trust the solver's matches; a
        #    composed leg is re-composed (`check_composition`) from the
        #    current book, operators included, against what fills have
        #    left of every give (a partial fill's remainder)
        available = self.available(loop.offer_ids, now)
        gate = self.gate(proposal.register_roots, now=now)
        for leg in loop.legs:
            reason = self.verify_leg(leg, now=now, available=available, gate=gate)
            if reason:
                return reject(reason)

        # 3. the arithmetic: potentials exist (a simple cycle: product > 1)
        #    with the required uniform gain, and the indivisible gate
        if not loop.feasible:
            return reject("no node potentials: the legs do not balance")
        if loop.surplus < self.min_surplus:
            return reject(f"surplus {float(loop.surplus):.4f} below minimum")
        if self.require_per_node and not loop.all_divisible \
                and not loop.per_node_ok:
            return reject("indivisible legs without per-node surplus")

        # 4. atomic commitment: all fills land under one new root, or none —
        #    with the holds an option leg writes and the exercises that
        #    consume them (C2), in the same commit
        self.registry.mark_filled(proposal.fills(), lid, proposal.to_record(),
                                  extra=self.hold_records(loop, lid, now))
        root = self.registry.commit()
        return Receipt(True, lid, book_root=root)

    def verify_leg(self, leg, *, now: int, available: dict, held: dict | None = None,
                   gate: CounterpartyGate | None = None) -> str | None:
        """Re-derive one leg from this clearing's book and ontology — the
        exact check for its shape: `check_aggregate` for explicit shares,
        `check_parts` for a composed want, `check_match` for one give,
        `check_composition` for a thing moved by operators — against what
        `available` says fills have left of each give, and `held` (the
        escrow's holdings, this clearing's own when not given) says of each
        deposit. None when the leg
        holds, else the reason. The unit of U3, and of a challenger's
        re-derivation (beat.py): the same code that cleared a leg is what
        convicts it."""
        if held is None:
            held = self.deposits(leg.offer_ids)
        if gate is None:
            gate = self.gate(now=now)
        fresh_want = self.registry.get(leg.want.offer_id)
        fresh_gives = [self.registry.get(g.offer_id) for g in leg.gives]
        if leg.quantities is not None:
            ok = check_aggregate(fresh_want, fresh_gives, leg.quantities, self.ontology,
                                 now=now, available=available, held=held, gate=gate)
        elif fresh_want.composed:
            ok = check_parts(fresh_want, fresh_gives, self.ontology, now=now,
                             available=available, held=held, gate=gate)
        elif leg.simple:
            ok = check_match(fresh_gives[0], fresh_want, self.ontology, now=now,
                             available=available, held=held, gate=gate)
        else:
            ok = check_composition(fresh_want, fresh_gives, self.ontology, now=now,
                                   available=available, held=held, gate=gate)
        if ok is None:
            reason = (f"leg fails re-verification: "
                      f"{'+'.join(g.offer_id[:8] for g in leg.gives)}"
                      f" -> {leg.want.offer_id[:8]}")
            faults = self.gate_faults(fresh_want, fresh_gives, gate)
            return reason + (" — the counterparty gate: " + " | ".join(faults) if faults else "")
        return None

    def hold_records(self, loop, lid: str, now: int) -> dict:
        """The `option/` records an option leg writes — a hold on its
        underlying for the leg's wanter until the exercise window ends, of
        what the leg took — and the `exercise/` records a holder's leg on a
        held offer writes (options-and-cover.md §3.2, §3.5)."""
        out: dict = {}
        for leg in loop.legs:
            for i, g in enumerate(leg.gives):
                taken = leg.taken(i)
                if g.v >= 6 and g.underlying:
                    until = int(g.exercise.end)
                    out[f"option/{g.underlying}/{lid}"] = {
                        "option": g.offer_id, "holder": leg.want.maker, "until": until, "qty": rat(taken)}
                    subject = self.registry.get(g.underlying)
                else:
                    if self.registry.held_by(g.offer_id, leg.want.maker, now) > 0:
                        out.update(self.registry.exercise_records(g.offer_id, leg.want.maker, taken, now, lid))
                    subject = g
                    until = self._claim_until(leg.want, g, now)
                # the per-item rule (I2): the maker's claim on each item the
                # fill or the hold is about, until the handover or the window
                for h in items.ids(subject.thing.concepts):
                    out[f"item/{h}/{g.maker}/{lid}"] = {"offer": subject.offer_id, "until": until}
        return out

    def _claim_until(self, want: Offer, give: Offer, now: int) -> int:
        """When a fill's item claim ends: the leg's handover window (the
        want's `time(...)` term), else the give's own validity — an item
        sold is spoken for until it changes hands. Performance recorded
        earlier (a countersign) would end it sooner; the book has no such
        record yet."""
        _start, end = CounterpartyGate.over(self.registry, {}, now=now, span=self.span).window(want)
        if end > now:
            return end
        return int(give.valid.end) if give.valid.end is not None else 2 ** 62

    def gate_faults(self, want: Offer, gives, gate: CounterpartyGate) -> list[str]:
        """Every failing step of either side's credential requirement on a
        leg (plan E4: one refusal listing every discrepancy, so a
        re-presentation cures in one round)."""
        window = gate.window(want)
        out = []
        for give in gives:
            for mine, other in ((want, give), (give, want)):
                if mine.requires is not None and mine.requires.counterparty:
                    taken = q(want.thing.qty) if other is give and not want.composed else None
                    whole = q(give.thing.qty) if other is give else None
                    out += [f"{mine.maker} of {other.maker}: {f}"
                            for f in gate.faults(mine, other, self.ontology, window=window,
                                                 taken=taken, whole=whole)]
        return out

    def rehearse(self, proposal: LoopProposal) -> Receipt:
        """The whole checklist, nothing committed: the verdict a proposal
        would get here. `ChainClearing` runs it before posting a beat; a
        challenger runs it against the beat's snapshot."""
        dry = MockClearing(_Dry(self.registry), self.ontology, min_surplus=self.min_surplus,
                           require_per_node=self.require_per_node, clock=self.clock,
                           verifiable_oracles=self.verifiable_oracles, chain_fills=self.chain_fills,
                           escrow_held=self.escrow_held, register_at=self.register_at, span=self.span,
                           register_latest=self.register_latest)
        return dry.submit(proposal)


class ChainClearing(MockClearing):
    """`MockClearing` whose accepted proposals are also posted as beats on
    `BeatClearing` (P2, 2026-09-15). The book is the data — the loop record
    and the fills land in this clearing's own book exactly as before, after
    the full U3 re-derivation — and the chain holds the commitments and,
    once the window closes and someone finalizes, the fills. A proposal the
    local re-derivation rejects never reaches the chain; one the chain
    refuses (a bond short, a node down) is rejected here too, so the book
    and the chain never disagree about what was cleared. The receipt's
    `reason` carries the beat id on acceptance."""

    def __init__(self, registry, ontology, *, beat_client, snapshot_of=None, **kw):
        kw.setdefault("chain_fills", beat_client.filled)     # the chain is the fill authority
        super().__init__(registry, ontology, **kw)
        self.beat_client = beat_client
        self.snapshot_of = snapshot_of or (lambda root: OfferRegistry(
            type(registry.store).at(root, registry.store.blobs)))
        self.beats: dict[str, int] = {}

    def submit(self, proposal: LoopProposal) -> Receipt:
        from .beat import submission
        lid = proposal.circulation.loop_id
        now = self.clock()
        try:
            snapshot = self.snapshot_of(proposal.book_root)
            # the holds and item claims this clearing would write, and the
            # statements the gate accepts over the pinned snapshot (C4, I3, R3b)
            records = self.hold_records(proposal.circulation, lid, now)
            gate = self.gate(proposal.register_roots, now=now)
            gate = CounterpartyGate.over(snapshot, gate.registers, now=now, span=self.span,
                                         held=gate.held, capacity=gate.capacity)
            sub = submission(proposal, snapshot, records=records, gate=gate, ontology=self.ontology)
        except Exception as exc:  # noqa: BLE001 — the proposal's evidence cannot be built
            return Receipt(False, lid, f"beat: {exc}")
        # the local checklist first, without committing
        verdict = self.rehearse(proposal)
        if not verdict.accepted:
            return verdict
        # then the contract's own verifier on every leg, for free (eth_call):
        # a beat it would convict is never posted — the bond would be anyone's.
        # Live 2026-09-18: a Swarm-addressed clearing book proves under BMT
        # roots the sha256 verifier cannot check ("node hash mismatch"), so
        # its honest beat was convictable; the BMT verifier is not built.
        for i in range(len(sub.legs)):
            reason = self.beat_client.verdict_of(sub, i)
            if reason not in (None, "leg verifies"):
                hint = " (a Swarm-addressed book: the contract verifies sha256 roots)" \
                    if reason == "node hash mismatch" else ""
                return Receipt(False, lid, f"the contract would convict leg {i}: {reason}{hint}")
        try:
            beat, _receipt = self.beat_client.submit(sub)
        except Exception as exc:  # noqa: BLE001
            return Receipt(False, lid, f"beat refused: {exc}")
        receipt = super().submit(proposal)
        if receipt.accepted:
            self.beats[lid] = beat
            return Receipt(True, lid, f"beat {beat}", receipt.book_root)
        return receipt


class _Dry:
    """A registry that reads through and swallows writes: `MockClearing`'s
    checklist run to the end without committing anything."""

    def __init__(self, registry):
        self._r = registry

    def __getattr__(self, name):
        return getattr(self._r, name)

    def mark_filled(self, *a, **k):
        pass

    def commit(self, *a, **k):
        return self._r.store.root


class _Held:
    """The escrow's holdings as the mapping the gate reads, asked lazily
    (a statement's deposit may be any offer in the book)."""

    def __init__(self, escrow_held) -> None:
        self._held = escrow_held

    def get(self, offer_id: str, default=0):
        return q(self._held(offer_id))
