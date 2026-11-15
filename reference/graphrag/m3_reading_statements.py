"""Milestone 3 · Reading the statements: a reference solution (fast path: networkx, rapidfuzz, heist.llm).

Spoilers. `heist use-reference 3` copies this over your file.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta
from typing import Any

import networkx as nx
from rapidfuzz.distance import JaroWinkler

from heist.case import Case, Document

PREDICATES = {
    "arrived_at": "the subject arrived (object: none)",
    "was_in": "the subject was in a room (object: a room id, R03)",
    "saw": "the subject saw someone (object: a person id)",
    "talked_to": "the subject talked to someone (object: a person id)",
    "called": "the subject phoned someone (object: a person id)",
    "knows": "the subject knows someone: family, friend, flatmate (object: a person id)",
    "money_trouble": "the subject is short of money (object: none)",
    "led_tour": "the subject led guests through the galleries (object: none)",
}
PERSON_OBJECT = {"saw", "talked_to", "called", "knows"}
ROOM_OBJECT = {"was_in"}


# ── The lexical graph ─────────────────────────────────────────────────────────


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def lexical_graph(case: Case) -> nx.DiGraph:
    g = nx.DiGraph()
    for doc in case.documents:
        d = ("doc", doc.doc_id)
        g.add_node(d, kind="document", title=doc.title, author=doc.author)
        chunks = paragraphs(doc.text)
        for i, text in enumerate(chunks):
            c = ("chunk", doc.doc_id, i)
            g.add_node(c, kind="chunk", text=text)
            g.add_edge(c, d, type="PART_OF")
            if i:
                g.add_edge(("chunk", doc.doc_id, i - 1), c, type="NEXT")
    return g


def lexical_summary(graph: nx.DiGraph) -> dict[str, int]:
    kinds = [d["kind"] for _, d in graph.nodes(data=True)]
    return {
        "documents": kinds.count("document"),
        "chunks": kinds.count("chunk"),
        "next": sum(1 for _, _, e in graph.edges(data=True) if e["type"] == "NEXT"),
    }


def neighborhood(graph: nx.DiGraph, doc_id: str, index: int) -> dict:
    node = ("chunk", doc_id, index)
    before = [u for u, _, e in graph.in_edges(node, data=True) if e["type"] == "NEXT"]
    after = [v for _, v, e in graph.out_edges(node, data=True) if e["type"] == "NEXT"]
    return {
        "title": graph.nodes[("doc", doc_id)]["title"],
        "before": graph.nodes[before[0]]["text"] if before else None,
        "chunk": graph.nodes[node]["text"],
        "after": graph.nodes[after[0]]["text"] if after else None,
    }


# ── Linking names to people ───────────────────────────────────────────────────

NICK = {"kas": "kasimir", "val": "valentin", "toby": "tobias", "teo": "matteo", "bea": "beatriz", "aurel": "aurelio",
        "gid": "gideon", "quin": "quentin", "sersha": "saoirse", "siggi": "sigrid", "xime": "ximena", "nadi": "nadia",
        "dami": "damian", "dima": "dmitri", "lei": "leila", "quino": "joaquin", "zee": "zainab"}  # fmt: skip
ROLE_WORDS = {
    "the director": "Director", "the conservator": "Conservator", "the registrar": "Registrar",
    "the head of security": "Head of Security", "the events manager": "Events Manager",
    "the facilities technician": "Facilities Technician", "the education officer": "Education Officer",
    "the chef": "Chef", "the sound technician": "AV Technician", "the cleaner": "Cleaner",
    "one of the guards": "Security Guard", "one of the waiters": "Waiter", "one of the curators": "Curator",
    "one of the donors": "donor", "a collector": "collector", "an artist": "artist", "a board member": "board member",
    "a journalist": "journalist",
}  # fmt: skip


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)).strip()


class People:
    """Everyone in the case's lists, by first name, surname and role."""

    def __init__(self, case: Case):
        self.rows: list[tuple[str, str, str, str]] = []  # (id, first, last, role)
        for s in case.staff:
            first, _, last = s.full_name.partition(" ")
            self.rows.append((s.employee_id, _plain(first), _plain(last), s.role))
        for g in case.guests:
            last, _, first = g.name.partition(", ")
            self.rows.append((g.guest_id, _plain(first), _plain(last), g.category))
        for w in case.contractors:
            first, _, last = w.worker_name.partition(" ")
            self.rows.append((w.contractor_id, _plain(first), _plain(last), w.job))

    def resolve(self, text: str) -> str | None:
        words = _plain(text).split()
        if not words:
            return None
        if len(words) >= 2:
            first, last = NICK.get(words[0], words[0]), " ".join(words[1:])
            scored = [(JaroWinkler.similarity(last, r[2]), r[0]) for r in self.rows if r[1] == first]
            best = max(scored, default=(0.0, None))
            return best[1] if best[0] >= 0.88 else None
        word = NICK.get(words[0], words[0])
        by_first = [r[0] for r in self.rows if r[1] == word]
        by_last = [r[0] for r in self.rows if r[2] == word]
        found = by_first if by_first else by_last
        return found[0] if len(found) == 1 else None

    def by_role(self, role: str) -> str | None:
        found = [r[0] for r in self.rows if r[3] == role]
        return found[0] if len(found) == 1 else None


