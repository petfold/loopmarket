"""Detached signatures (planned U8): recoverable, fail-closed, outside identity."""

import pytest

pytest.importorskip("eth_keys")

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    GeoDisc, OfferRegistry, Thing, TimeWindow, ask,
    maker_address, recover_maker, sign_offer, verify_offer_sig,
)

W = dict(
    service=TimeWindow(1_000, 2_000),
    where=GeoDisc(46.0, 14.0, 1_000),
    valid=TimeWindow(0, 10_000),
)
KEY = "01" * 32
OTHER_KEY = "02" * 32


def test_sign_and_recover_roundtrip():
    maker = maker_address(KEY)
    offer = ask(maker, Thing(("x",)), 10, nonce=7, **W)
    sig = sign_offer(offer, KEY)
    assert recover_maker(offer.offer_id, sig) == maker
    assert verify_offer_sig(offer, sig)
    assert not verify_offer_sig(offer, sign_offer(offer, OTHER_KEY))
    assert not verify_offer_sig(offer, "0xnot-a-signature")


def test_registry_stores_only_signatures_that_recover_to_the_maker():
    maker = maker_address(KEY)
    offer = ask(maker, Thing(("x",)), 10, nonce=7, **W)
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
    offer = ask(maker, Thing(("x",)), 10, nonce=7, **W)
    registry = OfferRegistry(RecordStore(MemoryBytesStore()))
    oid = registry.publish(offer)
    record_before = registry.store.get(f"offer/{oid}")
    registry.attach_signature(oid, sign_offer(offer, KEY))
    assert registry.get(oid).offer_id == oid
    assert registry.store.get(f"offer/{oid}") == record_before
