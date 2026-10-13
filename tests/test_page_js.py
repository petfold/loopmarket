"""The page's announcement (browser/announce.js) against eth_account, under
node: the call data for announce(book, role) and the signed transaction,
byte for byte (browser/test/announce_vector.json, made by
make_announce_vector.py). The page's other scripts are ontodag's, copied in
by browser/build.py; this assembles the same, so it skips without node or
without ontodag's checkout beside this one."""

import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BROWSER = os.path.join(os.path.dirname(HERE), "browser")
ONTODAG_PAGE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ontodag", "demo", "freedom")


@pytest.mark.skipif(not shutil.which("node") or not os.path.isdir(ONTODAG_PAGE),
                    reason="needs node and ontodag's checkout beside this one")
def test_an_announcement_is_signed_as_loop_announce_signs_it():
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(os.path.join(BROWSER, "announce.js"), tmp)
        for f in ("publish.js", "swarm.js"):
            shutil.copy(os.path.join(ONTODAG_PAGE, f), tmp)
        shutil.copytree(os.path.join(ONTODAG_PAGE, "vendor"), os.path.join(tmp, "vendor"))
        os.makedirs(os.path.join(tmp, "test"))
        shutil.copy(os.path.join(BROWSER, "test", "test_announce.mjs"), os.path.join(tmp, "test"))
        run = subprocess.run(["node", os.path.join(tmp, "test", "test_announce.mjs"),
                              os.path.join(BROWSER, "test", "announce_vector.json")],
                             capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all passed" in run.stdout
