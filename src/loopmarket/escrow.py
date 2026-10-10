"""The crypto escrow on chain (P3, `docs/plans/P3-release-and-reclearing.md`
§5a, built 2026-09-19): `LoopEscrow` holds a giver's deposit — the v5
record's `Bond` — behind an offer id, reserves a share of it per fill,
pays the wanter on a ruling of failure, returns it on the wanter's
countersignature of delivery or after the window with no claim.

Why the deposit is keyed by the *offer* and reservations by (offer,
loop): the bond is declared on the offer before any loop exists (§5d:
`Bond.escrow` is this contract's address, part of the id), and P3 §3a
rule 8 reserves bond × taken / quantity per fill — so a divisible give's
deposit backs every fill it gets, each with its own reservation, and the
contract's `free` is what no fill has claimed. The contract converts
nothing: the quantity was fixed at clearing in the asset's own unit (U14),
and this module only turns that exact rational into the asset's smallest
unit (`to_wei`), rejecting a quantity the asset cannot represent.

Custody here, adjudication in factbond (§5e, Peter, 2026-09-19: "a
ruling or a timeout"). The contract settles every undisputed case by
itself — quiet after the window (`settle`, anyone), the wanter's
countersignature, the giver's cancellation at the ladder's amount — and
a contested claim goes to the resolver fixed at clearing, which calls
`hold` and `resolve`, nothing more: by default one arbitrator both sides
accept, whose ruling is final (`case.py`), or factbond's `Assertions` for
a bonded ladder.

A held reservation is released only by a ruling or by both parties
(2026-09-28, E1 of the development sequence of 2026-09-25): with factbond
as resolver the contract reads the claim inside `hold` and opens only the
wanter's own, naming the giver, within the reservation and the windows it
requires; a retraction reopens the reservation instead of refunding it; a
cover reservation (`claim_only`) is never countersigned; the wanter may
`assign` the claim to any key, the two parties `settle` at a split each
signs, the giver `extend_claim`; a payout an address refuses is credited
for `collect` rather than blocking the settlement.

`EscrowClient` sends and reads; web3 loads lazily behind the `chain`
extra (boundary B2). `reserve` is the clearing's call, with the leg's
wanter, window, resolver, claim terms and the ladder in asset units;
`loop finalize` sends it, and the notice period on withdrawal guards the
gap between clearing and finalization.
"""

from __future__ import annotations

import json
import re
from fractions import Fraction

from .schema import q

NATIVE = "0x0000000000000000000000000000000000000000"


def abi() -> dict:
    """The compiled `LoopEscrow` (solc 0.8.24, via IR, optimizer 200 runs),
    shipped as `loopmarket/contracts/LoopEscrow.json` by `scripts/build_beat.py`."""
    from importlib import resources
    with resources.files("loopmarket").joinpath("contracts", "LoopEscrow.json").open(
            encoding="utf-8") as fh:
        return json.load(fh)


def to_wei(qty: Fraction | int | str, decimals: int = 18) -> int:
    """An exact quantity in the asset's unit as its smallest unit; a
    quantity the asset cannot hold exactly is refused rather than rounded
    (U9: what the contract holds is what clearing compared)."""
    scaled = Fraction(qty) * 10 ** decimals
    if scaled.denominator != 1:
        raise ValueError(f"{qty} is not a whole number of 10^-{decimals} units")
    return int(scaled)


def floor_wei(qty, decimals: int = 18) -> int:
    """A quantity rounded down to the asset's smallest unit — for the
    ladder's points, which bound a payout and may lose the dust."""
    return int(Fraction(qty) * 10 ** decimals)


def held_units(client: "EscrowClient", decimals: int = 18):
    """offer id -> what the escrow holds, in the asset's unit (a Fraction):
    the `escrow_held` the agent and the clearing take."""
    return lambda offer_id: Fraction(client.held(offer_id), 10 ** decimals)


def is_address(text: str) -> bool:
    return isinstance(text, str) and len(text) == 42 and text.startswith("0x") \
        and all(c in "0123456789abcdefABCDEF" for c in text[2:])


