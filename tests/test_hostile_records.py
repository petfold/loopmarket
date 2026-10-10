"""Hostile records that are well formed (the 2026-10 review, §7 suggestion
3): real keys, valid signatures and properly sealed payloads, each over
the wrong content or for the wrong party. The seeded mutator
(`test_schema.py`) and the garbage under every keyspace
(`test_federation.py`) feed the readers records they cannot parse; these
parse, and their signatures verify, so they get past any reader that
checks only that. Every reader must refuse or ignore them with a reason,
never crash, and never let one count.

The keys are throwaway, made here and never printed."""

import dataclasses
import secrets

import pytest
from recordstore import MemoryBytesStore, RecordStore

pytest.importorskip("coincurve", reason="signatures and sealing need the sig extra")

from loopmarket import Aggregator, OfferRegistry, Thing, TimeWindow, cli, give  # noqa: E402
from loopmarket.cli.claims import _public_key_for, _public_key_of  # noqa: E402
from loopmarket.handoff import open_, public_key_of, seal  # noqa: E402
from loopmarket.sigs import (  # noqa: E402
    contact_card_public_key, maker_address, sign_contact_card, sign_offer, verify_offer_sig,
)
from test_cli import Runner, _od_with_prelude  # noqa: E402

V = dict(valid=TimeWindow(0))


def _key():
    k = "0x" + secrets.token_hex(32)
    return k, maker_address(k)


def _fold(blobs, books):
    """Fold `books` ({owner: OfferRegistry}) as an aggregator would; returns
    (the folded book, {rejected key: reason})."""
    agg = Aggregator(lambda: RecordStore(blobs), aggregator_id="agg")
    for owner, book in books.items():
        agg.announce(owner, book.store)
    m = agg.fold()
    folded = OfferRegistry(RecordStore.at(m.book_root, blobs) if m.book_root else RecordStore(blobs))
    rejected = {k: v["reason"] for k, v in RecordStore.at(m.provenance_root, blobs).items("reject/")} \
        if m.provenance_root else {}
    return folded, rejected


# ---------------------------------------------------------------- signatures over other content

def test_a_signature_over_another_offer_vouches_for_nothing_else():
    """Bruno's genuine signature on one offer, replayed beside an offer
    Mallory wrote in his name, and Mallory's own valid signature on that
    forgery: neither makes it Bruno's. Mallory's own offer carrying her
    signature over a different offer of hers is folded without it, so no
    reader recovers a key from it to seal to: a signature over other bytes
    recovers to a key nobody holds."""
    kb, B = _key()
    km, M = _key()
    real = give(B, Thing(("ride", "geo(u24)")), 4, **V)
    forged = give(B, Thing(("ride", "geo(u24)")), 1, **V)                  # "Bruno rides for 1"
    forged2 = give(B, Thing(("ride", "geo(u24)")), 2, **V)
    sig_real = sign_offer(real, kb)
    assert verify_offer_sig(real, sig_real)
    assert not verify_offer_sig(forged, sig_real)                           # valid, over other bytes
    assert not verify_offer_sig(forged2, sign_offer(forged2, km))           # valid, by another key
    blobs = MemoryBytesStore()
    bruno, mallory = OfferRegistry(RecordStore(blobs)), OfferRegistry(RecordStore(blobs))
    bruno.publish(real)
    bruno.attach_signature(real.offer_id, sig_real)
    mallory.publish(forged)
    with pytest.raises(ValueError, match="does not recover"):
        mallory.attach_signature(forged.offer_id, sig_real)                 # the book refuses it too
    mallory.store.put(f"sig/{forged.offer_id}", sig_real)
    mallory.publish(forged2)
    mallory.store.put(f"sig/{forged2.offer_id}", sign_offer(forged2, km))
    mine = give(M, Thing(("ride", "geo(u24)")), 3, **V)
    other = give(M, Thing(("ride", "geo(u24)")), 5, **V)
    mallory.publish(mine)
    mallory.store.put(f"sig/{mine.offer_id}", sign_offer(other, km))       # her key, other bytes
    for book in (bruno, mallory):
        book.commit()
    folded, rejected = _fold(blobs, {B: bruno, M: mallory})
    for f in (forged, forged2):
        assert rejected[f"reject/{M}/offer/{f.offer_id}"] == "foreign maker without valid signature"
    assert {o.offer_id for o in folded.offers(include_filled=True)} == {real.offer_id, mine.offer_id}
    assert folded.signature(real.offer_id) == sig_real
    assert folded.signature(mine.offer_id) is None
    assert _public_key_of(folded, real.offer_id) == public_key_of(kb)
    with pytest.raises(ValueError, match="no public key here"):
        _public_key_of(folded, mine.offer_id)


