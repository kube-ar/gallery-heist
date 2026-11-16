"""Detective 6 · Case review.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/case-review

Every run leaves a record at the desk. Turn it into an execution graph you can query, diagnose a
failed run with four checks in order, pick the fix by code from the diagnosis, and only ship a
changed detective if it solves more cases without forgetting the ones it used to solve.

Check your work with `uv run heist check d6`: everything here is deterministic.
"""

from __future__ import annotations

from typing import Any

from heist.precinct import Precinct

DIAGNOSES = ("grounding", "knowledge", "retrieval", "reasoning", "none")


def execution_graph(desk: Precinct) -> Any:
    """A node per desk call (step, tool, arguments, minute, cost, ok), NEXT between consecutive calls,
    and, if there was an accusation, a node for it with CITES edges to the calls whose kind of source
    its evidence names (heist.precinct.cited_sources reads them the way the chief does)."""
    raise NotImplementedError


def wasted_minutes(graph: Any) -> int:
    """Minutes spent on successful source calls (keycard, camera, phone, bank, interview) whose kind of
    source the accusation never cites. With no accusation, every source call's minutes."""
    raise NotImplementedError


def diagnose(desk: Precinct) -> str:
    """The first of four checks that fails, in this order (or "none" when the case was solved):

    grounding: the evidence cites a kind of source the desk never returned.
    knowledge: the chief refused the warrant under R2 or R4 (the rules weren't followed).
    retrieval: the run never asked the camera log about the theft window, or never asked the keycard
      log about the stolen room or the Security Office, or never pulled anyone's phone records.
    reasoning: it had all that and still named the wrong person, or never accused."""
    raise NotImplementedError


def choose_fix(diagnosis: str) -> str:
    """grounding → "constraint", knowledge → "prompt", retrieval → "retrieval", reasoning → "fine-tune",
    none → "none". Decided by code, the same way every time."""
    raise NotImplementedError


def safe_to_ship(before: dict[str, bool], after: dict[str, bool], max_forgetting: int = 0) -> bool:
    """Ship the new detective only if it solves more cases than the old one and forgets (stops solving)
    at most `max_forgetting` cases the old one solved. Both map case id → solved."""
    raise NotImplementedError
