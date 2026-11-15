"""Detective 8 · The hard case.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/the-hard-case

Put it all together: the rulebook, the notebook, the plan, the gated tools, the review. Run your
best detective on the hard pack, then take it apart one piece at a time and see which pieces were
carrying the cases.

Check your work with `uv run heist check d8`.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.precinct import Precinct


def ablation(scores: dict[str, float]) -> list[tuple[str, float]]:
    """From solve rates like {"full": 0.75, "without notebook": 0.5, "without rulebook": 0.75}, the pieces
    whose removal lowered the rate, as (piece, drop), biggest drop first; ties by name. The piece's name
    is what follows "without "."""
    raise NotImplementedError


def investigate(case: Case, llm: Any) -> Precinct:
    """Your best detective."""
    raise NotImplementedError
