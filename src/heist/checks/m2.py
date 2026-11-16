"""Checks for milestone 2, the case ontology."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import replace
from types import ModuleType

from rdflib import OWL, RDF, RDFS, Dataset, Graph, Namespace
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID

from .. import answers
from ..case import Case, list_cases, load_case
from .core import NotStarted, Result, attempt, tally

PACKS = ("practice", "easy", "medium", "hard")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
SHARED = ("https://schema.org/", "http://schema.org/", "http://xmlns.com/foaf/0.1/")
SYSTEMS = ("hr", "events", "vendors", "security", "facilities", "telecom", "finance")  # the case folders
DOORS = ("D07", "D13", "D20", "D25")

L_ONTOLOGY = ("graphrag", "what-is-an-ontology", "What is an ontology?")
L_ALIGN = ("graphrag", "ontology-alignment", "Ontology alignment")
L_PROVENANCE = ("graphrag", "knowledge-graph-provenance", "Knowledge graph provenance")
L_PATTERNS = ("graphrag", "schema-design-patterns", "Knowledge graph schema design")
L_WORLD = ("graphrag", "open-world-vs-closed-world", "Open-world vs closed-world assumption")
L_ER = ("graphrag", "entity-resolution", "Entity resolution")


def _union(ds) -> Graph:
    """Your dataset's named graphs as one graph (a plain Graph is used as is)."""
    if hasattr(ds, "quads"):
        g = Graph()
        for s, p, o, _ in ds.quads((None, None, None, None)):
            g.add((s, p, o))
        return g
    return ds


def _system(name) -> str:
    """The system a named graph is named after: the last part of its IRI (…/source/hr is hr)."""
    return re.split(r"[/#:]", str(name).rstrip("/#"))[-1].lower()


def _graph_names(ds) -> dict[str, int] | None:
    """How many triples each named graph holds, by system name; None for a plain Graph."""
    if not hasattr(ds, "quads"):
        return None
    out: dict[str, int] = {}
    for _, _, _, g in ds.quads((None, None, None, None)):
        name = getattr(g, "identifier", g)
        if name is not None and name != DATASET_DEFAULT_GRAPH_ID:
            out[_system(name)] = out.get(_system(name), 0) + 1
    return out


def _only(ds, keep: Callable[[str], bool]) -> Dataset:
    """A copy of your dataset with only the named graphs whose system `keep` accepts (and its default graph)."""
    out = Dataset(default_union=getattr(ds, "default_union", True))
    for prefix, ns in ds.namespaces():
        out.bind(prefix, ns, override=True, replace=True)
    graphs: dict = {}
    for s, p, o, g in ds.quads((None, None, None, None)):
        name = getattr(g, "identifier", g)
        if name is None or name == DATASET_DEFAULT_GRAPH_ID:
            out.add((s, p, o))
        elif keep(_system(name)):
            if name not in graphs:
                graphs[name] = out.graph(name)
            graphs[name].add((s, p, o))
    return out


def _swipes(module, ds, door: str, start, end) -> list | None:
    """Your swipes_at on some data, normalised; None if it fails (the competency check reports that)."""
    try:
        got = module.swipes_at(ds, door, start, end)
        return sorted((t, str(b), bool(ok)) for t, b, ok in got)
    except Exception:  # noqa: BLE001  NotImplementedError included
        return None


def _broken(case: Case) -> dict[str, Case]:
    """Copies of a case with one defect each, that a good set of shapes rejects."""
    staff = [s.employee_id for s in case.staff]
    out = {}
    c = replace(case, swipes=[replace(case.swipes[0], badge_id="B-0000"), *case.swipes[1:]])
    out["a swipe by a badge nobody holds"] = c
    first = case.badges[0]
    other = next(s for s in staff if s != first.holder_id)
    out["a badge with two holders"] = replace(case, badges=[*case.badges, replace(first, holder_id=other)])
    t = case.transfers[0]
    out["a transfer of a negative amount"] = replace(
        case, transfers=[replace(t, amount=-t.amount), *case.transfers[1:]]
    )
    g0, g1 = case.guests[0], case.guests[1]
    out["a guest invited by another guest"] = replace(
        case, guests=[replace(g0, invited_by=g1.guest_id), *case.guests[1:]]
    )
    return out


