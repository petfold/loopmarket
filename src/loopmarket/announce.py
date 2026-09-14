"""The announcement channel: how a book becomes discoverable.

A book is a Swarm feed named by (owner, topic), and knowing that pair is
the whole of discovery. Until 2026-09-14 the plan carried two channels —
GSOC, a Swarm-native single-owner chunk mined into an aggregator's
neighbourhood, and a registry event on Gnosis Chain as its permanent
fallback. Peter dropped GSOC: an announcement is per *book*, not per
offer (a maker says "my book is here" a handful of times, ever), so there
is no volume to optimise; the chain is what a censored announcement would
be detected against, so the chain is the channel; and GSOC's receivers
needed a full Bee node each, with fan-out growing with the number of
aggregators — the wrong shape for "several aggregators minimum". A
sub-cent transaction that anyone can read forever is strictly better on
every property the design cares about (`P1-federated-book.md` §4).

The channel is a log of `Announcement`s, latest per owner, with
retractions. Three backends behind one protocol, chosen by spec the way
books are (`rs:` / `swarm:`):

- `chain:RPC_URL@CONTRACT` — the `LoopBookRegistry` contract
  (`contracts/LoopBookRegistry.sol`) on Gnosis Chain or any EVM chain,
  read with `eth_getLogs`, written by the maker's own transaction so
  `msg.sender` is the owner. Needs the `chain` extra (web3); imported
  lazily inside this path, never at module import (boundary B2).
- `file:PATH` — a JSON-lines log on disk: several sessions on one
  machine discover each other's `rs:` books without a chain, the dev
  stand-in `rs:` is for Swarm.
- `memory:[NAME]` — in-process, for tests and demos.

An announcement names a *book spec without its owner* (`swarm:TOPIC`,
or `rs:PATH` on the file backend); a reader opens it as `swarm:TOPIC@OWNER`
— the owner comes from the channel, never from the book, which is what
makes U8's admission by feed owner real: the aggregator folds each book
as *that* owner's and refuses speech the owner may not make.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Iterable, Protocol

MAKER = "maker"
CLEARING = "clearing"
_ROLES = (MAKER, CLEARING)


@dataclass(frozen=True, slots=True)
class Announcement:
    """`owner`'s book is `book` (a spec without its owner), in `role`;
    `seq` orders announcements (block number and log index on chain, a
    counter elsewhere) so the latest per owner is well defined."""

    owner: str
    book: str
    role: str = MAKER
    seq: int = 0

    def spec(self) -> str:
        """The spec a reader opens: the owner appended for a Swarm feed,
        the path as it is for a local book."""
        return f"{self.book}@{self.owner}" if self.book.startswith("swarm:") \
            else self.book


class Announcements(Protocol):
    def announced(self) -> list[Announcement]:
        """The standing announcements, latest per owner, retractions
        applied, sorted by owner."""

    def announce(self, book: str, role: str = MAKER, *,
                 owner: str | None = None) -> Announcement: ...

    def retract(self, *, owner: str | None = None) -> None: ...


def _latest(events: Iterable[tuple[int, str, Announcement | None]]) -> list[Announcement]:
    """Fold a (seq, owner, announcement-or-None) log into the standing set."""
    standing: dict[str, Announcement | None] = {}
    for _seq, owner, ann in sorted(events, key=lambda e: e[0]):
        standing[owner] = ann
    return [ann for _owner, ann in sorted(standing.items()) if ann is not None]


class MemoryAnnouncements:
    """An in-process log; with `path`, a JSON-lines file shared by every
    session that names it (the `file:` backend)."""

    def __init__(self, path: str | None = None):
        self._path = path
        self._events: list[tuple[int, str, Announcement | None]] = []
        self._lock = threading.Lock()
        if path and os.path.exists(path):
            self._load()

    def _load(self) -> None:
        self._events = []
        with open(self._path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                ann = None if rec.get("retract") else Announcement(
                    rec["owner"], rec["book"], rec.get("role", MAKER), rec["seq"])
                self._events.append((rec["seq"], rec["owner"], ann))

    def _append(self, rec: dict) -> None:
        if self._path:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def announced(self) -> list[Announcement]:
        with self._lock:
            if self._path and os.path.exists(self._path):
                self._load()
            return _latest(self._events)

    def announce(self, book: str, role: str = MAKER, *,
                 owner: str | None = None) -> Announcement:
        if role not in _ROLES:
            raise ValueError(f"unknown book role: {role!r}")
        if not owner:
            raise ValueError("an announcement needs its owner")
        with self._lock:
            if self._path and os.path.exists(self._path):
                self._load()
            seq = len(self._events)
            ann = Announcement(owner, book, role, seq)
            self._events.append((seq, owner, ann))
            self._append({"seq": seq, "owner": owner, "book": book, "role": role})
            return ann

    def retract(self, *, owner: str | None = None) -> None:
        if not owner:
            raise ValueError("a retraction needs its owner")
        with self._lock:
            if self._path and os.path.exists(self._path):
                self._load()
            seq = len(self._events)
            self._events.append((seq, owner, None))
            self._append({"seq": seq, "owner": owner, "retract": True})


#: The contract's ABI — the two events readers decode and the two calls a
#: maker sends. Kept beside the Solidity source so a reader needs no
#: compiler; `scripts/deploy_registry.py` compiles and deploys.
ABI = [
    {"type": "event", "name": "Announce", "anonymous": False, "inputs": [
        {"name": "owner", "type": "address", "indexed": True},
        {"name": "book", "type": "string", "indexed": False},
        {"name": "role", "type": "uint8", "indexed": False}]},
    {"type": "event", "name": "Retract", "anonymous": False, "inputs": [
        {"name": "owner", "type": "address", "indexed": True}]},
    {"type": "function", "name": "announce", "stateMutability": "nonpayable",
     "inputs": [{"name": "book", "type": "string"}, {"name": "role", "type": "uint8"}],
     "outputs": []},
    {"type": "function", "name": "retract", "stateMutability": "nonpayable",
     "inputs": [], "outputs": []},
]


class ChainAnnouncements:
    """`LoopBookRegistry` on an EVM chain: the announced set is the event
    log, `msg.sender` is the owner, a transaction is the speech act.

    `web3` (the `chain` extra) is imported lazily inside each call, so the
    core stays offline-clean (B1/B2). `key` is the maker's secp256k1 key —
    the one that signs their Swarm feed — needed only to announce or
    retract; reading needs nothing but an RPC endpoint. `client` may be
    given directly (anything with web3's `eth` face) for tests and for
    embedders that already hold one.
    """

    def __init__(self, rpc_url: str, contract: str, *, key: str | None = None,
                 from_block: int = 0, client=None):
        self.rpc_url, self.contract_address = rpc_url, contract
        self._key, self._from_block, self._client = key, from_block, client

    def _web3(self):
        if self._client is None:
            try:
                from web3 import Web3
            except ImportError as exc:
                raise RuntimeError(
                    "the chain announcement channel needs web3: "
                    "pip install 'loopmarket[chain]'") from exc
            self._client = Web3(Web3.HTTPProvider(self.rpc_url))
        return self._client

    def _contract(self):
        return self._web3().eth.contract(address=self.contract_address, abi=ABI)

    @staticmethod
    def _seq(log) -> int:
        return log["blockNumber"] * 1_000_000 + log["logIndex"]

    def announced(self) -> list[Announcement]:
        contract = self._contract()
        events = []
        for log in contract.events.Announce.get_logs(from_block=self._from_block):
            owner = log["args"]["owner"]
            role = CLEARING if log["args"]["role"] == 1 else MAKER
            events.append((self._seq(log), owner,
                           Announcement(owner, log["args"]["book"], role, self._seq(log))))
        for log in contract.events.Retract.get_logs(from_block=self._from_block):
            events.append((self._seq(log), log["args"]["owner"], None))
        return _latest(events)

    def _send(self, fn):
        w3 = self._web3()
        account = w3.eth.account.from_key(self._key)
        tx = fn.build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
        })
        signed = account.sign_transaction(tx)
        receipt = w3.eth.wait_for_transaction_receipt(
            w3.eth.send_raw_transaction(signed.raw_transaction))
        return account.address, receipt

    def announce(self, book: str, role: str = MAKER, *,
                 owner: str | None = None) -> Announcement:
        if role not in _ROLES:
            raise ValueError(f"unknown book role: {role!r}")
        if not self._key:
            raise ValueError("announcing needs the maker's key (bee_signer)")
        address, receipt = self._send(
            self._contract().functions.announce(book, 1 if role == CLEARING else 0))
        return Announcement(address, book, role, receipt["blockNumber"] * 1_000_000)

    def retract(self, *, owner: str | None = None) -> None:
        if not self._key:
            raise ValueError("retracting needs the maker's key (bee_signer)")
        self._send(self._contract().functions.retract())


_MEMORY: dict[str, MemoryAnnouncements] = {}


def open_announcements(spec: str, *, key: str | None = None) -> Announcements:
    """`chain:RPC_URL@CONTRACT`, `file:PATH`, or `memory:[NAME]` (one shared
    log per name in this process)."""
    if spec.startswith("chain:"):
        rpc, _, contract = spec[6:].rpartition("@")
        if not rpc or not contract:
            raise ValueError(f"{spec}: a chain registry is chain:RPC_URL@CONTRACT")
        return ChainAnnouncements(rpc, contract, key=key)
    if spec.startswith("file:"):
        return MemoryAnnouncements(os.path.abspath(os.path.expanduser(spec[5:])))
    if spec.startswith("memory:"):
        return _MEMORY.setdefault(spec[7:], MemoryAnnouncements())
    raise ValueError(
        f"{spec}: a registry is chain:RPC_URL@CONTRACT, file:PATH or memory:[NAME]")
