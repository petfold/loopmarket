"""Detached offer signatures: the off-feed half of authenticity (planned U8).

In per-maker books, *feed ownership* is the primary authenticity: an offer
is the maker's because it arrived on the maker's signed feed. This module is
the secondary layer — a detached secp256k1 signature over the 32-byte
`offer_id`, recoverable to `maker` — for offers circulating outside their
home feed: gossip, solver forwarding, registry events, P2 calldata
(docs/plans/P1-federated-book.md §1).

Detached means detached: nothing here ever enters `canonical_bytes()`.
Honest holders of one offer may carry or lack the sidecar, and the treaty
with ontodag is that nothing varying between honest replicas may enter
identity — so offer ids stay stable and book roots stay pure. The registry
stores signatures *beside* the offer under `sig/<offer_id>` and refuses one
that does not recover to the offer's maker (fail closed, U7's spirit).

Makers are Ethereum-style addresses: the same secp256k1 key owns the
maker's Swarm feed, recovers from these signatures, and is the address
P2's on-chain clearing sees — one identity, three roles. The aggregator's
fold rule (an offer from a foreign feed without a valid signature never
enters the fold) calls this module (`federation.Aggregator`).

The cryptography is libsecp256k1's, through swarmfs's shared signer
(`swarmfs.signer`, the same one that signs the maker's feed); this module
owns only the encoding. A signature is stored as eth-keys wrote it before
2026-10-08: `0x`, then r ‖ s ‖ v in hex with v 0 or 1 — unchanged byte for
byte (tests/test_sigs.py pins eth-keys' own outputs). Recovery needs no
compiled library; signing does. The signer loads lazily inside each
function: signing is a federation-edge concern, never a requirement of the
model (boundary B1) — install the `sig` extra to use it.
"""

from __future__ import annotations

from .schema import Offer

_EXTRA = "pip install 'loopmarket[sig]'"


def _signer():
    try:
        from swarmfs import signer
    except ImportError as e:  # pragma: no cover - exercised only without extra
        raise RuntimeError(f"signatures need swarmfs's signer: {_EXTRA}") from e
    if not hasattr(signer, "recover_hash"):  # pragma: no cover - old swarmfs
        raise RuntimeError(f"signatures need swarmfs 0.14.0 or later: {_EXTRA}")
    return signer


def _key(private_key_hex: str):
    S = _signer()
    try:
        return S.Signer(private_key_hex)
    except ImportError as e:  # pragma: no cover - exercised only without extra
        raise RuntimeError(f"signing needs coincurve: {_EXTRA}") from e


def _to_hex(signature: bytes) -> str:
    """The stored form: `0x` and r ‖ s ‖ v with v 0 or 1."""
    return "0x" + (signature[:64] + bytes([signature[64] - 27])).hex()


def _from_hex(sig_hex: str) -> bytes:
    """Bytes of a stored signature; only the stored form is accepted."""
    sig = bytes.fromhex(_strip(sig_hex))
    if len(sig) != 65 or sig[64] not in (0, 1):
        raise ValueError("a signature is 65 bytes ending in v = 0 or 1")
    return sig


def _sign(private_key_hex: str, hash32: bytes) -> str:
    return _to_hex(_key(private_key_hex).sign_hash(hash32))


def _recover_key(hash32: bytes, sig_hex: str) -> bytes:
    """The signer's uncompressed public key."""
    return _signer().recover_hash_key(_from_hex(sig_hex), hash32)


def _address(public_key: bytes) -> str:
    S = _signer()
    return S.checksum_address(S.address_of(public_key))


def maker_address(private_key_hex: str) -> str:
    """The Ethereum-style address this key signs as — use it as `maker`."""
    return _signer().checksum_address(_key(private_key_hex).address)


def sign_offer(offer: Offer, private_key_hex: str) -> str:
    """A recoverable 65-byte signature (hex) over the offer's 32-byte id.

    Signing the id rather than the record is equivalent (the id *is* the
    SHA-256 of the canonical bytes) and lets verifiers work from the id
    alone — no record hydration to check who is speaking.
    """
    return _sign(private_key_hex, bytes.fromhex(offer.offer_id))


def recover_maker(offer_id: str, sig_hex: str) -> str:
    """The address that signed this offer id."""
    return _address(_recover_key(bytes.fromhex(offer_id), sig_hex))


def verify_offer_sig(offer: Offer, sig_hex: str) -> bool:
    """Does the signature recover to the offer's own maker?"""
    try:
        return recover_maker(offer.offer_id, sig_hex) == offer.maker
    except Exception:  # malformed signature: invalid, never an error
        return False


def recover_public_key(offer_id: str, sig_hex: str) -> bytes:
    """The signer's compressed public key, from a detached signature over
    an offer id — what `handoff.seal` encrypts to. No key registry: any
    signature a maker left is their public key."""
    return _signer().compressed(_recover_key(bytes.fromhex(offer_id), sig_hex))


def _strip(hex_: str) -> str:
    return hex_[2:] if hex_.startswith("0x") else hex_


# -- contact cards (2026-10-01) ------------------------------------------------------
#
# Sealing to a key (a handoff, a notice, a claim to an arbitrator) needs its
# public key, recovered from any signature it left. A maker leaves one on
# every offer; an arbitrator or a register may have no offer at all. A key
# card is the smallest such signature: over a fixed message naming the key's
# own address, so it says nothing but "this public key is mine", and anyone
# checks it with no store. Why not a key registry: the book is already the
# channel, and a card in the key's own book needs nobody's permission.

CONTACT_CARD_DOMAIN = b"loopmarket contact card\n"


def contact_card_hash(address: str) -> bytes:
    """The 32-byte message a contact card signs: the domain and the address."""
    import hashlib
    return hashlib.sha256(CONTACT_CARD_DOMAIN + address.lower().encode("ascii")).digest()


def sign_contact_card(private_key_hex: str) -> tuple[str, str]:
    """(address, signature hex) — this key's card."""
    address = maker_address(private_key_hex)
    return address, _sign(private_key_hex, contact_card_hash(address))


def contact_card_public_key(address: str, sig_hex: str) -> bytes:
    """The compressed public key a card proves for `address`; raises when
    the signature does not recover to that address (a card for another key)."""
    public = _recover_key(contact_card_hash(address), sig_hex)
    if _address(public).lower() != address.lower():
        raise ValueError("the contact card does not recover to its address")
    return _signer().compressed(public)
