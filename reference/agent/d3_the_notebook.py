"""Detective 3 · The notebook: a reference solution. Spoilers: `heist use-reference d3` copies it."""

from __future__ import annotations

import json
from typing import Any

import networkx as nx

from heist.case import Case
from heist.llm import Conversation
from heist.precinct import Precinct, extract_facts


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return (h + (24 if h < 12 else 0)) * 60 + m


def new_notebook() -> nx.MultiDiGraph:
    return nx.MultiDiGraph()


def remember(nb: nx.MultiDiGraph, fact: dict, learned_at: int) -> str:
    """Fact nodes hang off person and room nodes; valid time and record time are both on the fact."""
    fid = f"f{nb.number_of_nodes()}"
    nb.add_node(fid, node="fact", **fact, learned_at=learned_at)
    nb.add_edge(("person", fact["person"]), fid, type="ABOUT")
    nb.add_edge(fid, ("room", fact["room"]), type="IN")
    return fid


def _facts(nb, person: str, as_of: int | None = None) -> list[dict]:
    out = [nb.nodes[f] for _, f in nb.out_edges(("person", person))] if ("person", person) in nb else []
    return [f for f in out if as_of is None or f["learned_at"] <= as_of]


def believed_at(nb, person: str, at: str, as_of: int | None = None) -> str | None:
    t = _minutes(at)
    facts = _facts(nb, person, as_of)
    seen = [f for f in facts if f["kind"] == "observed" and _minutes(f["at"]) <= t]
    if seen:
        return max(seen, key=lambda f: (_minutes(f["at"]), f["learned_at"]))["room"]
    said = [f for f in facts if f["kind"] == "claimed" and 0 <= t - _minutes(f["at"]) <= 60]
    if said:
        return max(said, key=lambda f: (_minutes(f["at"]), f["learned_at"]))["room"]
    return None


def _regions(case: Case) -> dict[str, set[str]]:
    links: dict[str, set[str]] = {}
    for d in case.doors:
        if not d.has_reader:
            links.setdefault(d.room_a, set()).add(d.room_b)
            links.setdefault(d.room_b, set()).add(d.room_a)
    out = {}
    for r in case.rooms:
        seen, stack = {r.room_id}, [r.room_id]
        while stack:
            for nxt in links.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        out[r.room_id] = seen
    return out


def conflicts(nb, case: Case) -> list[dict]:
    region = _regions(case)
    out = []
    people = {n[1] for n in nb.nodes if isinstance(n, tuple) and n[0] == "person"}
    for person in sorted(people):
        facts = _facts(nb, person)
        seen = sorted((f for f in facts if f["kind"] == "observed"), key=lambda f: _minutes(f["at"]))
        for c in (f for f in facts if f["kind"] == "claimed"):
            t = _minutes(c["at"])
            before = [f for f in seen if _minutes(f["at"]) <= t - 10]
            during = [f for f in seen if t - 10 < _minutes(f["at"]) <= t + 10]
            spans = before[-1:] + during
            if spans and all(c["room"] not in region[f["room"]] for f in spans):
                out.append({"person": person, "room": c["room"], "at": c["at"]})
    return out


def history(nb, person: str) -> list[dict]:
    facts = sorted(_facts(nb, person), key=lambda f: (_minutes(f["at"]), f["kind"] != "observed", f["learned_at"]))
    return [{k: f[k] for k in ("room", "at", "kind", "source", "learned_at")} for f in facts]


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


SYSTEM = """You are a detective investigating a theft at a museum gala. Every desk tool costs minutes.
Your notebook remembers every fact from the logs and the statements, with when it was true and when you
learned it. Ask it before you ask the desk again: `believed_at` says where you believe someone was, and
`conflicts` lists the statements the logs rule out. A contradicted statement is a lead, not a fact."""


def investigate(case: Case, llm: Any) -> Precinct:
    desk = Precinct(case)
    nb = new_notebook()
    extra = [
        {"name": "believed_at", "description": "Where your notebook places a person at a time (HH:MM). Free.",
         "parameters": {"type": "object", "properties": {"person": {"type": "string"}, "at": {"type": "string"}},
                        "required": ["person", "at"], "additionalProperties": False}},
        {"name": "conflicts", "description": "Statements the logs you've read rule out. Free.",
         "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    ]  # fmt: skip

    def run(name: str, args: dict) -> Any:
        if name == "believed_at":
            return {"room": believed_at(nb, str(args.get("person")), str(args.get("at", "00:00")))}
        if name == "conflicts":
            return conflicts(nb, case)
        result = desk.call(name, args)
        for fact in extract_facts(case, name, args, result):
            remember(nb, fact, desk.spent)
        return result

    convo = Conversation(llm, desk.tools() + extra, system=SYSTEM)
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
