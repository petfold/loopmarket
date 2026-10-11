"""What a missing optional dependency says: an instruction naming the
command that installs it. A `RuntimeError`, as before, so callers that
catch one still do; the `loop` command prints it as one line, never a
traceback."""


class MissingExtra(RuntimeError):
    """An optional dependency is not installed; the message names the
    extra that brings it (`pip install 'loopmarket[chain]'`)."""
