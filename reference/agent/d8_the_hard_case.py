"""Detective 8 · The hard case: a reference solution. Spoilers: `heist use-reference d8` copies it.

It reuses the planned investigation from detective 4 (loaded from the same folder)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from heist.case import Case
from heist.precinct import Precinct

HERE = Path(__file__).resolve().parent


def ablation(scores: dict[str, float]) -> list[tuple[str, float]]:
    full = scores["full"]
    drops = [(k.removeprefix("without "), round(full - v, 10)) for k, v in scores.items()
             if k.startswith("without ") and v < full]  # fmt: skip
    return sorted(drops, key=lambda x: (-x[1], x[0]))


def investigate(case: Case, llm: Any) -> Precinct:
    spec = importlib.util.spec_from_file_location("d4_for_d8", HERE / "d4_the_investigation_plan.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.investigate(case, llm)
