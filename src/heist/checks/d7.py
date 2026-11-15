"""Checks for detective 7, budget and clearance."""

from __future__ import annotations

import math
from types import ModuleType

from ..case import load_case
from ..precinct import Precinct, records
from .core import NotStarted, Result, attempt, tally

L_ROUTING = ("agentic-graphrag", "model-routing", "Model routing for agents")
L_ACCESS = ("agentic-graphrag", "knowledge-graph-access-control", "Knowledge graph access control")


def run(module: ModuleType) -> list[Result]:
    routing = Result("The cheapest model that's good enough", L_ROUTING)
    cost = Result("Cost per solved case", L_ROUTING)
    access = Result("Restricted records are invisible", L_ACCESS)
    audited = Result("An auditor's question, answered from the logs", L_ACCESS)
    erased = Result("Personal data, erased on request", L_ACCESS)
    try:
        models = {"small": (0.7, 1.0), "medium": (0.85, 4.0), "large": (0.95, 15.0)}
        bars = {"plan": 0.9, "extract": 0.6, "decide": 0.8}
        fixtures = [(("plan", bars, models), "large"), (("extract", bars, models), "small"),
                    (("decide", bars, models), "medium"), (("chat", bars, models), "small"),
                    (("plan", {"plan": 0.99}, models), "large")]  # fmt: skip
        right = sum(attempt(routing, module.route_model, *args) == want for args, want in fixtures)
        tally(routing, right, len(fixtures), "steps")
    except NotStarted:
        routing.started = routing.passed = False
    try:
        fixtures = [([(2.0, True), (3.0, False), (1.0, True)], 3.0), ([(1.0, False)], math.inf), ([], math.inf)]
        right = 0
        for runs, want in fixtures:
            got = attempt(cost, module.cost_per_solved, runs)
            right += got == want
            if got != want:
                cost.fail(f"cost_per_solved({runs}) = {got}, want {want}")
        tally(cost, right, len(fixtures), "fixtures")
    except NotStarted:
        cost.started = cost.passed = False
    case = load_case("practice/case-01")
    person = case.staff[0].employee_id
    try:
        right = total = 0
        junior = attempt(access, module.restricted, Precinct(case), "junior")
        senior = attempt(access, module.restricted, Precinct(case), "senior")
        if junior is not None and senior is not None:
            names = {t["name"] for t in junior.tools()}
            total += 1
            right += not ({"bank_records", "phone_records"} & names) and "keycard_log" in names
            unknown = Precinct(case).call("teleport", {})["error"].replace("'teleport'", "'bank_records'")
            total += 1
            right += junior.call("bank_records", {"person": person}) == {"error": unknown}
            total += 1
            right += isinstance(senior.call("phone_records", {"person": person}), list)
            if right < total:
                access.fail("a junior desk must not list bank or phone records, must fail on them exactly like an "
                            "unknown tool, and a senior desk must still have them")  # fmt: skip
        tally(access, right, total or 1, "checks")
    except NotStarted:
        access.started = access.passed = False
    try:
        a, b = Precinct(case), Precinct(load_case("practice/case-02"))
        other = case.staff[1].employee_id
        a.call("interview", {"person": person})
        a.call("phone_records", {"person": other})
        a.call("bank_records", {"person": person})
        b.call("phone_records", {"person": person})
        a.call("interview", {"person": "nobody"})
        want = [(case.id, 1, "interview"), (case.id, 3, "bank_records")]
        got = attempt(audited, module.audit, [a, b], person)
        ok = got == want
        if not ok:
            audited.fail(f"audit = {got}, want {want}")
        tally(audited, int(ok), 1, "questions")
    except NotStarted:
        audited.started = audited.passed = False
    try:
        people = records(case)["people"]
        got = attempt(erased, module.erase, people, person)
        want = [{"id": p["id"], "kind": p["kind"]} if p["id"] == person else p for p in people]
        ok = got == want
        if not ok:
            erased.fail("only this person's row loses its personal data: id and kind stay, the rest goes")
        tally(erased, int(ok), 1, "tables")
    except NotStarted:
        erased.started = erased.passed = False
    return [routing, cost, access, audited, erased]
