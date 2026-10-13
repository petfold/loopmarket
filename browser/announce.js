// Announcing a book on the LoopBookRegistry from the page (BROWSER.md §5c):
// the transaction `loop announce` sends (announce.py, web3's
// build_transaction and sign_transaction), built and signed here with the
// maker's key. It is an EIP-1559 transaction on Gnosis (chain 100) calling
// announce(string book, uint8 role), paid in xDAI from the key's address.
//
// encodeAnnounce and signedTransaction are pure, and pinned by
// test/announce_vector.json, which eth_account signed; send() talks to a
// Gnosis RPC.

import { keccak_256 } from "./vendor/noble-hashes/sha3.js";
import { hex, unhex } from "./swarm.js";

export const CHAIN_ID = 100;
export const ROLE = { maker: 0, clearing: 1, register: 2 };

const utf8 = new TextEncoder();

function concat(parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

// A non-negative integer as minimal big-endian bytes (0 is empty).
function intBytes(n) {
  let v = BigInt(n);
  if (v < 0n) throw new Error("a negative number in a transaction");
  const out = [];
  while (v > 0n) { out.unshift(Number(v & 0xffn)); v >>= 8n; }
  return Uint8Array.from(out);
}

// Recursive-length prefix: bytes, or arrays of them.
export function rlp(item) {
  if (Array.isArray(item)) {
    const body = concat(item.map(rlp));
    return concat([lengthPrefix(body.length, 0xc0), body]);
  }
  const b = item instanceof Uint8Array ? item : intBytes(item);
  if (b.length === 1 && b[0] < 0x80) return b;
  return concat([lengthPrefix(b.length, 0x80), b]);
}

function lengthPrefix(length, offset) {
  if (length < 56) return Uint8Array.of(offset + length);
  const l = intBytes(length);
  return concat([Uint8Array.of(offset + 55 + l.length), l]);
}

function word(n) {
  const b = intBytes(n);
  const out = new Uint8Array(32);
  out.set(b, 32 - b.length);
  return out;
}

// The call data for announce(string book, uint8 role).
export function encodeAnnounce(book, role) {
  const selector = keccak_256(utf8.encode("announce(string,uint8)")).subarray(0, 4);
  const text = utf8.encode(book);
  const padded = new Uint8Array(Math.ceil(text.length / 32) * 32);
  padded.set(text);
  return concat([selector, word(64), word(role), word(text.length), padded]);
}

// The raw signed transaction (type 2) and its hash. `tx` has nonce, gas,
// maxFeePerGas, maxPriorityFeePerGas, to, value and data; `key` is
// publish.js's Key.
export function signedTransaction(tx, key) {
  const fields = [
    BigInt(tx.chainId ?? CHAIN_ID), BigInt(tx.nonce), BigInt(tx.maxPriorityFeePerGas),
    BigInt(tx.maxFeePerGas), BigInt(tx.gas), unhex(tx.to.replace(/^0x/, "")),
    BigInt(tx.value ?? 0), tx.data, [],
  ];
  const digest = keccak_256(concat([Uint8Array.of(2), rlp(fields)]));
  const sig = key.signHash(digest);                 // r || s || v, v 0 or 1
  const big = (b) => BigInt(`0x${hex(b) || "0"}`);
  const raw = concat([Uint8Array.of(2), rlp([...fields, BigInt(sig[64]), big(sig.subarray(0, 32)), big(sig.subarray(32, 64))])]);
  return { raw: `0x${hex(raw)}`, hash: `0x${hex(keccak_256(raw))}` };
}

async function rpcCall(rpc, method, params) {
  const res = await fetch(rpc, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const body = await res.json();
  if (body.error) throw new Error(`${method}: ${body.error.message}`);
  return body.result;
}

// What announcing would cost, and whether the key can pay: {fee, balance}
// in wei, and the transaction to send.
export async function prepareAnnounce(rpc, contract, key, book, role = ROLE.maker) {
  const from = key.checksummed;
  const data = encodeAnnounce(book, role);
  const [nonce, gas, tip, block, balance] = await Promise.all([
    rpcCall(rpc, "eth_getTransactionCount", [from, "pending"]),
    rpcCall(rpc, "eth_estimateGas", [{ from, to: contract, data: `0x${hex(data)}` }]),
    rpcCall(rpc, "eth_maxPriorityFeePerGas", []).catch(() => "0x3b9aca00"),
    rpcCall(rpc, "eth_getBlockByNumber", ["latest", false]),
    rpcCall(rpc, "eth_getBalance", [from, "latest"]),
  ]);
  const base = BigInt(block.baseFeePerGas || "0x0");
  const maxPriorityFeePerGas = BigInt(tip);
  const maxFeePerGas = 2n * base + maxPriorityFeePerGas;
  const gasLimit = (BigInt(gas) * 12n) / 10n;          // a margin, as web3's estimate leaves none
  const tx = { chainId: CHAIN_ID, nonce: BigInt(nonce), gas: gasLimit, maxFeePerGas, maxPriorityFeePerGas, to: contract, value: 0n, data };
  return { tx, fee: gasLimit * maxFeePerGas, balance: BigInt(balance) };
}

// Send it and wait for its receipt (up to `minutes`).
export async function send(rpc, tx, key, { minutes = 3 } = {}) {
  const { raw, hash } = signedTransaction(tx, key);
  const sent = await rpcCall(rpc, "eth_sendRawTransaction", [raw]);
  if (sent && sent.toLowerCase() !== hash) throw new Error(`the RPC took it as ${sent}, not ${hash}`);
  const deadline = Date.now() + minutes * 60_000;
  while (Date.now() < deadline) {
    const receipt = await rpcCall(rpc, "eth_getTransactionReceipt", [hash]);
    if (receipt) {
      if (receipt.status !== "0x1") throw new Error(`the announcement failed on chain (transaction ${hash})`);
      return { hash, block: parseInt(receipt.blockNumber, 16) };
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(`no receipt yet for ${hash}; it may still be mined`);
}
