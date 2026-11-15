"""The precinct: where the detective agent works a case.

The board milestones got every file at once. A detective doesn't: it gets the briefing and a
desk of tools, and each request costs minutes from the night's budget. When it's sure, it
accuses, and the chief signs the warrant only if the evidence follows the rulebook.

    from heist.precinct import Precinct
    desk = Precinct(load_case("practice/case-01"))
    desk.tools()                          # the tool descriptions (JSON Schema), for any LLM
    desk.call("keycard_log", {"room": "R21", "start": "22:40", "end": "23:45"})
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "E-1855", "method": "insider",
                         "evidence": ["..."]})
    desk.verdict()                        # what the chief decided, and whether it was right

Every call is recorded in `desk.log`: the raw material of an execution graph (milestone 6).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .case import Case

BUDGET_MINUTES = 360  # six hours of investigation before the morning briefing
MAX_ROWS = 60

# The chief's rulebook: rules the agent can read (milestone 2 stores them in the graph).
RULEBOOK = [
    {"id": "R1", "rule": "An accusation names a culprit, an accomplice (or none) and a method: insider, borrowed_badge or fire_door."},
    {"id": "R2", "rule": "The evidence cites at least two independent kinds of source: keycard log, camera log, phone records, bank records, statements."},
    {"id": "R3", "rule": "Only cite sources you consulted tonight: the chief checks the desk's log."},
    {"id": "R4", "rule": "A statement alone never proves where someone was: people lie."},
]  # fmt: skip

SOURCE_WORDS = {
    "keycard": ("keycard", "badge", "swipe", "door"),
    "camera": ("camera",),
    "phone": ("call", "phone", "rang"),
    "bank": ("bank", "transfer", "payment", "paid", "account"),
    "statement": ("statement", "interview", "told the", "claimed", "testified"),
}
TOOL_SOURCE = {"keycard_log": "keycard", "camera_log": "camera", "phone_records": "phone",
               "bank_records": "bank", "interview": "statement"}  # fmt: skip


@dataclass
class Action:
    """One call at the desk: what was asked, what it cost, what came back (in short)."""

    step: int
    minute: int
    tool: str
    arguments: dict
    cost: int
    ok: bool
    summary: str


@dataclass
class Precinct:
    case: Case
    budget: int = BUDGET_MINUTES
    spent: int = 0
    log: list[Action] = field(default_factory=list)
    accusation: dict | None = None

    # ── Tool descriptions ─────────────────────────────────────────────────────

    COSTS = {"briefing": 0, "rulebook": 0, "list_people": 5, "floor_plan": 5, "documents": 5, "read_document": 5,
             "keycard_log": 15, "camera_log": 10, "phone_records": 20, "bank_records": 30, "interview": 20,
             "accuse": 0}  # fmt: skip

    def tools(self) -> list[dict]:
        time = {"type": "string", "description": "a time on the gala night, HH:MM (24-hour)"}
        person = {"type": "string", "description": "an employee, guest or contractor id (E-…, G-…, C-…)"}
        obj = lambda props, req: {"type": "object", "properties": props, "required": req, "additionalProperties": False}  # noqa: E731
        return [
            {"name": "briefing", "description": "What happened, as the night shift reported it. Free.", "parameters": obj({}, [])},
            {"name": "rulebook", "description": "The chief's rules for a warrant. Free.", "parameters": obj({}, [])},
            {"name": "list_people", "description": "Everyone on the museum's lists: staff, guests and contract workers, with their ids and roles. 5 minutes.", "parameters": obj({}, [])},
            {"name": "floor_plan", "description": "Rooms, wings and doors, and which doors have card readers. 5 minutes.", "parameters": obj({}, [])},
            {"name": "documents", "description": "The documents filed tonight (reports, emails, press), without the statements. 5 minutes.", "parameters": obj({}, [])},
            {"name": "read_document", "description": "One document's text. 5 minutes.", "parameters": obj({"doc_id": {"type": "string"}}, ["doc_id"])},
            {"name": "keycard_log", "description": f"Badge swipes, filtered by room, badge and time. At most {MAX_ROWS} rows: narrow the filter if you get an error. 15 minutes.",
             "parameters": obj({"room": {"type": "string", "description": "a room id like R21"}, "badge": {"type": "string"}, "start": time, "end": time}, [])},
            {"name": "camera_log", "description": "When each camera went offline or online, between two times. 10 minutes.", "parameters": obj({"start": time, "end": time}, [])},
            {"name": "phone_records", "description": "Calls to and from one person's phone, the night and the weeks before. 20 minutes.", "parameters": obj({"person": person}, ["person"])},
            {"name": "bank_records", "description": "Transfers in and out of one person's accounts. 30 minutes.", "parameters": obj({"person": person}, ["person"])},
            {"name": "interview", "description": "One person's statement, if they gave one. 20 minutes.", "parameters": obj({"person": person}, ["person"])},
            {"name": "accuse", "description": "Ask the chief for a warrant. Ends the investigation.",
             "parameters": obj({"culprit": person, "accomplice": {"type": "string", "description": "a person id, or empty for none"},
                                "method": {"type": "string", "enum": ["insider", "borrowed_badge", "fire_door"]},
                                "evidence": {"type": "array", "items": {"type": "string"}, "description": "one fact per item, naming its source"}},
                               ["culprit", "accomplice", "method", "evidence"])},
        ]  # fmt: skip

    # ── Calling a tool ────────────────────────────────────────────────────────

    @property
    def remaining(self) -> int:
        return self.budget - self.spent

    def call(self, name: str, arguments: dict | None = None) -> Any:
        """Run a tool by name. Errors come back as {"error": ...}, never as exceptions."""
        arguments = dict(arguments or {})
        if self.accusation is not None:
            return self._record(name, arguments, 0, False, {"error": "the investigation is over: you already accused"})
        if name not in self.COSTS:
            return self._record(name, arguments, 0, False, {"error": f"no tool {name!r}"})
        cost = self.COSTS[name]
        if cost > self.remaining:
            return self._record(name, arguments, 0, False,
                                {"error": f"not enough time left ({self.remaining} min) for {name} ({cost} min): accuse now"})  # fmt: skip
        try:
            result = getattr(self, f"_{name}")(**arguments)
        except TypeError as e:
            return self._record(name, arguments, 0, False, {"error": f"bad arguments for {name}: {e}"})
        except ValueError as e:
            return self._record(name, arguments, 0, False, {"error": str(e)})
        ok = not (isinstance(result, dict) and "error" in result)
        return self._record(name, arguments, cost if ok else 0, ok, result)

    def _record(self, name: str, arguments: dict, cost: int, ok: bool, result: Any) -> Any:
        self.spent += cost
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        self.log.append(Action(len(self.log) + 1, self.spent, name, arguments, cost, ok, text[:160]))
        return result

    # ── The tools ─────────────────────────────────────────────────────────────

    def _when(self, value: str | None, default: datetime) -> datetime:
        if not value:
            return default
        try:
            return self.case.at(value)
        except ValueError as e:
            raise ValueError(f"times are HH:MM, got {value!r}") from e

    def _briefing(self) -> str:
        return self.case.briefing

    def _rulebook(self) -> list[dict]:
        return RULEBOOK

    def _list_people(self) -> list[dict]:
        out = [{"id": s.employee_id, "name": s.full_name, "kind": "staff", "role": s.role} for s in self.case.staff]
        for g in self.case.guests:
            last, _, first = g.name.partition(", ")
            out.append({"id": g.guest_id, "name": f"{first} {last}", "kind": "guest", "role": g.category})
        out += [{"id": w.contractor_id, "name": w.worker_name, "kind": "contractor", "role": f"{w.job}, {w.company}"}
                for w in self.case.contractors]  # fmt: skip
        return out

    def _floor_plan(self) -> dict:
        return {
            "rooms": [{"id": r.room_id, "name": r.name, "wing": r.wing} for r in self.case.rooms],
            "doors": [
                {"id": d.door_id, "between": [d.room_a, d.room_b], "reader": d.has_reader, "kind": d.kind}
                for d in self.case.doors
            ],  # fmt: skip
        }

    def _documents(self) -> list[dict]:
        return [{"doc_id": d.doc_id, "kind": d.kind, "title": d.title, "author": d.author}
                for d in self.case.documents if d.kind != "statement"]  # fmt: skip

    def _read_document(self, doc_id: str) -> str | dict:
        doc = next((d for d in self.case.documents if d.doc_id == doc_id and d.kind != "statement"), None)
        return doc.text if doc else {"error": f"no document {doc_id!r} (statements come from interviews)"}

    def _keycard_log(self, room: str | None = None, badge: str | None = None, start: str | None = None,
                     end: str | None = None) -> list[dict] | dict:  # fmt: skip
        lo, hi = self._when(start, datetime.min), self._when(end, datetime.max)
        holder = {b.badge_id: b.holder_id for b in self.case.badges}
        rows = [{"time": f"{s.time:%H:%M}", "badge": s.badge_id, "holder": holder.get(s.badge_id), "door": s.door_id,
                 "to_room": s.to_room, "result": "granted" if s.granted else "denied"}
                for s in self.case.swipes
                if (room is None or s.to_room == room) and (badge is None or s.badge_id == badge) and lo <= s.time < hi]  # fmt: skip
        if len(rows) > MAX_ROWS:
            return {"error": f"{len(rows)} rows: narrow it by room, badge or time (at most {MAX_ROWS})"}
        return rows

    def _camera_log(self, start: str | None = None, end: str | None = None) -> list[dict]:
        lo, hi = self._when(start, datetime.min), self._when(end, datetime.max)
        rooms = {c.camera_id: c.room_id for c in self.case.cameras}
        return [{"time": f"{e.time:%H:%M}", "camera": e.camera_id, "room": rooms.get(e.camera_id), "status": e.status}
                for e in self.case.camera_log if lo <= e.time < hi]  # fmt: skip

    def _phone_of(self, person: str) -> str:
        for s in self.case.staff:
            if s.employee_id == person:
                return s.phone
        for g in self.case.guests:
            if g.guest_id == person:
                return g.phone
        for w in self.case.contractors:
            if w.contractor_id == person:
                return w.phone
        raise ValueError(f"no person {person!r}: ids look like E-1042, G-311, C-219")

    def _phone_records(self, person: str) -> list[dict]:
        phone = self._phone_of(person)
        who = {p["id"]: p["id"] for p in self._list_people()}
        number_to_id = {self._phone_of(i): i for i in who}
        return [{"start": f"{c.start:%Y-%m-%d %H:%M}", "from": number_to_id.get(c.caller, c.caller),
                 "to": number_to_id.get(c.callee, c.callee), "seconds": c.seconds}
                for c in self.case.calls if phone in (c.caller, c.callee)]  # fmt: skip

    def _bank_records(self, person: str) -> list[dict]:
        phone = self._phone_of(person)
        mine = {a.account_id for a in self.case.accounts if a.contact_phone == phone}
        holders = {a.account_id: a.holder_name for a in self.case.accounts}
        return [{"time": f"{t.time:%Y-%m-%d}", "from": f"{t.from_account} ({holders.get(t.from_account)})",
                 "to": f"{t.to_account} ({holders.get(t.to_account)})", "amount": t.amount, "reference": t.reference}
                for t in self.case.transfers if t.from_account in mine or t.to_account in mine]  # fmt: skip

    def _interview(self, person: str) -> str:
        self._phone_of(person)  # validates the id
        author = {p["id"]: p["name"] for p in self._list_people()}[person]
        doc = next((d for d in self.case.documents if d.kind == "statement" and d.author == author), None)
        return doc.text if doc else f"{author} has nothing to add to what the night shift already knows."

    def _accuse(self, culprit: str, accomplice: str, method: str, evidence: list[str]) -> dict:
        self.accusation = {"culprit": culprit, "accomplice": accomplice or None, "method": method,
                           "evidence": list(evidence)}  # fmt: skip
        return self.verdict()

    # ── The chief ─────────────────────────────────────────────────────────────

    def consulted(self) -> set[str]:
        return {TOOL_SOURCE[a.tool] for a in self.log if a.ok and a.tool in TOOL_SOURCE}

    def verdict(self) -> dict:
        """The chief's decision on the accusation, and (on labeled cases) whether it was right."""
        if self.accusation is None:
            return {"warrant": False, "reason": "no accusation yet", "solved": False}
        acc = self.accusation
        ids = {p["id"] for p in self._list_people()}
        problems = []
        if acc["culprit"] not in ids or (acc["accomplice"] and acc["accomplice"] not in ids):
            problems.append("R1: name people by their ids")
        if acc["method"] not in ("insider", "borrowed_badge", "fire_door"):
            problems.append("R1: unknown method")
        cited = {source for source, words in SOURCE_WORDS.items()
                 for line in acc["evidence"] for w in words if w in line.lower()}  # fmt: skip
        if len(cited) < 2:
            problems.append("R2: cite at least two kinds of source")
        unread = cited - self.consulted()
        if unread:
            problems.append(f"R3: you cite {sorted(unread)} but never consulted them")
        if cited <= {"statement"}:
            problems.append("R4: statements alone prove nothing")
        result = {"warrant": not problems, "reason": "; ".join(problems) or "the evidence holds up",
                  "minutes": self.spent}  # fmt: skip
        result.update(self._score())
        result["solved"] = result["warrant"] and result["right"]["culprit"]
        return result

    def _score(self) -> dict:
        acc = self.accusation or {}
        truth_path = self.case.path / "truth.json"
        if truth_path.exists():
            crime = json.loads(truth_path.read_text(encoding="utf-8"))["crime"]
            right = {"culprit": acc.get("culprit") == crime["culprit"]["native_id"],
                     "accomplice": acc.get("accomplice") == crime["accomplice"]["native_id"],
                     "method": acc.get("method") == crime["method"]}  # fmt: skip
        else:
            hashes = json.loads((self.case.path / "answers.sha256.json").read_text(encoding="utf-8"))
            salt = hashes["salt"]

            def same(key, value):
                return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest() == hashes[key]

            right = {k: same(k, acc.get(k)) for k in ("culprit", "accomplice", "method")}
        return {"right": right}

    def record(self) -> list[dict]:
        return [asdict(a) for a in self.log]
