"""The examples, run as a user runs them (the 2026-10 review, §7
suggestion 9): the federation demo with ontodag's core pack, in memory,
and the delivery session fed to the `loop` command line. Each runs in a
subprocess from this checkout's source, in a scratch home, with no Bee
node and no key in its environment, and its output is checked line by
line for what the example claims."""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


def _run(tmp_path, argv, stdin=None):
    """`argv` under this checkout's `src`, homes in `tmp_path`, and nothing
    of the caller's loop, Bee or ontodag settings: a live Bee node in the
    environment would turn the federation demo live."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LOOP_", "BEE_", "ONTODAG_"))}
    env.update(PYTHONPATH=os.path.join(ROOT, "src"), LOOP_HOME=str(tmp_path / "loop"),
               ONTODAG_HOME=str(tmp_path / "odag"))
    result = subprocess.run([sys.executable, *argv], stdin=stdin, env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_federation_demo_runs_and_says_what_it_shows(tmp_path):
    out = _run(tmp_path, [os.path.join(EXAMPLES, "demo_federation.py")])
    for claim in (
            "=== the federated book — in memory ===",
            "adopted ontodag's core pack",
            "all three manifest roots byte-identical: True",
            "different book_root (True): the fold is pure",
            "all by ['chen']",
            "honest aggregator A audits clean: True",
            "a solver trusting Cain's manifest finds 0 loops",
            "lands on A's book_root: True",
            "active offers in the fold: 7",
            'the forgery was refused: "foreign maker without valid signature"',
            "bruno's tombstone closed his regretted offer: True",
            "re-commit reproduces the root: True",
            "the solver cleared 1 loop",
            "re-fold with the clearing book: identical again: True",
            "reads the loop and 6 atomic fills",
            "second solver pass over the cleared fold finds: 0 loops",
            "=== done ==="):
        assert claim in out, claim
    assert re.search(r"finds (\d+) omissions", out).group(1) == "2"       # chen's two offers
    assert "proof verifies with no store access: False" not in out


def test_the_delivery_session_clears_its_composed_leg(tmp_path):
    with open(os.path.join(EXAMPLES, "delivery.loop"), encoding="utf-8") as script:
        out = _run(tmp_path, ["-m", "loopmarket", "--catalogue", os.path.join(EXAMPLES, "delivery.od")],
                   stdin=script)
    assert out.count("  offer_id ") == 9                                            # nine offers published
    cleared = out[out.index("\ncleared "):]
    assert re.match(r"\ncleared [0-9a-f]{16}… surplus 104\.08%\n", cleared)
    assert re.search(r"grocer gives \S+ vegetable-box \+ courier gives .*transport\(small-item\)"
                     r" to buyer \(composed\)", cleared)
    for leg in ("mechanic gives bicycle-repair", "buyer gives", "to mechanic", "to courier"):
        assert leg in cleared, leg
    assert cleared.count(" gives ") == 5                                            # four legs, one composed
    assert re.search(r"\nbook root [0-9a-f]{64}\n", cleared)
