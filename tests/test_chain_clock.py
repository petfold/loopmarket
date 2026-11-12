"""`ChainClearing` judges a proposal at one instant. It builds the beat's
evidence, rehearses the checklist, posts the beat and then commits the
loop to its book; the clock read again at each step can pass the end of an
offer's validity between the rehearsal and the commit, and the book then
refused a loop whose beat, with its bond, was already posted. A stand-in
client and evidence builder here: only the order of the readings is at
issue, so this needs neither the `chain` nor the `evm` extra."""

import types

from recordstore import MemoryBytesStore, RecordStore

import loopmarket.beat
from loopmarket import OfferRegistry, Ontology, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.clearing import ChainClearing, LoopProposal

NOW = 5_000
END = NOW + 10                      # the farm's apples stop being on offer
V = dict(valid=TimeWindow(0, 1_000_000))


class _Client:
    """A clearing contract that verifies every leg and takes every beat."""

    def __init__(self):
        self.posted = []

    def filled(self, offer_id):
        return 0

    def verdict_of(self, sub, index):
        return "leg verifies"

    def submit(self, sub):
        self.posted.append(sub)
        return len(self.posted), None


def _proposal(monkeypatch):
    monkeypatch.setattr(loopmarket.beat, "submission",
                        lambda proposal, snapshot, **kw: types.SimpleNamespace(legs=[None, None]))
    cat = Ontology.persistent(RecordStore(MemoryBytesStore()))
    cat.load({"apple": [], "lesson": []})
    cat.commit()
    pins = cat.pins
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    book.publish_many([give("farm", Thing(("apple",), 100, "kg", step=5), 200, valid=TimeWindow(0, END), **pins),
                       want("b1", Thing(("apple",), 40, "kg"), 90, **V, **pins),
                       give("b1", Thing(("lesson",)), 80, **V, **pins),
                       want("farm", Thing(("lesson",)), 85, **V, **pins)])
    book.commit()
    root = book.store.root
    _root, loops = SolverAgent(book, cat, clearing=None, solver_id="t", min_surplus=0.0).find_loops(now=NOW)
    return cat, book, LoopProposal(loops[0], root, cat.root, "t", NOW)


def _clearing(cat, book, client, readings):
    times = iter(readings)
    return ChainClearing(book, cat, beat_client=client, clock=lambda: next(times),
                         snapshot_of=lambda root: OfferRegistry(RecordStore.at(root, book.store.blobs)))


def test_a_beat_that_is_posted_is_a_loop_the_book_takes(monkeypatch):
    cat, book, proposal = _proposal(monkeypatch)
    client = _Client()
    # the offer is open when the proposal arrives, and over by the time the beat is on chain
    receipt = _clearing(cat, book, client, [NOW, END + 5, END + 5]).submit(proposal)
    assert len(client.posted) == 1
    assert receipt.accepted and receipt.reason == "beat 1"
    assert book.store.contains("loop/" + receipt.loop_id)


def test_a_proposal_too_late_at_its_one_instant_posts_no_beat(monkeypatch):
    cat, book, proposal = _proposal(monkeypatch)
    client = _Client()
    receipt = _clearing(cat, book, client, [END + 5, NOW, NOW]).submit(proposal)
    assert not receipt.accepted and client.posted == []
    assert not book.store.contains("loop/" + receipt.loop_id)
