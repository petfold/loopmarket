"""A case before one named arbitrator (2026-10-01, Peter: the default
resolver of a leg is one arbitrator both sides accept, whose ruling is
final — commercial arbitration's model; `counterparty-gate.md` §7a).

The escrow already gives such an arbitrator its two acts: a key named as a
reservation's resolver `hold`s it (the quiet timeout stops) and `resolve`s
it, finally. What the book adds is the case between them, carried like a
notice — sealed to each recipient beside a salted commitment, in the
writer's own book, admitted by the fold only as the writer's speech:

    case/<loop>/<offer>/claim/<to>    the wanter's claim: an amount of the
                                       reservation, its evidence, the notice it
                                       follows — to the arbitrator and the giver
    case/<loop>/<offer>/answer/<to>   the giver's answer — to the arbitrator
                                       and the claimant
    case/<loop>/<offer>/ruling/<to>   the arbitrator's reasons — to both
                                       parties; the money moves on chain

Each party sees what the other submitted (the claim goes to the giver, the
answer to the claimant), and the ruling's reasons go to both: due process
without a forum. Why sealed: a claim names an accusation against a key, and
a permanent public store would make it a public accusation, decided or not
(factbond THREATS T17); a party who wants reasons read by peers — the
reputation signal of `counterparty-gate.md` §7a — discloses the opening.
Keys are handoff's (ECIES over secp256k1, the `sig` extra, loaded lazily:
B1); a key with no signed offer is sealed to through its contact card.
"""

from __future__ import annotations

from typing import Any

from .notice import ref     # a case record's reference, as factbond computes it

__all__ = ["CASE", "KINDS", "VERSION", "answer_record", "claim_record",
           "fault", "key", "read", "ref", "ruling_record", "sealed"]

CASE = "case/"
VERSION = 1
KINDS = ("claim", "answer", "ruling")


def claim_record(claimant: str, accused: str, offer: str, loop: str, amount: int, *, sent_at: int,
                 evidence_ref: str = "", notice_ref: str = "", text: str = "") -> dict:
    """The wanter's claim: `amount` of the reservation, in its smallest units."""
    return {"v": VERSION, "kind": "claim", "claimant": claimant, "accused": accused, "offer": offer,
            "loop": loop, "amount": int(amount), "sent_at": int(sent_at), "evidence_ref": evidence_ref,
            "notice_ref": notice_ref, "text": text}


def answer_record(author: str, claim_ref: str, *, time: int, evidence_ref: str = "", text: str = "") -> dict:
    """The giver's answer to a claim, named by its reference."""
    return {"v": VERSION, "kind": "answer", "author": author, "claim_ref": claim_ref, "time": int(time),
            "evidence_ref": evidence_ref, "text": text}


def ruling_record(arbitrator: str, claim_ref: str, to_wanter: int, *, time: int, reason: str) -> dict:
    """The arbitrator's ruling and its reasons; the payout is the escrow's
    `resolve`, this the record of why."""
    return {"v": VERSION, "kind": "ruling", "arbitrator": arbitrator, "claim_ref": claim_ref,
            "to_wanter": int(to_wanter), "time": int(time), "reason": reason}


def sealed(record: dict, *, sender: str, recipient: str, recipient_public_key: bytes) -> tuple[dict, dict]:
    """The sidecar record and the opening its writer keeps."""
    from . import notice
    side, opening = notice.sealed(record, sender=sender, recipient=recipient,
                                  recipient_public_key=recipient_public_key)
    side["kind"] = record["kind"]
    return side, opening


def read(side: dict, private_key_hex: str) -> dict:
    """The recipient opens a sealed claim, answer or ruling."""
    from . import notice
    return notice.read(side, private_key_hex)


def key(loop_id: str, offer_id: str, kind: str, to: str, writer: str) -> str:
    """Where `writer`'s case record of `kind` to `to` is kept, one key per
    writer (review item 23): `case/<loop>/<offer>/<kind>/<to>/<writer>`."""
    return f"{CASE}{loop_id}/{offer_id}/{kind}/{to.lower()}/{writer.lower()}"


def fault(owner: str, key_: str, rec: Any) -> str:
    """Why a `case/` record is not `owner`'s speech under `owner`'s key, or ""."""
    parts = key_[len(CASE):].split("/")
    if len(parts) == 4 and parts[2] in KINDS:
        return "a case key that does not name its writer"
    if len(parts) != 5 or parts[2] not in KINDS:
        return "unreadable case record"
    if parts[4] != owner.lower():
        return "a case record under another writer's key"
    if not isinstance(rec, dict) or rec.get("v") != VERSION or rec.get("kind") != parts[2]:
        return "unreadable case record"
    if str(rec.get("from", "")).lower() != owner.lower():
        return "a case record from a key other than the book's owner"
    if str(rec.get("to", "")).lower() != parts[3]:
        return "a case record addressed otherwise than its key says"
    if not isinstance(rec.get("sealed"), dict) or "ct" not in rec["sealed"]:
        return "unreadable case record"
    c = rec.get("commitment")
    if not (isinstance(c, str) and len(c) == 64 and all(ch in "0123456789abcdef" for ch in c)):
        return "unreadable case record"
    return ""
