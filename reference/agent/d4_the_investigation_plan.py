"""Detective 4 · The investigation plan: a reference solution. Spoilers: `heist use-reference d4`.

The plan does the legwork in code, step by step, and turns what it found into a short list of facts.
The model makes one decision: who, with whom, and how. Its answer can only name people on the lists
(an enum in the schema), its meaning is checked before the chief sees it, and what code can fix,
code fixes. Then the plan checks the answer against the facts it gathered, and sends the model back once
with what disagrees. The fewer things the model has to get right, the less a small model gets wrong.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from heist.case import Case
from heist.precinct import Precinct, cited_sources

KINDS = ("reasoning", "execution", "decision", "validation")
PROBLEMS = ("unknown-person", "same-person", "bad-method", "too-few-sources", "unconsulted-source",
            "no-unguarded-door", "no-badge")  # fmt: skip
OFFICE = "R34"  # the Security Office: the guards' room between rounds, and where the cameras are run
NEAR = timedelta(minutes=20)  # a call this close to the outage is part of the story
SOURCE_NAMES = {"keycard": "keycard log", "camera": "camera log", "phone": "phone records", "bank": "bank records",
                "statement": "statement"}  # fmt: skip


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
    cited = cited_sources(accusation.get("evidence", []))
    if len(cited) < 2:
        found.add("too-few-sources")
    if cited - desk.consulted():
        found.add("unconsulted-source")
    if method == "fire_door" and not unguarded_doors(desk.case):
        found.add("no-unguarded-door")
    if method == "insider" and not any(b.holder_id == culprit for b in desk.case.badges):
        found.add("no-badge")
    return [p for p in PROBLEMS if p in found]


def unguarded_doors(case: Case) -> list[str]:
    """Doors without a card reader that lead into the stolen painting's wing from outside it."""
    wing = case.meta["room"]["wing"]
    inside = {r.room_id for r in case.rooms if r.wing == wing}
    return [d.door_id for d in case.doors if not d.has_reader and (d.room_a in inside) != (d.room_b in inside)]


# ── The steps of the plan: each one calls only its own tools and writes what it found into `notes` ──


def _frame(desk: Precinct, case: Case, notes: dict) -> None:
    """What the briefing says: where the painting hung, and the window between the last round and the alarm."""
    notes["room"], notes["wing"] = case.meta["room"]["id"], case.meta["room"]["wing"]
    notes["seen"], notes["found"] = case.meta["last_seen"][11:], case.meta["discovered"][11:]


def _place(desk: Precinct, case: Case, notes: dict) -> None:
    building = desk.call("floor_plan")
    people = desk.call("list_people")
    notes["people"] = {p["id"]: p for p in people} if isinstance(people, list) else {}
    doors = building.get("doors", []) if isinstance(building, dict) else []
    inside = {r["id"] for r in building.get("rooms", []) if r["wing"] == notes["wing"]} if doors else set()
    notes["unlogged"] = [f"{d['id']} ({d['kind']}, between {d['between'][0]} and {d['between'][1]})" for d in doors
                         if not d["reader"] and (d["between"][0] in inside) != (d["between"][1] in inside)]  # fmt: skip


def _cameras(desk: Precinct, case: Case, notes: dict) -> None:
    """The outage: the moment the most cameras went dark together. A single camera blinking off for a few
    minutes is maintenance; the theft needs every camera on the way dark at once."""
    log = desk.call("camera_log", {"start": notes["seen"], "end": notes["found"]})
    log = log if isinstance(log, list) else []
    offline: dict[str, list[dict]] = {}
    for e in log:
        if e["status"] == "offline":
            offline.setdefault(e["time"], []).append(e)
    if not offline:
        notes["outage"] = None
        return
    dark = max(sorted(offline, key=case.at), key=lambda t: len(offline[t]))  # most cameras; the earliest on a tie
    cams = {e["camera"]: e["room"] for e in offline[dark]}
    back = [
        e["time"] for e in log if e["status"] == "online" and e["camera"] in cams and case.at(e["time"]) > case.at(dark)
    ]
    notes["outage"] = {"dark": dark, "back": max(back, key=case.at) if back else notes["found"], "cameras": cams}
    notes["blips"] = [f"{t}: {', '.join(e['camera'] for e in es)}" for t, es in offline.items() if t != dark]


def _room(desk: Precinct, case: Case, notes: dict) -> None:
    rows = desk.call("keycard_log", {"room": notes["room"], "start": notes["seen"], "end": notes["found"]})
    notes["room_swipes"] = rows if isinstance(rows, list) else []


