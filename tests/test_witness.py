"""The door's witness types (R7, 2026-09-29; `counterparty-gate.md` §7):
`possession` and `photo-match` in clearing's verifiable set, a requirement
naming a door level as a cumulative category, and the settlement check —
countersign requires the witness, a replayed response fails, and an offer
naming an unrostered type is refused at submit."""

import secrets

import pytest
from recordstore import MemoryBytesStore, RecordStore

pytest.importorskip("eth_keys", reason="the door's witnesses need the sig extra")

from loopmarket import MockClearing, OfferRegistry, Ontology, Requires, SolverAgent, Thing, TimeWindow, give, want  # noqa: E402
from loopmarket.matching import check_match  # noqa: E402
from loopmarket.sigs import maker_address  # noqa: E402
from loopmarket.witness import (  # noqa: E402
    DoorCheck, accepted_types, countersign_ready, photo_commitment, photo_opens, respond,
)

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))


def _cat():
    return Ontology().load({"repair": [], "lesson": []})


def test_door_levels_are_cumulative_categories():
    assert accepted_types(["door-at-least-possession"]) == {"possession", "photo-match"}
    assert accepted_types(["door-at-least-photo"]) == {"photo-match"}
    assert accepted_types(["countersign", "door-at-least-photo"]) == {"countersign", "photo-match"}
    cat = _cat()
    strict = want("w", Thing(("repair",)), 20, **V, requires=Requires(oracles=("door-at-least-photo",)))
    loose = want("w", Thing(("repair",)), 20, **V, nonce=2, requires=Requires(oracles=("door-at-least-possession",)))
    by_key = give("g", Thing(("repair",)), 10, **V, oracle="possession", v=5)
    by_face = give("g", Thing(("repair",)), 10, **V, nonce=3, oracle="photo-match", v=5)
    assert check_match(by_face, strict, cat, now=NOW) and not check_match(by_key, strict, cat, now=NOW)
    assert check_match(by_face, loose, cat, now=NOW) and check_match(by_key, loose, cat, now=NOW)


def test_countersign_requires_the_witness_and_a_replay_fails():
    key = "0x" + secrets.token_hex(32)
    giver = maker_address(key)
    g = give(giver, Thing(("repair",)), 10, **V, oracle="photo-match")
    door = DoorCheck()
    assert countersign_ready(g) == "the giver's key has not answered a fresh challenge"
    c = door.challenge()
    answer = respond(c, g.offer_id, key)
    assert door.possession(c, answer, g.offer_id, giver)
    assert not door.possession(c, answer, g.offer_id, giver)                     # replayed: spent
    c2 = door.challenge()
    assert not door.possession(c2, respond(c2, g.offer_id, "0x" + secrets.token_hex(32)), g.offer_id, giver)
    assert countersign_ready(g, possession=True) == "the face has not been confirmed against the committed photo"
    salt, face = secrets.token_bytes(32), b"the repairer"
    commitment = photo_commitment(face, salt)
    assert photo_opens(commitment, face, salt) and not photo_opens(commitment, b"someone else", salt)
    assert countersign_ready(g, possession=True, photo_confirmed=True) == ""
    assert countersign_ready(give(giver, Thing(("repair",)), 10, **V, oracle="possession"), possession=True) == ""
    assert countersign_ready(give(giver, Thing(("repair",)), 10, **V)) == ""        # plain countersign
    assert "no settlement check" in countersign_ready(give(giver, Thing(("repair",)), 10, **V, oracle="locker"))


def test_a_door_witness_clears_and_an_unrostered_type_is_refused_at_submit():
    cat = _cat()
    for oracle, accepted in (("possession", True), ("photo-match", True), ("registry-transfer", False)):
        book = OfferRegistry(RecordStore(MemoryBytesStore()))
        book.publish_many([give("a", Thing(("repair",)), 10, **V, oracle=oracle), want("b", Thing(("repair",)), 20, **V),
                           give("b", Thing(("lesson",)), 10, **V), want("a", Thing(("lesson",)), 20, **V)])
        book.commit()
        clearing = MockClearing(book, cat, clock=lambda: NOW)
        receipts = SolverAgent(book, cat, clearing=clearing, solver_id="t").step(now=NOW)
        assert [r.accepted for r in receipts] == [accepted]
        if not accepted:
            assert receipts[0].reason == "unverifiable oracle type: registry-transfer"
