"""Detective 3 · The notebook.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/the-notebook

The rookie forgot what it had read three tool calls ago and believed whoever spoke last. Give the
detective a notebook: a memory graph of facts with two times each (when the fact was true, and
when the detective learned it), that keeps what was observed (the logs) apart from what was
claimed (the statements), finds the claims the observations rule out, and can tell you what the
detective believed at any moment of the investigation.

heist.precinct.extract_facts(case, tool, arguments, result) turns a tool's result into facts:
{"person", "room", "at" (HH:MM), "kind" ("observed" or "claimed"), "source"}.

Check your work with `uv run heist check d3`: the notebook needs no LLM.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.precinct import Precinct


def new_notebook() -> Any:
    raise NotImplementedError


def remember(notebook: Any, fact: dict, learned_at: int) -> str:
    """Store a fact, learned at minute `learned_at` of the investigation. Return its id."""
    raise NotImplementedError


def believed_at(notebook: Any, person: str, at: str, as_of: int | None = None) -> str | None:
    """The room the notebook places `person` in at `at` (HH:MM), counting only facts learned by
    minute `as_of` (all of them if None).

    An observation wins over a claim: the room of the latest observed fact at or before `at`.
    With no observation, the latest claim at or before `at`, if it's at most 60 minutes old.
    Otherwise None. Times after midnight come after times before it (00:15 is after 23:50)."""
    raise NotImplementedError


def conflicts(notebook: Any, case: Case) -> list[dict]:
    """The claimed facts that the observations rule out, as {"person", "room", "at"}.

    A claim is ruled out when every observed position of that person from 10 minutes before the
    claim's time to 10 minutes after is somewhere the claimed room can't be reached from without
    a card reader (no observations then: not ruled out)."""
    raise NotImplementedError


def history(notebook: Any, person: str) -> list[dict]:
    """Everything known about a person, in the order it was true, each as {"room", "at", "kind",
    "source", "learned_at"}. Ties: observed first, then by when it was learned."""
    raise NotImplementedError


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: each list adds 1 / (k + rank) for every item in it (rank from 1).
    Return (item, score) best first; equal scores in item order."""
    raise NotImplementedError


def investigate(case: Case, llm: Any) -> Precinct:
    """Your detective, now with a notebook: remember the facts of every tool result, and give the
    agent tools to ask what it believes and which statements the logs contradict."""
    raise NotImplementedError
