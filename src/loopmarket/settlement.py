"""Compatibility alias: `loopmarket.settlement` was renamed `loopmarket.clearing`
on 2026-09-07.

Why: what this module does is *clearing* in the finance sense — a solver's
proposal becomes a bundle of fixed obligations under one root. *Settlement*
is when the makers actually deliver; that is P3's territory (oracles, bonds,
factbond). Using one word for both hid the gap. Sister repos (factbond,
ontodag docs) still say `MockSettlement`; this shim keeps them importable
for one release and then goes.
"""

from .clearing import (  # noqa: F401
    Clearing, LoopProposal, MockClearing, Receipt,
)

Settlement = Clearing
MockSettlement = MockClearing
