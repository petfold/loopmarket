"""Notices before claims (R6, 2026-09-29; `docs/plans/counterparty-gate.md`
§6, plan A2 and B1): rung zero of every claim on a reservation.

A claimant who relied on a giver and lost tells the giver, first, which
fact is wrong and until when it may cure — deliver, refund at the ladder,
correct the statement. Only refusal or silence past the cure deadline
opens the bonded claim, and the claim must come before the notice expires:
three record-checkable clocks, no judgement about when the claimant
discovered the fault. The clocks and the refusals are factbond's
(`factbond.procedure.decide`, whose `Notice` and `Cure` records are the
content carried here); loopmarket carries them between the parties:

    notice/<loop>/<offer>  -> the claimant's notice, sealed to the giver
    cure/<loop>/<offer>    -> the giver's answer, sealed to the claimant

each `{"v": 1, "from", "to", "commitment", "sealed"}`, written in the
writer's own book — the book is the channel, as for handoffs — and admitted
by the fold only there (`from` is the book's owner).

Why sealed, with a commitment beside the ciphertext (factbond THREATS T17,
2026-09-28): a notice names an accusation against a key, and a permanent
public store would make every notice a public accusation, cured or not. So
the public record is ciphertext the recipient opens and a salted hash of
the plaintext; a cured matter leaves nothing readable. When a claim cites
the notice, the claimant discloses the plaintext and the salt in the case
file, and anyone checks them against the commitment the book fixed under a
root (`opens`). The time a notice was *sent* is its `sent_at`, as good as
the root it was committed under; anchoring that root in time is factbond's
records-and-anchoring work.

`lapsed` is the watch's re-check before a leg's window: the statements a
cleared leg relied on that no longer stand under the registers' current
roots — the moment a notice is due. Keys and sealing are handoff's (ECIES
over the makers' secp256k1 keys, the `sig` extra, loaded lazily: B1).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Iterable

from .handoff import open_, seal
from .schema import Statement

NOTICE = "notice/"
CURE = "cure/"
VERSION = 1


def _body(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ref(record: dict) -> str:
    """A notice's or cure's reference, as factbond computes it (`_ref`: the
    SHA-256 of recordstore's canonical encoding) — what a cure names as the
    notice it answers, and a claim as the notice it follows."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def notice_record(notifier: str, accused: str, referred_fact: str, *, policy_ref: str, sent_at: int,
                  cure_period: int) -> dict:
    """A notice in factbond's `Notice` shape: the cure deadline is the
    class's cure period after sending (factbond's procedure refuses a
    shorter one)."""
    return {"notifier": notifier, "accused": accused, "referred_fact": referred_fact,
            "policy_ref": policy_ref, "sent_at": int(sent_at), "cure_deadline": int(sent_at) + int(cure_period),
            "v": 1, "kind": "notice"}


def cure_record(notice_ref: str, author: str, time: int, evidence_ref: str = "") -> dict:
    """The giver's answer in factbond's `Cure` shape."""
    return {"notice_ref": notice_ref, "author": author, "time": int(time), "evidence_ref": evidence_ref,
            "v": 1, "kind": "cure"}


def sealed(record: dict, *, sender: str, recipient: str, recipient_public_key: bytes) -> tuple[dict, dict]:
    """The sidecar record and the opening its writer keeps: the record
    sealed to the recipient beside a salted commitment to its plaintext."""
    salt = os.urandom(32)
    body = _body(record)
    side = {"v": VERSION, "from": sender, "to": recipient,
            "commitment": hashlib.sha256(salt + body).hexdigest(),
            "sealed": seal(body.decode("utf-8"), recipient_public_key)}
    return side, {"salt": salt.hex(), "record": record}


def read(side: dict, private_key_hex: str) -> dict:
    """The recipient opens a sealed notice or cure."""
    return json.loads(open_(side["sealed"], private_key_hex))


def opens(side: dict, opening: dict) -> bool:
    """Does a disclosed opening — the plaintext and the salt, cited in a
    claim's case file — match the commitment the book fixed? And is it the
    record between the parties the sidecar names?"""
    try:
        body = _body(opening["record"])
        digest = hashlib.sha256(bytes.fromhex(opening["salt"]) + body).hexdigest()
    except (KeyError, TypeError, ValueError):
        return False
    rec = opening["record"]
    parties = (rec.get("notifier"), rec.get("accused")) if rec.get("kind") == "notice" else (rec.get("author"), None)
    return digest == side.get("commitment") and parties[0] == side.get("from") \
        and (parties[1] is None or parties[1] == side.get("to"))


def fault(owner: str, rec: Any) -> str:
    """Why a `notice/` or `cure/` record is not `owner`'s speech, or ""."""
    if not isinstance(rec, dict) or rec.get("v") != VERSION:
        return "unreadable notice record"
    if rec.get("from") != owner:
        return "notice from a key other than the book's owner"
    if not rec.get("to") or not isinstance(rec.get("sealed"), dict) or "ct" not in rec["sealed"]:
        return "unreadable notice record"
    c = rec.get("commitment")
    if not (isinstance(c, str) and len(c) == 64 and all(ch in "0123456789abcdef" for ch in c)):
        return "unreadable notice record"
    return ""


def lapsed(gives: Iterable[tuple[str, str]], statements_of, registers) -> list[tuple[str, Statement, str]]:
    """The watch's re-check (§6): for each (give offer id, maker) a cleared
    loop took (`gives_of`), the statements that maker presented which its
    issuer's register now marks revoked or suspended, as (offer id,
    statement, what changed). A leg whose statement lapsed between clearing
    and the window is the giver's non-performance, and this is when the
    wanter's client writes the notice. `statements_of(maker)` reads the
    fold's `cred/`; `registers` maps a register id to the register at its
    latest root."""
    out = []
    for oid, maker in gives:
        for st in statements_of(maker):
            reg = registers.get(st.issuer)
            if reg is None:
                continue
            if reg.revoked(st.statement_id):
                out.append((oid, st, "revoked"))
            elif reg.suspended(st.statement_id):
                out.append((oid, st, "suspended"))
    return out


def gives_of(loop_record: dict, book, *, wanter: str | None = None) -> Iterable[tuple[str, str]]:
    """(give offer id, its maker) for every give a cleared loop took — or,
    with `wanter`, only the gives on legs whose want is that maker's: the
    ones whose statements it relied on, and whose notices are its to send."""
    for leg in loop_record.get("legs", []):
        if wanter is not None and book.get(leg["want"]).maker != wanter:
            continue
        for oid in leg.get("gives", [leg.get("give")]):
            if oid:
                yield oid, book.get(oid).maker
