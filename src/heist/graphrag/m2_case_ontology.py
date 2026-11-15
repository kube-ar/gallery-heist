"""Milestone 2 · The case ontology.

Instructions: https://kube.ar/graphrag/project/gallery-heist/case-ontology

Milestone 1 put the systems in a graph with whatever shape worked. Now design the shape on
purpose: an ontology that says what kinds of things exist and how they relate, the same facts
written as RDF, one named graph per source system, shapes that reject broken data, an alibi
that knows the difference between "no" and "we don't know", and the people behind the front
desk's handwritten sign-in sheet.

Check your work with `uv run heist check 2`.

Fast path: rdflib (graphs, SPARQL), pyshacl (shapes), rapidfuzz (name similarity).
Deep path: the same with fewer helpers: your own matcher, your own reachability.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from heist.case import Case

HERE = Path(__file__).resolve().parent
ONTOLOGY = HERE / "m2_heist.ttl"  # your ontology, in Turtle
SHAPES = HERE / "m2_shapes.ttl"  # your SHACL shapes, in Turtle


def to_rdf(case: Case) -> Any:
    """The case as RDF, using your ontology: an rdflib Dataset with one named graph per system.

    Name the graphs after the case folders: hr, events, vendors, security, facilities, telecom,
    finance. Every class and property you use must be declared in ONTOLOGY. Write events (a
    swipe, a call, a transfer) as nodes with their own properties, not as single edges.
    """
    raise NotImplementedError


def rooms_in_wing(data: Any, wing: str) -> set[str]:
    """Room ids (R11...) in a wing ("east", "west", "service", "central"), from your graph."""
    raise NotImplementedError


def unguarded_ways_in(data: Any, wing: str) -> set[str]:
    """Door ids that lead into the wing from outside it and log nothing: no card reader."""
    raise NotImplementedError


def swipes_at(data: Any, door_id: str, start: datetime, end: datetime) -> list[tuple[datetime, str, bool]]:
    """Every swipe at a door with start <= time < end, as (time, badge id, granted), in time order."""
    raise NotImplementedError


def sources_of(data: Any, person_id: str) -> set[str]:
    """Which of hr, events, vendors, security, telecom and finance hold a fact about this person.

    A fact about their phone counts (a call, an account's contact number), and so does being
    the host who invited a guest or sitting at a dinner table.
    """
    raise NotImplementedError


def alibi(data: Any, person_id: str, wing: str, start: datetime, end: datetime) -> str:
    """'placed', 'elsewhere' or 'unknown', from the keycard log, without closing the world.

    placed: their badge was in a room of the wing at some moment from start to end.
    elsewhere: for the whole window their badge was somewhere the wing can't be reached from
      without passing a card reader. Doors without a reader (archways, fire doors) count as open.
    unknown: anything else, including no badge at all, or a window that starts before their
      badge's first swipe.
    """
    raise NotImplementedError


def resolve_signins(case: Case) -> list[str | None]:
    """For each row of case.signins, in order: the guest id of who wrote it, or None.

    Names are written by hand ("M. Vos", "vos, mara", a typo, a nickname), phones are often
    missing and sometimes misread, and some rows are plus-ones who are on no list at all.
    Each guest signed once.
    """
    raise NotImplementedError
