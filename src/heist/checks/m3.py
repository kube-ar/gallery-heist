"""Checks for milestone 3, reading the statements."""

from __future__ import annotations

import json
from datetime import timedelta
from types import ModuleType

from .. import answers
from ..case import Case, list_cases, load_case
from ..llm import LLMError
from .core import NotStarted, Result, attempt, model_for, tally

PACKS = ("practice", "easy", "medium", "hard")
L_LEXICAL = ("graphrag", "lexical-graph", "Lexical graph")
L_LINKING = ("graphrag", "entity-linking", "Entity linking")
L_EXTRACT = ("graphrag", "llm-knowledge-graph-extraction", "Knowledge graph extraction with LLMs")
L_QUALITY = ("graphrag", "knowledge-graph-quality", "Knowledge graph quality")
PREDICATES = {"arrived_at", "was_in", "saw", "talked_to", "called", "knows", "money_trouble", "led_tour"}


def _truth(case: Case) -> dict:
    return json.loads((case.path / "truth.json").read_text(encoding="utf-8"))


def _native(truth: dict) -> dict[str, str | None]:
    return {p["id"]: next((k for k in p["keys"] if k[:2] in ("E-", "G-", "C-")), None) for p in truth["people"]}


def gold_claims(case: Case) -> dict[str, list[dict]]:
    """The claims each document makes, with people as their ids in the museum's lists."""
    truth = _truth(case)
    native = _native(truth)
    out = {}
    for doc_id, gold in truth["documents"].items():
        rows = []
        for c in gold["claims"]:
            obj = c["object"]
            if obj in native:
                obj = native[obj]
            time = None
            if c["time"] is not None:
                t = case.date + timedelta(minutes=c["time"])
                time = f"{t:%H:%M}"
            rows.append({"subject": native.get(c["subject"]), "predicate": c["predicate"], "object": obj,
                         "time": time, "true": c["true"]})  # fmt: skip
        out[doc_id] = rows
    return out


def cases_for_claims() -> list[Case]:
    """The claims check calls an LLM per document, so it runs on the practice pack only."""
    return [load_case(n) for n in list_cases("practice")]


def run(module: ModuleType) -> list[Result]:
    cases = [load_case(n) for pack in PACKS for n in list_cases(pack)]
    lexical = Result("The documents as a lexical graph", L_LEXICAL)
    linking = Result("People found and linked", L_LINKING)
    claims = Result("Claims read with your LLM", L_EXTRACT)
    quality = Result("Claims checked against the keycard log", L_QUALITY)
    results = [lexical, linking, claims, quality]
    _lexical(module, cases, lexical)
    _linking(module, cases, linking)
    _claims(module, cases_for_claims(), claims)
    _quality(module, cases, quality)
    return results


def _lexical(module, cases, r: Result) -> None:
    total = right = 0
    try:
        for case in cases:
            total += 1
            g = attempt(r, module.lexical_graph, case)
            if g is None:
                continue
            chunks = {d.doc_id: [p.strip() for p in d.text.split("\n\n") if p.strip()] for d in case.documents}
            want = {"documents": len(chunks), "chunks": sum(map(len, chunks.values())),
                    "next": sum(len(c) - 1 for c in chunks.values() if c)}  # fmt: skip
            got = attempt(r, module.lexical_summary, g)
            if got is None:
                continue
            wrong = [f"{k}: {got.get(k, 'missing')} (want {v})" for k, v in want.items() if got.get(k) != v]
            for doc_id, paras in list(chunks.items())[:4]:
                i = len(paras) // 2
                hood = attempt(r, module.neighborhood, g, doc_id, i)
                expected = {"title": next(d.title for d in case.documents if d.doc_id == doc_id),
                            "before": paras[i - 1] if i else None, "chunk": paras[i],
                            "after": paras[i + 1] if i + 1 < len(paras) else None}  # fmt: skip
                if hood is not None and {k: hood.get(k) for k in expected} != expected:
                    wrong.append(f"neighborhood({doc_id}, {i}) isn't the chunk with its neighbors and title")
            if wrong:
                r.fail(f"{case.id}: " + "; ".join(wrong))
            else:
                right += 1
    except NotStarted:
        return
    tally(r, right, total, "cases")