def reservations_for(proposal, *, escrow: str, resolver: str, claim_seconds: int, now: int,
                     span=None, decimals: int = 18, claim_only=None, min_challenge: int = 0,
                     min_ruling: int = 0, gate=None, ontology=None) -> list[dict]:
    """What the clearing reserves on the escrow for a cleared loop: one
    reservation per give whose `bond` names `escrow` — the share bond ×
    taken / quantity (§3a rule 8) in smallest units, the leg's wanter (its
    maker, which must be a key address: the payout's destination), the
    resolver (the give's declared `arbitrator` when it is an address, else
    `resolver`, the clearing's own: factbond's `Assertions` or a key), the want's handover window
    (`span(text)` reads the first `time(...)` term of the want, else the
    window is `now`), the claim period, and the wanter's ladder converted
    at her acceptance price for the deposit's asset into that asset —
    rounded down, capped at the reservation. `claim_only(give)` says which
    reservations are cover (never countersigned; `cover_predicate` reads
    the catalogue); `min_challenge` and `min_ruling` are the least windows
    a claim must name, 0 leaving the resolver's own bounds. Pure: nothing
    is sent.

    E2 (2026-09-29), on the v6 record: the claim period is the leg's —
    the want's `claim_period` when it asks one (the gate made sure the
    give's `claim_max` reaches it), else `claim_seconds`, and never longer
    than the give's declared `claim_max`; the resolver is never a party to
    the leg (C4's formality: the want's or the give's maker), and when the
    want requires `resolvers` it must be one they admit — the gate already
    refused the leg otherwise, so a failure here is a clearing that
    bypassed the gate, and it raises.

    C5 (2026-09-29): a cover reservation's window is the **covered period** —
    the `time(...)` inside the insured's `insure(...)` want, else inside the
    insurer's give, else the leg's handover window (cover composed with the
    thing, `requires.legs`, runs while the thing is handed over) — and its
    claim period runs from that period's end: claims made and reported
    within it (`options-and-cover.md` §4.2). A v7 deposit's deductible is
    reserved with the share, in proportion as it (`Bond.deductible_share`),
    in smallest units. C5 stage 2 (D-2): a cover composed with a bonded
    thing in one leg **covers** that thing's reservation — `covers`, its key
    on the escrow — so the insured assigns her claim there to the insurer
    before the cover pays, and the cover nets whatever it already paid her."""
    out = []
    escrow = escrow.lower()
    for leg in proposal.circulation.legs:
        want = leg.want
        window = _period(_concepts(want), span, nested=False) or (now, now)
        is_cover = [bool(claim_only(g)) if claim_only else False for g in leg.gives]
        covered = next((g for g, c in zip(leg.gives, is_cover)
                        if not c and g.v >= 5 and g.bond is not None and g.bond.escrow.lower() == escrow), None)
        covered_key = reservation_key(covered.offer_id, proposal.circulation.loop_id) if covered else ""
        for i, give in enumerate(leg.gives):
            bond = give.bond if give.v >= 5 else None
            if bond is None or bond.escrow.lower() != escrow:
                continue
            if not is_address(want.maker):
                raise ValueError(f"{want.maker!r} is not a key address: the payout has no destination")
            share = bond.reserved(leg.taken(i), give.thing.qty)
            amount = to_wei(share, decimals)
            deductible = to_wei(bond.deductible_share(leg.taken(i), give.thing.qty), decimals) \
                if give.v >= 7 else 0
            from .arbitrators import constrained, resolver_of
            chosen = give.arbitrator if is_address(give.arbitrator) else resolver
            parties = (want.maker, give.maker)
            if chosen.lower() in {p.lower() for p in parties}:
                raise ValueError(f"the resolver {chosen} is a party to the leg on {give.offer_id[:12]} (C4)")
            if constrained(want, give):
                # §7a: the first candidate both sides admit, read now — the
                # same order the gate chose in, the clearing's own last
                picked = resolver_of(want, give, default=resolver, gate=gate, ontology=ontology,
                                     window=window)
                if picked is None:
                    raise ValueError(f"no resolver {want.maker} and {give.maker} both accept "
                                     f"(the give's {chosen} is not one)")
                chosen = picked
            cover = bool(claim_only(give)) if claim_only else False
            covered = None
            if cover:
                covered = _period(_concepts(want), span, nested=True) \
                    or _period(give.thing.concepts, span, nested=True)
            claim = int(claim_seconds)
            if want.v >= 6 and want.requires is not None and want.requires.claim_period:
                claim = want.requires.claim_period
            if give.v >= 6 and give.claim_max:
                claim = min(claim, give.claim_max)
            ladder = []
            req = want.requires
            if req is not None and req.ladder:
                price = next((q(a.price) for a in req.accepts
                              if a.unit == bond.asset.unit and set(a.concepts) <= set(bond.asset.concepts)),
                             None)
                if price is None:            # the acceptance the gate matched by subsumption:
                    price = next((q(a.price) for a in req.accepts if a.unit == bond.asset.unit), None)
                if price is not None:
                    ladder = [(int(lead), min(amount, floor_wei(q(a) / price, decimals)))
                              for lead, a in req.ladder]
            out.append({"offer_id": give.offer_id, "loop_id": proposal.circulation.loop_id,
                        "wanter": want.maker, "resolver": chosen,
                        "amount": amount,
                        "window": tuple(int(x) for x in (covered or window)),
                        "claim_seconds": claim, "ladder": ladder,
                        "claim_only": cover, "deductible": deductible,
                        "covers": covered_key if cover else "",
                        "min_challenge": int(min_challenge), "min_ruling": int(min_ruling)})
    return out


