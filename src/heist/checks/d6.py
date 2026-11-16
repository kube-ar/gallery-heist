"""Checks for detective 6, case review."""

from __future__ import annotations

import json
from types import ModuleType

from ..case import load_case
from ..precinct import TOOL_SOURCE, Precinct, cited_sources
from .core import NotStarted, Result, attempt, tally

L_EXEC = ("agentic-graphrag", "execution-graph", "Execution graph")
L_DIAG = ("agentic-graphrag", "agent-failure-diagnosis", "Agent failure diagnosis")
L_EVOLVE = ("agentic-graphrag", "self-evolving-agents", "Self-evolving agents")
L_SAFE = ("agentic-graphrag", "safe-agent-evolution", "Safe agent evolution")


def scripted() -> dict[str, tuple[Precinct, str]]:
    """Runs that end each way, with the diagnosis they deserve."""
    case = load_case("practice/case-01")
    crime = json.loads((case.path / "truth.json").read_text(encoding="utf-8"))["crime"]
    culprit, accomplice, method = crime["culprit"]["native_id"], crime["accomplice"]["native_id"], crime["method"]
    innocent = next(s.employee_id for s in case.staff if s.employee_id not in (culprit, accomplice))
    seen, found, room = case.meta["last_seen"][11:], case.meta["discovered"][11:], case.meta["room"]["id"]
    good = ["the camera log shows the cameras went dark", "the keycard log puts the accomplice in the Security Office",
            "phone records show the two of them calling"]  # fmt: skip

    def gather(desk, cameras=True, doors=True, phones=True):
        if cameras:
            desk.call("camera_log", {"start": seen, "end": found})
        if doors:
            desk.call("keycard_log", {"room": room, "start": seen, "end": found})
        if phones:
            desk.call("phone_records", {"person": accomplice})
        return desk

    runs = {}
    d = gather(Precinct(case))
    d.call("accuse", {"culprit": culprit, "accomplice": accomplice, "method": method, "evidence": good})
    runs["solved"] = (d, "none")
    d = gather(Precinct(case), phones=False)
    d.call("accuse", {"culprit": culprit, "accomplice": accomplice, "method": method,
                      "evidence": ["the camera log", "bank transfers between them"]})  # fmt: skip
    runs["cites the bank, never asked it"] = (d, "grounding")
    d = gather(Precinct(case), doors=False, phones=False)
    d.call("accuse", {"culprit": culprit, "accomplice": accomplice, "method": method, "evidence": ["the camera log"]})
    runs["one kind of source"] = (d, "knowledge")
    d = Precinct(case)
    d.call("keycard_log", {"room": "R34", "start": seen, "end": found})
    d.call("interview", {"person": innocent})
    d.call("accuse", {"culprit": innocent, "accomplice": "", "method": "insider",
                      "evidence": ["the keycard log", "the statement given in the interview"]})  # fmt: skip
    runs["never looked at the cameras"] = (d, "retrieval")
    d = gather(Precinct(case))
    d.call("accuse", {"culprit": innocent, "accomplice": accomplice, "method": method, "evidence": good})
    runs["had it all, named the wrong person"] = (d, "reasoning")
    d = gather(Precinct(case))
    runs["never accused"] = (d, "reasoning")
    return runs


def official_waste(desk: Precinct) -> int:
    cited = cited_sources((desk.accusation or {}).get("evidence", []))
    return sum(a.cost for a in desk.log if a.ok and a.tool in TOOL_SOURCE and TOOL_SOURCE[a.tool] not in cited)


def run(module: ModuleType) -> list[Result]:
    graph = Result("An execution graph you can query", L_EXEC)
    diag = Result("Four checks, in order", L_DIAG)
    fix = Result("The fix, chosen by code", L_EVOLVE)
    ship = Result("Ship only what doesn't forget", L_SAFE)
    runs = scripted()
    try:
        right = 0
        for label, (desk, _) in runs.items():
            g = attempt(graph, module.execution_graph, desk)
            got = attempt(graph, module.wasted_minutes, g) if g is not None else None
            want = official_waste(desk)
            right += got == want
            if got != want and got is not None:
                graph.fail(f"{label}: wasted {got} minutes, want {want}")
        tally(graph, right, len(runs), "runs")
    except NotStarted:
        graph.started = graph.passed = False
    try:
        right = 0
        for label, (desk, want) in runs.items():
            got = attempt(diag, module.diagnose, desk)
            right += got == want
            if got != want and got is not None:
                diag.fail(f"{label}: {got!r}, want {want!r}")
        tally(diag, right, len(runs), "runs")
    except NotStarted:
        diag.started = diag.passed = False
    try:
        want = {"grounding": "constraint", "knowledge": "prompt", "retrieval": "retrieval", "reasoning": "fine-tune",
                "none": "none"}  # fmt: skip
        right = sum(attempt(fix, module.choose_fix, d) == f for d, f in want.items())
        tally(fix, right, len(want), "diagnoses")
    except NotStarted:
        fix.started = fix.passed = False
    try:
        before = {"a": True, "b": True, "c": False, "d": False}
        fixtures = [
            ({"a": True, "b": True, "c": True, "d": False}, 0, True),
            ({"a": True, "b": False, "c": True, "d": True}, 0, False),
            ({"a": True, "b": False, "c": True, "d": True}, 1, True),
            ({"a": True, "b": True, "c": False, "d": False}, 0, False),
        ]
        right = 0
        for after, limit, want_ok in fixtures:
            got = attempt(ship, module.safe_to_ship, before, after, limit)
            right += got is want_ok
            if got is not want_ok:
                ship.fail(f"safe_to_ship({after}, max_forgetting={limit}) = {got}, want {want_ok}")
        tally(ship, right, len(fixtures), "releases")
    except NotStarted:
        ship.started = ship.passed = False
    return [graph, diag, fix, ship]
