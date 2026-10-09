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


from test_cli import NOW as CLI_NOW, Runner, _od_with_prelude


def test_watch_reports_a_lapsed_licence_and_the_notice_and_cure_travel_sealed(env, tmp_path, monkeypatch):
    """R6 at the command line (2026-09-29 night): a patient's want requires
    a licensed dentist; the attester's register is read by spec (`set
    registers`), the loop clears through the gate and pins it. The licence
    is revoked after clearing: the patient's `watch` reports it lapsed with
    the notice to send; `notice` seals it to the dentist; the dentist's
    `watch` opens it and `cure` answers, sealed back; the patient's `watch`
    reports the cure. The patient keeps the opening a claim would cite."""
    from loopmarket import Credential, Requires, Thing, want
    from loopmarket.cli import _open_book
    from loopmarket.sigs import sign_offer
    _od_with_prelude(tmp_path / "town.od", [("dentistry", []), ("lesson", []), ("licence", []),
                                             ("dentist-licensed", ["licence"])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "town.od"))
    monkeypatch.delenv("LOOP_MAKER")                   # identity = the signer's address
    (kp, P), (kd, D) = _keys(), _keys()
    ATT = "0x" + "a7" * 20

    def as_(key):
        monkeypatch.setenv("BEE_SIGNER", key)

    run = Runner()
    as_(kd)
    give_id = run.ok("give", "dentistry", "4").strip().splitlines()[-1]
    run.ok("want", "lesson", "5")
    as_(kp)
    run.ok("give", "lesson", "3")
    book = run.session.book
    g = book.get(give_id)
    w = want(P, Thing(("dentistry",), 1, "unit"), 5, valid=g.valid, nonce=7, ontology_root=g.ontology_root,
             registry_version=g.registry_version, contract_version=g.contract_version,
             requires=Requires(counterparty=(Credential("dentist-licensed", ("attested",), roots=(ATT,),
                                                        max_root_age=DAY),)))
    book.publish(w)
    book.attach_signature(w.offer_id, sign_offer(w, kp))
    s = Statement(subject=D, category="dentist-licensed", issuer=ATT, kind="attested", as_of=CLI_NOW - DAY,
                  until=CLI_NOW + 30 * DAY, evidence="ee" * 32, path=(ATT,), paid_by="subject")
    book.present(s)
    book.commit()
    reg = Register(_open_book(f"rs:{tmp_path / 'attester'}").store)
    reg.issue(s.statement_id, CLI_NOW - DAY)
    reg.heartbeat(CLI_NOW - 100)
    reg.commit()
    assert run("clearing")[0] == 1                     # the register unread: the gate refuses (U7)
    run.ok("set", "registers", f"{ATT}=rs:{tmp_path / 'attester'}")
    assert "cleared" in run.ok("clearing")
    loop_id = run.session.book.loop_of(give_id)
    assert run.session.book.store.get(f"loop/{loop_id}")["register_roots"] == {ATT: reg.root}
    assert "lapsed" not in run.ok("watch", "--once")   # the fills; nothing lapsed yet
    reg.revoke(s.statement_id, CLI_NOW - 10)
    reg.commit()
    out = run.ok("watch", "--once")
    assert f"lapsed   dentist-licensed of {D}" in out and "revoked" in out and "loop notice" in out
    assert run("watch", "--once")[0] == 1              # reported once
    code, out, err = run("notice", give_id[:12])
    assert code != 0                                   # the cure period is mine to state, no default
    out = run.ok("notice", give_id[:12], "--fact", s.statement_id[:12], "--cure", "3d")
    assert f"notice   sent to {D}" in out
    side = run.session.book.notice(loop_id, give_id)
    assert side["from"] == P and side["to"] == D and s.statement_id not in json.dumps(side)
    path = out.strip().rsplit(" ", 1)[-1]
    opening = json.loads(open(path).read())
    assert opens(side, opening) and opening["record"]["referred_fact"] == s.statement_id
    as_(kd)
    out = run.ok("watch", "--once")
    assert f"notice   from {P} on {give_id[:12]}" in out and "cure by" in out
    as_(kp)
    assert "no notice to me" in run("cure", give_id[:12])[2]    # the patient has none to answer
    as_(kd)
    assert f"cure     sent to {P}" in run.ok("cure", give_id[:12], "--evidence", "ab" * 32)
    as_(kp)
    out = run.ok("watch", "--once")
    assert f"cured    by {D} on {give_id[:12]}" in out and "evidence abababab" in out
    for key in ("registers",):
        monkeypatch.setenv("LOOP_" + key.upper(), ""); run.ok("set", key, "")