def test_a_contact_card_signed_over_other_content_proves_no_key():
    """A card is a signature over the domain and its own address. Bruno's
    genuine card filed as Mallory's, and Mallory's own valid signature over
    one of her offers filed as her card, prove no key for her: the book
    refuses them, the fold rejects them with the reason, and a client
    sealing to her finds no key rather than a wrong one."""
    kb, _ = _key()
    _, bruno_card = sign_contact_card(kb)
    blobs = MemoryBytesStore()
    books = {}
    for card_of in ("bruno's card", "a signature over an offer"):
        km, M = _key()
        card = bruno_card if card_of == "bruno's card" else sign_offer(give(M, Thing(("ride",)), 1, **V), km)
        with pytest.raises(ValueError, match="does not recover"):
            contact_card_public_key(M, card)
        book = OfferRegistry(RecordStore(blobs))
        with pytest.raises(ValueError, match="does not recover"):
            book.publish_contact_card(M, card)
        book.store.put(f"key/{M.lower()}", card)
        book.commit()
        books[M] = book
    folded, rejected = _fold(blobs, books)
    for M in books:
        assert rejected[f"reject/{M}/key/{M.lower()}"] == \
            "a contact card that does not recover to the book's owner"
        assert folded.contact_card(M) is None
        with pytest.raises(ValueError, match="no public key here"):
            _public_key_for(folded, M)


def test_a_door_response_over_another_challenge_or_id_opens_nothing():
    """The possession witness signs the challenge with the id it vouches
    for. The giver's own key answering for another of its offers, an answer
    to another challenge, and a challenge another door issued all fail,
    and the door still opens for the honest answer after them."""
    from loopmarket.witness import DoorCheck, respond, signer
    key, G = _key()
    g = give(G, Thing(("repair",)), 10, **V, oracle="possession")
    other = give(G, Thing(("repair",)), 11, **V, oracle="possession")
    door, elsewhere = DoorCheck(), DoorCheck()
    c1, c2, c3 = door.challenge(), door.challenge(), door.challenge()
    assert signer(c1, g.offer_id, respond(c1, other.offer_id, key)) != G
    assert not door.possession(c1, respond(c1, other.offer_id, key), g.offer_id, G)   # the key, another id
    assert not door.possession(c2, respond(c3, g.offer_id, key), g.offer_id, G)       # another challenge's answer
    c4 = elsewhere.challenge()
    assert not door.possession(c4, respond(c4, g.offer_id, key), g.offer_id, G)       # not issued here
    assert door.possession(c3, respond(c3, g.offer_id, key), g.offer_id, G)           # the honest answer


# ---------------------------------------------------------------- a register's word over other content

