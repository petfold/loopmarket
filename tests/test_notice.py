"""Notices before claims (R6, 2026-09-29; `counterparty-gate.md` §6): the
claimant's notice travels sealed to the giver in the claimant's own book
(`notice/<loop>/<offer>`), the giver's cure sealed back (`cure/`), each
beside a salted commitment; the fold admits each only as its writer's own
speech. A cured matter leaves nothing readable in public; a claim that
cites the notice discloses the plaintext and the salt, and anyone checks
them against the commitment. The watch's re-check finds a relied-on
statement revoked or suspended since clearing. The clocks themselves are
factbond's procedure (`factbond.procedure.decide`), which reads these
records' content."""

import json
import secrets

import pytest
from recordstore import MemoryBytesStore, RecordStore

pytest.importorskip("coincurve", reason="sealed notices need the sig extra")

from loopmarket import Aggregator, OfferRegistry, Statement  # noqa: E402
from loopmarket.handoff import public_key_of  # noqa: E402
from loopmarket.notice import (  # noqa: E402
    cure_record, gives_of, lapsed, notice_record, opens, read, sealed,
)
from loopmarket.register import Register  # noqa: E402
from loopmarket.sigs import maker_address  # noqa: E402

NOW = 1_790_000_000
LOOP, OFFER = "1f" * 32, "2e" * 32
DAY = 86_400


def _keys():
    k = "0x" + secrets.token_hex(32)
    return k, maker_address(k)


def test_a_notice_travels_sealed_and_opens_only_for_its_recipient_and_its_claim():
    kp, P = _keys()
    kd, D = _keys()
    notice = notice_record(P, D, "ab" * 32, policy_ref="cd" * 32, sent_at=NOW, cure_period=7 * DAY)
    assert notice["cure_deadline"] == NOW + 7 * DAY and notice["kind"] == "notice"
    side, opening = sealed(notice, sender=P, recipient=D, recipient_public_key=public_key_of(kd))
    public = json.dumps(side)
    assert "ab" * 32 not in public and "cd" * 32 not in public and str(NOW) not in public   # nothing readable
    assert read(side, kd) == notice
    with pytest.raises(Exception):
        read(side, kp)                                                  # only the giver opens it
    # the claim's case file discloses the opening; anyone checks it against the book's commitment
    assert opens(side, opening)
    assert not opens(side, dict(opening, record=dict(notice, sent_at=NOW - DAY)))      # back-dated
    assert not opens(side, dict(opening, salt="00" * 32))
    assert not opens(dict(side, **{"from": D}), opening)                # the notice names its sender


def test_the_fold_admits_a_notice_and_a_cure_only_as_their_writers_speech():
    kp, P = _keys()
    kd, D = _keys()
    blobs = MemoryBytesStore()
    patient, dentist, other = (OfferRegistry(RecordStore(blobs)) for _ in range(3))
    side, _ = sealed(notice_record(P, D, "ab" * 32, policy_ref="cd" * 32, sent_at=NOW, cure_period=7 * DAY),
                     sender=P, recipient=D, recipient_public_key=public_key_of(kd))
    patient.send_notice(LOOP, OFFER, side)
    cure, _ = sealed(cure_record("notice-ref", D, NOW + DAY, evidence_ref="refund-tx"), sender=D, recipient=P,
                     recipient_public_key=public_key_of(kp))
    dentist.send_cure(LOOP, OFFER, cure)
    other.send_notice(LOOP, OFFER, side)                                # a copy of P's notice in someone else's book
    for book in (patient, dentist, other):
        book.commit()
    with pytest.raises(ValueError, match="unreadable"):
        patient.send_notice(LOOP, OFFER, {"v": 1, "from": P})
    agg = Aggregator(lambda: RecordStore(blobs))
    agg.announce(P, patient.store)
    agg.announce(D, dentist.store)
    agg.announce("0xother", other.store)
    m = agg.fold()
    fold = OfferRegistry(RecordStore.at(m.book_root, blobs))
    assert fold.notice(LOOP, OFFER) == side and fold.cure(LOOP, OFFER) == cure
    assert read(fold.cure(LOOP, OFFER), kp)["evidence_ref"] == "refund-tx"
    rejected = {k: v["reason"] for k, v in RecordStore.at(m.provenance_root, blobs).items("reject/")}
    assert rejected == {f"reject/0xother/notice/{LOOP}/{OFFER}": "notice from a key other than the book's owner"}


def test_the_watch_finds_a_statement_that_lapsed_since_clearing():
    from loopmarket import Bond, Thing, TimeWindow, give
    blobs = MemoryBytesStore()
    book = OfferRegistry(RecordStore(blobs))
    kd, D = _keys()
    g = give(D, Thing(("dentistry",), 1, "visit"), 30, valid=TimeWindow(0, NOW + DAY), nonce=1,
             bond=Bond(Thing(("stablecoin-eur",), 50, "EUR"), 50, "0xE"))
    book.publish(g)
    issuer = "0x" + "a7" * 20
    s = Statement(subject=D, category="dentist-licensed", issuer=issuer, kind="attested", as_of=NOW - DAY,
                  until=NOW + 30 * DAY, evidence="ee" * 32, path=(issuer,), paid_by="subject")
    book.present(s)
    book.commit()
    reg = Register(RecordStore(blobs))
    reg.issue(s.statement_id, NOW - DAY)
    reg.commit()
    record = {"legs": [{"give": g.offer_id, "gives": [g.offer_id], "want": "3d" * 32}]}
    pairs = list(gives_of(record, book))
    assert pairs == [(g.offer_id, D)]

    def statements_of(maker):
        return [st for st, _ in book.statements(maker)]
    assert lapsed(pairs, statements_of, {issuer: reg}) == []
    reg.suspend(s.statement_id, NOW)
    assert lapsed(pairs, statements_of, {issuer: reg}) == [(g.offer_id, s, "suspended")]
    reg.revoke(s.statement_id, NOW + 1)
    assert lapsed(pairs, statements_of, {issuer: reg}) == [(g.offer_id, s, "revoked")]
    assert lapsed(pairs, statements_of, {}) == []                       # an unread register reports nothing
