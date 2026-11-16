"""Checks for detective 4, the investigation plan."""

from __future__ import annotations

from types import ModuleType

from ..case import list_cases, load_case
from ..llm import LLMError
from ..precinct import Precinct, cited_sources
from .core import NotStarted, Result, attempt, model_for, tally

L_RELIABLE = ("agentic-graphrag", "agent-reliability", "Agent reliability")
L_WORKFLOW = ("agentic-graphrag", "agent-workflow-graph", "Agent workflow graphs")
L_OUTPUT = ("agentic-graphrag", "structured-output", "Structured output for agents")
L_PLANNING = ("agentic-graphrag", "agent-planning", "Agent planning")
DESK_TOOLS = {"briefing", "rulebook", "list_people", "floor_plan", "documents", "read_document", "keycard_log",
              "camera_log", "phone_records", "bank_records", "interview", "board", "accuse"}  # fmt: skip


def official_phases(steps):
    done, left, out = set(), {s["id"]: set(s["needs"]) for s in steps}, []
    while left:
        ready = sorted(i for i, needs in left.items() if needs <= done)
        if not ready:
            return None
        out.append(ready)
        done |= set(ready)
        for i in ready:
            del left[i]
    return out


def run(module: ModuleType) -> list[Result]:
    compound = Result("Small errors compound", L_RELIABLE)
    plan = Result("A plan that's a workflow graph", L_PLANNING)
    phased = Result("Phases that can run in parallel", L_WORKFLOW)
    meaning = Result("Meaning checks before the warrant", L_OUTPUT)
    agent = Result("The planned investigation", L_WORKFLOW)
    for check, r in ((_compound, compound), (_plan, plan), (_phases, phased), (_meaning, meaning)):
        try:
            check(module, r)
        except NotStarted:
            r.started = r.passed = False
    _agent(module, agent)
    return [compound, plan, phased, meaning, agent]


def _compound(module, r: Result) -> None:
    right = 0
    fixtures = [((0.95, 20), 0.95**20), ((0.99, 100), 0.99**100), ((1.0, 50), 1.0), ((0.9, 1), 0.9)]
    for args, want in fixtures:
        got = attempt(r, module.compound_success, *args)
        ok = got is not None and abs(got - want) < 1e-9
        right += ok
        if not ok:
            r.fail(f"compound_success{args} = {got}, want {want:.4f}")
    tally(r, right, len(fixtures), "fixtures")


def _plan(module, r: Result) -> None:
    steps = attempt(r, module.plan, load_case("practice/case-01"))
    if steps is None:
        return
    ids = [s.get("id") for s in steps]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("two steps share an id")
    if any(n not in ids for s in steps for n in s.get("needs", [])):
        problems.append("a step needs a step that doesn't exist")
    if official_phases(steps) is None:
        problems.append("the plan has a cycle")
    kinds = {s.get("kind") for s in steps}
    if not {"reasoning", "execution", "decision", "validation"} <= kinds:
        problems.append(
            f"missing kinds of step: {sorted({'reasoning', 'execution', 'decision', 'validation'} - kinds)}"
        )
    for s in steps:
        tools = s.get("tools", [])
        if s.get("kind") != "execution" and tools:
            problems.append(f"{s['id']}: only execution steps hold tools")
        if len(tools) > 2:
            problems.append(f"{s['id']}: {len(tools)} tools; keep execution nodes narrow (two at most)")
        if set(tools) - DESK_TOOLS:
            problems.append(f"{s['id']}: unknown tools {sorted(set(tools) - DESK_TOOLS)}")
    if not any(s.get("kind") == "execution" and "board" in s.get("tools", []) for s in steps):
        problems.append("no execution step asks the evidence board: who was where, and who called whom, are "
                        "questions for the graph (the board tool)")  # fmt: skip
    for p in problems:
        r.fail(p)
    r.score = f"{len(steps)} steps, {len(problems)} problems"


def _phases(module, r: Result) -> None:
    fixtures = [
        [
            {"id": "a", "needs": []},
            {"id": "b", "needs": ["a"]},
            {"id": "c", "needs": ["a"]},
            {"id": "d", "needs": ["b", "c"]},
        ],
        [{"id": "x", "needs": []}, {"id": "y", "needs": []}, {"id": "z", "needs": []}],
        [{"id": "s3", "needs": ["s2"]}, {"id": "s2", "needs": ["s1"]}, {"id": "s1", "needs": []}],
    ]
    try:
        mine = attempt(r, module.plan, load_case("practice/case-01"))
        if mine and official_phases(mine) is not None:
            fixtures.append(mine)
    except NotStarted:
        pass
    right = 0
    for steps in fixtures:
        got = attempt(r, module.phases, steps)
        want = official_phases(steps)
        right += got == want
        if got != want:
            r.fail(f"phases of {[s['id'] for s in steps]}: {got}, want {want}")
    tally(r, right, len(fixtures), "plans")


