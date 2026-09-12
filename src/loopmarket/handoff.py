"""Sealed handoffs: how the exact address reaches the cleared courier.

Matching runs on cells; a delivery needs a door. The address is settlement
data on the maker's place node, never vocabulary, never in the record
(`docs/plans/P1-spacetime-terms.md` §4, Peter 2026-09-12). After a loop
clears, the place-owner's *client* writes one record into its own book,
`handoff/<loop_id>/<offer_id>`, whose payload is the text encrypted to the
leg counterparty's public key — a sidecar beside `sig/`, never in
identity, merged as OR-set presence, carried by aggregators unread. The
counterparty reads the fold they already follow and opens it. No side
channel, no message: the book is the channel.

Keys are the ones makers already hold. The `sig` extra's secp256k1 key
owns the maker's feed and signs their offers; a public key recovers from
any detached signature (`sigs.recover_public_key`), so there is no key
registry. The sealing is ECIES over that curve: an ephemeral key, ECDH,
HKDF-SHA256, AES-256-GCM with the ephemeral public key as associated data.
A fresh ephemeral key per record means equal addresses never produce
equal ciphertexts — deliberate here (this is not a convergent store; a
sidecar is written once by one party), unlike ontodag's deterministic
encrypted store, which is the later seam for a whole private place layer.

Against harvesting (offering courier service only to learn addresses):
disclosure follows *obligation* — the record exists only for a cleared
leg, under P3 only once the courier's bond is escrowed; *timing* — the
client may write it when the service window is near; and *no address at
all* — `oracle="locker"` or a public pickup node. Everything imports
lazily: the core works without any of it (boundary B1).
"""

from __future__ import annotations

import os
from typing import Any

_INFO = b"loopmarket-handoff-v1"
VERSION = 1


def _crypto():
    try:
        from coincurve import PrivateKey, PublicKey
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError as exc:  # pragma: no cover - optional layer
        raise RuntimeError(
            "sealed handoffs need the `sig` extra (coincurve, cryptography)"
        ) from exc
    return PrivateKey, PublicKey, AESGCM, HKDF, hashes


def _key_bytes(private_key_hex: str) -> bytes:
    hex_ = private_key_hex[2:] if private_key_hex.startswith("0x") else private_key_hex
    return bytes.fromhex(hex_)


def _derive(shared: bytes, epk: bytes) -> bytes:
    _, _, _, HKDF, hashes = _crypto()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=epk,
                info=_INFO).derive(shared)


def public_key_of(private_key_hex: str) -> bytes:
    """The compressed (33-byte) public key of a maker's private key."""
    PrivateKey, _, _, _, _ = _crypto()
    return PrivateKey(_key_bytes(private_key_hex)).public_key.format(compressed=True)


def seal(text: str, recipient_public_key: bytes) -> dict[str, Any]:
    """Encrypt `text` so that only the holder of the matching private key
    reads it. `recipient_public_key` is compressed or uncompressed SEC1
    bytes (what `sigs.recover_public_key` returns)."""
    PrivateKey, PublicKey, AESGCM, _, _ = _crypto()
    ephemeral = PrivateKey()
    recipient = PublicKey(recipient_public_key).format(compressed=True)
    shared = ephemeral.ecdh(recipient)
    epk = ephemeral.public_key.format(compressed=True)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive(shared, epk)).encrypt(nonce, text.encode("utf-8"), epk)
    return {"v": VERSION, "epk": epk.hex(), "nonce": nonce.hex(),
            "ct": ciphertext.hex()}


def open_(record: dict[str, Any], private_key_hex: str) -> str:
    """Decrypt a sealed record with the recipient's private key. Raises on
    a wrong key or a tampered record (AES-GCM authenticates)."""
    PrivateKey, _, AESGCM, _, _ = _crypto()
    if record.get("v") != VERSION:
        raise ValueError(f"unknown handoff record version: {record.get('v')!r}")
    epk = bytes.fromhex(record["epk"])
    shared = PrivateKey(_key_bytes(private_key_hex)).ecdh(epk)
    plaintext = AESGCM(_derive(shared, epk)).decrypt(
        bytes.fromhex(record["nonce"]), bytes.fromhex(record["ct"]), epk)
    return plaintext.decode("utf-8")
