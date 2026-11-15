"""Detective 4 · The investigation plan: a reference solution. Spoilers: `heist use-reference d4`."""

from __future__ import annotations

import json
from typing import Any

from heist.case import Case
from heist.precinct import SOURCE_WORDS, Precinct

KINDS = ("reasoning", "execution", "decision", "validation")
PROBLEMS = ("unknown-person", "same-person", "bad-method", "too-few-sources", "unconsulted-source",
            "no-unguarded-door", "no-badge")  # fmt: skip


def compound_success(per_step: float, steps: int) -> float:
    return per_step**steps


def plan(case: Case) -> list[dict]:
    return [
        {"id": "frame", "kind": "reasoning", "tools": [], "needs": []},
        {"id": "place", "kind": "execution", "tools": ["floor_plan", "list_people"], "needs": ["frame"]},
        {"id": "cameras", "kind": "execution", "tools": ["camera_log"], "needs": ["frame"]},
        {"id": "room", "kind": "execution", "tools": ["keycard_log"], "needs": ["frame"]},
        {"id": "office", "kind": "execution", "tools": ["keycard_log"], "needs": ["cameras"]},
        {"id": "calls", "kind": "execution", "tools": ["phone_records"], "needs": ["office"]},
        {"id": "story", "kind": "execution", "tools": ["interview"], "needs": ["calls"]},
        {"id": "decide", "kind": "decision", "tools": [], "needs": ["place", "room", "calls", "story"]},
        {"id": "check", "kind": "validation", "tools": [], "needs": ["decide"]},
    ]


def phases(steps: list[dict]) -> list[list[str]]:
    done: set[str] = set()
    left = {s["id"]: set(s["needs"]) for s in steps}
    out = []
    while left:
        ready = sorted(i for i, needs in left.items() if needs <= done)
        if not ready:
            raise ValueError("the plan has a cycle")
        out.append(ready)
        done |= set(ready)
        for i in ready:
            del left[i]
    return out


def validate_accusation(desk: Precinct, accusation: dict) -> list[str]:
    people = {p["id"]: p for p in desk._list_people()}
    found = set()
    culprit, accomplice = accusation.get("culprit"), accusation.get("accomplice") or None
    if culprit not in people or (accomplice and accomplice not in people):
        found.add("unknown-person")
    if accomplice and accomplice == culprit:
        found.add("same-person")
    method = accusation.get("method")
    if method not in ("insider", "borrowed_badge", "fire_door"):
        found.add("bad-method")
    text = " ".join(accusation.get("evidence", [])).lower()
    cited = {kind for kind, words in SOURCE_WORDS.items() if any(w in text for w in words)}
    if len(cited) < 2:
        found.add("too-few-sources")
    if cited - desk.consulted():
        found.add("unconsulted-source")
    if method == "fire_door":
        wing = desk.case.meta["room"]["wing"]
        inside = {r.room_id for r in desk.case.rooms if r.wing == wing}
        if not any(not d.has_reader and (d.room_a in inside) != (d.room_b in inside) for d in desk.case.doors):
            found.add("no-unguarded-door")
    if method == "insider" and not any(b.holder_id == culprit for b in desk.case.badges):
        found.add("no-badge")
    return [p for p in PROBLEMS if p in found]


ACCUSATION = {
    "type": "object",
    "properties": {
        "culprit": {"type": "string"},
        "accomplice": {"type": "string"},
        "method": {"type": "string", "enum": ["insider", "borrowed_badge", "fire_door"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["culprit", "accomplice", "method", "evidence"],
    "additionalProperties": False,
}


def investigate(case: Case, llm: Any) -> Precinct:
    desk = Precinct(case)
    room, wing = case.meta["room"]["id"], case.meta["room"]["wing"]
    seen, found = case.meta["last_seen"][11:], case.meta["discovered"][11:]
    notes: dict[str, Any] = {}
    for phase in phases(plan(case)):
        for step in phase:
            if step == "place":
                notes["floor_plan"] = desk.call("floor_plan")
                notes["people"] = desk.call("list_people")
            elif step == "cameras":
                notes["cameras"] = desk.call("camera_log", {"start": seen, "end": found})
            elif step == "room":
                notes["room"] = desk.call("keycard_log", {"room": room, "start": seen, "end": found})
            elif step == "office":
                dark = [e["time"] for e in notes.get("cameras", []) if e["status"] == "offline"]
                notes["office"] = desk.call("keycard_log", {"room": "R34", "end": min(dark) if dark else found})
            elif step == "calls":
                inside = sorted(
                    {r["holder"] for r in notes.get("office", []) if isinstance(r, dict) and r.get("holder")}
                )
                notes["calls"] = {p: desk.call("phone_records", {"person": p}) for p in inside[:3]}
            elif step == "story":
                notes["story"] = {}
                for p, calls in notes.get("calls", {}).items():
                    tonight = [c for c in calls if isinstance(c, dict) and c["start"][11:] >= seen]
                    for c in tonight[:1]:
                        other = c["to"] if c["from"] == p else c["from"]
                        notes["story"][other] = desk.call("interview", {"person": other})
    prompt = (f"The painting was in room {room} ({wing} wing), last seen {seen}, missing at {found}. "
              "Here is everything gathered. Name the culprit, the accomplice and the method, with evidence that "
              "names its source (camera log, keycard log, phone records, statement).\n\n" + json.dumps(notes, default=str))  # fmt: skip
    accusation = llm.json(prompt, ACCUSATION, system="You are a careful detective. Use only the evidence given.")
    problems = validate_accusation(desk, accusation)
    if problems:
        accusation = llm.json(prompt + f"\n\nYour last answer had these problems: {problems}. Fix them.", ACCUSATION)
    desk.call("accuse", accusation)
    return desk
