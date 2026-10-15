// loopmarket's read-only page: the books announced on Gnosis, folded with
// loopmarket's own code under Pyodide, their open offers listed. Swarm comes
// through swarm.js (ontodag's, copied in by build.py): Freedom Browser's
// window.swarm, or a node over HTTP. Python's synchronous store calls wait on
// those reads through JSPI, so every call into Python is a callPromising.

import { ChunkReader, BlobStore, FreedomSwarm, HttpSwarm, StoredChunks, hex, topicOf, unhex } from "./swarm.js";
import { standing } from "./registry.js";
import { LocalFile, download } from "./localfile.js";
import { PythonCalls } from "./pycall.js";
import { Key, NodeWriter, Stage, feedUpdate, uploadStaged } from "./publish.js";
import { secp256k1 } from "./vendor/noble-curves/secp256k1.js";
import { prepareAnnounce, send as sendTransaction } from "./announce.js";
import { keccak_256 } from "./vendor/noble-hashes/sha3.js";

// The LoopBookRegistry (loopmarket's DEFAULT_REGISTRY), deployed 2026-09-14.
const REGISTRY = {
  rpc: "https://rpc.gnosischain.com",
  contract: "0xD4379E494a488411D964BebDb210C0bf628d97af",
  fromBlock: 48249000,
};

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

// Pyodide 0.27.7 is published once, as its own folder on Swarm, and every
// page loads it from there: it is never stamped again with a page, and a
// browser caches it under one address for every page and version. Until its
// own folder is published, the copy inside the published ontodag page.
// ?pyodide=URL names another (the checks serve a local copy).
const PYODIDE = "e0f26cbbcf0985f518fc6ffcdcad9d6ff121b1a5bd10deea6be430e83be7926a/pyodide";

function pyodideBase() {
  const named = params.get("pyodide");
  if (named) return new URL(named.endsWith("/") ? named : `${named}/`, location.href).href;
  if (location.protocol === "bzz:") return `bzz://${PYODIDE}/`;
  if (location.pathname.startsWith("/bzz/")) return `${location.origin}/bzz/${PYODIDE}/`;
  return `${params.get("gateway") || "https://api.gateway.ethswarm.org"}/bzz/${PYODIDE}/`;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.append(s);
  });
}
let py, reader, folded = null;
let searchFile = null, searches = false, searchChanged = false;
const SEARCH_TYPES = [{ description: "loopmarket saved searches", accept: { "application/json": [".json"] } }];
let busy = false;

function status(text, warn = false) {
  $("status").textContent = text;
  $("status").classList.toggle("warn", warn);
}

function chooseSource() {
  if (FreedomSwarm.present()) return new FreedomSwarm();
  const named = params.get("gateway");
  if (named) return new HttpSwarm(named);
  if (location.pathname.startsWith("/bzz/")) return new HttpSwarm(location.origin);
  return new HttpSwarm("https://api.gateway.ethswarm.org");
}

// How Python waits for Swarm, "jspi" or "retry" (Pyodide on iOS): pycall.js.
let calls = null;

function call(name, ...args) {
  return calls.call(name, ...args);
}

function showRetrying() {
  if (!$("source").textContent.includes("retrying")) {
    $("source").textContent += "; Python reads by retrying (it cannot wait on Swarm in this browser)";
  }
}

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

const short = (owner) => `${owner.slice(0, 6)}…${owner.slice(-4)}`;

function showBooks(books) {
  $("books").tBodies[0].replaceChildren(...books.map((b) => {
    const tr = document.createElement("tr");
    tr.append(cell(short(b.owner), "mono"), cell(b.book, "mono"), cell(b.role),
      cell(b.root ? `update ${b.index}, root ${b.root.slice(0, 12)}…` : "—", "mono"),
      cell(b.folded ? `yes, ${b.offers} offer record${b.offers === 1 ? "" : "s"}` : `no: ${b.why}`));
    return tr;
  }));
}

function showRejected(rejections) {
  $("rejectedcard").classList.toggle("hidden", !rejections.length);
  $("rejected").tBodies[0].replaceChildren(...rejections.map((r) => {
    const tr = document.createElement("tr");
    tr.append(cell(short(r.owner), "mono"), cell(r.key, "mono"), cell(r.reason));
    return tr;
  }));
}

