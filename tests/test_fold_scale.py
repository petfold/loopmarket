"""A fold's work grows with its books' total size times log N, not N².

Folding maker books one at a time into a growing union cost about the size
of the union per book: 400 maker books took 10.8 s, the time per book
doubling with N (2026-10-10). The fold now merges in rounds of pairs, earlier
books on the left (`Aggregator.fold`'s `merged_all`), which gives the same
root: these tests pin both, by counting what the merges touch rather than by
timing them."""

import math

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import (Aggregator, OfferRegistry, Ontology, Thing, TimeWindow,
                        give, want)

NOW = 1_700_000_000
W = dict(valid=TimeWindow(NOW - 1, NOW + 30 * 86_400))      # v4 offers
ONT = Ontology().load({"service": [], "lesson": ["service"], "repair": ["service"]})


def maker_books(n, blobs):
    books = {}
    for i in range(n):
        reg = OfferRegistry(RecordStore(blobs))
        reg.publish_many([
            give(f"m{i:03}", Thing(("lesson",), unit="course"), 100,
                 nonce=2 * i + 1, **W),
            want(f"m{i:03}", Thing(("repair",), unit="course"), 90,
                 nonce=2 * i + 2, **W)])
        reg.commit()
        books[f"m{i:03}"] = reg
    return books


def fold(books, blobs):
    agg = Aggregator(lambda: RecordStore(blobs), ontology=ONT)
    for owner, reg in books.items():
        agg.announce(owner, reg.store)
    return agg.fold()


def test_the_fold_of_clean_books_is_the_union_of_their_records():
    blobs = MemoryBytesStore()
    books = maker_books(13, blobs)            # odd, so a round carries one over
    union = RecordStore(blobs)
    for reg in books.values():
        source = RecordStore.at(reg.store.root, blobs)
        for key in source.keys():
            union.put(key, source.get(key))
    assert fold(books, blobs).book_root == union.commit()


def test_each_record_enters_about_log_n_merges(monkeypatch):
    blobs = MemoryBytesStore()
    n = 64
    books = maker_books(n, blobs)
    sizes = {reg.store.root: len(list(RecordStore.at(reg.store.root, blobs).keys()))
             for reg in books.values()}
    touched = []
    real = RecordStore.merge

    def counting(bytes_store, base, ours, theirs, **kw):
        size = lambda root: len(list(RecordStore.at(root, blobs).keys()))
        touched.append(size(ours) + size(theirs))
        return real(bytes_store, base, ours, theirs, **kw)

    monkeypatch.setattr(RecordStore, "merge", staticmethod(counting))
    fold(books, blobs)
    total = sum(sizes.values())
    # a merge tree touches each record once per round: log2(64) = 6 rounds;
    # one book at a time touches the union once per book, about n/2 a record
    assert sum(touched) <= 2 * total * math.ceil(math.log2(n)), (sum(touched), total)
