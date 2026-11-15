"""Detective 2 · The rulebook.

Instructions: https://kube.ar/agentic-graphrag/project/gallery-heist/the-rulebook

The rookie learned the chief's rules from a tool's text, if it read them at all. Put the rules
where an agent can read them and can't change them: in a graph, with an owner. Give the agent one
generic `describe` tool that works for every kind of record because a type spec says how, not
because the code knows each type. Then run it with a distraction: one innocent witness "remembers"
something that looks decisive.

Check your work with `uv run heist check d2`: the rules and `describe` need no LLM.
"""

from __future__ import annotations

from typing import Any

from heist.case import Case
from heist.precinct import RULEBOOK, Precinct  # noqa: F401  (the rules to put in your graph)

# How `describe` finds and explains each kind of record. A context entry is
# [table, their field, our field, output field]: the rows of `table` whose `their field` equals
# this record's `our field`, as a sorted list of their `output field`. Tables: heist.precinct.records().
SPEC: dict[str, dict] = {
    "Person": {"match": r"^[EGC]-\d+$", "table": "people", "key": "id", "identify": ["name", "kind", "role"],
               "context": {"badges": ["badges", "holder_id", "id", "badge_id"],
                           "accounts": ["accounts", "phone", "phone", "account_id"]}},
    "Room": {"match": r"^R\d{2}$", "table": "rooms", "key": "room_id", "identify": ["name", "wing"],
             "context": {"doors": ["doors", "room_a", "room_id", "door_id"], "more_doors": ["doors", "room_b", "room_id", "door_id"]}},
    "Door": {"match": r"^D\d{2}$", "table": "doors", "key": "door_id", "identify": ["room_a", "room_b", "reader", "kind"],
             "context": {}},
    "Badge": {"match": r"^B-\d+$", "table": "badges", "key": "badge_id", "identify": ["holder_id", "zones"], "context": {}},
}  # fmt: skip


def rules_graph() -> Any:
    """The rulebook as a graph: a Rule node per rule (text, owner "chief", version), and an edge from
    each rule to the action it governs ("accuse")."""
    raise NotImplementedError


def rules_for(graph: Any, action: str) -> list[str]:
    """The ids of the rules that govern an action, sorted. No rules: []."""
    raise NotImplementedError


def rule_text(graph: Any, rule_id: str) -> str:
    raise NotImplementedError


def update_rule(graph: Any, rule_id: str, text: str, actor: str) -> bool:
    """Change a rule's text. Only its owner may: anyone else gets False and the rule stays as it was."""
    raise NotImplementedError


def describe(case: Case, node_id: str, spec: dict = SPEC) -> dict:
    """Any record, explained by the spec: {"type", "id", its identify fields..., "context": {...}}.

    The type is the one whose `match` pattern fits the id. Unknown ids: {"error": ...}. A new kind of
    record must work by adding it to the spec, with no change to this function."""
    raise NotImplementedError


def investigate(case: Case, llm: Any, distract: bool = False) -> Precinct:
    """Your rookie, plus two tools of your own: read the rules from your graph, and describe a record.
    Build the desk with Precinct(case, distract=distract)."""
    raise NotImplementedError
