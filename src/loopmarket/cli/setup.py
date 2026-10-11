"""`loop setup`: the first start (`docs/plans/cli.md` §16; questions 34
and 35, decided by Peter 2026-10-11).

One dialog, every step with a default and a line of explanation: the
ontology offers are written against; the identity (loop's own key by
default, the Bee node's key as an option, a plain name without a node);
where offers live (a Swarm book when a Bee node answers, a book on this
machine otherwise: the demo); and, with a node, whether setup may use the
node's wallet: a postage batch for the book, and the few cents of xDAI
loop's own key needs to announce it. Nothing is spent without a yes, and
`loop setup --defaults` takes every default and spends nothing.

The settings land in loop's config file, as `loop set` writes them; a
small record of what setup chose (never a key) marks setup as done, so
the first `loop` command at a terminal asks for it only once.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .settings import DEFAULT_REGISTRY, _configured, _home_dir, _read_config, _registry, _write_config

GUIDE = "https://github.com/petfold/loopmarket/blob/main/docs/USER-GUIDE.md"
#: The packs the default catalogue holds over ontodag's prelude: `core`,
#: ontodag's ~5,000 everyday categories. Built the same on every machine,
#: so every user who keeps the default pins one catalogue root.
DEFAULT_PACKS = ("core",)
#: ontodag's domain packs, built over core like it (ontodag-core).
DOMAIN_PACKS = ("physics", "mathematics", "chemistry", "biology", "medicine", "ai",
                "economics", "computing", "geography", "space")
#: What setup asks the node to pay loop's own key: enough xDAI for
#: thousands of announcements at Gnosis's gas prices.
FUND_WEI = 10 ** 16                     # 0.01 xDAI
#: Below this a key cannot be counted on to announce (a few transactions).
ENOUGH_WEI = 10 ** 14
#: The postage a new Swarm book is planned for: room and time.
BOOK_BYTES = 64 * 2 ** 20
BOOK_DAYS = 30
_RECORD = "setup.json"


def setup_done() -> bool:
    """Has setup run for this loop home?"""
    return os.path.exists(os.path.join(_home_dir(), _RECORD))


def first_start() -> bool:
    """A first start: neither setup's record nor a config file yet."""
    return not setup_done() and not os.path.exists(os.path.join(_home_dir(), "config"))


# ------------------------------------------------------------------ the dialog

