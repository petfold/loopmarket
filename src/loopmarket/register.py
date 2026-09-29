"""Registers: the status of statements, separately rooted and pinned (R3a,
2026-09-29; `docs/plans/counterparty-gate.md` §3.3).

A register is a recordstore keyspace owned by an issuer, an accreditor or
an insurer — its own book, announced under the `register` role, never
folded into the offer book:

    status/<statement id>     -> {"state": issued | suspended | revoked, "at": t}
    revoked/<statement id>    -> {"at": t}      the absence-proof set
    suspended/<statement id>  -> {"at": t}      in the view while suspended (D2)
    accredit/<issuer>/<category> -> {"by", "since", "until", "scheme"}

Why separately rooted: a statement's status changes without its subject
re-signing anything, and a requirer checks it against the register's own
root, pinned in the proposal (`register_roots`, U4) — so a register is read
as of one root, a revocation after that root is a later clearing's matter,
and absence (not revoked, not suspended) is a proof under the pinned root,
not a lookup against a live service. The gate that reads it is R4's; the
root's age and the consistency between roots are R5's; a register as a
transparency log (G1) is the view here plus that proof.

Pure over a duck-typed RecordStore, like the offer book (B1).
"""

from __future__ import annotations

ISSUED, SUSPENDED, REVOKED = "issued", "suspended", "revoked"
HEARTBEAT = "heartbeat"      # {"at": t}: when this root was published (R4's freshness)
CHAIN = "chain"              # {"prev", "seq"}: the root this one supersedes, and its number (R5)
STATUS = "status/"
REVOKED_KEYS = "revoked/"
SUSPENDED_KEYS = "suspended/"
ACCREDIT = "accredit/"
#: What a register may never drop from one root to the next: its revocations
#: (a suspension is lifted by `reinstate`, a status moves on; a revocation
#: stands forever). Each root must extend its predecessor on these (R5).
MONOTONE = (REVOKED_KEYS,)


