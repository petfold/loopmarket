"""Arbitrators accepted by property (2026-09-29, `docs/plans/counterparty-gate.md`
§7a): a maker accepts the resolver of a leg's reservation — or the giver of
a required leg (D4) — by what can be read about it, not only by name.

An `Accept` reads *who* as alternatives — a key in `keys`, or every key that
can rule accredited under one of `roots` — and its *floors* all together:

- **accreditation** (`roots`): a statement about the ruling key, presented
  in its own book (`cred/`, R2), of a category under `arbitrator` (for a
  resolver; under the required leg's category for a leg's giver), signed or
  attested, whose path reaches a named root through pinned registers — the
  counterparty gate's steps 1–5 and 7 (`CounterpartyGate.accredited`);
- **a deposit** (`min_deposit`, on the requirer's own scale): what one
  reversed ruling forfeits — factbond's rung deposit, `min(deposits
  (adjudicator), depositWei)`, and nothing when there is no final rung to
  reverse it — at least the floor converted at the requirer's acceptance
  price for the deposit's asset, once (U14);
- **a clean record** (`clean_for` seconds): no reversal of the resolver's
  rulings within the look-back, *and* a record covering it — a resolver
  whose ledger starts inside the look-back has not shown a year unreversed,
  and a key that ruled, was reversed and came back under a new name would
  otherwise pass (the tenure reading, as ruled in `counterparty-gate.md`
  §7a). The record is the resolver
  contract's, not its current adjudicator's: an owner swapping the key
  does not wipe it;
- **issuance** (D8): not read yet, so an acceptance naming it admits nothing.

Never a count of rulings or inspections (THREATS T16), and never a party to
the leg — every key that can rule, not only the address the reservation
names. An acceptance whose reads are missing admits nothing (U7).

**Who resolves a leg** (`resolver_of`): the give's named `arbitrator`
first, then every key either side's acceptance names in sorted order, then
the clearing's own default when the give leaves the choice to it (names no
arbitrator and no acceptance) — the first that both sides admit. Record
data decide the order, so every replica chooses alike (U6), and the
clearing's default comes last so that what a solver chose (it cannot see
the default) is what the reservation gets while the reads stand.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .schema import GIVE, Offer, q

ARBITRATOR = "arbitrator"               # the catalogue node a resolver's accreditation falls under


@dataclass(frozen=True)
class Profile:
    """What the chain says about a resolver address: the keys that can rule
    on it (an `Assertions` contract's adjudicator and final arbiter; a key
    ruling directly is its own), what a reversed ruling forfeits (a quantity
    of `asset` = (concepts, unit); None when nothing is at stake), when its
    rulings were reversed (None: no appeal ledger to read — a key ruling
    directly is never reversed, which shows nothing) and since when that
    record runs."""

    rulers: tuple[str, ...]
    deposit: Fraction | None = None
    asset: tuple[tuple[str, ...], str] | None = None
    reversals: tuple[int, ...] | None = None
    since: int | None = None


def accept_faults(accept, key: str, *, parties=(), requirer: Offer | None = None, ontology=None,
                  gate=None, category: str = ARBITRATOR, window=None) -> list[str]:
    """Every reason `accept` does not admit `key` ([] when it does), in the
    gate's style (plan E4: one refusal lists every discrepancy). `gate` is
    the `CounterpartyGate` the reads come from: its clock, the statements,
    the registers, and `profile(address)` for a resolver's chain record."""
    if not key:
        return ["no key named"]
    profile = gate.profile(key) if gate is not None and gate.profile is not None else None
    rulers = profile.rulers if profile is not None and profile.rulers else (key,)
    lowered = {p.lower() for p in parties if p}
    if key.lower() in lowered or any(r.lower() in lowered for r in rulers):
        return [f"{key} is a party to the leg, or rules through one"]
    f: list[str] = []
    # who: a named key, or every ruler accredited under a named root
    if accept.keys or accept.roots:
        named = key.lower() in {k.lower() for k in accept.keys}
        if not named:
            why = [] if accept.roots else [f"{key} is not a named key"]
            if accept.roots:
                if gate is None or ontology is None:
                    why = ["accreditation needs the registers (no gate)"]
                else:
                    span = window or (gate.now, gate.now)
                    for r in rulers:
                        why.extend(gate.accredited(r, category, accept.roots, ontology, span))
            f.extend(why)
    # the floors, all of them
    if accept.min_deposit:
        f.extend(_deposit_faults(accept, profile, requirer, ontology))
    if accept.clean_for:
        f.extend(_record_faults(accept, profile, gate))
    if accept.issuance:
        f.append("issuance sources (D8) are not read yet")
    return f


def admits(accept, key: str, **reads) -> bool:
    """Does `accept` admit `key`? (`accept_faults` is empty.)"""
    return not accept_faults(accept, key, **reads)


def _deposit_faults(accept, profile, requirer, ontology) -> list[str]:
    if profile is None or profile.deposit is None or profile.asset is None:
        return ["no deposit at stake on its rulings is known"]
    if requirer is None or requirer.requires is None or ontology is None:
        return ["no acceptance to price the deposit floor"]
    concepts, unit = profile.asset
    for acc in requirer.requires.accepts:
        if acc.unit == unit and ontology.satisfies(tuple(concepts), acc.concepts):
            need = accept.min_deposit / acc.price
            if q(profile.deposit) >= need:
                return []
            return [f"{profile.deposit} {unit} at stake on a reversal, less than {need} for the floor "
                    f"{accept.min_deposit}"]
    return [f"no acceptance of {' '.join(concepts)} {unit} to price the deposit floor"]


