"""The announcement channel (announce.py, 2026-09-14): a book becomes
discoverable by one announcement, latest per owner, with retractions; the
aggregator folds exactly the announced set; a reader audits any manifest
against the same set alone — a never-folded book is an omission with a
proof, like a dropped record. GSOC was dropped the same day: the chain is
what a censored announcement would be detected against, so the chain is
the channel."""

import os

import pytest
from recordstore import MemoryBytesStore, RecordStore, verify_proof

from loopmarket import OfferRegistry, Thing, TimeWindow, give, want
from loopmarket.announce import (
    ABI, CLEARING, MAKER, Announcement, ChainAnnouncements, MemoryAnnouncements,
    open_announcements,
)
from loopmarket.federation import Aggregator, audit_manifest

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def _books(blobs):
    books = {}
    for owner, offers in {
        "amara": [give("amara", Thing(("g1",)), 100, **V), want("amara", Thing(("g3",)), 104, **V)],
        "bruno": [give("bruno", Thing(("g2",)), 50, **V), want("bruno", Thing(("g1",)), 52, **V)],
        "chen": [give("chen", Thing(("g3",)), 80, **V), want("chen", Thing(("g2",)), 83, **V)],
    }.items():
        reg = OfferRegistry(RecordStore(blobs))
        reg.publish_many(offers); reg.commit()
        books[owner] = reg
    return books


def test_latest_per_owner_and_retractions(tmp_path):
    for channel in (MemoryAnnouncements(), MemoryAnnouncements(str(tmp_path / "log"))):
        channel.announce("swarm:book-a", owner="0xA")
        channel.announce("rs:/b", owner="B")
        channel.announce("swarm:book-a2", owner="0xA")          # replaces
        channel.retract(owner="B")
        standing = channel.announced()
        assert [(a.owner, a.book, a.role) for a in standing] == [("0xA", "swarm:book-a2", MAKER)]
        assert standing[0].spec() == "swarm:book-a2@0xA"       # the owner comes from the channel
        channel.announce("rs:/b", CLEARING, owner="B")
        assert [a.spec() for a in channel.announced()] == ["swarm:book-a2@0xA", "rs:/b"]
        with pytest.raises(ValueError):
            channel.announce("rs:/c", "auditor", owner="C")
        with pytest.raises(ValueError):
            channel.announce("rs:/c")
    # the file channel is shared by every session that names it
    second = open_announcements(f"file:{tmp_path / 'log'}")
    assert [a.owner for a in second.announced()] == ["0xA", "B"]
    assert open_announcements("memory:x") is open_announcements("memory:x")
    with pytest.raises(ValueError):
        open_announcements("gsoc:whatever")


def test_the_aggregator_folds_exactly_the_announced_set():
    blobs = MemoryBytesStore()
    books = _books(blobs)
    channel = MemoryAnnouncements()
    for owner in ("amara", "bruno", "chen"):
        channel.announce(f"book:{owner}", owner=owner)
    agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="a")
    opened = agg.subscribe(channel, lambda spec: books[spec[5:]].store)
    assert [a.owner for a in opened] == ["amara", "bruno", "chen"]
    first = agg.fold()
    assert set(OfferRegistry(RecordStore.at(first.book_root, blobs)).offers()) and \
        len(list(OfferRegistry(RecordStore.at(first.book_root, blobs)).offers())) == 6
    # a retraction drops the book at the next subscribe; an unreachable one is skipped
    channel.retract(owner="chen")
    channel.announce("book:nowhere", owner="dora")
    opened = agg.subscribe(channel, lambda spec: books[spec[5:]].store)
    assert [a.owner for a in opened] == ["amara", "bruno"]
    second = agg.fold()
    assert len(list(OfferRegistry(RecordStore.at(second.book_root, blobs)).offers())) == 4
    # any other subscriber to the same channel lands on the same root
    other = Aggregator(lambda: RecordStore(blobs), aggregator_id="b")
    other.subscribe(channel, lambda spec: books[spec[5:]].store)
    assert other.fold().book_root == second.book_root