async function showOffers() {
  const answer = await call("offers", $("filter").value);
  const head = document.createElement("tr");
  head.append(...answer.columns.map((c) => { const th = document.createElement("th"); th.textContent = c; return th; }));
  $("offers").tHead.replaceChildren(head);
  $("offers").tBodies[0].replaceChildren(...answer.rows.map((r) => {
    const tr = document.createElement("tr");
    r.forEach((v, i) => {
      const col = answer.columns[i];
      tr.append(cell(col === "maker" ? short(v) : v,
        col === "side" ? v : (col === "id" || col === "maker") ? "mono" : ""));
    });
    return tr;
  }));
  $("nooffers").textContent = answer.rows.length ? "" : "No open offers in the fold.";
  return answer.rows.length;
}

function showStats() {
  const s = reader.stats;
  $("stats").textContent = `blobs and chunks fetched ${s.reads} (${(s.bytes / 1024).toFixed(0)} KB), kept from earlier visits ${s.stored}, reused ${s.cached}` +
    (s.waits ? ` · waited for the read budget ${s.waits}×` : "");
}

async function refresh() {
  if (busy) return;
  busy = true;
  const started = performance.now();
  try {
    status("Reading the registry on Gnosis…");
    const { announcements, via, logs } = await standing(REGISTRY);
    announced = announcements.map((a) => ({ owner: a.owner, book: a.book }));
    if (key) showKey();
    $("via").textContent = `${announcements.length} standing announcement${announcements.length === 1 ? "" : "s"} from ${logs} registry events, read through ${via}.`;
    status(`Finding the newest state of ${announcements.length} book${announcements.length === 1 ? "" : "s"}…`);
    await Promise.all(announcements.map(async (a) => {
      if (!a.book.startsWith("swarm:")) { a.root = null; a.why = "not a book on Swarm"; return; }
      const name = a.book.slice(6).split("@")[0];
      try {
        const latest = await reader.feedRoot(a.owner, topicOf(name));
        if (latest) { a.root = latest.root; a.index = latest.index; }
        else { a.root = null; a.why = "its feed has no update"; }
      } catch (e) {
        a.root = null; a.why = `its feed could not be read (${e.message})`;
      }
    }));
    status("Folding the books…");
    folded = await call("fold", JSON.stringify(announcements));
    showBooks(folded.books);
    showRejected(folded.rejections);
    const n = await showOffers();
    status(`${n} open offer${n === 1 ? "" : "s"}; read in ${((performance.now() - started) / 1000).toFixed(1)} s`);
    showStats();
    if (searches) await runSearches();
    return { offers: n, books: folded.books, rejections: folded.rejections };
  } catch (e) {
    status(`${e.message || e}`, true);
    console.error(e);
    return { error: String(e.message || e) };
  } finally {
    busy = false;
  }
}

// Saved searches: the person's own, in a local file (BROWSER.md §5b).
function showSearchState(summary, note = "") {
  searches = true;
  searchChanged = summary.changed;
  const n = summary.searches.length;
  $("searchstate").textContent = `${summary.name} · ${n} search${n === 1 ? "" : "es"}` +
    (summary.changed ? " · unsaved changes" : " · saved") +
    (searchFile.inPlace ? " · Save writes back to the file" : " · Save downloads the file") + (note ? ` · ${note}` : "");
  $("searchsave").disabled = false;
  $("searchadd").classList.remove("hidden");
}

function offersTable(answer, fresh) {
  const table = document.createElement("table");
  const head = document.createElement("tr");
  head.append(...answer.columns.map((c) => { const th = document.createElement("th"); th.textContent = c; return th; }));
  table.createTHead().append(head);
  const body = table.createTBody();
  for (const r of answer.rows) {
    const tr = document.createElement("tr");
    if (fresh.has(r[0])) tr.className = "newrow";
    r.forEach((v, i) => {
      const col = answer.columns[i];
      tr.append(cell(col === "maker" ? short(v) : v, col === "side" ? v : (col === "id" || col === "maker") ? "mono" : ""));
    });
    body.append(tr);
  }
  return table;
}

