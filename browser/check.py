"""End-to-end check of loopmarket's read-only page, outside the suite:
Playwright's Chromium runs the page from browser/dist/ through a stand-in
for Freedom Browser's window.swarm answered from a real Bee node, and reads
the registry on Gnosis from the public RPC, as the page does outside
Freedom. Its offers are compared with the same fold computed natively:
the standing announcements through web3, each book's root through
recordstore's SwarmFeedPointer, the books through BeeBytesStore.

    python3 browser/build.py && python3 browser/check.py
    python3 browser/check.py --url http://localhost:1633/bzz/REF/   # served by the node
    python3 browser/check.py --url ... --publish --batch ID         # and make an offer

`--publish` (through the node only) makes an offer in the page under a
throwaway key, as `loop give` would, publishes it into the key's book, reads
the book back natively (SwarmFeedPointer, BeeBytesStore) and checks the
offer, its signature and its catalogue pin, then withdraws it in the page
and checks that too. The key is never printed.

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


#: The saved search the check makes in the page and answers natively.
SEARCH = "lesson"


async def check_searches(page, want):
    """Saved searches through the page's buttons (BROWSER.md §5b): a new
    list, a search (its offers equal the native search's, all new), mark
    seen, save (a download), open again by the file input. The problems."""
    import tempfile
    problems = []
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await page.evaluate("window.loopPage.searchFile.pickers = false")
    await page.click("#searchnew")
    await page.wait_for_selector("#searchadd:not(.hidden)")
    await page.fill("#searchname", "lessons")
    await page.fill("#searchcats", SEARCH)
    t = time.time()
    await page.click("#searchbutton")
    await page.wait_for_selector("#searchresults .search", timeout=180_000)
    first = time.time() - t
    rows = await page.eval_on_selector_all("#searchresults table tbody tr",
                                           "trs => trs.map(tr => [...tr.cells].map(td => td.textContent))")
    fresh = await page.eval_on_selector_all("#searchresults tr.newrow", "trs => trs.length")
    shown = sorted(tuple(r) for r in rows)
    expected = sorted(tuple(r[:1]) + tuple(r[1:]) for r in want)
    if [r[0] for r in shown] != [r[0] for r in expected]:
        problems.append(f"search {SEARCH!r}: page {shown}, native {expected}")
    if fresh != len(want):
        problems.append(f"{fresh} marked new of {len(want)}")
    if want:
        await page.click("#searchresults button:text('Mark seen')")
        await page.wait_for_function("!document.querySelector('#searchresults tr.newrow')")
    async with page.expect_download() as info:
        await page.click("#searchsave")
    saved = json.loads(open(await (await info.value).path()).read())
    seen = saved["searches"][0]["seen"] if saved.get("searches") else None
    if saved.get("format") != "loopmarket saved searches" or seen is None or len(seen) != len(want):
        problems.append(f"saved file: {saved!r}")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(saved, fh)
    await page.click("#searchnew")
    async with page.expect_file_chooser() as chooser:
        await page.click("#searchopen")
    await (await chooser.value).set_files(fh.name)
    await page.wait_for_selector("#searchresults .search", timeout=60_000)
    again = await page.eval_on_selector_all("#searchresults tr.newrow", "trs => trs.length")
    if again:
        problems.append(f"after reopening, {again} still marked new")
    os.unlink(fh.name)
    print(f"  first search (the catalogue built in the page): {first:.1f} s")
    print(f"  saved searches: new list, search, mark seen, save (download), open (file input): "
          f"{'ok' if not problems else problems}")
    return problems


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
    return folded, json.loads(page.offers())["rows"], json.loads(page.search(SEARCH))["rows"]


#: What Pyodide reads to choose its JavaScript trampoline (and so no JSPI):
#: an iPhone's navigator.platform. `--iphone` reports it, so Chromium runs the
#: page as Freedom on iOS does.
IPHONE = "Object.defineProperty(Navigator.prototype, 'platform', { get: () => 'iPhone' })"


def _book_natively(address, topic):
    """The key's book as its feed has it, read natively: (root, registry)."""
    from recordstore import BeeBytesStore, RecordStore, SwarmFeedPointer

    from loopmarket.registry import OfferRegistry
    root = SwarmFeedPointer(API, topic, owner=address).get()
    return root, (OfferRegistry(RecordStore.at(root, BeeBytesStore(API))) if root else None)


async def check_maker(page):
    """An offer made, published and withdrawn in the page under a throwaway
    key, each step read back natively; the problems found."""
    import secrets
    import tempfile

    from loopmarket.sigs import maker_address, verify_offer_sig
    problems = []
    if not await page.evaluate("window.loopPage.writing()"):
        return ["the page has no node to publish through"]
    secret = "0x" + secrets.token_hex(32)       # (check_searches already accepts the page's dialogs)
    address = maker_address(secret)
    with tempfile.TemporaryDirectory() as tmp:
        keyfile = os.path.join(tmp, "key.txt")
        with open(keyfile, "w") as fh:
            fh.write(secret + "\n")
        t = time.time()
        async with page.expect_file_chooser() as chooser:
            await page.click("#keyopen")
        await (await chooser.value).set_files(keyfile)
        await page.wait_for_function("window.loopPage.topic()", timeout=600_000)
        owner = await page.evaluate("window.loopPage.owner()")
        topic = await page.evaluate("window.loopPage.topic()")
        print(f"  maker ready in {time.time() - t:.0f} s (the catalogue built in the page): book swarm:{topic}")
        if owner != address:
            problems.append("the page read another address from the key file")
        await page.fill("#offerline", "give piano-lesson 30")
        await page.click("#prepare")
        await page.wait_for_selector("#approval:not(.hidden)")
        block = await page.inner_text("#block")
        if "piano-lesson" not in block or owner not in block:
            problems.append(f"the approval block: {block[:200]!r}")
        t = time.time()
        await page.click("#publishoffer")
        await page.wait_for_function("/^(Published|Not published)/.test(document.getElementById('makerresult').textContent)",
                                     timeout=600_000)
        said = await page.inner_text("#makerresult")
        print(f"  publish: {said[:100]} ({time.time() - t:.0f} s)")
        if not said.startswith("Published"):
            return problems + [f"publishing failed: {said}"]
        root, book = await asyncio.to_thread(_book_natively, owner, topic)
        offers = [o for o in book.offers(include_filled=True)] if book else []
        if len(offers) != 1:
            return problems + [f"the book, read natively, holds {len(offers)} offers"]
        offer = offers[0]
        catalogue_root = await page.evaluate("window.loopPage.call('maker_start_root')")
        if offer.maker != owner:
            problems.append(f"the offer's maker is {offer.maker}")
        if not verify_offer_sig(offer, book.signature(offer.offer_id) or ""):
            problems.append("the offer's signature does not recover to its maker natively")
        if offer.ontology_root != catalogue_root.get("root"):
            problems.append(f"the offer pins {offer.ontology_root[:12]}, not the page's catalogue")
        # Announcing with no xDAI: the page asks Gnosis what it would cost,
        # sees the balance, and sends nothing (nothing is announced or spent).
        await page.click("#announce")
        await page.wait_for_function("/(xDAI|Not announced)/.test(document.getElementById('makerresult').textContent)",
                                     timeout=120_000)
        said = await page.inner_text("#makerresult")
        print(f"  announce with an empty key: {said[:120]}")
        if "has 0.000000 xDAI" not in said:
            problems.append(f"announcing from an empty key: {said}")
        t = time.time()
        await page.click("#mine button")
        await page.wait_for_function("/^(Withdrew|Not withdrawn)/.test(document.getElementById('makerresult').textContent)",
                                     timeout=600_000)
        said = await page.inner_text("#makerresult")
        print(f"  withdraw: {said[:100]} ({time.time() - t:.0f} s)")
        _root, book = await asyncio.to_thread(_book_natively, owner, topic)
        if not book or not book.is_withdrawn(offer.offer_id):
            problems.append(f"the withdrawal did not reach the book: {said}")
    print(f"  your offers: key file, prepare, publish, read natively (maker, signature, catalogue pin), withdraw: "
          f"{'ok' if not problems else problems}")
    return problems


async def check_page(url, freedom, searched=(), mode=None, iphone=False, publish=False):
    from playwright.async_api import async_playwright
    calls = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on("console", lambda m: m.type == "error" and print("  page console:", m.text))
        if iphone:
            await page.add_init_script(IPHONE)
        if freedom:
            async def answer(method, params):
                return await asyncio.to_thread(standin, calls, method, params)
            await page.expose_function("__standin", answer)
            await page.add_init_script(FREEDOM_STANDIN)
        started = time.time()
        if url.startswith("http://127.0.0.1"):           # served here: Pyodide from the npm copy
            url += ("&" if "?" in url else "?") + "pyodide=/pyodide/"
        await page.goto(url + (("&" if "?" in url else "?") + f"bridge={mode}" if mode else ""))
        result = await page.evaluate("window.loopPage.ready")
        print(f"  page ready after {time.time() - started:.1f} s; source: {await page.inner_text('#source')}")
        print(f"  bridge: {await page.evaluate('window.loopPage.bridge()')}")
        print(f"  status: {await page.inner_text('#status')}")
        print(f"  registry: {await page.inner_text('#via')}")
        rows = (await page.evaluate("window.loopPage.call('offers', '')"))["rows"] if "error" not in result else None
        stats = await page.evaluate("window.loopPage.stats()")
        print(f"  chunks fetched {stats['reads']} ({stats['bytes'] // 1024} KB); window.swarm calls {calls}")
        problems = await check_searches(page, searched) if rows is not None else []
        if publish and rows is not None:
            problems += await check_maker(page)
        await browser.close()
    return result, rows, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="the page as a node serves it (http://localhost:1633/bzz/REF/)")
    ap.add_argument("--bridge", choices=("jspi", "retry"),
                    help="how Python waits for Swarm (default: the page decides); "
                         "retry is what Pyodide on iOS needs")
    ap.add_argument("--publish", action="store_true",
                    help="with --url: make, publish and withdraw an offer through the node")
    ap.add_argument("--iphone", action="store_true",
                    help="report an iPhone's platform, as Freedom on iOS does (Pyodide then takes its "
                         "JavaScript trampoline, and the page must read by retrying)")
    args = ap.parse_args()
    folded, want, searched = native()
    print("native: " + "; ".join(f"{b['book']} ({b['role']}) folded={b['folded']}" for b in folded["books"]))
    print(f"native: {len(want)} open offers, {len(folded['rejections'])} rejections")
    if args.url:
        print(f"over HTTP: {args.url}")
        result, rows, problems = asyncio.run(check_page(args.url, freedom=False, searched=searched, mode=args.bridge,
                                                        iphone=args.iphone, publish=args.publish))
    else:
        server = serve(os.path.join(HERE, "dist"))
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        print(f"Freedom's path (stand-in window.swarm over {API}): {url}")
        result, rows, problems = asyncio.run(check_page(url, freedom=True, searched=searched, mode=args.bridge, iphone=args.iphone))
        server.shutdown()
    if rows is None:
        print(f"the page failed: {result}")
        sys.exit(1)
    same = sorted(map(tuple, rows)) == sorted(map(tuple, want))
    for r in rows:
        print("  ", "  ".join(r))
    print("the page's offers match the native fold" if same else "MISMATCH between the page and the native fold")
    if problems:
        print(f"saved searches: {len(problems)} problems")
    sys.exit(0 if same and not problems else 1)


if __name__ == "__main__":
    main()
