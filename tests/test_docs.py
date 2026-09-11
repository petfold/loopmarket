"""Documentation guards: claims in the docs that a test can check."""


def test_readme_states_the_current_test_count(request):
    """The README quotes a test count, and a quoted number goes stale in silence.

    `session.testscollected` is the number of *selected* tests — it includes
    runtime-skipped ones and excludes marker-deselected ones — so the README
    must state that total, not the number that happened to pass. Skipped when
    only part of the suite ran, because the count would be meaningless then.
    """
    import re
    from pathlib import Path

    import pytest

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    m = re.search(r"(\d{2,4}) (?:tests|passed)", readme)
    assert m, "the README no longer quotes a test count — drop this guard, or restore it"
    claimed, collected = int(m.group(1)), request.session.testscollected
    if collected < claimed * 0.8:
        pytest.skip(f"partial run: {collected} of ~{claimed} selected")
    assert collected == claimed, (
        f"README says {claimed} tests, the suite selects {collected}. "
        "Update the README (this is the reminder that docs drift silently)."
    )