class Register:
    """One register's keyspace over `store`."""

    def __init__(self, store) -> None:
        self.store = store

    @property
    def root(self) -> str:
        return self.store.root or ""

    def commit(self) -> str:
        """Commit what is staged, the new root naming the root it supersedes
        and its number in the register's sequence (R5, 2026-09-29) — so
        every root, heartbeat or not, is a link a reader can check against
        the one before (`extends_predecessor`). Nothing staged: the same
        root, no new link."""
        status = getattr(self.store, "status", None)
        if status is None or status()["staged"]:
            self.store.put(CHAIN, {"prev": self.store.root or None, "seq": self.seq + 1})
        return self.store.commit()

    # -- writes (the register's owner) -------------------------------------------

    def heartbeat(self, at: int) -> None:
        """Stamp the root about to be committed with its publication time:
        the root's age against a clearing's clock is what `max_root_age`
        bounds (counterparty-gate.md §5). A register heartbeats at least at
        its declared cadence; a silent one outruns strict requirers. That the
        pinned root is the *latest* as of t is the register's feed — its
        signed sequence of roots, which the gate's `latest` reads — and,
        where trusted time is needed, an anchor: not something a root can
        say about itself."""
        self.store.put(HEARTBEAT, {"at": int(at)})

    def _record(self, key: str) -> dict | None:
        return self.store.get(key) if self.store.contains(key) else None

    @property
    def as_of(self) -> int | None:
        """The heartbeat of the root this register is read at, or None."""
        beat = self._record(HEARTBEAT)
        return beat["at"] if beat is not None else None

    @property
    def predecessor(self) -> str | None:
        """The root this one superseded (None: the first root)."""
        link = self._record(CHAIN)
        return link["prev"] if link is not None else None

    @property
    def seq(self) -> int:
        """This root's number in the register's sequence (-1 before the first)."""
        link = self._record(CHAIN)
        return int(link["seq"]) if link is not None else -1

    def extends(self, base: str | None) -> bool | None:
        """Does this root keep every revocation `base` held (recordstore's
        extension check on `MONOTONE`)? None when it cannot be checked here —
        a recordstore without extension proofs, or `base`'s nodes out of
        reach — which a gate reads as failing (U7)."""
        if base is None:
            return True
        check = getattr(self.store, "extends", None)
        if check is None:
            return None
        try:
            return bool(check(base, list(MONOTONE)))
        except Exception:  # noqa: BLE001 — unreachable nodes: not provable here
            return None

    def extends_predecessor(self) -> bool | None:
        """Does this root keep every revocation its predecessor held? True
        for a first root."""
        return self.extends(self.predecessor)

    def extension_proof(self) -> dict | None:
        """The self-contained proof that this root extends its predecessor on
        `MONOTONE` (recordstore's `verify_extension` checks it with no store),
        or None for a first root — what a register publishes beside its root
        for readers without its blobs."""
        prev = self.predecessor
        return None if prev is None else self.store.prove_extension(prev, list(MONOTONE))

    def issue(self, statement_id: str, at: int) -> None:
        self._state(statement_id, ISSUED, at)

    def suspend(self, statement_id: str, at: int) -> None:
        """Suspended until ruled (D2: a self-knowable claim whose evidence
        was not produced in time); `reinstate` clears it from the view."""
        self._state(statement_id, SUSPENDED, at)
        self.store.put(SUSPENDED_KEYS + statement_id, {"at": int(at)})

    def reinstate(self, statement_id: str, at: int) -> None:
        if self.revoked(statement_id):
            raise ValueError("a revoked statement stays revoked: issue a new one")
        self._state(statement_id, ISSUED, at)
        self.store.delete(SUSPENDED_KEYS + statement_id)

    def revoke(self, statement_id: str, at: int) -> None:
        """Monotone, like a tombstone: once revoked, always revoked."""
        self._state(statement_id, REVOKED, at)
        self.store.put(REVOKED_KEYS + statement_id, {"at": int(at)})
        if self.store.contains(SUSPENDED_KEYS + statement_id):
            self.store.delete(SUSPENDED_KEYS + statement_id)

    def accredit(self, issuer: str, category: str, *, by: str, since: int, until: int,
                 scheme: str = "") -> None:
        """Who may issue what, and how it is checked (E3's `scheme`)."""
        if not since < until:
            raise ValueError("an accreditation runs from since until a later until")
        self.store.put(f"{ACCREDIT}{issuer}/{category}",
                       {"by": by, "since": int(since), "until": int(until), "scheme": scheme})

    def _state(self, statement_id: str, state: str, at: int) -> None:
        current = self.status(statement_id)
        if current is not None and current["state"] == REVOKED and state != REVOKED:
            raise ValueError("a revoked statement stays revoked")
        self.store.put(STATUS + statement_id, {"state": state, "at": int(at)})

    # -- reads (anyone, at a pinned root) ----------------------------------------

    def status(self, statement_id: str) -> dict | None:
        key = STATUS + statement_id
        return self.store.get(key) if self.store.contains(key) else None

    def revoked(self, statement_id: str) -> bool:
        return self.store.contains(REVOKED_KEYS + statement_id)

    def suspended(self, statement_id: str) -> bool:
        return self.store.contains(SUSPENDED_KEYS + statement_id)

    def accreditation(self, issuer: str, category: str) -> dict | None:
        key = f"{ACCREDIT}{issuer}/{category}"
        return self.store.get(key) if self.store.contains(key) else None

    def accreditations(self, issuer: str):
        """Every (category, record) accrediting `issuer` here."""
        prefix = f"{ACCREDIT}{issuer}/"
        for key, rec in self.store.items(prefix):
            yield key[len(prefix):], rec

    def prove(self, key: str):
        """recordstore's inclusion-or-absence proof of `key` under this
        register's root — what makes "not revoked" a proof (R4)."""
        return self.store.prove(key)


def named_registers(offers) -> set[str]:
    """The registers a set of offers' requirements name as trust roots —
    what a proposal through them must pin (R3a). A register on the path
    below a root is found by the solver when it resolves a statement's path
    (R4); the roots are what the requirers named themselves."""
    out: set[str] = set()
    for o in offers:
        req = o.requires
        if req is None:
            continue
        for cred in req.counterparty:
            out.update(cred.roots)
    return out


def newest_reader(pointer_for, blobs):
    """The gate's `latest` (R5) over registers' feeds: `pointer_for(rid)` is
    the register's feed pointer (or None), and the reader opens the register
    at the root the feed's tip names, over `blobs`. The root read is the
    newest the reader can see — a node withholding the tip makes a stale pin
    pass here, which is why the signed sequence (recordstore's
    `verify_feed_update`) and an anchor are the evidence a claim uses, and
    this only the clearing's own look."""
    from recordstore import RecordStore

    def latest(rid: str):
        pointer = pointer_for(rid)
        root = pointer.get() if pointer is not None else None
        return Register(RecordStore.at(root, blobs)) if root else None
    return latest