def _office(desk: Precinct, case: Case, notes: dict) -> None:
    """Who was in the Security Office when the cameras went dark: a badge that went in during the two hours
    before, and didn't open another door between its last entry and the outage."""
    notes["office"], notes["office_since"] = [], {}
    if not notes.get("outage"):
        return
    dark = case.at(notes["outage"]["dark"])
    rows = desk.call("keycard_log", {"room": OFFICE, "start": f"{dark - timedelta(hours=2):%H:%M}",
                                     "end": f"{dark:%H:%M}"})  # fmt: skip
    last: dict[str, dict] = {}
    for r in rows if isinstance(rows, list) else []:
        if r.get("holder") and r["result"] == "granted":
            last[r["badge"]] = r  # rows come in time order: the last one is the latest entry
    for badge, r in sorted(last.items(), key=lambda kv: kv[1]["time"]):
        after = f"{case.at(r['time']) + timedelta(minutes=1):%H:%M}"
        moves = desk.call("keycard_log", {"badge": badge, "start": after, "end": f"{dark:%H:%M}"})
        if moves == []:
            notes["office"].append(r["holder"])
            notes["office_since"][r["holder"]] = r["time"]


def _calls(desk: Precinct, case: Case, notes: dict) -> None:
    """Everyone who was in the office: their calls around the outage, and who was on the other end."""
    notes["calls"] = []
    if not notes.get("outage"):
        return
    lo = case.at(notes["outage"]["dark"]) - NEAR
    hi = case.at(notes["outage"]["back"]) + NEAR
    seen = set()
    for person in notes["office"]:
        if desk.remaining < desk.COSTS["phone_records"] + 2 * desk.COSTS["interview"]:
            break  # keep time to hear the story
        for c in desk.call("phone_records", {"person": person}) or []:
            when = datetime.fromisoformat(c["start"]) if isinstance(c, dict) else None
            key = (c["start"], c["from"], c["to"]) if when else None
            if when and lo <= when <= hi and key not in seen:
                seen.add(key)
                notes["calls"].append(
                    {"time": c["start"][11:], "from": c["from"], "to": c["to"], "seconds": c["seconds"]}
                )


def _story(desk: Precinct, case: Case, notes: dict) -> None:
    """The statements of the people on those calls who weren't in the office."""
    others = []
    for c in notes["calls"]:
        for p in (c["from"], c["to"]):
            if p in notes["people"] and p not in notes["office"] and p not in others:
                others.append(p)
    notes["statements"] = {}
    for p in others[:3]:
        if desk.remaining >= desk.COSTS["interview"]:
            notes["statements"][p] = desk.call("interview", {"person": p})


STEPS = {"frame": _frame, "place": _place, "cameras": _cameras, "room": _room, "office": _office, "calls": _calls,
         "story": _story}  # fmt: skip


# ── The decision ──────────────────────────────────────────────────────────────

SYSTEM = """You are a careful detective. You get the facts an investigation gathered and you name who did it.
Use only these facts. The methods:
- insider: the culprit's own badge opened the painting's room while the cameras were dark.
- borrowed_badge: a badge opened the room while the cameras were dark, but its holder wasn't the one who went in:
  the culprit is the person working with the accomplice, and the badge was someone else's.
- fire_door: no badge opened the room while the cameras were dark, and an unlogged door leads into the wing.
The accomplice is the one who turned the cameras off from the Security Office. The two call each other just
before and just after the outage."""


def facts(desk: Precinct, notes: dict) -> str:
    """What the plan found, as short lines a model can read: people by id, with their name and role."""
    people = notes.get("people", {})

    def who(pid: str | None) -> str:
        p = people.get(pid or "")
        return f"{pid} ({p['name']}, {p['role']})" if p else str(pid)

    lines = [f"The painting hung in room {notes['room']} ({notes['wing']} wing). Last seen at {notes['seen']}, "
             f"missing at {notes['found']}."]  # fmt: skip
    out = notes.get("outage")
    if out:
        cams = ", ".join(f"{c} in {r}" for c, r in sorted(out["cameras"].items()))
        lines.append(f"Camera log: {len(out['cameras'])} cameras went dark together at {out['dark']} and came back at "
                     f"{out['back']}: {cams}.")  # fmt: skip
        if notes.get("blips"):
            lines.append(f"Camera log, short blinks at other times (maintenance): {'; '.join(notes['blips'])}.")
        during = [r for r in notes.get("room_swipes", [])
                  if desk.case.at(out["dark"]) <= desk.case.at(r["time"]) <= desk.case.at(out["back"])]  # fmt: skip
        if during:
            for r in during:
                lines.append(f"Keycard log: at {r['time']}, badge {r['badge']} of {who(r['holder'])} opened door "
                             f"{r['door']} into {r['to_room']} ({r['result']}), while the cameras were dark.")  # fmt: skip
        else:
            lines.append(f"Keycard log: no badge opened {notes['room']} while the cameras were dark.")
        since = notes.get("office_since", {})
        office = ", ".join(f"{who(p)}, in since {since[p]}" for p in notes.get("office", [])) or "nobody"
        lines.append(f"Keycard log: in the Security Office ({OFFICE}) when the cameras went dark, with no swipe "
                     f"anywhere else after going in: {office}.")  # fmt: skip
    else:
        lines.append("Camera log: no camera went dark between the last round and the alarm.")
    unlogged = notes.get("unlogged", [])
    lines.append(f"Floor plan: doors without a card reader into the {notes['wing']} wing: "
                 f"{', '.join(unlogged) if unlogged else 'none'}.")  # fmt: skip
    if notes.get("calls"):
        for c in notes["calls"]:
            lines.append(f"Phone records: at {c['time']}, {who(c['from'])} called {who(c['to'])} ({c['seconds']} s).")
    else:
        lines.append("Phone records: no calls around the outage.")
    for p, text in notes.get("statements", {}).items():
        lines.append(f"Statement of {who(p)}: {' '.join(str(text).split())[:600]}")
    return "\n".join(lines)


