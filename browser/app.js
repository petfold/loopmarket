// loopmarket's read-only page: the books announced on Gnosis, folded with
// loopmarket's own code under Pyodide, their open offers listed. Swarm comes
// through swarm.js (ontodag's, copied in by build.py): Freedom Browser's
// window.swarm, or a node over HTTP. Python's synchronous store calls wait on
// those reads through JSPI, so every call into Python is a callPromising.

import { ChunkReader, BlobStore, FreedomSwarm, HttpSwarm, StoredChunks, topicOf } from "./swarm.js";
import { standing } from "./registry.js";

// The LoopBookRegistry (loopmarket's DEFAULT_REGISTRY), deployed 2026-09-14.
const REGISTRY = {
  rpc: "https://rpc.gnosischain.com",
  contract: "0xD4379E494a488411D964BebDb210C0bf628d97af",
  fromBlock: 48249000,
};

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
let py, reader, folded = null;
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

async function call(name, ...args) {
  const fn = py.globals.get(name);
  try {
    return JSON.parse(await fn.callPromising(...args));
  } finally {
    fn.destroy();
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
  $("stats").textContent = `chunks fetched ${s.reads} (${(s.bytes / 1024).toFixed(0)} KB), kept from earlier visits ${s.stored}, reused ${s.cached}` +
    (s.waits ? ` · waited for the read budget ${s.waits}×` : "");
}

async function refresh() {
  if (busy) return;
  busy = true;
  const started = performance.now();
  try {
    status("Reading the registry on Gnosis…");
    const { announcements, via, logs } = await standing(REGISTRY);
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
    return { offers: n, books: folded.books, rejections: folded.rejections };
  } catch (e) {
    status(`${e.message || e}`, true);
    console.error(e);
    return { error: String(e.message || e) };
  } finally {
    busy = false;
  }
}

async function boot() {
  py = await loadPyodide({ indexURL: new URL("pyodide/", location.href).href });
  status("Installing loopmarket…");
  const manifest = await (await fetch("wheels/manifest.json")).json();
  await py.loadPackage(manifest.wheels.map((w) => new URL(`wheels/${w}`, location.href).href));

  const source = chooseSource();
  $("source").textContent = `Reading Swarm through ${source.kind}`;
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

market = MarketPage(loopBlobs)

def fold(books):
    return market.fold(books)

def offers(text):
    return market.offers(text)
`);
  $("refresh").disabled = false;
  $("filter").disabled = false;
  $("refresh").onclick = refresh;
  let typing;
  $("filter").oninput = () => { clearTimeout(typing); typing = setTimeout(() => folded && showOffers(), 200); };
  return refresh();
}

// For tests and the console.
globalThis.loopPage = { refresh, call, stats: () => reader && reader.stats, connect: () => $("connect").click(), ready: null };
globalThis.loopPage.ready = boot().then((r) => r, (e) => { status(`Could not start: ${e.message || e}`, true); console.error(e); return { error: String(e) }; });
