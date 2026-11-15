"""Simulates one gala night: who was where, minute by minute, and what every system logged.

Everything is derived from a seed, so a case can always be rebuilt exactly. Each part of the
world draws from its own random stream (`_rng(seed, "people")`, ...), so adding a new part
later (documents, interviews) never changes the parts that already exist.

Times inside the simulation are minutes after midnight on the gala day; values above 1440
fall on the next day.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import names
from .venue import OUTSIDE, Venue, build_venue

GENERATOR_VERSION = 2

ATRIUM, DINING, TERRACE, KITCHEN, SERVICE = "R03", "R04", "R05", "R31", "R30"
LOADING, VAULT, SECURITY, STAFF_ROOM, OFFICES = "R32", "R33", "R34", "R35", "R36"
ENTRANCE, CLOAKROOM = "R01", "R02"
EAST_GALLERIES, WEST_GALLERIES, LAB = ["R11", "R12"], ["R21", "R22"], "R13"


def _rng(seed: int, part: str) -> random.Random:
    return random.Random(f"{seed}:{part}")


# ── Difficulty ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Level:
    guests: int
    guards: int
    waiters: int
    methods: tuple[str, ...]
    ring_cycle: bool  # money passed around a loop to blur where it came from
    innocent_cycle: bool  # flatmates sharing rent: a loop that proves nothing
    cleaner: bool
    camera_blips: int
    denied_noise: int


LEVELS = {
    "practice": Level(8, 3, 2, ("insider",), False, False, False, 0, 1),
    "easy": Level(10, 3, 2, ("insider",), False, False, False, 0, 2),
    "medium": Level(14, 4, 3, ("borrowed_badge", "insider"), True, False, True, 1, 3),
    "hard": Level(20, 5, 4, ("fire_door", "borrowed_badge"), True, True, True, 2, 4),
    "final": Level(18, 5, 4, ("fire_door", "borrowed_badge", "insider"), True, True, True, 2, 4),
}

ZONES = {
    "director": {"service", "offices", "east", "west"},
    "curator": {"service", "offices", "east", "west"},
    "conservator": {"service", "offices", "east"},
    "registrar": {"service", "offices", "east", "west", "vault"},
    "head_of_security": {"service", "offices", "east", "west", "vault", "security"},
    "guard": {"service", "offices", "east", "west", "vault", "security"},
    "events_manager": {"service", "offices"},
    "education_officer": {"service", "offices"},
    "facilities_tech": {"service", "offices", "security"},
    "chef": {"service"},
    "waiter": {"service"},
    "av_tech": {"service"},
    "cleaner": {"service", "offices"},
}

HOSTS = ("director", "curator", "events_manager", "education_officer", "conservator", "registrar")


# ── Records ───────────────────────────────────────────────────────────────────


@dataclass
class Person:
    id: str
    first: str
    last: str
    kind: str  # staff | guest | contractor | external
    role: str
    employee_id: str | None = None
    guest_id: str | None = None
    contractor_id: str | None = None
    company: str | None = None
    phone: str | None = None
    account: str | None = None
    badge: str | None = None
    zones: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}" if self.first else self.last

    @property
    def native_id(self) -> str | None:
        return self.employee_id or self.guest_id or self.contractor_id


@dataclass
class Stay:
    person: str
    room: str
    start: int
    end: int


@dataclass
class Swipe:
    time: int
    badge: str
    door: str
    to_room: str
    granted: bool
    carried_by: str  # who really held the badge (truth only)


@dataclass
class Call:
    time: int  # minutes relative to midnight of the gala day (negative = days before)
    caller: str
    callee: str
    seconds: int


@dataclass
class Transfer:
    time: int
    source: str
    target: str
    amount: int
    memo: str


@dataclass
class CameraEvent:
    time: int
    camera: str
    status: str  # online | offline
    cause: str  # truth only: start | tampering | maintenance


@dataclass
class Relationship:
    a: str
    b: str
    kind: str  # sibling | spouse | friend | flatmate | lender | ring
    note: str = ""


@dataclass
class Crime:
    method: str
    culprit: str
    accomplice: str
    fence: str
    victim: str | None  # whose badge was borrowed
    room: str
    start: int
    end: int
    last_seen: int  # last guard visit before the theft
    discovered: int
    discovered_by: str
    stash: str
    artwork: str
    artist: str
    year: int


@dataclass
class World:
    seed: int
    level: str
    venue: Venue
    venue_name: str
    date: str  # ISO date of the gala
    people: dict[str, Person]
    stays: list[Stay] = field(default_factory=list)
    swipes: list[Swipe] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    camera_events: list[CameraEvent] = field(default_factory=list)
    seating: dict[str, int] = field(default_factory=dict)  # person -> table
    invited_by: dict[str, str] = field(default_factory=dict)  # guest -> host
    relationships: list[Relationship] = field(default_factory=list)
    crime: Crime | None = None
    red_herrings: list[dict] = field(default_factory=list)
    badge_holders: dict[str, str] = field(default_factory=dict)  # badge -> person
    shells: dict[str, str] = field(default_factory=dict)  # account -> company name


# ── Walking ───────────────────────────────────────────────────────────────────


class Walker:
    """Moves one person through the venue and records stays and badge swipes."""

    def __init__(self, world: World, person: Person, room: str, t: int):
        self.w = world
        self.p = person
        self.room = room
        self.t = t
        self.since = t
        self.badge = person.badge
        self.zones = person.zones
        self.extra: frozenset[str] = frozenset()

    def _close(self, at: int) -> None:
        if at > self.since:
            self.w.stays.append(Stay(self.p.id, self.room, self.since, at))
        self.since = at

    def wait(self, until: int) -> None:
        self.t = max(self.t, until)

    def hops(self, room: str, escorted: bool = False) -> int:
        zones = self._route_zones(escorted)
        return len(self.w.venue.route(self.room, room, zones, self.extra))

    def _route_zones(self, escorted: bool) -> frozenset[str]:
        return frozenset({"east", "west", "service", "offices"}) if escorted else self.zones

    def go(self, room: str, at: int | None = None, escorted: bool = False) -> None:
        """Leave at `at` (or now) and walk to `room`, one minute per door."""
        if at is not None:
            self.wait(at)
        if room == self.room:
            return
        route = self.w.venue.route(self.room, room, self._route_zones(escorted), self.extra)
        for i, door in enumerate(route):
            t = self.t + i
            nxt = door.other(self.room)
            if door.reader and not escorted:
                self.w.swipes.append(Swipe(t, self.badge or "", door.id, nxt, True, self.p.id))
            self._close(t)
            self.room = nxt
        self.t += len(route)  # the last room is entered at t + n - 1 and held for at least a minute

    def arrive(self, room: str, by: int) -> None:
        """Walk to `room` so that you get there exactly at `by`."""
        depart = by - self.hops(room) + 1
        if depart < self.t:
            raise _Retry(f"{self.p.id} can't reach {room} by {by} (now {self.t} in {self.room})")
        self.go(room, depart)

    def drop_badge(self) -> None:
        self.badge, self.zones = None, frozenset()

    def pick_up_badge(self) -> None:
        self.badge, self.zones = self.p.badge, self.p.zones

    def try_door(self, door_id: str, at: int) -> None:
        """A swipe the reader refuses: the person stays where they are."""
        self.wait(at)
        door = self.w.venue.doors[door_id]
        self.w.swipes.append(Swipe(self.t, self.badge or "", door_id, door.other(self.room), False, self.p.id))
        self.t += 1

    def finish(self, at: int) -> None:
        self.wait(at)
        self._close(self.t)


# ── Building a case ───────────────────────────────────────────────────────────


def simulate(seed: int, level_name: str, method: str | None = None) -> World:
    """Build a whole case. Retries with a derived seed if the plot can't fit the night.

    `method` forces how the theft is done (insider, borrowed_badge, fire_door); by default
    the level picks one.
    """
    for attempt in range(50):
        try:
            return _simulate(seed, level_name, attempt, method)
        except _Retry:
            continue
    raise RuntimeError(f"could not build a case for seed {seed}")


class _Retry(Exception):
    pass


def _simulate(seed: int, level_name: str, attempt: int, method: str | None) -> World:
    level = LEVELS[level_name]
    tag = f"{seed}/{attempt}"
    r_people, r_plot, r_night = _rng(tag, "people"), _rng(tag, "plot"), _rng(tag, "night")
    r_money, r_calls = _rng(tag, "money"), _rng(tag, "calls")

    picked = r_plot.choice(level.methods)
    plot_method = method or picked
    venue = build_venue(r_plot, propped=False)
    month, day = r_plot.randint(2, 11), r_plot.randint(3, 27)
    world = World(
        seed=seed,
        level=level_name,
        venue=venue,
        venue_name=r_plot.choice(names.VENUES),
        date=f"2026-{month:02d}-{day:02d}",
        people={},
    )
    _cast(world, level, r_people)
    crime = _plot(world, level, plot_method, r_plot)
    world.crime = crime
    _night(world, level, r_night, tag)
    _money(world, level, r_money)
    _calls(world, r_calls)
    world.stays.sort(key=lambda s: (s.start, s.person))
    world.swipes.sort(key=lambda s: (s.time, s.badge, s.door))
    world.calls.sort(key=lambda c: (c.time, c.caller))
    world.transfers.sort(key=lambda x: (x.time, x.source))
    world.camera_events.sort(key=lambda e: (e.time, e.camera))
    return world


def _cast(world: World, level: Level, rng: random.Random) -> None:
    firsts = rng.sample(names.FIRST_NAMES, len(names.FIRST_NAMES))
    lasts = rng.sample(names.LAST_NAMES, len(names.LAST_NAMES))
    phones = rng.sample(range(1000), 200)
    accounts = rng.sample(range(100000, 999999), 200)
    emp_ids = rng.sample(range(1000, 1999), 60)
    guest_ids = rng.sample(range(100, 999), 60)
    con_ids = rng.sample(range(200, 899), 60)
    badge_ids = rng.sample(range(100, 999), 60)
    counter = {"p": 0}

    def person(kind: str, role: str, last: str | None = None, company: str | None = None) -> Person:
        counter["p"] += 1
        p = Person(
            id=f"P{counter['p']:02d}",
            first="" if role == "shell" else firsts.pop(),
            last=last or lasts.pop(),
            kind=kind,
            role=role,
            company=company,
        )
        p.phone = f"+44 7700 900{phones.pop():03d}"
        p.account = f"ACC-{accounts.pop()}"
        if kind == "staff":
            p.employee_id = f"E-{emp_ids.pop()}"
        elif kind == "guest":
            p.guest_id = f"G-{guest_ids.pop()}"
        elif kind == "contractor":
            p.contractor_id = f"C-{con_ids.pop()}"
        if role in ZONES:
            p.badge = f"B-0{badge_ids.pop()}"
            p.zones = frozenset(ZONES[role])
            world.badge_holders[p.badge] = p.id
        world.people[p.id] = p
        return p

    staff_roles = ["director", "curator", "curator", "conservator", "registrar", "head_of_security"]
    staff_roles += ["guard"] * level.guards + ["events_manager", "facilities_tech"]
    if level.cleaner:
        staff_roles.append("education_officer")
    for role in staff_roles:
        person("staff", role)

    caterer, av, cleaning = rng.choice(names.CATERERS), rng.choice(names.AV_COMPANIES), rng.choice(names.CLEANERS)
    person("contractor", "chef", company=caterer)
    for _ in range(level.waiters):
        person("contractor", "waiter", company=caterer)
    person("contractor", "av_tech", company=av)
    if level.cleaner:
        person("contractor", "cleaner", company=cleaning)

    guests = [
        person("guest", rng.choice(["donor", "collector", "artist", "board member", "journalist", "donor"]))
        for _ in range(level.guests)
    ]

    # Family ties: a sibling pair shares a surname, a married couple doesn't have to.
    cast = [p for p in world.people.values()]
    a, b = rng.sample(cast, 2)
    b.last = a.last
    world.relationships.append(Relationship(a.id, b.id, "sibling"))
    c, d = rng.sample([p for p in guests if p.id not in (a.id, b.id)], 2)
    world.relationships.append(Relationship(c.id, d.id, "spouse"))
    for _ in range(3 + level.guests // 4):
        x, y = rng.sample(cast, 2)
        world.relationships.append(Relationship(x.id, y.id, "friend"))

    # People who never came: they only show up in phone and bank records.
    person("external", "fence")
    person("external", "lender")
    for _ in range(2):
        person("external", "relative")
    # Two companies on paper. The bank has the fence's mobile as their contact number.
    fence = _by_role(world, "fence")[0]
    for company in rng.sample(names.SHELL_COMPANIES, 2):
        shell = person("external", "shell", last=company, company=company)
        shell.phone = fence.phone
        world.shells[shell.account or ""] = company


def _by_role(world: World, role: str) -> list[Person]:
    return [p for p in world.people.values() if p.role == role]


def _plot(world: World, level: Level, method: str, rng: random.Random) -> Crime:
    people = world.people
    guards = _by_role(world, "guard")
    accomplice = rng.choice(guards)
    fence = _by_role(world, "fence")[0]
    victim = None

    if method == "insider":
        culprit = rng.choice(_by_role(world, "curator") + _by_role(world, "conservator") + _by_role(world, "registrar"))
        rooms = [r for r in EAST_GALLERIES if "east" in culprit.zones] + [
            r for r in WEST_GALLERIES if "west" in culprit.zones
        ]
        room = rng.choice(rooms)
        stash = OFFICES
    elif method == "borrowed_badge":
        culprit = rng.choice([p for p in people.values() if p.role in ("waiter", "av_tech") or p.kind == "guest"])
        victim = rng.choice(_by_role(world, "curator") + _by_role(world, "registrar"))
        room = rng.choice(EAST_GALLERIES + WEST_GALLERIES)
        stash = LOADING
    else:  # fire_door
        culprit = rng.choice(_by_role(world, "waiter") + _by_role(world, "chef"))
        room = LAB
        stash = LOADING

    world.relationships.append(Relationship(culprit.id, accomplice.id, "ring", "old friends from a previous job"))
    world.relationships.append(Relationship(culprit.id, fence.id, "ring", "the buyer's go-between"))
    title, artist = rng.choice(names.ARTWORK_TITLES), rng.choice(names.ARTISTS)
    return Crime(
        method=method,
        culprit=culprit.id,
        accomplice=accomplice.id,
        fence=fence.id,
        victim=victim.id if victim else None,
        room=room,
        start=0,
        end=0,
        last_seen=0,
        discovered=1425,
        discovered_by="",
        stash=stash,
        artwork=title,
        artist=artist,
        year=rng.randint(1868, 1931),
    )


# ── The night ─────────────────────────────────────────────────────────────────


def _night(world: World, level: Level, rng: random.Random, tag: str) -> None:
    crime = world.crime
    assert crime is not None
    people = world.people
    ring = {crime.culprit, crime.accomplice}
    if crime.victim:
        ring.add(crime.victim)

    for cam in world.venue.cameras:
        world.camera_events.append(CameraEvent(1050, cam, "online", "start"))

    # 1. Guards who aren't in on it walk their rounds; one of them finds the empty frame.
    #    They walk twice: once to find a quiet moment for the theft, then again from the same
    #    random stream, skipping the room after the theft so the finder is the first to see it.
    guards = [g for g in _by_role(world, "guard") if g.id != crime.accomplice]
    finder = rng.choice(guards)
    crime.discovered_by = finder.id
    mark = (len(world.stays), len(world.swipes))

    def walk_guards(skip_after: int | None) -> None:
        rounds_rng = _rng(tag, "guards")
        for g in guards:
            _guard(world, g, rounds_rng, discover=(g is finder), skip_after=skip_after)

    walk_guards(None)

    # 2. Pick the theft window: nobody in the room, and a guard saw the painting earlier.
    visits = [s for s in world.stays if s.room == crime.room]
    duration = rng.randint(6, 10)
    options = []
    for start in range(1330, 1396):
        end = start + duration
        if any(s.start < end + 6 and s.end > start - 6 for s in visits):
            continue
        before = [s.end for s in visits if s.end <= start - 6]
        if before and max(before) >= 1290:
            options.append((start, max(before)))
    if not options:
        raise _Retry
    crime.start, crime.last_seen = rng.choice(options)
    crime.end = crime.start + duration
    del world.stays[mark[0] :], world.swipes[mark[1] :]
    walk_guards(crime.start)
    _head_of_security(world, _by_role(world, "head_of_security")[0], rng)

    # 3. The ring.
    _accomplice(world, people[crime.accomplice], rng)
    if crime.victim:
        _staff_evening(world, people[crime.victim], rng, victim=True)
    _culprit(world, people[crime.culprit], rng)

    # 4. Everybody else. A few workers swipe a door they can't open: a mistake, not a plan.
    kitchen = [
        p for p in sorted(people.values(), key=lambda p: p.id) if p.role in ("waiter", "chef") and p.id not in ring
    ]
    denied = {p.id: rng.choice(["D25", "D24", "D21"]) for p in kitchen[: level.denied_noise]}
    for p in sorted(people.values(), key=lambda p: p.id):
        if p.id in ring or p.role in ("guard", "head_of_security") or p.kind == "external":
            continue
        if p.kind == "guest":
            _guest(world, p, rng)
        elif p.role in HOSTS:
            _staff_evening(world, p, rng)
        else:
            _worker(world, p, rng, denied=denied.get(p.id))
    if denied:
        first = next(iter(denied))
        world.red_herrings.append(
            {"person": first, "kind": "denied_swipe", "why": f"tried door {denied[first]} and was refused"}
        )

    # 5. Red herrings and noise.
    _herrings(world, level, rng)
    _seating(world, rng)
    _check_room_empty(world)


def _check_room_empty(world: World) -> None:
    """Nobody but the culprit may be in the room during the theft."""
    c = world.crime
    assert c is not None
    for s in world.stays:
        if s.room == c.room and s.person != c.culprit and s.start < c.end and s.end > c.start:
            raise _Retry


def _arrive_staff(w: Walker, rng: random.Random, early: int, late: int) -> None:
    w.go(LOADING, rng.randint(early, late))


def _leave_staff(w: Walker, at: int) -> None:
    w.go(OUTSIDE, at)
    w.finish(at + 6)


def _mingle(
    w: Walker, rng: random.Random, until: int, rooms=(ATRIUM, DINING, TERRACE), stop: int | None = None
) -> None:
    """Drift between rooms until `until` (or until `stop`, to break off for something else)."""
    end = until if stop is None else min(until, stop)
    while w.t < end:
        room = rng.choice(rooms)
        w.go(room)
        w.wait(min(end, w.t + rng.randint(8, 22)))


def _guard(world: World, g: Person, rng: random.Random, discover: bool, skip_after: int | None = None) -> None:
    w = Walker(world, g, OUTSIDE, 1040)
    _arrive_staff(w, rng, 1040, 1065)
    w.go(SECURITY)
    t = 1090 + rng.randint(0, 30)
    rounds = [EAST_GALLERIES + [LAB], WEST_GALLERIES + ["R23"]]
    turn = rng.randint(0, 1)
    last = 1405 if discover else 1440
    target = world.crime.room if world.crime else None
    while t < last - 35:
        w.wait(t)
        for room in rounds[turn % 2]:
            if skip_after is not None and w.t >= skip_after and room == target:
                continue  # after the theft, only the finder walks into that room
            w.go(room)
            w.wait(w.t + rng.randint(2, 4))
        w.go(SECURITY)
        turn += 1
        t = w.t + rng.randint(25, 45)
    if discover:
        c = world.crime
        assert c is not None
        w.wait(max(w.t, 1412))
        w.arrive(c.room, c.discovered)
        w.wait(c.discovered + 12)
        w.go(SECURITY)
        w.wait(1460)
    _leave_staff(w, max(w.t, 1470) + rng.randint(0, 10))


def _head_of_security(world: World, h: Person, rng: random.Random) -> None:
    w = Walker(world, h, OUTSIDE, 1030)
    _arrive_staff(w, rng, 1030, 1045)
    w.go(SECURITY)
    w.wait(1180)
    w.go(ATRIUM)  # greets the guests
    w.wait(1215)
    w.go(SECURITY)
    w.wait(1440)
    _leave_staff(w, 1485)


def _accomplice(world: World, a: Person, rng: random.Random) -> None:
    """A guard in on it: kills the cameras while the culprit works, and props the fire door."""
    c = world.crime
    assert c is not None
    w = Walker(world, a, OUTSIDE, 1040)
    _arrive_staff(w, rng, 1040, 1060)
    w.go(SECURITY)
    t = 1100 + rng.randint(0, 25)
    rounds = [EAST_GALLERIES + [LAB], WEST_GALLERIES + ["R23"]]
    turn = rng.randint(0, 1)
    prop_at = c.start - rng.randint(40, 60) if c.method == "fire_door" else None
    while t < c.start - 50:
        w.wait(t)
        for room in rounds[turn % 2]:
            if room == c.room:
                continue  # skips the target room so nobody else's round lines up with the theft
            w.go(room)
            w.wait(w.t + rng.randint(2, 4))
        w.go(SECURITY)
        turn += 1
        t = w.t + rng.randint(30, 45)
    if prop_at is not None:
        w.go(LAB, max(w.t, prop_at))
        w.wait(w.t + 2)
        w.go(SECURITY)
    w.wait(max(w.t, c.start - 8))
    cams = _cameras_for(world)
    for cam in cams:
        world.camera_events.append(CameraEvent(c.start - 2, cam, "offline", "tampering"))
        world.camera_events.append(CameraEvent(c.end + 4, cam, "online", "tampering"))
    w.wait(c.end + 8)
    t = w.t + 20
    while t < 1440:
        w.wait(t)
        for room in rounds[turn % 2]:
            if room == c.room:
                continue  # stays away from the empty frame and lets someone else find it
            w.go(room)
            w.wait(w.t + rng.randint(2, 4))
        w.go(SECURITY)
        turn += 1
        t = w.t + rng.randint(30, 45)
    _leave_staff(w, max(w.t, 1470) + rng.randint(0, 10))


def _cameras_for(world: World) -> list[str]:
    c = world.crime
    assert c is not None
    rooms = {c.room, "R10" if c.room in EAST_GALLERIES + [LAB] else "R20"}
    if c.stash == LOADING:
        rooms.add(LOADING)
    return sorted(cam.id for cam in world.venue.cameras.values() if cam.room in rooms)


def _culprit(world: World, p: Person, rng: random.Random) -> None:
    c = world.crime
    assert c is not None
    leave_for_job = c.start - 12

    def job(w: Walker) -> None:
        if c.method == "borrowed_badge":
            victim = world.people[c.victim or ""]
            w.badge = victim.badge
            w.zones = p.zones | victim.zones
        if c.method == "fire_door":
            w.extra = frozenset({"D12"})
        w.arrive(c.room, c.start)
        w.wait(c.end)
        w.go(c.stash)
        w.wait(w.t + 3)
        if c.method == "borrowed_badge":
            w.go(STAFF_ROOM)  # puts the badge back in the jacket
            w.wait(w.t + 2)
            w.badge, w.zones = p.badge, p.zones
        w.extra = frozenset()

    if p.kind == "guest":
        _guest(world, p, rng, job=job, job_at=leave_for_job, borrow=True)
    elif p.role in HOSTS:
        _staff_evening(world, p, rng, job=job, job_at=leave_for_job)
    else:
        _worker(world, p, rng, job=job, job_at=leave_for_job, borrow=c.method == "borrowed_badge")


def _guest(world: World, p: Person, rng: random.Random, job=None, job_at: int = 0, borrow: bool = False) -> None:
    w = Walker(world, p, OUTSIDE, 1135)
    arrive = rng.randint(1140, 1185)
    w.go(ENTRANCE, arrive)
    w.go(CLOAKROOM, arrive + 1)
    w.go(ATRIUM, arrive + rng.randint(3, 5))
    if rng.random() < 0.3 and arrive < 1165:
        gallery = rng.choice(EAST_GALLERIES + WEST_GALLERIES)
        w.go(gallery, max(w.t, 1168), escorted=True)  # curator's tour: escorted guests don't swipe
        w.wait(1185)
        w.go(ATRIUM, escorted=True)
    w.wait(1195)
    w.go(DINING, rng.randint(1196, 1203))
    if borrow:
        w.go(STAFF_ROOM, rng.randint(1240, 1265))  # slips out through the kitchen, takes a badge from a jacket
        w.wait(w.t + 3)
        w.go(DINING)
    elif rng.random() < 0.4:
        w.go(TERRACE, rng.randint(1230, 1260))
        w.wait(w.t + rng.randint(4, 10))
        w.go(DINING)
    w.go(ATRIUM, rng.randint(1288, 1293))
    w.wait(1320)
    leave = rng.randint(1350, 1470)
    if job:
        leave = max(leave, world.crime.end + 40)  # type: ignore[union-attr]
        _mingle(w, rng, job_at)
        job(w)
        w.go(ATRIUM)
    _mingle(w, rng, leave)
    w.go(CLOAKROOM)
    w.go(OUTSIDE, w.t + 2)
    w.finish(w.t + 4)


def _staff_evening(world: World, p: Person, rng: random.Random, job=None, job_at: int = 0, victim=False) -> None:
    """Hosts: a bit of backstage work, then the gala with the guests."""
    w = Walker(world, p, OUTSIDE, 1045)
    _arrive_staff(w, rng, 1050, 1110)
    first = {"conservator": LAB, "registrar": VAULT}.get(p.role, OFFICES)
    w.go(first)
    if victim:
        w.go(STAFF_ROOM, 1118)  # leaves a jacket, badge in the pocket
        w.drop_badge()
        w.wait(w.t + 3)
    w.wait(1130)
    w.go(ATRIUM)
    if p.role == "curator" and not victim:
        w.go(rng.choice(EAST_GALLERIES + WEST_GALLERIES), 1166)  # leads a short tour
        w.wait(1185)
        w.go(ATRIUM)
    w.wait(1195)
    w.go(DINING, 1198)
    if p.role == "events_manager":
        for _ in range(3):
            w.go(KITCHEN, w.t + rng.randint(12, 25))
            w.wait(w.t + 3)
            w.go(DINING)
    w.go(ATRIUM, 1288)
    w.wait(1320)
    leave = rng.randint(1445, 1475)
    if job:
        _mingle(w, rng, job_at)
        job(w)
        w.go(ATRIUM)
    elif victim:
        _mingle(w, rng, 1440, rooms=(ATRIUM, DINING))
        w.go(STAFF_ROOM)  # collects the jacket
        w.pick_up_badge()
        w.wait(w.t + 2)
    else:
        if rng.random() < 0.5:
            _mingle(w, rng, rng.randint(1330, 1400))
            w.go(OFFICES)
            w.wait(w.t + rng.randint(5, 12))
            w.go(ATRIUM)
    _mingle(w, rng, leave)
    _leave_staff(w, max(w.t, leave))


def _worker(
    world: World,
    p: Person,
    rng: random.Random,
    job=None,
    job_at: int = 0,
    borrow: bool = False,
    denied: str | None = None,
) -> None:
    """Contractors and backstage staff: kitchen, trays, the loading dock."""
    w = Walker(world, p, OUTSIDE, 1060)
    _arrive_staff(w, rng, 1065, 1110)
    home = {"chef": KITCHEN, "waiter": KITCHEN, "av_tech": ATRIUM, "cleaner": OFFICES, "facilities_tech": SECURITY}
    base = home.get(p.role, KITCHEN)
    w.go(base)
    rooms = {
        "chef": (KITCHEN, KITCHEN, KITCHEN, LOADING),
        "waiter": (KITCHEN, DINING, ATRIUM, DINING, KITCHEN, TERRACE),
        "av_tech": (ATRIUM, ATRIUM, SERVICE, LOADING),
        "cleaner": (OFFICES, STAFF_ROOM, KITCHEN, SERVICE),
        "facilities_tech": (SECURITY, LOADING, ATRIUM, SERVICE),
    }[p.role]
    leave = rng.randint(1455, 1480)
    if job:
        if borrow:
            _mingle(w, rng, rng.randint(1250, 1290), rooms=rooms)
            w.go(STAFF_ROOM)  # takes a badge from a jacket
            w.wait(w.t + 3)
        _mingle(w, rng, job_at, rooms=rooms)
        job(w)
        w.go(base)
    if denied:
        _mingle(w, rng, rng.randint(1300, 1410), rooms=rooms)
        w.go(SERVICE)
        w.try_door(denied, w.t)  # wrong door: the reader refuses
    if p.role == "waiter" and not job:
        _mingle(w, rng, rng.randint(1330, 1380), rooms=rooms)
        w.go(STAFF_ROOM)  # break
        w.wait(w.t + rng.randint(8, 12))
    _mingle(w, rng, leave, rooms=rooms)
    _leave_staff(w, max(w.t, leave))


def _herrings(world: World, level: Level, rng: random.Random) -> None:
    c = world.crime
    assert c is not None
    # Someone who could have done it, owes money, and has a reason to look nervous.
    pool = [
        p
        for p in world.people.values()
        if p.kind == "staff" and p.id not in (c.culprit, c.accomplice, c.victim) and p.role in ("curator", "registrar")
    ]
    if pool:
        suspect = rng.choice(pool)
        world.red_herrings.append(
            {"person": suspect.id, "kind": "debt", "why": "owes a lender money and can open the galleries"}
        )
        world.relationships.append(Relationship(suspect.id, _by_role(world, "lender")[0].id, "lender"))
    if c.victim:
        world.red_herrings.append(
            {
                "person": c.victim,
                "kind": "borrowed_badge",
                "why": "their badge opened the gallery doors, but they were at the party",
            }
        )
    for _ in range(level.camera_blips):
        cam = rng.choice(sorted(world.venue.cameras))
        t = rng.choice([rng.randint(1150, 1300), rng.randint(1420, 1460)])
        world.camera_events.append(CameraEvent(t, cam, "offline", "maintenance"))
        world.camera_events.append(CameraEvent(t + rng.randint(2, 4), cam, "online", "maintenance"))


def _seating(world: World, rng: random.Random) -> None:
    diners = [p for p in world.people.values() if p.kind == "guest" or (p.kind == "staff" and p.role in HOSTS)]
    diners.sort(key=lambda p: p.id)
    rng.shuffle(diners)
    tables = max(2, len(diners) // 6)
    for i, p in enumerate(diners):
        world.seating[p.id] = i % tables + 1
    hosts = sorted(p.id for p in world.people.values() if p.role in ("director", "curator", "events_manager"))
    for g in sorted(p.id for p in world.people.values() if p.kind == "guest"):
        world.invited_by[g] = rng.choice(hosts)


# ── Money and phones ──────────────────────────────────────────────────────────

DAY = 1440


def _money(world: World, level: Level, rng: random.Random) -> None:
    c = world.crime
    assert c is not None
    p = world.people
    acc = {k: v.account or "" for k, v in p.items()}

    def pay(src: str, dst: str, days_before: float, amount: int, memo: str) -> None:
        t = -int(days_before * DAY) + rng.randint(480, 1200)
        world.transfers.append(Transfer(t, acc[src], acc[dst], amount, memo))

    for rel in world.relationships:
        if rel.kind in ("sibling", "spouse", "friend"):
            for _ in range(rng.randint(1, 2)):
                memo = rng.choice(
                    ["dinner", "birthday present", "concert tickets", "train tickets", "thanks!", "half the taxi"]
                )
                a, b = (rel.a, rel.b) if rng.random() < 0.5 else (rel.b, rel.a)
                pay(a, b, rng.uniform(1, 30), rng.randint(15, 180), memo)

    lender = _by_role(world, "lender")[0].id
    for rel in world.relationships:
        if rel.kind == "lender":
            pay(lender, rel.a, rng.uniform(25, 30), rng.choice([3000, 4500, 6000, 8000]), "loan")
            for i in range(rng.randint(1, 2)):
                pay(rel.a, lender, 20 - i * 9, rng.choice([150, 200, 250]), f"repayment {i + 1}/12")

    shells = sorted(a for a in world.shells)
    shell_owner = {a: pid for pid, person in p.items() for a in [person.account] if a in world.shells}
    fence = c.fence
    advance = rng.choice([12000, 15000, 18000, 24000])
    s1, s2 = shell_owner[shells[0]], shell_owner[shells[1]]
    pay(fence, s1, 21, advance, "advisory retainer")
    pay(s1, c.culprit, 19, advance - 2000, "consulting fee, invoice 0412")
    pay(c.culprit, c.accomplice, 6, rng.choice([2500, 3000, 3500]), "freelance work")
    if level.ring_cycle:
        pay(c.culprit, s2, 12, rng.choice([1500, 2000]), "loan repayment")
        pay(s2, fence, 10, rng.choice([1400, 1900]), "transfer")

    if level.innocent_cycle:
        mates = rng.sample(
            sorted(x.id for x in p.values() if x.kind in ("staff", "guest") and x.id not in (c.culprit, c.accomplice)),
            3,
        )
        for i in range(3):
            world.relationships.append(Relationship(mates[i], mates[(i + 1) % 3], "flatmate"))
            pay(mates[i], mates[(i + 1) % 3], 3 + i, rng.choice([420, 450, 480]), "rent share")


def _calls(world: World, rng: random.Random) -> None:
    c = world.crime
    assert c is not None
    p = world.people
    ph = {k: v.phone or "" for k, v in p.items()}

    def call(a: str, b: str, t: int, lo: int, hi: int) -> None:
        world.calls.append(Call(t, ph[a], ph[b], rng.randint(lo, hi)))

    for rel in world.relationships:
        if rel.kind == "friend" and rng.random() < 0.5:
            continue  # some friends settle up by bank transfer and never call
        if rel.kind in ("sibling", "spouse", "friend", "flatmate"):
            for _ in range(rng.randint(1, 3)):
                a, b = (rel.a, rel.b) if rng.random() < 0.5 else (rel.b, rel.a)
                call(a, b, -rng.randint(1, 20) * DAY + rng.randint(500, 1300), 20, 600)
    relatives = _by_role(world, "relative")
    guests = sorted(x.id for x in p.values() if x.kind == "guest")
    for rel in relatives:
        # Someone outside the museum two guests both call: a shared relative, a babysitter.
        for g in rng.sample(guests, 2):
            world.relationships.append(Relationship(g, rel.id, "relative", "family at home"))
            call(g, rel.id, rng.randint(1250, 1400), 30, 240)
    for rel in world.relationships:
        if rel.kind == "lender":
            call(rel.b, rel.a, -rng.randint(2, 8) * DAY + rng.randint(600, 1100), 60, 300)
    # The ring talks before and on the night.
    for d in rng.sample(range(3, 20), 3):
        call(c.culprit, c.fence, -d * DAY + rng.randint(600, 1300), 60, 420)
    for d in rng.sample(range(2, 15), 2):
        call(c.accomplice, c.culprit, -d * DAY + rng.randint(600, 1300), 30, 300)
    call(c.culprit, c.accomplice, c.start - 9, 15, 45)
    call(c.accomplice, c.culprit, c.end + 5, 10, 40)
    call(c.culprit, c.fence, c.end + 16, 40, 120)
    # Night-time noise among staff.
    staff = sorted(x.id for x in p.values() if x.kind == "staff")
    for _ in range(4):
        a, b = rng.sample(staff, 2)
        call(a, b, rng.randint(1100, 1460), 10, 120)
