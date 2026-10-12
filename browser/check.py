"""End-to-end check of loopmarket's read-only page, outside the suite:
Playwright's Chromium runs the page from browser/dist/ through a stand-in
for Freedom Browser's window.swarm answered from a real Bee node, and reads
the registry on Gnosis from the public RPC, as the page does outside
Freedom. Its offers are compared with the same fold computed natively:
the standing announcements through web3, each book's root through
recordstore's SwarmFeedPointer, the books through BeeBytesStore.

    python3 browser/build.py && python3 browser/check.py
    python3 browser/check.py --url http://localhost:1633/bzz/REF/   # served by the node

Needs a Bee node (BEE_API, default localhost:1633) that can reach the
announced books, the `chain` extra (web3) for the native side, and
playwright with Chromium.
"""

import argparse
import asyncio
import base64
import functools
import http.server
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PYODIDE_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ontodag", "demo", "pyodide", "node_modules", "pyodide")
API = os.environ.get("BEE_API", "http://localhost:1633").rstrip("/")
RPC, CONTRACT = "https://rpc.gnosischain.com", "0xD4379E494a488411D964BebDb210C0bf628d97af"

FREEDOM_STANDIN = """
window.swarm = {
  isFreedomBrowser: true,
  async request({ method, params }) {
    const r = await window.__standin(method, params || {});
    if (r.error) { const e = new Error(r.error.message); e.code = r.error.code; e.data = r.error.data; throw e; }
    return r.result;
  },
  requestAccess() { return this.request({ method: 'swarm_requestAccess' }); },
  readChunk(p) { return this.request({ method: 'swarm_readChunk', params: p }); },
  readSingleOwnerChunk(p) { return this.request({ method: 'swarm_readSingleOwnerChunk', params: p }); },
  readFeedEntry(p) { return this.request({ method: 'swarm_readFeedEntry', params: p }); },
};
"""


def bee(path):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=120) as res:
            return res.status, res.read(), res.headers
    except urllib.error.HTTPError as e:
        return e.code, b"", e.headers


def not_found(reason):
    return {"error": {"code": -32602, "message": reason, "data": {"reason": reason}}}


def _span(raw):
    """A span as Freedom hands it over: a number, or for one past 2^53 (an
    erasure-coded chunk's level byte) a BigInt, here its decimal string,
    which BigInt() in swarm.js reads the same."""
    value = int.from_bytes(raw, "little")
    return value if value <= 2**53 - 1 else str(value)


def standin(calls, method, params):
    """Freedom's provider answered from the node, with Freedom's result
    shapes and error reasons (swarm-provider-ipc.js, chunk-service.js)."""
    from swarmfs.bmt import keccak256
    calls[method] = calls.get(method, 0) + 1
    if method == "swarm_requestAccess":
        return {"result": {"connected": True}}
    if method == "swarm_readChunk":
        status, wire, _ = bee(f"/chunks/{params['reference']}")
        if status == 404:
            return not_found("chunk_not_found")
        return {"result": {"data": base64.b64encode(wire[8:]).decode(), "encoding": "base64",
                           "span": _span(wire[:8])}}
    if method == "swarm_readSingleOwnerChunk":
        owner = params["owner"].removeprefix("0x").lower()
        address = keccak256(bytes.fromhex(params["identifier"]) + bytes.fromhex(owner)).hex()
        status, wire, _ = bee(f"/chunks/{address}")
        if status == 404:
            return not_found("chunk_not_found")
        return {"result": {"data": base64.b64encode(wire[105:]).decode(), "encoding": "base64",
                           "span": _span(wire[97:105]), "reference": address,
                           "owner": owner, "identifier": params["identifier"], "signature": wire[32:97].hex()}}
    if method == "swarm_readFeedEntry":
        owner = params["owner"].removeprefix("0x").lower()
        status, body, headers = bee(f"/feeds/{owner}/{params['topic']}")
        if status == 404:
            return not_found("feed_empty")
        index = int(headers["swarm-feed-index"], 16)
        return {"result": {"data": base64.b64encode(body).decode(), "encoding": "base64",
                           "index": index, "nextIndex": index + 1}}
    return {"error": {"code": 4200, "message": f"{method} is not in this stand-in"}}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    """dist/, with /pyodide/ answered from demo/pyodide's npm copy: the page
    is told ?pyodide=/pyodide/ instead of fetching the shared folder."""

    def log_message(self, *args):
        pass

    def translate_path(self, path):
        clean = path.split("?", 1)[0]
        if clean.startswith("/pyodide/"):
            return os.path.join(PYODIDE_DIR, clean[len("/pyodide/"):])
        return super().translate_path(path)


