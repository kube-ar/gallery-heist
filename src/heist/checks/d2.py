"""Checks for detective 2, the rulebook."""

from __future__ import annotations

import re
from types import ModuleType

from ..case import list_cases, load_case
from ..precinct import RULEBOOK, records
from .core import NotStarted, Result, attempt, tally

L_RULES = ("agentic-graphrag", "business-rules-in-the-graph", "Business rules in the knowledge graph")
L_ONTO = ("agentic-graphrag", "ontology-driven-retrieval", "Ontology-driven retrieval")
L_DISTRACT = ("agentic-graphrag", "distracting-effect", "The distracting effect")

EXTRA = {
    "Camera": {"match": r"^C\d{2}$", "table": "cameras", "key": "camera_id", "identify": ["room_id"], "context": {}},
    "Account": {
        "match": r"^ACC-\d+$",
        "table": "accounts",
        "key": "account_id",
        "identify": ["holder", "phone"],
        "context": {},
    },
}


def official_describe(case, node_id: str, spec: dict) -> dict:
    tables = records(case)
    for type_name, t in spec.items():
        if not re.match(t["match"], node_id):
            continue
        record = next((r for r in tables[t["table"]] if str(r[t["key"]]) == node_id), None)
        if record is None:
            return {"error": "unknown"}
        context = {rel: sorted(str(r[out]) for r in tables[table] if r[theirs] == record[ours])
                   for rel, (table, theirs, ours, out) in t["context"].items()}  # fmt: skip
        return {"type": type_name, "id": node_id, **{f: record[f] for f in t["identify"]}, "context": context}
    return {"error": "unknown"}


def run(module: ModuleType) -> list[Result]:
    rules = Result("Rules live in the graph, with an owner", L_RULES)
    onto = Result("One tool for every kind of record", L_ONTO)
    agent = Result("The detective, distracted and not", L_DISTRACT)
    for check, r in ((_rules, rules), (_describe, onto)):
        try:
            check(module, r)
        except NotStarted:
            r.started = r.passed = False
    _agent(module, agent)
    return [rules, onto, agent]


def _rules(module, r: Result) -> None:
    g = attempt(r, module.rules_graph)
    if g is None:
        return
    right = total = 0
    every = sorted(rule["id"] for rule in RULEBOOK)
    for action, want in (("accuse", every), ("interview", [])):
        total += 1
        got = attempt(r, module.rules_for, g, action)
        right += got == want
        if got != want:
            r.fail(f"rules_for({action!r}) = {got}, want {want}")
    before = attempt(r, module.rule_text, g, "R2")
    total += 2
    refused = attempt(r, module.update_rule, g, "R2", "One source is enough.", "agent")
    unchanged = attempt(r, module.rule_text, g, "R2") == before
    right += refused is False and unchanged
    if not (refused is False and unchanged):
        r.fail("the agent changed rule R2: only its owner, the chief, may")
    allowed = attempt(r, module.update_rule, g, "R2", "Cite three kinds of source.", "chief")
    changed = attempt(r, module.rule_text, g, "R2") == "Cite three kinds of source."
    right += allowed is True and changed
    if not (allowed is True and changed):
        r.fail("the chief couldn't change rule R2")
    tally(r, right, total, "answers")


def _describe(module, r: Result) -> None:
    spec = dict(module.SPEC)
    right = total = 0
    for name in ("practice/case-01", "medium/case-01"):
        case = load_case(name)
        tables = records(case)
        ids = [
            tables["people"][0]["id"],
            tables["people"][-1]["id"],
            "R11",
            "R13",
            "D12",
            tables["badges"][0]["badge_id"],
            "X-404",
        ]
        for node_id in ids:
            total += 1
            got = attempt(r, module.describe, case, node_id, spec)
            want = official_describe(case, node_id, spec)
            ok = (got or {}).get("error") is not None if "error" in want else got == want
            right += ok
            if not ok and got is not None:
                r.fail(f"{name} · describe({node_id!r}): {got}")
        bigger = {**spec, **EXTRA}
        for node_id in ("C03", tables["accounts"][0]["account_id"]):
            total += 1
            got = attempt(r, module.describe, case, node_id, bigger)
            ok = got == official_describe(case, node_id, bigger)
            right += ok
            if not ok and got is not None:
                r.fail(f"{name} · a new kind of record, {node_id!r}: {got} (add it to the spec, change no code)")
    tally(r, right, total, "records")


def _agent(module, r: Result) -> None:
    from ..llm import LLMError, get_llm

    try:
        llm = get_llm()
    except LLMError as e:
        r.started = r.passed = False
        r.notes.append(f"Needs an LLM: {e}. Then run `uv run heist llm`.")
        return
    try:
        for distract in (False, True):
            solved = fooled = accused = 0
            for name in list_cases("practice"):
                desk = attempt(r, module.investigate, load_case(name), llm, distract)
                if desk is None:
                    continue
                v = desk.verdict()
                accused += desk.accusation is not None
                solved += v["solved"]
                planted = desk.distraction()
                fooled += bool(planted and desk.accusation and desk.accusation["culprit"] == planted["about"])
            r.notes.append(
                f"{'distracted' if distract else 'plain'}: {accused}/3 accused, {solved} solved, fooled {fooled}"
            )
            if accused < 3:
                r.fail(f"{'distracted' if distract else 'plain'} runs must each end in an accusation")
    except NotStarted:
        return
    except LLMError as e:
        r.fail(f"the LLM call failed: {e}")