async function runSearches() {
  if (!folded) return;
  status("Searching (the catalogue is built once per visit)…");
  const answer = await call("searches_run");
  const box = $("searchresults");
  box.replaceChildren();
  let fresh = 0;
  for (const r of answer.results) {
    const div = document.createElement("div");
    div.className = "search";
    const h = document.createElement("h3");
    h.append(r.name);
    const info = document.createElement("span");
    if (r.error) {
      info.className = "err"; info.textContent = r.error;
      h.append(info);
    } else {
      fresh += r.new.length;
      info.className = "muted";
      info.textContent = `${r.categories}: ${r.rows.length} offer${r.rows.length === 1 ? "" : "s"}`;
      h.append(info);
      if (r.new.length) {
        const n = document.createElement("span");
        n.className = "new"; n.textContent = `${r.new.length} new`;
        const seen = document.createElement("button");
        seen.textContent = "Mark seen";
        seen.onclick = async () => { showSearchState(await call("searches_seen", r.name, JSON.stringify(r.new))); runSearches(); };
        h.append(n, seen);
      }
    }
    const del = document.createElement("button");
    del.textContent = "Delete";
    del.onclick = async () => { showSearchState(await call("searches_remove", r.name)); runSearches(); };
    h.append(del);
    div.append(h);
    if (!r.error && r.rows.length) div.append(offersTable(r, new Set(r.new)));
    box.append(div);
  }
  status(`${fresh} new offer${fresh === 1 ? "" : "s"} in your saved searches`);
}

async function searchNew() {
  if (searchChanged && !confirm("Your saved searches have unsaved changes. Start a new list anyway?")) return;
  searchFile.forget();
  showSearchState(await call("searches_new"));
  $("searchresults").replaceChildren();
}

async function searchOpen() {
  if (searchChanged && !confirm("Your saved searches have unsaved changes. Open another file anyway?")) return;
  const file = await searchFile.open();
  if (!file) return;
  const summary = await call("searches_open", await file.text(), file.name);
  if (summary.error) { status(summary.error, true); return; }
  showSearchState(summary);
  await runSearches();
}

async function searchSave() {
  const { text, name } = await call("searches_text");
  const where = await searchFile.save(text, name);
  if (!where) return;
  showSearchState(await call("searches_saved", where.name),
    where.how === "download" ? "downloaded; keep it where you like and open it next time" : "");
}

async function searchAdd() {
  const name = $("searchname").value.trim(), cats = $("searchcats").value.trim();
  const summary = await call("searches_add", name, cats);
  if (summary.error) { status(summary.error, true); return; }
  showSearchState(summary);
  $("searchname").value = ""; $("searchcats").value = "";
  await runSearches();
}

addEventListener("beforeunload", (e) => { if (searchChanged) { e.preventDefault(); e.returnValue = ""; } });

// Your offers (BROWSER.md §3, §5b): a key the person keeps in a file (the
// bee_signer value loop uses), offers made from lines by loop's own code
// (loopmarket.browser.MakerBook), signed here, published at once into the
// book loop setup names for the key (swarm:loop-<address>), through the node
// that served the page (publish.js, ontodag's, copied in by build.py).
let key = null;
let writer = null;          // a NodeWriter, when the page came from a node
let makerTopic = null;
let prepared = null;        // {id, block} of the offer shown for approval
let announced = [];         // the registry's standing announcements, last read
const stage = new Stage();
globalThis.loopStage = stage;

// The address an offer signature recovers to, checksummed as loop's makers
// are: what the book checks before it stores a signature (fail closed).
// Python calls it synchronously; loop's own signer does not install here.
function recoverMaker(offerId, sigHex) {
  const sig = unhex(String(sigHex).replace(/^0x/, ""));
  const point = secp256k1.Signature.fromCompact(sig.subarray(0, 64)).addRecoveryBit(sig[64])
    .recoverPublicKey(unhex(String(offerId)));
  const address = hex(keccak_256(point.toRawBytes(false).subarray(1)).subarray(12));
  const nibbles = hex(keccak_256(new TextEncoder().encode(address)));
  return "0x" + [...address].map((c, i) => (parseInt(nibbles[i], 16) >= 8 ? c.toUpperCase() : c)).join("");
}
globalThis.loopRecover = recoverMaker;