def test_a_statement_re_keyed_to_another_subject_has_no_status():
    """Mallory takes the dentist's genuine statement, which the attester's
    register has issued, and re-keys it to herself. It is her speech about
    her own key, so the fold admits it, but its id is new and the register
    has no status for it: the gate refuses it at step 3. The genuine
    statement copied into her book is rejected by the fold, and read under
    her key all the same (a peer's book is not folded) the gate refuses it
    as a statement about someone else."""
    from loopmarket.gate import CounterpartyGate
    from test_gate import NOW, SPANS, T, WINDOW, World, _cat
    w = World()
    _, M = _key()
    forged = dataclasses.replace(w.statement, subject=M)
    assert forged.statement_id != w.statement.statement_id
    impostor = give(M, Thing(("dentistry", f"time({T})"), 10, "visit", step=1), 300, valid=w.dentist.valid,
                    nonce=9)
    mallory = OfferRegistry(RecordStore(w.blobs))
    mallory.publish(impostor)
    mallory.present(forged)
    mallory.store.put(f"cred/{w.statement.subject}/{w.statement.statement_id}",
                      {"statement": w.statement.to_record(), "presentation": None})
    mallory.commit()
    folded, rejected = _fold(w.blobs, {w.dentist.maker: w.book, M: mallory})
    assert rejected[f"reject/{M}/cred/{w.statement.subject}/{w.statement.statement_id}"] == \
        "statement about a key other than the book's owner"
    assert not any(k.startswith(f"reject/{M}/cred/{M}/") for k in rejected)
    assert [s.statement_id for s, _ in folded.statements(M)] == [forged.statement_id]
    gate = CounterpartyGate.over(folded, w.registers, now=NOW, span=SPANS.get)
    faults = gate.faults(w.patient, impostor, _cat(), window=WINDOW, taken=1, whole=10)
    assert faults == [f"dentist-licensed: 3 {w.statement.issuer}'s register has no status for the statement"]
    assert gate.faults(w.patient, w.dentist, _cat(), window=WINDOW, taken=1, whole=10) == []   # the genuine one
    entry = w.patient.requires.counterparty[0]
    assert gate.statement_faults(entry, w.statement, w.patient, impostor, _cat(), window=WINDOW) == \
        [f"statement about {w.statement.subject}, not {M}"]


# ---------------------------------------------------------------- sealed payloads for other parties

@pytest.fixture
def cleared(env, tmp_path, monkeypatch):
    """Amara and Bruno, each with a throwaway key, in one shared book:
    Bruno gives Amara a ride and Amara gives Bruno a piano lesson, cleared.
    Mallory and Carol have keys and no part in the loop; the judge has a
    key and a contact card in the book, and no offer."""
    from types import SimpleNamespace
    _od_with_prelude(tmp_path / "town.od", [("ride", []), ("piano-lesson", [])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "town.od"))
    monkeypatch.delenv("LOOP_MAKER")                   # identity = the signer's address
    keys = {name: _key() for name in ("amara", "bruno", "mallory", "carol", "judge")}
    run = Runner()

    def as_(name):
        monkeypatch.setenv("BEE_SIGNER", keys[name][0])

    as_("amara")
    run.ok("place", "home", "46.05,14.50,5km")
    ride_want = run.ok("want", "ride", "home", "5").strip().splitlines()[-1]
    run.ok("give", "piano-lesson", "home", "4")
    as_("bruno")
    run.ok("place", "depot", "46.05,14.50,5km")
    ride = run.ok("give", "ride", "geo(depot)", "4").strip().splitlines()[-1]
    run.ok("want", "piano-lesson", "geo(depot)", "5")
    assert "cleared" in run.ok("clearing")
    book = run.session.book
    for name in ("judge",):                              # an arbitrator with no offer: its card is its key
        address, card = sign_contact_card(keys[name][0])
        book.publish_contact_card(address, card)
    book.commit()
    return SimpleNamespace(run=run, as_=as_, book=book, loop=book.loop_of(ride), ride=ride, ride_want=ride_want,
                           key={n: k for n, (k, _) in keys.items()}, who={n: a for n, (_, a) in keys.items()})