def serve(directory):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=directory))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def native():
    """The same fold in plain Python: announcements through web3, roots
    through SwarmFeedPointer, books through BeeBytesStore."""
    from recordstore import BeeBytesStore, SwarmFeedPointer
    from loopmarket.announce import ChainAnnouncements
    from loopmarket.browser import MarketPage

    class NodeBlobs:                      # the page's BlobStore shape, synchronous
        def __init__(self):
            self.store = BeeBytesStore(API)

        def download(self, ref):
            return self.store.get(ref)

    books = []
    for ann in ChainAnnouncements(RPC, CONTRACT).announced():
        b = {"owner": ann.owner, "book": ann.book, "role": ann.role, "root": None}
        if ann.book.startswith("swarm:"):
            b["root"] = SwarmFeedPointer(API, ann.book[6:].split("@")[0], owner=ann.owner).get()
        books.append(b)
    page = MarketPage(NodeBlobs(), bridge=lambda value: value)
    folded = json.loads(page.fold(json.dumps(books)))
    return folded, json.loads(page.offers())["rows"]


async def check_page(url, freedom):
    from playwright.async_api import async_playwright
    calls = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on("console", lambda m: m.type == "error" and print("  page console:", m.text))
        if freedom:
            async def answer(method, params):
                return await asyncio.to_thread(standin, calls, method, params)
            await page.expose_function("__standin", answer)
            await page.add_init_script(FREEDOM_STANDIN)
        started = time.time()
        if url.startswith("http://127.0.0.1"):           # served here: Pyodide from the npm copy
            url += ("&" if "?" in url else "?") + "pyodide=/pyodide/"
        await page.goto(url)
        result = await page.evaluate("window.loopPage.ready")
        print(f"  page ready after {time.time() - started:.1f} s; source: {await page.inner_text('#source')}")
        print(f"  status: {await page.inner_text('#status')}")
        print(f"  registry: {await page.inner_text('#via')}")
        rows = (await page.evaluate("window.loopPage.call('offers', '')"))["rows"] if "error" not in result else None
        stats = await page.evaluate("window.loopPage.stats()")
        print(f"  chunks fetched {stats['reads']} ({stats['bytes'] // 1024} KB); window.swarm calls {calls}")
        await browser.close()
    return result, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="the page as a node serves it (http://localhost:1633/bzz/REF/)")
    args = ap.parse_args()
    folded, want = native()
    print("native: " + "; ".join(f"{b['book']} ({b['role']}) folded={b['folded']}" for b in folded["books"]))
    print(f"native: {len(want)} open offers, {len(folded['rejections'])} rejections")
    if args.url:
        print(f"over HTTP: {args.url}")
        result, rows = asyncio.run(check_page(args.url, freedom=False))
    else:
        server = serve(os.path.join(HERE, "dist"))
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        print(f"Freedom's path (stand-in window.swarm over {API}): {url}")
        result, rows = asyncio.run(check_page(url, freedom=True))
        server.shutdown()
    if rows is None:
        print(f"the page failed: {result}")
        sys.exit(1)
    same = sorted(map(tuple, rows)) == sorted(map(tuple, want))
    for r in rows:
        print("  ", "  ".join(r))
    print("the page's offers match the native fold" if same else "MISMATCH between the page and the native fold")
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
