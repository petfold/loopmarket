"""Dependency boundaries (mirroring OntoDAG's B-tests; must always pass).

B1  The model core imports and works with no network and no Bee node.
B2  Dependency direction is one-way: loopmarket -> ontodag -> recordstore.
    loopmarket never reaches around ontodag/recordstore to import Swarm
    machinery at module import time; Bee/feed code loads only inside
    swarm_offer_book / Ontology.persistent call paths.
"""

import subprocess
import sys


def test_b1_core_imports_offline():
    code = (
        "import socket\n"
        "def deny(*a, **k): raise AssertionError('network at import time')\n"
        "socket.socket.connect = deny\n"
        "import loopmarket\n"
        "from loopmarket import Offer, Ontology, OfferRegistry, SolverAgent\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=".", env={"PYTHONPATH": "src", "PATH": ""},
    )
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr


def test_b2_no_bee_modules_at_import():
    code = (
        "import sys\n"
        "import loopmarket\n"
        "loaded = [m for m in sys.modules if 'requests' in m or 'swarm_bee' in m]\n"
        "print('LOADED:' + ','.join(loaded))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=".", env={"PYTHONPATH": "src", "PATH": ""},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "LOADED:", out.stdout
