"""Milestone 2 · The case ontology: a reference solution (the fast path: rdflib, SPARQL, rapidfuzz).

Spoilers. `heist use-reference 2` copies this, m2_heist.ttl and m2_shapes.ttl over your files.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from rapidfuzz.distance import JaroWinkler
from rdflib import RDF, XSD, Dataset, Literal, Namespace, URIRef

from heist.case import Case

HERE = Path(__file__).resolve().parent
ONTOLOGY = HERE / "m2_heist.ttl"
SHAPES = HERE / "m2_shapes.ttl"

H = Namespace("https://kube.ar/heist/ontology#")
DATA = "https://kube.ar/heist/data/"
SOURCE = "https://kube.ar/heist/source/"


def node(kind: str, key) -> URIRef:
    return URIRef(f"{DATA}{kind}/{str(key).replace(' ', '_').replace('+', '')}")


def to_rdf(case: Case) -> Dataset:
    ds = Dataset(default_union=True)  # queries without GRAPH see every named graph
    g = {name: ds.graph(URIRef(SOURCE + name)) for name in
         ("hr", "events", "vendors", "security", "facilities", "telecom", "finance")}  # fmt: skip

    def person(graph, pid, cls, name, role):
        p = node("person", pid)
        graph.add((p, RDF.type, cls))
        graph.add((p, H.id, Literal(pid)))
        graph.add((p, H.name, Literal(name)))
        graph.add((p, H.role, Literal(role)))
        return p

    def phone(graph, owner, number):
        ph = node("phone", number)
        graph.add((ph, RDF.type, H.Phone))
        graph.add((ph, H.id, Literal(number)))
        if owner is not None:
            graph.add((owner, H.hasPhone, ph))
        return ph

    for s in case.staff:
        phone(g["hr"], person(g["hr"], s.employee_id, H.StaffMember, s.full_name, s.role), s.phone)
    for x in case.guests:
        last, _, first = x.name.partition(", ")
        p = person(g["events"], x.guest_id, H.Guest, f"{first} {last}", x.category)
        phone(g["events"], p, x.phone)
        g["events"].add((p, H.invitedBy, node("person", x.invited_by)))
    for seat in case.seating:
        table = node("table", seat.table)
        g["events"].add((table, RDF.type, H.Table))
        g["events"].add((node("person", seat.attendee_id), H.satAt, table))
    for w in case.contractors:
        p = person(g["vendors"], w.contractor_id, H.Contractor, w.worker_name, w.job)
        phone(g["vendors"], p, w.phone)
        company = node("company", w.company)
        g["vendors"].add((company, RDF.type, H.Company))
        g["vendors"].add((company, H.name, Literal(w.company)))
        g["vendors"].add((p, H.worksFor, company))

    for r in case.rooms:
        room, wing = node("room", r.room_id), node("wing", r.wing)
        g["facilities"].add((room, RDF.type, H.Room))
        g["facilities"].add((room, H.id, Literal(r.room_id)))
        g["facilities"].add((room, H.name, Literal(r.name)))
        g["facilities"].add((wing, RDF.type, H.Wing))
        g["facilities"].add((wing, H.id, Literal(r.wing)))
        g["facilities"].add((room, H.inWing, wing))
    for d in case.doors:
        door = node("door", d.door_id)
        sec = g["security"]
        sec.add((door, RDF.type, H.Door))
        sec.add((door, H.id, Literal(d.door_id)))
        sec.add((door, H.hasReader, Literal(d.has_reader)))
        sec.add((door, H.kind, Literal(d.kind)))
        sec.add((door, H.connects, node("room", d.room_a)))
        sec.add((door, H.connects, node("room", d.room_b)))
    for b in case.badges:
        badge = node("badge", b.badge_id)
        g["security"].add((badge, RDF.type, H.Badge))
        g["security"].add((badge, H.id, Literal(b.badge_id)))
        for z in b.zones:
            g["security"].add((badge, H.zone, Literal(z)))
        g["security"].add((node("person", b.holder_id), H.holds, badge))
    for i, s in enumerate(case.swipes):
        ev = node("swipe", i)
        sec = g["security"]
        sec.add((ev, RDF.type, H.Swipe))
        sec.add((ev, H.at, Literal(s.time, datatype=XSD.dateTime)))
        sec.add((ev, H.badge, node("badge", s.badge_id)))
        sec.add((ev, H.door, node("door", s.door_id)))
        sec.add((ev, H.toRoom, node("room", s.to_room)))
        sec.add((ev, H.granted, Literal(s.granted)))

    for i, c in enumerate(case.calls):
        ev = node("call", i)
        tel = g["telecom"]
        tel.add((ev, RDF.type, H.Call))
        tel.add((ev, H.at, Literal(c.start, datatype=XSD.dateTime)))
        tel.add((ev, H.caller, phone(tel, None, c.caller)))
        tel.add((ev, H.callee, phone(tel, None, c.callee)))
        tel.add((ev, H.seconds, Literal(c.seconds)))
    fin = g["finance"]
    for a in case.accounts:
        acc = node("account", a.account_id)
        fin.add((acc, RDF.type, H.Account))
        fin.add((acc, H.id, Literal(a.account_id)))
        fin.add((acc, H.name, Literal(a.holder_name)))
        fin.add((acc, H.contactPhone, phone(fin, None, a.contact_phone)))
    for i, t in enumerate(case.transfers):
        ev = node("transfer", i)
        fin.add((ev, RDF.type, H.Transfer))
        fin.add((ev, H.at, Literal(t.time, datatype=XSD.dateTime)))
        fin.add((ev, H.fromAccount, node("account", t.from_account)))
        fin.add((ev, H.toAccount, node("account", t.to_account)))
        fin.add((ev, H.amount, Literal(t.amount)))
        fin.add((ev, H.reference, Literal(t.reference)))
    return ds


PREFIX = "PREFIX : <https://kube.ar/heist/ontology#>\n"


def _ids(ds: Dataset, query: str, **bindings) -> set[str]:
    return {str(row[0]) for row in ds.query(PREFIX + query, initBindings=bindings)}


def rooms_in_wing(ds: Dataset, wing: str) -> set[str]:
    return _ids(ds, "SELECT ?id WHERE { ?r :inWing ?w ; :id ?id . ?w :id ?wing }", wing=Literal(wing))


def unguarded_ways_in(ds: Dataset, wing: str) -> set[str]:
    return _ids(
        ds,
        """SELECT ?id WHERE {
            ?d :hasReader false ; :id ?id ; :connects ?in, ?out .
            ?in :inWing/:id ?wing .
            ?out :inWing/:id ?other . FILTER (?other != ?wing)
        }""",
        wing=Literal(wing),
    )


def swipes_at(ds: Dataset, door_id: str, start: datetime, end: datetime) -> list[tuple[datetime, str, bool]]:
    rows = ds.query(
        PREFIX
        + """SELECT ?t ?b ?ok WHERE {
            ?s a :Swipe ; :door/:id ?door ; :at ?t ; :badge/:id ?b ; :granted ?ok .
            FILTER (?t >= ?start && ?t < ?end)
        }""",
        initBindings={
            "door": Literal(door_id),
            "start": Literal(start, datatype=XSD.dateTime),
            "end": Literal(end, datatype=XSD.dateTime),
        },
    )
    return sorted((r[0].toPython(), str(r[1]), bool(r[2].toPython())) for r in rows)


SIX = ("hr", "events", "vendors", "security", "telecom", "finance")


def sources_of(ds: Dataset, person_id: str) -> set[str]:
    """Named graphs holding a triple about the person, their phone, or an account on their phone."""
    rows = ds.query(
        PREFIX
        + """SELECT DISTINCT ?g WHERE {
            ?p :id ?pid .
            { GRAPH ?g { { ?p ?x ?y } UNION { ?y ?x ?p } } }
            UNION { ?p :hasPhone ?ph . GRAPH ?g { { ?ph ?x ?y } UNION { ?y ?x ?ph } } }
        }""",
        initBindings={"pid": Literal(person_id)},
    )
    names = {str(r[0]).removeprefix(SOURCE) for r in rows}
    return names & set(SIX)


def alibi(ds: Dataset, person_id: str, wing: str, start: datetime, end: datetime) -> str:
    badge = _ids(ds, "SELECT ?b WHERE { ?p :id ?pid ; :holds/:id ?b }", pid=Literal(person_id))
    if not badge:
        return "unknown"
    swipes = sorted(
        (r[0].toPython(), str(r[1]))
        for r in ds.query(
            PREFIX + "SELECT ?t ?room WHERE { ?s :badge/:id ?b ; :granted true ; :at ?t ; :toRoom/:id ?room }",
            initBindings={"b": Literal(next(iter(badge)))},
        )
    )
    spans = [(room, t, nxt[0] if nxt else None) for (t, room), nxt in zip(swipes, [*swipes[1:], None])]
    spans = [s for s in spans if s[1] < end and (s[2] is None or s[2] > start)]
    if not spans or spans[0][1] > start:
        return "unknown"
    inside = rooms_in_wing(ds, wing)
    if any(room in inside for room, _, _ in spans):
        return "placed"
    region = _regions(ds)
    return "elsewhere" if all(not (region[room] & inside) for room, _, _ in spans) else "unknown"


_region_cache: dict[int, dict[str, frozenset[str]]] = {}


def _regions(ds: Dataset) -> dict[str, frozenset[str]]:
    if id(ds) in _region_cache:
        return _region_cache[id(ds)]
    links: dict[str, set[str]] = {}
    for a, b in ds.query(
        PREFIX + "SELECT ?a ?b WHERE { ?d :hasReader false ; :connects ?x, ?y . ?x :id ?a . ?y :id ?b }"
    ):
        links.setdefault(str(a), set()).add(str(b))
    rooms = _ids(ds, "SELECT ?id WHERE { ?r a :Room ; :id ?id }")
    out: dict[str, frozenset[str]] = {}
    for room in rooms:
        if room in out:
            continue
        seen, stack = {room}, [room]
        while stack:
            for nxt in links.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for r in seen:
            out[r] = frozenset(seen)
    _region_cache[id(ds)] = out
    return out


# ── Entity resolution: who signed the sheet ───────────────────────────────────

NICK = {"kas": "kasimir", "val": "valentin", "toby": "tobias", "teo": "matteo", "bea": "beatriz", "aurel": "aurelio",
        "gid": "gideon", "quin": "quentin", "sersha": "saoirse", "siggi": "sigrid", "xime": "ximena", "nadi": "nadia",
        "dami": "damian", "dima": "dmitri", "lei": "leila", "quino": "joaquin", "zee": "zainab"}  # fmt: skip


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone)
    return d[-10:] if len(d) >= 10 else ""


def _name_parts(written: str) -> tuple[str, str]:
    """(first, last) from 'Mara Vos', 'Vos, Mara', 'M. Vos', 'mara vos'."""
    s = _plain(written).strip()
    if "," in s:
        last, first = (x.strip() for x in s.split(",", 1))
    else:
        parts = s.replace(".", "").split()
        first, last = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else ("", s)
    return NICK.get(first, first), last


def _score(row_first: str, row_last: str, first: str, last: str) -> float:
    surname = JaroWinkler.similarity(row_last, last)
    if not row_first:
        given = 0.5
    elif len(row_first) == 1:
        given = 1.0 if first.startswith(row_first) else 0.0
    else:
        given = JaroWinkler.similarity(row_first, first)
    return 0.6 * surname + 0.4 * given


def resolve_signins(case: Case) -> list[str | None]:
    guests = []
    for g in case.guests:
        last, _, first = g.name.partition(", ")
        guests.append((g.guest_id, _plain(first), _plain(last), _digits(g.phone)))
    candidates = []
    for i, row in enumerate(case.signins):
        if "(with" in row.name:
            continue  # someone's plus-one, written as such
        first, last = _name_parts(row.name)
        digits = _digits(row.phone)
        for gid, gfirst, glast, gdigits in guests:
            score = _score(first, last, gfirst, glast)
            if digits and digits == gdigits:
                score += 0.3  # strong evidence, but a plus-one may share the host's number
            candidates.append((score, i, gid))
    out: list[str | None] = [None] * len(case.signins)
    used: set[str] = set()
    for score, i, gid in sorted(candidates, reverse=True):
        if score < 0.85 or out[i] is not None or gid in used:
            continue
        out[i] = gid
        used.add(gid)
    return out
