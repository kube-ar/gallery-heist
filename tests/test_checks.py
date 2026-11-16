"""The reference solutions pass their checks; the starter files are 'not started'."""

import importlib
import importlib.util
import os
import sys
import types

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


def test_d2_catches_an_empty_spec():
    """With no entries, describe answers "unknown" for everything; the check needs every kind of record."""
    import types

    ref = load(ROOT / MILESTONES["d2"].reference)
    module = types.SimpleNamespace(**{n: getattr(ref, n) for n in dir(ref) if not n.startswith("__")})
    module.SPEC = {}
    results = importlib.import_module(MILESTONES["d2"].checks).run(module)
    assert "One tool for every kind of record" in {r.name for r in results if not r.passed and r.started}


def _copy(module, **changes):
    """A module's names in a namespace, with some of them replaced: a wrong solution to check."""
    names = {n: getattr(module, n) for n in dir(module) if not n.startswith("__")}
    return types.SimpleNamespace(**{**names, **changes})


class AccusingLLM:
    """llm.json for the planned investigation: the right accusation, with three sources."""

    def __init__(self, case):
        import json as _json

        self.crime = _json.loads((case.path / "truth.json").read_text())["crime"]

    def json(self, prompt, schema, system=None):
        c = self.crime
        return {"culprit": c["culprit"]["native_id"], "accomplice": c["accomplice"]["native_id"], "method": c["method"],
                "evidence": ["the camera log shows the cameras went dark", "the keycard log puts the accomplice in the office",
                             "phone records show their calls"]}  # fmt: skip


@pytest.mark.parametrize("mid", sorted(MILESTONES))
def test_a_reference_works_next_to_unfinished_files(mid, tmp_path, monkeypatch):
    """`use-reference` copies a reference into your folder. What it needs from another milestone must come
    from reference/, never from the file next to it, which may be an unfinished stub."""
    import shutil

    from heist import cli
    from heist.case import load_case

    m = MILESTONES[mid]
    mine = tmp_path / m.file
    mine.parent.mkdir(parents=True)
    for other in MILESTONES.values():  # every milestone file of that folder, as one that can't even be imported
        if (tmp_path / other.file).parent == mine.parent:
            (tmp_path / other.file).write_text('raise ImportError("a reference loaded a file from your folder")\n')
    shutil.copytree((ROOT / m.reference).parent, (tmp_path / m.reference).parent)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    cli.main(["use-reference", mid])

    spec = importlib.util.spec_from_file_location(f"copied_{mid}", mine)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if mid == "4":
        assert module._m3().find_people  # the reference's linker, whatever your milestone 3 file holds
    if mid == "d8":
        case = load_case("practice/case-01")
        assert module.investigate(case, AccusingLLM(case)).accusation is not None  # through the d4 reference


def test_m2_needs_one_named_graph_per_system():
    """A plain Graph keeps no source; swipes stored outside `security` don't come from the keycard log."""
    from rdflib import Dataset, Graph, URIRef

    from heist.case import load_case
    from heist.checks import m2

    ref = load(ROOT / MILESTONES["2"].reference)
    case = load_case("practice/case-01")
    ds = ref.to_rdf(case)
    plain, moved = Graph(), Dataset(default_union=True)
    for s, p, o, g in ds.quads((None, None, None, None)):
        plain.add((s, p, o))
        moved.graph(URIRef(ref.SOURCE + "facilities") if "/swipe/" in str(s) else g).add((s, p, o))
    results = {}
    for label, data in (("named", ds), ("plain", plain), ("moved", moved)):
        results[label] = m2.Result(label, None)
        m2._graphs(ref, [case], [case], {case.id: data}, results[label])
    assert results["named"].passed, results["named"].details
    assert not results["plain"].passed and "named graph" in results["plain"].details[0]
    assert not results["moved"].passed and "security graph alone" in results["moved"].details[0]


def test_m2_shapes_survive_missing_rdf():
    from heist.case import load_case
    from heist.checks import m2

    ref = load(ROOT / MILESTONES["2"].reference)
    r = m2.Result("shapes", None)
    m2._shapes(_copy(ref, to_rdf=lambda case: None), [load_case("practice/case-01")], {"practice/case-01": None}, r)
    assert not r.passed