def test_a_handoff_sealed_to_another_key_is_never_opened(cleared):
    """A handoff addressed to Bruno but sealed to Carol's key: Bruno's
    `watch` reports his fills, says on stderr why the handoff does not
    open, and tries again next pass; `handoffs` says the same. Nothing of
    the text, and no crash."""
    c = cleared
    record = dict(seal("Trubarjeva 12", public_key_of(c.key["carol"])),
                  **{"from": c.who["amara"], "to": c.who["bruno"]})
    c.book.attach_handoff(c.loop, c.ride_want, record)
    c.book.commit()
    assert open_(record, c.key["carol"]) == "Trubarjeva 12"          # sealed, just not to him
    c.as_("bruno")
    code, out, err = c.run("watch", "--once")
    assert code == 0 and out.count("filled   ") == 2
    assert "handoff  from" not in out and "Trubarjeva" not in out + err
    assert "cannot open (InvalidTag)" in err
    code, out, err = c.run("watch", "--once")
    assert code == 1 and "cannot open (InvalidTag)" in err            # nothing new; refused again
    assert "(cannot open: InvalidTag)" in c.run.ok("handoffs")


class _Escrow:
    """The escrow as `answer` and `rule` read it: one reservation, Amara its
    wanter, the judge its resolver, Bruno's deposit behind it."""

    def __init__(self, c, me: str):
        self.c, self.me = c, me

    def reservation(self, oid, loop):
        return {"amount": 10 ** 18, "wanter": self.c.who["amara"], "resolver": self.c.who["judge"],
                "settled": False, "held": True, "claim_only": False, "claim_until": 0}

    def deposit_of(self, oid):
        return {"giver": self.c.who["bruno"], "token": "0x0", "amount": 2 * 10 ** 18, "released": 0}

    def account(self):
        return type("Account", (), {"address": self.c.who[self.me]})()

    def hold(self, oid, loop):
        return {"gasUsed": 1}

    def resolve(self, oid, loop, amount):
        return {"gasUsed": 1}


def _case(c, kind, body, *, sender, to, sealed_to=None):
    """Write a case record from `sender` to `to` on the ride's leg, sealed
    to `sealed_to`'s key (`to`'s by default)."""
    from loopmarket.case import sealed
    side, _ = sealed(dict(body, v=1, kind=kind), sender=c.who[sender], recipient=c.who[to],
                     recipient_public_key=public_key_of(c.key[sealed_to or to]))
    c.book.write_case(c.loop, c.ride, kind, side)
    c.book.commit()


def _notice(c, kind, *, sender, to, sealed_to=None, **fields):
    from loopmarket.notice import cure_record, notice_record, sealed
    if kind == "notice":
        record = notice_record(c.who[sender], c.who[to], c.ride, policy_ref="cd" * 32, sent_at=1, cure_period=3)
    else:
        record = cure_record("ab" * 32, c.who[sender], 2)
    side, _ = sealed(dict(record, **fields), sender=c.who[sender], recipient=c.who[to],
                     recipient_public_key=public_key_of(c.key[sealed_to or to]))
    (c.book.send_notice if kind == "notice" else c.book.send_cure)(c.loop, c.ride, side)
    c.book.commit()


