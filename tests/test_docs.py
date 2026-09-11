"""Documentation guards: claims in the docs that a test can check."""


def test_readme_states_the_current_test_count(request):
    """The README quotes a test count, and a quoted number goes stale in silence.

    Enforced **only in CI**, because the collected count depends on which
    optional dependencies are installed and CI is the one reproducible
    environment (`pip install -e ".[test]"` on a clean runner). A developer
    machine with extra packages present — or missing one — collects a
    different number through no fault of the docs, so failing there would be
    noise. Publication is gated on CI, which is where this needs to hold.
    """
    import os
    import re
    from pathlib import Path

    import pytest

    if not os.environ.get("CI"):
        pytest.skip("enforced in CI, where the environment is canonical")
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    m = re.search(r"(\d{2,4}) (?:tests|passed)", readme)
    assert m, "the README no longer quotes a test count — drop this guard, or restore it"
    claimed, collected = int(m.group(1)), request.session.testscollected
    assert collected == claimed, (
        f"README says {claimed} tests, CI selects {collected}. "
        "Update the README (this is the reminder that docs drift silently)."
    )
