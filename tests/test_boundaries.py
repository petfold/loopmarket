"""Dependency boundaries (mirroring OntoDAG's B-tests; must always pass).

B1  The model core imports and works with no network and no Bee node.
B2  Dependency direction is one-way: loopmarket -> ontodag -> recordstore.
    loopmarket never reaches around ontodag/recordstore to import Swarm
    machinery at module import time; Bee/feed code loads only inside
    swarm_offer_book / Ontology.persistent call paths.
B3  The baseline solver is kept apart (the 2026-10 review's item 2, decided
    by Peter 2026-10-10): nothing in loopmarket but the command line
    imports `loopmarket.solver`, and the solver imports only loopmarket's
    public interfaces, as a solver outside loopmarket would.
"""

import ast
import pkgutil
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "loopmarket"


def test_b1_core_imports_offline():
    code = (
        "import socket\n"
        "def deny(*a, **k): raise AssertionError('network at import time')\n"
        "socket.socket.connect = deny\n"
        "import loopmarket\n"
        "from loopmarket import Offer, Ontology, OfferRegistry, SolverAgent\n"
        "import loopmarket.cli\n"   # the command line is core too (cli.md G3)
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
        "import loopmarket.cli\n"
        # the Swarm path's clients: requests/swarm_bee until recordstore
        # 0.22, swarmfs over aiohttp since (and coincurve for its signer)
        "loaded = [m for m in sys.modules if m.split('.')[0] in "
        "('requests', 'swarm_bee', 'swarmfs', 'aiohttp', 'coincurve')]\n"
        "print('LOADED:' + ','.join(loaded))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=".", env={"PYTHONPATH": "src", "PATH": ""},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "LOADED:", out.stdout


def test_b3_no_module_but_the_command_line_loads_the_solver():
    """Every module of the package but the command line's and the solver's
    own imports, in a fresh interpreter, without loading the solver; then
    `from loopmarket import SolverAgent` still works, loading it on first
    use."""
    import loopmarket
    names = sorted(f"loopmarket.{m.name}" for m in pkgutil.iter_modules(loopmarket.__path__)
                   if m.name not in ("cli", "solver", "__main__"))
    assert "loopmarket.clearing" in names and "loopmarket.auction" in names and "loopmarket.beat" in names
    code = (
        "import importlib, sys\n"
        f"for name in {names!r}: importlib.import_module(name)\n"
        "print('SOLVER:' + ','.join(sorted(m for m in sys.modules if m.startswith('loopmarket.solver'))))\n"
        "from loopmarket import SolverAgent\n"
        "print('LAZY:' + SolverAgent.__module__)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=".", env={"PYTHONPATH": "src", "PATH": ""},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == ["SOLVER:", "LAZY:loopmarket.solver.agent"], out.stdout


def _imported(path: Path, package: list[str]) -> list[str]:
    """Every module an `import` or `from ... import` anywhere in the file
    names — inside functions too — relative imports resolved."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            out += [module] + [f"{module}.{a.name}" for a in node.names]
    return out


def test_b3_no_source_but_the_command_lines_names_the_solver():
    """The same, read from the source rather than the import system: no
    module outside `cli/` and `solver/` imports the solver, not even inside
    a function (where the auction once imported it to compute its reserve
    bid; `loopmarket.solver.baseline_proposals` computes that now)."""
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        if rel.parts[0] in ("cli", "solver") or rel.name == "__main__.py":
            continue
        package = ["loopmarket", *rel.parts[:-1]]
        solver = [m for m in _imported(path, package)
                  if m == "loopmarket.solver" or m.startswith("loopmarket.solver.")]
        assert not solver, f"{rel} imports {solver}"


def test_b3_the_solver_uses_only_public_interfaces():
    """The solver imports from loopmarket what an outside solver could:
    names exported by `loopmarket.__all__` or documented in
    docs/REFERENCE.md, never a private one, each by its absolute path; a
    relative import stays inside the solver package."""
    import loopmarket
    reference = (SRC.parent.parent / "docs" / "REFERENCE.md").read_text(encoding="utf-8")
    seen = 0
    for path in sorted((SRC / "solver").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert node.level == 1, f"{path.name}: a relative import out of the solver package"
            elif isinstance(node, ast.ImportFrom) and node.module.split(".")[0] == "loopmarket":
                for alias in node.names:
                    name, seen = alias.name, seen + 1
                    assert not name.startswith("_"), f"{path.name} imports the private {node.module}.{name}"
                    documented = re.search(rf"`(?:[\w.]+\.)?{re.escape(name)}[`(]", reference)
                    assert name in loopmarket.__all__ or documented, \
                        f"{path.name} imports {node.module}.{name}, which is neither exported nor documented"
            elif isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "loopmarket" for a in node.names), path.name
    assert seen > 20
