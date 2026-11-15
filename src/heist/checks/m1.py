"""Checks for milestone 1, the timeline board."""

from __future__ import annotations

from types import ModuleType

from .. import answers
from ..case import Case, list_cases, load_case
from .core import NotStarted, Result, attempt, tally

PACKS = ("practice", "easy", "medium", "hard")
KS = (5, 10, 25, 50, 100)

L_SILOS = ("graphrag", "data-silos", "Data silos")
L_GRAPHRAG = ("graphrag", "what-is-graphrag", "What is GraphRAG?")
L_GRAPH = ("graphrag", "what-is-a-graph", "What is a graph?")
L_VECTOR = ("graphrag", "knowledge-graph-vs-vector-database", "Knowledge graph vs vector database")


def cases() -> list[Case]:
    return [load_case(n) for pack in PACKS for n in list_cases(pack)]


def _parties(case: Case, keys, result: Result, what: str) -> set[str] | None:
    if keys is None:
        return None
    if isinstance(keys, str) or not hasattr(keys, "__iter__"):
        result.fail(f"{case.id} · {what}: expected a set of ids, got {type(keys).__name__}")
        return None
    p = answers.Parties(case)
    out = set()
    for k in keys:
        party = p.party(k)
        if party is None:
            result.fail(f"{case.id} · {what}: {k!r} isn't an id of anyone in this case")
        else:
            out.add(party)
    return out


def run(module: ModuleType) -> list[Result]:
    all_cases = cases()
    summary = Result("Every system is in the graph", L_SILOS)
    wing = Result("Who was in the wing", L_GRAPHRAG)
    conn = Result("Shortest connection", L_GRAPH)
    loops = Result("Money loops", L_GRAPH)
    vector = Result("The vector search baseline", L_VECTOR)
    results = [summary, wing, conn, loops, vector]

    graphs = {}
    try:
        for case in all_cases:
            graphs[case.id] = attempt(summary, module.build_graph, case)
    except NotStarted:
        for r in results:
            r.started, r.passed = False, False
        return results

    # 1. Every system's rows made it in.
    ok = 0
    for case in all_cases:
        g = graphs[case.id]
        if g is None:
            continue
        try:
            got = attempt(summary, module.graph_summary, g)
        except NotStarted:
            summary.started = False
            break
        if not isinstance(got, dict):
            summary.fail(f"{case.id}: graph_summary should return a dict, got {type(got).__name__}")
            continue
        want = answers.counts(case)
        wrong = [f"{k}: {got.get(k, 'missing')} (want {v})" for k, v in want.items() if got.get(k) != v]
        if wrong:
            summary.fail(f"{case.id}: " + ", ".join(wrong))
        else:
            ok += 1
    tally(summary, ok, len(all_cases), "cases")

    # 2. Who was in the wing, by the keycard log.
    total = right = 0
    try:
        for case in all_cases:
            g = graphs[case.id]
            for q in case.meta["questions"]["who_was_in"]:
                total += 1
                start, end = case.at(q["start"]), case.at(q["end"])
                what = f"{q['wing']} wing {q['start']}–{q['end']}"
                got = _parties(case, attempt(wing, module.who_was_in, g, q["wing"], start, end), wing, what)
                if got is None:
                    continue
                want = answers.in_wing(case, q["wing"], start, end)
                if got == want:
                    right += 1
                    continue
                p = answers.Parties(case)
                missing = ", ".join(p.label(x) for x in sorted(want - got))
                extra = ", ".join(p.label(x) for x in sorted(got - want))
                wing.fail(
                    f"{case.id} · {what} (end not included): "
                    + "; ".join(
                        x for x in [f"missing {missing}" if missing else "", f"extra {extra}" if extra else ""] if x
                    )
                )
    except NotStarted:
        pass
    tally(wing, right, total, "questions")

    # 3. Shortest connection: a real path, as short as any.
    total = right = 0
    try:
        for case in all_cases:
            g = graphs[case.id]
            adj = answers.links(case)
            p = answers.Parties(case)
            for q in case.meta["questions"]["connection"]:
                total += 1
                path = attempt(conn, module.connection, g, q["a"], q["b"])
                what = f"{q['a']} → {q['b']}"
                if path is None:
                    continue
                parties = [p.party(k) for k in path]
                parties = [x for i, x in enumerate(parties) if i == 0 or x != parties[i - 1]]
                if None in parties:
                    bad = next(k for k in path if p.party(k) is None)
                    conn.fail(f"{case.id} · {what}: {bad!r} isn't an id of anyone in this case")
                    continue
                best = answers.shortest_hops(case, q["a"], q["b"], adj)
                broken = next((i for i in range(len(parties) - 1) if parties[i + 1] not in adj[parties[i]]), None)
                if not parties or parties[0] != p.party(q["a"]) or parties[-1] != p.party(q["b"]):
                    conn.fail(f"{case.id} · {what}: the path should start at {q['a']} and end at {q['b']}")
                elif broken is not None:
                    conn.fail(f"{case.id} · {what}: {parties[broken]} and {parties[broken + 1]} aren't directly linked")
                elif len(parties) - 1 != best:
                    conn.fail(f"{case.id} · {what}: {len(parties) - 1} links, but {best} is enough")
                else:
                    right += 1
    except NotStarted:
        pass
    tally(conn, right, total, "pairs")

    # 4. Money loops.
    right = 0
    try:
        for case in all_cases:
            got_raw = attempt(loops, module.money_loops, graphs[case.id])
            if got_raw is None:
                continue
            got = {answers.canonical_loop([str(a) for a in loop]) for loop in got_raw if loop}
            want = answers.money_loops(case)
            if got == want:
                right += 1
                continue
            missing = [" → ".join((*x, x[0])) for x in sorted(want - got)]
            extra = [" → ".join((*x, x[0])) for x in sorted(got - want)]
            loops.fail(
                f"{case.id}: "
                + "; ".join(
                    x for x in [f"missing {missing}" if missing else "", f"not loops {extra}" if extra else ""] if x
                )
            )
    except NotStarted:
        pass
    tally(loops, right, len(all_cases), "cases")

    # 5. Vector search over the same logs, for comparison. It passes when it runs:
    #    the point is the table, not a score.
    try:
        rows = []
        exact = False
        for case in [c for c in all_cases if c.id.startswith("practice/")]:
            q = case.meta["questions"]["who_was_in"][0]
            start, end = case.at(q["start"]), case.at(q["end"])
            want = answers.in_wing(case, q["wing"], start, end)
            line = []
            for k in KS:
                got = _parties(
                    case, attempt(vector, module.vector_who_was_in, case, q["wing"], start, end, k), vector, "vector"
                )
                if got is None:
                    break
                hit = len(got & want)
                precision = hit / len(got) if got else 0.0
                recall = hit / len(want) if want else 1.0
                exact |= got == want
                line.append(f"{precision:.2f}/{recall:.2f}")
            rows.append((case.id, line))
        if not rows or any(len(line) < len(KS) for _, line in rows):
            vector.passed = False
        if vector.passed:
            vector.score = "ran on the practice pack"
            vector.notes.append("precision/recall at k = " + ", ".join(str(k) for k in KS))
            for cid, line in rows:
                vector.notes.append(f"{cid}: " + "  ".join(line))
            vector.notes.append(
                "Some k got it exactly right. Try a later window or another wing."
                if exact
                else "No k returns exactly the right people. Why? The milestone page asks you to explain it."
            )
    except NotStarted:
        pass
    return results
