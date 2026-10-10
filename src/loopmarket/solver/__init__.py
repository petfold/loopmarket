"""The baseline solver, kept apart from the rest of loopmarket: nothing but
the command line imports this package (agent.py's docstring)."""

from .agent import SolverAgent, baseline_proposals

__all__ = ["SolverAgent", "baseline_proposals"]
