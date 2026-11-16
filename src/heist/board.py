"""The evidence board at the desk: the graph GraphRAG milestone 4 builds, for the case being worked.

A planned detective asks it in Cypher instead of pulling the logs one tool call at a time:

    desk = Precinct(load_case("practice/case-01"))
    desk.call("board", {"query": "MATCH (p:Person {kind: 'guest'}) RETURN p.id AS id LIMIT 5"})

It holds the records: people, phones, companies, tables, rooms, wings, doors, badges, swipes, calls,
accounts and transfers. Not the documents: statements still come from interviews, and the camera log
from `camera_log`. It's loaded with the course's own milestone 4 solution
(reference/graphrag/m4_ask_the_board.py), so it works whether or not you built milestone 4, and it
needs Neo4j: `docker compose up -d`. Loading a case replaces whatever the database held.

The chief counts what a query reads as consulted: a query over `Swipe` nodes read the keycard log, one
over `Call` nodes the phone records, one over `Transfer` or `Account` nodes the bank records.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date, datetime
from typing import Any

from .case import ROOT, Case

M4 = ROOT / "reference" / "graphrag" / "m4_ask_the_board.py"
LABELS = {"Person", "Phone", "Company", "Table", "Room", "Wing", "Door", "Badge", "Swipe", "Call", "Account",
          "Transfer"}  # fmt: skip
RELS = {"HAS_PHONE", "WORKS_FOR", "INVITED", "SAT_AT", "IN_WING", "CONNECTS", "HOLDS", "BY", "AT", "INTO", "FROM",
        "TO", "CONTACT", "FROM_ACCOUNT", "TO_ACCOUNT"}  # fmt: skip
SOURCES = {"Swipe": "keycard", "Call": "phone", "Transfer": "bank", "Account": "bank"}
WRITES = re.compile(r"(?<![:\w])(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|CALL)\b", re.IGNORECASE)
SCHEMA = """Nodes: Person {id, name, kind, role}, Phone {number}, Company {name}, Table {number}, Room {id, name},
Wing {id}, Door {id, reader, kind}, Badge {id}, Swipe {at, granted}, Call {at, seconds}, Account {id, holder},
Transfer {at, amount, reference}.
Relationships: (Person)-[:HAS_PHONE]->(Phone), (Person)-[:WORKS_FOR]->(Company), (Person)-[:INVITED]->(Person),
(Person)-[:SAT_AT]->(Table), (Room)-[:IN_WING]->(Wing), (Door)-[:CONNECTS]->(Room), (Person)-[:HOLDS]->(Badge),
(Swipe)-[:BY]->(Badge), (Swipe)-[:AT]->(Door), (Swipe)-[:INTO]->(Room), (Call)-[:FROM]->(Phone),
(Call)-[:TO]->(Phone), (Account)-[:CONTACT]->(Phone), (Transfer)-[:FROM_ACCOUNT]->(Account),
(Transfer)-[:TO_ACCOUNT]->(Account).
Times are local datetimes: compare them with localdatetime('2026-09-08T22:15'), never datetime()."""

_loaded: str | None = None  # the case this process last loaded; the database is checked too


def _strip(query: str) -> str:
    return re.sub(r"'[^']*'|\"[^\"]*\"", "''", query)  # string literals can't hide a keyword or a label


def problem(query: str, max_rows: int) -> str | None:
    """Why a query can't run on the board, or None: read-only, labels and relationships the board has,
    and a LIMIT of at most max_rows."""
    if not isinstance(query, str) or not query.strip():
        return "a Cypher query, as a string"
    text = _strip(query)
    if WRITES.search(text):
        return "the board is read-only: no CREATE, MERGE, SET, DELETE, REMOVE, DROP, LOAD CSV, FOREACH or CALL"
    if not re.search(r"\bMATCH\b", text, re.I) or not re.search(r"\bRETURN\b", text, re.I):
        return "a query needs MATCH and RETURN"
    limit = re.search(r"\bLIMIT\s+(\d+)\s*;?\s*$", text, re.I)
    if not limit or int(limit.group(1)) > max_rows:
        return f"end the query with LIMIT n, n at most {max_rows}"
    labels = set(re.findall(r"\(\s*\w*\s*:\s*(\w+)", text))
    rels = {r for group in re.findall(r"\[\s*\w*\s*:\s*([\w|:]+)", text) for r in re.split(r"[|:]", group) if r}
    if labels - LABELS or rels - RELS:
        return f"the board has no {sorted((labels - LABELS) | (rels - RELS))}: {SCHEMA.splitlines()[0]} …"
    return None


def sources(query: str) -> set[str]:
    """The kinds of record a query reads, by the labels it names."""
    return {SOURCES[label] for label in re.findall(r":\s*(\w+)", _strip(str(query))) if label in SOURCES}


def _m4():
    spec = importlib.util.spec_from_file_location("m4_for_the_desk", M4)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_M4 = None


def _board(case: Case):
    """The board for this case, loaded into Neo4j if it isn't already."""
    global _M4, _loaded
    _M4 = _M4 or _m4()
    board = _M4.Board(_M4._DRIVER or _M4._driver(), case)
    _M4._DRIVER = board.driver
    if _loaded != case.id or board.q("MATCH (m:DeskBoard) RETURN m.case AS c") != [{"c": case.id}]:
        board = _M4.store(case)
        board.q("MATCH (n) WHERE n:Document OR n:Chunk DETACH DELETE n")
        board.q("CREATE (:DeskBoard {case: $case})", case=case.id)
        _loaded = case.id
    return board


def _plain(value: Any) -> Any:
    if hasattr(value, "to_native"):
        value = value.to_native()
    if isinstance(value, datetime):
        return f"{value:%Y-%m-%d %H:%M}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def run(case: Case, query: str, params: dict | None, max_rows: int) -> list[dict] | dict:
    """The rows a read-only query returns on this case's board, or {"error": ...}."""
    from neo4j.exceptions import AuthError, CypherSyntaxError, ServiceUnavailable

    why = problem(query, max_rows)
    if why:
        return {"error": why}
    if params is not None and not isinstance(params, dict):
        return {"error": "params is an object of query parameters"}
    down = reachable()  # fast when Neo4j is off; a query would retry for half a minute before failing
    if down:
        return {"error": down}
    try:
        board = _board(case)
        return [_plain(row) for row in board.q(query, **(params or {}))]
    except (ServiceUnavailable, AuthError, OSError) as e:
        return {"error": f"the evidence board needs Neo4j: run `docker compose up -d` and check NEO4J_* in .env ({e})"}
    except CypherSyntaxError as e:
        return {"error": f"the query doesn't parse: {str(e.message or e)[:240]}"}
    except Exception as e:  # a type error in the query, a missing parameter: the model can fix those
        return {"error": f"the query failed: {str(getattr(e, 'message', None) or e)[:240]}"}


def reachable() -> str | None:
    """None when the board's Neo4j answers, else what to do about it."""
    global _M4
    try:
        _M4 = _M4 or _m4()
        _M4._DRIVER = _M4._DRIVER or _M4._driver()
        _M4._DRIVER.verify_connectivity()
        return None
    except Exception as e:  # not running, wrong password, wrong port
        return f"The evidence board needs Neo4j: run `docker compose up -d`, and check NEO4J_* in .env ({type(e).__name__})."
