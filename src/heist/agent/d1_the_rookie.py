"""Detective 1 · The rookie.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/the-rookie

The board answered questions about files it already had. A detective has to go and get the
evidence: interviews, logs and records from the precinct's desk, each costing minutes from the
night's budget, until it's ready to ask the chief for a warrant (heist.precinct).

Build the simplest agent that can do it: one model, the desk's tools, a loop. Then read its runs
and name what went wrong, with the five failures from the course's overview lesson. This rookie
is the baseline every later milestone has to beat.

Check your work with `uv run heist check d1`: naming failures needs no LLM; running the agent does.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.precinct import Precinct

FAILURES = ("context amnesia", "relationship blindness", "temporal ignorance", "reasoning paralysis", "tool chaos")


def investigate(case: Case, llm: Any, max_turns: int = 40) -> Precinct:
    """Work the case at a Precinct desk with `llm` (heist.llm.Conversation helps), and return the desk.

    Stop when the agent accuses, or after `max_turns` model turns. Don't accuse on its behalf:
    a rookie that never makes up its mind is a failure worth seeing."""
    raise NotImplementedError


def failures(desk: Precinct) -> list[str]:
    """The failures in a finished run, by the rules below, in the order of FAILURES.

    context amnesia: the same tool was called twice with the same arguments (both succeeded).
    relationship blindness: the run consulted fewer than two kinds of source (desk.consulted()).
    temporal ignorance: no keycard_log or camera_log call gave both a start and an end that
      overlap the theft window, from the last round to the discovery.
    reasoning paralysis: the run ended without an accusation.
    tool chaos: three or more calls failed.
    """
    raise NotImplementedError
