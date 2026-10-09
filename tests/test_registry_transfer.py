"""The title register's transfer as the handover witness (I4, 2026-09-29
night; `items-and-ownership.md` §5.2): for land and vehicles the register
is the title, so a give declaring `registry-transfer(ID)` is performed when
the register ID shows every item it names held by the wanter. The wanter
accepts exactly the registers she names (`require_transfer`); clearing
admits the type only on a give that names an item; the register records
titles (`transfer`, `holder`); the wanter's `watch` reports the transfer
and `countersign` refuses before it."""


from ontodag import OntoDAG
from recordstore import MemoryBytesStore, RecordStore

from loopmarket import MockClearing, OfferRegistry, Ontology, Requires, SolverAgent, Thing, TimeWindow, give, want
from loopmarket.items import vin_id
from loopmarket.matching import check_match
from loopmarket.register import Register
from loopmarket.witness import countersign_ready, transfer_faults, transfer_register

NOW = 5_000
V = dict(valid=TimeWindow(0, 1_000_000))
REG, OTHER = "0x" + "4e" * 20, "0x" + "0f" * 20
H = vin_id("WVWZZZ1JZXW000001")


def _cat():
    cat = Ontology(OntoDAG())
    cat.declare_item_heads()
    cat.load({"car": [], "lesson": []})
    return cat


def test_the_type_names_its_register_and_the_register_names_the_holder():
    assert transfer_register(f"registry-transfer({REG})") == REG
    for bad in ("registry-transfer()", "registry-transfer", "registry-transfer(a b)", "possession", None):
        assert transfer_register(bad) is None
    reg = Register(RecordStore(MemoryBytesStore()))
    car = give("seller", Thing(("car", f"item({H})"), 1, "car"), 50, **V, nonce=1, oracle=f"registry-transfer({REG})")
    assert "not held by buyer" in transfer_faults(car, "buyer", reg)[0]
    assert "is not read" in transfer_faults(car, "buyer", None)[0]
    reg.transfer(H, "seller", 100)
    reg.transfer(H, "buyer", 200)
    assert reg.holder(H) == {"holder": "buyer", "at": 200, "from": "seller"}
    assert transfer_faults(car, "buyer", reg, since=150) == []
    assert "before the loop cleared" in transfer_faults(car, "buyer", reg, since=250)[0]
    plain = give("seller", Thing(("car",), 1, "car"), 50, **V, nonce=2, oracle=f"registry-transfer({REG})")
    assert "names no item" in transfer_faults(plain, "buyer", reg)[0]
    assert "has not shown the transfer" in countersign_ready(car)
    assert countersign_ready(car, transferred=True) == ""


def test_the_wanter_names_the_register_and_clearing_needs_an_item():
    cat = _cat()
    car = give("seller", Thing(("car", f"item({H})"), 1, "car"), 50, **V, nonce=1, oracle=f"registry-transfer({REG})")
    trusts = want("buyer", Thing(("car", f"item({H})"), 1, "car"), 90, **V, nonce=2,
                  requires=Requires(oracles=(f"registry-transfer({REG})",)))
    elsewhere = want("buyer", Thing(("car", f"item({H})"), 1, "car"), 90, **V, nonce=3,
                     requires=Requires(oracles=(f"registry-transfer({OTHER})",)))
    assert check_match(car, trusts, cat, now=NOW) is not None
    assert check_match(car, elsewhere, cat, now=NOW) is None           # a register she did not name
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    back = [give("buyer", Thing(("lesson",), 1, "hour"), 5, **V, nonce=4),
            want("seller", Thing(("lesson",), 1, "hour"), 60, **V, nonce=5)]
    book.publish_many([car, trusts, *back])
    book.commit()
    (r,) = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t").step(now=NOW)
    assert r.accepted
    # the same witness on a give that names no item: nothing a register could transfer
    book = OfferRegistry(RecordStore(MemoryBytesStore()))
    itemless = give("seller", Thing(("car",), 1, "car"), 50, **V, nonce=6, oracle=f"registry-transfer({REG})")
    wants = want("buyer", Thing(("car",), 1, "car"), 90, **V, nonce=7,
                 requires=Requires(oracles=(f"registry-transfer({REG})",)))
    book.publish_many([itemless, wants, *back])
    book.commit()
    receipts = SolverAgent(book, cat, clearing=MockClearing(book, cat, clock=lambda: NOW), solver_id="t").step(now=NOW)
    assert receipts and not receipts[0].accepted and "unverifiable oracle type" in receipts[0].reason


from test_cli import Runner, _od_with_prelude


def test_the_title_register_at_the_command_line(env, tmp_path, monkeypatch):
    """A vehicle register run with `register transfer`; a buyer's want with
    `require_transfer`, a seller's give with `oracle registry-transfer(ID)`;
    after clearing the buyer's `watch` stays quiet until the register shows
    the car held by the buyer, then says so once."""
    from loopmarket import cli
    _od_with_prelude(tmp_path / "town.od", [("car", []), ("lesson", [])])
    monkeypatch.setenv("LOOP_CATALOGUE", str(tmp_path / "town.od"))
    with open(tmp_path / "town.od", "a") as fh:
        fh.write("item prefix-dimension\n")
    run = Runner()
    run.session.book
    spec = f"rs:{tmp_path / 'vehicles'}"
    monkeypatch.setenv("LOOP_BOOK", spec)
    monkeypatch.setenv("LOOP_MAKER", REG)
    registrar = Runner()
    registrar.ok("register", "transfer", H, "seller")
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    run.ok("set", "registers", f"{REG}={spec}")
    monkeypatch.setenv("LOOP_MAKER", "seller")
    run.ok("set", "oracle", f"registry-transfer({REG})")
    car_id = run.ok("give", "car", f"item({H})", "50").strip().splitlines()[-1]
    run.ok("set", "oracle", "countersign")
    run.ok("want", "lesson", "60")
    monkeypatch.setenv("LOOP_MAKER", "buyer")
    run.ok("give", "lesson", "5")
    run.ok("set", "require_transfer", REG)
    out = run.ok("want", "car", f"item({H})", "90")
    assert f"oracle registry-transfer({REG})" in out
    run.ok("set", "require_transfer", "")
    assert "cleared" in run.ok("clearing")
    loop_id = run.session.book.loop_of(car_id)
    assert "transfer " not in run.ok("watch", "--once")
    assert "is not held by buyer" in cli._transfer_faults(run.session, car_id, loop_id, "buyer")[0]
    monkeypatch.setenv("LOOP_BOOK", spec)
    monkeypatch.setenv("LOOP_MAKER", REG)
    registrar.ok("register", "transfer", H, "buyer")
    assert "held by buyer" in registrar.ok("register", "status")
    monkeypatch.setenv("LOOP_BOOK", f"rs:{tmp_path / 'book'}")
    monkeypatch.setenv("LOOP_MAKER", "buyer")
    out = run.ok("watch", "--once")
    assert f"transfer {car_id[:12]}" in out and f"the register {REG} shows it held by me" in out
    assert cli._transfer_faults(run.session, car_id, loop_id, "buyer") == []
    code, out, err = run("set", "oracle", "registry-transfer()")
    assert code != 0
    for key in ("registers",):
        monkeypatch.setenv("LOOP_" + key.upper(), ""); run.ok("set", key, "")
