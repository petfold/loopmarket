"""The federated book: fold rules (U8), convergence, the follower template.

Memory-backed variants of the P1 gates (docs/plans/P1-federated-book.md):
byte-identical manifests across aggregators folding in different orders,
one loop solved and cleared over the fold, a scorched-earth follower
reading it all back from roots alone, and forged makers dying at the fold.
"""

import pytest
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (
    Aggregator, BookClearing, OfferRegistry, Ontology,
    SolverAgent, Thing, TimeWindow, give, want,
)
from loopmarket.federation import CLEARING

NOW = 1_700_000_000
W = dict(valid=TimeWindow(NOW - 1, NOW + 30 * 86_400))
ONT = Ontology().load({
    "service": [], "lesson": ["service"], "music-lesson": ["lesson"],
    "piano-lesson": ["music-lesson"], "repair": ["service"],
    "bicycle-repair": ["repair"], "food": [], "produce": ["food"],
    "local": [], "weekly": [], "vegetable-box": ["produce", "local", "weekly"],
})


def _maker_books(blobs):
    """Three per-maker books: each maker writes only their own offers."""
    books = {}
    offers = {
        "amara": [
            give("amara", Thing(("piano-lesson",), unit="course"), 100,
                nonce=1, **W),
            want("amara", Thing(("produce", "local", "weekly"),
                               unit="course"), 104, nonce=2, **W),
        ],
        "bruno": [
            give("bruno", Thing(("vegetable-box",), unit="course"), 50,
                nonce=3, **W),
            want("bruno", Thing(("bicycle-repair",), unit="course"), 52,
                nonce=4, **W),
        ],
        "chen": [
            give("chen", Thing(("bicycle-repair",), unit="course"), 80,
                nonce=5, **W),
            want("chen", Thing(("music-lesson",), unit="course"), 83,
                nonce=6, **W),
        ],
    }
    for owner, own in offers.items():
        reg = OfferRegistry(RecordStore(blobs))
        reg.publish_many(own)
        reg.commit()
        books[owner] = reg
    return books


def _aggregator(blobs, aggregator_id, books, order, ontology=ONT, chain=False):
    """Every reader's fold re-checks a clearing book's loops under its
    catalogue (review item 9), so the aggregator is given the one the
    offers are matched under."""
    agg = Aggregator(lambda: RecordStore(blobs), aggregator_id=aggregator_id, ontology=ontology, chain=chain)
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
                 nonce=666, **W)   # "amara" sells cheap, says mallory
    honest = give("mallory", Thing(("vegetable-box",), unit="course"), 50,
                 nonce=7, **W)
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
                nonce=8, **W)
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
    offer = give("sneaky", Thing(("vegetable-box",)), 50, nonce=9, **W)
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
            nonce=7, **W))
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
    assert f"reject/fake-clearing/loop/{'cd' * 32}" in rejected
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
    assert rejected == {f"reject/{hostile}/loop/{'cd' * 32}"}
    folded = OfferRegistry(RecordStore.at(manifest.book_root, blobs))
    assert list(folded.offers(now=NOW)) == []   # the honest loop filled all


def _dana(blobs):
    """A fourth maker who trades with bruno alone: her repair for his box."""
    dana = OfferRegistry(RecordStore(blobs))
    dana.publish_many([give("dana", Thing(("bicycle-repair",), unit="course"), 40, nonce=7, **W),
                       want("dana", Thing(("vegetable-box",), unit="course"), 60, nonce=8, **W)])
    dana.commit()
    return dana


