"""The federated book: fold rules (U8), convergence, the follower template.

Memory-backed variants of the P1 gates (docs/plans/P1-federated-book.md):
byte-identical manifests across aggregators folding in different orders,
one loop solved and cleared over the fold, a scorched-earth follower
reading it all back from roots alone, and forged makers dying at the fold.
"""

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Aggregator, GeoDisc, MockClearing, OfferRegistry, Ontology,
    SolverAgent, Thing, TimeWindow, give, want,
)
from loopmarket.federation import CLEARING

NOW = 1_700_000_000
W = dict(
    service=TimeWindow(NOW, NOW + 90 * 86_400),
    valid=TimeWindow(NOW - 1, NOW + 30 * 86_400),
)
ONT = Ontology().load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})

FLAT = GeoDisc(46.05, 14.50, 5_000)
FARM = GeoDisc(46.10, 14.55, 15_000)
SHOP = GeoDisc(46.06, 14.51, 4_000)


def _maker_books(blobs):
    """Three per-maker books: each maker writes only their own offers."""
    books = {}
    offers = {
        "amara": [
            give("amara", Thing(("piano-lesson",), unit="course"), 100,
                nonce=1, where=FLAT, **W),
            want("amara", Thing(("produce", "local", "weekly"),
                               unit="course"), 104, nonce=2, where=FLAT, **W),
        ],
        "bruno": [
            give("bruno", Thing(("vegetable-box",), unit="course"), 50,
                nonce=3, where=FARM, **W),
            want("bruno", Thing(("bicycle-repair",), unit="course"), 52,
                nonce=4, where=FARM, **W),
        ],
        "chen": [
            give("chen", Thing(("bicycle-repair",), unit="course"), 80,
                nonce=5, where=SHOP, **W),
            want("chen", Thing(("music-lesson",), unit="course"), 83,
                nonce=6, where=SHOP, **W),
        ],
    }
    for owner, own in offers.items():
        reg = OfferRegistry(RecordStore(blobs))
        reg.publish_many(own)
        reg.commit()
        books[owner] = reg
    return books


def _aggregator(blobs, aggregator_id, books, order):
    agg = Aggregator(lambda: RecordStore(blobs), aggregator_id=aggregator_id)
    for owner in order:
        agg.announce(owner, books[owner].store)
    return agg


def test_convergence_gate():
    # the P1 convergence gate, memory-backed: 3 makers, 2 aggregators
    # folding in different orders, 1 solver — byte-identical manifests on
    # both aggregators, one loop cleared, second pass empty
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    agg_a = _aggregator(blobs, "agg-a", books, ["amara", "bruno", "chen"])
    agg_b = _aggregator(blobs, "agg-b", books, ["chen", "amara", "bruno"])
    m_a, m_b = agg_a.fold(), agg_b.fold()
    assert m_a.book_root and m_a.book_root == m_b.book_root
    # the whole manifest reproduces, not just the book: same inputs, same
    # rules, same derived state
    assert (m_a.provenance_root, m_a.index_root, m_a.announcement_root) == \
           (m_b.provenance_root, m_b.index_root, m_b.announcement_root)

    # the derived index exists at the aggregator (maker books carry none)
    idx = OfferRegistry(RecordStore(blobs, root=m_a.index_root))
    assert list(idx.ids_by_index("idx/c/piano-lesson/"))
    assert not list(books["amara"].store.keys("idx/"))

    # clearing is its own writer: it bases its own book on the fold by
    # re-asserting it — and canonical addressing proves the base is
    # exactly the fold (the re-commit reproduces book_root byte-for-byte)
    clearing_reg = OfferRegistry(RecordStore(blobs))
    clearing_reg.absorb(OfferRegistry(RecordStore(blobs, root=m_a.book_root)))
    assert clearing_reg.commit() == m_a.book_root
    agent = SolverAgent(
        clearing_reg, ONT,
        MockClearing(clearing_reg, ONT, clock=lambda: NOW),
        solver_id="fed-solver",
    )
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and receipts[0].accepted

    # both aggregators fold the clearing book in, again in different
    # orders, and stay byte-identical; the loop arrived whole (U11 runs
    # inside every fold)
    for agg in (agg_a, agg_b):
        agg.announce("clearing-0", clearing_reg.store, role=CLEARING)
    m_a2, m_b2 = agg_a.fold(), agg_b.fold()
    assert m_a2.book_root == m_b2.book_root != m_a.book_root

    folded = OfferRegistry(RecordStore(blobs, root=m_a2.book_root))
    assert folded.store.contains(f"loop/{receipts[0].loop_id}")
    assert list(folded.offers(now=NOW)) == []   # everything filled

    # a second solver pass over the new fold clears nothing
    reg2 = OfferRegistry(RecordStore(blobs, root=m_a2.book_root))
    agent2 = SolverAgent(reg2, ONT, MockClearing(reg2, ONT, clock=lambda: NOW))
    assert agent2.step(now=NOW) == []


