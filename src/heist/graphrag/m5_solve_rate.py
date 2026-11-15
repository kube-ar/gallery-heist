"""Milestone 5 · Solve rate.

Instructions: https://kube.ar/graphrag/project/gallery-heist/solve-rate

Put the board to work on the whole case: name the thief, the accomplice and how it was done,
with the evidence. Then measure it the way the evaluation lesson does: solve rate per pack,
layer scores read from the bottom, a pairwise judge that can't be fooled by order or length,
and a manifest for every run so two runs can be compared fairly.

Check your work with `uv run heist check 5`. The final pack's answers are hashed: the check
tells you how many you solved, never who did it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from heist.case import Case


def solve(case: Case) -> dict:
    """{"culprit": id, "accomplice": id or None, "method": "insider" | "borrowed_badge" |
    "fire_door", "evidence": [sentences]}. Use anything you've built: the graph, the alibis,
    the statements, the board, an LLM."""
    raise NotImplementedError


def triple_scores(predicted: list[tuple], gold: list[tuple]) -> dict[str, float]:
    """{"precision", "recall", "f1"} of predicted triples against a gold set. Duplicates count once;
    with nothing predicted, or nothing right, every score is 0."""
    raise NotImplementedError


def bottom_up(scores: dict[str, float], bars: dict[str, float]) -> str | None:
    """The first layer, from the bottom (graph, then retrieval, then answer), whose score is under
    its bar. None when every layer clears its bar."""
    raise NotImplementedError


def pairwise(question: str, a: str, b: str, judge: Callable[[str, str, str], str]) -> str:
    """ "a", "b" or "tie". judge(question, first, second) answers "first" or "second".

    Cancel position bias (ask in both orders; a winner only if both agree) and length bias
    (show the judge both answers at the same length)."""
    raise NotImplementedError


def manifest(case: Case, **config: Any) -> dict:
    """Everything a run depends on: "case", "case_fingerprint" (a hash of the case's files,
    truth.json excluded), "code" (the git commit), "provider" and "model" (from .env), "config"
    (what you passed) and "created" (when)."""
    raise NotImplementedError


def diff(a: dict, b: dict) -> dict:
    """What differs between two manifests, as {key: (a's value, b's value)}, with config keys at
    the top level and "created" ignored."""
    raise NotImplementedError
