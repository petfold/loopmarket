"""A personal view of arbitrators (2026-10-01, `counterparty-gate.md` §7a):
what a maker can see for itself about the arbitrators it and the makers it
trusts have chosen — never a score the protocol reads.

An arbitrator's parties are no witnesses to its quality — the winner is
always satisfied and the loser almost never — and every count is
manufactured by puppet trades (U12, THREATS T16). What remains readable is
the choice made before a dispute, when neither side knew who would lose,
and its strongest form: a party who lost a ruling under an arbitrator and
chose it again. Restricted to me and the makers I name as trusted, a puppet
gains nothing: it can only flatter an arbitrator in front of makers who
already trusted the puppet.

From the escrow's log: `Reserved` names each fill's wanter and resolver,
`Settled` how it ended (`resolved` is a ruling; `toWanter` what it paid),
`Deposited` the giver behind each deposit. A wanter paid nothing by a ruling
lost it; a giver paying anything lost it. A return is a choice only when
the party's offer on the later leg was *posted* after the loss: a later
fill of an offer posted before it was chosen before it. `posted(maker,
offer, loop)` answers that from the book (the give itself, or the want the
loop record says it served); an unknown posting counts nothing. Pure: the
events and the reader are handed in.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Arbitrator:
    """What `view` reports about one resolver."""

    key: str
    legs: list = field(default_factory=list)          # (wanter, giver, time) naming it, me or trusted a party
    rulings: list = field(default_factory=list)       # (wanter, giver, to_wanter, amount, time)
    chosen_again: list = field(default_factory=list)  # makers who lost a ruling under it and named it later


def _key(offer: str, loop: str) -> str:
    from .escrow import reservation_key
    return reservation_key(offer, loop)


def view(reserved, settled, deposited, *, me: str, trusted=(), posted=None) -> list[Arbitrator]:
    """Every arbitrator named on a reservation where I or a trusted maker
    was a party: the legs, the rulings, and which of us lost a ruling under
    it and chose it again afterwards. Sorted by key (U6: the same log, the
    same view)."""
    circle = {me.lower(), *(t.lower() for t in trusted)}
    giver_of = {d["offer"].removeprefix("0x"): d["giver"] for d in deposited}
    ended = {s["key"].removeprefix("0x"): s for s in settled}
    out: dict[str, Arbitrator] = {}
    losses: dict[tuple[str, str], int] = {}           # (resolver, maker) -> time of the first loss
    for r in sorted(reserved, key=lambda r: (r["time"], r["block"])):
        offer, loop = r["offer"].removeprefix("0x"), r["loop"].removeprefix("0x")
        wanter, giver, resolver = r["wanter"], giver_of.get(offer, ""), r["resolver"]
        if not ({wanter.lower(), giver.lower()} & circle):
            continue
        a = out.setdefault(resolver.lower(), Arbitrator(resolver))
        a.legs.append((wanter, giver, r["time"]))
        for maker in (wanter, giver):
            lost_at = losses.get((resolver.lower(), maker.lower()))
            if lost_at is None or maker.lower() not in circle or maker in a.chosen_again:
                continue
            at = posted(maker, offer, loop) if posted is not None else None
            if at is not None and at > lost_at:
                a.chosen_again.append(maker)
        s = ended.get(_key(offer, loop))
        if s is not None and s.get("how") == "resolved":
            to_wanter = int(s["toWanter"])
            a.rulings.append((wanter, giver, to_wanter, int(r["amount"]), s["time"]))
            loser = wanter if to_wanter == 0 else giver
            losses.setdefault((resolver.lower(), loser.lower()), s["time"])
    return [out[k] for k in sorted(out)]