def test_follower_reconstructs_from_roots_alone():
    # the P1 follower gate, memory-backed template: nothing but the blob
    # space and a manifest — no shared Python state — reads the cleared
    # loop and every fill back
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    agg = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"])
    m1 = agg.fold()
    clearing_reg = OfferRegistry(RecordStore(blobs, root=m1.book_root))
    agent = SolverAgent(clearing_reg, ONT,
                        MockClearing(clearing_reg, ONT, clock=lambda: NOW))
    receipts = agent.step(now=NOW)
    agg.announce("clearing-0", clearing_reg.store, role=CLEARING)
    manifest = agg.fold()

    follower = OfferRegistry(RecordStore(blobs, root=manifest.book_root))
    loop_rec = follower.store.get(f"loop/{receipts[0].loop_id}")
    assert len(loop_rec["legs"]) == 3
    for leg in loop_rec["legs"]:
        for oid in (leg["give"], leg["want"]):
            assert follower.is_filled(oid)
    assert len(list(follower.offers(include_filled=True))) == 6
    follower.verify_loop_atomicity()


def test_forged_maker_dies_at_the_fold():
    # U8's primary layer: an offer naming a maker other than the book's
    # owner, with no valid detached signature, never enters the fold —
    # and the rejection is an attributed provenance record
    blobs = MemoryBytesStore()
    mallory = OfferRegistry(RecordStore(blobs))
    forged = give("amara", Thing(("piano-lesson",), unit="course"), 1,
                 nonce=666, where=FLAT, **W)   # "amara" sells cheap, says mallory
    honest = give("mallory", Thing(("vegetable-box",), unit="course"), 50,
                 nonce=7, where=FARM, **W)
    mallory.publish_many([forged, honest])
    mallory.commit()

    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce("mallory", mallory.store)
    manifest = agg.fold()

    folded = OfferRegistry(RecordStore(blobs, root=manifest.book_root))
    ids = {o.offer_id for o in folded.offers(now=NOW)}
    assert honest.offer_id in ids and forged.offer_id not in ids
    prov = RecordStore(blobs, root=manifest.provenance_root)
    rejection = prov.get(f"reject/mallory/offer/{forged.offer_id}")
    assert "signature" in rejection["reason"]
    assert prov.get(f"origin/{honest.offer_id}")["owner"] == "mallory"


def test_foreign_offer_with_valid_signature_enters():
    pytest.importorskip("eth_keys")
    from loopmarket import maker_address, sign_offer

    blobs = MemoryBytesStore()
    key = "01" * 32
    maker = maker_address(key)
    offer = give(maker, Thing(("vegetable-box",), unit="course"), 50,
                nonce=8, where=FARM, **W)
    relay = OfferRegistry(RecordStore(blobs))    # someone else's book
    relay.publish(offer)
    relay.attach_signature(offer.offer_id, sign_offer(offer, key))
    relay.commit()

    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce("relay-0", relay.store)
    manifest = agg.fold()
    folded = OfferRegistry(RecordStore(blobs, root=manifest.book_root))
    assert any(o.offer_id == offer.offer_id for o in folded.offers(now=NOW))
    assert folded.signature(offer.offer_id)     # the sidecar rode along


def test_maker_book_speaking_clearing_is_refused():
    blobs = MemoryBytesStore()
    sneaky = OfferRegistry(RecordStore(blobs))
    offer = give("sneaky", Thing(("vegetable-box",)), 50, nonce=9,
                where=FARM, **W)
    sneaky.publish(offer)
    sneaky.mark_filled((offer.offer_id,), "L-fake",
                       {"legs": [{"give": offer.offer_id,
                                  "want": offer.offer_id}]})
    sneaky.commit()

    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce("sneaky", sneaky.store)
    manifest = agg.fold()
    folded = OfferRegistry(RecordStore(blobs, root=manifest.book_root))
    assert not folded.is_filled(offer.offer_id)  # the fake fill died
    assert not folded.store.contains("loop/L-fake")
    prov = RecordStore(blobs, root=manifest.provenance_root)
    assert "clearing keys" in prov.get(
        f"reject/sneaky/fill/{offer.offer_id}")["reason"]


