// loopmarket's read-only page in real Freedom Browser, run from a Freedom
// checkout (as ontodag's demo/freedom/freedom_check.cjs runs its page).
//
//   node browser/freedom_check.cjs REF [FREEDOM_DIR]
//
// Freedom gets a throwaway profile and the Bee node at 127.0.0.1:1633 as its
// external Swarm node; the page is opened at bzz://REF/ and its market read
// back: the standing announcements, the books in the fold, the open offers.

const path = require("path");
const fs = require("fs");
const os = require("os");
const { createRequire } = require("module");

const ref = process.argv[2];
const freedomDir = path.resolve(process.argv[3] || path.join(__dirname, "..", "..", "freedom-browser"));
if (!/^[0-9a-f]{64}$/.test(ref || "")) { console.error("usage: node freedom_check.cjs REF [FREEDOM_DIR]"); process.exit(2); }
const { _electron: electron } = createRequire(path.join(freedomDir, "package.json"))("@playwright/test");

const inPage = (window, code) => window.evaluate(async (snippet) => {
  const wv = document.querySelector("webview:not(.hidden)");
  if (!wv || typeof wv.executeJavaScript !== "function") return { error: "no webview" };
  try { return await wv.executeJavaScript(snippet); } catch (e) { return { error: String(e) }; }
}, code);

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "loopmarket-freedom-"));
  const dirs = Object.fromEntries(["userData", "ant-data", "ipfs-data", "identity"].map((d) => {
    const p = path.join(tmp, d); fs.mkdirSync(p, { recursive: true }); return [d, p];
  }));
  fs.writeFileSync(path.join(dirs.userData, "settings.json"),
    JSON.stringify({ startIpfsAtLaunch: false, startRadicleAtLaunch: false, startTorAtLaunch: false }));
  fs.writeFileSync(path.join(dirs.userData, "external-node-decisions.json"),
    JSON.stringify({ bee: { choice: "external", endpoints: ["http://127.0.0.1:1633"] } }));
  const app = await electron.launch({
    args: ["."], cwd: freedomDir, timeout: 90_000,
    env: { ...process.env, FREEDOM_TEST_USER_DATA: dirs.userData, FREEDOM_ANT_DATA: dirs["ant-data"],
      FREEDOM_IPFS_DATA: dirs["ipfs-data"], FREEDOM_IDENTITY_DATA: dirs.identity,
      ELECTRON_DISABLE_SECURITY_WARNINGS: "true", LANG: "en_US.UTF-8" },
  });
  const out = { ref, profile: tmp };
  try {
    const window = await app.firstWindow();
    await window.waitForLoadState("domcontentloaded");
    const input = window.locator('[data-test="address-input"]');
    await input.waitFor({ state: "visible", timeout: 60_000 });
    await input.click();
    await input.fill(`bzz://${ref}/`);
    await input.press("Enter");
    const started = Date.now();
    await new Promise((r) => setTimeout(r, 1500));
    let result = null;
    while (Date.now() - started < 300_000) {
      result = await inPage(window, "window.loopPage ? window.loopPage.ready : null");
      if (result && (result.offers !== undefined || result.error)) break;
      await new Promise((r) => setTimeout(r, 2000));
    }
    out.seconds = (Date.now() - started) / 1000;
    out.result = result;
    out.source = await inPage(window, "document.getElementById('source').textContent");
    out.status = await inPage(window, "document.getElementById('status').textContent");
    out.registry = await inPage(window, "document.getElementById('via').textContent");
    out.offers = await inPage(window, "window.loopPage.call('offers', '').then((a) => a.rows)");
    out.stats = await inPage(window, "window.loopPage.stats()");
    await window.screenshot({ path: path.join(tmp, "freedom.png") });
    out.screenshot = path.join(tmp, "freedom.png");
  } finally {
    await app.close().catch(() => {});
  }
  fs.writeFileSync(path.join(tmp, "report.json"), JSON.stringify(out, null, 1));
  console.log(JSON.stringify(out, null, 1));
}

main().catch((e) => { console.error(e); process.exit(1); });