def _record_faults(accept, profile, gate) -> list[str]:
    if profile is None or profile.reversals is None or gate is None:
        return ["no appeal ledger records its rulings"]
    start = gate.now - accept.clean_for
    if profile.since is None or profile.since > start:
        return [f"its record starts inside the {accept.clean_for}s look-back"]
    late = [t for t in profile.reversals if t > start]
    if late:
        return [f"{len(late)} ruling(s) reversed within the last {accept.clean_for}s"]
    return []


# -- who resolves a leg -------------------------------------------------------------

def _resolvers(o: Offer):
    return o.requires.resolvers if o.v >= 6 and o.requires is not None else None


def constrained(want: Offer, give: Offer) -> bool:
    """Does either side accept resolvers by an acceptance?"""
    return _resolvers(want) is not None or _resolvers(give) is not None


def resolver_of(want: Offer, give: Offer, *, default: str = "", gate=None, ontology=None,
                window=None) -> str | None:
    """The resolver of the reservation on `give` for `want`'s leg: the first
    candidate (the give's `arbitrator`, then the keys either acceptance
    names, sorted, then `default` — the clearing's own) that both sides
    admit, never a party; None when none is. With no acceptance on either
    side, the give's arbitrator else the default, as before."""
    from .escrow import is_address
    arbitrator = give.arbitrator if is_address(give.arbitrator) else ""
    w_acc, g_acc = _resolvers(want), _resolvers(give)
    if w_acc is None and g_acc is None:
        return arbitrator or default or None
    if give.kind != GIVE:
        return None
    parties = (want.maker, give.maker)
    names = sorted({k.lower(): k for acc in (w_acc, g_acc) if acc is not None for k in acc.keys}.values(),
                   key=str.lower)
    candidates = []
    for k in [arbitrator, *names, default]:
        if k and k.lower() not in {c.lower() for c in candidates}:
            candidates.append(k)
    reads = dict(parties=parties, gate=gate, ontology=ontology, window=window)

    def giver_takes(k: str) -> bool:
        if g_acc is not None:
            return (arbitrator and k.lower() == arbitrator.lower()) or admits(g_acc, k, requirer=give, **reads)
        if arbitrator:
            return k.lower() == arbitrator.lower()
        return bool(default) and k.lower() == default.lower()     # the give left it to the clearing

    for k in candidates:
        if not giver_takes(k):
            continue
        if w_acc is not None and not admits(w_acc, k, requirer=want, **reads):
            continue
        if accept_faults(_ANYONE, k, parties=parties, gate=gate):  # the formality for a give's own pick
            continue
        return k
    return None


class _Anyone:
    keys = roots = issuance = ()
    min_deposit = clean_for = 0


_ANYONE = _Anyone()


# -- the chain's record of a resolver -------------------------------------------------

_ABI = [
    {"name": n, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": t, "name": ""}]}
    for n, t in (("adjudicator", "address"), ("arbiter", "address"), ("depositWei", "uint256"))
] + [
    {"name": "deposits", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "Reversed", "type": "event", "anonymous": False, "inputs": [
        {"name": "id", "type": "uint256", "indexed": True},
        {"name": "adjudicator", "type": "address", "indexed": True},
        {"name": "forfeited", "type": "uint256", "indexed": False}]},
]


def chain_profile(address: str, *, rpc: str | None = None, client=None, asset=(("xdai",), "xDAI"),
                  decimals: int = 18, from_block: int = 0) -> Profile | None:
    """A resolver's `Profile` read from the chain: an address with no code
    is a key ruling directly (itself the ruler; nothing at stake, no appeal
    ledger); a factbond `Assertions` contract rules through its adjudicator
    and, above it, its arbiter — what a reversal forfeits is the rung's
    deposit up to `depositWei`, nothing without an arbiter (rulings final),
    and the record is its `Reversed` events since its first event of any
    kind. Anything else is None (U7). web3 is imported here, behind the
    `chain` extra (B2)."""
    from web3 import Web3
    w3 = client or Web3(Web3.HTTPProvider(rpc))
    addr = Web3.to_checksum_address(address)
    if not w3.eth.get_code(addr):
        return Profile(rulers=(addr,))
    c = w3.eth.contract(address=addr, abi=_ABI)
    try:
        adjudicator, arbiter = c.functions.adjudicator().call(), c.functions.arbiter().call()
        at_stake = min(c.functions.deposits(adjudicator).call(), c.functions.depositWei().call())
    except Exception:                    # noqa: BLE001 — not a contract this reader knows
        return None
    final = int(arbiter, 16) == 0
    rulers = (adjudicator,) if final else (adjudicator, arbiter)
    times: dict[int, int] = {}

    def when(n: int) -> int:
        if n not in times:
            times[n] = w3.eth.get_block(n)["timestamp"]
        return times[n]
    logs = w3.eth.get_logs({"address": addr, "fromBlock": from_block, "toBlock": "latest"})
    since = when(min(log["blockNumber"] for log in logs)) if logs else None
    reversals = tuple(when(log["blockNumber"]) for log in c.events.Reversed().get_logs(from_block=from_block))
    deposit = Fraction(0) if final else Fraction(at_stake, 10 ** decimals)
    return Profile(rulers=rulers, deposit=deposit, asset=(tuple(asset[0]), asset[1]), reversals=reversals,
                   since=since)
