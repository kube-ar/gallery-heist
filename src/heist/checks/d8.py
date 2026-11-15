"""Checks for detective 8, the hard case."""

from __future__ import annotations

from types import ModuleType

from ..case import list_cases, load_case
from .core import NotStarted, Result, attempt, tally

L_END = ("agentic-graphrag", "agentic-graphrag-end-to-end", "Agentic GraphRAG end to end")


def run(module: ModuleType) -> list[Result]:
    table = Result("Which pieces carry the cases", L_END)
    hard = Result("Your best detective on the hard pack", L_END)
    try:
        fixtures = [
            ({"full": 0.75, "without notebook": 0.5, "without rulebook": 0.75, "without plan": 0.25},
             [("plan", 0.5), ("notebook", 0.25)]),
            ({"full": 0.5, "without gate": 0.5}, []),
            ({"full": 1.0, "without b": 0.5, "without a": 0.5}, [("a", 0.5), ("b", 0.5)]),
        ]  # fmt: skip
        right = 0
        for scores, want in fixtures:
            got = attempt(table, module.ablation, scores)
            ok = got is not None and [(p, round(d, 6)) for p, d in got] == want
            right += ok
            if not ok:
                table.fail(f"ablation({scores}) = {got}, want {want}")
        tally(table, right, len(fixtures), "tables")
    except NotStarted:
        table.started = table.passed = False
    from ..llm import LLMError, get_llm

    try:
        llm = get_llm()
    except LLMError as e:
        hard.started = hard.passed = False
        hard.notes.append(f"Needs an LLM: {e}. Then run `uv run heist llm`.")
        return [table, hard]
    try:
        accused = solved = 0
        names = list_cases("hard")
        for name in names:
            desk = attempt(hard, module.investigate, load_case(name), llm)
            if desk is None:
                continue
            accused += desk.accusation is not None
            solved += desk.verdict()["solved"]
        hard.score = f"{accused}/{len(names)} accused, {solved} solved"
        if accused < len(names):
            hard.fail("Every hard case must end in an accusation.")
    except NotStarted:
        pass
    except LLMError as e:
        hard.fail(f"the LLM call failed: {e}")
    return [table, hard]
