"""Detached signatures (planned U8): recoverable, fail-closed, outside identity."""

import sys

import pytest

pytest.importorskip("coincurve")

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    OfferRegistry, Thing, TimeWindow, give,
    maker_address, recover_maker, sign_offer, verify_offer_sig,
)

W = dict(valid=TimeWindow(0, 10_000))
KEY = "01" * 32
OTHER_KEY = "02" * 32


def test_sign_and_recover_roundtrip():
    maker = maker_address(KEY)
    offer = give(maker, Thing(("x",)), 10, nonce=7, **W)
    sig = sign_offer(offer, KEY)
    assert recover_maker(offer.offer_id, sig) == maker
    assert verify_offer_sig(offer, sig)
    assert not verify_offer_sig(offer, sign_offer(offer, OTHER_KEY))
    assert not verify_offer_sig(offer, "0xnot-a-signature")


def test_registry_stores_only_signatures_that_recover_to_the_maker():
    maker = maker_address(KEY)
    offer = give(maker, Thing(("x",)), 10, nonce=7, **W)
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    oid = registry.publish(offer)
    assert registry.signature(oid) is None
    with pytest.raises(ValueError):
        registry.attach_signature(oid, sign_offer(offer, OTHER_KEY))
    registry.attach_signature(oid, sign_offer(offer, KEY))
    registry.commit()
    assert recover_maker(oid, registry.signature(oid)) == maker


def test_signature_never_enters_identity():
    # detached means detached: attaching the sidecar moves neither the
    # offer's id nor its stored record — only the sig/ key appears
    maker = maker_address(KEY)
    offer = give(maker, Thing(("x",)), 10, nonce=7, **W)
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    oid = registry.publish(offer)
    record_before = registry.store.get(f"offer/{oid}")
    registry.attach_signature(oid, sign_offer(offer, KEY))
    assert registry.get(oid).offer_id == oid
    assert registry.store.get(f"offer/{oid}") == record_before


# -- the stored form, unchanged since eth-keys (2026-10-08) --------------------
#
# Computed with eth-keys before the move onto swarmfs's signer: the address,
# the offer signature over OID, the compressed public key it recovers, the
# contact card, and a door witness's response to sha256(b"challenge") bound
# to OID. Signatures already in books must keep verifying, and new ones must
# be the same bytes.

import hashlib  # noqa: E402

from loopmarket import sigs, witness  # noqa: E402

OID = "3b3806a2e0303869f29bacb8cf52e5806f70b477d8909401cd47275785553890"
CHALLENGE = hashlib.sha256(b"challenge").hexdigest()
ETH_KEYS = [
    ("01" * 32,
     "0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1",
     "0x0acd72ebaadcd3dfdbb3257edee8a362fc2cab1d207b2eb17525346dc95c5a14240990587100c80397a40cde4790d5b4ce8b2ef5a84dec79cb0faf21585b4f7201",
     "031b84c5567b126440995d3ed5aaba0565d71e1834604819ff9c17f5e9d5dd078f",
     "0xaa98649f019d1890c21c7676ddbdd282f05f44c231abbd64c2f1cd264f611d2520b5d174b6cf6db4fdcbad192cd880a98a329c439473afdd86e8831f847727cf01",
     "0xba425310dbf9945f4f5bca6367dd7608a7f1f4f87fbbabab2ba0d2946cbe4b7f79590b0cbf4b40a0d409aaaf873b90e3e0a3aed02625c22e66d6d4aa6c9c5e9300"),
    ("02" * 32,
     "0x5050A4F4b3f9338C3472dcC01A87C76A144b3c9c",
     "0xb3d696b04f8c27485e9d1b0a3bf7ecd3428bd9c3e825e2874996802a9bf776f052350be2ffe6a3d2376d6e3339e39ad6dd949a3793c91eeb28c267c92536ecba01",
     "024d4b6cd1361032ca9bd2aeb9d900aa4d45d9ead80ac9423374c451a7254d0766",
     "0xe05c43f12c64042a2c5ad3f0b4051e100d712edf94354a5f645cb37307025eed0b6e5a625bb994fd812f4640462d5440c44d90d485085a8cc1dfb03cc1353dee01",
     "0x1aaf87b5f67ce1f8b57f490b855f64e399a5a084597f5ed7f6c9f4253304b0fa4d7bc3bcdd752c1587d5e18784d785e84eca85bc944d71860d0e7d6ea9e61acb00"),
    ("634fb5a872396d9693e5c9f9d7233cfa93f395c093371017ff44aa9ae6564cdd",
     "0x8D3766440f0d7B949a5E32995D09619A7F86e632",
     "0xeecd14cbca8c5521ca7b0771c6d1feabd3949e91263ee3de9197f6cc6b6af92878e6e4fc3c317b467d309f4c75df05d2733381eaf777d5bedbd7235054cf928601",
     "03c32bb011339667a487b6c1c35061f15f7edc36aa9a0f8648aba07a4b8bd741b4",
     "0xb9685a7bcb0dff77554586b71c0f1441b32b3302e626c45272b119ead4bc093b76c91601ae8f39332f1435651553b5bfc2d32fd7c639672391e4aa116aff83a701",
     "0xdabdf8c693d9bfee720bf985c39ec94050950aee71fdd7001405cced91518f4256dafb3e74b3e7f8695025a3d7570fdb46e20a70ee5ccc556f12d5ea6b27542201"),
]


class _Id:
    offer_id = OID


@pytest.mark.parametrize("key,address,sig,public,card,response", ETH_KEYS)
def test_signing_is_byte_identical_to_eth_keys(key, address, sig, public, card,
                                               response):
    assert sigs.maker_address(key) == address
    assert sigs.sign_offer(_Id, key) == sig
    assert sigs.sign_contact_card(key) == (address, card)
    assert witness.respond(CHALLENGE, OID, key) == response


@pytest.mark.parametrize("coincurve_present", [True, False])
@pytest.mark.parametrize("key,address,sig,public,card,response", ETH_KEYS)
def test_stored_signatures_still_recover(monkeypatch, coincurve_present, key,
                                         address, sig, public, card, response):
    if not coincurve_present:  # a reader with no compiled library
        monkeypatch.setitem(sys.modules, "coincurve", None)
    assert sigs.recover_maker(OID, sig) == address
    assert sigs.recover_public_key(OID, sig).hex() == public
    assert sigs.contact_card_public_key(address, card).hex() == public
    assert witness.signer(CHALLENGE, OID, response) == address


def test_only_the_stored_form_is_accepted():
    key, address, sig, *_ = ETH_KEYS[0]
    raw = bytes.fromhex(sig[2:])
    as_bee = "0x" + (raw[:64] + bytes([raw[64] + 27])).hex()  # v 27/28
    for bad in (as_bee, sig[:-2], sig + "00", "0xnot-a-signature"):
        with pytest.raises(ValueError):
            sigs.recover_maker(OID, bad)
    assert witness.signer(CHALLENGE, OID, as_bee) == ""