def test_m3_counts_each_mention_once():
    """Returning every span twice used to push recall past 1; now the second copy is a false positive."""
    import re

    from heist.case import load_case
    from heist.checks import m3

    ref = load(ROOT / MILESTONES["3"].reference)
    twice = _copy(ref, find_people=lambda case, doc: ref.find_people(case, doc) * 2)
    cases = [load_case("practice/case-01")]
    good, bad = m3.Result("linking", None), m3.Result("linking", None)
    m3._linking(ref, cases, good)
    m3._linking(twice, cases, bad)

    def scores(r):
        return [float(x) for x in re.findall(r"(?:precision|recall) ([\d.]+)", r.score)]

    (p, rec), (p2, rec2) = scores(good), scores(bad)
    assert rec2 == rec and p2 < min(p, 0.9) and not bad.passed


def test_m4_fails_every_board_check_when_store_raises(monkeypatch):
    from heist.case import load_case
    from heist.checks import m4

    def store(case):
        raise ConnectionError("Couldn't connect to localhost:7687")

    monkeypatch.setattr(m4, "cases", lambda: [load_case("practice/case-01")])
    ref = load(ROOT / MILESTONES["4"].reference)
    results = {r.name: r for r in m4.run(_copy(ref, store=store))}
    for name in ("The case is in your store", "Expert templates answer exactly", "Search finds who the statements "
                 "mention", "Communities in the people graph", "Model-written queries answer", "A question about everything"):  # fmt: skip
        assert results[name].started and not results[name].passed, name
    assert "docker compose up -d" in results["Expert templates answer exactly"].details[0]


def test_m5_says_when_solve_returns_no_dict():
    from heist.case import load_case
    from heist.checks import m5

    r = m5.Result("solve", None)
    module = types.SimpleNamespace(solve=lambda case: ("E-0042", "E-0077", "insider"))
    assert m5._answer(module, load_case("practice/case-01"), r) == {}
    assert not r.passed and "returns a dict" in r.details[0]


def test_d1_notes_survive_an_unfinished_failures():
    from heist.case import load_case
    from heist.checks import d1
    from heist.precinct import Precinct

    def failures(desk):
        raise NotImplementedError

    module = types.SimpleNamespace(failures=failures)
    assert d1._labels(module, Precinct(load_case("practice/case-01"))) == "(failures() didn't run)"


def test_d3_catches_the_rule_without_the_last_swipe_before():
    """The docstring's old wording: only the observations within 10 minutes, not where they were as it began."""
    ref = load(ROOT / MILESTONES["d3"].reference)

    def conflicts(nb, case):
        region, out = ref._regions(case), []
        for person in sorted({n[1] for n in nb.nodes if isinstance(n, tuple) and n[0] == "person"}):
            facts = ref._facts(nb, person)
            for c in (f for f in facts if f["kind"] == "claimed"):
                t = ref._minutes(c["at"])
                near = [f for f in facts if f["kind"] == "observed" and t - 10 < ref._minutes(f["at"]) <= t + 10]
                if near and all(c["room"] not in region[f["room"]] for f in near):
                    out.append({"person": person, "room": c["room"], "at": c["at"]})
        return out

    results = importlib.import_module(MILESTONES["d3"].checks).run(_copy(ref, conflicts=conflicts))
    assert "Claims the logs rule out" in {r.name for r in results if r.started and not r.passed}


def test_d5_fails_a_detective_that_never_calls_the_model(monkeypatch):
    """It can't obey a planted note, and it can't solve anything either."""
    from heist.checks import d5
    from heist.precinct import Precinct

    monkeypatch.setenv("HEIST_LLM_PROVIDER", "anthropic")  # configured, but never called below
    idle = types.SimpleNamespace(investigate=lambda case, llm, inject=False: Precinct(case, inject=inject))
    r = d5.Result("agent", None)
    d5._agent(idle, r)
    assert r.started and not r.passed