def reservation_key(offer_id: str, loop_id: str) -> str:
    """The escrow's key of one fill's reservation, keccak(offer ‖ loop) —
    what `LoopEscrow.key` computes, here without a chain call."""
    from eth_hash.auto import keccak
    return keccak(bytes.fromhex(offer_id) + bytes.fromhex(loop_id)).hex()


_NESTED_TIME = re.compile(r"time\(([^()]*)\)")


def _period(concepts, span, *, nested: bool):
    """The first time span among `concepts` that `span` reads: a top-level
    `time(...)` term, and with `nested` one inside another term too (the
    covered period of an `insure(... time(...))`); None when there is none."""
    if span is None:
        return None
    for term in concepts:
        if not isinstance(term, str):
            continue
        if term.startswith("time(") and term.endswith(")"):
            texts = [term[5:-1]]
        elif nested:
            texts = _NESTED_TIME.findall(term)
        else:
            continue
        for text in texts:
            try:
                return tuple(span(text))
            except Exception:              # noqa: BLE001 — not a span this reader knows
                continue
    return None


#: `terms(bytes32,bytes32)` as the escrows before the deductible answer it
#: (2026-09-28/29 until C5: four fields).
_LEGACY_TERMS = {
    "name": "terms", "type": "function", "stateMutability": "view",
    "inputs": [{"name": "offer", "type": "bytes32"}, {"name": "loop", "type": "bytes32"}],
    "outputs": [{"name": "claimOnly", "type": "bool"}, {"name": "minChallenge", "type": "uint64"},
                {"name": "minRuling", "type": "uint64"}, {"name": "claim", "type": "uint256"}]}


def cover_predicate(ontology, head: str = "insure"):
    """Which gives are cover, for `reservations_for`'s `claim_only`: a give
    whose thing falls under the catalogue's `insure` (one-way, as any
    category). A catalogue without the category marks nothing: a
    countersign stays possible, as before. The `insure(...)` term with its
    nested roles is C5's grammar; a plain category under `insure` is enough
    for the reservation's flag."""
    if not ontology.known(head):
        return lambda give: False

    def is_cover(give) -> bool:
        if give.kind != "give":
            return False
        for c in give.thing.concepts:
            op = ontology.operator_of(c)           # `insure(...)`: the term names its head (D4)
            if op is not None and (op == head or ontology.covers(head, op)):
                return True
        return ontology.satisfies(give.thing.concepts, (head,))
    return is_cover


def _concepts(want):
    if want.composed:
        return [c for part in want.parts for c in part.concepts]
    return list(want.thing.concepts)


def offer_key(offer_id: str) -> bytes:
    return bytes.fromhex(offer_id)