def test_the_credential_case_runs_from_the_command_line(env, tmp_path, monkeypatch):
    """C7 (2026-09-29 night): an attester runs a register in its own book
    (`register issue` prints the statement), the dentist presents it (`cred
    present`), the patient's want requires it (`require_credentials`), the
    loop clears through the registers read by spec; the attester revokes and
    the patient's `cred` and `watch` see it."""
    _od_with_prelude(tmp_path / "town.od", [("dentistry", []), ("lesson", []), ("licence", []),
                                             ("dentist-licensed", ["licence"])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "town.od"))
    monkeypatch.delenv("LOOP_MAKER")
    (kp, _), (kd, D), (ka, A) = _keys(), _keys(), _keys()

    def as_(key):
        monkeypatch.setenv("BEE_SIGNER", key)

    run = Runner()
    run.session.book                                    # my book, opened before the register's
    book_spec = f"rs:{tmp_path / 'attester'}"
    monkeypatch.setenv("LOOP_BOOK", book_spec)
    as_(ka)
    attester = Runner()
    out = attester.ok("register", "issue", D, "dentist-licensed", "--until", "30d", "--evidence", "ee" * 32,
                      "--paid-by", "subject")
    record = json.loads(out)
    assert record["issuer"] == A and record["subject"] == D and record["path"] == [A]
    code, out, err = attester("register", "issue", D, "dentist-licensed", "--until", "30d")
    assert code != 0 and "--evidence" in err            # what was checked is the issuer's to state
    attester.ok("register", "accredit", "0x" + "cc" * 20, "licence", "--until", "365d")
    monkeypatch.delenv("LOOP_BOOK")
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    (tmp_path / "st.json").write_text(json.dumps(record))
    as_(kd)
    out = run.ok("cred", "present", str(tmp_path / "st.json"))
    assert "presented" in out and "dentist-licensed (attested" in out
    assert "issuer's register not read" in run.ok("cred")
    as_(kp)
    code, out, err = run("cred", "present", str(tmp_path / "st.json"))
    assert code != 0 and "subject's own book" in err
    run.ok("set", "registers", f"{A}={book_spec}")
    assert ": issued" in run.ok("cred", D)
    as_(kd)
    give_id = run.ok("give", "dentistry", "4").strip().splitlines()[-1]
    run.ok("want", "lesson", "5")
    as_(kp)
    run.ok("give", "lesson", "3")
    run.ok("set", "require_credentials", f"dentist-licensed attested root:{A} age:1d")
    out = run.ok("want", "dentistry", "5")
    assert f"credentials dentist-licensed attested root:{A} age:1d" in out and "v6" in out
    monkeypatch.setenv("LOOP_REQUIRE_CREDENTIALS", ""); run.ok("set", "require_credentials", "")
    assert "cleared" in run.ok("clearing")
    assert run.session.book.is_filled(give_id)
    as_(ka)
    assert attester("register", "revoke", record_id(record)[:10])[0] == 0
    out = attester.ok("register", "status")
    assert "revoked" in out and "accredit 0x" + "cc" * 20 + " for licence" in out and "seq 2" in out   # roots 0, 1, 2
    as_(kp)
    assert ": revoked" in run.ok("cred", D)
    assert f"lapsed   dentist-licensed of {D}" in run.ok("watch", "--once")
    for key in ("registers",):
        monkeypatch.setenv("LOOP_" + key.upper(), ""); run.ok("set", key, "")


def record_id(record) -> str:
    return Statement.from_record(record).statement_id
