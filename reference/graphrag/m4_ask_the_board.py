"""Milestone 4 · Ask the board: a reference solution (the fast path: Neo4j, Cypher, a vector index).

Spoilers. `heist use-reference 4` copies this over your file. It uses the milestone 3 reference's
linker, loaded from reference/graphrag/, so it works whatever your own milestone 3 file holds.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

import networkx as nx
from neo4j import GraphDatabase

from heist.case import ROOT, Case
from heist.vectors import embed

# By path from reference/, never from this file's folder: after `use-reference 4` that's your folder.
M3 = ROOT / "reference" / "graphrag" / "m3_reading_statements.py"


def _m3():
    spec = importlib.util.spec_from_file_location("m3_for_m4", M3)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Board:
    driver: Any
    case: Case

    def q(self, query: str, **params) -> list[dict]:
        records, _, _ = self.driver.execute_query(query, parameters_=params)
        return [r.data() for r in records]


def _driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "heist-password"))
    return GraphDatabase.driver(uri, auth=auth)


_DRIVER = None


def store(case: Case) -> Board:
    """Load one case into Neo4j (replacing whatever was there) and return a handle to it."""
    global _DRIVER
    _DRIVER = _DRIVER or _driver()
    b = Board(_DRIVER, case)
    b.q("MATCH (n) DETACH DELETE n")
    people = [
        {"id": s.employee_id, "name": s.full_name, "kind": "staff", "role": s.role, "phone": s.phone}
        for s in case.staff
    ]
    for g in case.guests:
        last, _, first = g.name.partition(", ")
        people.append(
            {"id": g.guest_id, "name": f"{first} {last}", "kind": "guest", "role": g.category, "phone": g.phone}
        )
    people += [{"id": w.contractor_id, "name": w.worker_name, "kind": "contractor", "role": w.job, "phone": w.phone,
                "company": w.company} for w in case.contractors]  # fmt: skip
    b.q("""UNWIND $rows AS r CREATE (p:Person {id: r.id, name: r.name, kind: r.kind, role: r.role})
           MERGE (ph:Phone {number: r.phone}) CREATE (p)-[:HAS_PHONE]->(ph)
           FOREACH (c IN CASE WHEN r.company IS NULL THEN [] ELSE [r.company] END |
             MERGE (co:Company {name: c}) CREATE (p)-[:WORKS_FOR]->(co))""", rows=people)  # fmt: skip
    b.q("UNWIND $rows AS r MATCH (h:Person {id: r.host}), (g:Person {id: r.guest}) CREATE (h)-[:INVITED]->(g)",
        rows=[{"host": g.invited_by, "guest": g.guest_id} for g in case.guests])  # fmt: skip
    b.q("UNWIND $rows AS r MATCH (p:Person {id: r.who}) MERGE (t:Table {number: r.table}) CREATE (p)-[:SAT_AT]->(t)",
        rows=[{"who": s.attendee_id, "table": s.table} for s in case.seating])  # fmt: skip
    b.q("UNWIND $rows AS r CREATE (:Room {id: r.id, name: r.name}) MERGE (w:Wing {id: r.wing})",
        rows=[{"id": r.room_id, "name": r.name, "wing": r.wing} for r in case.rooms])  # fmt: skip
    b.q("UNWIND $rows AS r MATCH (room:Room {id: r.id}), (w:Wing {id: r.wing}) CREATE (room)-[:IN_WING]->(w)",
        rows=[{"id": r.room_id, "wing": r.wing} for r in case.rooms])  # fmt: skip
    b.q("""UNWIND $rows AS r MATCH (a:Room {id: r.a}), (c:Room {id: r.b})
           CREATE (d:Door {id: r.id, reader: r.reader, kind: r.kind}) CREATE (d)-[:CONNECTS]->(a) CREATE (d)-[:CONNECTS]->(c)""",
        rows=[{"id": d.door_id, "a": d.room_a, "b": d.room_b, "reader": d.has_reader, "kind": d.kind} for d in case.doors])  # fmt: skip
    b.q("UNWIND $rows AS r MATCH (p:Person {id: r.holder}) CREATE (p)-[:HOLDS]->(:Badge {id: r.id})",
        rows=[{"id": x.badge_id, "holder": x.holder_id} for x in case.badges])  # fmt: skip
    b.q("""UNWIND $rows AS r MATCH (bg:Badge {id: r.badge}), (d:Door {id: r.door}), (room:Room {id: r.room})
           CREATE (s:Swipe {at: r.at, granted: r.granted}) CREATE (s)-[:BY]->(bg) CREATE (s)-[:AT]->(d)
           CREATE (s)-[:INTO]->(room)""",
        rows=[{"badge": s.badge_id, "door": s.door_id, "room": s.to_room, "at": s.time, "granted": s.granted}
              for s in case.swipes])  # fmt: skip
    b.q("""UNWIND $rows AS r MERGE (a:Phone {number: r.a}) MERGE (c:Phone {number: r.b})
           CREATE (call:Call {at: r.at, seconds: r.s}) CREATE (call)-[:FROM]->(a) CREATE (call)-[:TO]->(c)""",
        rows=[{"a": c.caller, "b": c.callee, "at": c.start, "s": c.seconds} for c in case.calls])  # fmt: skip
    b.q("""UNWIND $rows AS r MERGE (ph:Phone {number: r.phone})
           CREATE (a:Account {id: r.id, holder: r.holder}) CREATE (a)-[:CONTACT]->(ph)""",
        rows=[{"id": a.account_id, "holder": a.holder_name, "phone": a.contact_phone} for a in case.accounts])  # fmt: skip
    b.q("""UNWIND $rows AS r MATCH (a:Account {id: r.a}), (c:Account {id: r.b})
           CREATE (t:Transfer {at: r.at, amount: r.amount, reference: r.ref})
           CREATE (t)-[:FROM_ACCOUNT]->(a) CREATE (t)-[:TO_ACCOUNT]->(c)""",
        rows=[{"a": t.from_account, "b": t.to_account, "at": t.time, "amount": t.amount, "ref": t.reference}
              for t in case.transfers])  # fmt: skip

    # The documents: a lexical graph with embeddings, and who each paragraph mentions.
    m3 = _m3()
    chunks = []
    for d in case.documents:
        paragraphs = (
            m3.paragraphs(d.text) if hasattr(m3, "paragraphs") else [p for p in d.text.split("\n\n") if p.strip()]
        )
        mentions = m3.find_people(case, d)
        offset = 0
        for i, text in enumerate(paragraphs):
            start = d.text.index(text, offset)
            end = start + len(text)
            offset = end
            who = sorted({pid for a, z, pid in mentions if pid and start <= a < end})
            chunks.append({"doc": d.doc_id, "i": i, "text": text, "who": who})
    vectors = embed([c["text"] for c in chunks]) if chunks else []
    for c, v in zip(chunks, vectors):
        c["v"] = [float(x) for x in v]
    b.q("UNWIND $rows AS r CREATE (:Document {id: r.id, title: r.title, kind: r.kind, author: r.author})",
        rows=[{"id": d.doc_id, "title": d.title, "kind": d.kind, "author": d.author} for d in case.documents])  # fmt: skip
    b.q("""UNWIND $rows AS r MATCH (d:Document {id: r.doc})
           CREATE (c:Chunk {doc: r.doc, index: r.i, text: r.text, embedding: r.v}) CREATE (c)-[:PART_OF]->(d)
           WITH c, r UNWIND r.who AS pid MATCH (p:Person {id: pid}) CREATE (c)-[:MENTIONS]->(p)""", rows=chunks)  # fmt: skip
    b.q("""MATCH (a:Chunk), (c:Chunk) WHERE a.doc = c.doc AND c.index = a.index + 1 CREATE (a)-[:NEXT]->(c)""")
    b.q(f"""CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS FOR (c:Chunk) ON c.embedding
            OPTIONS {{indexConfig: {{`vector.dimensions`: {len(chunks[0]['v']) if chunks else 256},
            `vector.similarity_function`: 'cosine'}}}}""")  # fmt: skip
    b.q("CALL db.awaitIndexes(120)")
    return b


def store_summary(board: Board) -> dict[str, int]:
    count = lambda label: board.q(f"MATCH (n:{label}) RETURN count(n) AS n")[0]["n"]  # noqa: E731
    return {
        "people": count("Person"), "badges": count("Badge"), "rooms": count("Room"), "doors": count("Door"),
        "swipes": count("Swipe"), "calls": count("Call"), "transfers": count("Transfer"),
        "documents": count("Document"), "chunks": count("Chunk"),
    }  # fmt: skip


# ── Expert templates ──────────────────────────────────────────────────────────

TEMPLATES = {
    "who_was_in": """
        MATCH (:Wing {id: $wing})<-[:IN_WING]-(r:Room)<-[:INTO]-(s:Swipe {granted: true})-[:BY]->(b:Badge)<-[:HOLDS]-(p:Person)
        WHERE s.at < $end
        OPTIONAL MATCH (n:Swipe {granted: true})-[:BY]->(b) WHERE n.at > s.at
        WITH p, s, min(n.at) AS until
        WHERE until IS NULL OR until > $start
        RETURN DISTINCT p.id AS id LIMIT 1000""",
    "callers_of": """
        MATCH (:Person {id: $person})-[:HAS_PHONE]->(mine:Phone)<-[:FROM|TO]-(c:Call)-[:FROM|TO]->(other:Phone)
        WHERE other <> mine AND c.at >= $start AND c.at < $end
        OPTIONAL MATCH (q:Person)-[:HAS_PHONE]->(other)
        RETURN DISTINCT coalesce(q.id, other.number) AS id LIMIT 1000""",
    "unguarded_ways_in": """
        MATCH (d:Door {reader: false})-[:CONNECTS]->(:Room)-[:IN_WING]->(:Wing {id: $wing}),
              (d)-[:CONNECTS]->(:Room)-[:IN_WING]->(w:Wing) WHERE w.id <> $wing
        RETURN DISTINCT d.id AS id LIMIT 1000""",
}


def ask_template(board: Board, name: str, **params) -> set[str]:
    return {row["id"] for row in board.q(TEMPLATES[name], **params)}


# ── Model-written queries, checked before they run ────────────────────────────

LABELS = {"Person", "Phone", "Company", "Table", "Room", "Wing", "Door", "Badge", "Swipe", "Call", "Account",
          "Transfer", "Document", "Chunk"}  # fmt: skip
RELS = {"HAS_PHONE", "WORKS_FOR", "INVITED", "SAT_AT", "IN_WING", "CONNECTS", "HOLDS", "BY", "AT", "INTO", "FROM",
        "TO", "CONTACT", "FROM_ACCOUNT", "TO_ACCOUNT", "PART_OF", "NEXT", "MENTIONS"}  # fmt: skip
# Clause keywords, but not labels: `:Call` is a label, `CALL` a procedure call.
WRITES = re.compile(r"(?<![:\w])(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|CALL)\b", re.IGNORECASE)


def validate_query(query: str) -> bool:
    """Read-only, only labels and relationships the board has, and a LIMIT of at most 1000."""
    text = re.sub(r"'[^']*'|\"[^\"]*\"", "''", query)  # ignore string literals
    if WRITES.search(text) or not re.search(r"\bMATCH\b", text, re.I) or not re.search(r"\bRETURN\b", text, re.I):
        return False
    limit = re.search(r"\bLIMIT\s+(\d+)\s*;?\s*$", text, re.I)
    if not limit or int(limit.group(1)) > 1000:
        return False
    labels = set(re.findall(r"\(\s*\w*\s*:\s*(\w+)", text))
    rels = {r for group in re.findall(r"\[\s*\w*\s*:\s*([\w|:]+)", text) for r in re.split(r"[|:]", group) if r}
    return labels <= LABELS and rels <= RELS


SCHEMA_TEXT = """Nodes: Person {id, name, kind, role}, Phone {number}, Company {name}, Table {number}, Room {id, name},
Wing {id}, Door {id, reader, kind}, Badge {id}, Swipe {at, granted}, Call {at, seconds}, Account {id, holder},
Transfer {at, amount, reference}, Document {id, title, kind, author}, Chunk {doc, index, text}.
Relationships: (Person)-[:HAS_PHONE]->(Phone), (Person)-[:WORKS_FOR]->(Company), (Person)-[:INVITED]->(Person),
(Person)-[:SAT_AT]->(Table), (Room)-[:IN_WING]->(Wing), (Door)-[:CONNECTS]->(Room), (Person)-[:HOLDS]->(Badge),
(Swipe)-[:BY]->(Badge), (Swipe)-[:AT]->(Door), (Swipe)-[:INTO]->(Room), (Call)-[:FROM]->(Phone),
(Call)-[:TO]->(Phone), (Account)-[:CONTACT]->(Phone), (Transfer)-[:FROM_ACCOUNT]->(Account),
(Transfer)-[:TO_ACCOUNT]->(Account), (Chunk)-[:PART_OF]->(Document), (Chunk)-[:NEXT]->(Chunk),
(Chunk)-[:MENTIONS]->(Person). Times are local datetimes: compare them with localdatetime('2026-09-08T17:00'),
never datetime(), which carries a time zone and matches nothing."""


def generated_query(board: Board, question: str, llm: Any) -> list[dict]:
    answer = llm.json(
        f"Write one read-only Cypher query that answers: {question}\nThe gala night is {board.case.meta['date']}.",
        {
            "type": "object",
            "properties": {"cypher": {"type": "string"}},
            "required": ["cypher"],
            "additionalProperties": False,
        },  # fmt: skip
        system=f"You write Cypher for Neo4j. The graph:\n{SCHEMA_TEXT}\nAlways end with LIMIT 100.",
    )
    query = answer["cypher"].strip().rstrip(";")
    if not validate_query(query):
        return []
    return board.q(query)


# ── Search over the statements, with the graph's help ─────────────────────────


def search(board: Board, question: str, k: int) -> list[tuple[str, int]]:
    """Plain vector search over the paragraphs."""
    rows = board.q(
        "CALL db.index.vector.queryNodes('chunk_embeddings', $k, $v) YIELD node RETURN node.doc AS doc, node.index AS i",
        k=k, v=[float(x) for x in embed([question])[0]],
    )  # fmt: skip
    return [(r["doc"], r["i"]) for r in rows]


def graph_search(board: Board, question: str, k: int) -> list[tuple[str, int]]:
    """Vector hits, expanded and re-ranked by the people the question names (MENTIONS edges)."""
    m3 = _m3()
    people = m3.People(board.case)
    named = set()
    for m in m3.NAME.finditer(question):
        pid = people.resolve(m.group())
        if pid:
            named.add(pid)
    hits = search(board, question, max(k, 20))
    mentioning = []
    if named:
        rows = board.q("MATCH (c:Chunk)-[:MENTIONS]->(p:Person) WHERE p.id IN $ids RETURN c.doc AS doc, c.index AS i",
                       ids=sorted(named))  # fmt: skip
        mentioning = [(r["doc"], r["i"]) for r in rows]
    ranked = [h for h in hits if h in mentioning] + [h for h in mentioning if h not in hits] + hits
    return list(dict.fromkeys(ranked))[:k]


# ── Routing ───────────────────────────────────────────────────────────────────


def route(question: str) -> str:
    q = question.lower()
    if re.search(r"\b(overall|across|themes?|summari[sz]e|everyone|all the (statements|documents))\b", q):
        return "global"
    if re.search(r"\b(say|said|says|statements?|mention|mentions|wrote|claims?|according to)\b", q):
        return "search"
    if re.search(r"^(who was in|which doors|who called|who phoned)\b", q):
        return "template"
    return "generated"


# ── Global search: communities and their summaries ────────────────────────────


def _people_graph(board: Board) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(r["id"] for r in board.q("MATCH (p:Person) RETURN p.id AS id"))
    queries = [
        "MATCH (a:Person)-[:HAS_PHONE]->(:Phone)<-[:FROM|TO]-(:Call)-[:FROM|TO]->(:Phone)<-[:HAS_PHONE]-(b:Person) "
        "WHERE a.id < b.id RETURN DISTINCT a.id AS a, b.id AS b",
        "MATCH (a:Person)-[:HAS_PHONE]->(:Phone)<-[:CONTACT]-(:Account)<-[:FROM_ACCOUNT|TO_ACCOUNT]-(:Transfer)"
        "-[:FROM_ACCOUNT|TO_ACCOUNT]->(:Account)-[:CONTACT]->(:Phone)<-[:HAS_PHONE]-(b:Person) "
        "WHERE a.id < b.id RETURN DISTINCT a.id AS a, b.id AS b",
        "MATCH (a:Person)-[:SAT_AT]->(:Table)<-[:SAT_AT]-(b:Person) WHERE a.id < b.id RETURN a.id AS a, b.id AS b",
        "MATCH (a:Person)-[:INVITED]->(b:Person) RETURN a.id AS a, b.id AS b",
        "MATCH (a:Person)-[:WORKS_FOR]->(:Company)<-[:WORKS_FOR]-(b:Person) WHERE a.id < b.id RETURN a.id AS a, b.id AS b",
    ]
    for q in queries:
        g.add_edges_from((r["a"], r["b"]) for r in board.q(q))
    return g


def communities(board: Board) -> list[set[str]]:
    return [set(c) for c in nx.community.louvain_communities(_people_graph(board), seed=7)]


def global_answer(board: Board, question: str, llm: Any) -> set[str]:
    """Map-reduce over community reports: summarize each group's paragraphs, ask each summary, merge."""
    names = {r["id"]: r["name"] for r in board.q("MATCH (p:Person) RETURN p.id AS id, p.name AS name")}
    found: set[str] = set()
    for group in communities(board):
        if len(group) < 2:
            continue
        rows = board.q("MATCH (c:Chunk)-[:MENTIONS]->(p:Person) WHERE p.id IN $ids "
                       "MATCH (c)-[:PART_OF]->(d:Document) RETURN DISTINCT d.author AS author, c.text AS text",
                       ids=sorted(group))  # fmt: skip
        if not rows:
            continue
        report = llm.text(
            "Summarize what these paragraphs say about these people: who they are, what they did, what others "
            "say about them.\n\nPeople: "
            + ", ".join(names[p] for p in sorted(group))
            + "\n\n"
            + "\n\n".join(f"{r['author']}: {r['text']}" for r in rows)
        )
        answer = llm.json(
            f"Question: {question}\n\nAnswer only from this report. List the full names of the people it says "
            f"answer the question, and no one else; an empty list when the report doesn't say.\n\n{report}",
            {
                "type": "object",
                "properties": {"names": {"type": "array", "items": {"type": "string"}}},
                "required": ["names"],
                "additionalProperties": False,
            },  # fmt: skip
        )
        people = _m3().People(board.case)
        found |= {pid for n in answer["names"] if (pid := people.resolve(n))}
    return found