def test_a_never_folded_book_is_an_omission_with_a_proof():
    """The check that replaces comparing aggregators with each other: the
    channel's standing set against one manifest's announcement set."""
    blobs = MemoryBytesStore()
    books = _books(blobs)
    channel = MemoryAnnouncements()
    for owner in ("amara", "bruno", "chen"):
        channel.announce(f"book:{owner}", owner=owner)
    censor = Aggregator(lambda: RecordStore(blobs), aggregator_id="censor")
    censor.announce("amara", books["amara"].store)
    censor.announce("bruno", books["bruno"].store)     # chen left out entirely
    manifest = censor.fold()
    omissions = audit_manifest(manifest, blobs, expected=channel.announced())
    assert [(o.owner, o.key) for o in omissions] == [("chen", "announce/chen")]
    assert verify_proof(omissions[0].proof, manifest.announcement_root)
    honest = Aggregator(lambda: RecordStore(blobs), aggregator_id="honest")
    honest.subscribe(channel, lambda spec: books[spec[5:]].store)
    assert audit_manifest(honest.fold(), blobs, expected=channel.announced()) == []


class _FakeLog(dict):
    pass


class _FakeEvent:
    def __init__(self, logs):
        self._logs = logs

    def get_logs(self, from_block=0):
        return [l for l in self._logs if l["blockNumber"] >= from_block]


class _FakeContract:
    def __init__(self, announces, retracts):
        class Events:
            Announce = _FakeEvent(announces)
            Retract = _FakeEvent(retracts)
        self.events = Events()


class _FakeEth:
    def __init__(self, contract):
        self._contract = contract

    def contract(self, address, abi):
        assert abi is ABI and address == "0xC0"
        return self._contract


class _FakeWeb3:
    def __init__(self, contract):
        self.eth = _FakeEth(contract)


def test_chain_logs_decode_to_the_standing_set():
    """The chain backend against a client with web3's face: block number and
    log index order the events, `msg.sender` is the owner, role 1 is a
    clearing book, a retraction ends an announcement."""
    announces = [
        {"blockNumber": 10, "logIndex": 0, "args": {"owner": "0xA", "book": "swarm:a1", "role": 0}},
        {"blockNumber": 10, "logIndex": 1, "args": {"owner": "0xB", "book": "swarm:b", "role": 1}},
        {"blockNumber": 12, "logIndex": 0, "args": {"owner": "0xA", "book": "swarm:a2", "role": 0}},
    ]
    retracts = [{"blockNumber": 11, "logIndex": 0, "args": {"owner": "0xA"}}]
    chain = ChainAnnouncements("http://rpc", "0xC0", client=_FakeWeb3(_FakeContract(announces, retracts)))
    standing = chain.announced()
    assert [(a.owner, a.book, a.role) for a in standing] == \
        [("0xA", "swarm:a2", MAKER), ("0xB", "swarm:b", CLEARING)]
    assert standing[0].spec() == "swarm:a2@0xA"
    with pytest.raises(ValueError):
        chain.announce("swarm:x")                          # no key
    # without web3 installed the real client fails closed with the pip hint
    bare = ChainAnnouncements("http://rpc", "0xC0")
    try:
        import web3  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match=r"loopmarket\[chain\]"):
            bare.announced()
    spec = open_announcements("chain:http://rpc:8545@0xC0")
    assert isinstance(spec, ChainAnnouncements) and spec.rpc_url == "http://rpc:8545" \
        and spec.contract_address == "0xC0"


def test_several_channels_read_as_one_the_newer_listed_last():
    """A chain move is a setting: makers announce on both channels with one
    command, readers watching both see one set, and where an owner stands
    on both the last-listed channel wins."""
    from loopmarket.announce import UnionAnnouncements
    old, new = MemoryAnnouncements(), MemoryAnnouncements()
    old.announce("swarm:a-old", owner="0xA")
    old.announce("swarm:b", owner="0xB")
    new.announce("swarm:a-new", owner="0xA")
    union = UnionAnnouncements([old, new])
    assert [(a.owner, a.book) for a in union.announced()] == [("0xA", "swarm:a-new"), ("0xB", "swarm:b")]
    union.announce("swarm:c", owner="0xC")                 # written to both
    assert [a.owner for a in old.announced()] == ["0xA", "0xB", "0xC"]
    assert [a.owner for a in new.announced()] == ["0xA", "0xC"]
    union.retract(owner="0xA")                             # from both
    assert [a.owner for a in union.announced()] == ["0xB", "0xC"]
    both = open_announcements("memory:u1, memory:u2")
    assert isinstance(both, UnionAnnouncements) and len(both.members) == 2
    with pytest.raises(ValueError):
        UnionAnnouncements([])