@pytest.mark.parametrize("rival", ["0-rival", "zz-rival"])
def test_two_valid_books_claiming_one_offer_fail_loudly(rival):
    """Two clearing books each hold a valid loop over bruno's offers: the
    triangle, and a loop of two between bruno and dana. Each passes the
    re-check and is whole on its own, and the merged book fails U11: the
    open problem of P1-federated-book.md §3, which review item 9 leaves open
    for a fold without a chain. Admitting whichever owner sorts first would
    settle races by name, and an owner id can be chosen to win them."""
    from loopmarket import PartialLoopError
    blobs = MemoryBytesStore()
    books = {**_maker_books(blobs), "dana": _dana(blobs)}
    triangle = _cleared(blobs, _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold().book_root,
                        "fed-solver")
    pair = _cleared(blobs, _aggregator(blobs, "agg", books, ["bruno", "dana"]).fold().book_root, "other-solver")
    agg = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen", "dana"])
    agg.announce("clearing-0", triangle.store, role=CLEARING)
    agg.announce(rival, pair.store, role=CLEARING)
    with pytest.raises(PartialLoopError):
        agg.fold()


@pytest.mark.parametrize("rival", ["0-rival", "zz-rival"])
def test_under_a_chain_two_valid_books_claiming_one_offer_are_rivals(rival):
    """Question 25 (decided by Peter 2026-10-10: A): where a chain decides
    what is filled, the same two books are rivals, not a failure. Both
    loops stay in the fold with their records, one `rival/` record per
    rival names the other and both owners and the offers they share, and
    U11 holds for everything but the rivals' claims on those offers; the
    chain's finalized fills say which loop took them. Whichever owner sorts
    first, the same rivals are recorded."""
    from loopmarket import PartialLoopError
    from loopmarket.federation import rival_claims
    blobs = MemoryBytesStore()
    books = {**_maker_books(blobs), "dana": _dana(blobs)}
    triangle = _cleared(blobs, _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold().book_root,
                        "fed-solver")
    pair = _cleared(blobs, _aggregator(blobs, "agg", books, ["bruno", "dana"]).fold().book_root, "other-solver")
    (t,) = [k[len("loop/"):] for k in triangle.store.keys("loop/")]
    (p,) = [k[len("loop/"):] for k in pair.store.keys("loop/")]
    shared = sorted(o.offer_id for o in books["bruno"].offers(now=NOW))
    agg = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen", "dana"], chain=True)
    agg.announce("clearing-0", triangle.store, role=CLEARING)
    agg.announce(rival, pair.store, role=CLEARING)
    m = agg.fold()
    prov = RecordStore.at(m.provenance_root, blobs)
    assert not list(prov.items("reject/"))
    recorded = dict(prov.items("rival/"))
    assert recorded == {
        f"rival/{t}/{p}": {"loop": t, "owner": "clearing-0", "rival": p, "rival_owner": rival, "offers": shared},
        f"rival/{p}/{t}": {"loop": p, "owner": rival, "rival": t, "rival_owner": "clearing-0", "offers": shared}}
    folded = OfferRegistry(RecordStore.at(m.book_root, blobs))
    assert folded.store.contains(f"loop/{t}") and folded.store.contains(f"loop/{p}")
    folded.verify_loop_atomicity(rivals=rival_claims(prov))
    with pytest.raises(PartialLoopError):
        folded.verify_loop_atomicity()
    # the same fold with the books announced under swapped names records the same rivals
    other = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen", "dana"], chain=True)
    other.announce(rival, triangle.store, role=CLEARING)
    other.announce("clearing-0", pair.store, role=CLEARING)
    swapped = dict(RecordStore.at(other.fold().provenance_root, blobs).items("rival/"))
    assert {k: (v["loop"], v["rival"]) for k, v in swapped.items()} == \
        {k: (v["loop"], v["rival"]) for k, v in recorded.items()}


