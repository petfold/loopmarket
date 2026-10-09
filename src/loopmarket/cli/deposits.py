"""The escrow behind my legs: `deposit` funds my gives' bonds,
`reservations` lists what it holds per fill, the escrow's acts
(`countersign`, `cancel`, `assign`, `settle`, `extend-claim`) run under my
key, and `collect` takes the payouts my address refused."""

from __future__ import annotations

import shlex
from fractions import Fraction

from ..schema import GIVE, WANT, q
from . import clients
from .registers import _transfer_faults
from .render import _num
from .settings import _configured, _err
from .spellings import _iso, duration_s
from .stores import _resolve_id


def cmd_deposit(args, session, out):
    """Fund the declared bond of my gives on the escrow contract (P3 §5a,
    2026-09-19): for the offer named, or every unfilled give of mine whose
    `bond` names the `escrow` contract and is not yet held there, deposit
    the bond's quantity in the chain's native coin — the default asset,
    xDAI on Gnosis — from the bee_signer key. `--check` reports what the
    contract holds against each and sends nothing. An ERC-20 deposit is
    the client's `deposit(token=)`; the CLI funds the gas token only, as
    the one asset every maker on the chain already holds."""
    from ..escrow import to_wei
    client = clients._escrow_client(session)
    mine = [o for o in session.book.offers(include_filled=False)
            if o.maker == session.maker and o.kind == GIVE and o.v >= 5 and o.bond is not None]
    if args.id:
        mine = [o for o in mine if o.offer_id.startswith(args.id)]
        if not mine:
            raise ValueError(f"{args.id}: not an unfilled give of mine with a bond")
    escrow = client.address.lower()
    mine = [o for o in mine if o.bond.escrow.lower() == escrow]
    if not mine:
        print("nothing to deposit: no give of mine names this escrow", file=_err())
        return 1
    sent = 0
    for o in mine:
        need, held = to_wei(o.bond.asset.qty), client.held(o.offer_id)
        asset = f"{_num(o.bond.asset.qty)}{o.bond.asset.unit} {' '.join(o.bond.asset.concepts)}"
        if held >= need:
            print(f"{o.offer_id[:16]}… {asset}: held", file=out)
            continue
        if args.check:
            print(f"{o.offer_id[:16]}… {asset}: {_num(Fraction(need - held, 10 ** 18))} to deposit", file=out)
            continue
        receipt = client.deposit(o.offer_id, need - held)
        sent += 1
        print(f"{o.offer_id[:16]}… {asset}: deposited, gas {receipt['gasUsed']}", file=out)
    return 0


# ---------------------------------------------------------------- C6: the escrow's acts

def _reservation_ref(session, offer: str, loop: str | None) -> tuple[str, str]:
    """(offer id, loop id) of a reservation: `offer` a prefix of a give in
    the fold (or a whole id), `loop` a prefix of one of the loops that took
    from it — optional when there is one."""
    full = lambda x: len(x) == 64 and all(c in "0123456789abcdef" for c in x.lower())
    fold = session.fold()
    oid = offer.lower() if full(offer) else _resolve_id(session, offer, mine_only=False)
    loops = sorted(set(fold.loops_of(oid)) | set(session.book.loops_of(oid)))
    if loop and full(loop):
        return oid, loop.lower()
    if loop:
        loops = [x for x in loops if x.startswith(loop.lower())]
    if len(loops) == 1:
        return oid, loops[0]
    if not loops:
        raise ValueError(f"{oid[:16]}…: no loop" + (f" {loop}" if loop else "") + " took from it here; "
                         "name the loop by its whole id (--loop)")
    raise ValueError(f"{oid[:16]}…: several loops — name one (--loop): " + ", ".join(x[:16] for x in loops))


def _asset_amount(text: str, whole: int) -> int:
    """A split typed at the command line, in the reservation's smallest
    units: `all`, `N%` of the reservation, `NUNIT` in the deposit's asset
    (`0.004xDAI`), or a bare amount on my scale — converted once at my
    price for the asset (`default_asset`), as every amount I type is."""
    from ..escrow import to_wei
    t = text.strip()
    if t == "all":
        return whole
    if t.endswith("%"):
        return int(whole * q(t[:-1]) / 100)          # rounded down: never beyond the share named
    toks = shlex.split(_configured("default_asset") or "")
    unit = toks[-2] if len(toks) >= 3 else "xDAI"
    if t.endswith(unit):
        return to_wei(q(t[:-len(unit)]))
    if len(toks) < 3:
        raise ValueError(f"a bare amount is on my scale and needs my price for the asset: "
                         f"`set default_asset 'xdai xDAI PRICE'`, or type `{t}{unit}` or a percentage")
    return to_wei(q(t) / q(toks[-1]))


