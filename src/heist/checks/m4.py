"""Checks for milestone 4, ask the board."""

from __future__ import annotations

import json
from datetime import timedelta
from types import ModuleType

import networkx as nx

from .. import answers
from ..case import Case, list_cases, load_case
from .core import NotStarted, Result, attempt, tally

L_DB = ("graphrag", "choosing-a-graph-database", "Graph database or PostgreSQL?")
L_PATTERNS = ("graphrag", "graph-retrieval-patterns", "GraphRAG retrieval patterns")
L_GLOBAL = ("graphrag", "global-search", "GraphRAG global search")
L_METHODS = ("graphrag", "graphrag-methods-compared", "GraphRAG methods compared")

BAD_QUERIES = [
    "MATCH (n) DETACH DELETE n",
    "MATCH (p:Person) SET p.name = 'nobody' RETURN p LIMIT 10",
    "CREATE (x:Person {id: 'X-1'}) RETURN x LIMIT 1",
    "MATCH (p:Person) RETURN p",
    "MATCH (p:Person) RETURN p LIMIT 100000",
    "MATCH (s:Spaceship) RETURN s LIMIT 5",
    "MATCH (p:Person)-[:OWNS_YACHT]->(y) RETURN p LIMIT 5",
    "CALL dbms.components() YIELD name RETURN name LIMIT 1",
    "LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row LIMIT 1",
]

ROUTES = {
    "template": [
        "Who was in the east wing between 22:10 and 23:45?",
        "Who was in the service wing between 20:30 and 21:00?",
        "Which doors into the west wing log nothing?",
        "Who called E-1342 on the gala night?",
        "Who phoned the head of security that evening?",
    ],
    "search": [
        "Which statements mention Nadia Jessop?",
        "What did the conservator say about the Restoration Lab?",
        "Who said they saw a waiter near the kitchen?",
        "According to the incident report, when was the painting last seen?",
        "What does the press clipping say about the director?",
    ],
    "generated": [
        "Which badge swiped the most times at door D07?",
        "How many transfers were larger than 1000?",
        "Which room had the most swipes after 22:00?",
        "How many calls lasted more than five minutes?",
        "Which guest sat at the same table as the director?",
    ],
    "global": [
        "What do the statements say overall about money trouble?",
        "Across all the documents, which themes come up most?",
        "Summarize what everyone says about the evening.",
        "Overall, which people are mentioned as being near the galleries?",
        "What do all the statements together say about the guards?",
    ],
}


def cases() -> list[Case]:
    """Loading a case takes a few seconds, so the checks use the practice and medium packs."""
    return [load_case(n) for pack in ("practice", "medium") for n in list_cases(pack)]


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans, offset = [], 0
    for p in [p.strip() for p in text.split("\n\n") if p.strip()]:
        start = text.index(p, offset)
        spans.append((start, start + len(p)))
        offset = start + len(p)
    return spans


def run(module: ModuleType) -> list[Result]:
    stored = Result("The case is in your store", L_DB)
    templates = Result("Expert templates answer exactly", L_PATTERNS)
    guard = Result("Model-written queries are checked first", L_PATTERNS)
    search = Result("Search finds who the statements mention", L_PATTERNS)
    routes = Result("Each question takes the right route", L_PATTERNS)
    groups = Result("Communities in the people graph", L_GLOBAL)
    generated = Result("Model-written queries answer", L_METHODS)
    global_q = Result("A question about everything", L_GLOBAL)
    results = [stored, templates, guard, search, routes, groups, generated, global_q]

    _validator(module, guard)
    _routes(module, routes)
    for case in cases():
        try:
            board = attempt(stored, module.store, case)
        except NotStarted:
            for r in (templates, search, groups, generated, global_q):
                r.started = r.passed = False
            break
        if board is None:
            continue
        for check, r in ((_summary, stored), (_templates, templates), (_search, search), (_communities, groups)):
            if r.started:
                try:
                    check(module, case, board, r)
                except NotStarted:
                    r.started = r.passed = False
        if case.id == "practice/case-01":
            try:
                _llm_checks(module, case, board, generated, global_q)
            except NotStarted:
                pass
    return results


def _counter(r: Result, ok: bool) -> None:
    r.__dict__.setdefault("right", 0)
    r.__dict__.setdefault("total", 0)
    r.__dict__["total"] += 1
    r.__dict__["right"] += ok
    tally(r, r.__dict__["right"], r.__dict__["total"], r.__dict__.get("unit", "answers"))