NAME = re.compile(r"[A-ZÀ-Ý][\w'’-]+(?:\s+(?:Van\s+)?[A-ZÀ-Ý][\w'’-]+)?")


def find_people(case: Case, doc: Document) -> list[tuple[int, int, str | None]]:
    people = People(case)
    found: list[tuple[int, int, str | None]] = []
    taken: list[tuple[int, int]] = []
    for phrase, role in ROLE_WORDS.items():
        for m in re.finditer(re.escape(phrase), doc.text, re.IGNORECASE):
            found.append((m.start(), m.end(), people.by_role(role)))
            taken.append((m.start(), m.end()))
    for m in NAME.finditer(doc.text):
        if any(a < m.end() and m.start() < b for a, b in taken):
            continue
        pid = people.resolve(m.group())
        if pid is None and " " in m.group():  # "At Mara" → try the last word alone
            last = m.group().split()[-1]
            pid = people.resolve(last)
            if pid:
                found.append((m.end() - len(last), m.end(), pid))
            continue
        if pid:
            found.append((m.start(), m.end(), pid))
    return sorted(found)


# ── Claims, with the LLM ──────────────────────────────────────────────────────

SYSTEM = """You extract claims from documents written after a theft at a museum gala.

Use only these predicates:
{predicates}

Rules:
- Extract every claim the text makes, true or not: statements can lie. One claim per fact.
- subject: the person exactly as the text names them, or "I" for the author.
- object: for was_in, the room's name as written; for saw, talked_to, called and knows, the person
  as the text names them; otherwise "".
- time: the time the text gives for this claim, as 24-hour HH:MM, else "". The evening runs from
  17:00 to 01:00, so "around 7:35" means 19:35 and "a quarter past ten" means 22:15.
- Don't invent claims the text doesn't make."""

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string", "enum": sorted(PREDICATES)},
                    "object": {"type": "string"},
                    "time": {"type": "string"},
                },
                "required": ["subject", "predicate", "object", "time"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def read_document(case: Case, doc: Document, llm: Any) -> list[dict]:
    system = SYSTEM.format(predicates="\n".join(f"- {k}: {v}" for k, v in PREDICATES.items()))
    answer = llm.json(f"Author: {doc.author}\nTitle: {doc.title}\n\n{doc.text}", SCHEMA, system=system)
    people = People(case)
    author = people.resolve(doc.author)
    rooms = {_plain(r.name): r.room_id for r in case.rooms}
    claims = []
    for raw in answer.get("claims", []):
        subject = author if raw["subject"].strip().lower() in ("i", "me") else _who(people, raw["subject"])
        predicate = raw["predicate"]
        obj: str | None = None
        if predicate in ROOM_OBJECT:
            name = _plain(raw["object"]).removeprefix("the ")
            obj = rooms.get(name)
        elif predicate in PERSON_OBJECT:
            obj = author if raw["object"].strip().lower() in ("i", "me") else _who(people, raw["object"])
        time = raw["time"] if re.fullmatch(r"\d{2}:\d{2}", raw["time"] or "") else None
        if predicate not in PREDICATES:
            status = "rejected"
        elif subject is None or ((predicate in ROOM_OBJECT | PERSON_OBJECT) and obj is None):
            status = "review"  # a person or room we couldn't link: a human decides
        else:
            status = "accepted"
        claims.append({"subject": subject, "predicate": predicate, "object": obj, "time": time, "status": status})
    return claims


def _who(people: People, text: str) -> str | None:
    text = text.strip()
    for phrase, role in ROLE_WORDS.items():
        if text.lower() == phrase:
            return people.by_role(role)
    return people.resolve(text)


# ── Checking claims against the keycard log ───────────────────────────────────


def contradictions(case: Case, claims: list[dict]) -> list[int]:
    badge_of = {b.holder_id: b.badge_id for b in case.badges}
    swipes: dict[str, list] = {}
    for s in sorted(case.swipes, key=lambda s: s.time):
        if s.granted:
            swipes.setdefault(s.badge_id, []).append(s)
    links: dict[str, set[str]] = {}
    for d in case.doors:
        if not d.has_reader:
            links.setdefault(d.room_a, set()).add(d.room_b)
            links.setdefault(d.room_b, set()).add(d.room_a)

    def region(room: str) -> set[str]:
        seen, stack = {room}, [room]
        while stack:
            for nxt in links.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    out = []
    for i, c in enumerate(claims):
        if c["predicate"] != "was_in" or not c.get("time") or c["subject"] not in badge_of:
            continue
        hh, mm = map(int, c["time"].split(":"))
        at = case.date + timedelta(days=1 if hh < 12 else 0, hours=hh, minutes=mm)
        start, end = at - timedelta(minutes=10), at + timedelta(minutes=10)
        rows = swipes.get(badge_of[c["subject"]], [])
        spans = [(s.to_room, s.time, n.time if n else None) for s, n in zip(rows, [*rows[1:], None])]
        spans = [s for s in spans if s[1] < end and (s[2] is None or s[2] > start)]
        if spans and spans[0][1] <= start and all(c["object"] not in region(room) for room, _, _ in spans):
            out.append(i)
    return out