def official_problems(desk: Precinct, acc: dict) -> list[str]:
    order = ("unknown-person", "same-person", "bad-method", "too-few-sources", "unconsulted-source",
             "no-unguarded-door", "no-badge")  # fmt: skip
    people = {p["id"] for p in desk._list_people()}
    found = set()
    c, a = acc.get("culprit"), acc.get("accomplice") or None
    if c not in people or (a and a not in people):
        found.add("unknown-person")
    if a and a == c:
        found.add("same-person")
    if acc.get("method") not in ("insider", "borrowed_badge", "fire_door"):
        found.add("bad-method")
    cited = cited_sources(acc.get("evidence", []))
    if len(cited) < 2:
        found.add("too-few-sources")
    if cited - desk.consulted():
        found.add("unconsulted-source")
    if acc.get("method") == "fire_door":
        inside = {x.room_id for x in desk.case.rooms if x.wing == desk.case.meta["room"]["wing"]}
        if not any(not d.has_reader and (d.room_a in inside) != (d.room_b in inside) for d in desk.case.doors):
            found.add("no-unguarded-door")
    if acc.get("method") == "insider" and not any(b.holder_id == c for b in desk.case.badges):
        found.add("no-badge")
    return [p for p in order if p in found]


def _meaning(module, r: Result) -> None:
    right = total = 0
    for name in ("practice/case-01", "hard/case-01"):
        case = load_case(name)
        desk = Precinct(case)
        desk.call("camera_log", {"start": "22:00", "end": "23:00"})
        desk.call("keycard_log", {"room": "R34", "start": "22:00", "end": "22:30"})
        staff = [s.employee_id for s in case.staff]
        guest = case.guests[0].guest_id
        both = ["the camera log shows the cameras went dark", "the keycard log puts them in the Security Office"]
        fixtures = [
            {"culprit": staff[0], "accomplice": staff[1], "method": "insider", "evidence": both},
            {"culprit": "E-0000", "accomplice": staff[1], "method": "insider", "evidence": both},
            {"culprit": staff[0], "accomplice": staff[0], "method": "teleport", "evidence": both},
            {"culprit": staff[0], "accomplice": "", "method": "insider", "evidence": ["the camera log"]},
            {
                "culprit": staff[0],
                "accomplice": "",
                "method": "insider",
                "evidence": ["the camera log", "bank transfers"],
            },
            {"culprit": guest, "accomplice": staff[1], "method": "insider", "evidence": both},
            {"culprit": guest, "accomplice": staff[1], "method": "fire_door", "evidence": both},
        ]
        for acc in fixtures:
            total += 1
            got = attempt(r, module.validate_accusation, desk, acc)
            want = official_problems(desk, acc)
            right += got == want
            if got != want and got is not None:
                r.fail(f"{name} · {acc['culprit']}/{acc['method']}/{len(acc['evidence'])} lines: {got}, want {want}")
    tally(r, right, total, "accusations")


def _agent(module, r: Result) -> None:
    llm = model_for(r)
    if llm is None:
        return
    from ..board import reachable

    trouble = reachable()
    if trouble:
        r.started = r.passed = False
        r.notes.append(trouble)
        return
    try:
        accused = warrants = solved = calls = 0
        refused = []
        for name in list_cases("practice"):
            desk = attempt(r, module.investigate, load_case(name), llm)
            if desk is None:
                continue
            verdict = desk.verdict()
            accused += desk.accusation is not None
            warrants += verdict["warrant"]
            solved += verdict["solved"]
            calls += len(desk.log)
            if desk.accusation is not None and not verdict["warrant"]:
                refused.append(f"{name}: the chief refused the warrant: {verdict['reason']}")
        r.score = f"{accused}/3 accused, {warrants} warrants, {solved} solved, {calls} desk calls"
        if accused < 3:
            r.fail("Every practice run must end in an accusation.")
        elif warrants < accused:
            r.fail(
                "An accusation reached the chief with a problem your checks are there to stop. Leave the model less "
                "to get wrong: the people's ids as an enum in the schema, and in code, drop evidence that cites a "
                "source you never consulted."
            )
            r.details.extend(refused)
    except NotStarted:
        return
    except LLMError as e:
        r.fail(f"the LLM call failed: {e}")
