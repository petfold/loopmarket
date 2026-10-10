"""The session's links beyond the book: the clearing contract, the escrow,
the sealed beat, the registers it reads and the resolvers' chain records,
each opened from the settings when a command asks for it, and the `Reads`
they supply to the solver and the clearing.

A test replaces a client here (`cli.clients._beat_client`,
`_escrow_client`, `_MEMORY_SEALED`), and every other module calls them
through this module, so one replacement reaches every command."""

from __future__ import annotations

import shlex

from ..reads import Reads
from . import stores
from .settings import _configured, _err
from .spellings import _calendar_span


def _beat_client(session):
    from ..beat import BeatClient
    spec = _configured("beat")
    if not spec or not spec.startswith("chain:"):
        raise ValueError("no clearing contract: `loop set beat chain:RPC_URL@CONTRACT`")
    rpc, _, address = spec[6:].rpartition("@")
    return BeatClient(rpc, address, key=_configured("bee_signer") or None)


def _chain_fills(session):
    """`BeatClearing.filled` when a clearing contract is set — the fill
    authority the hunt and the checklist subtract from what the book says
    is left — else None (2026-09-18: a fold that never saw a clearing's
    fills proposed a loop through an offer the chain had already filled)."""
    if not (_configured("beat") or "").startswith("chain:"):
        return None
    return _beat_client(session).filled


def _reads(session) -> Reads:
    """What the hunt reads beyond the book, where this session names it:
    the clearing contract's fills and the escrow's holdings and free shares
    (`Reads`, each None when its contract is not set)."""
    return Reads(chain_fills=_chain_fills(session), escrow_held=_escrow_held(session),
                 escrow_free=_escrow_free(session))


def _escrow_client(session):
    from ..escrow import EscrowClient
    spec = _configured("escrow")
    if not spec or not spec.startswith("chain:"):
        raise ValueError("no escrow contract: `loop set escrow chain:RPC_URL@CONTRACT`")
    rpc, _, address = spec[6:].rpartition("@")
    return EscrowClient(rpc, address, key=_configured("bee_signer") or None)


def _registers(session) -> dict:
    """Register id -> the `Register` at its head (R3a, 2026-09-29 night):
    every `registers` pair, and with a `registry` every book announced under
    the `register` role, its owner the id (the feed's signer, as for maker
    books). The head is what the gate calls the newest root (R5)."""
    from ..register import Register
    cached = getattr(session, "_registers", None)
    if cached is not None:
        return cached
    out: dict = {}
    for pair in (_configured("registers") or "").split():
        rid, sep, spec = pair.partition("=")
        if not sep or not rid or not spec:
            raise ValueError(f"registers entry {pair!r} is ID=SPEC")
        out[rid] = Register(stores._open_book(spec).store)
    if _configured("registry"):
        from ..announce import REGISTER
        for ann in session.announcements.announced():
            if ann.role != REGISTER or ann.owner in out:
                continue
            try:
                out[ann.owner] = Register(stores._open_book(ann.spec()).store)
            except Exception as exc:        # noqa: BLE001 — an unreadable register pins nothing
                print(f"loop: register {ann.owner}: {exc}", file=_err())
    session._registers = out
    return out


def _register_at(session):
    """(register id, root) -> the register read at that root, over the blobs
    of the register this session opened — what a clearing re-reads at the
    proposal's pins (U3); None for a register it does not read."""
    from recordstore import RecordStore
    from ..register import Register
    regs = _registers(session)

    def at(rid: str, root: str):
        reg = regs.get(rid)
        return Register(RecordStore.at(root, reg.store.blobs)) if reg is not None and root else None
    return at


def _gate_reads(session) -> dict:
    """The counterparty gate's reads as keyword arguments, for a solver and
    a clearing alike: the registers, their heads, the resolvers' records."""
    regs = _registers(session)
    return {"registers": regs, "register_latest": regs.get, "resolver_profile": _resolver_profiles(session)}


def _clearing_reads(session) -> dict:
    regs = _registers(session)
    return {"register_at": _register_at(session), "register_latest": regs.get,
            "resolver_profile": _resolver_profiles(session), "span": _calendar_span}


def _resolver_profiles(session):
    """A resolver's chain record (`arbitrators.chain_profile`, §7a), read
    through the escrow's (else the clearing contract's) RPC and cached for
    the session, when either is set — what `require_resolvers`' `min:` and
    `clean:` weigh; None otherwise, and those floors admit nothing. The
    deposit is in the chain's native coin, named as `default_asset` names
    it (Gnosis's `xdai xDAI` otherwise: a fact about the chain, not a price)."""
    spec = next((v for v in (_configured("escrow"), _configured("beat")) if (v or "").startswith("chain:")), "")
    if not spec:
        return None
    rpc = spec[6:].rpartition("@")[0]
    toks = shlex.split(_configured("default_asset") or "")
    asset = (tuple(toks[:-2]), toks[-2]) if len(toks) >= 3 else (("xdai",), "xDAI")
    cache: dict = {}

    def profile(address: str):
        from ..arbitrators import chain_profile
        if address.lower() not in cache:
            try:
                cache[address.lower()] = chain_profile(address, rpc=rpc, asset=asset)
            except Exception:              # noqa: BLE001 — an unreadable record admits nothing (U7)
                cache[address.lower()] = None
        return cache[address.lower()]
    return profile


def _escrow_held(session):
    """`EscrowClient.held` in asset units when an escrow contract is set —
    the authority on every deposit the hunt and the checklist weigh — else
    None (the declaration stands)."""
    if not (_configured("escrow") or "").startswith("chain:"):
        return None
    from ..escrow import held_units
    return held_units(_escrow_client(session))


def _escrow_free(session):
    """`EscrowClient.free` in asset units when an escrow contract is set:
    what of a deposit no reservation holds, all a statement's floor may
    count (question 27); else None."""
    if not (_configured("escrow") or "").startswith("chain:"):
        return None
    from ..escrow import free_units
    return free_units(_escrow_client(session))


_MEMORY_SEALED = None


def _sealed_client(session):
    """The sealed beat named by `auction` (auction.py): a chain contract, or
    one in-process instance per process for `memory:`."""
    global _MEMORY_SEALED
    from ..auction import MemorySealedBeat, open_sealed
    spec = _configured("auction")
    if not spec:
        raise ValueError("no sealed beat: `loop set auction chain:RPC_URL@CONTRACT` (or memory:)")
    if spec.startswith("memory") and _MEMORY_SEALED is None:
        _MEMORY_SEALED = MemorySealedBeat(solver=_configured("maker") or "me")
    return open_sealed(spec, key=_configured("bee_signer") or None, memory=_MEMORY_SEALED)
