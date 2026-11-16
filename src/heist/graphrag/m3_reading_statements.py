"""Milestone 3 · Reading the statements.

Instructions: https://kube.ar/graphrag/project/gallery-heist/reading-the-statements

After the theft, people wrote things down: witness statements, emails, an incident report, a
press clipping (case.documents). Turn them into graph facts: the documents as a lexical graph,
the people they mention linked to the records you already have, the claims they make extracted
with an LLM and limited to the predicates below, and every claim about where someone was checked
against the keycard log.

Check your work with `uv run heist check 3` (the claims check calls your LLM: set up .env first,
then `uv run heist llm`).

Fast path: networkx for the lexical graph, rapidfuzz for names, `heist.llm` for extraction.
Deep path: your own prompt and JSON schema, your own linker, your own review queue.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case, Document

# The predicates a claim may use: the ontology's vocabulary for what witnesses say.
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


def lexical_graph(case: Case) -> Any:
    """The documents as a lexical graph.

    A Document node per document, a Chunk node per paragraph (paragraphs are separated by a
    blank line), PART_OF from each chunk to its document, and NEXT from each chunk to the one
    after it in the same document.
    """
    raise NotImplementedError


def lexical_summary(graph: Any) -> dict[str, int]:
    """Counted from the graph: {"documents": ..., "chunks": ..., "next": ...}."""
    raise NotImplementedError


def neighborhood(graph: Any, doc_id: str, index: int) -> dict:
    """What a search hit on chunk `index` (from 0) of a document expands to.

    Return {"title": the document's title, "before": the previous chunk's text or None,
    "chunk": this chunk's text, "after": the next chunk's text or None}.
    """
    raise NotImplementedError


def find_people(case: Case, doc: Document) -> list[tuple[int, int, str | None]]:
    """Every mention of a person in doc.text, once each, as (start, end, id).

    The id is an employee, guest or contractor id, or None when you can't tell who it is.
    People are written many ways: a full name, a first name, a surname, a nickname, a typo,
    or only a role ("one of the guards").
    """
    raise NotImplementedError


def read_document(case: Case, doc: Document, llm: Any) -> list[dict]:
    """The claims the document makes, extracted with `llm` (from heist.llm.get_llm()).

    Each claim is {"subject": person id, "predicate": one of PREDICATES, "object": a person id,
    a room id or None, "time": "HH:MM" (24-hour, as the text states it) or None, "status":
    "accepted", "review" or "rejected"}. "I" is the document's author (the index names them).
    Only accepted claims are scored: send anything you can't link to "review".
    """
    raise NotImplementedError


def contradictions(case: Case, claims: list[dict]) -> list[int]:
    """Indices of the "was_in" claims that the keycard log rules out.

    A claim is ruled out when, for the whole span from 10 minutes before its time to 10 minutes
    after, the subject's badge was somewhere that room can't be reached from without a swipe.
    No badge, or a span the log knows nothing about, rules nothing out.
    """
    raise NotImplementedError
