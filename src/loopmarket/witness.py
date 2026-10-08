"""The door's witness types (R7, 2026-09-29; `counterparty-gate.md` §7,
plan D8): binding the key a statement names to the person at the handover.

A statement binds a *key*; the person at the door must control it, and the
counterparty must recognise them. Two witness types enter the roster the
way every type does (`P3-guarantee-coupling.md` §4: the roster in factbond's
evidence policy, clearing's verifiable set, the settlement check here):

- `possession` — the counterparty's device draws a fresh challenge, the
  giver's key signs it together with the id it vouches for (the offer, or
  the statement the gate read), and the device accepts the response once:
  nothing reusable exists, so a copied code dies at once;
- `photo-match` — possession, plus the photo the attester bound to the key
  at issuance: its salted commitment rides in the presentation, the photo
  and salt are disclosed to the counterparty's device at the door, and the
  counterparty confirms the face. That hands the counterparty a provable
  link from the face to the key and its history (THREATS T19, 2026-09-29):
  possession is the default, photo the opt-in a requirer asks for only
  where the stakes need it.

A third type, `registry-transfer(ID)` (I4, 2026-09-29 night;
`items-and-ownership.md` §5.2), is not the door's: for land and vehicles
the register *is* the title, so the leg is performed when the register
named ID shows every item the give names held by the wanter — a failed
transfer is non-performance. The register is named in the type itself, as
a term names its argument: the wanter accepts exactly the registers she
names, and the record needs no field for it.

A *door level* is a cumulative category (`DOOR_LEVELS`):
`door-at-least-possession` is met by possession or photo-match,
`door-at-least-photo` by photo-match alone. The command line takes the
level and writes the types it stands for into the record (2026-10-01,
Peter): the chain checks a give's witness type against a want's list by
exact name, so a level's name in a record would refuse an honest leg on
chain. A want lists today's types and lapses with its validity; a new door
type joins `DOOR_LEVELS`, and later wants list it. `accepted_types` still
reads a level's name, for a record that carries one. `countersign_ready`
is the settlement check: a leg whose give declares a door type may be
countersigned only once its witness has been produced. hansa's handover
app is the device side (`hansa.binding`); the protocol — what is signed,
what is spent, what opens — is fixed here, where clearing and settlement
read it. Signatures are `sigs`' (B1: loaded lazily).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

POSSESSION = "possession"
PHOTO_MATCH = "photo-match"
DOOR_TYPES = (POSSESSION, PHOTO_MATCH)
REGISTRY_TRANSFER = "registry-transfer"

#: a door level -> the witness types that meet it (cumulative: a higher
#: level's type meets every lower level)
DOOR_LEVELS = {
    "door-at-least-possession": (POSSESSION, PHOTO_MATCH),
    "door-at-least-photo": (PHOTO_MATCH,),
}


def accepted_types(names) -> set[str]:
    """The witness types a requirement's `oracles` accepts: a door level
    stands for every type that meets it, any other name for itself."""
    out: set[str] = set()
    for n in names:
        out.update(DOOR_LEVELS.get(n, (n,)))
    return out


def digest(challenge: str, bound_id: str) -> str:
    """What the key signs: the challenge and the id it vouches for."""
    return hashlib.sha256(bytes.fromhex(challenge) + bytes.fromhex(bound_id)).hexdigest()


def respond(challenge: str, bound_id: str, private_key_hex: str) -> str:
    """The giver's device: sign the challenge with the bound id."""
    from .sigs import _sign
    return _sign(private_key_hex, bytes.fromhex(digest(challenge, bound_id)))


def signer(challenge: str, bound_id: str, response: str) -> str:
    """Who signed a response, or "" for a malformed one."""
    try:
        from .sigs import _address, _recover_key
        return _address(_recover_key(bytes.fromhex(digest(challenge, bound_id)), response))
    except Exception:  # noqa: BLE001 — malformed: invalid, never an error
        return ""


class DoorCheck:
    """The counterparty's device: issues challenges and spends each on the
    first response, right or wrong."""

    def __init__(self) -> None:
        self._open: set[str] = set()

    def challenge(self) -> str:
        c = secrets.token_hex(32)
        self._open.add(c)
        return c

    def possession(self, challenge: str, response: str, bound_id: str, key: str) -> bool:
        """The response signs this challenge and id by `key`, and the
        challenge was issued here and not spent: a replay, another key, or
        a challenge from elsewhere fails."""
        if challenge not in self._open:
            return False
        self._open.discard(challenge)
        return signer(challenge, bound_id, response).lower() == key.lower()


def photo_commitment(photo: bytes, salt: bytes) -> str:
    """The attester's salted hash of the photo it bound to the key — all
    the public record says of the face."""
    return hashlib.sha256(salt + photo).hexdigest()


def photo_opens(commitment: str, photo: bytes, salt: bytes) -> bool:
    return hmac.compare_digest(photo_commitment(photo, salt), commitment)


def transfer_register(oracle: str) -> str | None:
    """The register a `registry-transfer(ID)` witness names, else None."""
    head = REGISTRY_TRANSFER + "("
    if isinstance(oracle, str) and oracle.startswith(head) and oracle.endswith(")"):
        rid = oracle[len(head):-1].strip()
        return rid if rid and "(" not in rid and ")" not in rid and " " not in rid else None
    return None


def transfer_faults(give, wanter: str, register, *, since: int = 0) -> list[str]:
    """I4's settlement check: why the register does not (yet) show `give`
    performed to `wanter` — every item the give names held by the wanter,
    recorded at or after `since` (the loop's clearing) — or [] when it does.
    A give naming no item has nothing a register could transfer, and an
    unread register shows nothing (U7)."""
    from .items import ids
    items = ids(give.thing.concepts)
    if not items:
        return ["the give names no item for a register to transfer"]
    if register is None:
        return [f"the register {transfer_register(give.oracle)} is not read"]
    out = []
    for h in items:
        rec = register.holder(h)
        if rec is None or rec["holder"].lower() != wanter.lower():
            out.append(f"item {h[:12]} is not held by {wanter} in the register")
        elif rec["at"] < since:
            out.append(f"item {h[:12]} was recorded to {wanter} before the loop cleared")
    return out


def countersign_ready(give, *, possession: bool = False, photo_confirmed: bool = False,
                      transferred: bool = False) -> str:
    """The settlement check (R7): what the wanter's client still needs
    before it may countersign `give`'s leg, or "" when nothing. A give that
    declares `possession` needs a spent, valid challenge–response; one that
    declares `photo-match` needs that and the counterparty's confirmation of
    the face the commitment opened to; `countersign` itself needs nothing
    more; a type this module does not know is never ready (U7)."""
    kind = give.oracle
    if kind == "countersign":
        return ""
    if kind == POSSESSION:
        return "" if possession else "the giver's key has not answered a fresh challenge"
    if kind == PHOTO_MATCH:
        if not possession:
            return "the giver's key has not answered a fresh challenge"
        return "" if photo_confirmed else "the face has not been confirmed against the committed photo"
    if transfer_register(kind):
        return "" if transferred else f"the register {transfer_register(kind)} has not shown the transfer"
    return f"no settlement check for the witness type {kind!r}"
