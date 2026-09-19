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

`EscrowClient` sends and reads; web3 loads lazily behind the `chain`
extra (boundary B2). The verdicts (`reserve`, `release`, `refund` by the
arbiter) are the clearing contract's arbiter hook's shape; wiring
`BeatClearing`'s finalization to `reserve` is the next step, and until
then the notice period on withdrawal is the guard.
"""

from __future__ import annotations

import json
from fractions import Fraction

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

    # ---- the arbiter and the wanter ------------------------------------------

    def reserve(self, offer_id: str, loop_id: str, amount: int) -> dict:
        return self._send(self.contract().functions.reserve(offer_key(offer_id), offer_key(loop_id), amount))

    def release(self, offer_id: str, loop_id: str, to: str, amount: int, reason: str = "") -> dict:
        return self._send(self.contract().functions.release(
            offer_key(offer_id), offer_key(loop_id), to, amount, reason))

    def refund(self, offer_id: str, loop_id: str, wanter: str, reason: str = "") -> dict:
        return self._send(self.contract().functions.refund(
            offer_key(offer_id), offer_key(loop_id), wanter, reason))

    # ---- reads ---------------------------------------------------------------

    def held(self, offer_id: str) -> int:
        return self.contract().functions.held(offer_key(offer_id)).call()

    def free(self, offer_id: str) -> int:
        return self.contract().functions.free(offer_key(offer_id)).call()

    def reserved(self, offer_id: str, loop_id: str) -> int:
        c = self.contract()
        return c.functions.reserved(c.functions.key(offer_key(offer_id), offer_key(loop_id)).call()).call()

    def deposit_of(self, offer_id: str) -> dict:
        giver, token, amount, released = self.contract().functions.deposits(offer_key(offer_id)).call()
        return {"giver": giver, "token": token, "amount": amount, "released": released}