def _summary(module, case: Case, board, r: Result) -> None:
    r.__dict__["unit"] = "cases"
    got = attempt(r, module.store_summary, board)
    if got is None:
        return _counter(r, False)
    want = {k: v for k, v in answers.counts(case).items() if k in ("people", "badges", "rooms", "doors", "swipes",
                                                                    "calls", "transfers")}  # fmt: skip
    want["documents"] = len(case.documents)
    want["chunks"] = sum(len(_paragraph_spans(d.text)) for d in case.documents)
    wrong = [f"{k}: {got.get(k, 'missing')} (want {v})" for k, v in want.items() if got.get(k) != v]
    if wrong:
        r.fail(f"{case.id}: " + ", ".join(wrong))
    _counter(r, not wrong)


def _templates(module, case: Case, board, r: Result) -> None:
    night = (case.at("17:00"), case.at("17:00") + timedelta(hours=9))
    for q in case.meta["questions"]["who_was_in"]:
        start, end = case.at(q["start"]), case.at(q["end"])
        got = attempt(r, module.ask_template, board, "who_was_in", wing=q["wing"], start=start, end=end)
        want = answers.in_wing(case, q["wing"], start, end)
        ok = got is not None and set(got) == want
        if not ok and got is not None:
            r.fail(
                f"{case.id} · who_was_in({q['wing']}, {q['start']}–{q['end']}): {len(set(got) ^ want)} people differ"
            )
        _counter(r, ok)
    parties = answers.Parties(case)
    callers = [s.employee_id for s in case.staff][:3]
    for person in callers:
        phone = next(s.phone for s in case.staff if s.employee_id == person)
        want = set()
        for c in case.calls:
            if night[0] <= c.start < night[1] and phone in (c.caller, c.callee):
                other = c.callee if c.caller == phone else c.caller
                want.add(parties.party(other))
        got = attempt(r, module.ask_template, board, "callers_of", person=person, start=night[0], end=night[1])
        ok = got is not None and set(got) == want
        if not ok and got is not None:
            r.fail(f"{case.id} · callers_of({person}): got {sorted(got)}, want {sorted(want)}")
        _counter(r, ok)
    for wing in ("east", "west", "service"):
        got = attempt(r, module.ask_template, board, "unguarded_ways_in", wing=wing)
        want = answers.unguarded_ways_in(case, wing)
        ok = got is not None and set(got) == want
        if not ok and got is not None:
            r.fail(f"{case.id} · unguarded_ways_in({wing}): got {sorted(got)}, want {sorted(want)}")
        _counter(r, ok)


def _validator(module, r: Result) -> None:
    try:
        right = total = 0
        for q in BAD_QUERIES:
            total += 1
            ok = attempt(r, module.validate_query, q) is False
            right += ok
            if not ok:
                r.fail(f"let through: {q}")
        for name, q in getattr(module, "TEMPLATES", {}).items():
            total += 1
            ok = attempt(r, module.validate_query, q) is True
            right += ok
            if not ok:
                r.fail(f"rejected your own template {name!r}")
        tally(r, right, total, "queries judged right")
    except NotStarted:
        pass


def _routes(module, r: Result) -> None:
    try:
        right = total = 0
        for want, questions in ROUTES.items():
            for q in questions:
                total += 1
                got = attempt(r, module.route, q)
                right += got == want
                if got != want and got is not None and len(r.details) < 5:
                    r.details.append(f"{q!r}: got {got!r}, want {want!r}")
        r.score = f"{right}/{total} questions"
        r.passed = right / total >= 0.8 and not any("raised" in d for d in r.details)
        if r.passed:
            r.details.clear()
        else:
            r.details.insert(0, "Needs at least 80% of the questions on the right route.")
    except NotStarted:
        pass