class Dialog:
    """The questions, one at a time. `defaults` answers each with its
    default and refuses everything that spends; `read` is where answers
    come from (a terminal's `input`, or a test's list)."""

    def __init__(self, out, *, defaults: bool = False, read=None):
        self.out, self.defaults = out, defaults
        self._read = read or input

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def _answer(self, prompt: str) -> str:
        self.out.flush()
        return self._read(prompt).strip()

    def choose(self, title: str, options: list[tuple[str, str]], default: str) -> str:
        """`options` are (key, line) pairs; the answer is a key, or its
        number, or empty for the default."""
        self.say(title)
        for n, (key, line) in enumerate(options, 1):
            mark = " (default)" if key == default else ""
            self.say(f"  {n}. {line}{mark}")
        if self.defaults:
            return default
        keys = [k for k, _ in options]
        while True:
            got = self._answer(f"Choose 1-{len(options)} [{keys.index(default) + 1}]: ")
            if not got:
                return default
            if got.isdigit() and 1 <= int(got) <= len(options):
                return keys[int(got) - 1]
            if got in keys:
                return got
            self.say(f"  answer with a number from 1 to {len(options)}")

    def ask(self, prompt: str, default: str) -> str:
        if self.defaults:
            self.say(f"{prompt}: {default}")
            return default
        return self._answer(f"{prompt} [{default}]: ") or default

    def yes(self, prompt: str, default: bool) -> bool:
        """A yes/no question. Under `--defaults` the answer is no whenever
        a yes would spend; the callers ask those with default=False."""
        if self.defaults:
            self.say(f"{prompt} {'yes' if default else 'no'}")
            return default
        got = self._answer(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").lower()
        return default if not got else got in ("y", "yes")


# ------------------------------------------------------------- the Bee node

def _http(method: str, url: str, timeout: float = 5.0):
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def _get(api: str, path: str):
    try:
        return _http("GET", api.rstrip("/") + path)
    except (OSError, ValueError):
        return None


def node_status(api: str) -> dict | None:
    """What setup needs to know about the Bee node at `api`, or None when
    none answers: its mode, its own address, its wallet and its usable
    postage batches."""
    if _get(api, "/health") is None:
        return None
    node = _get(api, "/node") or {}
    addresses = _get(api, "/addresses") or {}
    wallet = _get(api, "/wallet") or {}
    stamps = (_get(api, "/stamps") or {}).get("stamps", [])
    return {"api": api, "mode": node.get("beeMode", "?"),
            "address": addresses.get("ethereum", ""),
            "xdai_wei": int(wallet.get("nativeTokenBalance") or 0),
            "bzz_plur": int(wallet.get("bzzBalance") or 0),
            "batches": [s for s in stamps if s.get("usable")]}


def withdraw_xdai(api: str, address: str, wei: int) -> str:
    """Ask the node to pay `wei` of xDAI to `address`; the transaction
    hash, or ValueError with the node's reason (Bee pays out only to
    addresses its config whitelists)."""
    url = f"{api.rstrip('/')}/wallet/withdraw/NativeToken?amount={wei}&address={address}"
    try:
        return _http("POST", url, timeout=60).get("transactionHash", "")
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read()).get("message", str(exc))
        except ValueError:
            reason = str(exc)
        raise ValueError(reason) from None


#: Where node installers keep Bee's config (with its password, data
#: directory and withdrawal whitelist): Swarm Desktop's, then a packaged
#: bee's.
BEE_CONFIGS = ("~/.local/share/Swarm Desktop/config.yaml",
               "~/Library/Application Support/Swarm Desktop/config.yaml",
               "/etc/bee/bee.yaml")


def bee_config() -> str | None:
    for path in BEE_CONFIGS:
        path = os.path.expanduser(path)
        if os.path.exists(path):
            return path
    return None


