"""The `cred/` sidecar (R2, 2026-09-29; `docs/plans/counterparty-gate.md`
§3.2): a statement about a key is presented in its subject's own book,
beside `sig/` and `handoff/`, under `cred/<subject>/<statement id>`; the
fold admits it only there, and every other presentation — a foreign
subject, a record under the wrong content address, a clearing book
speaking for a maker — earns an attributed rejection (U8). Whether the
statement is true is the gate's (R4), not the fold's."""

from recordstore import MemoryBytesStore, RecordStore

from loopmarket import Aggregator, OfferRegistry, Statement
from loopmarket.federation import CLEARING, audit_manifest

K, M, ISSUER = "0x" + "44" * 20, "0x" + "55" * 20, "0x" + "66" * 20


def _statement(subject=K, category="dentist-licensed"):
    return Statement(subject=subject, category=category, issuer=ISSUER, kind="attested", as_of=1_000,
                     until=1_000 + 28 * 86_400, evidence="ee" * 32, path=(ISSUER,), paid_by="subject")


def test_a_statement_is_presented_in_its_subjects_book_and_read_back():
    blobs = MemoryBytesStore()
    book = OfferRegistry(RecordStore(blobs))
    s = _statement()
    sid = book.present(s, {"issuer_sig": "0x" + "ab" * 65})
    book.commit()
    assert sid == s.statement_id
    assert list(book.statements()) == [(s, {"issuer_sig": "0x" + "ab" * 65})]
    assert list(book.statements(K)) == [(s, {"issuer_sig": "0x" + "ab" * 65})]
    assert list(book.statements(M)) == []


def test_the_fold_admits_a_statement_only_in_its_subjects_book():
    """The dentist presents her statement in her own book and it folds; a
    book presenting a statement about someone else, a record under the
    wrong address, and a clearing book presenting one are each rejected
    with provenance; the audit finds nothing omitted."""
    blobs = MemoryBytesStore()
    mine = OfferRegistry(RecordStore(blobs))
    mine.present(_statement())
    mine.commit()
    other = OfferRegistry(RecordStore(blobs))
    other.present(_statement())                                  # about K, in M's book
    forged = _statement(subject=M)
    other.store.put(f"cred/{M}/{'00' * 32}", {"statement": forged.to_record(), "presentation": None})
    other.commit()
    clearing = OfferRegistry(RecordStore(blobs))
    clearing.present(_statement(category="clearing-says"))
    clearing.commit()
    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce(K, mine.store)
    agg.announce(M, other.store)
    agg.announce("clearing-0", clearing.store, role=CLEARING)
    m = agg.fold()
    folded = OfferRegistry(RecordStore.at(m.book_root, blobs))
    assert [s.subject for s, _ in folded.statements()] == [K]
    provenance = RecordStore.at(m.provenance_root, blobs)
    reasons = {k: v["reason"] for k, v in provenance.items("reject/")}
    sid = _statement().statement_id
    assert reasons[f"reject/{M}/cred/{K}/{sid}"] == "statement about a key other than the book's owner"
    assert reasons[f"reject/{M}/cred/{M}/{'00' * 32}"] == "content address mismatch"
    assert not any(k.startswith("reject/clearing-0/") for k in reasons)   # a clearing's base is not its speech
    assert audit_manifest(m, blobs) == []
