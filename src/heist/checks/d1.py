"""Checks for detective 1, the rookie."""

from __future__ import annotations

from types import ModuleType

from ..case import list_cases, load_case
from ..llm import LLMError
from ..precinct import Precinct
from .core import NotStarted, Result, attempt, model_for, tally

L_WHAT = ("agentic-graphrag", "what-is-agentic-graphrag", "What is agentic GraphRAG?")
L_GRAPHS = ("agentic-graphrag", "knowledge-graph-and-workflow-graph", "Knowledge graph and workflow graph")


def _runs() -> dict[str, tuple[Precinct, list[str]]]:
    """Scripted runs that show each failure (and one that shows none), with the right labels."""
    case = load_case("practice/case-01")
    seen, found = case.meta["last_seen"][11:], case.meta["discovered"][11:]
    room = case.meta["room"]["id"]
    good_evidence = ["the camera log shows the cameras went dark", "the keycard log shows who opened the room"]
    runs = {}

    desk = Precinct(case)
    desk.call("camera_log", {"start": seen, "end": found})
    desk.call("keycard_log", {"room": room, "start": seen, "end": found})
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": good_evidence})
    runs["a careful run"] = (desk, [])

    desk = Precinct(case)
    desk.call("camera_log", {"start": seen, "end": found})
    desk.call("keycard_log", {"room": room, "start": seen, "end": found})
    desk.call("camera_log", {"start": seen, "end": found})
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": good_evidence})
    runs["the same question twice"] = (desk, ["context amnesia"])

    desk = Precinct(case)
    desk.call("keycard_log", {"room": room, "start": seen, "end": found})
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": good_evidence})
    runs["one kind of source"] = (desk, ["relationship blindness"])

    desk = Precinct(case)
    desk.call("keycard_log", {"room": room})
    desk.call("camera_log", {})
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": good_evidence})
    runs["never looked at the window"] = (desk, ["temporal ignorance"])

    desk = Precinct(case)
    desk.call("camera_log", {"start": seen, "end": found})
    desk.call("keycard_log", {"room": room, "start": seen, "end": found})
    runs["never accused"] = (desk, ["reasoning paralysis"])

    desk = Precinct(case)
    for bad in ({"person": "nobody"}, {"person": "E-0000"}, {"who": "E-1415"}):
        desk.call("interview", bad)
    desk.call("camera_log", {"start": seen, "end": found})
    desk.call("keycard_log", {"room": room, "start": seen, "end": found})
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": good_evidence})
    runs["three failed calls"] = (desk, ["tool chaos"])

    desk = Precinct(case)
    desk.call("keycard_log", {})
    desk.call("keycard_log", {})
    desk.call("teleport", {})
    desk.call("interview", {"person": "E-1415"})
    desk.call("interview", {"person": "E-1415"})
    runs["everything at once"] = (desk, list(("context amnesia", "relationship blindness", "temporal ignorance",
                                              "reasoning paralysis", "tool chaos")))  # fmt: skip
    return runs


def run(module: ModuleType) -> list[Result]:
    named = Result("Failures, named", L_WHAT)
    works = Result("The rookie works a case", L_GRAPHS)
    try:
        right = 0
        runs = _runs()
        for label, (desk, want) in runs.items():
            got = attempt(named, module.failures, desk)
            if got == want:
                right += 1
            elif got is not None:
                named.fail(f"{label}: got {got}, want {want}")
        tally(named, right, len(runs), "runs")
    except NotStarted:
        pass
    _works(module, works)
    return [named, works]


def _labels(module, desk: Precinct) -> str:
    """Your failures() on a real run, for the notes: "Failures, named" already says if it's wrong."""
    try:
        labels = module.failures(desk)
    except Exception:  # NotImplementedError included
        return "(failures() didn't run)"
    return ", ".join(map(str, labels or [])) or "none"


def _works(module, r: Result) -> None:
    llm = model_for(r)
    if llm is None:
        return
    accused = warrants = solved = 0
    names = list_cases("practice")
    try:
        for name in names:
            desk = attempt(r, module.investigate, load_case(name), llm)
            if desk is None:
                continue
            verdict = desk.verdict()
            accused += desk.accusation is not None
            warrants += verdict["warrant"]
            solved += verdict["solved"]
            r.notes.append(f"{name}: {len(desk.log)} calls, {desk.spent} min, "
                           f"{'solved' if verdict['solved'] else 'not solved'}; failures: {_labels(module, desk)}")  # fmt: skip
    except NotStarted:
        return
    except LLMError as e:
        r.fail(f"the LLM call failed: {e}")
        return
    r.score = f"{accused}/{len(names)} accused, {warrants} warrants, {solved} solved"
    if accused < len(names):
        r.fail(
            "The rookie has to reach an accusation on every practice case (it may be wrong). If it runs out of "
            "turns, give it more turns or a clearer task, but keep it naive."
        )
    r.notes.append(f"LLM: {llm.provider.name} {llm.model}, {llm.usage.calls} calls")