function makerResult(text, warn = false) {
  $("makerresult").textContent = text;
  $("makerresult").classList.toggle("warn", warn);
}

function showKey(note = "") {
  const mine = key && announced.find((a) => a.owner.toLowerCase() === key.checksummed.toLowerCase());
  const book = makerTopic ? ` Your book: swarm:${makerTopic}.` : "";
  const ann = !key ? "" : mine ? ` It is announced on the registry (${mine.book}).`
    : " It is not announced on the registry yet, so folds do not read it: Announce my book (a transaction from your key's address, paid in xDAI), or loop announce with this key.";
  $("announce").classList.toggle("hidden", !key || !makerTopic || Boolean(mine));
  $("keystate").textContent = key ? `Key ${key.checksummed}.${book}${ann}${note ? ` ${note}` : ""}` : "No key yet: making offers needs one.";
  const ready = Boolean(key && makerTopic);
  for (const id of ["offerline", "prepare", "readmine"]) $(id).disabled = !ready;
  $("publishoffer").disabled = !(ready && writer && $("makerbatch").value);
}

async function useKey(k, note) {
  key = k;
  status("Building the catalogue offers are made under (once per visit)…");
  const started = await call("maker_start", key.checksummed);
  makerTopic = started.topic;
  status(`Ready to make offers under the catalogue ${started.catalogue_root.slice(0, 12)}…, the one loop setup builds.`);
  showKey(note);
  await readMine();
}

function keyNew() {
  if (key && !confirm("Make a new key? Your book and offers stay under the key you have; keep its file.")) return;
  const k = Key.generate();
  const file = `loop-key-${k.address.slice(0, 6)}.txt`;
  download(k.text(), file);
  useKey(k, `Saved as ${file}, in your downloads unless your browser asked where. Keep that file: whoever has it can make offers as you, and without it you cannot withdraw them.`);
}

function keyOpen() {
  const input = $("keyfile");
  input.value = "";
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      await useKey(Key.fromText(await file.text()), `From ${file.name}.`);
    } catch (e) {
      makerResult(`${file.name}: ${e.message}`, true);
    }
  };
  input.click();
}

// The book's newest root: through the node when the page has one (the
// update checked against the key's address), or through what reads Swarm.
async function bookNow() {
  return writer ? writer.feedRoot(key.address, topicOf(makerTopic)) : reader.feedRoot(key.address, topicOf(makerTopic));
}

function showMine(mine) {
  const table = $("mine");
  table.classList.toggle("hidden", !mine.rows.length);
  const head = document.createElement("tr");
  head.append(...[...mine.columns, ""].map((c) => { const th = document.createElement("th"); th.textContent = c; return th; }));
  table.tHead.replaceChildren(head);
  table.tBodies[0].replaceChildren(...mine.rows.map((r) => {
    const tr = document.createElement("tr");
    r.forEach((v, i) => {
      const col = mine.columns[i];
      tr.append(cell(col === "maker" ? short(v) : v, col === "side" ? v : (col === "id" || col === "maker") ? "mono" : ""));
    });
    const td = document.createElement("td");
    const w = document.createElement("button");
    w.textContent = "Withdraw";
    w.disabled = !writer;
    w.onclick = () => withdrawOffer(r[0]);
    td.append(w);
    tr.append(td);
    return tr;
  }));
}

async function readMine() {
  try {
    const feed = await bookNow();
    const answer = await call("maker_fetch", feed ? feed.root : "");
    if (answer.error) return makerResult(answer.error, true);
    showMine(answer.mine);
    makerResult(feed ? `Your book, feed update ${feed.index}: ${answer.mine.rows.length} open offer${answer.mine.rows.length === 1 ? "" : "s"}.`
      : "Your book has nothing published yet.");
  } catch (e) {
    makerResult(`Reading your book: ${e.message || e}`, true);
  }
}

async function prepareOffer() {
  const line = $("offerline").value.trim();
  if (!line) return;
  const answer = await call("maker_prepare", line);
  if (answer.error) { $("approval").classList.add("hidden"); return makerResult(answer.error, true); }
  prepared = answer;
  $("block").textContent = answer.block;
  $("approval").classList.remove("hidden");
  makerResult(writer ? "Check the offer, then Publish." : $("makernote").textContent, !writer);
}

