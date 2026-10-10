"""The golden corpus (`tests/fixtures/golden_records.txt`): book records as
loopmarket wrote them still read, under the ids they got, and re-encode to
the same bytes (U2). Offer records of every version, v1 to v7; loop
records of every shape a book holds, the 2026-08 loop record and loop
record v1 and v2; and the fills written with them. Behaviour tests would
pass if an encoding changed on both sides at once; these pin the bytes
(the 2026-10 review's suggestion 4, ontodag `docs/plans/REVIEW_2026-10.md`
§7). The fixture is never regenerated to make this pass:
`tests/fixtures/make_golden.py` says when it may be."""

import hashlib
import json
from pathlib import Path

from recordstore import MemoryBytesStore, RecordStore, canonical_bytes

from loopmarket import Circulation, Offer, OfferRegistry, q
from loopmarket.beat import legs_from_record, proposal_from_record
from loopmarket.registry import LegRecord

FIXTURE = Path(__file__).parent / "fixtures" / "golden_records.txt"


def _corpus() -> dict[str, bytes]:
    records: dict[str, bytes] = {}
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, text = line.partition("\t")
            assert key not in records, f"{key} twice"
            records[key] = text.encode("utf-8")
    return records


CORPUS = _corpus()


def _of(prefix: str) -> dict:
    """The corpus's records under `prefix`, keyed by the rest of the key."""
    return {k[len(prefix):]: json.loads(v) for k, v in CORPUS.items() if k.startswith(prefix)}


def _book() -> OfferRegistry:
    """One book holding the whole corpus, as an old book's store holds it.
    The reconciled commit runs the U11 check over every loop and fill."""
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    for key, data in CORPUS.items():
        book.store.put(key, json.loads(data))
    book.commit()
    return book


def test_the_fixture_is_canonical_and_covers_every_version_and_shape():
    for key, data in CORPUS.items():
        assert canonical_bytes(json.loads(data)) == data, key
    kinds = {(rec["v"], "give" if rec["gives"]["type"] == "thing" else "want")
             for rec in _of("offer/").values()}
    assert kinds == {(v, kind) for v in range(1, 8) for kind in ("give", "want")}
    assert {rec.get("v") for rec in _of("loop/").values()} == {None, 1, 2}
    fills = _of("fill/")
    assert any(rec == {"loop": rec["loop"]} for rec in fills.values())       # 2026-08: the loop alone
    assert any("gives" in rec for rec in fills.values())                     # a want's
    assert any(set(rec) == {"loop", "qty"} and "/" not in k for k, rec in fills.items())   # a give whole
    assert any("/" in k for k in fills)                                      # a give in part


def test_every_offer_reads_back_under_its_id():
    """Each record parses, hashes to the id it is stored under, and
    re-encodes to the same bytes in its own version."""
    bad = []
    for oid, rec in _of("offer/").items():
        data = CORPUS[f"offer/{oid}"]
        offer = Offer.from_record(rec)
        if not (hashlib.sha256(data).hexdigest() == oid == offer.offer_id
                and offer.canonical_bytes() == data and offer.v == rec["v"]):
            bad.append(oid)
    assert not bad, bad


def test_every_loop_reads_and_hashes_to_its_id():
    """Every leg parses through `LegRecord`, names offers the corpus holds,
    and the legs rebuilt from the book hash to the record's `loop_id`,
    which is its key."""
    book = _book()
    for lid, rec in _of("loop/").items():
        legs = LegRecord.of_loop(rec)
        assert legs and book.loop_legs(lid) == legs, lid
        assert all(f"offer/{oid}" in CORPUS for leg in legs for oid in leg.offer_ids), lid
        assert rec["loop_id"] == lid == Circulation(legs_from_record(rec, book)).loop_id, lid


def test_versioned_loop_records_re_encode_with_their_fills():
    """Loop record v1 and v2 are the trace of a proposal: rebuilt from the
    book as a challenger rebuilds it (`proposal_from_record`), the proposal
    writes the same bytes and the same fills, key for key."""
    book = _book()
    fills = {k: v for k, v in CORPUS.items() if k.startswith("fill/")}
    versioned = 0
    for lid, rec in _of("loop/").items():
        if "v" not in rec:
            continue
        proposal = proposal_from_record(rec, book)
        assert canonical_bytes(proposal.to_record()) == CORPUS[f"loop/{lid}"], lid
        written = {f"fill/{k}": canonical_bytes(v) for k, v in proposal.fills().items()}
        assert written == {k: v for k, v in fills.items() if json.loads(v)["loop"] == lid}, lid
        versioned += 1
    assert versioned >= 4


def test_every_fill_reads_and_the_registry_follows_it():
    """Every fill names a loop of the corpus (a partial one under its key
    too); an offer of a 2026-08 loop carries `{"loop"}` alone and reads as
    filled by it; what fills took is what the registry says was taken."""
    book = _book()
    loops = _of("loop/")
    fills = _of("fill/")
    for key, rec in fills.items():
        oid, _, part = key.partition("/")
        assert rec["loop"] in loops and part in ("", rec["loop"]), key
        assert rec["loop"] in book.loops_of(oid), key
    for lid, rec in loops.items():
        if "v" in rec:
            continue
        for leg in LegRecord.of_loop(rec):
            for oid in leg.offer_ids:
                assert fills[oid] == {"loop": lid} and book.loop_of(oid) == lid and book.is_filled(oid)
    for key, rec in fills.items():
        oid, _, part = key.partition("/")
        offer = book.get(oid)
        if part:
            taken = sum(q(r["qty"]) for k, r in fills.items() if k.startswith(f"{oid}/"))
            assert book.taken(oid) == taken <= q(offer.thing.qty), key
        elif "qty" in rec:
            assert q(rec["qty"]) == q(offer.thing.qty) and book.is_filled(oid), key
