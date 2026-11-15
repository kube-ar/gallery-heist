"""Writes a simulated night to disk the way the museum's systems would export it.

Each folder is one system, and the systems don't share a common id for a person: HR knows
employee ids, the events team knows guest ids, the bank knows account numbers. Joining them
is the learner's job.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from .documents import documents, signin_sheet
from .simulate import GENERATOR_VERSION, OUTSIDE, World

ROLE_TITLES = {
    "director": ("Director", "Directorate"),
    "curator": ("Curator", "Collections"),
    "conservator": ("Conservator", "Collections"),
    "registrar": ("Registrar", "Collections"),
    "head_of_security": ("Head of Security", "Security"),
    "guard": ("Security Guard", "Security"),
    "events_manager": ("Events Manager", "Operations"),
    "facilities_tech": ("Facilities Technician", "Operations"),
    "education_officer": ("Education Officer", "Learning"),
}
JOB_TITLES = {"chef": "Chef", "waiter": "Waiter", "av_tech": "AV Technician", "cleaner": "Cleaner"}


def clock(world: World, minutes: int) -> datetime:
    return datetime.fromisoformat(world.date) + timedelta(minutes=minutes)


def stamp(world: World, minutes: int) -> str:
    return clock(world, minutes).strftime("%Y-%m-%dT%H:%M")


def hhmm(world: World, minutes: int) -> str:
    return clock(world, minutes).strftime("%H:%M")


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(header)
        out.writerows(rows)


def export(world: World, folder: Path, case_id: str, pack: str, hide_truth: bool = False) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    people = sorted(world.people.values(), key=lambda p: p.id)
    rng = random.Random(f"{world.seed}:export")
    gala = date.fromisoformat(world.date)

    staff = [p for p in people if p.kind == "staff"]
    _write(
        folder / "hr/staff.csv",
        ["employee_id", "full_name", "role", "department", "phone", "hired"],
        sorted(
            [
                [
                    p.employee_id,
                    p.name,
                    *ROLE_TITLES[p.role],
                    p.phone,
                    (gala - timedelta(days=rng.randint(200, 5000))).isoformat(),
                ]
                for p in staff
            ]
        ),
    )
    guests = [p for p in people if p.kind == "guest"]
    _write(
        folder / "events/guests.csv",
        ["guest_id", "name", "category", "phone", "invited_by"],
        sorted(
            [
                [p.guest_id, f"{p.last}, {p.first}", p.role, p.phone, world.people[world.invited_by[p.id]].employee_id]
                for p in guests
            ]
        ),
    )
    _write(
        folder / "events/seating.csv",
        ["table", "attendee_id"],
        sorted([[t, world.people[pid].native_id] for pid, t in world.seating.items()]),
    )
    workers = [p for p in people if p.kind == "contractor"]
    _write(
        folder / "vendors/contractors.csv",
        ["contractor_id", "company", "worker_name", "job", "phone"],
        sorted([[p.contractor_id, p.company, p.name, JOB_TITLES[p.role], p.phone] for p in workers]),
    )
    _write(
        folder / "security/badges.csv",
        ["badge_id", "holder_type", "holder_id", "zones"],
        sorted([[p.badge, p.kind, p.native_id, ";".join(sorted(p.zones))] for p in people if p.badge]),
    )
    v = world.venue
    _write(
        folder / "facilities/rooms.csv",
        ["room_id", "name", "wing", "public"],
        [[r.id, r.name, r.wing, str(r.public).lower()] for r in v.rooms.values()],
    )
    _write(
        folder / "security/doors.csv",
        ["door_id", "room_a", "room_b", "has_reader", "zone", "kind"],
        [[d.id, d.a, d.b, str(d.reader).lower(), d.zone or "", d.kind] for d in v.doors.values()],
    )
    _write(
        folder / "security/keycard_log.csv",
        ["time", "badge_id", "door_id", "to_room", "result"],
        [
            [stamp(world, s.time), s.badge, s.door, s.to_room, "granted" if s.granted else "denied"]
            for s in world.swipes
        ],
    )
    _write(folder / "security/cameras.csv", ["camera_id", "room_id"], [[c.id, c.room] for c in v.cameras.values()])
    _write(
        folder / "security/camera_log.csv",
        ["time", "camera_id", "status"],
        [[stamp(world, e.time), e.camera, e.status] for e in world.camera_events],
    )
    _write(
        folder / "telecom/calls.csv",
        ["start", "caller", "callee", "seconds"],
        [[stamp(world, c.time), c.caller, c.callee, c.seconds] for c in world.calls],
    )
    _write(
        folder / "finance/accounts.csv",
        ["account_id", "holder_name", "contact_phone"],
        sorted([[p.account, (p.company or f"{p.last} {p.first}").upper(), p.phone] for p in people]),
    )
    _write(
        folder / "finance/transfers.csv",
        ["time", "from_account", "to_account", "amount", "reference"],
        [[stamp(world, x.time), x.source, x.target, x.amount, x.memo] for x in world.transfers],
    )

    # Text: the front desk's handwritten sheet, and documents written after the theft.
    signins, plus_ones = signin_sheet(world)
    _write(
        folder / "frontdesk/signin.csv",
        ["time", "name", "phone", "visiting"],
        [[stamp(world, r.time), r.name, r.phone, r.visiting] for r in signins],
    )
    docs = documents(world)
    _write(
        folder / "documents/index.csv",
        ["doc_id", "kind", "title", "author", "date"],
        [[d.id, d.kind, d.title, d.author_as_written, d.date] for d in docs],
    )
    for d in docs:
        (folder / "documents" / f"{d.id}.txt").write_text(d.text, encoding="utf-8")

    c = world.crime
    assert c is not None
    room = v.rooms[c.room]
    meta = {
        "id": case_id,
        "pack": pack,
        "seed": None if hide_truth else world.seed,
        "level": world.level,
        "generator_version": GENERATOR_VERSION,
        "venue": world.venue_name,
        "date": world.date,
        "artwork": {"title": c.artwork, "artist": c.artist, "year": c.year},
        "room": {"id": room.id, "name": room.name, "wing": room.wing},
        "last_seen": stamp(world, c.last_seen),
        "discovered": stamp(world, c.discovered),
    }
    (folder / "case.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "case.md").write_text(_briefing(world, meta), encoding="utf-8")

    truth = _truth(world)
    truth["people"] += [{"id": x.id, "name": x.name, "kind": x.kind, "role": x.role, "keys": []} for x in plus_ones]
    native = {p.id: p.native_id for p in world.people.values()}
    truth["signin"] = [native.get(r.person) if r.person else None for r in signins]
    truth["documents"] = {d.id: {"author": d.author, **d.gold()} for d in docs}
    if hide_truth:
        salt = hashlib.sha256(f"{world.seed}:salt".encode()).hexdigest()[:16]
        culprit = world.people[c.culprit].native_id or ""
        accomplice = world.people[c.accomplice].native_id or ""
        hashed = {
            "salt": salt,
            "culprit": hashlib.sha256(f"{salt}:{culprit}".encode()).hexdigest(),
            "accomplice": hashlib.sha256(f"{salt}:{accomplice}".encode()).hexdigest(),
            "method": hashlib.sha256(f"{salt}:{c.method}".encode()).hexdigest(),
        }
        (folder / "answers.sha256.json").write_text(json.dumps(hashed, indent=2) + "\n", encoding="utf-8")
    else:
        (folder / "truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _truth(world: World) -> dict:
    c = world.crime
    assert c is not None
    p = world.people

    def key(pid: str) -> dict:
        person = p[pid]
        return {"id": pid, "name": person.name, "native_id": person.native_id, "role": person.role}

    return {
        "warning": "Spoilers. This file is what really happened; the checks read it, you shouldn't.",
        "crime": {
            "method": c.method,
            "culprit": key(c.culprit),
            "accomplice": key(c.accomplice),
            "fence": key(c.fence),
            "badge_victim": key(c.victim) if c.victim else None,
            "room": c.room,
            "start": stamp(world, c.start),
            "end": stamp(world, c.end),
            "stash": c.stash,
            "cameras_off": sorted({e.camera for e in world.camera_events if e.cause == "tampering"}),
            "fire_door_used": c.method == "fire_door",
        },
        "red_herrings": [{**h, **{"person": key(h["person"])}} for h in world.red_herrings],
        "people": [
            {
                "id": person.id,
                "name": person.name,
                "kind": person.kind,
                "role": person.role,
                "keys": [k for k in (person.native_id, person.badge, person.phone, person.account) if k],
            }
            for person in sorted(p.values(), key=lambda x: x.id)
        ],
        "relationships": [{"a": r.a, "b": r.b, "kind": r.kind, "note": r.note} for r in world.relationships],
        "presence": [
            {"person": s.person, "room": s.room, "start": stamp(world, s.start), "end": stamp(world, s.end)}
            for s in world.stays
            if s.room != OUTSIDE
        ],
        "badge_carriers": [
            {"time": stamp(world, s.time), "badge": s.badge, "carried_by": s.carried_by}
            for s in world.swipes
            if world.badge_holders.get(s.badge) != s.carried_by
        ],
    }


def _briefing(world: World, meta: dict) -> str:
    c = world.crime
    assert c is not None
    art = meta["artwork"]
    return f"""# {meta["id"]}: {art["title"]}

On the night of {world.date}, {world.venue_name} held its gala. At {hhmm(world, c.discovered)} a guard
on a round found an empty frame in the {meta["room"]["name"]} ({meta["room"]["wing"]} wing):
*{art["title"]}* by {art["artist"]} ({art["year"]}) was gone. A guard's round at {hhmm(world, c.last_seen)}
had found it in place.

The museum's systems exported everything they recorded that night. They don't share ids:
each system knows people by its own.

| Folder | System | What it holds |
|---|---|---|
| `hr/` | Human resources | Staff, with employee ids and phones |
| `events/` | Events team | Guests, who invited them, the dinner seating |
| `vendors/` | Procurement | Contract workers and their companies |
| `security/` | Security | Badges, doors, the keycard log, cameras and their log |
| `facilities/` | Facilities | Rooms and wings |
| `telecom/` | Phone company | Calls between numbers, the night and the weeks before |
| `finance/` | Bank | Accounts and transfers in the weeks before |

Times are local, `YYYY-MM-DDTHH:MM`. The gala night runs past midnight.
"""