// Upload what a change to the book staged, then move its feed and read it
// back: the same steps as ontodag's Publish.
async function commitBook(what, change) {
  const batch = $("makerbatch").value;
  makerResult("Reading your book's feed…");
  const feed = await bookNow();
  const answer = await change(feed ? feed.root : "");
  if (answer.error) throw new Error(answer.error);
  await uploadStaged(stage, writer, batch, { progress: (t) => makerResult(`${what}: ${t}…`) });
  const index = feed ? feed.index + 1 : 0;
  makerResult(`${what}: pointing your book's feed at the new root…`);
  const update = feedUpdate(key, topicOf(makerTopic), index, answer.root, Math.floor(Date.now() / 1000));
  await writer.writeFeed(update, batch);
  const now = await writer.feedRoot(key.address, topicOf(makerTopic));
  if (!now || now.root !== answer.root) throw new Error("the feed did not read back the new root; try again");
  answer.index = index;
  return answer;
}

async function publishOffer() {
  if (!prepared || !key || !writer || busy) return;
  busy = true;
  try {
    const signature = `0x${hex(key.signHash(unhex(prepared.id)))}`;
    const id = prepared.id;
    const answer = await commitBook("Publishing", (root) => call("maker_publish", id, signature, root));
    $("approval").classList.add("hidden");
    $("offerline").value = "";
    prepared = null;
    showMine(answer.mine);
    makerResult(`Published ${answer.id.slice(0, 12)} in swarm:${makerTopic}: root ${answer.root.slice(0, 12)}…, feed update ${answer.index}.`);
  } catch (e) {
    makerResult(`Not published: ${e.message || e}`, true);
  } finally {
    busy = false;
  }
}

async function withdrawOffer(shortId) {
  if (!key || !writer || busy) return;
  const full = await call("maker_full_id", shortId);
  if (full.error) return makerResult(full.error, true);
  if (!confirm(`Withdraw ${shortId}? Whoever folds your book sees it withdrawn.`)) return;
  busy = true;
  try {
    const answer = await commitBook("Withdrawing", (root) => call("maker_withdraw", full.id, root));
    showMine(answer.mine);
    makerResult(`Withdrew ${shortId}: root ${answer.root.slice(0, 12)}…, feed update ${answer.index}.`);
  } catch (e) {
    makerResult(`Not withdrawn: ${e.message || e}`, true);
  } finally {
    busy = false;
  }
}

// Announcing (announce.js): what `loop announce` sends, from the key's
// address, paid in xDAI; asked first, with the fee.
async function announceBook() {
  if (!key || !makerTopic || busy) return;
  const book = `swarm:${makerTopic}`;
  busy = true;
  try {
    makerResult("Asking Gnosis what announcing would cost…");
    const { tx, fee, balance } = await prepareAnnounce(REGISTRY.rpc, REGISTRY.contract, key, book);
    const xdai = (wei) => {
      const x = Number(wei) / 1e18;                       // Gnosis fees are often below a millionth
      const digits = x > 0 && x < 1e-6 ? Math.min(18, Math.ceil(-Math.log10(x)) + 1) : 6;
      return `${x.toFixed(digits)} xDAI`;
    };
    if (balance < fee) {
      makerResult(`Your key's address ${key.checksummed} has ${xdai(balance)}; announcing costs at most ${xdai(fee)}. Send it a little xDAI (0.001 is plenty), then announce.`, true);
      return;
    }
    if (!confirm(`Announce ${book} on the registry? A transaction on Gnosis from ${key.checksummed}, costing at most ${xdai(fee)}. Anyone can then fold your book.`)) {
      makerResult("Not announced.");
      return;
    }
    makerResult("Announcing: sending the transaction and waiting for it…");
    const done = await sendTransaction(REGISTRY.rpc, tx, key);
    makerResult(`Announced ${book} in block ${done.block} (transaction ${done.hash}). Reading the market again…`);
  } catch (e) {
    makerResult(`Not announced: ${e.message || e}`, true);
    return;
  } finally {
    busy = false;
  }
  await refresh();
  showKey();
}

