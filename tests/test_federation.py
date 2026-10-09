"""The federated book: fold rules (U8), convergence, the follower template.

Memory-backed variants of the P1 gates (docs/plans/P1-federated-book.md):
byte-identical manifests across aggregators folding in different orders,
one loop solved and cleared over the fold, a scorched-earth follower
reading it all back from roots alone, and forged makers dying at the fold.
"""

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Aggregator, GeoDisc, BookClearing, OfferRegistry, Ontology,
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
    assert (m_a.provenance_root, m_a.announcement_root) == \
           (m_b.provenance_root, m_b.announcement_root)

    # no index anywhere: the idx/{c,t,g} prefixes retired 2026-09-12, and
    # the manifest has no root for one
    assert not hasattr(m_a, "index_root")
    assert not any(k.startswith("idx/") for k in books["amara"].store.keys())

    # clearing is its own writer: it bases its own book on the fold by
    # re-asserting it — and canonical addressing proves the base is
    # exactly the fold (the re-commit reproduces book_root byte-for-byte)
    clearing_reg = OfferRegistry(RecordStore(blobs))
    clearing_reg.absorb(OfferRegistry(RecordStore(blobs, root=m_a.book_root)))
    assert clearing_reg.commit() == m_a.book_root
    agent = SolverAgent(
        clearing_reg, ONT,
        BookClearing(clearing_reg, ONT, clock=lambda: NOW),
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
    agent2 = SolverAgent(reg2, ONT, BookClearing(reg2, ONT, clock=lambda: NOW))
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
                        BookClearing(clearing_reg, ONT, clock=lambda: NOW))
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
    pytest.importorskip("coincurve")
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


def test_a_hostile_book_cannot_stop_the_fold():
    """Anyone may announce a book, so the fold is an admission boundary for
    untrusted input: what it cannot read is rejected with its reason, never
    allowed to abort the fold for every reader (2026-10-09: a record that is
    not an object raised AttributeError, and a "clearing" book with a loop
    and no fills raised PartialLoopError, so one announced book stopped
    every reader's fold)."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    garbled = RecordStore(blobs)
    garbled.put("offer/" + "ab" * 32, "not an object")
    garbled.commit()
    fake = RecordStore(blobs)
    fake.put("loop/" + "cd" * 32,
             {"legs": [{"give": "ef" * 32, "want": "01" * 32, "qty": "1"}]})
    fake.commit()
    agg = _aggregator(blobs, "agg-0", books, ["amara", "bruno", "chen"])
    agg.announce("mallory", garbled)
    agg.announce("fake-clearing", fake, role=CLEARING)
    manifest = agg.fold()
    rejected = {k for k, _ in RecordStore.at(manifest.provenance_root, blobs).items()
                if k.startswith("reject/")}
    assert "reject/fake-clearing/*" in rejected
    assert any(k.startswith("reject/mallory/offer/") for k in rejected)
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    makers = {o.maker for o in folded.offers(now=NOW)}
    assert makers == {"amara", "bruno", "chen"}       # the honest books stand
    honest = _aggregator(blobs, "agg-1", books, ["amara", "bruno", "chen"]).fold()
    assert manifest.book_root == honest.book_root


def _cleared(blobs, base_root, solver_id):
    """A clearing book: one solver clears the fold at `base_root`."""
    reg = OfferRegistry(RecordStore(blobs, root=base_root))
    agent = SolverAgent(reg, ONT, BookClearing(reg, ONT, clock=lambda: NOW),
                        solver_id=solver_id)
    receipts = agent.step(now=NOW)
    assert len(receipts) == 1 and receipts[0].accepted
    return reg


@pytest.mark.parametrize("hostile", ["0-clearing", "zz-clearing"])
def test_owner_names_cannot_decide_admission(hostile):
    """A clearing book is tested against the makers alone, so a broken book
    is rejected and an honest one admitted whichever owner sorts first."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    m1 = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold()
    honest = _cleared(blobs, m1.book_root, "fed-solver")
    fake = RecordStore(blobs)
    fake.put("loop/" + "cd" * 32,
             {"legs": [{"give": "ef" * 32, "want": "01" * 32, "qty": "1"}]})
    fake.commit()
    agg = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"])
    agg.announce("clearing-0", honest.store, role=CLEARING)
    agg.announce(hostile, fake, role=CLEARING)
    manifest = agg.fold()
    rejected = {k for k, _ in RecordStore.at(manifest.provenance_root, blobs).items()
                if k.startswith("reject/")}
    assert rejected == {f"reject/{hostile}/*"}
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    assert list(folded.offers(now=NOW)) == []   # the honest loop filled all