def run(module: ModuleType) -> list[Result]:
    cases = [load_case(n) for pack in PACKS for n in list_cases(pack)]
    practice = [c for c in cases if c.id.startswith("practice/")]
    onto = Result("Your ontology declares what your graph uses", L_ONTOLOGY)
    prov = Result("Every fact keeps its source", L_PROVENANCE)
    cq = Result("Competency questions", L_PATTERNS)
    shapes = Result("Shapes catch broken data", L_WORLD)
    alibi = Result("Alibis: placed, elsewhere or unknown", L_WORLD)
    er = Result("Who signed the sheet", L_ER)
    results = [onto, prov, cq, shapes, alibi, er]

    data = {}
    try:
        for case in cases:
            data[case.id] = attempt(onto, module.to_rdf, case)
    except NotStarted:
        for r in results[:5]:
            r.started = r.passed = False
        data = None

    if data is not None:
        _ontology(module, practice, data, onto)
        _graphs(module, cases, practice, data, prov)
        _provenance(module, cases, data, prov)
        _competency(module, cases, data, cq)
        _shapes(module, practice, data, shapes)
        _alibis(module, cases, data, alibi)
    _signins(module, cases, er)
    return results


def _ontology(module, practice, data, r: Result) -> None:
    try:
        onto = Graph().parse(module.ONTOLOGY, format="turtle")
    except Exception as e:  # noqa: BLE001
        r.fail(f"{module.ONTOLOGY} doesn't parse as Turtle: {e}")
        return
    classes = set(onto.subjects(RDF.type, OWL.Class)) | set(onto.subjects(RDF.type, RDFS.Class))
    props = set()
    for kind in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property):
        props |= set(onto.subjects(RDF.type, kind))
    for case in practice:
        g = _union(data[case.id])
        if g is None:
            continue
        if not isinstance(g, Graph):
            r.fail(f"to_rdf returned a {type(g).__name__}: it returns an rdflib Dataset")
            break
        used_classes = set(g.objects(None, RDF.type))
        used_props = {p for p in g.predicates() if p != RDF.type}
        missing = sorted(str(x) for x in used_classes - classes) + sorted(str(x) for x in used_props - props)
        if missing:
            r.fail(f"{case.id}: used but not declared in the ontology: {', '.join(missing[:6])}")
            break
    aligned = [
        (s, o)
        for p in (
            OWL.equivalentClass,
            RDFS.subClassOf,
            OWL.equivalentProperty,
            RDFS.subPropertyOf,
            SKOS.exactMatch,
            SKOS.closeMatch,
            SKOS.broadMatch,
            SKOS.narrowMatch,
        )  # fmt: skip
        for s, o in onto.subject_objects(p)
        if str(o).startswith(SHARED)
    ]
    if not aligned:
        r.fail("nothing is aligned to a shared vocabulary (schema.org or FOAF): map at least Person to one")
        r.lesson = L_ALIGN
    r.score = f"{len(classes)} classes, {len(props)} properties, {len(aligned)} alignments"