class _CensoringAggregator(Aggregator):
    """An aggregator that announces a maker and silently folds nothing of
    theirs — the T14 attack shape. Lives in the tests: the library has no
    honest use for it."""

    def __init__(self, *args, drop: str, **kw):
        super().__init__(*args, **kw)
        self._drop = drop

    def _sanitize(self, owner, role, root, source, provenance):
        if owner == self._drop:
            return self._new_store()   # announced, never folded, never rejected
        return super()._sanitize(owner, role, root, source, provenance)


def test_omission_is_a_proof_not_a_suspicion():
    # T14: an aggregator's announcement_root is its own claim about the
    # inputs it folded; whatever an announced maker book holds that neither
    # entered book_root nor earned a reject/ record was dropped silently.
    # The audit finds it from the manifest alone and hands back absence
    # proofs a stranger verifies with no store access.
    from recordstore import ABSENT, verify_proof

    from loopmarket import audit_manifest

    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    honest = _aggregator(blobs, "honest", books, ["amara", "bruno", "chen"])
    censor = _CensoringAggregator(lambda: RecordStore(blobs),
                                  aggregator_id="censor", drop="chen")
    for owner in ("amara", "bruno", "chen"):
        censor.announce(owner, books[owner].store)
    m_honest, m_censor = honest.fold(), censor.fold()

    # same input set, different fold: divergence with identical
    # announcement_roots is evidence by construction (the fold is pure)
    assert m_honest.announcement_root == m_censor.announcement_root
    assert m_honest.book_root != m_censor.book_root

    assert audit_manifest(m_honest, blobs) == []
    found = audit_manifest(m_censor, blobs)
    assert {o.owner for o in found} == {"chen"}
    assert sorted(o.key for o in found) == sorted(
        f"offer/{oid}" for oid in books["chen"].store.keys("offer/")
        for oid in [oid[len("offer/"):]])
    for o in found:
        assert o.announced_root == books["chen"].store.root
        assert verify_proof(o.proof, m_censor.book_root) is ABSENT

    # the censored offers are simply missing from the censor's book, so a
    # solver reading it finds no loop; one folding the announced maker
    # books itself — the censor's own announcement names them — recovers
    # the honest fold byte for byte
    censored = OfferRegistry(RecordStore(blobs, root=m_censor.book_root))
    assert len(list(censored.offers(now=NOW))) == 4
    announced = RecordStore.at(m_censor.announcement_root, blobs)
    own = Aggregator(lambda: RecordStore(blobs), aggregator_id="solver-self")
    for key in announced.keys("announce/"):
        rec = announced.get(key)
        own.announce(key[len("announce/"):],
                     RecordStore(blobs, root=rec["root"]))
    assert own.fold().book_root == m_honest.book_root


def test_dropped_tombstone_is_an_omission_too():
    # the nastier censorship: folding the offer but not its withdrawal
    # resurrects it. The audit covers withdraw/ for exactly this reason.
    from loopmarket import audit_manifest

    class _TombstoneEater(Aggregator):
        def _sanitize(self, owner, role, root, source, provenance):
            staged = super()._sanitize(owner, role, root, source, provenance)
            if owner == "bruno":
                clean = self._new_store()
                for key, rec in staged.items():
                    if not key.startswith("withdraw/"):
                        clean.put(key, rec)
                return clean
            return staged

    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    regret = books["bruno"].publish(
        give("bruno", Thing(("vegetable-box",), unit="course"), 90,
            nonce=7, where=FARM, **W))
    books["bruno"].withdraw(regret)
    books["bruno"].commit()
    eater = _TombstoneEater(lambda: RecordStore(blobs), aggregator_id="eater")
    for owner in ("amara", "bruno", "chen"):
        eater.announce(owner, books[owner].store)
    m = eater.fold()
    found = audit_manifest(m, blobs)
    assert [(o.owner, o.key) for o in found] == [("bruno", f"withdraw/{regret}")]
    assert not OfferRegistry(RecordStore(blobs, root=m.book_root)).is_withdrawn(regret)
