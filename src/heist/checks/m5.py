"""Checks for milestone 5, solve rate."""

from __future__ import annotations

import hashlib
import json
from types import ModuleType

from ..case import list_cases, load_case
from .core import NotStarted, Result, attempt, tally

L_EVAL = ("graphrag", "evaluating-graphrag", "GraphRAG evaluation")
PACKS = ("practice", "easy", "medium", "hard")


def run(module: ModuleType) -> list[Result]:
    solved = Result("Solve rate on the labeled packs", L_EVAL)
    final = Result("The final pack", L_EVAL)
    layers = Result("Layer metrics, read from the bottom", L_EVAL)
    judge = Result("A pairwise judge without position or length bias", L_EVAL)
    runs = Result("Runs you can compare", L_EVAL)
    for check, r in ((_solve, solved), (_final, final), (_layers, layers), (_pairwise, judge), (_manifests, runs)):
        try:
            check(module, r)
        except NotStarted:
            r.started = r.passed = False
    return [solved, final, layers, judge, runs]


def _solve(module, r: Result) -> None:
    by_pack: dict[str, list[int]] = {}
    culprits = accomplices = methods = total = 0
    for name in [n for pack in PACKS for n in list_cases(pack)]:
        case = load_case(name)
        crime = json.loads((case.path / "truth.json").read_text(encoding="utf-8"))["crime"]
        got = attempt(r, module.solve, case) or {}
        total += 1
        ok = got.get("culprit") == crime["culprit"]["native_id"]
        culprits += ok
        accomplices += got.get("accomplice") == crime["accomplice"]["native_id"]
        methods += got.get("method") == crime["method"]
        by_pack.setdefault(name.split("/")[0], [0, 0])
        by_pack[name.split("/")[0]][0] += ok
        by_pack[name.split("/")[0]][1] += 1
        if not ok and got and len(r.details) < 4:
            r.details.append(f"{name}: named {got.get('culprit')}")
    r.score = f"{culprits}/{total} thieves named"
    r.passed = total > 0 and culprits / total >= 0.8
    r.notes.append(" · ".join(f"{p} {a}/{b}" for p, (a, b) in by_pack.items()))
    r.notes.append(f"accomplices {accomplices}/{total}, methods {methods}/{total}")
    if not r.passed:
        r.details.insert(0, "Needs the right thief in at least 80% of the cases.")


def _final(module, r: Result) -> None:
    names = list_cases("final")
    right = 0
    for name in names:
        case = load_case(name)
        hashes = json.loads((case.path / "answers.sha256.json").read_text(encoding="utf-8"))
        got = attempt(r, module.solve, case) or {}
        digest = hashlib.sha256(f"{hashes['salt']}:{got.get('culprit')}".encode()).hexdigest()
        right += digest == hashes["culprit"]
    r.score = f"{right}/{len(names)} solved"
    r.passed = right >= len(names) - 1
    if not r.passed:
        r.details.append("Needs at least two of the three hidden cases.")


def _close(a: dict | None, b: dict) -> bool:
    return isinstance(a, dict) and all(abs(float(a.get(k, -1)) - v) < 1e-6 for k, v in b.items())


def _layers(module, r: Result) -> None:
    t = ("Vos", "was_in", "R03")
    u = ("Vos", "saw", "Lindgren")
    fixtures = [
        (([t, t, u], [t]), {"precision": 0.5, "recall": 1.0, "f1": 2 / 3}),
        (([], [t]), {"precision": 0.0, "recall": 0.0, "f1": 0.0}),
        (([u], [t]), {"precision": 0.0, "recall": 0.0, "f1": 0.0}),
        (([t, u], [t, u]), {"precision": 1.0, "recall": 1.0, "f1": 1.0}),
    ]
    right = total = 0
    for (pred, gold), want in fixtures:
        total += 1
        got = attempt(r, module.triple_scores, pred, gold)
        if _close(got, want):
            right += 1
        elif got is not None:
            r.fail(f"triple_scores({pred}, {gold}) = {got}, want {want}")
    bars = {"graph": 0.8, "retrieval": 0.7, "answer": 1.0}
    for scores, want in [
        ({"graph": 0.9, "retrieval": 0.4, "answer": 0.0}, "retrieval"),
        ({"graph": 0.5, "retrieval": 0.9, "answer": 0.0}, "graph"),
        ({"graph": 0.9, "retrieval": 0.9, "answer": 0.0}, "answer"),
        ({"graph": 0.9, "retrieval": 0.9, "answer": 1.0}, None),
    ]:
        total += 1
        got = attempt(r, module.bottom_up, scores, bars, none_ok=True)
        if got == want:
            right += 1
        else:
            r.fail(f"bottom_up({scores}) = {got!r}, want {want!r}")
    tally(r, right, total, "answers")


def _pairwise(module, r: Result) -> None:
    def always_first(question, first, second):
        return "first"

    def likes_long_text(question, first, second):
        # Prefers the longer answer; at about the same length, the one that names Vos.
        if abs(len(first) - len(second)) > 0.1 * max(len(first), len(second)):
            return "first" if len(first) > len(second) else "second"
        return "first" if "Vos" in first else "second"

    short = "Vos did it."
    long = "It was Lindgren, without a doubt, as anyone could see from the many long and detailed clues."
    cases = [
        ("position bias", always_first, short, long, "tie"),
        ("length bias", likes_long_text, short, long, "a"),
        ("length bias, swapped", likes_long_text, long, short, "b"),
    ]
    right = 0
    for label, judge, a, b, want in cases:
        got = attempt(r, module.pairwise, "Who took the painting?", a, b, judge)
        if got == want:
            right += 1
        else:
            r.fail(f"{label}: got {got!r}, want {want!r}")
    tally(r, right, len(cases), "judgments")


def _manifests(module, r: Result) -> None:
    one, two = load_case("practice/case-01"), load_case("practice/case-02")
    m1 = attempt(r, module.manifest, one, k=5, route="graph")
    m2 = attempt(r, module.manifest, one, k=10, route="graph")
    m3 = attempt(r, module.manifest, two, k=5, route="graph")
    if None in (m1, m2, m3):
        return
    right = total = 0
    missing = [k for k in ("case", "case_fingerprint", "code", "provider", "model", "config", "created") if k not in m1]
    total += 1
    right += not missing
    if missing:
        r.fail(f"the manifest has no {', '.join(missing)}")
    total += 1
    d = attempt(r, module.diff, m1, m2)
    if d == {"k": (5, 10)}:
        right += 1
    else:
        r.fail(f"diff of two runs that differ only in k: {d}")
    total += 1
    d = attempt(r, module.diff, m1, m3) or {}
    if set(d) == {"case", "case_fingerprint"}:
        right += 1
    else:
        r.fail(f"diff of the same run on two cases should name the case and its fingerprint, got {sorted(d)}")
    tally(r, right, total, "comparisons")
