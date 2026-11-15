"""Detective 7 · Budget and clearance.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/budget-and-clearance

Running the detective every night costs money and reads people's private records. Route each
step to the cheapest model that's good enough, measure cost per solved case rather than per call,
give a junior investigator a desk where restricted records don't exist (not a desk that says
"denied"), answer an auditor's question from the desks' logs, and erase a person's personal data
on request.

Check your work with `uv run heist check d7`: everything here is deterministic.
"""

from __future__ import annotations

from typing import Any

from heist.precinct import Precinct

RESTRICTED = {"junior": {"bank_records", "phone_records"}, "senior": set()}


def route_model(step: str, bars: dict[str, float], models: dict[str, tuple[float, float]]) -> str:
    """The cheapest model whose quality meets the step's bar. models: name → (quality, cost per call).
    Ties on cost: the better one. No model good enough: the best one there is."""
    raise NotImplementedError


def cost_per_solved(runs: list[tuple[float, bool]]) -> float:
    """Total cost of all runs divided by the number solved (float("inf") when none was solved)."""
    raise NotImplementedError


def restricted(desk: Precinct, role: str) -> Any:
    """A desk for a role: the same tools minus RESTRICTED[role], which aren't in its tools() and,
    when called anyway, fail exactly like a tool that doesn't exist."""
    raise NotImplementedError


def audit(desks: list[Precinct], person: str) -> list[tuple[str, int, str]]:
    """Every successful call, across these desks, that read records about `person` (phone_records,
    bank_records or interview with person=…), as (case id, step, tool), in order."""
    raise NotImplementedError


def erase(people: list[dict], person: str) -> list[dict]:
    """The people table with this person's personal data removed: their row keeps "id" and "kind",
    loses every other field. Other rows stay as they are."""
    raise NotImplementedError
