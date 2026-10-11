// The books announced on the LoopBookRegistry (Gnosis), read in the page:
// the contract's event log, the latest announcement per owner, retractions
// removing it (loopmarket's announce.py, ChainAnnouncements, does the same
// through web3). In Freedom Browser the log comes through the browser's own
// chain access (window.ethereum, which checks log answers against several
// RPCs); elsewhere from a public RPC, which allows any origin.

import { keccak_256 } from "./vendor/noble-hashes/sha3.js";
import { hex, unhex } from "./swarm.js";

const utf8 = new TextEncoder();
const topic0 = (signature) => "0x" + hex(keccak_256(utf8.encode(signature)));

export const ANNOUNCE = topic0("Announce(address,string,uint8)");
export const RETRACT = topic0("Retract(address)");
const ROLES = ["maker", "clearing", "register"];

// EIP-55: the mixed-case address loopmarket writes as an offer's maker; the
// fold compares a book's owner with its offers' makers as strings.
export function checksummed(address) {
  const lower = address.replace(/^0x/, "").toLowerCase();
  const digest = hex(keccak_256(utf8.encode(lower)));
  let out = "0x";
  for (let i = 0; i < 40; i++) {
    out += parseInt(digest[i], 16) >= 8 ? lower[i].toUpperCase() : lower[i];
  }
  return out;
}

async function getLogs({ rpc, contract, fromBlock }) {
  const filter = { address: contract, fromBlock: "0x" + fromBlock.toString(16), toBlock: "latest" };
  if (globalThis.ethereum && typeof globalThis.ethereum.request === "function") {
    try {
      // A wallet may hold a request for its user; a read waits 10 s at most.
      const logs = await Promise.race([
        globalThis.ethereum.request({ method: "eth_getLogs", params: [filter] }),
        new Promise((_, reject) => setTimeout(() => reject(new Error("no answer")), 10_000)),
      ]);
      if (Array.isArray(logs)) return { logs, via: "the browser's chain access (window.ethereum)" };
    } catch {
      // not offered to this page, or no answer: the public RPC below
    }
  }
  const res = await fetch(rpc, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getLogs", params: [filter] }),
  });
  const body = await res.json();
  if (body.error) throw new Error(`eth_getLogs: ${body.error.message}`);
  return { logs: body.result, via: rpc };
}

const word = (data, i) => data.slice(2 + 64 * i, 2 + 64 * (i + 1));
const ownerOf = (log) => checksummed("0x" + log.topics[1].slice(26));

function decodeAnnounce(log) {
  const data = log.data;
  const at = parseInt(word(data, 0), 16) / 32;          // where the string starts
  const role = parseInt(word(data, 1), 16);
  const length = parseInt(word(data, at), 16);
  const start = 2 + 64 * (at + 1);
  const book = new TextDecoder().decode(unhex(data.slice(start, start + 2 * length)));
  return { owner: ownerOf(log), book, role: ROLES[role] || "maker" };
}

const order = (a, b) => {
  const d = BigInt(a.blockNumber) - BigInt(b.blockNumber);
  if (d !== 0n) return d < 0n ? -1 : 1;
  const e = BigInt(a.logIndex) - BigInt(b.logIndex);
  return e < 0n ? -1 : e > 0n ? 1 : 0;
};

// The standing announcements: [{owner, book, role}], and where they came from.
export async function standing(registry) {
  const { logs, via } = await getLogs(registry);
  const latest = new Map();
  for (const log of logs.slice().sort(order)) {
    const kind = log.topics[0].toLowerCase();
    if (kind === ANNOUNCE) {
      const a = decodeAnnounce(log);
      latest.set(a.owner.toLowerCase(), a);
    } else if (kind === RETRACT) {
      latest.delete(ownerOf(log).toLowerCase());
    }
  }
  const announcements = [...latest.values()].sort((a, b) => (a.owner < b.owner ? -1 : 1));
  return { announcements, via, logs: logs.length };
}
