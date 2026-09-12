"""Sealed handoffs (docs/plans/P1-spacetime-terms.md §4, Peter 2026-09-12):
the address is settlement text on the place node; after clearing it reaches
the leg counterparty through the book, sealed to the public key their own
signature reveals. No side channel; the fill record is the notification."""

import json

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import OfferRegistry, Thing, TimeWindow, give, want
from loopmarket.federation import CLEARING, MAKER, Aggregator
from loopmarket.handoff import open_, public_key_of, seal
from loopmarket.sigs import maker_address, recover_public_key, sign_offer

KEY_A, KEY_B = "11" * 32, "22" * 32
A, B = maker_address(KEY_A), maker_address(KEY_B)
V = dict(valid=TimeWindow(0))


def test_seal_and_open_round_trip():
    record = seal("Trubarjeva 12, 4th floor", public_key_of(KEY_B))
    assert set(record) >= {"v", "epk", "nonce", "ct"}
    assert "Trubarjeva" not in json.dumps(record)
    assert open_(record, KEY_B) == "Trubarjeva 12, 4th floor"
    with pytest.raises(Exception):
        open_(record, KEY_A)                       # not the recipient
    with pytest.raises(Exception):
        open_(dict(record, ct=record["ct"][:-2] + "00"), KEY_B)   # tampered
    assert seal("x", public_key_of(KEY_B)) != seal("x", public_key_of(KEY_B))


def test_public_key_recovers_from_an_offer_signature():
    """No key registry: any signature a maker left is their public key."""
    o = give(B, Thing(("ride",)), 4, **V)
    assert recover_public_key(o.offer_id, sign_offer(o, KEY_B)) == public_key_of(KEY_B)


def _cleared_pair(blobs):
    w = want(A, Thing(("ride", "where(u24)")), 5, **V)
    g = give(B, Thing(("ride", "where(u24)")), 4, **V)
    book_a, book_b = OfferRegistry(RecordStore(blobs)), OfferRegistry(RecordStore(blobs))
    book_a.publish(w); book_a.attach_signature(w.offer_id, sign_offer(w, KEY_A)); book_a.commit()
    book_b.publish(g); book_b.attach_signature(g.offer_id, sign_offer(g, KEY_B)); book_b.commit()
    clearing = OfferRegistry(RecordStore(blobs))
    clearing.absorb(book_a); clearing.absorb(book_b)
    clearing.mark_filled([g.offer_id, w.offer_id], "loop-1",
                         {"legs": [{"give": g.offer_id, "want": w.offer_id, "rate": 1.25}],
                          "surplus": 0.25})
    clearing.commit()
    return w, g, book_a, book_b, clearing


def test_registry_handoff_needs_the_fill_and_folds_only_for_its_owner():
    blobs = MemoryBytesStore()
    w, g, book_a, book_b, clearing = _cleared_pair(blobs)
    record = dict(seal("Trubarjeva 12", recover_public_key(g.offer_id, book_b.signature(g.offer_id))),
                  **{"from": A, "to": B})
    with pytest.raises(ValueError):                # my book holds no fill
        book_a.attach_handoff("loop-1", w.offer_id, record)
    with pytest.raises(ValueError):                # not this loop
        book_a.attach_handoff("loop-2", w.offer_id, record, fold=clearing)
    book_a.attach_handoff("loop-1", w.offer_id, record, fold=clearing)
    book_a.commit()
    assert book_a.handoff("loop-1", w.offer_id) == record
    assert [(l, o) for l, o, _ in book_a.handoffs()] == [("loop-1", w.offer_id)]
    assert open_(record, KEY_B) == "Trubarjeva 12"
    # a forged handoff in B's book about A's offer
    book_b.store.put(f"handoff/loop-1/{w.offer_id}", dict(record, **{"from": B}))
    book_b.commit()
    agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="agg")
    agg.announce(A, book_a.store, role=MAKER)
    agg.announce(B, book_b.store, role=MAKER)
    agg.announce("clr", clearing.store, role=CLEARING)
    manifest = agg.fold()
    folded = OfferRegistry(RecordStore(blobs, root=manifest.book_root))
    assert folded.handoff("loop-1", w.offer_id) == record        # A's, admitted
    prov = RecordStore(blobs, root=manifest.provenance_root)
    assert prov.get(f"reject/{B}/handoff/loop-1/{w.offer_id}")["reason"] \
        == "handoff for an offer this book does not own"


# ------------------------------------------------------------------ the CLI

from test_cli import Runner, _od_with_prelude, env  # noqa: E402,F401  (fixture)


def test_watch_reports_fills_seals_and_opens_handoffs(env, tmp_path, monkeypatch):
    """Amara names her home with an address; Bruno is the courier. Clearing
    fills both; Amara's `watch` seals the address to Bruno's key (from the
    signature on his offer); Bruno's `watch` opens it. Nobody sent anything."""
    _od_with_prelude(tmp_path / "town.od", [("ride", []), ("piano-lesson", [])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "town.od"))
    monkeypatch.delenv("LOOP_MAKER")               # identity = the signer's address

    def as_(key):
        monkeypatch.setenv("BEE_SIGNER", key)

    run = Runner()
    as_(KEY_A)
    run.ok("place", "home", "46.05,14.50,5km", "Trubarjeva", "12,", "4th", "floor")
    out = run.ok("want", "ride", "where(home)", "5")
    assert "note     handoff where(home): Trubarjeva 12, 4th floor — sealed" in out
    want_id = out.strip().splitlines()[-1]
    out = run.ok("give", "piano-lesson", "where(home)", "4")
    give_id = out.strip().splitlines()[-1]
    run.ok("handoff", give_id[:12], "Ring", "twice")   # overrides the place text
    as_(KEY_B)
    run.ok("place", "depot", "46.05,14.50,5km")         # no address
    run.ok("give", "ride", "where(depot)", "4")
    run.ok("want", "piano-lesson", "where(depot)", "5")
    assert run("watch", "--once")[0] == 1               # nothing cleared yet
    run.ok("clearing")
    # Amara: two fills reported, two handoffs sealed to Bruno
    as_(KEY_A)
    out = run.ok("watch", "--once")
    assert out.count("filled   ") == 2 and f"{A} receives ride from {B}" in out
    assert out.count(f"sealed to {B}") == 2
    assert run("watch", "--once")[0] == 1               # nothing new
    assert run("handoffs")[0] == 1                      # none sealed *to* Amara
    # Bruno: two fills, two handoffs opened with his key
    as_(KEY_B)
    out = run.ok("watch", "--once")
    assert out.count("filled   ") == 2
    assert f"handoff  from {A} for loop" in out
    assert "where(home): Trubarjeva 12, 4th floor" in out and "Ring twice" in out
    assert run("watch", "--once")[0] == 1
    listing = run.ok("handoffs")
    assert listing.count(f"from {A}:") == 2 and "Ring twice" in listing
    # the sealed records are in Amara's book, opaque, addressed
    records = [r for _, _, r in run.session.book.handoffs()]
    assert len(records) == 2 and all(r["from"] == A and r["to"] == B for r in records)
    assert not any("Trubarjeva" in json.dumps(r) for r in records)
    # without the key nothing opens
    monkeypatch.delenv("BEE_SIGNER")
    monkeypatch.setenv("LOOP_MAKER", B)
    assert "set bee_signer to open" in run.ok("handoffs")
