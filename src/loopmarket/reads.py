"""What an exact check reads beyond the two offers and the catalogue.

Matching a give to a want, re-deriving a leg at clearing and hunting for
loops all read the same few facts from outside the offers themselves:

- `available`: offer id -> what fills (and, at a given time, active
  holds) have left of it, `OfferRegistry.availability`; absent, the
  offer's whole quantity.
- `held`: offer id -> what the escrow contract holds behind the offer's
  deposit, in the asset's unit; absent, the declaration stands. With it, a
  deposit that names an escrow counts only up to what is held
  (`matching.meets`).
- `free`: offer id -> what of that deposit no reservation holds (held,
  less every fill's share and every statement's floor reserved on it);
  absent, `held` stands. Step 6 of the gate counts only this, so a floor
  reserved for one leg is never counted again for another (question 27).
- `gate`: the counterparty gate over the book read (`gate.CounterpartyGate`:
  the statements presented, the registers, holds and item claims); absent,
  every requirement only a gate can check fails closed (U7).
- `chain_fills`: offer id -> the quantity the clearing contract has
  recorded as taken (`BeatClearing.filled`), the fill authority once a
  beat is finalized; absent, the book's fills are the authority.
- `escrow_held`: offer id -> what the escrow holds behind it, asked one
  offer at a time (`escrow.held_units`); absent, no escrow is read.
- `escrow_free`: offer id -> what of it is free, asked likewise
  (`escrow.free_units`); absent, only what is held is read.

The last three are the authorities a solver or a clearing is given. Each
pass derives the first four from them and from the snapshot it reads
(`SolverAgent.find_loops`, `BookClearing.submit`), and the exact checks
read those three. `Reads` carries all five as one value, so the command
line, the solver, the clearing and the checks pass one object instead of
threading seven keyword parameters through some twenty signatures. The
public functions still take the keywords each took before (the checks
`available`, `held` and `gate`; the solver, the clearings and the
auction `chain_fills` and `escrow_held`) and fold them into a `Reads`
(`reads_of`), because solvers outside this package call them that way.
"""

from __future__ import annotations

from dataclasses import dataclass, replace as _replace
from typing import TYPE_CHECKING, Callable, Mapping

if TYPE_CHECKING:
    from fractions import Fraction

    from .gate import CounterpartyGate


@dataclass(frozen=True, slots=True)
class Reads:
    """The reads of the module docstring. Each field is optional, and an
    absent one is the reading that asks nothing beyond the book."""

    available: Mapping[str, Fraction] | None = None
    held: Mapping[str, Fraction] | None = None
    gate: CounterpartyGate | None = None
    chain_fills: Callable[[str], object] | None = None
    escrow_held: Callable[[str], object] | None = None
    free: Mapping[str, Fraction] | None = None
    escrow_free: Callable[[str], object] | None = None

    def replace(self, **changes) -> Reads:
        """These reads with some fields changed."""
        return _replace(self, **changes)


#: No reads at all: the checks see the offers and the catalogue alone.
NO_READS = Reads()

#: The reads each pass derives from the authorities and its snapshot.
PER_PASS = ("available", "held", "gate", "free")


def reads_of(reads: Reads | None = None, *, available=None, held=None, gate=None,
             chain_fills=None, escrow_held=None, escrow_free=None) -> Reads:
    """`reads` with the reads a caller passed as keywords folded in: a
    caller writing `check_match(g, w, cat, now=t, gate=x)` means
    `reads=Reads(gate=x)`. A read given both ways is refused with a
    `TypeError` (two answers to one question, and nothing says which was
    meant) unless it is the same object."""
    if available is None and held is None and gate is None and chain_fills is None \
            and escrow_held is None and escrow_free is None:
        return NO_READS if reads is None else reads
    base = NO_READS if reads is None else reads
    given = {name: value for name, value in (("available", available), ("held", held), ("gate", gate),
                                             ("chain_fills", chain_fills), ("escrow_held", escrow_held),
                                             ("escrow_free", escrow_free))
             if value is not None}
    for name, value in given.items():
        already = getattr(base, name)
        if already is not None and already is not value:
            raise TypeError(f"{name} given twice: as {name}= and in reads=")
    return _replace(base, **given)


def authorities(reads: Reads | None = None, *, chain_fills=None, escrow_held=None,
                taker: str, escrow_free=None) -> Reads:
    """The reads a solver or a clearing is constructed with: the chain's
    fills and the escrow's holdings and free shares, by either spelling.
    Each of its passes derives `available`, `held`, `free` and the gate
    from these and its snapshot, so reads naming any of those four are
    refused rather than silently replaced."""
    reads = reads_of(reads, chain_fills=chain_fills, escrow_held=escrow_held, escrow_free=escrow_free)
    derived = [name for name in PER_PASS if getattr(reads, name) is not None]
    if derived:
        raise TypeError(f"{taker} derives {', '.join(derived)} from each snapshot it reads: "
                        f"give it chain_fills, escrow_held and escrow_free")
    return reads