def _yaml_value(path: str, key: str) -> str:
    """A top-level `key: value` of a flat YAML file such as Bee's config,
    unquoted; '' when absent. (Bee's config is flat; no YAML library.)"""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(f"{key}:"):
                return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def whitelist_address(path: str, address: str) -> str:
    """Add `address` to the `withdrawal-addresses-whitelist` of Bee's
    config at `path`, keeping a dated copy of the file first; returns the
    copy's path. Bee reads it at its next start."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    key = "withdrawal-addresses-whitelist:"
    copy = f"{path}.before-loop-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    with open(copy, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    for i, line in enumerate(lines):
        if line.startswith(key):
            value = line[len(key):].strip()
            if value in ("", "[]", "null", "~"):
                if value == "" and i + 1 < len(lines) and lines[i + 1].lstrip().startswith("- "):
                    lines.insert(i + 1, f"  - {address}")     # a block list follows
                else:
                    lines[i] = f"{key} [{address}]"
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                lines[i] = f"{key} [{inner + ', ' if inner else ''}{address}]"
            else:
                lines[i] = f"{key} [{value}, {address}]"
            break
    else:
        lines.append(f"{key} [{address}]")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return copy


def node_key(config_path: str, node_address: str) -> str:
    """The Bee node's private key, decrypted from its key file with the
    password its config holds; it must be the key of `node_address`.
    Needs the `chain` extra (eth-account)."""
    from .._extras import MissingExtra
    try:
        from eth_account import Account
    except ImportError as exc:
        raise MissingExtra("reading the node's key needs eth-account: "
                           "pip install 'loopmarket[chain]'") from exc
    data_dir = os.path.expanduser(_yaml_value(config_path, "data-dir") or "~/.bee")
    password = _yaml_value(config_path, "password")
    key_file = os.path.join(data_dir, "keys", "swarm.key")
    with open(key_file, encoding="utf-8") as fh:
        keystore = json.load(fh)
    key = "0x" + bytes(Account.decrypt(keystore, password)).hex()
    if Account.from_key(key).address.lower() != node_address.lower():
        raise ValueError(f"{key_file} is not the key of the node's address {node_address}")
    return key


# ---------------------------------------------------------------- the chain

def xdai_balance(address: str, rpc: str | None = None) -> int:
    """`address`'s xDAI on Gnosis, in wei, through the registry's RPC."""
    if rpc is None:
        spec = _registry() or DEFAULT_REGISTRY
        rpc = spec[len("chain:"):].rsplit("@", 1)[0] if spec.startswith("chain:") \
            else DEFAULT_REGISTRY[len("chain:"):].rsplit("@", 1)[0]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance",
                       "params": [address, "latest"]}).encode()
    req = urllib.request.Request(rpc, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return int(json.load(resp)["result"], 16)


def _xdai(wei: int) -> str:
    return f"{wei / 1e18:.4f} xDAI"


# ------------------------------------------------------------- the catalogue

def build_catalogue(spec: str, packs=DEFAULT_PACKS) -> str:
    """Build the default catalogue at `spec` (an `rs:` store): ontodag's
    prelude, `packs`, and the markers loop's matching reads (`handover` on
    `geo` and `time`, the route roles `from`/`to` and `depart`/`arrive`).
    The same on every machine, so the root is too; returns it. Operators,
    options and item heads are left out: their names (`transport`,
    `storage`, `option`, `item`) are everyday words in `core`."""
    import ontodag
    from ontodag import packs as ontodag_packs
    from ontodag import prelude

    from ..ontology import Ontology

    store = ontodag.open(spec)
    dag = store.dag
    prelude.apply(dag)
    for name in packs:
        ontodag_packs.apply(dag, name)
    ont = Ontology(dag)
    ont.declare_handover(["geo", "time"])
    ont.declare_roles({"from": "geo", "to": "geo", "depart": "time", "arrive": "time"})
    store.save()
    return Ontology(store.dag).root


# ------------------------------------------------------------------- setup

def run_setup(out, *, defaults: bool = False, read=None) -> dict:
    """The dialog; returns what it chose (never a key)."""
    d = Dialog(out, defaults=defaults, read=read)
    home = _home_dir()
    os.makedirs(home, exist_ok=True)
    cfg = _read_config()
    chosen: dict = {}

    d.say("loop: the setup. Each question has a default; Enter takes it.")
    d.say(f"The User Guide explains everything below: {GUIDE}")
    d.say()

    api = _configured("bee_api")
    node = node_status(api)
    if node:
        d.say(f"A Swarm (Bee) node answers at {api}: a {node['mode']} node, "
              f"wallet {node['address']}, {_xdai(node['xdai_wei'])} and "
              f"{node['bzz_plur'] / 1e16:.4f} xBZZ.")
    else:
        d.say(f"No Swarm (Bee) node answers at {api}: your offers stay on this "
              f"machine (a demo) until you add one and run `loop setup` again.")
    d.say()

    # 1. the ontology
    ontology = d.choose(
        "1. The ontology: the categories offers are written in. Two people's "
        "offers can match only when they use the same one.",
        [("core", "ontodag's core: about 5,000 everyday categories (apple, "
                  "piano-lesson, toaster...), the same for everyone who keeps it"),
         ("packs", "core with some of ontodag's domain packs (physics, medicine, "
                   "computing...)"),
         ("store", "an ontology store you already have (a path, rs:PATH or swarm:NAME)")],
        "core")
    if ontology == "store":
        spec = d.ask("The store", cfg.get("catalogue") or "~/.ontodag/store.od")
    else:
        packs = list(DEFAULT_PACKS)
        if ontology == "packs":
            extra = d.ask(f"Which packs, comma-separated ({', '.join(DOMAIN_PACKS)})", "")
            packs += [p.strip() for p in extra.split(",") if p.strip() in DOMAIN_PACKS]
        spec = f"rs:{os.path.join(home, 'catalogue')}"
        d.say(f"  building it at {spec} (a minute the first time)...")
        root = build_catalogue(spec, packs)
        chosen["catalogue_root"] = root
        chosen["packs"] = packs
        d.say(f"  done: root {root[:16]}...")
    cfg["catalogue"] = spec
    chosen["catalogue"] = spec
    d.say()

    # 2. the identity
    key = None
    if node:
        default_id = "own"
        options = [("own", "a key of loop's own: your identity on the market, "
                           "separate from the node (you back it up)")]
        if bee_config():
            options.append(("node", f"your node's key ({node['address']}): one wallet, "
                                    f"already funded; loop then holds the node's key"))
        identity = d.choose("2. Your identity: the key your offers are signed with and "
                            "your book is owned by.", options, default_id)
        if identity == "node":
            key = node_key(bee_config(), node["address"])
        else:
            key = cfg.get("bee_signer") or "0x" + secrets.token_hex(32)
        from ..sigs import maker_address
        address = maker_address(key)
        cfg["bee_signer"] = key
        cfg.pop("maker", None)
        chosen["identity"] = identity
        chosen["address"] = address
        d.say(f"  your address: {address}")
        if identity == "own":
            d.say(f"  the key is in {os.path.join(home, 'config')}: back that file up; "
                  f"whoever holds it can act as you")
    else:
        name = d.ask("2. A name for your offers (a demo without a node needs no key)",
                     cfg.get("maker") or os.environ.get("USER", "me"))
        cfg["maker"] = name
        chosen["identity"] = "name"
        address = None
    d.say()

    # 3. where offers live
    if node:
        book = d.choose("3. Where your offers live.",
                        [("swarm", f"a book on Swarm, swarm:loop-{address[2:10].lower()}: "
                                   f"others can read it once it is announced"),
                         ("local", "a book on this machine only (a demo)")], "swarm")
        cfg["book"] = f"swarm:loop-{address[2:10].lower()}" if book == "swarm" \
            else f"rs:{os.path.join(home, 'book')}"
    else:
        cfg["book"] = f"rs:{os.path.join(home, 'book')}"
    chosen["book"] = cfg["book"]
    d.say(f"  your book: {cfg['book']}")
    d.say()

    _write_config(cfg)

    # 4. the node's wallet
    if node and cfg["book"].startswith("swarm:"):
        _postage(d, node, chosen)
        if chosen.get("identity") == "own":
            _fund(d, node, address, chosen)
        _announce(d, cfg, address, chosen)

    chosen["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(os.path.join(home, _RECORD), "w", encoding="utf-8") as fh:
        json.dump(chosen, fh, indent=1, sort_keys=True)
    d.say("Setup is done. Try:  loop give apple 5")
    d.say("`loop categories` shows the words offers are written in, `loop help` the rest.")
    return chosen


def _postage(d: Dialog, node: dict, chosen: dict) -> None:
    if node["batches"]:
        b = max(node["batches"], key=lambda s: s.get("batchTTL", 0))
        d.say(f"4. Postage: your node has a usable batch ({b['batchID'][:8]}..., "
              f"{b.get('batchTTL', 0) // 86400} days left); your book uses it.")
        chosen["postage"] = "existing"
        return
    from swarmfs._client import SwarmClient
    from swarmfs.stamps import StampManager
    import asyncio

    async def plan():
        client = SwarmClient(node["api"])
        try:
            return await StampManager(client).plan(BOOK_BYTES, BOOK_DAYS * 86400)
        finally:
            await client.close()
    p = asyncio.run(plan())
    d.say(f"4. Postage: storing your book on Swarm needs a postage batch, and your "
          f"node has none. One for {BOOK_BYTES // 2 ** 20} MB for {BOOK_DAYS} days costs "
          f"{p.cost_bzz:.4f} xBZZ from the node's wallet.")
    if not d.yes("   Buy it now with the node's wallet?", False):
        d.say("   not bought: buy one later in your node's app, and run `loop setup` again")
        chosen["postage"] = "none"
        return

    async def buy():
        client = SwarmClient(node["api"])
        try:
            return await StampManager(client).buy(p.amount, p.depth)
        finally:
            await client.close()
    d.say("   buying (about a minute until the network accepts it)...")
    batch = asyncio.run(buy())
    d.say(f"   bought: batch {batch[:8]}...")
    chosen["postage"] = "bought"


def _fund(d: Dialog, node: dict, address: str, chosen: dict) -> None:
    balance = xdai_balance(address)
    if balance >= ENOUGH_WEI:
        d.say(f"5. Your key holds {_xdai(balance)}: enough to announce your book.")
        chosen["funded"] = "already"
        return
    d.say(f"5. Announcing your book is a small transaction from your key, which holds "
          f"{_xdai(balance)}. {_xdai(FUND_WEI)} covers thousands of them.")
    if node["xdai_wei"] > FUND_WEI and d.yes(
            f"   Pay {_xdai(FUND_WEI)} from your node's wallet to {address}?", False):
        for attempt in (1, 2):
            try:
                tx = withdraw_xdai(node["api"], address, FUND_WEI)
                d.say(f"   paid: transaction {tx}")
                chosen["funded"] = "node"
                _await_balance(address)
                return
            except ValueError as exc:
                if "whitelist" not in str(exc) or attempt == 2:
                    d.say(f"   the node refused: {exc}")
                    break
                path = bee_config()
                d.say("   your node pays out only to addresses its config lists, and "
                      "this one is not listed.")
                if not path or not d.yes(f"   Add {address} to the list in {path}? "
                                         f"(a copy of the file is kept)", False):
                    break
                copy = whitelist_address(path, address)
                d.say(f"   added (the old file is {copy}). Restart your node now (in "
                      f"Swarm Desktop: quit and open it again).")
                d.ask("   Press Enter when it is running again", "")
                if node_status(node["api"]) is None:
                    d.say("   the node does not answer yet")
                    break
    d.say(f"   to fund it yourself, send {_xdai(FUND_WEI)} on Gnosis to {address}, "
          f"then run `loop announce`")
    chosen.setdefault("funded", "no")


def _await_balance(address: str, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if xdai_balance(address) >= ENOUGH_WEI:
            return
        time.sleep(3)


def _announce(d: Dialog, cfg: dict, address: str, chosen: dict) -> None:
    if not _registry():
        return
    if xdai_balance(address) < ENOUGH_WEI:
        d.say("6. Your book is announced once your key holds xDAI: `loop announce`.")
        chosen["announced"] = False
        return
    from ..announce import open_announcements
    standing = [a for a in open_announcements(_registry()).announced()
                if a.owner.lower() == address.lower() and a.book == cfg["book"]]
    if standing:
        d.say("6. Your book is already announced on the registry.")
        chosen["announced"] = True
        return
    if not d.yes("6. Announce your book on the registry now, so others find it?", True):
        chosen["announced"] = False
        return
    open_announcements(_registry(), key=cfg["bee_signer"]).announce(cfg["book"], "maker", owner=address)
    d.say(f"   announced: {cfg['book']}")
    chosen["announced"] = True


def cmd_setup(args, session, out):
    """`loop setup [--defaults]`: the first start's dialog, run again any
    time to change the answers."""
    run_setup(out, defaults=getattr(args, "defaults", False))
    return 0
