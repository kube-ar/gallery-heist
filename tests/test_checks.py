"""The reference solutions pass their checks; the starter files are 'not started'."""

import importlib
import importlib.util
import os
import sys

import pytest

from heist.case import ROOT
from heist.milestones import MILESTONES


def load(path):
    spec = importlib.util.spec_from_file_location(f"ref_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def neo4j_up() -> bool:
    try:
        from neo4j import GraphDatabase

        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "heist-password"))
        with GraphDatabase.driver(uri, auth=auth) as driver:
            driver.verify_connectivity()
        return True
    except Exception:
        return False


NEEDS_NEO4J = {"4"}


@pytest.mark.parametrize("mid", sorted(MILESTONES))
def test_reference_passes(mid):
    if mid in NEEDS_NEO4J and not neo4j_up():
        pytest.skip("needs Neo4j: docker compose up -d")
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


@pytest.mark.skipif(not neo4j_up(), reason="needs Neo4j: docker compose up -d")
def test_model_written_queries_are_validated_then_run():
    from heist.case import load_case

    reference = load(ROOT / MILESTONES["4"].reference)
    case = load_case("practice/case-01")
    board = reference.store(case)

    class FakeLLM:
        def __init__(self, cypher):
            self.cypher = cypher

        def json(self, prompt, schema, system=None):
            return {"cypher": self.cypher}

    rows = reference.generated_query(
        board, "how many transfers?", FakeLLM("MATCH (t:Transfer) RETURN count(t) AS n LIMIT 1")
    )
    assert rows == [{"n": len(case.transfers)}]
    assert reference.generated_query(board, "wipe it", FakeLLM("MATCH (n) DETACH DELETE n")) == []
    assert reference.store_summary(board)["people"] > 0  # the bad query never ran


def test_rookie_loop_stops_at_the_accusation():
    from heist.case import load_case
    from heist.llm import ToolCall, Turn

    reference = load(ROOT / MILESTONES["d1"].reference)
    case = load_case("practice/case-01")
    seen, found = case.meta["last_seen"][11:], case.meta["discovered"][11:]
    script = [
        [ToolCall("1", "rulebook", {})],
        [ToolCall("2", "camera_log", {"start": seen, "end": found}), ToolCall("3", "keycard_log", {"room": "R34"})],
        [
            ToolCall(
                "4",
                "accuse",
                {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": ["camera log", "keycard log"]},
            )
        ],
        [ToolCall("5", "briefing", {})],  # never reached
    ]

    class FakeConversation:
        def __init__(self, llm, tools, system=None):
            self.turns = iter(script)

        def send(self, text):
            return Turn("", next(self.turns))

        def reply(self, results, errors=frozenset()):
            return Turn("", next(self.turns))

    reference.Conversation = FakeConversation
    desk = reference.investigate(case, llm=None)
    assert desk.accusation is not None and [a.tool for a in desk.log][-1] == "accuse"
    assert "briefing" not in [a.tool for a in desk.log]
    assert reference.failures(desk) == []  # two kinds of source, and the camera call covered the window


def test_planned_investigation_runs_its_phases_then_validates():
    import json as _json

    from heist.case import load_case

    reference = load(ROOT / MILESTONES["d4"].reference)
    case = load_case("practice/case-01")
    crime = _json.loads((case.path / "truth.json").read_text())["crime"]

    class FakeLLM:
        def json(self, prompt, schema, system=None):
            return {"culprit": crime["culprit"]["native_id"], "accomplice": crime["accomplice"]["native_id"],
                    "method": crime["method"],
                    "evidence": ["the camera log shows the cameras went dark", "the keycard log puts the accomplice in the office",
                                 "phone records show their calls"]}  # fmt: skip

    desk = reference.investigate(case, FakeLLM())
    tools = [a.tool for a in desk.log]
    # the first phase (cameras, place, room) runs together, before anything that needs it
    assert set(tools[:4]) == {"camera_log", "floor_plan", "list_people", "keycard_log"} and tools[-1] == "accuse"
    assert desk.verdict()["solved"]
