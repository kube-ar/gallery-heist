"""Detective 4 · The investigation plan.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/the-investigation-plan

The rookie improvised every call. Split the case into a workflow graph instead: a planning step
with no tools, narrow execution nodes that each hold one or two desk tools, a validation node,
and a decision. Run independent nodes in the same phase. Before asking for a warrant, check the
accusation's meaning, not just its shape: a valid JSON accusation can still name the wrong kind
of person or a method the building doesn't allow.

Check your work with `uv run heist check d4`: the plan and the checks need no LLM.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.precinct import Precinct

KINDS = ("reasoning", "execution", "decision", "validation")
PROBLEMS = ("unknown-person", "same-person", "bad-method", "too-few-sources", "unconsulted-source",
            "no-unguarded-door", "no-badge")  # fmt: skip


def compound_success(per_step: float, steps: int) -> float:
    """The chance a run of `steps` independent steps all succeed, each with probability `per_step`."""
    raise NotImplementedError


def plan(case: Case) -> list[dict]:
    """The investigation as a workflow graph, made without calling any tool.

    Each step: {"id", "kind" (one of KINDS), "tools" (desk tools it may call), "needs" (ids of the
    steps whose output it uses)}. Only execution steps hold tools, at most two each."""
    raise NotImplementedError


def phases(steps: list[dict]) -> list[list[str]]:
    """The steps in phases that can run in parallel: each phase holds the steps whose needs are all
    in earlier phases. Ids sorted inside a phase."""
    raise NotImplementedError


def validate_accusation(desk: Precinct, accusation: dict) -> list[str]:
    """The meaning problems of an accusation, as codes from PROBLEMS, in that order.

    unknown-person: the culprit or the accomplice isn't on the lists.
    same-person: culprit and accomplice are the same person.
    bad-method: not insider, borrowed_badge or fire_door.
    too-few-sources: the evidence cites fewer than two kinds of source.
    unconsulted-source: it cites a kind of source the desk never returned.
    no-unguarded-door: fire_door, but no door without a reader leads into the stolen painting's wing.
    no-badge: insider, but the culprit holds no badge."""
    raise NotImplementedError


def investigate(case: Case, llm: Any) -> Precinct:
    """Run your plan: execute each phase's tools, decide with structured output (llm.json with a
    schema), validate, and only then accuse."""
    raise NotImplementedError
