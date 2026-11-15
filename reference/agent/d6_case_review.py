"""Detective 6 · Case review: a reference solution. Spoilers: `heist use-reference d6` copies it."""

from __future__ import annotations

import networkx as nx

from heist.precinct import SOURCE_WORDS, TOOL_SOURCE, Precinct

DIAGNOSES = ("grounding", "knowledge", "retrieval", "reasoning", "none")


def _cited(accusation: dict | None) -> set[str]:
    text = " ".join((accusation or {}).get("evidence", [])).lower()
    return {kind for kind, words in SOURCE_WORDS.items() if any(w in text for w in words)}


def execution_graph(desk: Precinct) -> nx.DiGraph:
    g = nx.DiGraph()
    previous = None
    for a in desk.log:
        node = ("call", a.step)
        g.add_node(node, step=a.step, tool=a.tool, arguments=a.arguments, minute=a.minute, cost=a.cost, ok=a.ok)
        if previous:
            g.add_edge(previous, node, type="NEXT")
        previous = node
    if desk.accusation:
        g.add_node(("accusation",), **desk.accusation)
        cited = _cited(desk.accusation)
        for a in desk.log:
            if a.ok and TOOL_SOURCE.get(a.tool) in cited:
                g.add_edge(("accusation",), ("call", a.step), type="CITES")
    return g


def wasted_minutes(graph: nx.DiGraph) -> int:
    cited = (
        {v for _, v, d in graph.out_edges(("accusation",), data=True) if d["type"] == "CITES"}
        if ("accusation",) in graph
        else set()
    )
    return sum(d["cost"] for n, d in graph.nodes(data=True)
               if n[0] == "call" and d["ok"] and d["tool"] in TOOL_SOURCE and n not in cited)  # fmt: skip


def diagnose(desk: Precinct) -> str:
    verdict = desk.verdict()
    if verdict.get("solved"):
        return "none"
    acc = desk.accusation
    if acc and _cited(acc) - desk.consulted():
        return "grounding"
    if acc and ("R2" in verdict["reason"] or "R4" in verdict["reason"]):
        return "knowledge"
    case = desk.case
    seen, found = case.at(case.meta["last_seen"][11:]), case.at(case.meta["discovered"][11:])
    room = case.meta["room"]["id"]

    def covers(a) -> bool:
        if not (a.arguments.get("start") and a.arguments.get("end")):
            return False
        return case.at(a.arguments["start"]) < found and case.at(a.arguments["end"]) > seen

    ok = [a for a in desk.log if a.ok]
    cameras = any(a.tool == "camera_log" and covers(a) for a in ok)
    doors = any(a.tool == "keycard_log" and a.arguments.get("room") in (room, "R34") for a in ok)
    phones = any(a.tool == "phone_records" for a in ok)
    if not (cameras and doors and phones):
        return "retrieval"
    return "reasoning"


FIXES = {
    "grounding": "constraint",
    "knowledge": "prompt",
    "retrieval": "retrieval",
    "reasoning": "fine-tune",
    "none": "none",
}


def choose_fix(diagnosis: str) -> str:
    return FIXES[diagnosis]


def safe_to_ship(before: dict[str, bool], after: dict[str, bool], max_forgetting: int = 0) -> bool:
    forgotten = sum(1 for case, solved in before.items() if solved and not after.get(case, False))
    return sum(after.values()) > sum(before.values()) and forgotten <= max_forgetting
