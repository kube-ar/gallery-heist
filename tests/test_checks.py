"""The reference solutions pass their checks; the starter files are 'not started'."""

import importlib
import importlib.util
import os

import pytest

from heist.case import ROOT
from heist.milestones import MILESTONES


def load(path):
    spec = importlib.util.spec_from_file_location(f"ref_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mid", sorted(MILESTONES))
def test_reference_passes(mid):
    m = MILESTONES[mid]
    results = importlib.import_module(m.checks).run(load(ROOT / m.reference))
    # Checks that need an LLM are "not started" when none is configured (as in CI): skip those.
    failed = [(r.name, r.details[:2]) for r in results if not r.passed and r.started]
    assert failed == []


UPSTREAM = os.environ.get("GITHUB_REPOSITORY", "") == "kube-ar/gallery-heist" or os.environ.get("HEIST_UPSTREAM")


@pytest.mark.skipif(not UPSTREAM, reason="your copy has your code in the starter files, not the stubs")
@pytest.mark.parametrize("mid", sorted(MILESTONES))
def test_starter_is_not_started(mid):
    m = MILESTONES[mid]
    starter = load(ROOT / m.file)
    results = importlib.import_module(m.checks).run(starter)
    assert all(not r.started for r in results)


def test_claims_check_scores_extraction(monkeypatch):
    """Milestone 3's LLM check, driven without an LLM: perfect claims pass, wrong ones fail."""
    from heist.checks import m3

    monkeypatch.setenv("HEIST_LLM_PROVIDER", "anthropic")  # configured, but never called below
    reference = load(ROOT / MILESTONES["3"].reference)
    cases = [c for c in m3.cases_for_claims()]

    class Oracle:
        def __getattr__(self, name):
            return getattr(reference, name)

        @staticmethod
        def read_document(case, doc, llm):
            gold = m3.gold_claims(case)[doc.doc_id]
            return [
                {**{k: c[k] for k in ("subject", "predicate", "object", "time")}, "status": "accepted"} for c in gold
            ]

    class Wrong(Oracle):
        @staticmethod
        def read_document(case, doc, llm):
            return [{"subject": "E-0000", "predicate": "was_in", "object": "R03", "time": None, "status": "accepted"}]

    good = m3.Result("claims", None)
    m3._claims(Oracle(), cases, good)
    assert good.passed, good.details
    bad = m3.Result("claims", None)
    m3._claims(Wrong(), cases, bad)
    assert not bad.passed


def test_reference_reads_a_model_answer(monkeypatch):
    """The reference's read_document turns a model's raw answer into linked, triaged claims."""
    from heist.checks import m3

    reference = load(ROOT / MILESTONES["3"].reference)
    case = m3.cases_for_claims()[0]
    names = {s.employee_id: s.full_name for s in case.staff} | {
        w.contractor_id: w.worker_name for w in case.contractors
    }
    for g in case.guests:
        last, _, first = g.name.partition(", ")
        names[g.guest_id] = f"{first} {last}"
    rooms = {r.room_id: r.name for r in case.rooms}

    class FakeLLM:
        def __init__(self, doc):
            self.doc = doc

        def json(self, prompt, schema, system=None):
            author = reference.People(case).resolve(self.doc.author)
            rows = []
            for c in m3.gold_claims(case)[self.doc.doc_id]:
                subject = "I" if c["subject"] == author else names.get(c["subject"], "")
                obj = rooms.get(c["object"], names.get(c["object"], "")) if c["object"] else ""
                rows.append({"subject": subject, "predicate": c["predicate"], "object": obj, "time": c["time"] or ""})
            return {"claims": rows}

    tp = total = 0
    for doc in case.documents:
        got = reference.read_document(case, doc, FakeLLM(doc))
        want = {(c["subject"], c["predicate"], c["object"]) for c in m3.gold_claims(case)[doc.doc_id]}
        have = {(c["subject"], c["predicate"], c["object"]) for c in got if c["status"] == "accepted"}
        tp, total = tp + len(want & have), total + len(want)
        assert have <= want, (doc.doc_id, have - want)
    assert tp / total > 0.95