def _reservation_line(r: dict) -> str:
    state = "settled" if r["settled"] else "held by a claim" if r["held"] else "open"
    return (f"{_num(Fraction(r['amount'], 10 ** 18))} for {r['wanter']}, resolver {r['resolver']}, "
            f"claims until {_iso(r['claim_until'])}" + (", cover" if r["claim_only"] else "")
            + (f", deductible {_num(Fraction(r['deductible'], 10 ** 18))}" if r.get("deductible") else "")
            + f": {state}")


def cmd_reservations(args, session, out):
    """The reservations on the escrow behind my legs: my bonded gives' (I
    am the giver) and my filled wants' gives' (I am the wanter), each with
    its amount, wanter, resolver, claim period and state — read from the
    contract, the loops from the fold. A claim assigned to me is not found
    here (the book does not record it); name it to the verbs directly."""
    client = clients._escrow_client(session)
    escrow = client.address.lower()
    fold = session.fold()
    rows = []
    for o in fold.offers(include_filled=True):
        if o.maker != session.maker:
            continue
        if o.kind == GIVE and o.v >= 5 and o.bond is not None and o.bond.escrow.lower() == escrow:
            rows += [("giver", o.offer_id, loop) for loop in fold.loops_of(o.offer_id)]
        elif o.kind == WANT:
            for loop in fold.loops_of(o.offer_id):
                for leg in fold.loop_legs(loop):
                    if leg.want != o.offer_id:
                        continue
                    for g in leg.gives:
                        try:
                            give_ = fold.get(g)
                        except KeyError:
                            continue
                        if give_.v >= 5 and give_.bond is not None and give_.bond.escrow.lower() == escrow:
                            rows.append(("wanter", g, loop))
    shown = 0
    for role, oid, loop in sorted(set(rows)):
        r = client.reservation(oid, loop)
        if not r["amount"] or (r["settled"] and not args.all):
            continue
        shown += 1
        print(f"{oid[:16]}… loop {loop[:16]}… (I am the {role}): {_reservation_line(r)}", file=out)
    if not shown:
        print("no open reservation behind my legs" + ("" if args.all else " (--all: settled too)"), file=out)
    return 0


def _escrow_act(args, session, out, act: str) -> int:
    client = clients._escrow_client(session)
    oid, loop = _reservation_ref(session, args.offer, args.loop)
    r = client.reservation(oid, loop)
    if not r["amount"]:
        raise ValueError(f"{oid[:16]}… loop {loop[:16]}…: no reservation on this escrow")
    if act == "countersign":
        why = _transfer_faults(session, oid, loop, r["wanter"])
        if why:
            raise ValueError("not countersigned: " + "; ".join(why) + " (a title register's transfer is the "
                             "performance this give declared)")
        receipt, said = client.countersign(oid, loop), "countersigned: the reservation returns to the giver"
    elif act == "cancel":
        receipt, said = client.cancel(oid, loop), "cancelled: the ladder's amount at this lead to the wanter"
    elif act == "assign":
        receipt, said = client.assign(oid, loop, args.to), f"assigned the claim to {args.to}"
    elif act == "extend-claim":
        secs = duration_s(args.duration)
        receipt, said = client.extend_claim(oid, loop, secs), f"claim period lengthened by {args.duration}"
    elif act == "settle" and args.split is None:
        receipt, said = client.settle(oid, loop), "settled quiet: the reservation returned to the giver"
    else:
        amount = _asset_amount(args.split, r["amount"])
        if amount > r["amount"]:
            raise ValueError(f"a split of {_num(Fraction(amount, 10 ** 18))} is beyond the reservation "
                             f"({_num(Fraction(r['amount'], 10 ** 18))})")
        receipt = client.settle(oid, loop, amount)
        after = client.reservation(oid, loop)
        said = (f"signed the split {_num(Fraction(amount, 10 ** 18))} to the wanter"
                + (": both signed, settled" if after["settled"] else ": waiting for the other party's"))
    print(f"{oid[:16]}… loop {loop[:16]}…: {said}, gas {receipt['gasUsed']}", file=out)
    return 0


def cmd_collect(args, session, out):
    """Collect the payouts my address refused when the escrow pushed them
    (E1's `owed`); `--check` reports what waits."""
    client = clients._escrow_client(session)
    me = client.account().address
    owed = client.owed(me)
    if not owed:
        print(f"nothing owed to {me}", file=out)
        return 1 if not args.check else 0
    if args.check:
        print(f"{_num(Fraction(owed, 10 ** 18))} owed to {me}", file=out)
        return 0
    receipt = client.collect()
    print(f"collected {_num(Fraction(owed, 10 ** 18))}, gas {receipt['gasUsed']}", file=out)
    return 0
