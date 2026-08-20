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
maker's Swarm feed, recovers from these signatures, and will be the address
P2's on-chain settlement sees — one identity, three roles. The aggregator's
fold rule (an offer from a foreign feed without a valid signature never
enters the fold) lands with the P1 aggregator; this module is the primitive
it will call.

eth-keys loads lazily inside each function: signing is a federation-edge
concern, never a requirement of the model (boundary B1) — install the
`sig` extra to use it.
"""

from __future__ import annotations

from .schema import Offer


def _keys():
    try:
        from eth_keys import keys
    except ImportError as e:  # pragma: no cover - exercised only without extra
        raise RuntimeError(
            "detached offer signatures need eth-keys: "
            "pip install 'loopmarket[sig]'"
        ) from e
    return keys


def _key_bytes(private_key_hex: str) -> bytes:
    return bytes.fromhex(private_key_hex.removeprefix("0x"))


def maker_address(private_key_hex: str) -> str:
    """The Ethereum-style address this key signs as — use it as `maker`."""
    keys = _keys()
    return keys.PrivateKey(_key_bytes(private_key_hex)) \
        .public_key.to_checksum_address()


def sign_offer(offer: Offer, private_key_hex: str) -> str:
    """A recoverable 65-byte signature (hex) over the offer's 32-byte id.

    Signing the id rather than the record is equivalent (the id *is* the
    SHA-256 of the canonical bytes) and lets verifiers work from the id
    alone — no record hydration to check who is speaking.
    """
    keys = _keys()
    key = keys.PrivateKey(_key_bytes(private_key_hex))
    return key.sign_msg_hash(bytes.fromhex(offer.offer_id)).to_hex()


def recover_maker(offer_id: str, sig_hex: str) -> str:
    """The address that signed this offer id."""
    keys = _keys()
    sig = keys.Signature(signature_bytes=_key_bytes(sig_hex))
    return sig.recover_public_key_from_msg_hash(
        bytes.fromhex(offer_id)
    ).to_checksum_address()


def verify_offer_sig(offer: Offer, sig_hex: str) -> bool:
    """Does the signature recover to the offer's own maker?"""
    try:
        return recover_maker(offer.offer_id, sig_hex) == offer.maker
    except Exception:  # malformed signature: invalid, never an error
        return False