// Writing goes through a Bee node: the one that served this page (opened as
// http://localhost:1633/bzz/…), or one named with ?node=URL.
async function setUpWriting() {
  const named = params.get("node");
  const served = /^https?:$/.test(location.protocol) && location.pathname.startsWith("/bzz/") ? location.origin : null;
  const base = named || served;
  const via = "To publish, open this page through your own node (with Swarm Desktop: http://localhost:1633/bzz/loopmarket.eth/).";
  if (!base) {
    $("makernote").textContent = FreedomSwarm.present()
      ? `Publishing from Freedom waits for it to accept a chunk the page signed (freedom-browser#647). ${via}`
      : `Publishing needs your own Bee node, which pays for it. ${via}`;
    return;
  }
  const node = new NodeWriter(base);
  const batches = await node.batches();
  if (batches === null) { $("makernote").textContent = `${base} is not a node with postage batches, so this page cannot publish through it. ${via}`; return; }
  if (!batches.length) { $("makernote").textContent = `The node at ${base} has no usable postage batch. Buy one in Swarm Desktop, then reload this page.`; return; }
  writer = node;
  const select = $("makerbatch");
  select.replaceChildren(...batches.map((b) => {
    const o = document.createElement("option");
    o.value = b.id;
    o.textContent = `${b.label || `${b.id.slice(0, 8)}…`} · ${(b.ttl / 86400).toFixed(0)} days · ${Math.round(100 * b.full)}% full`;
    return o;
  }));
  select.classList.remove("hidden");
  $("makernote").textContent = `Publishing goes through the node at ${base}, paid from the batch chosen. Your key signs your offers and your book's feed; the page never stores it.`;
}