def test_a_sealed_record_that_does_not_read_never_stops_a_reader(cleared, monkeypatch):
    """Records sealed to the wrong key, and records sealed to the right key
    whose plaintext is not the record their kind names, each reported as
    unreadable with the reason, the pass finishing (so the next pass has
    nothing new); `cure` and `answer` refuse with the reason, and `rule`
    rules citing no claim. (Until 2026-10-10 `watch` read a record's fields
    outside its try, so a ruling whose `to_wanter` was not a number raised
    TypeError past the command line, and `cure`, `answer` and `rule` let
    cryptography's InvalidTag escape.)"""
    c = cleared
    A, B, J = c.who["amara"], c.who["bruno"], c.who["judge"]
    where = f"on {c.ride[:12]} in loop {c.loop[:16]}…"
    _notice(c, "notice", sender="amara", to="bruno", sealed_to="carol")
    _case(c, "claim", {"claimant": A, "amount": 5}, sender="amara", to="bruno", sealed_to="carol")
    _case(c, "ruling", {"arbitrator": J, "to_wanter": "half", "reason": "late"}, sender="judge", to="bruno")
    _case(c, "claim", {"claimant": A, "amount": 5}, sender="amara", to="judge", sealed_to="carol")
    _notice(c, "cure", sender="bruno", to="amara", time="noon")
    c.as_("bruno")
    code, out, err = c.run("watch", "--once")
    assert code == 0, err
    assert f"notice   from {A} {where}: cannot be read (InvalidTag)" in out and "loop cure" not in out
    assert f"case     {A} claim {where}: cannot be read (InvalidTag)" in out
    assert f"case     {J} ruling {where}: cannot be read (TypeError)" in out
    assert c.run("watch", "--once")[0] == 1                             # the pass finished: all seen
    code, out, err = c.run("cure", c.ride, "--loop", c.loop)
    assert code == 1 and "cannot be read with my key (InvalidTag)" in err
    monkeypatch.setattr(cli.clients, "_escrow_client", lambda session: _Escrow(c, "bruno"))
    code, out, err = c.run("answer", c.ride, "--loop", c.loop, "--text", "came on time")
    assert code == 1 and "cannot be read with my key (InvalidTag)" in err
    c.as_("judge")
    monkeypatch.setattr(cli.clients, "_escrow_client", lambda session: _Escrow(c, "judge"))
    out = c.run.ok("rule", c.ride, "all", "--loop", c.loop, "--reason", "no show")
    assert "ruled    1 to the wanter" in out
    from loopmarket.case import read
    assert read(c.book.case_record(c.loop, c.ride, "ruling", A), c.key["amara"])["claim_ref"] == ""
    c.as_("amara")
    code, out, err = c.run("watch", "--once")
    assert code == 0 and f"cured    by {B} {where}: cannot be read (TypeError)" in out


@pytest.mark.xfail(strict=True, reason="a notice or a cure counts from whoever wrote it: `watch` reports "
                   "Mallory's notice on Bruno's give as a notice, `cure` answers it, and `answer` seals the "
                   "giver's answer to whoever the claim's plaintext names as claimant")
def test_a_notice_cure_or_claim_counts_only_from_the_legs_party(cleared, monkeypatch):
    """Mallory, no party to the loop, seals a notice to Bruno on his ride,
    a cure to Amara on the same leg, and a claim to Bruno naming herself the
    claimant. A notice is the leg's wanter's and a cure its giver's, by the
    fold's loop record; a claim is the escrow reservation's wanter's. So
    Bruno's and Amara's `watch` set them aside on stderr with the reason,
    `cure` refuses, and `answer` refuses rather than seal Bruno's answer to
    Mallory; the judge's ruling cites no claim of hers."""
    c = cleared
    M = c.who["mallory"]
    _notice(c, "notice", sender="mallory", to="bruno", notifier=c.who["amara"])   # her plaintext names Amara
    _notice(c, "cure", sender="mallory", to="amara")
    _case(c, "claim", {"claimant": M, "accused": c.who["bruno"], "amount": 5, "text": "pay me"},
          sender="mallory", to="bruno")
    _case(c, "claim", {"claimant": M, "amount": 5}, sender="mallory", to="judge")
    c.as_("bruno")
    code, out, err = c.run("watch", "--once")
    assert f"notice   from {M}" not in out and "not this leg's wanter" in err
    code, out, err = c.run("cure", c.ride, "--loop", c.loop)
    assert code == 1 and "not this leg's wanter" in err
    monkeypatch.setattr(cli.clients, "_escrow_client", lambda session: _Escrow(c, "bruno"))
    code, out, err = c.run("answer", c.ride, "--loop", c.loop, "--text", "the gate code is 4711")
    assert code == 1 and "the reservation's wanter" in err
    assert not any(rec["to"].lower() == M.lower() for _, _, kind, rec in c.book.cases() if kind == "answer")
    c.as_("judge")
    monkeypatch.setattr(cli.clients, "_escrow_client", lambda session: _Escrow(c, "judge"))
    c.run.ok("rule", c.ride, "all", "--loop", c.loop, "--reason", "no show")
    from loopmarket.case import read
    assert read(c.book.case_record(c.loop, c.ride, "ruling", c.who["amara"]), c.key["amara"])["claim_ref"] == ""
    c.as_("amara")
    code, out, err = c.run("watch", "--once")
    assert f"cured    by {M}" not in out and "not this leg's giver" in err