def _search(module, case: Case, board, r: Result) -> None:
    truth = json.loads((case.path / "truth.json").read_text(encoding="utf-8"))
    native = {p["id"]: next((k for k in p["keys"] if k[:2] in ("E-", "G-", "C-")), None) for p in truth["people"]}
    names = {s.employee_id: s.full_name for s in case.staff} | {
        w.contractor_id: w.worker_name for w in case.contractors
    }
    for g in case.guests:
        last, _, first = g.name.partition(", ")
        names[g.guest_id] = f"{first} {last}"
    where: dict[str, set[tuple[str, int]]] = {}
    indirect: dict[str, int] = {}  # mentions that don't write the full name: a first name, a role, a typo
    for doc in case.documents:
        spans = _paragraph_spans(doc.text)
        for m in truth["documents"][doc.doc_id]["mentions"]:
            pid = native.get(m["person"])
            if not pid:
                continue
            i = next(i for i, (a, b) in enumerate(spans) if a <= m["start"] < b)
            where.setdefault(pid, set()).add((doc.doc_id, i))
            indirect[pid] = indirect.get(pid, 0) + (m["text"] != names.get(pid))
    # Ask about the people the text names least directly: that's where the graph's links matter.
    asked = sorted(where, key=lambda p: (-indirect.get(p, 0), -len(where[p]), p))[:5]
    scores = r.__dict__.setdefault("recalls", [])
    plain = r.__dict__.setdefault("plain", [])
    for pid in asked:
        question = f"Which statements mention {names[pid]}?"
        got = attempt(r, module.graph_search, board, question, 5)
        gold = where[pid]
        recall = len(gold & {tuple(x) for x in got}) / min(len(gold), 5) if got is not None else 0.0
        scores.append(recall)
        if hasattr(module, "search"):
            hits = module.search(board, question, 5) or []
            plain.append(len(gold & {tuple(x) for x in hits}) / min(len(gold), 5))
        if recall < 0.5 and len(r.details) < 4:
            r.details.append(
                f"{case.id} · {names[pid]}: {recall:.0%} of the paragraphs that mention them in your top 5"
            )
    mean = sum(scores) / len(scores)
    r.score = f"mean recall@5 {mean:.2f} over {len(scores)} questions"
    r.passed = mean >= 0.85 and not any("raised" in d for d in r.details)
    r.notes[:] = [f"plain vector search, same questions: {sum(plain) / len(plain):.2f}"] if plain else []


def _communities(module, case: Case, board, r: Result) -> None:
    got = attempt(r, module.communities, board)
    if got is None:
        return _counter(r, False)
    listed = [s.employee_id for s in case.staff] + [g.guest_id for g in case.guests]
    listed += [w.contractor_id for w in case.contractors]
    graph = nx.Graph()
    graph.add_nodes_from(listed)
    adj = answers.links(case)
    graph.add_edges_from((a, b) for a in listed for b in adj.get(a, ()) if b in set(listed))
    seen: set[str] = set()
    parts = []
    for group in got:
        part = set(group) & set(listed)
        if part & seen:
            r.fail(f"{case.id}: someone is in two communities")
            return _counter(r, False)
        seen |= part
        if part:
            parts.append(part)
    parts += [{p} for p in listed if p not in seen]
    q = nx.community.modularity(graph, parts)
    ok = q >= 0.25
    if not ok:
        r.fail(f"{case.id}: modularity {q:.2f}; groups this loose won't summarize well (want ≥ 0.25)")
    _counter(r, ok)
    r.__dict__["unit"] = "cases"


def _llm_checks(module, case: Case, board, generated: Result, global_q: Result) -> None:
    from ..llm import LLMError, get_llm

    try:
        llm = get_llm()
    except LLMError as e:
        for r in (generated, global_q):
            r.started = r.passed = False
            r.notes.append(f"Needs an LLM: {e}. Then run `uv run heist llm`.")
        return
    night = (case.at("17:00"), case.at("17:00") + timedelta(hours=9))
    calls = sum(night[0] <= c.start < night[1] for c in case.calls)
    big = sum(t.amount > 1000 for t in case.transfers)
    asks = {
        f"How many phone calls started between {night[0]:%Y-%m-%d %H:%M} and {night[1]:%Y-%m-%d %H:%M}?": calls,
        "How many bank transfers had an amount greater than 1000?": big,
    }
    right = 0
    try:
        for question, want in asks.items():
            rows = attempt(generated, module.generated_query, board, question, llm) or []
            values = [v for row in rows for v in (row.values() if isinstance(row, dict) else [row])]
            ok = want in values
            right += ok
            if not ok:
                generated.fail(f"{question} → {values[:5]} (want {want})")
        tally(generated, right, len(asks), "questions")
        truth = json.loads((case.path / "truth.json").read_text(encoding="utf-8"))
        native = {p["id"]: next((k for k in p["keys"] if k[:2] in ("E-", "G-", "C-")), None) for p in truth["people"]}
        want = {native[c["subject"]] for d in truth["documents"].values() for c in d["claims"]
                if c["predicate"] == "money_trouble"}  # fmt: skip
        got = attempt(global_q, module.global_answer, board, "Who do the documents say is short of money?", llm)
        if got is not None:
            got = set(got)
            recall = len(got & want) / len(want) if want else 1.0
            precision = len(got & want) / len(got) if got else 0.0
            global_q.score = f"precision {precision:.2f}, recall {recall:.2f}"
            if recall < 1.0 or precision < 0.5:
                global_q.fail(f"got {sorted(got)}, want {sorted(want)}")
        global_q.notes.append(
            f"LLM: {llm.provider.name} {llm.model}, {llm.usage.calls} calls ({llm.usage.cached} cached)"
        )
    except LLMError as e:
        generated.fail(f"the LLM call failed: {e}")