async function boot() {
  const base = pyodideBase();
  await loadScript(`${base}pyodide.js`);
  py = await loadPyodide({ indexURL: base });
  status("Installing loopmarket…");
  const manifest = await (await fetch("wheels/manifest.json")).json();
  await py.loadPackage(manifest.wheels.map((w) => new URL(`wheels/${w}`, location.href).href));

  const source = chooseSource();
  $("source").textContent = `Reading Swarm through ${source.kind}`;
  calls = new PythonCalls(py, globalThis.loopBlobs || null, {
    onRetry: async () => { showRetrying(); await calls.call("make_market", true); },
  });
  const connected = { yes: false };
  reader = new ChunkReader(source, {
    stored: await StoredChunks.open("loopmarket-swarm-chunks"),
    onRateLimit: (ms) => {
      if (source instanceof FreedomSwarm && !connected.yes) {
        status(`Freedom lets a site that has not connected read only so much of Swarm a minute; waiting ${ms / 1000} s. Press "Read faster (connect)" to read five times as much.`, true);
        $("connect").classList.add("primary");
      } else {
        status(`The read budget is spent; waiting ${ms / 1000} s…`, true);
      }
    },
  });
  globalThis.loopBlobs = new BlobStore(reader);
  if (source instanceof FreedomSwarm) {
    $("connect").classList.remove("hidden");
    $("connect").onclick = async () => {
      try {
        await source.connect();
        connected.yes = true;
        $("connect").disabled = true;
        $("connect").classList.remove("primary");
        $("connect").textContent = "Connected";
      } catch (e) {
        status(`Freedom did not connect: ${e.message}`, true);
      }
    };
  }
  await py.runPythonAsync(`
from js import loopBlobs
from loopmarket.browser import MarketPage
from ontodag.browser import RETRY, NeedBlobs

market = None
searches = None

def make_market(retry):
    """The market reader, its blobs read waiting on Swarm or by retrying."""
    global market, retrying
    retrying = bool(retry)
    catalogue = getattr(market, "_catalogue", None)
    market = MarketPage(loopBlobs, bridge=RETRY if retry else None)
    market._catalogue = catalogue
    import json
    return json.dumps({})

def fold(books):
    import json
    try:
        return market.fold(books)
    except NeedBlobs as need:
        return json.dumps({"need": need.refs})

def offers(text):
    return market.offers(text)

def searches_new():
    global searches
    from loopmarket.browser import SavedSearches
    searches = SavedSearches()
    return searches.summary()

def searches_open(text, name):
    global searches
    import json
    from loopmarket.browser import SavedSearches
    try:
        searches = SavedSearches.from_text(text, name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return searches.summary()

def searches_add(name, categories):
    return searches.add(name, categories)

def searches_remove(name):
    return searches.remove(name)

def searches_seen(name, ids):
    return searches.mark_seen(name, ids)

def searches_run():
    return searches.run(market)

def searches_text():
    import json
    return json.dumps({"text": searches.text(), "name": searches.name})

def searches_saved(name):
    return searches.saved(name)

# Your offers: loopmarket.browser.MakerBook over ontodag's StagedBlobs.
maker = None
retrying = False

def maker_start(address):
    global maker
    import json
    from loopmarket.browser import MakerBook
    from js import loopRecover
    maker = MakerBook(address, market.catalogue(), recover=lambda oid, sig: str(loopRecover(oid, sig)))
    return json.dumps({"topic": maker.topic, "catalogue_root": maker.catalogue.root})

def _staged():
    from js import loopStage
    from ontodag.browser import JsBytesStore, StagedBlobs
    if retrying:
        reader = JsBytesStore(loopBlobs, RETRY)
    else:
        from pyodide.ffi import run_sync
        reader = JsBytesStore(loopBlobs, run_sync)
    return StagedBlobs(loopStage, reader)

def maker_prepare(line):
    return maker.prepare(line)

def maker_publish(offer_id, signature, root):
    from ontodag.browser import needing
    return needing(maker.publish, offer_id, signature, root or None, _staged())

def maker_withdraw(offer_id, root):
    from ontodag.browser import needing
    return needing(maker.withdraw, offer_id, root or None, _staged())

def maker_fetch(root):
    from ontodag.browser import needing
    return needing(maker.fetch, root or None, _staged())

def maker_start_root():
    import json
    return json.dumps({"root": maker.catalogue.root})

def maker_full_id(short):
    import json
    ids = [o.offer_id for o in maker.book.offers(include_filled=True) if o.offer_id.startswith(short)]
    return json.dumps({"id": ids[0]} if len(ids) == 1 else {"error": f"{short} names {len(ids)} offers in your book"})
`);
  searchFile = new LocalFile({ input: $("searchfile"), types: SEARCH_TYPES,
    pickers: !(source instanceof FreedomSwarm), refusedKey: "loopmarket-pickers-refused" });
  globalThis.loopPage.searchFile = searchFile;
  for (const id of ["searchnew", "searchopen"]) $(id).disabled = false;
  $("searchnew").onclick = searchNew;
  $("searchopen").onclick = searchOpen;
  $("searchsave").onclick = searchSave;
  $("searchbutton").onclick = searchAdd;
  $("searchcats").onkeydown = (e) => { if (e.key === "Enter") searchAdd(); };
  calls.blobs = globalThis.loopBlobs;
  await calls.call("make_market", calls.choose(params.get("bridge")) === "retry");
  await setUpWriting();
  $("keynew").onclick = keyNew;
  $("keyopen").onclick = keyOpen;
  for (const id of ["keynew", "keyopen"]) $(id).disabled = false;
  $("prepare").onclick = prepareOffer;
  $("offerline").onkeydown = (e) => { if (e.key === "Enter") prepareOffer(); };
  $("publishoffer").onclick = publishOffer;
  $("cancelprepare").onclick = () => { prepared = null; $("approval").classList.add("hidden"); makerResult(""); };
  $("readmine").onclick = readMine;
  $("announce").onclick = announceBook;
  $("makerbatch").onchange = () => showKey();
  if (calls.mode === "retry") showRetrying();
  $("refresh").disabled = false;
  $("filter").disabled = false;
  $("refresh").onclick = refresh;
  let typing;
  $("filter").oninput = () => { clearTimeout(typing); typing = setTimeout(() => folded && showOffers(), 200); };
  return refresh();
}

// For tests and the console.
globalThis.loopPage = { refresh, call, stats: () => reader && reader.stats, connect: () => $("connect").click(), ready: null,
  bridge: () => calls && calls.mode, owner: () => key && key.checksummed, writing: () => Boolean(writer), topic: () => makerTopic };
globalThis.loopPage.ready = boot().then((r) => r, (e) => { status(`Could not start: ${e.message || e}`, true); console.error(e); return { error: String(e) }; });