def accusation_schema(desk: Precinct) -> dict:
    """The accusation's shape, with the people as an enum: an answer can only name someone on the lists."""
    ids = sorted(p["id"] for p in desk._list_people())
    return {
        "type": "object",
        "properties": {
            "culprit": {"type": "string", "enum": ids},
            "accomplice": {"type": "string", "enum": [*ids, ""]},
            "method": {"type": "string", "enum": ["insider", "borrowed_badge", "fire_door"]},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["culprit", "accomplice", "method", "evidence"],
        "additionalProperties": False,
    }


def contradictions(desk: Precinct, notes: dict, accusation: dict) -> list[str]:
    """Where the accusation disagrees with the facts the plan gathered. validate_accusation checks it against
    the lists and the rules; this checks it against what the logs showed tonight."""
    out = notes.get("outage")
    if not out:
        return []
    at = desk.case.at
    culprit, method = accusation.get("culprit"), accusation.get("method")
    opened = {r["holder"] for r in notes.get("room_swipes", [])
              if r["result"] == "granted" and at(out["dark"]) <= at(r["time"]) <= at(out["back"])}  # fmt: skip
    found = []
    if culprit in notes.get("office", []):
        found.append(f"{culprit} was in the Security Office when the cameras went dark, so they weren't the one in "
                     "the room: whoever was in the office is the accomplice")  # fmt: skip
    if method == "insider" and culprit not in opened:
        found.append("insider means the culprit's own badge opened the room while the cameras were dark, and it didn't")
    if method == "borrowed_badge" and not opened:
        found.append("borrowed_badge needs a badge that opened the room while the cameras were dark, and none did")
    if method == "borrowed_badge" and culprit in opened:
        found.append(f"the badge that opened the room is {culprit}'s own: if it was borrowed, the culprit is the "
                     "person who borrowed it, not its holder")  # fmt: skip
    if method == "fire_door" and opened:
        found.append("fire_door means no badge opened the room while the cameras were dark, and one did")
    return found


def repaired(desk: Precinct, accusation: dict) -> dict:
    """What code can fix without guessing: an id written with a name around it, and evidence lines that cite a
    source nobody consulted (dropped, as long as two kinds of source are left)."""
    ids = {p["id"] for p in desk._list_people()}
    fixed = dict(accusation)
    for field in ("culprit", "accomplice"):
        value = str(fixed.get(field) or "")
        if value and value not in ids:
            inside = [i for i in ids if i in value]
            fixed[field] = inside[0] if len(inside) == 1 else value
    consulted = desk.consulted()
    kept = [e for e in fixed.get("evidence", []) if cited_sources([e]) <= consulted]
    if len(cited_sources(kept)) >= 2:
        fixed["evidence"] = kept
    return fixed


def investigate(case: Case, llm: Any) -> Precinct:
    desk = Precinct(case)
    notes: dict[str, Any] = {}
    for phase in phases(plan(case)):
        for step in phase:
            if step in STEPS:
                STEPS[step](desk, case, notes)
    consulted = ", ".join(SOURCE_NAMES[s] for s in sorted(desk.consulted()))
    prompt = (f"{facts(desk, notes)}\n\nName the culprit, the accomplice and the method. Give three or four lines "
              f"of evidence, one fact each, and name its source in each line with these words: {consulted}. "
              "Those are the only sources consulted tonight: cite no other.")  # fmt: skip
    schema = accusation_schema(desk)
    accusation = repaired(desk, llm.json(prompt, schema, system=SYSTEM))
    problems = validate_accusation(desk, accusation) + contradictions(desk, notes, accusation)
    if problems:
        retry = f"{prompt}\n\nYour last answer was {accusation}. It had these problems: {problems}. Fix them."
        accusation = repaired(desk, llm.json(retry, schema, system=SYSTEM))
    desk.call("accuse", accusation)
    return desk