def test_under_a_chain_a_rival_never_hides_a_broken_book():
    """A rival is a valid loop: a clearing book whose loop fails the
    re-check is rejected under a chain as without one, and records no
    rivalry."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    honest = _cleared(blobs, _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"]).fold().book_root,
                      "fed-solver")
    fake = RecordStore(blobs)
    fake.put("loop/" + "cd" * 32, {"legs": [{"give": "ef" * 32, "want": "01" * 32, "qty": "1"}]})
    fake.commit()
    agg = _aggregator(blobs, "agg", books, ["amara", "bruno", "chen"], chain=True)
    agg.announce("clearing-0", honest.store, role=CLEARING)
    agg.announce("mallory", fake, role=CLEARING)
    prov = RecordStore.at(agg.fold().provenance_root, blobs)
    assert {k for k, _ in prov.items("reject/")} == {f"reject/mallory/loop/{'cd' * 32}"}
    assert not list(prov.items("rival/"))


# --------------------------------------------------------------------------- #
# Review item 9 (decided by Peter 2026-10-10): every reader's fold re-checks
# each loop of a clearing book against the maker books, as clearing checks it
# --------------------------------------------------------------------------- #

def _open(manifest, blobs):
    return OfferRegistry(RecordStore.at(manifest.book_root, blobs))


def _rejections(manifest, blobs):
    return {k[len("reject/"):]: v["reason"]
            for k, v in RecordStore.at(manifest.provenance_root, blobs).items("reject/")}


def _hand_written(blobs, legs, loop_id="ab" * 32):
    """A clearing book as anyone may announce one: a loop record and the
    fills it claims, written by hand, no clearing asked."""
    book = OfferRegistry(RecordStore(blobs))
    record = {"v": 1, "loop_id": loop_id, "solver": "mallory", "found_at": NOW, "book_root": "",
              "ontology_root": "", "surplus": "1/10", "nodes": sorted({w.maker for _, w in legs}),
              "legs": [{"give": g.offer_id, "gives": [g.offer_id], "taken": ["1"], "want": w.offer_id}
                       for g, w in legs],
              "potentials": {}}
    fills = {}
    for g, w in legs:
        fills[w.offer_id] = {"loop": loop_id, "gives": [{"offer": g.offer_id, "qty": "1"}]}
        fills[g.offer_id] = {"loop": loop_id, "qty": "1"}
    book.mark_filled(fills, loop_id, record)
    book.store.commit()
    return book


def test_an_invented_loop_is_rejected_with_its_reason_and_hides_nothing():
    """The case measured before deciding: on the three maker books, a
    clearing book anyone announced with one invented loop, amara's piano
    lesson filling bruno's bicycle-repair want (which `check_match`
    refuses), took every reader's open offers from six to four. The fold
    re-derives the leg as clearing would, rejects the loop with its reason,
    and the six stay open."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    makers = ["amara", "bruno", "chen"]
    offers = {(o.maker, o.kind): o for o in _open(_aggregator(blobs, "agg", books, makers).fold(), blobs).offers(now=NOW)}
    fake = _hand_written(blobs, [(offers[("amara", "give")], offers[("bruno", "want")])])
    agg = _aggregator(blobs, "agg", books, makers)
    agg.announce("mallory", fake.store, role=CLEARING)
    manifest = agg.fold()
    assert len(list(_open(manifest, blobs).offers(now=NOW))) == 6
    reasons = _rejections(manifest, blobs)
    assert list(reasons) == [f"mallory/loop/{'ab' * 32}"]
    assert reasons[f"mallory/loop/{'ab' * 32}"].startswith("leg fails re-verification")


