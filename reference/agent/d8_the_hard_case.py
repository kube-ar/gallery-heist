"""Detective 8 · The hard case: a reference solution. Spoilers: `heist use-reference d8` copies it.

It reuses the planned investigation of the d4 reference, loaded from reference/agent/, so it works
whatever your own d4 file holds."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

from heist.case import ROOT, Case
from heist.precinct import Precinct

# By path from reference/, never from this file's folder: after `use-reference d8` that's your folder.
D4 = ROOT / "reference" / "agent" / "d4_the_investigation_plan.py"


def ablation(scores: dict[str, float]) -> list[tuple[str, float]]:
    full = scores["full"]
    drops = [(k.removeprefix("without "), round(full - v, 10)) for k, v in scores.items()
             if k.startswith("without ") and v < full]  # fmt: skip
    return sorted(drops, key=lambda x: (-x[1], x[0]))


def _d4():
    spec = importlib.util.spec_from_file_location("d4_for_d8", D4)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def investigate(case: Case, llm: Any) -> Precinct:
    return _d4().investigate(case, llm)
