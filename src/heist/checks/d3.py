"""Checks for detective 3, the notebook."""

from __future__ import annotations

from types import ModuleType

from .. import answers
from ..case import Case, list_cases, load_case
from ..llm import LLMError
from ..precinct import Precinct, extract_facts
from .core import NotStarted, Result, attempt, model_for, tally

L_MEMORY = ("agentic-graphrag", "graph-memory", "Graph memory")
L_RETRIEVAL = ("agentic-graphrag", "memory-retrieval", "Memory retrieval")
L_CONTEXT = ("agentic-graphrag", "context-graph", "Context graph")
L_WHY = ("agentic-graphrag", "agent-memory", "Agent memory")


def _m(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return (h + (24 if h < 12 else 0)) * 60 + m


def stream(case: Case) -> list[tuple[dict, int]]:
    """A scripted investigation: every statement first, then the whole keycard log, learned later."""
    desk = Precinct(case)
    people = {p["name"]: p["id"] for p in desk._list_people()}
    out, minute = [], 0
    for doc in case.documents:
        if doc.kind == "statement" and doc.author in people:
            minute += 20
            pid = people[doc.author]
            out += [(f, minute) for f in extract_facts(case, "interview", {"person": pid}, doc.text)]
    holder = {b.badge_id: b.holder_id for b in case.badges}
    rows = [{"time": f"{s.time:%H:%M}", "holder": holder.get(s.badge_id), "to_room": s.to_room,
             "result": "granted" if s.granted else "denied"} for s in case.swipes]  # fmt: skip
    minute = 500
    out += [(f, minute) for f in extract_facts(case, "keycard_log", {}, rows)]
    return out


def official_believed(facts, person, at, as_of=None):
    t = _m(at)
    mine = [(f, w) for f, w in facts if f["person"] == person and (as_of is None or w <= as_of)]
    seen = [(f, w) for f, w in mine if f["kind"] == "observed" and _m(f["at"]) <= t]
    if seen:
        return max(seen, key=lambda x: (_m(x[0]["at"]), x[1]))[0]["room"]
    said = [(f, w) for f, w in mine if f["kind"] == "claimed" and 0 <= t - _m(f["at"]) <= 60]
    if said:
        return max(said, key=lambda x: (_m(x[0]["at"]), x[1]))[0]["room"]
    return None


def official_conflicts(facts, case) -> set[tuple]:
    region = answers.regions(case)
    out = set()
    for person in {f["person"] for f, _ in facts}:
        seen = sorted(
            (f for f, _ in facts if f["person"] == person and f["kind"] == "observed"), key=lambda f: _m(f["at"])
        )
        for c in (f for f, _ in facts if f["person"] == person and f["kind"] == "claimed"):
            t = _m(c["at"])
            spans = [f for f in seen if _m(f["at"]) <= t - 10][-1:] + [
                f for f in seen if t - 10 < _m(f["at"]) <= t + 10
            ]
            if spans and all(c["room"] not in region[f["room"]] for f in spans):
                out.add((person, c["room"], c["at"]))
    return out


def run(module: ModuleType) -> list[Result]:
    belief = Result("What the notebook believes, and when", L_MEMORY)
    clash = Result("Claims the logs rule out", L_CONTEXT)
    past = Result("A person's history", L_WHY)
    fused = Result("Reciprocal rank fusion", L_RETRIEVAL)
    agent = Result("The detective with a notebook", L_MEMORY)
    try:
        for name in ("practice/case-01", "medium/case-01"):
            case = load_case(name)
            facts = stream(case)
            nb = attempt(belief, module.new_notebook)
            if nb is None:
                continue
            for f, w in facts:
                attempt(belief, module.remember, nb, dict(f), w)
            _belief(module, nb, case, facts, belief)
            _clash(module, nb, case, facts, clash)
            _history(module, nb, facts, past)
    except NotStarted:
        for r in (belief, clash, past):
            if not r.details:
                r.started = r.passed = False
    try:
        _rrf(module, fused)
    except NotStarted:
        fused.started = fused.passed = False
    _agent(module, agent)
    return [belief, clash, past, fused, agent]


def _count(r: Result, ok: bool, unit: str) -> None:
    r.__dict__["right"] = r.__dict__.get("right", 0) + ok
    r.__dict__["total"] = r.__dict__.get("total", 0) + 1
    tally(r, r.__dict__["right"], r.__dict__["total"], unit)


def _belief(module, nb, case, facts, r: Result) -> None:
    claims = [f for f, _ in facts if f["kind"] == "claimed"]
    for f in claims:
        for as_of in (None, 499):
            got = attempt(r, module.believed_at, nb, f["person"], f["at"], as_of, none_ok=True)
            want = official_believed(facts, f["person"], f["at"], as_of)
            ok = got == want
            if not ok and len(r.details) < 4:
                r.details.append(
                    f"{case.id} · believed_at({f['person']}, {f['at']}, as_of={as_of}): {got}, want {want}"
                )
            _count(r, ok, "questions")


def _clash(module, nb, case, facts, r: Result) -> None:
    got = attempt(r, module.conflicts, nb, case)
    want = official_conflicts(facts, case)
    have = {(c["person"], c["room"], c["at"]) for c in got or []}
    ok = have == want
    if not ok and got is not None:
        missed, extra = sorted(want - have, key=str), sorted(have - want, key=str)
        r.fail(f"{case.id}: missed {len(missed)}, flagged {len(extra)} that the logs allow")
        for label, rows in (("missed", missed), ("flagged", extra)):
            for person, room, at in rows[:2]:
                r.details.append(f"    {label}: {person} claims {room} at {at}")
    _count(r, ok, "cases")


def _history(module, nb, facts, r: Result) -> None:
    people = sorted({f["person"] for f, _ in facts if f["kind"] == "claimed"})[:3]
    for person in people:
        mine = sorted(((f, w) for f, w in facts if f["person"] == person),
                      key=lambda x: (_m(x[0]["at"]), x[0]["kind"] != "observed", x[1]))  # fmt: skip
        want = [
            {"room": f["room"], "at": f["at"], "kind": f["kind"], "source": f["source"], "learned_at": w}
            for f, w in mine
        ]
        got = attempt(r, module.history, nb, person)
        ok = got == want
        if not ok and got is not None and len(r.details) < 3:
            r.details.append(f"history({person}): {len(got)} facts, want {len(want)} in valid-time order")
        _count(r, ok, "people")


def _rrf(module, r: Result) -> None:
    a, b, c = 1 / 61 + 1 / 62, 1 / 63, 1.0
    fixtures = [
        (([["a", "b", "c"], ["b", "a", "d"]], 60), [("a", a), ("b", a), ("c", b), ("d", b)]),
        (([["x"], ["x", "y"]], 1), [("x", c), ("y", 1 / 3)]),
        (([], 60), []),
    ]
    right = 0
    for (rankings, k), want in fixtures:
        got = attempt(r, module.rrf, rankings, k)
        ok = (
            got is not None
            and [x for x, _ in got] == [x for x, _ in want]
            and all(abs(s - t) < 1e-9 for (_, s), (_, t) in zip(got, want, strict=False))
        )
        right += ok
        if not ok:
            r.fail(f"rrf({rankings}, k={k}) = {got}, want {want}")
    tally(r, right, len(fixtures), "fixtures")


def _agent(module, r: Result) -> None:
    llm = model_for(r)
    if llm is None:
        return
    try:
        accused = solved = 0
        for name in list_cases("practice"):
            desk = attempt(r, module.investigate, load_case(name), llm)
            if desk is None:
                continue
            accused += desk.accusation is not None
            solved += desk.verdict()["solved"]
        r.score = f"{accused}/3 accused, {solved} solved"
        if accused < 3:
            r.fail("Every practice run must end in an accusation.")
    except NotStarted:
        return
    except LLMError as e:
        r.fail(f"the LLM call failed: {e}")