def test_a_valid_loop_is_admitted_and_its_fills_must_be_the_loops():
    """The honest clearing passes the re-check and fills its six offers. A
    clearing book that writes more than its loop takes, here a fill on an
    offer the loop never touched, holds a loop whose fills are not the ones
    clearing it writes: rejected with its reason, so it hides nothing."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    extra = give("dana", Thing(("vegetable-box",), unit="course"), 40, nonce=7, **W)
    books["dana"] = OfferRegistry(RecordStore(blobs))
    books["dana"].publish(extra)
    books["dana"].commit()
    order = ["amara", "bruno", "chen", "dana"]
    honest = _cleared(blobs, _aggregator(blobs, "agg", books, order).fold().book_root, "fed-solver")
    agg = _aggregator(blobs, "agg", books, order)
    agg.announce("clearing-0", honest.store, role=CLEARING)
    manifest = agg.fold()
    assert _rejections(manifest, blobs) == {}
    assert [o.offer_id for o in _open(manifest, blobs).offers(now=NOW)] == [extra.offer_id]
    lid = next(iter(honest.store.keys("loop/")))[len("loop/"):]
    honest.store.put(f"fill/{extra.offer_id}", {"loop": lid, "qty": "1"})
    honest.commit()
    manifest = agg.fold()
    reasons = _rejections(manifest, blobs)
    assert list(reasons) == [f"clearing-0/loop/{lid}"] and "fill" in reasons[f"clearing-0/loop/{lid}"]
    assert len(list(_open(manifest, blobs).offers(now=NOW))) == 7


def test_a_loop_of_the_2026_08_shape_is_admitted_and_an_orphan_record_is_not():
    """A clearing book written before the v4 fills (2026-08: a leg names
    one give, a fill only its loop) is re-checked like any other, its fills
    the ones that shape wrote. A record naming a loop the book does not
    hold is rejected on its own, and the book's loop still stands."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    makers = ["amara", "bruno", "chen"]
    honest = _cleared(blobs, _aggregator(blobs, "agg", books, makers).fold().book_root, "fed-solver")
    _key, rec = next(iter(honest.store.items("loop/")))
    legs = [{"give": leg["give"], "want": leg["want"], "rate": leg["rate"]} for leg in rec["legs"]]
    old = OfferRegistry(RecordStore(blobs))
    old.mark_filled([oid for leg in legs for oid in (leg["give"], leg["want"])], rec["loop_id"],
                    {**{k: v for k, v in rec.items() if k not in ("legs", "potentials")}, "legs": legs})
    old.store.put(f"item/{'ee' * 32}/amara/{'99' * 32}", {"offer": legs[0]["give"], "until": NOW + 1})
    old.store.commit()                          # as written, unchecked: anyone may announce a book
    agg = _aggregator(blobs, "agg", books, makers)
    agg.announce("clearing-0", old.store, role=CLEARING)
    manifest = agg.fold()
    assert _rejections(manifest, blobs) == {
        f"clearing-0/item/{'ee' * 32}/amara/{'99' * 32}": "names a loop this book does not hold"}
    assert list(_open(manifest, blobs).offers(now=NOW)) == []


def test_a_fold_without_a_catalogue_admits_no_loop():
    """A loop is re-checked under a catalogue, so a fold given none admits
    no clearing book's loop (U7, fail closed): the offers stay open, and
    each rejection says why."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    makers = ["amara", "bruno", "chen"]
    honest = _cleared(blobs, _aggregator(blobs, "agg", books, makers).fold().book_root, "fed-solver")
    agg = _aggregator(blobs, "agg", books, makers, ontology=None)
    agg.announce("clearing-0", honest.store, role=CLEARING)
    manifest = agg.fold()
    assert len(list(_open(manifest, blobs).offers(now=NOW))) == 6
    reasons = _rejections(manifest, blobs)
    assert len(reasons) == 1 and all("catalogue" in r for r in reasons.values())


def test_a_bad_number_rejects_its_record_not_the_book():
    """A record whose numbers cannot be read is rejected on its own; the
    rest of its maker's book is folded (a zero denominator escaped the
    admission rules as ZeroDivisionError until 2026-10-09, and an exponent
    like 1e10000000 took 12 s to read)."""
    blobs = MemoryBytesStore()
    books = _maker_books(blobs)
    amara = books["amara"].store
    honest = sorted(k for k in amara.keys() if k.startswith("offer/"))
    record = next(amara.get(k) for k in honest if amara.get(k)["gives"]["type"] == "thing")   # her give
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