@pytest.mark.xfail(strict=True, reason="`watch` reports a case record from whoever wrote it: a case's "
                   "parties are the escrow reservation's (its wanter, its deposit's giver, its resolver), "
                   "and watch does not read the escrow")
def test_a_case_record_counts_only_from_the_reservations_party(cleared):
    """Mallory seals a claim to Bruno and a ruling to Amara on their leg.
    Neither is hers to make, and neither should be reported as a claim or a
    ruling."""
    c = cleared
    M = c.who["mallory"]
    _case(c, "claim", {"claimant": M, "amount": 5}, sender="mallory", to="bruno")
    _case(c, "ruling", {"arbitrator": M, "to_wanter": 10 ** 18, "reason": "pay her"}, sender="mallory", to="amara")
    c.as_("bruno")
    assert f"case     {M}" not in c.run("watch", "--once")[1]
    c.as_("amara")
    assert f"case     {M}" not in c.run("watch", "--once")[1]


@pytest.mark.xfail(strict=True, reason="the fold keeps the first-merged value of a key two books write, and "
                   "it merges books in owner order (or_set_resolver): a stranger whose address sorts first "
                   "displaces a party's notice, cure or case record in every reader's fold. Keeping the "
                   "party's needs the fold to know a leg's parties when it admits a record, or one key per "
                   "writer")
def test_a_strangers_record_never_displaces_a_partys():
    """The wanter's notice and claim and the giver's cure, each displaced by
    a record Mallory writes under the same key in her own book."""
    from loopmarket.case import claim_record, sealed as case_sealed
    from loopmarket.notice import cure_record, notice_record, sealed
    loop, offer = "1f" * 32, "2e" * 32

    def key_whose_address(sorts_first: bool):
        # an address beginning 0x0 or 0x1 sorts before one beginning with
        # any other digit or letter, whatever the checksum's case
        while True:
            k, a = _key()
            if (a[2] in "01") == sorts_first:
                return k, a
    (kw, W), (kg, G), (kj, J) = key_whose_address(False), key_whose_address(False), _key()
    _, M = key_whose_address(True)
    blobs = MemoryBytesStore()
    wanter, giver, mallory = (OfferRegistry(RecordStore(blobs)) for _ in range(3))
    notice = lambda frm: sealed(notice_record(frm, G, "ab" * 32, policy_ref="cd" * 32, sent_at=1, cure_period=3),
                                sender=frm, recipient=G, recipient_public_key=public_key_of(kg))[0]
    cure = lambda frm: sealed(cure_record("ab" * 32, frm, 2), sender=frm, recipient=W,
                              recipient_public_key=public_key_of(kw))[0]
    claim = lambda frm: case_sealed(claim_record(frm, G, offer, loop, 5, sent_at=1), sender=frm, recipient=J,
                                    recipient_public_key=public_key_of(kj))[0]
    wanter.send_notice(loop, offer, notice(W))
    wanter.write_case(loop, offer, "claim", claim(W))
    giver.send_cure(loop, offer, cure(G))
    mallory.send_notice(loop, offer, notice(M))
    mallory.send_cure(loop, offer, cure(M))
    mallory.write_case(loop, offer, "claim", claim(M))
    for book in (wanter, giver, mallory):
        book.commit()
    folded, rejected = _fold(blobs, {W: wanter, G: giver, M: mallory})
    assert not rejected                                                  # each is its writer's own speech
    assert folded.notice(loop, offer)["from"] == W
    assert folded.cure(loop, offer)["from"] == G
    assert folded.case_record(loop, offer, "claim", J)["from"] == W
