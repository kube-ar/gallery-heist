"""Milestone 1 · The timeline board: a reference solution (the fast path, with networkx).

Spoilers. `heist use-reference 1` copies this over your file if you want to skip ahead.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from itertools import combinations

import networkx as nx

from heist.case import Case
from heist.vectors import VectorIndex


def build_graph(case: Case) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()

    def node(kind: str, key, **attrs) -> str:
        n = f"{kind}:{key}"
        g.add_node(n, kind=kind, key=str(key), **attrs)
        return n

    def phone(number: str) -> str:
        return node("phone", number)

    for s in case.staff:
        p = node("person", s.employee_id, name=s.full_name, role=s.role)
        g.add_edge(p, phone(s.phone), type="HAS_PHONE")
    for x in case.guests:
        last, _, first = x.name.partition(", ")
        p = node("person", x.guest_id, name=f"{first} {last}", role=x.category)
        g.add_edge(p, phone(x.phone), type="HAS_PHONE")
        g.add_edge(f"person:{x.invited_by}", p, type="INVITED")
    for w in case.contractors:
        p = node("person", w.contractor_id, name=w.worker_name, role=w.job)
        g.add_edge(p, phone(w.phone), type="HAS_PHONE")
        g.add_edge(p, node("company", w.company), type="WORKS_FOR")
    for seat in case.seating:
        g.add_edge(f"person:{seat.attendee_id}", node("table", seat.table), type="SAT_AT")

    for r in case.rooms:
        g.add_edge(node("room", r.room_id, name=r.name), node("wing", r.wing), type="IN_WING")
    for d in case.doors:
        door = node("door", d.door_id, reader=d.has_reader, zone=d.zone)
        g.add_edge(door, f"room:{d.room_a}", type="CONNECTS")
        g.add_edge(door, f"room:{d.room_b}", type="CONNECTS")
    for b in case.badges:
        g.add_edge(f"person:{b.holder_id}", node("badge", b.badge_id, zones=b.zones), type="HOLDS")
    for s in case.swipes:
        g.add_edge(
            f"badge:{s.badge_id}", f"door:{s.door_id}", type="SWIPED", time=s.time, to_room=s.to_room, granted=s.granted
        )

    for a in case.accounts:
        g.add_edge(node("account", a.account_id, holder=a.holder_name), phone(a.contact_phone), type="CONTACT")
    for c in case.calls:
        g.add_edge(phone(c.caller), phone(c.callee), type="CALLED", time=c.start, seconds=c.seconds)
    for t in case.transfers:
        g.add_edge(f"account:{t.from_account}", f"account:{t.to_account}", type="PAID", time=t.time, amount=t.amount)
    return g


def _edges(g: nx.MultiDiGraph, kind: str):
    return [(u, v, d) for u, v, d in g.edges(data=True) if d["type"] == kind]


def graph_summary(graph: nx.MultiDiGraph) -> dict[str, int]:
    kinds = defaultdict(int)
    for _, d in graph.nodes(data=True):
        kinds[d["kind"]] += 1
    return {
        "people": kinds["person"],
        "badges": kinds["badge"],
        "rooms": kinds["room"],
        "doors": kinds["door"],
        "phones": kinds["phone"],
        "accounts": kinds["account"],
        "swipes": len(_edges(graph, "SWIPED")),
        "calls": len(_edges(graph, "CALLED")),
        "transfers": len(_edges(graph, "PAID")),
    }


def _key(g: nx.MultiDiGraph, n: str) -> str:
    return g.nodes[n]["key"]


def who_was_in(graph: nx.MultiDiGraph, wing: str, start: datetime, end: datetime) -> set[str]:
    rooms_in_wing = {u for u, v, _ in _edges(graph, "IN_WING") if v == f"wing:{wing}"}
    found = set()
    for badge, d in graph.nodes(data=True):
        if d["kind"] != "badge":
            continue
        swipes = sorted(
            (e for _, _, e in graph.out_edges(badge, data=True) if e["type"] == "SWIPED" and e["granted"]),
            key=lambda e: e["time"],
        )
        for cur, nxt in zip(swipes, [*swipes[1:], None]):
            until = nxt["time"] if nxt else None
            if f"room:{cur['to_room']}" in rooms_in_wing and cur["time"] < end and (until is None or until > start):
                holder = next(u for u, _, e in graph.in_edges(badge, data=True) if e["type"] == "HOLDS")
                found.add(_key(graph, holder))
                break
    return found


def _party(g: nx.MultiDiGraph, n: str) -> str:
    """A phone belongs to the person who lists it; an account to its contact phone's owner."""
    kind = g.nodes[n]["kind"]
    if kind == "person":
        return _key(g, n)
    if kind == "account":
        contact = next(v for _, v, e in g.out_edges(n, data=True) if e["type"] == "CONTACT")
        return _party(g, contact)
    owners = [u for u, _, e in g.in_edges(n, data=True) if e["type"] == "HAS_PHONE"]
    return _key(g, owners[0]) if owners else _key(g, n)


def _people_graph(g: nx.MultiDiGraph) -> nx.Graph:
    h = nx.Graph()
    for u, v, _ in _edges(g, "CALLED") + _edges(g, "PAID"):
        a, b = _party(g, u), _party(g, v)
        if a != b:
            h.add_edge(a, b)
    for u, v, _ in _edges(g, "INVITED"):
        h.add_edge(_key(g, u), _key(g, v))
    for kind in ("SAT_AT", "WORKS_FOR"):
        members = defaultdict(list)
        for u, v, _ in _edges(g, kind):
            members[v].append(_key(g, u))
        for people in members.values():
            h.add_edges_from(combinations(people, 2))
    return h


def connection(graph: nx.MultiDiGraph, a: str, b: str) -> list[str]:
    if "people_graph" not in graph.graph:
        graph.graph["people_graph"] = _people_graph(graph)
    return nx.shortest_path(graph.graph["people_graph"], a, b)


def money_loops(graph: nx.MultiDiGraph) -> list[list[str]]:
    money = nx.DiGraph()
    money.add_edges_from((u, v) for u, v, _ in _edges(graph, "PAID") if u != v)
    return [[_key(graph, n) for n in loop] for loop in nx.simple_cycles(money)]


_indexes: dict[str, tuple[VectorIndex, list[str]]] = {}


def vector_who_was_in(case: Case, wing: str, start: datetime, end: datetime, k: int) -> set[str]:
    if case.id not in _indexes:
        holder = {b.badge_id: b.holder_id for b in case.badges}
        names = {s.employee_id: s.full_name for s in case.staff} | {
            w.contractor_id: w.worker_name for w in case.contractors
        }
        rooms = {r.room_id: r for r in case.rooms}
        texts, who = [], []
        for s in case.swipes:
            if not s.granted:
                continue
            room = rooms[s.to_room]
            person = holder[s.badge_id]
            texts.append(f"At {s.time:%H:%M}, {names[person]} badged into the {room.name}, {room.wing} wing.")
            who.append(person)
        _indexes[case.id] = (VectorIndex(texts), who)
    index, who = _indexes[case.id]
    hits = index.search(f"Who was in the {wing} wing between {start:%H:%M} and {end:%H:%M}?", k)
    return {who[i] for i in hits}
