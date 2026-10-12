// loopmarket's read-only page: the books announced on Gnosis, folded with
// loopmarket's own code under Pyodide, their open offers listed. Swarm comes
// through swarm.js (ontodag's, copied in by build.py): Freedom Browser's
// window.swarm, or a node over HTTP. Python's synchronous store calls wait on
// those reads through JSPI, so every call into Python is a callPromising.

import { ChunkReader, BlobStore, FreedomSwarm, HttpSwarm, StoredChunks, topicOf } from "./swarm.js";
import { standing } from "./registry.js";
import { LocalFile } from "./localfile.js";

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

async function boot() {
  const base = pyodideBase();
  await loadScript(`${base}pyodide.js`);
  py = await loadPyodide({ indexURL: base });
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
searches = None

def fold(books):
    return market.fold(books)

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
