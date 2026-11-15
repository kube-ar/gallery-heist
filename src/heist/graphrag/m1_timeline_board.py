"""Milestone 1 · The timeline board.

Instructions: https://kube.ar/graphrag/project/gallery-heist/timeline-board

Seven systems, none of them sharing ids. Put them in one graph, then answer three questions
no single system can: who was in a wing at a given time, how two people are connected, and
where money went around in a loop. Then ask a vector search the first question and see what
it gets wrong.

Check your work with `uv run heist check 1`.

Ids. Wherever a function returns people, return their id in the museum's lists: an employee
id (E-…), a guest id (G-…) or a contractor id (C-…). Someone in none of those lists has only
a phone number: return that. (The checks also accept a badge or an account, and resolve it.)

Fast path: networkx gives you the graph, shortest paths and cycles.
Deep path: a dict of adjacency sets, and the search and the cycle finding written by you.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from heist.case import Case


def build_graph(case: Case) -> Any:
    """Every row of every system as nodes and edges in one graph.

    Suggested shape (any shape works, as long as the functions below can answer from it):
    nodes for people, badges, rooms, wings, doors, phones, accounts and tables; edges like
    HOLDS (person → badge), SWIPED (badge → door, with time, to_room and result), IN_WING
    (room → wing), HAS_PHONE, CALLED (phone → phone, with time), OWNS (person → account),
    PAID (account → account, with time and amount), SAT_AT, INVITED, WORKS_FOR.
    """
    raise NotImplementedError


def graph_summary(graph: Any) -> dict[str, int]:
    """How much of each system is in your graph, counted from the graph (not the case).

    Return these keys: people (staff + guests + contractors), badges, rooms, doors, phones
    (every distinct number), accounts, swipes (granted and denied), calls, transfers.
    """
    raise NotImplementedError


def who_was_in(graph: Any, wing: str, start: datetime, end: datetime) -> set[str]:
    """Who was in a room of `wing` at any moment from `start` to `end`, by the keycard log.

    A badge is in the room it last swiped into (granted swipes only) until its next granted
    swipe. Before its first swipe, the log says nothing. Return the badge holders' ids.
    """
    raise NotImplementedError


def connection(graph: Any, a: str, b: str) -> list[str]:
    """A shortest chain of people from `a` to `b`, both ends included: [a, ..., b].

    Two people are directly linked when they called each other, sent each other money, sat
    at the same dinner table, one invited the other, or they work for the same contractor.
    A phone belongs to whoever lists it; an account to whoever owns its contact phone.
    """
    raise NotImplementedError


def money_loops(graph: Any) -> list[list[str]]:
    """Every loop in the transfers: accounts [x, y, ..., z] where x paid y, ..., and z paid x.

    Each account appears once per loop. Any starting point is fine.
    """
    raise NotImplementedError


def vector_who_was_in(case: Case, wing: str, start: datetime, end: datetime, k: int) -> set[str]:
    """The same question as who_was_in, answered the way a plain vector search would.

    Write each granted swipe as one sentence ("At 22:04, Mara Vos badged into the Map Room,
    east wing."), embed them all, search with the question in words, keep the top k
    sentences, and return the people they name. Fast path: heist.vectors.VectorIndex.
    """
    raise NotImplementedError