class EscrowClient:
    """`LoopEscrow` at `address` on the chain behind `rpc_url`. `key` signs
    (the giver's for deposits, the arbiter's for verdicts, the wanter's for
    a countersigned refund); reading needs none. `client` may be a web3
    instance (tests, embedders)."""

    def __init__(self, rpc_url: str, address: str, *, key: str | None = None, client=None):
        self.rpc_url, self.address, self._key, self._client = rpc_url, address, key, client

    def _web3(self):
        if self._client is None:
            try:
                from web3 import Web3
            except ImportError as exc:
                raise RuntimeError("the escrow needs web3: pip install 'loopmarket[chain]'") from exc
            self._client = Web3(Web3.HTTPProvider(self.rpc_url))
        return self._client

    def contract(self):
        return self._web3().eth.contract(address=self.address, abi=abi()["abi"])

    def account(self):
        if not self._key:
            raise ValueError("a transaction needs a key (bee_signer)")
        return self._web3().eth.account.from_key(self._key)

    def _send(self, fn, value: int = 0):
        w3 = self._web3()
        account = self.account()
        tx = {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address),
              "value": value}
        signed = account.sign_transaction(fn.build_transaction(tx))
        return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    # ---- the giver -----------------------------------------------------------

    def deposit(self, offer_id: str, amount: int, token: str | None = None) -> dict:
        """Hold `amount` (smallest units) behind the offer: the native coin,
        or an ERC-20 this key approved to the contract first."""
        c = self.contract()
        if token is None or token == NATIVE:
            return self._send(c.functions.deposit(offer_key(offer_id)), value=amount)
        return self._send(c.functions.depositToken(offer_key(offer_id), token, amount))

    def notice(self, offer_id: str) -> dict:
        return self._send(self.contract().functions.notice(offer_key(offer_id)))

    def withdraw(self, offer_id: str, amount: int) -> dict:
        return self._send(self.contract().functions.withdraw(offer_key(offer_id), amount))

    # ---- the clearing, the wanter, the resolver ------------------------------

    def reserve(self, offer_id: str, loop_id: str, wanter: str, resolver: str, amount: int, *,
                window: tuple[int, int], claim_seconds: int, ladder: list[tuple[int, int]] = (),
                claim_only: bool = False, min_challenge: int = 0, min_ruling: int = 0,
                deductible: int = 0, covers: str | bytes = b"") -> dict:
        """Reserve `amount` for one fill (the clearing's key): the leg's
        wanter and handover window (unix seconds), the resolver both
        offers declared acceptable, the claim period after the window, the
        least windows a claim must name, whether it is cover, the ladder as
        (lead seconds, amount in smallest units), descending, the
        deductible's share for this fill (C5: a ruled payout leaves it with
        the giver), and for cover the key of the reservation it covers (C5
        stage 2: the insured assigns her claim there to the insurer before
        the cover pays, and the cover nets what it already paid her)."""
        leads = [int(lead) for lead, _ in ladder]
        amounts = [int(a) for _, a in ladder]
        covers = bytes.fromhex(covers) if isinstance(covers, str) else bytes(covers)
        terms = (int(window[0]), int(window[1]), int(claim_seconds), int(min_challenge), int(min_ruling),
                 bool(claim_only), int(deductible), covers.rjust(32, b"\0") if covers else bytes(32))
        return self._send(self.contract().functions.reserve(
            offer_key(offer_id), offer_key(loop_id), wanter, resolver, amount, terms, leads, amounts))

    def cancel(self, offer_id: str, loop_id: str) -> dict:
        """The giver's cancellation: the ladder's amount to the wanter."""
        return self._send(self.contract().functions.cancel(offer_key(offer_id), offer_key(loop_id)))

    def countersign(self, offer_id: str, loop_id: str) -> dict:
        """The wanter's countersignature of delivery: the reservation returns
        now (refused on cover)."""
        return self._send(self.contract().functions.countersign(offer_key(offer_id), offer_key(loop_id)))

    def settle(self, offer_id: str, loop_id: str, to_wanter: int | None = None) -> dict:
        """Quiet after the claim period (no `to_wanter`): anyone returns the
        reservation. With `to_wanter`, this key's signature of a split — the
        wanter's or the giver's; the second matching signature settles it."""
        c = self.contract().functions
        if to_wanter is None:
            return self._send(c.settle(offer_key(offer_id), offer_key(loop_id)))
        return self._send(c.settle(offer_key(offer_id), offer_key(loop_id), int(to_wanter)))

    def assign(self, offer_id: str, loop_id: str, to: str) -> dict:
        """The wanter assigns its claim on the reservation to any key."""
        return self._send(self.contract().functions.assign(offer_key(offer_id), offer_key(loop_id), to))

    def extend_claim(self, offer_id: str, loop_id: str, seconds: int) -> dict:
        """The giver lengthens the claim period (tail cover)."""
        return self._send(self.contract().functions.extendClaim(
            offer_key(offer_id), offer_key(loop_id), int(seconds)))

    def collect(self, token: str | None = None) -> dict:
        """Collect payouts this key's address refused when they were pushed."""
        return self._send(self.contract().functions.collect(token or NATIVE))

    def hold(self, offer_id: str, loop_id: str) -> dict:
        """The resolver: a claim is open."""
        return self._send(self.contract().functions.hold(offer_key(offer_id), offer_key(loop_id)))

    def resolve(self, offer_id: str, loop_id: str, to_wanter: int) -> dict:
        """The resolver: the outcome, what the wanter gets of the reservation."""
        return self._send(self.contract().functions.resolve(offer_key(offer_id), offer_key(loop_id), to_wanter))

    # ---- reads ---------------------------------------------------------------

    def held(self, offer_id: str) -> int:
        return self.contract().functions.held(offer_key(offer_id)).call()

    def free(self, offer_id: str) -> int:
        return self.contract().functions.free(offer_key(offer_id)).call()

    def reservation(self, offer_id: str, loop_id: str) -> dict:
        c = self.contract().functions
        r = c.reservation(offer_key(offer_id), offer_key(loop_id)).call()
        try:
            t = c.terms(offer_key(offer_id), offer_key(loop_id)).call()
        except Exception as exc:                # noqa: BLE001 — an escrow from before the deductible
            if "decode" not in str(exc).lower():
                raise
            legacy = self._web3().eth.contract(address=self.address, abi=[_LEGACY_TERMS])
            t = list(legacy.functions.terms(offer_key(offer_id), offer_key(loop_id)).call()) + [0]
        return {"wanter": r[0], "resolver": r[1], "amount": r[2], "window": (r[3], r[4]),
                "claim_until": r[5], "held": r[6], "settled": r[7], "ladder": list(zip(r[8], r[9])),
                "claim_only": t[0], "min_challenge": t[1], "min_ruling": t[2], "claim": t[3],
                "deductible": t[4]}

    def cover_of(self, offer_id: str, loop_id: str) -> dict:
        """What a cover reservation covers (the key, or None), and what this
        reservation paid its wanter at settlement (C5 stage 2)."""
        covers, paid_to, paid = self.contract().functions.coverOf(offer_key(offer_id), offer_key(loop_id)).call()
        return {"covers": None if int.from_bytes(covers, "big") == 0 else bytes(covers).hex(),
                "paid_to": paid_to, "paid_to_wanter": paid}

    def owed(self, to: str, token: str | None = None) -> int:
        """Payouts `to`'s address refused, waiting for its `collect`."""
        return self.contract().functions.owed(token or NATIVE, to).call()

    def subject(self, offer_id: str, loop_id: str) -> bytes:
        """The reservation's key — the `subject` a generic resolver (factbond's
        `Assertions`) names in a claim about this fill."""
        return self.contract().functions.key(offer_key(offer_id), offer_key(loop_id)).call()

    def deposit_of(self, offer_id: str) -> dict:
        giver, token, amount, released = self.contract().functions.deposits(offer_key(offer_id)).call()
        return {"giver": giver, "token": token, "amount": amount, "released": released}

    def events(self, name: str, from_block: int = 0) -> list[dict]:
        """The contract's `name` events (`Reserved`, `Settled`, `Deposited`,
        ...) as dicts of their arguments plus `block` and `time` (the
        block's timestamp), bytes32 arguments as hex — the escrow's history,
        read from its log alone."""
        w3, times, out = self._web3(), {}, []
        for log in getattr(self.contract().events, name)().get_logs(from_block=from_block):
            n = log["blockNumber"]
            if n not in times:
                times[n] = w3.eth.get_block(n)["timestamp"]
            args = {k: (v.hex() if isinstance(v, (bytes, bytearray)) else v) for k, v in dict(log["args"]).items()}
            out.append({**args, "block": n, "time": times[n]})
        return out
