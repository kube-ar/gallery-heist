"""Detective 1 · The rookie: a reference solution. Spoilers: `heist use-reference d1` copies it."""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.llm import Conversation
from heist.precinct import Precinct

FAILURES = ("context amnesia", "relationship blindness", "temporal ignorance", "reasoning paralysis", "tool chaos")

SYSTEM = """You are a detective investigating a theft at a museum gala. You work at a desk of tools:
records, logs, interviews. Every tool costs minutes from a limited budget, so choose what to ask for.
When you are confident, call `accuse` with the culprit, the accomplice, the method and the evidence.
Read the rulebook first: the chief only signs a warrant if your evidence follows it."""


def investigate(case: Case, llm: Any, max_turns: int = 40) -> Precinct:
    desk = Precinct(case)
    convo = Conversation(llm, desk.tools(), system=SYSTEM)
    turn = convo.send("A painting was stolen tonight. Work the case and accuse whoever did it.")
    for _ in range(max_turns):
        if turn.done or desk.accusation is not None:
            break
        results = {call.id: desk.call(call.name, call.arguments) for call in turn.tool_calls}
        if desk.accusation is not None:
            break
        errors = {cid for cid, r in results.items() if isinstance(r, dict) and "error" in r}
        turn = convo.reply(results, errors=errors)
    return desk


def failures(desk: Precinct) -> list[str]:
    case = desk.case
    seen, found = case.at(case.meta["last_seen"][11:]), case.at(case.meta["discovered"][11:])
    calls = [a for a in desk.log if a.ok]
    keys = [(a.tool, tuple(sorted((k, str(v)) for k, v in a.arguments.items()))) for a in calls]
    found_failures = set()
    if len(keys) != len(set(keys)):
        found_failures.add("context amnesia")
    if len(desk.consulted()) < 2:
        found_failures.add("relationship blindness")
    windowed = False
    for a in calls:
        if a.tool in ("keycard_log", "camera_log") and a.arguments.get("start") and a.arguments.get("end"):
            start, end = case.at(a.arguments["start"]), case.at(a.arguments["end"])
            windowed |= start < found and end > seen
    if not windowed:
        found_failures.add("temporal ignorance")
    if desk.accusation is None:
        found_failures.add("reasoning paralysis")
    if sum(not a.ok for a in desk.log) >= 3:
        found_failures.add("tool chaos")
    return [f for f in FAILURES if f in found_failures]