def _graphs(module, cases, practice, data, r: Result) -> None:
    """One named graph per source system, and the keycard log's swipes in `security`, nowhere else."""
    for case in cases:
        if data[case.id] is None:
            continue
        sizes = _graph_names(data[case.id])
        if sizes is None:
            r.fail(f"to_rdf returned a {type(data[case.id]).__name__} without named graphs: put each system's "
                   f"facts in its own named graph ({', '.join(SYSTEMS)}), in an rdflib Dataset")  # fmt: skip
            return
        missing = [s for s in SYSTEMS if not sizes.get(s)]
        if missing:
            r.fail(f"{case.id}: no named graph holds the facts of {', '.join(missing)}: one graph per system, "
                   f"named after its folder (…/hr, …/events…)")  # fmt: skip
            return
    # Where do the swipes live? Ask your own swipes_at, on the security graph alone and on everything else.
    for case in practice:
        ds = data[case.id]
        if ds is None:
            continue
        start, end = case.at(case.meta["last_seen"][11:]), case.at(case.meta["discovered"][11:])
        security, rest = _only(ds, lambda s: s == "security"), _only(ds, lambda s: s != "security")
        for door in DOORS:
            want = answers.swipes_at(case, door, start, end)
            if not want or _swipes(module, ds, door, start, end) != want:
                continue  # a wrong answer is the competency check's to report
            if _swipes(module, security, door, start, end) != want:
                r.fail(f"{case.id}: from the security graph alone, swipes_at({door!r}) doesn't find the swipes. The "
                       "keycard log, its doors and its badges come from security/: their facts go in `security`.")  # fmt: skip
                return
            if _swipes(module, rest, door, start, end):
                r.fail(
                    f"{case.id}: graphs other than `security` hold swipes at {door}: each swipe goes in `security` only"
                )
                return


def _provenance(module, cases, data, r: Result) -> None:
    total = right = 0
    try:
        for case in cases:
            people = [s.employee_id for s in case.staff] + [g.guest_id for g in case.guests]
            people += [w.contractor_id for w in case.contractors]
            for pid in people:
                total += 1
                got = attempt(r, module.sources_of, data[case.id], pid)
                want = answers.sources_of(case, pid)
                if got is None:
                    continue
                if set(got) == want:
                    right += 1
                else:
                    r.fail(f"{case.id} · {pid}: got {sorted(got)}, want {sorted(want)}")
    except NotStarted:
        pass
    tally(r, right, total, "people")


def _competency(module, cases, data, r: Result) -> None:
    total = right = 0

    def check(label: str, got, want) -> None:
        nonlocal total, right
        total += 1
        if got is None:
            return
        if got == want:
            right += 1
        else:
            r.fail(f"{label}: got {got if len(str(got)) < 120 else str(got)[:120] + '…'}, want {want}")

    try:
        for case in cases:
            ds = data[case.id]
            for wing in ("east", "west", "service"):
                check(f"{case.id} · rooms_in_wing({wing})", attempt(r, module.rooms_in_wing, ds, wing),
                      answers.rooms_in_wing(case, wing))  # fmt: skip
                got = attempt(r, module.unguarded_ways_in, ds, wing)
                check(f"{case.id} · unguarded_ways_in({wing})", set(got) if got is not None else None,
                      answers.unguarded_ways_in(case, wing))  # fmt: skip
            start, end = case.at(case.meta["last_seen"][11:]), case.at(case.meta["discovered"][11:])
            for door in ("D07", "D13", "D20", "D25"):
                got = attempt(r, module.swipes_at, ds, door, start, end)
                got = sorted((t, str(b), bool(ok)) for t, b, ok in got) if got is not None else None
                check(f"{case.id} · swipes_at({door})", got, answers.swipes_at(case, door, start, end))
    except NotStarted:
        pass
    tally(r, right, total, "answers")


