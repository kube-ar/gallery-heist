"""Load a case: every system's export as plain Python records.

    from heist.case import load_case
    case = load_case("practice/case-01")
    case.swipes[0]          # Swipe(time=datetime(...), badge_id='B-0412', door_id='D07', ...)
    case.at("22:15")        # a datetime on the gala night (times after midnight roll over)

Nothing here joins the systems together. That's your job.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "cases"
PACK_ORDER = ("practice", "easy", "medium", "hard", "final")


@dataclass(frozen=True)
class StaffMember:
    employee_id: str
    full_name: str
    role: str
    department: str
    phone: str
    hired: str


@dataclass(frozen=True)
class Guest:
    guest_id: str
    name: str  # "Last, First", the way the events team writes it
    category: str
    phone: str
    invited_by: str  # an employee_id


@dataclass(frozen=True)
class Seat:
    table: int
    attendee_id: str  # a guest_id or an employee_id


@dataclass(frozen=True)
class Contractor:
    contractor_id: str
    company: str
    worker_name: str
    job: str
    phone: str


@dataclass(frozen=True)
class Badge:
    badge_id: str
    holder_type: str  # staff | contractor
    holder_id: str  # an employee_id or a contractor_id
    zones: tuple[str, ...]


@dataclass(frozen=True)
class Room:
    room_id: str
    name: str
    wing: str
    public: bool


@dataclass(frozen=True)
class Door:
    door_id: str
    room_a: str
    room_b: str
    has_reader: bool
    zone: str | None
    kind: str  # door | archway | fire


@dataclass(frozen=True)
class Swipe:
    time: datetime
    badge_id: str
    door_id: str
    to_room: str  # the room on the far side of the door
    granted: bool


@dataclass(frozen=True)
class Camera:
    camera_id: str
    room_id: str


@dataclass(frozen=True)
class CameraEvent:
    time: datetime
    camera_id: str
    status: str  # online | offline


@dataclass(frozen=True)
class Call:
    start: datetime
    caller: str  # phone number
    callee: str
    seconds: int


@dataclass(frozen=True)
class Account:
    account_id: str
    holder_name: str  # as the bank writes it
    contact_phone: str


@dataclass(frozen=True)
class Transfer:
    time: datetime
    from_account: str
    to_account: str
    amount: int
    reference: str


@dataclass(frozen=True)
class SignIn:
    time: datetime
    name: str  # as the guest wrote it
    phone: str  # as written: often missing, sometimes misread
    visiting: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    kind: str  # statement | email | report | press
    title: str
    author: str  # as written
    date: str
    text: str


@dataclass
class Case:
    id: str
    path: Path
    meta: dict
    staff: list[StaffMember] = field(default_factory=list)
    guests: list[Guest] = field(default_factory=list)
    seating: list[Seat] = field(default_factory=list)
    contractors: list[Contractor] = field(default_factory=list)
    badges: list[Badge] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    doors: list[Door] = field(default_factory=list)
    swipes: list[Swipe] = field(default_factory=list)
    cameras: list[Camera] = field(default_factory=list)
    camera_log: list[CameraEvent] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    signins: list[SignIn] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    @property
    def date(self) -> datetime:
        return datetime.fromisoformat(self.meta["date"])

    def at(self, hhmm: str) -> datetime:
        """A time on the gala night. Before noon means after midnight: "00:20" is the next day."""
        t = time.fromisoformat(hhmm)
        day = self.date + (timedelta(days=1) if t.hour < 12 else timedelta())
        return datetime.combine(day.date(), t)

    @property
    def briefing(self) -> str:
        return (self.path / "case.md").read_text(encoding="utf-8")

    def __repr__(self) -> str:
        return f"<Case {self.id}: {self.meta['artwork']['title']}>"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_case(name: str | Path) -> Case:
    """Load a case by name ("practice/case-01") or by path."""
    path = Path(name)
    if not path.is_absolute() and not (path / "case.json").exists():
        path = CASES / name
    if not (path / "case.json").exists():
        raise FileNotFoundError(f"no case at {path} (try `heist cases`)")
    meta = json.loads((path / "case.json").read_text(encoding="utf-8"))
    c = Case(id=f"{meta['pack']}/{meta['id']}", path=path, meta=meta)
    c.staff = [StaffMember(**r) for r in _rows(path / "hr/staff.csv")]
    c.guests = [Guest(**r) for r in _rows(path / "events/guests.csv")]
    c.seating = [Seat(int(r["table"]), r["attendee_id"]) for r in _rows(path / "events/seating.csv")]
    c.contractors = [Contractor(**r) for r in _rows(path / "vendors/contractors.csv")]
    c.badges = [
        Badge(r["badge_id"], r["holder_type"], r["holder_id"], tuple(z for z in r["zones"].split(";") if z))
        for r in _rows(path / "security/badges.csv")
    ]
    c.rooms = [
        Room(r["room_id"], r["name"], r["wing"], r["public"] == "true") for r in _rows(path / "facilities/rooms.csv")
    ]
    c.doors = [
        Door(r["door_id"], r["room_a"], r["room_b"], r["has_reader"] == "true", r["zone"] or None, r["kind"])
        for r in _rows(path / "security/doors.csv")
    ]
    c.swipes = [
        Swipe(_dt(r["time"]), r["badge_id"], r["door_id"], r["to_room"], r["result"] == "granted")
        for r in _rows(path / "security/keycard_log.csv")
    ]
    c.cameras = [Camera(**r) for r in _rows(path / "security/cameras.csv")]
    c.camera_log = [
        CameraEvent(_dt(r["time"]), r["camera_id"], r["status"]) for r in _rows(path / "security/camera_log.csv")
    ]
    c.calls = [
        Call(_dt(r["start"]), r["caller"], r["callee"], int(r["seconds"])) for r in _rows(path / "telecom/calls.csv")
    ]
    c.accounts = [Account(**r) for r in _rows(path / "finance/accounts.csv")]
    c.transfers = [
        Transfer(_dt(r["time"]), r["from_account"], r["to_account"], int(r["amount"]), r["reference"])
        for r in _rows(path / "finance/transfers.csv")
    ]
    signin = path / "frontdesk/signin.csv"
    if signin.exists():
        c.signins = [SignIn(_dt(r["time"]), r["name"], r["phone"], r["visiting"]) for r in _rows(signin)]
    index = path / "documents/index.csv"
    if index.exists():
        c.documents = [
            Document(r["doc_id"], r["kind"], r["title"], r["author"], r["date"],
                     (path / "documents" / f"{r['doc_id']}.txt").read_text(encoding="utf-8"))
            for r in _rows(index)
        ]  # fmt: skip
    return c


def list_cases(pack: str | None = None) -> list[str]:
    """Case names, like "practice/case-01". Pass a pack to list only that one."""
    order = {name: i for i, name in enumerate(PACK_ORDER)}
    found = sorted(
        (p.parent.relative_to(CASES).as_posix() for p in CASES.glob("*/*/case.json")),
        key=lambda n: (order.get(n.split("/")[0], len(order)), n),
    )
    return [n for n in found if pack is None or n.startswith(f"{pack}/")]
