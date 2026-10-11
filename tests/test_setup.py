"""`loop setup`, the first start (docs/plans/cli.md §16; questions 34 and 35,
decided by Peter 2026-10-11). The Bee node is faked here: nothing is spent,
and the node's key is a throwaway keystore made in the test."""

import io
import json
import os

import pytest

from loopmarket.cli import setup

from test_cli import Runner

KEY_ADDRESS_ENOUGH = setup.ENOUGH_WEI * 10


@pytest.fixture
def fresh(env, monkeypatch):
    """env's homes, without the settings env gives through the environment,
    so what setup writes to the config file is what loop reads."""
    for var in ("LOOP_CATALOGUE", "LOOP_BOOK", "LOOP_MAKER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("USER", "peter")
    return env


def answers(*items):
    it = iter(items)
    return lambda prompt: next(it)


def fake_node(**over):
    node = {"api": "http://node:1633", "mode": "light", "address": "0x" + "ab" * 20,
            "xdai_wei": 10 ** 17, "bzz_plur": 4 * 10 ** 16,
            "batches": [{"batchID": "cd" * 32, "usable": True, "batchTTL": 40 * 86400}]}
    node.update(over)
    return node


def small_store(tmp_path):
    from ontodag import OntoDAG, native, prelude
    d = OntoDAG()
    prelude.apply(d)
    d.put("apple", [])
    path = tmp_path / "small.od"
    native.save(d, str(path))
    return str(path)


def test_without_a_node_the_defaults_make_a_demo_ready_for_offers(fresh, monkeypatch):
    monkeypatch.setattr(setup, "node_status", lambda api: None)
    out = io.StringIO()
    chosen = setup.run_setup(out, defaults=True)
    assert chosen["identity"] == "name" and chosen["book"].startswith("rs:")
    assert chosen["packs"] == ["core"] and len(chosen["catalogue_root"]) == 64
    assert "a demo" in out.getvalue() and "loop give apple 5" in out.getvalue()
    assert setup.setup_done() and not setup.first_start()
    run = Runner()
    assert "give     apple" in run.ok("give", "apple", "5")      # ready for offers
    assert "give     piano-lesson" in run.ok("give", "piano-lesson", "100")


def test_the_default_catalogue_is_the_same_everywhere(tmp_path):
    a = setup.build_catalogue(f"rs:{tmp_path / 'a'}")
    b = setup.build_catalogue(f"rs:{tmp_path / 'b'}")
    assert a == b


def test_with_a_node_and_its_batch_an_own_key_is_made_and_announced(fresh, monkeypatch, tmp_path):
    pytest.importorskip("coincurve", reason="a key needs the sig extra")
    monkeypatch.setenv("LOOP_REGISTRY", "memory:setup-test")
    monkeypatch.setattr(setup, "node_status", lambda api: fake_node())
    monkeypatch.setattr(setup, "xdai_balance", lambda address, rpc=None: KEY_ADDRESS_ENOUGH)
    monkeypatch.setattr(setup, "bee_config", lambda: None)
    out = io.StringIO()
    chosen = setup.run_setup(out, read=answers("3", small_store(tmp_path), "", "", ""))
    assert chosen["identity"] == "own" and chosen["postage"] == "existing"
    assert chosen["funded"] == "already" and chosen["announced"] is True
    assert chosen["book"] == f"swarm:loop-{chosen['address'][2:10].lower()}"
    cfg = open(os.path.join(fresh, "loop", "config")).read()
    assert "bee_signer = 0x" in cfg and "maker" not in cfg
    record = json.load(open(os.path.join(fresh, "loop", "setup.json")))
    assert "bee_signer" not in json.dumps(record)                 # never a key in the record


def test_defaults_spend_nothing(fresh, monkeypatch, tmp_path):
    pytest.importorskip("coincurve", reason="a key needs the sig extra")
    spent = []
    monkeypatch.setattr(setup, "node_status", lambda api: fake_node(batches=[]))
    monkeypatch.setattr(setup, "xdai_balance", lambda address, rpc=None: 0)
    monkeypatch.setattr(setup, "withdraw_xdai", lambda *a: spent.append("xdai"))
    monkeypatch.setattr(setup, "_postage", lambda d, node, chosen: (
        d.say("4. Postage: ..."), d.yes("   Buy it now with the node's wallet?", False)
        and spent.append("batch"), chosen.update(postage="none")))
    monkeypatch.setenv("LOOP_REGISTRY", "memory:setup-test-2")
    monkeypatch.setattr(setup, "DEFAULT_PACKS", ())                # a fast catalogue
    chosen = setup.run_setup(io.StringIO(), defaults=True)
    assert spent == [] and chosen["funded"] == "no" and chosen["announced"] is False


def test_funding_from_the_node_adds_the_key_to_beess_whitelist_when_asked(fresh, monkeypatch, tmp_path):
    pytest.importorskip("coincurve", reason="a key needs the sig extra")
    config = tmp_path / "config.yaml"
    config.write_text("api-addr: 127.0.0.1:1633\nwithdrawal-addresses-whitelist: []\npassword: x\n")
    listed, balance = [], {"wei": 0}

    def withdraw(api, address, wei):
        if address not in config.read_text():
            raise ValueError("provided address not whitelisted")
        listed.append(address)
        balance["wei"] = wei
        return "0xtx"
    monkeypatch.setenv("LOOP_REGISTRY", "memory:setup-test-3")
    monkeypatch.setattr(setup, "node_status", lambda api: fake_node())
    monkeypatch.setattr(setup, "xdai_balance", lambda address, rpc=None: balance["wei"])
    monkeypatch.setattr(setup, "withdraw_xdai", withdraw)
    monkeypatch.setattr(setup, "bee_config", lambda: str(config))
    # store, its path, identity (own), book (swarm), pay from node, add to the list,
    # Enter after the restart, announce
    out = io.StringIO()
    chosen = setup.run_setup(out, read=answers("3", small_store(tmp_path), "1", "", "y", "y", "", ""))
    assert listed == [chosen["address"]] and chosen["funded"] == "node"
    assert f"withdrawal-addresses-whitelist: [{chosen['address']}]" in config.read_text()
    assert any(p.name.startswith("config.yaml.before-loop-") for p in tmp_path.iterdir())
    assert chosen["announced"] is True


@pytest.mark.parametrize("line, after", [
    ("withdrawal-addresses-whitelist: []", "withdrawal-addresses-whitelist: [0xA]"),
    ("withdrawal-addresses-whitelist:", "withdrawal-addresses-whitelist: [0xA]"),
    ("withdrawal-addresses-whitelist: [0xB]", "withdrawal-addresses-whitelist: [0xB, 0xA]"),
])
def test_the_whitelist_line_takes_the_address_in_each_shape(tmp_path, line, after):
    path = tmp_path / "config.yaml"
    path.write_text(f"password: x\n{line}\ndata-dir: /d\n")
    setup.whitelist_address(str(path), "0xA")
    assert after in path.read_text().splitlines()
    assert "password: x" in path.read_text() and "data-dir: /d" in path.read_text()


def test_a_block_list_and_a_missing_key_take_it_too(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text("withdrawal-addresses-whitelist:\n  - 0xB\npassword: x\n")
    setup.whitelist_address(str(path), "0xA")
    assert path.read_text().splitlines()[:3] == ["withdrawal-addresses-whitelist:", "  - 0xA", "  - 0xB"]
    path = tmp_path / "b.yaml"
    path.write_text("password: x\n")
    setup.whitelist_address(str(path), "0xA")
    assert "withdrawal-addresses-whitelist: [0xA]" in path.read_text()


def test_the_nodes_key_is_read_from_its_key_file_with_its_password(tmp_path):
    eth_account = pytest.importorskip("eth_account", reason="the chain extra")
    acct = eth_account.Account.create()
    (tmp_path / "data" / "keys").mkdir(parents=True)
    (tmp_path / "data" / "keys" / "swarm.key").write_text(
        json.dumps(eth_account.Account.encrypt(acct.key, "s3cret")))
    config = tmp_path / "config.yaml"
    config.write_text(f"data-dir: {tmp_path / 'data'}\npassword: s3cret\n")
    assert setup.node_key(str(config), acct.address) == "0x" + bytes(acct.key).hex()
    with pytest.raises(ValueError, match="not the key of"):
        setup.node_key(str(config), "0x" + "00" * 20)