@pytest.mark.parametrize("rival", ["00" * 32, "ff" * 32])
def test_two_whole_books_claiming_one_offer_fail_loudly(rival):
    """Two books, each whole on its own, clear the same offers in different
    loops (two clearers solving one fold give one loop id, so the rival is
    written by hand). Neither is rejected, and the merged book fails U11:
    the open problem of P1-federated-book.md §3. Admitting whichever owner
    sorts first would settle races by name, and an owner id can be chosen
    to win them."""
    from loopmarket import PartialLoopError
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    m1 = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold()
    honest = _cleared(blobs, m1.book_root, "fed-solver")
    rival_book = RecordStore(blobs)
    for key, rec in honest.store.items():
        if key.startswith("loop/"):
            rival_book.put("loop/" + rival, rec)
        elif key.startswith("fill/"):
            rival_book.put(key, {**rec, "loop": rival})
    rival_book.commit()
    agg = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"])
    agg.announce("clearing-0", honest.store, role=CLEARING)
    agg.announce("0-rival", rival_book, role=CLEARING)
    with pytest.raises(PartialLoopError):
        agg.fold()


def test_a_bad_number_rejects_its_record_not_the_book():
    """A record whose numbers cannot be read is rejected on its own; the
    rest of its maker's book is folded (a zero denominator escaped the
    admission rules as ZeroDivisionError until 2026-10-09, and an exponent
    like 1e10000000 took 12 s to read)."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    amara = books["amara"].store
    honest = sorted(k for k in amara.keys() if k.startswith("offer/"))
    record = amara.get(honest[0])
    bad = {}
    for n, (side, field, text) in enumerate((("wants", "amount", "1/0"),
                                             ("gives", "qty", "1e10000000"))):
        broken = {**record, side: {**record[side], field: text}}
        key = "offer/" + f"{n:02d}" * 32
        amara.put(key, broken)
        bad[key] = text
    amara.commit()
    manifest = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold()
    provenance = dict(RecordStore.at(manifest.provenance_root, blobs).items())
    for key in bad:
        assert provenance[f"reject/amara/{key}"]["reason"] == "unreadable offer record"
    assert "reject/amara/*" not in provenance
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    assert {f"offer/{o.offer_id}" for o in folded.offers(now=NOW) if o.maker == "amara"} == set(honest)


def test_garbage_under_any_keyspace_is_rejected_record_by_record():
    """A maker book with garbage under every keyspace: the fold finishes,
    rejects the garbage record by record, never the whole book, and keeps
    the maker's honest offers. (Found 2026-10-09 by this mutator: a
    statement that was not an object rejected the whole book.)"""
    import random
    prefixes = ["sig/", "withdraw/", "handoff/", "cred/", "notice/", "cure/",
                "key/", "case/", "loop/", "fill/", "option/", "exercise/",
                "item/", "zzz/"]
    values = [None, 0, -1, 1.5, "", "x", "0x" + "ab" * 20, [], {}, [1, "a"],
              {"from": "amara"}, {"statement": {}}, {"statement": None},
              {"statement": {"subject": "amara"}}, {"presentation": 5},
              {"loop": 7}, {"qty": "1/0"}, {"legs": [{}]}, True,
              {"sealed": "zz", "from": "amara"}, "1e10000000"]
    for trial in range(200):
        rng = random.Random(trial)
        blobs = MemoryBytesStore()
        books = _maker_books(blobs)
        amara = books["amara"].store
        honest = sorted(k for k in amara.keys() if k.startswith("offer/"))
        for _ in range(rng.randint(1, 4)):
            parts = [rng.choice(["", "ab" * 32, "amara", rng.choice(honest)[6:],
                                 "x/y", "0x" + "cd" * 20])
                     for _ in range(rng.choice((1, 2, 3)))]
            amara.put(rng.choice(prefixes) + "/".join(parts), rng.choice(values))
        amara.commit()
        manifest = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold()
        provenance = dict(RecordStore.at(manifest.provenance_root, blobs).items())
        assert "reject/amara/*" not in provenance, (trial, provenance.get("reject/amara/*"))
        folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
        kept = {f"offer/{o.offer_id}" for o in folded.offers(now=NOW, include_filled=True)
                if o.maker == "amara"}
        assert kept == set(honest), trial