def _shapes(module, practice, data, r: Result) -> None:
    from pyshacl import validate

    try:
        shapes = Graph().parse(module.SHAPES, format="turtle")
    except Exception as e:  # noqa: BLE001
        r.fail(f"{module.SHAPES} doesn't parse as Turtle: {e}")
        return
    total = right = 0
    try:
        for case in practice:
            total += 1
            clean = _union(data[case.id])
            if not isinstance(clean, Graph):  # to_rdf failed on this case, or didn't return RDF
                r.fail(f"{case.id}: no RDF from to_rdf to validate")
                continue
            try:
                conforms, _, text = validate(clean, shacl_graph=shapes, inference="none")
            except Exception as e:  # noqa: BLE001
                r.fail(f"{case.id}: pyshacl couldn't validate with your shapes: {e}")
                continue
            if conforms:
                right += 1
            else:
                first = next((line.strip() for line in text.splitlines() if "Message" in line), "")
                r.fail(f"{case.id}: the clean case doesn't conform. {first}")
            for label, broken in _broken(case).items():
                total += 1
                g = _union(attempt(r, module.to_rdf, broken))
                if not isinstance(g, Graph):
                    continue
                try:
                    conforms, _, _ = validate(g, shacl_graph=shapes, inference="none")
                except Exception as e:  # noqa: BLE001
                    r.fail(f"{case.id}: pyshacl couldn't validate {label} with your shapes: {e}")
                    continue
                if conforms:
                    r.fail(f"{case.id}: {label} passes your shapes")
                else:
                    right += 1
    except NotStarted:
        pass
    tally(r, right, total, "cases judged right")


def _alibis(module, cases, data, r: Result) -> None:
    total = right = 0
    broke = []
    try:
        for case in cases:
            m = case.meta
            wing = m["room"]["wing"]
            start, end = case.at(m["last_seen"][11:]), case.at(m["discovered"][11:])
            truth = json.loads((case.path / "truth.json").read_text(encoding="utf-8"))
            there = _truly_there(case, truth, wing, start, end)
            people = [s.employee_id for s in case.staff] + [g.guest_id for g in case.guests]
            people += [w.contractor_id for w in case.contractors]
            for pid in people:
                total += 1
                got = attempt(r, module.alibi, data[case.id], pid, wing, start, end)
                want = answers.alibi(case, pid, wing, start, end)
                if got is None:
                    continue
                if got == want:
                    right += 1
                    if got == "elsewhere" and pid in there:
                        broke.append(f"{case.id} · {pid}")
                else:
                    r.fail(f"{case.id} · {pid}: got {got!r}, want {want!r}")
    except NotStarted:
        pass
    tally(r, right, total, "people")
    if r.passed and broke:
        r.notes.append("'elsewhere', and yet they were in the wing: " + ", ".join(broke) + ". Which assumption broke?")


def _truly_there(case: Case, truth: dict, wing: str, start, end) -> set[str]:
    inside = answers.rooms_in_wing(case, wing)
    ids = {p["id"]: next((k for k in p["keys"] if k[:2] in ("E-", "G-", "C-")), None) for p in truth["people"]}
    out = set()
    for s in truth["presence"]:
        if (
            s["room"] in inside
            and s["start"] < end.isoformat(timespec="minutes")
            and s["end"] > start.isoformat(timespec="minutes")
        ):
            if ids.get(s["person"]):
                out.add(ids[s["person"]])
    return out


def _signins(module, cases, r: Result) -> None:
    linked = correct = should = 0
    try:
        for case in cases:
            gold = json.loads((case.path / "truth.json").read_text(encoding="utf-8"))["signin"]
            got = attempt(r, module.resolve_signins, case)
            if got is None:
                continue
            if len(got) != len(case.signins):
                r.fail(f"{case.id}: {len(got)} answers for {len(case.signins)} rows")
                continue
            for i, (g, w) in enumerate(zip(got, gold, strict=True)):
                should += w is not None
                if g is not None:
                    linked += 1
                    correct += g == w
                if g != w and len(r.details) < 12:
                    row = case.signins[i]
                    r.details.append(
                        f"{case.id} · row {i + 1} '{row.name}' {row.phone or '(no phone)'}: got {g}, want {w}"
                    )
    except NotStarted:
        r.started = r.passed = False
        return
    precision = correct / linked if linked else 0.0
    recall = correct / should if should else 0.0
    r.score = f"precision {precision:.2f}, recall {recall:.2f}"
    r.passed = precision >= 0.95 and recall >= 0.9 and not any("answers for" in d for d in r.details)
    if r.passed:
        r.details.clear()
    else:
        r.details.insert(0, "Needs precision ≥ 0.95 and recall ≥ 0.90 over all packs.")
