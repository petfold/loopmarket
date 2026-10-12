"""Assemble loopmarket's read-only page into browser/dist/, and publish it.

    python3 browser/build.py                       # dist/ only
    python3 browser/build.py --publish --batch ID  # and upload it to Swarm

The page's Swarm layer (swarm.js and its vendored keccak) is ontodag's
(demo/freedom/ in the ontodag checkout beside this one), copied in so there
is one source. Pyodide is not in it: the page loads the shared Pyodide
folder on Swarm (app.js, PYODIDE), as ontodag's page does. The wheels are built from this
checkout and from ontodag's and recordstore's beside it. Publishing reuses
ontodag's build.py: one deterministic collection on a Bee node's /bzz, its
reference printed before its retrievability is checked.
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PROJECTS = os.path.dirname(REPO)
ONTODAG_PAGE = os.path.join(PROJECTS, "ontodag", "demo", "freedom")


def ontodag_build():
    """ontodag's demo/freedom/build.py, as a module."""
    spec = importlib.util.spec_from_file_location("ontodag_page_build", os.path.join(ONTODAG_PAGE, "build.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assemble(dist, base):
    if os.path.isdir(dist):
        shutil.rmtree(dist)
    os.makedirs(os.path.join(dist, "wheels"))
    for f in ("index.html", "app.js", "registry.js"):
        shutil.copy(os.path.join(HERE, f), os.path.join(dist, f))
    for f in ("swarm.js", "localfile.js", "pycall.js"):
        shutil.copy(os.path.join(ONTODAG_PAGE, f), os.path.join(dist, f))
    shutil.copytree(os.path.join(ONTODAG_PAGE, "vendor"), os.path.join(dist, "vendor"))
    wheels = [base.wheel(os.path.join(PROJECTS, p), os.path.join(dist, "wheels"))
              for p in ("recordstore", "ontodag")]
    wheels.append(base.wheel(REPO, os.path.join(dist, "wheels")))
    with open(os.path.join(dist, "wheels", "manifest.json"), "w") as fh:
        json.dump({"wheels": wheels}, fh, indent=1)
    base.fingerprint(dist)
    return wheels


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dist", default=os.path.join(HERE, "dist"))
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--api", default=os.environ.get("BEE_API", "http://localhost:1633"))
    ap.add_argument("--batch", default=os.environ.get("BEE_BATCH"))
    ap.add_argument("--no-build", action="store_true", help="publish dist/ as it is")
    ap.add_argument("--wait", type=float, default=20)
    args = ap.parse_args()
    base = ontodag_build()
    if not args.no_build:
        print(f"wheels: {', '.join(assemble(args.dist, base))}")
    if args.publish:
        if not args.batch:
            sys.exit("publishing needs a postage batch: --batch ID or BEE_BATCH")
        api = args.api.rstrip("/")
        ref = base.upload(args.dist, api, args.batch)
        print(f"published: bzz://{ref}/  ({api}/bzz/{ref}/)", flush=True)
        base.advance_feed("loopmarket", api, ref, args.batch)
        ok = base.retrievable(api, ref, args.wait)
        print("retrievable" if ok else "NOT yet retrievable: check GET /stewardship later")


if __name__ == "__main__":
    main()
