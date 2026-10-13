// node browser/test/test_announce.mjs browser/test/announce_vector.json
// Checks announce.js against eth_account: the call data for
// announce(book, role) and the signed EIP-1559 transaction, byte for byte.
import { readFileSync } from "node:fs";
import { encodeAnnounce, signedTransaction } from "../announce.js";
import { Key } from "../publish.js";
import { hex } from "../swarm.js";

let failures = 0;
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failures++; };

const v = JSON.parse(readFileSync(process.argv[2], "utf8"));
const key = Key.fromText(v.key);
const data = encodeAnnounce(v.book, v.role);
check(`0x${hex(data)}` === v.data.toLowerCase(), "the call data, as web3 encodes announce(string,uint8)");
const signed = signedTransaction({ ...v.tx, data }, key);
check(signed.raw === v.raw, "the signed transaction, byte for byte eth_account's");
check(signed.hash === v.hash, "its hash");
if (failures) { console.log(`${failures} failed`); process.exit(1); }
console.log("all passed");