def _linking(module, cases, r: Result) -> None:
    gold_total = predicted = correct = 0
    try:
        for case in cases:
            truth = _truth(case)
            native = _native(truth)
            for doc in case.documents:
                gold = [
                    (m["start"], m["end"], native.get(m["person"])) for m in truth["documents"][doc.doc_id]["mentions"]
                ]
                gold = [g for g in gold if g[2]]
                got = attempt(r, module.find_people, case, doc)
                if got is None:
                    continue
                gold_total += len(gold)
                matched: set[int] = set()  # each gold mention counts once: a second span on it is a false positive
                for start, end, pid in got:
                    if pid is None:
                        continue
                    predicted += 1
                    overlaps = [i for i, (a, b, who) in enumerate(gold) if a < end and start < b and pid == who]
                    hit = next((i for i in overlaps if i not in matched), None)
                    if hit is not None:
                        matched.add(hit)
                        correct += 1
                    elif len(r.details) < 6:
                        why = "was already found once" if overlaps else f"isn't {pid}"
                        r.details.append(f"{case.id} · {doc.doc_id}: {doc.text[start:end]!r} {why}")
    except NotStarted:
        return
    precision = correct / predicted if predicted else 0.0
    recall = correct / gold_total if gold_total else 0.0
    r.score = f"precision {precision:.2f}, recall {recall:.2f} over {gold_total} mentions"
    r.passed = precision >= 0.9 and recall >= 0.7 and not any("raised" in d for d in r.details)
    if r.passed:
        r.details.clear()
    else:
        r.details.insert(0, "Needs precision ≥ 0.90 (a wrong link is worse than none) and recall ≥ 0.70.")


def _claims(module, cases, r: Result) -> None:
    llm = model_for(r)
    if llm is None:
        return
    tp = fp = fn = 0
    times = timed = 0
    bad_predicates: set[str] = set()
    try:
        for case in cases:
            gold = gold_claims(case)
            for doc in case.documents:
                got = attempt(r, module.read_document, case, doc, llm)
                if got is None:
                    continue
                accepted = [c for c in got if c.get("status") == "accepted"]
                bad_predicates |= {str(c.get("predicate")) for c in accepted} - PREDICATES
                want = {(c["subject"], c["predicate"], c["object"]) for c in gold[doc.doc_id]}
                have = {(c.get("subject"), c.get("predicate"), c.get("object")) for c in accepted}
                tp, fp, fn = tp + len(want & have), fp + len(have - want), fn + len(want - have)
                for c in accepted:
                    match = next((g for g in gold[doc.doc_id] if (g["subject"], g["predicate"], g["object"]) ==
                                  (c.get("subject"), c.get("predicate"), c.get("object")) and g["time"]), None)  # fmt: skip
                    if match and c.get("time"):
                        timed += 1
                        times += _minutes_apart(match["time"], c["time"]) <= 10
    except NotStarted:
        return
    except LLMError as e:
        r.fail(f"the LLM call failed: {e}")
        return
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    r.score = f"F1 {f1:.2f} (precision {precision:.2f}, recall {recall:.2f}) on the practice pack"
    if bad_predicates:
        r.fail(f"accepted claims use predicates outside the ontology: {sorted(bad_predicates)}")
    if f1 < 0.7:
        r.fail("Needs F1 ≥ 0.70 on (subject, predicate, object) of accepted claims.")
    if timed:
        r.notes.append(f"times within 10 minutes of what the text says: {times}/{timed}")
    r.notes.append(f"LLM: {llm.provider.name} {llm.model}, {llm.usage.calls} calls ({llm.usage.cached} cached)")


def _minutes_apart(a: str, b: str) -> int:
    def m(t: str) -> int:
        h, mm = map(int, t.split(":"))
        return (h + (24 if h < 12 else 0)) * 60 + mm

    return abs(m(a) - m(b))


def _quality(module, cases, r: Result) -> None:
    total = right = lies = caught = 0
    try:
        for case in cases:
            claims = [
                c for rows in gold_claims(case).values() for c in rows if c["predicate"] == "was_in" and c["time"]
            ]
            shown = [{k: v for k, v in c.items() if k != "true"} for c in claims]
            got = attempt(r, module.contradictions, case, shown)
            if got is None:
                continue
            want = set()
            for i, c in enumerate(claims):
                hh, mm = map(int, c["time"].split(":"))
                at = case.date + timedelta(days=1 if hh < 12 else 0, hours=hh, minutes=mm)
                if answers.contradicts(case, c["subject"], c["object"], at):
                    want.add(i)
            total += 1
            if set(got) == want:
                right += 1
                lies += sum(not c["true"] for c in claims)
                caught += sum(not claims[i]["true"] for i in want)
            else:
                missing, extra = sorted(want - set(got)), sorted(set(got) - want)
                r.fail(f"{case.id}: missed {len(missing)} contradictions, flagged {len(extra)} that the log allows")
    except NotStarted:
        return
    tally(r, right, total, "cases")
    if r.passed:
        r.notes.append(f"The log rules out {caught} of the {lies} lies in the statements. What would catch the rest?")
