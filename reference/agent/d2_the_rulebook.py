"""Detective 2 · The rulebook: a reference solution. Spoilers: `heist use-reference d2` copies it."""

from __future__ import annotations

import json
import re
from typing import Any

import networkx as nx

from heist.case import Case
from heist.llm import Conversation
from heist.precinct import RULEBOOK, Precinct, records

SPEC: dict[str, dict] = {
    "Person": {"match": r"^[EGC]-\d+$", "table": "people", "key": "id", "identify": ["name", "kind", "role"],
               "context": {"badges": ["badges", "holder_id", "id", "badge_id"],
                           "accounts": ["accounts", "phone", "phone", "account_id"]}},
    "Room": {"match": r"^R\d{2}$", "table": "rooms", "key": "room_id", "identify": ["name", "wing"],
             "context": {"doors": ["doors", "room_a", "room_id", "door_id"], "more_doors": ["doors", "room_b", "room_id", "door_id"]}},
    "Door": {"match": r"^D\d{2}$", "table": "doors", "key": "door_id", "identify": ["room_a", "room_b", "reader", "kind"],
             "context": {}},
    "Badge": {"match": r"^B-\d+$", "table": "badges", "key": "badge_id", "identify": ["holder_id", "zones"], "context": {}},
}  # fmt: skip


def rules_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node(("action", "accuse"), kind="action")
    for rule in RULEBOOK:
        node = ("rule", rule["id"])
        g.add_node(node, kind="rule", text=rule["rule"], owner="chief", version=1)
        g.add_edge(node, ("action", "accuse"), type="GOVERNS")
    return g


def rules_for(graph: nx.DiGraph, action: str) -> list[str]:
    target = ("action", action)
    if target not in graph:
        return []
    return sorted(u[1] for u, _, d in graph.in_edges(target, data=True) if d["type"] == "GOVERNS")


def rule_text(graph: nx.DiGraph, rule_id: str) -> str:
    return graph.nodes[("rule", rule_id)]["text"]


def update_rule(graph: nx.DiGraph, rule_id: str, text: str, actor: str) -> bool:
    node = graph.nodes.get(("rule", rule_id))
    if node is None or actor != node["owner"]:
        return False  # the guardrail lives here, in code: no prompt can talk its way past it
    node["text"], node["version"] = text, node["version"] + 1
    return True


def describe(case: Case, node_id: str, spec: dict = SPEC) -> dict:
    tables = records(case)
    for type_name, t in spec.items():
        if not re.match(t["match"], node_id):
            continue
        record = next((r for r in tables[t["table"]] if str(r[t["key"]]) == node_id), None)
        if record is None:
            return {"error": f"no {type_name} {node_id!r}"}
        context = {rel: sorted(str(r[out]) for r in tables[table] if r[theirs] == record[ours])
                   for rel, (table, theirs, ours, out) in t["context"].items()}  # fmt: skip
        return {"type": type_name, "id": node_id, **{f: record[f] for f in t["identify"]}, "context": context}
    return {"error": f"no kind of record matches {node_id!r}"}


SYSTEM = """You are a detective investigating a theft at a museum gala. Every desk tool costs minutes from a
limited budget. Read the chief's rules with `read_rules` before you accuse: a warrant is signed only if your
evidence follows them. Use `describe` (free) to look up any id: a person, a room, a door, a badge.
Witnesses can be wrong or lie: check what they say against the logs before you rely on it."""


def investigate(case: Case, llm: Any, distract: bool = False) -> Precinct:
    desk = Precinct(case, distract=distract)
    graph = rules_graph()
    extra = [
        {"name": "read_rules", "description": "The chief's rules for an accusation, from the rulebook graph. Free.",
         "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
        {"name": "describe", "description": "Look up any record by id: person, room, door or badge. Free.",
         "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"],
                        "additionalProperties": False}},
    ]  # fmt: skip

    def run(name: str, args: dict) -> Any:
        if name == "read_rules":
            return [{"id": r, "rule": rule_text(graph, r)} for r in rules_for(graph, "accuse")]
        if name == "describe":
            return describe(case, str(args.get("id", "")))
        return desk.call(name, args)

    tools = [t for t in desk.tools() if t["name"] != "rulebook"] + extra
    convo = Conversation(llm, tools, system=SYSTEM)
    turn = convo.send("A painting was stolen tonight. Work the case and accuse whoever did it.")
    for _ in range(40):
        if turn.done or desk.accusation is not None:
            break
        results = {c.id: run(c.name, c.arguments) for c in turn.tool_calls}
        if desk.accusation is not None:
            break
        turn = convo.reply({k: v if isinstance(v, str) else json.dumps(v) for k, v in results.items()},
                           errors={k for k, v in results.items() if isinstance(v, dict) and "error" in v})  # fmt: skip
    return desk
