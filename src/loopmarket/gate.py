"""The counterparty gate (R4, 2026-09-29; `docs/plans/counterparty-gate.md`
§4): a maker's `requires.counterparty` credentials checked against the
statements the other side of the leg presented in its book (`cred/`, R2),
read under the registers the proposal pinned (`register_roots`, R3a), at
the leg's handover window.

For each credential entry, the counterparty must hold a statement that
passes all seven steps:

1. **category** below the entry's (the catalogue decides, one-way) and
   **kind** among the entry's kinds;
2. a **path** from its issuer through `accredit/` records — each hop's
   register accrediting the one below for a category above the
   statement's, valid through the window — to a trust root the entry
   names, with **every register on the path pinned** (an unpinned one
   fails closed; nothing is fetched);
3. **not revoked** under the issuer's pinned root (an absence proof);
4. every register on the path **fresh**: its root's heartbeat no older
   than `max_root_age` against the clock;
5. **valid** (`as_of` .. `until`) through the leg's handover window — a
   licence expiring before the appointment meets nothing;
6. when the statement names a **deposit**: what is free of it after this
   fill's reservation, counted up to what the escrow holds, covers
   `min_bond` at the requirer's price for the deposit's asset;
7. **not suspended** under the issuer's pinned root (D2).

A self-bonded statement is its subject's own: it has no issuer register,
so steps 2–4 and 7 apply only as far as the entry names roots, and its
deposit is what backs it. Any step unprovable fails the statement (U7).
Why every failing step is returned rather than the first (plan E4): most
first presentations fail on formalities, and one refusal listing every
discrepancy lets a re-presentation cure in one round (UCP's rule).

Pure (B1): the gate reads statements, registers and holdings handed to it,
never a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable, Iterable, Mapping

from .ontology import Ontology
from .schema import GIVE, Credential, Offer, Statement, q

Window = tuple[int, int]


@dataclass(frozen=True)
class CounterpartyGate:
    """What the gate reads beyond the two offers: the statements presented
    about a key (`statements(subject)`), the registers at their pinned roots
    (`registers`: id -> `Register`), the clock, how to read a handover
    window from a `time(...)` term's text (`span`), the offers a statement's
    deposit may name (`offer(id)`), and what the escrow holds behind a
    deposit (`held`: offer id -> quantity in the asset's unit)."""

    statements: Callable[[str], Iterable[Statement]]
    registers: Mapping[str, object]
    now: int
    span: Callable[[str], Window] | None = None
    offer: Callable[[str], Offer | None] = field(default=lambda oid: None)
    held: Mapping[str, Fraction] | None = None
    # options (C2, 2026-09-29; options-and-cover.md §3): what a holder may
    # take of an offer by exercising now, what is left of an offer after
    # fills and active holds, whether it was withdrawn
    held_by: Callable[[str, str], Fraction] = field(default=lambda oid, holder: Fraction(0))
    capacity: Callable[[str], Fraction | None] = field(default=lambda oid: None)
    withdrawn: Callable[[str], bool] = field(default=lambda oid: False)
    # items (I2): does a maker hold an active claim on an item through another offer?
    item_claimed: Callable[[str, str, str], bool] = field(default=lambda h, maker, oid: False)
    # R5 (2026-09-29): register id -> the register at the newest root it has
    # published (its feed's tip), or None; no reader: the pinned root's age alone
    latest: Callable[[str], object | None] | None = None

    @classmethod
    def over(cls, book, registers: Mapping[str, object], *, now: int, span=None, held=None,
             capacity=None, latest=None) -> "CounterpartyGate":
        """The gate over an offer book's presented statements, offers and
        holds; `capacity` (offer id -> what is left) defaults to the book's."""
        def statements(subject: str):
            return [s for s, _ in book.statements(subject)]

        def offer(oid: str):
            try:
                return book.get(oid)
            except KeyError:
                return None

        def left(oid: str):
            try:
                return book.available(oid, now)
            except KeyError:
                return None
        return cls(statements, dict(registers), int(now), span, offer, held,
                   lambda oid, holder: book.held_by(oid, holder, now), capacity or left, book.is_withdrawn,
                   lambda h, maker, oid: book.item_claimed(h, maker, now, offer_id=oid), latest)

    # -- items ---------------------------------------------------------------------

    def item_fault(self, give: Offer) -> str:
        """Why a leg on `give` would break the per-item rule, or "" (I2): its
        maker already holds an active claim on an item it names through
        another offer. An option's items are its underlying's."""
        from .items import ids
        subject = give
        if give.v >= 6 and give.underlying:
            subject = self.offer(give.underlying) or give
        for h in ids(subject.thing.concepts):
            if self.item_claimed(h, give.maker, subject.offer_id):
                return f"{give.maker} already holds an open claim on item {h[:12]}"
        return ""

    # -- options ------------------------------------------------------------------

    def option_fault(self, option: Offer) -> str:
        """Why an option give cannot clear now, or "" (§3.4): its underlying
        is in the book, made by the option's own writer, not withdrawn,
        valid through the exercise window, in the option's unit, and has the
        held quantity free after fills and active holds."""
        p = self.offer(option.underlying)
        if p is None:
            return "option on an offer not in the book"
        if p.maker != option.maker:
            return "option by another maker than its underlying's"
        if self.withdrawn(p.offer_id):
            return "the underlying is withdrawn"
        if p.kind != GIVE:
            return "an option holds a give: its underlying is a want"
        if not p.valid.contains(option.exercise):
            return "the underlying is not valid through the exercise window"
        if option.thing.unit != p.thing.unit:
            return "the option's unit is not its underlying's"
        left = self.capacity(p.offer_id)
        if left is None or left < q(option.thing.qty):
            return "no free capacity on the underlying for the hold"
        return ""

    @property
    def roots(self) -> tuple[tuple[str, str], ...]:
        """The (register id, root) pins of every register this gate reads —
        what a proposal through it pins as `register_roots`."""
        return tuple(sorted((rid, reg.root) for rid, reg in self.registers.items() if reg.root))

    # -- the leg's window -----------------------------------------------------------

    def window(self, want: Offer) -> Window:
        """The handover window: the want's first `time(...)` term read by
        `span`, else the clock's instant."""
        if self.span is not None:
            concepts = [c for p in want.parts for c in p.concepts]
            for term in concepts:
                if isinstance(term, str) and term.startswith("time(") and term.endswith(")"):
                    try:
                        start, end = self.span(term[5:-1])
                        return int(start), int(end)
                    except Exception:           # noqa: BLE001 — not a span this reader knows
                        continue
        return self.now, self.now

    # -- the check ----------------------------------------------------------------

    def faults(self, requirer: Offer, counterparty: Offer, ontology: Ontology, *, window: Window,
               taken=None, whole=None) -> list[str]:
        """Every failing step of `requirer`'s credential entries against
        `counterparty`'s presented statements; [] when every entry is met.
        One line per entry: the entry, then the faults of the presented
        statement that came closest (fewest faults), or that none was
        presented."""
        out = []
        for entry in requirer.requires.counterparty:
            best = None
            for s in self.statements(counterparty.maker):
                f = self.statement_faults(entry, s, requirer, counterparty, ontology, window=window,
                                          taken=taken, whole=whole)
                if not f:
                    best = []
                    break
                if best is None or len(f) < len(best):
                    best = f
            if best is None:
                out.append(f"{entry.category}: no statement presented by {counterparty.maker}")
            elif best:
                out.append(f"{entry.category}: " + "; ".join(best))
        return out

    def chosen(self, entry: Credential, requirer: Offer, counterparty: Offer, ontology: Ontology, *,
               window: Window, taken=None, whole=None) -> Statement | None:
        """The statement that meets `entry` — the first presented one with no
        failing step, the one `faults` accepts — or None: what a beat's leg
        carries for the entry (R3b)."""
        for s in self.statements(counterparty.maker):
            if not self.statement_faults(entry, s, requirer, counterparty, ontology, window=window,
                                         taken=taken, whole=whole):
                return s
        return None

    def statement_faults(self, entry: Credential, s: Statement, requirer: Offer, counterparty: Offer,
                         ontology: Ontology, *, window: Window, taken=None, whole=None) -> list[str]:
        """The seven steps for one statement against one entry."""
        f: list[str] = []
        if s.subject != counterparty.maker:
            return [f"statement about {s.subject}, not {counterparty.maker}"]
        # 1. category and kind
        if not ontology.satisfies((s.category,), (entry.category,)):
            f.append(f"1 category {s.category} is not under {entry.category}")
        if s.kind not in entry.kinds:
            f.append(f"1 kind {s.kind} is not one of {', '.join(entry.kinds)}")
        # 2–4, 7. the path, its registers, their freshness; revocation and suspension
        self_bonded = s.kind == "self-bonded"
        if not (self_bonded and not entry.roots):
            f.extend(self._path_faults(entry, s, ontology, window, self_bonded))
        # 5. valid through the handover window
        if not (s.as_of <= window[0] and window[1] <= s.until):
            f.append(f"5 valid {s.as_of}..{s.until}, not through the window {window[0]}..{window[1]}")
        # 6. the deposit's free share covers the floor
        if s.deposit is not None and entry.min_bond:
            f.extend(self._deposit_faults(entry, s, requirer, counterparty, ontology, taken=taken, whole=whole))
        return f

    def _path_faults(self, entry: Credential, s: Statement, ontology: Ontology, window: Window,
                     self_bonded: bool) -> list[str]:
        f: list[str] = []
        path = s.path
        if path[-1] not in entry.roots:
            f.append(f"2 path ends at {path[-1]}, not a trust root named ({', '.join(entry.roots) or 'none'})")
        on_path = list(path[1:]) if self_bonded else list(path)    # the issuer's register holds the status
        unpinned = [r for r in on_path if r not in self.registers]
        for r in unpinned:
            f.append(f"2 register {r} on the path is not pinned")
        for below, above in zip(path, path[1:]):
            reg = self.registers.get(above)
            if reg is None:
                continue
            ok = any(ontology.satisfies((s.category,), (cat,)) and rec["since"] <= window[0]
                     and window[1] <= rec["until"] for cat, rec in reg.accreditations(below))
            if not ok:
                f.append(f"2 {below} is not accredited by {above} for {s.category} through the window")
        for r in on_path:
            reg = self.registers.get(r)
            if reg is None:
                continue
            at = reg.as_of
            if at is None:
                f.append(f"4 register {r} is silent (no heartbeat at its pinned root)")
            elif self.now - at > entry.max_root_age:
                f.append(f"4 register {r}'s root is {self.now - at}s old, more than {entry.max_root_age}s")
            # R5: the root keeps every revocation its predecessor held (a
            # root that cannot show it fails, U7) ...
            extended = reg.extends_predecessor()
            if extended is None:
                f.append(f"4 register {r}'s root cannot be checked against its predecessor")
            elif not extended:
                f.append(f"4 register {r}'s root drops a revocation its predecessor held")
            # ... and a newer root published by this clearing's clock extends it
            newest = self._newest(r, reg)
            if newest is not None and newest.extends(reg.root) is False:
                f.append(f"4 register {r}'s newest root drops a revocation the pinned root holds")
        issuer = None if self_bonded else self.registers.get(s.issuer)
        if issuer is not None:
            if issuer.revoked(s.statement_id):
                f.append(f"3 revoked under {s.issuer}'s pinned root")
            if issuer.suspended(s.statement_id):
                f.append(f"7 suspended under {s.issuer}'s pinned root")
            if issuer.status(s.statement_id) is None:
                f.append(f"3 {s.issuer}'s register has no status for the statement")
            # a stale pin must not hide what the register has said since
            newest = self._newest(s.issuer, issuer)
            if newest is not None:
                since = f"{s.issuer}'s newest root (published {newest.as_of}; the pinned root is stale)"
                if newest.revoked(s.statement_id) and not issuer.revoked(s.statement_id):
                    f.append(f"3 revoked under {since}")
                if newest.suspended(s.statement_id) and not issuer.suspended(s.statement_id):
                    f.append(f"7 suspended under {since}")
        return f

    def _newest(self, rid: str, pinned):
        """The register's newest root, when it differs from the pinned one and
        was published by this clearing's clock (a root with no heartbeat
        counts: an unstamped successor is not a later one); else None."""
        newest = self.latest(rid) if self.latest is not None else None
        if newest is None or newest.root == pinned.root:
            return None
        at = newest.as_of
        return newest if at is None or at <= self.now else None

    def _deposit_faults(self, entry: Credential, s: Statement, requirer: Offer, counterparty: Offer,
                        ontology: Ontology, *, taken=None, whole=None) -> list[str]:
        oid, escrow = s.deposit
        backing = self.offer(oid)
        bond = backing.bond if backing is not None and backing.v >= 5 else None
        if bond is None or bond.escrow.lower() != escrow.lower():
            return [f"6 the deposit {oid[:12]} is not a bond held by {escrow}"]
        qty = q(bond.asset.qty)
        if self.held is not None and bond.escrow:
            qty = min(qty, q(self.held.get(oid, 0)))
        if oid == counterparty.offer_id and taken is not None and q(whole or 0) > 0:
            qty -= bond.reserved(taken, whole)                   # after this fill's own reservation
        qty -= bond.deductible                                   # v7: what a claim on it cannot take
        req = requirer.requires
        for acc in req.accepts:
            if acc.unit == bond.asset.unit and ontology.satisfies(bond.asset.concepts, acc.concepts):
                need = entry.min_bond / acc.price
                if qty >= need:
                    return []
                return [f"6 {qty} {acc.unit} free of the deposit, less than {need} for the floor {entry.min_bond}"]
        return [f"6 no acceptance of {' '.join(bond.asset.concepts)} {bond.asset.unit} to price the floor"]
