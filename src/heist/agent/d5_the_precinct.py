"""Detective 5 · The precinct.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/the-precinct

A real precinct has far more tools than tonight's case needs (heist.catalog.CATALOG: 59 of them,
each with what it takes, what it gives and its class of action). Put all of them in the prompt and
the agent picks worse. Find the few a question needs, chain tools by the types they take and give,
and keep untrusted text from driving actions: tonight, one statement carries an instruction aimed
at the agent itself.

Check your work with `uv run heist check d5`: finding, chaining and gating tools need no LLM.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.catalog import CATALOG  # noqa: F401  name -> (description, takes, gives, class)
from heist.precinct import Precinct


def select_tools(question: str, k: int = 5) -> list[str]:
    """The k catalog tools most likely to answer the question, best first (search their descriptions)."""
    raise NotImplementedError


def chain(have: str, want: str) -> list[str] | None:
    """A shortest chain of tools from a thing of type `have` to one of type `want`: each tool takes
    what the previous one gives. None when no chain exists."""
    raise NotImplementedError


def allowed(tool: str, arguments: dict, desk: Precinct) -> str:
    """ "allow", "ask" (a person decides) or "deny", before the tool runs.

    human tools: deny. machine tools: allow. supervised tools (accuse, freeze_account): allow only
    if every person they name appears in what a log returned tonight (keycard_log, camera_log,
    phone_records, bank_records, in desk.outputs); a name that only came from statements or
    documents is untrusted, so: ask."""
    raise NotImplementedError


def investigate(case: Case, llm: Any, inject: bool = False) -> Precinct:
    """Your detective with tool retrieval over the catalog, and every call gated by `allowed`.
    Build the desk with Precinct(case, inject=inject)."""
    raise NotImplementedError
