"""Milestone 4 · Ask the board.

Instructions: https://kube.ar/graphrag/project/gallery-heist/ask-the-board

Move the case into a graph database and ask it questions four ways: expert templates for the
questions you know, model-written queries (checked before they run) for the ones you don't,
search over the statements helped by the graph, and global search over communities for the
questions about everything. A router picks the way for each question.

Start Neo4j with `docker compose up -d`, then check your work with `uv run heist check 4`.
Two checks call your LLM; the rest don't.

Fast path: Neo4j with Cypher, its vector index, and networkx for communities.
Deep path: a graph layer on PostgreSQL, or your own store, with the same functions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from heist.case import Case

# Your Cypher templates by name: "who_was_in" ($wing, $start, $end), "callers_of" ($person,
# $start, $end) and "unguarded_ways_in" ($wing). Each returns rows with an `id` column.
TEMPLATES: dict[str, str] = {}


def store(case: Case) -> Any:
    """Load one case into your store, replacing what was there, and return a handle to it.

    Everything from milestones 1 to 3: people, phones, badges, rooms, wings, doors, swipes,
    calls, accounts, transfers, tables, documents and their paragraphs (Chunk nodes with an
    embedding), and MENTIONS from each paragraph to the people your milestone 3 linker finds.
    """
    raise NotImplementedError


def store_summary(board: Any) -> dict[str, int]:
    """Counted in the store: people, badges, rooms, doors, swipes, calls, transfers, documents, chunks."""
    raise NotImplementedError


def ask_template(board: Any, name: str, **params) -> set[str]:
    """Run TEMPLATES[name] with these parameters and return the ids it finds."""
    raise NotImplementedError


def validate_query(query: str) -> bool:
    """Is a model-written query safe to run? Read-only, only labels and relationships your
    store has, and ending in a LIMIT of at most 1000."""
    raise NotImplementedError


def generated_query(board: Any, question: str, llm: Any) -> list[dict]:
    """Ask the LLM for one Cypher query that answers the question, validate it, run it, return the rows.
    Return [] when the query doesn't pass validate_query."""
    raise NotImplementedError


def graph_search(board: Any, question: str, k: int) -> list[tuple[str, int]]:
    """The k best paragraphs for a question about the statements, as (doc_id, paragraph index).

    Start from a vector search over the paragraphs, then use the graph: paragraphs that MENTION
    a person the question names go first, found even when they never write that person's name.
    """
    raise NotImplementedError


def route(question: str) -> str:
    """Which way to answer: "template", "generated", "search" or "global"."""
    raise NotImplementedError


def communities(board: Any) -> list[set[str]]:
    """Groups of people who are densely linked (calls, money, tables, invitations, companies)."""
    raise NotImplementedError


def global_answer(board: Any, question: str, llm: Any) -> set[str]:
    """Answer a question about everything: summarize each community's paragraphs with the LLM,
    ask each summary the question, and merge the answers into person ids."""
    raise NotImplementedError


_ = datetime  # times in your templates' parameters are datetimes
