"""Places in the tests: the rectangle a coordinate literal spells."""

from ontodag import dimensions as _dims


def square(literal: str) -> str:
    """The parameter of the `geo` term `literal` spells, in ontodag's
    canonical bounds: `square('46.05,14.50±5km')` is
    `46.005033..46.094967,14.435157..14.564843`."""
    return _dims.split_term(_dims.canonicalize(f"geo({literal})", _dims.KIND_RECT))[1]
