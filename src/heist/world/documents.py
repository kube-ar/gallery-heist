"""Text the night left behind: witness statements, emails, an incident report, a press clipping,
and the front desk's handwritten sign-in sheet.

Everything is written from the simulated truth by templates, so every mention of a person and
every claim a sentence makes is known exactly (`Mention`, `Claim`). That's what lets the checks
score extraction and entity linking without guessing. A witness can be wrong about a time, and
the culprit and the accomplice lie about where they were: their false claims are marked.

Each part draws from its own random stream (`<seed>:signin`, `<seed>:docs`), so adding text
never changes the night itself.
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .simulate import ATRIUM, DINING, OUTSIDE, SECURITY, TERRACE, Person, World

PUBLIC = {"R01", "R02", ATRIUM, DINING, TERRACE}

ROLE_PHRASES = {
    "director": "the director",
    "curator": "one of the curators",
    "conservator": "the conservator",
    "registrar": "the registrar",
    "head_of_security": "the head of security",
    "guard": "one of the guards",
    "events_manager": "the events manager",
    "facilities_tech": "the facilities technician",
    "education_officer": "the education officer",
    "chef": "the chef",
    "waiter": "one of the waiters",
    "av_tech": "the sound technician",
    "cleaner": "the cleaner",
    "donor": "one of the donors",
    "collector": "a collector",
    "artist": "an artist",
    "board member": "a board member",
    "journalist": "a journalist",
}
RELATION_WORDS = {"sibling": "sibling", "spouse": "partner", "friend": "friend", "flatmate": "flatmate"}
NICKNAMES = {
    "Kasimir": "Kas",
    "Valentin": "Val",
    "Tobias": "Toby",
    "Matteo": "Teo",
    "Beatriz": "Bea",
    "Aurelio": "Aurel",
    "Gideon": "Gid",
    "Quentin": "Quin",
    "Saoirse": "Sersha",
    "Sigrid": "Siggi",
    "Ximena": "Xime",
    "Nadia": "Nadi",
    "Damian": "Dami",
    "Alexandra": "Alex",
    "Dmitri": "Dima",
    "Leila": "Lei",
    "Joaquín": "Quino",
    "Zainab": "Zee",
}
PREDICATES = ("arrived_at", "left_at", "was_in", "saw", "talked_to", "called", "knows", "worked_with",
              "money_trouble", "led_tour")  # fmt: skip


@dataclass
class Mention:
    start: int
    end: int
    text: str
    person: str | None  # truth id; None for someone in no list at all


@dataclass
class Claim:
    subject: str
    predicate: str
    object: str | None  # a room id, a person id, a relation word, or None
    time: int | None  # minutes after midnight on the gala day, as the text states it
    sentence: int
    true: bool  # agrees with what really happened


@dataclass
class Document:
    id: str
    kind: str  # statement | email | report | press
    title: str
    author: str | None
    author_as_written: str
    date: str
    text: str = ""
    mentions: list[Mention] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)

    def gold(self) -> dict:
        return {"mentions": [asdict(m) for m in self.mentions], "claims": [asdict(c) for c in self.claims]}


# ── Writing with offsets ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Ref:
    """A person slot in a template, with the exact words to write."""

    person: str | None
    words: str


class Writer:
    """Builds a document's text while remembering where every person is mentioned."""

    def __init__(self, doc: Document):
        self.doc = doc
        self.parts: list[str] = []
        self.size = 0
        self.sentence = 0

    def _add(self, s: str) -> None:
        self.parts.append(s)
        self.size += len(s)

    def say(self, template: str, claims: list[tuple] = (), **slots) -> None:
        """Write one sentence. `{name}` slots holding a Ref become mentions."""
        if self.parts and not self.parts[-1].endswith("\n"):
            self._add(" ")
        pos = 0
        for match in re.finditer(r"\{(\w+)\}", template):
            self._add(template[pos : match.start()])
            value = slots[match.group(1)]
            if isinstance(value, Ref):
                start = self.size
                self._add(value.words)
                self.doc.mentions.append(Mention(start, self.size, value.words, value.person))
            else:
                self._add(str(value))
            pos = match.end()
        self._add(template[pos:])
        for subject, predicate, obj, t, true in claims:
            self.doc.claims.append(Claim(subject, predicate, obj, t, self.sentence, true))
        self.sentence += 1

    def paragraph(self) -> None:
        if self.parts:
            self._add("\n\n")

    def done(self) -> None:
        self.doc.text = "".join(self.parts).rstrip() + "\n"


# ── Times and names, the way people say them ──────────────────────────────────

WORDS = ["twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]


def inside(name: str) -> str:
    """'in the Map Room', but 'on the Terrace'."""
    return f"on the {name}" if name == "Terrace" else f"in the {name}"


def clock(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def spoken(rng: random.Random, minutes: int) -> tuple[str, int]:
    """A time as a witness would say it, and the minute that phrase means."""
    style = rng.random()
    if style < 0.65:
        five = 5 * round(minutes / 5)
        h, m = (five // 60) % 24, five % 60
        if style < 0.3:
            return f"at {clock(five)}", five
        if style < 0.5:
            return f"around {clock(five)}", five
        return f"around {h % 12 or 12}:{m:02d}", five  # 12-hour, no am/pm: the evening is implied
    quarter = 15 * round(minutes / 15)
    h, m = (quarter // 60) % 24, quarter % 60
    hour, nxt = WORDS[h % 12], WORDS[(h + 1) % 12]
    if m == 0 and style > 0.85:
        return f"just after {hour}", quarter
    phrase = {0: f"at about {hour}", 15: f"at about a quarter past {hour}", 30: f"at about half past {hour}",
              45: f"at about a quarter to {nxt}"}[m]  # fmt: skip
    return phrase, quarter


def typo(rng: random.Random, word: str) -> str:
    if len(word) < 5:
        return word
    i = rng.randint(1, len(word) - 3)
    if rng.random() < 0.5:
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]  # two letters swapped
    return word[:i] + word[i + 1 :]  # a letter dropped


class Namer:
    """How one speaker refers to others in one document: fuller the first time, shorter later."""

    def __init__(self, world: World, speaker: str | None, rng: random.Random, close: set[str]):
        self.world, self.speaker, self.rng, self.close = world, speaker, rng, close
        self.seen: set[str] = set()

    def __call__(self, pid: str, describe: bool = True) -> Ref:
        p = self.world.people[pid]
        r = self.rng.random()
        if pid in self.seen:
            if pid in self.close or r < 0.5:
                return Ref(pid, p.first)
            return Ref(pid, p.last)
        self.seen.add(pid)
        if pid in self.close:
            if r < 0.15 and p.first in NICKNAMES:
                return Ref(pid, NICKNAMES[p.first])
            return Ref(pid, p.first if r < 0.6 else p.name)
        if describe and r < 0.3 and p.role in ROLE_PHRASES:
            return Ref(pid, ROLE_PHRASES[p.role])
        if r < 0.38:
            return Ref(pid, f"{p.first} {typo(self.rng, p.last)}")
        return Ref(pid, p.name)


# ── The sign-in sheet ─────────────────────────────────────────────────────────


@dataclass
class SignIn:
    time: int
    name: str
    phone: str
    visiting: str
    person: str | None  # truth: the guest who signed, None for a plus-one on no list


def phone_as_written(rng: random.Random, phone: str) -> str:
    digits = phone.replace("+44", "0").replace(" ", "")
    r = rng.random()
    if r < 0.3:
        return ""
    if r < 0.4:  # one digit misread
        i = rng.randint(6, len(digits) - 1)
        digits = digits[:i] + str((int(digits[i]) + rng.randint(1, 8)) % 10) + digits[i + 1 :]
    style = rng.random()
    if style < 0.4:
        return f"{digits[:5]} {digits[5:]}"
    if style < 0.7:
        return digits
    return "+44" + digits[1:]


def signin_sheet(world: World) -> tuple[list[SignIn], list[Person]]:
    rng = random.Random(f"{world.seed}:signin")
    firsts = [
        "Sam", "Robin", "Alex", "Jordan", "Kim", "Noa", "Ari", "Remy", "Sasha", "Jules", "Eli", "Toni",
    ]  # fmt: skip
    rows: list[SignIn] = []
    plus_ones: list[Person] = []
    arrivals = {}
    for s in world.stays:
        if s.room == "R01" and s.person not in arrivals and world.people[s.person].kind == "guest":
            arrivals[s.person] = s.start
    for pid, t in sorted(arrivals.items(), key=lambda x: x[1]):
        p = world.people[pid]
        host = world.people[world.invited_by[pid]]
        r = rng.random()
        if r < 0.35:
            name = p.name
        elif r < 0.55:
            name = f"{p.first[0]}. {p.last}"
        elif r < 0.7:
            name = f"{p.last}, {p.first}"
        elif r < 0.8:
            name = p.name.lower()
        elif r < 0.9:
            name = f"{p.first} {typo(rng, p.last)}"
        else:
            name = f"{NICKNAMES.get(p.first, p.first)} {p.last}"
        visiting = rng.choice([host.first, host.name, "gala", ""])
        rows.append(SignIn(t, name, phone_as_written(rng, p.phone or ""), visiting, pid))
        if rng.random() < 0.25:  # brought someone who isn't on any list
            guest = Person(
                id=f"X{len(plus_ones) + 1:02d}", first=rng.choice(firsts), last=rng.choice([p.last, typo(rng, p.last) + "e"]),
                kind="plus_one", role="plus_one",
            )  # fmt: skip
            plus_ones.append(guest)
            # Often written with the host's phone: same number, different person.
            same_phone = rng.random() < 0.5
            written = phone_as_written(rng, p.phone or "") if same_phone else ""
            rows.append(SignIn(t + 1, guest.name if rng.random() < 0.6 else f"{guest.first} (with {p.first})",
                               written, visiting, None))  # fmt: skip
    return rows, plus_ones


# ── Statements ────────────────────────────────────────────────────────────────


def _stays(world: World, pid: str) -> list[tuple[str, int, int]]:
    merged: list[list] = []
    for s in sorted((s for s in world.stays if s.person == pid), key=lambda s: s.start):
        if merged and merged[-1][0] == s.room:
            merged[-1][2] = s.end
        else:
            merged.append([s.room, s.start, s.end])
    return [(r, a, b) for r, a, b in merged]


def _together(world: World, pid: str, room: str, start: int, end: int) -> list[str]:
    """People in the same room for at least four minutes of [start, end)."""
    found = []
    for s in world.stays:
        if s.room == room and s.person != pid and min(end, s.end) - max(start, s.start) >= 4:
            found.append(s.person)
    return sorted(set(found))


def _relations(world: World, pid: str) -> dict[str, str]:
    out = {}
    for rel in world.relationships:
        if rel.kind in RELATION_WORDS and pid in (rel.a, rel.b):
            out[rel.b if rel.a == pid else rel.a] = rel.kind
    return out


def statement(world: World, pid: str, n: int, rng: random.Random) -> Document:
    c = world.crime
    assert c is not None
    p = world.people[pid]
    rooms = world.venue.rooms
    doc = Document(f"statement-{n:02d}", "statement", f"Statement of {p.name}", pid, p.name, world.date)
    w = Writer(doc)
    relations = _relations(world, pid)
    colleagues = {
        q.id for q in world.people.values() if q.kind == p.kind == "staff" or (p.company and q.company == p.company)
    }
    name = Namer(world, pid, rng, close=set(relations) | colleagues)
    stays = [s for s in _stays(world, pid) if s[0] != OUTSIDE]
    lie = pid in (c.culprit, c.accomplice)

    # 1. Arrival.
    first = stays[0]
    said, t = spoken(rng, first[1])
    if p.kind == "guest":
        partner = next((q for q, k in relations.items() if k == "spouse"), None)
        if partner and world.people[partner].kind == "guest":
            w.say("I arrived {t} with my partner {q}.", [(pid, "arrived_at", None, t, True)], t=said, q=name(partner))
        else:
            w.say("I arrived {t}.", [(pid, "arrived_at", None, t, True)], t=said)
    else:
        w.say("I started work {t}.", [(pid, "arrived_at", None, t, True)], t=said)
        if p.role == "curator" and any(r[0] in ("R11", "R12", "R21", "R22") and 1160 <= r[1] <= 1190 for r in stays):
            tour = next(r for r in stays if r[0] in ("R11", "R12", "R21", "R22") and 1160 <= r[1] <= 1190)
            said, t = spoken(rng, tour[1])
            w.say("{t} I took a few guests through the {room}.",
                  [(pid, "led_tour", None, t, True), (pid, "was_in", tour[0], t, True)],
                  t=said.capitalize(), room=rooms[tour[0]].name)  # fmt: skip
    w.paragraph()

    # 2. The evening, three to five moments, with who was there.
    window = (c.last_seen, c.discovered)
    evening = [s for s in stays if s[2] - s[1] >= 6 and 1150 <= s[1] < window[0] and s[0] != SECURITY]
    if p.role == "guard":
        evening = [s for s in stays if s[2] - s[1] >= 3 and 1150 <= s[1] < window[0]]
    for room, start, end in sorted(rng.sample(evening, min(len(evening), rng.randint(3, 5))), key=lambda s: s[1]):
        said, t = spoken(rng, start)
        verb = rng.choice(["{t} I was {room}.", "{t} I went {room}."])
        where = inside(rooms[room].name)
        if "went" in verb:
            where = where.replace("in the", "to the").replace("on the", "out to the")
        w.say(verb, [(pid, "was_in", room, t, True)], t=said.capitalize(), room=where)  # fmt: skip
        others = [q for q in _together(world, pid, room, start, end) if world.people[q].kind != "plus_one"]
        if others and rng.random() < 0.8:
            q = rng.choice(others)
            seen_at = max(start, next(s.start for s in world.stays if s.person == q and s.room == room
                                      and min(end, s.end) - max(start, s.start) >= 4))  # fmt: skip
            said, t = spoken(rng, seen_at)
            verb = "talked to" if (room in PUBLIC and world.people[q].kind != "contractor") else "saw"
            pred = "talked_to" if verb == "talked to" else "saw"
            w.say("I " + verb + " {q} there.", [(pid, pred, q, t, True)], q=name(q))
    w.paragraph()

    # 3. The window that matters: the truth for most, a lie for the two who did it.
    during = [s for s in stays if s[1] < window[1] and s[2] > window[0] and s[2] - s[1] >= 3]
    if lie:
        cover = rng.choice([ATRIUM, DINING, TERRACE]) if pid == c.culprit else rng.choice(["R20", "R10"])
        if pid == c.accomplice and cover == ("R10" if c.room in ("R11", "R12", "R13") else "R20"):
            cover = "R20" if cover == "R10" else "R10"
        said, t = spoken(rng, c.start - rng.randint(0, 6))
        if pid == c.accomplice:
            w.say("{t} I was on my round {room}.", [(pid, "was_in", cover, t, False)],
                  t=said.capitalize(), room=inside(rooms[cover].name))  # fmt: skip
        else:
            w.say("{t} I was {room} the whole time.", [(pid, "was_in", cover, t, False)],
                  t=said.capitalize(), room=inside(rooms[cover].name))  # fmt: skip
        w.say("I didn't go anywhere near the galleries.")
    elif during:
        room, start, end = max(during, key=lambda s: min(s[2], window[1]) - max(s[1], window[0]))
        said, t = spoken(rng, max(start, window[0]))
        w.say("{t} I was {room}.", [(pid, "was_in", room, t, True)],
              t=said.capitalize(), room=inside(rooms[room].name))  # fmt: skip
        others = _together(world, pid, room, max(start, window[0]), min(end, window[1]))
        if others:
            q = rng.choice(others)
            w.say("{q} was there too.", [(pid, "saw", q, t, True)], q=name(q))
    # Calls on the night.
    phones = {v.phone: k for k, v in world.people.items() if v.kind != "shell"}
    calls = [x for x in world.calls if x.time > 1080 and (phones.get(x.caller) == pid or phones.get(x.callee) == pid)]
    for call in calls[:2]:
        other = phones.get(call.callee if phones.get(call.caller) == pid else call.caller)
        if other is None or world.people[other].kind in ("shell", "external"):
            continue
        ring_call = {pid, other} == {c.culprit, c.accomplice}
        if ring_call and lie:
            continue  # they don't mention calling each other
        said, t = spoken(rng, call.time)
        if phones.get(call.caller) == pid:
            w.say("I called {q} {t}.", [(pid, "called", other, t, True)], q=name(other), t=said)
        else:
            w.say("{q} called me {t}.", [(other, "called", pid, t, True)], q=name(other), t=said)
    w.paragraph()

    # 4. What they know about people.
    for q, kind in sorted(relations.items())[:2]:
        if world.people[q].kind in ("external", "plus_one"):
            continue
        word = RELATION_WORDS[kind]
        w.say("{q} is my " + word + ".", [(pid, "knows", q, None, True)], q=name(q, describe=False))
    gossip = [h for h in world.red_herrings if h["kind"] == "debt" and h["person"] != pid]
    if gossip and p.kind == "staff" and rng.random() < 0.5:
        s = gossip[0]["person"]
        w.say("{q} told me money had been tight lately.", [(s, "money_trouble", None, None, True)], q=name(s))
    w.paragraph()
    w.say(rng.choice(["I didn't notice anything unusual.", "The music was loud and the rooms were full.",
                      "I only heard about the painting when the guards closed the doors."]))  # fmt: skip
    w.done()
    return doc


def _witnesses(world: World, rng: random.Random, count: int) -> list[str]:
    c = world.crime
    assert c is not None
    must = [c.culprit, c.accomplice, c.discovered_by]
    if c.victim:
        must.append(c.victim)
    must += [h["person"] for h in world.red_herrings if h["kind"] == "debt"]
    pool = sorted(
        p.id
        for p in world.people.values()
        if p.kind in ("guest", "staff", "contractor") and p.id not in must and p.role != "head_of_security"
    )
    chosen = list(dict.fromkeys(must)) + rng.sample(pool, max(0, count - len(set(must))))
    rng.shuffle(chosen)
    return chosen


# ── The other documents ───────────────────────────────────────────────────────


def schedule_email(world: World, rng: random.Random) -> Document:
    sender = next(p for p in world.people.values() if p.role == "events_manager")
    doc = Document("email-01", "email", "Gala night: running order", sender.id, sender.name, world.date)
    w = Writer(doc)
    name = Namer(world, sender.id, rng, close={p.id for p in world.people.values() if p.kind == "staff"})
    curators = sorted(p.id for p in world.people.values() if p.role == "curator")
    w.say("Hi all, here is the running order for tonight.")
    w.paragraph()
    w.say("Guests arrive from 19:00 and the reception is in the Grand Atrium.")
    w.say("Dinner is served at 20:00 in the Dining Hall, and the speeches start at 21:30.")
    w.say("Before dinner, {a} and {b} will take small groups through the galleries.",
          [(curators[0], "led_tour", None, None, True), (curators[1], "led_tour", None, None, True)],
          a=name(curators[0], describe=False), b=name(curators[1], describe=False))  # fmt: skip
    w.say("Guests on a tour walk in with the curator, so they won't need a badge.")
    w.paragraph()
    w.say("Thanks, {me}", me=Ref(sender.id, sender.first))
    w.done()
    return doc


def fire_door_email(world: World, rng: random.Random) -> Document:
    sender = next(p for p in world.people.values() if p.role == "facilities_tech")
    head = next(p for p in world.people.values() if p.role == "head_of_security")
    doc = Document("email-02", "email", "Restoration Lab fire door", sender.id, sender.name, world.date)
    w = Writer(doc)
    w.say("{h}, the alarm on the fire door between the Restoration Lab and the Loading Dock is faulty again.",
          h=Ref(head.id, head.first))  # fmt: skip
    w.say("The part arrives next week.")
    w.say("Until then the door can be opened without the alarm going off, so please ask the guards to check it.")
    w.paragraph()
    w.say("{me}", me=Ref(sender.id, sender.name))
    w.done()
    return doc


def advance_email(world: World, rng: random.Random) -> Document | None:
    debt = [h["person"] for h in world.red_herrings if h["kind"] == "debt"]
    if not debt:
        return None
    s = world.people[debt[0]]
    director = next(p for p in world.people.values() if p.role == "director")
    doc = Document("email-03", "email", "A small request", s.id, s.name, world.date)
    w = Writer(doc)
    w.say("Dear {d}, I'm sorry to ask, but could I have an advance on next month's salary?",
          [(s.id, "money_trouble", None, None, True)], d=Ref(director.id, director.first))  # fmt: skip
    w.say("Something came up at home and I need to settle a loan.")
    w.paragraph()
    w.say("Best, {me}", me=Ref(s.id, s.first))
    w.done()
    return doc


def incident_report(world: World, rng: random.Random) -> Document:
    c = world.crime
    assert c is not None
    head = next(p for p in world.people.values() if p.role == "head_of_security")
    finder = world.people[c.discovered_by]
    room = world.venue.rooms[c.room].name
    doc = Document("report-01", "report", "Incident report", head.id, head.name, world.date)
    w = Writer(doc)
    name = Namer(world, head.id, rng, close=set())
    w.say("At {t} {f} found the frame {room} empty during a round.",
          [(finder.id, "was_in", c.room, c.discovered, True)], t=clock(c.discovered), f=name(finder.id, describe=False),
          room=inside(room))  # fmt: skip
    w.say("The painting was in place on the round that ended at {t}.", t=clock(c.last_seen))
    off = sorted(
        {e.camera for e in world.camera_events if e.status == "offline" and c.last_seen <= e.time <= c.discovered}
    )
    if off:
        w.say("The camera log shows " + ", ".join(off) + " offline for some minutes between those times.")
    w.say("No alarm went off.")
    w.say("The doors were closed and statements were taken from the people still in the building.")
    w.done()
    return doc


def press_clipping(world: World, rng: random.Random) -> Document:
    c = world.crime
    assert c is not None
    director = next(p for p in world.people.values() if p.role == "director")
    doc = Document("press-01", "press", f"Painting stolen during gala at {world.venue_name}", None, "City Courier",
                   world.date)  # fmt: skip
    w = Writer(doc)
    day = date.fromisoformat(world.date).strftime("%A")
    w.say(f"A painting, {c.artwork} by {c.artist}, was taken from {world.venue_name} during its gala on {day} night.")
    w.say("Staff noticed it was missing shortly before midnight.")
    w.say("{d}, the museum's director, said the museum was \"shocked\" and was working with the police.",
          d=Ref(director.id, f"{director.name}"))  # fmt: skip
    guests = sum(p.kind == "guest" for p in world.people.values())
    w.say(f"About {5 * round(guests / 5) or guests} guests attended the dinner.")
    w.done()
    return doc


STATEMENTS = {"practice": 5, "easy": 6, "medium": 8, "hard": 10, "final": 10}


def documents(world: World) -> list[Document]:
    rng = random.Random(f"{world.seed}:docs")
    docs = [incident_report(world, rng), schedule_email(world, rng), fire_door_email(world, rng)]
    extra = advance_email(world, rng)
    if extra:
        docs.append(extra)
    docs.append(press_clipping(world, rng))
    for i, pid in enumerate(_witnesses(world, rng, STATEMENTS[world.level]), start=1):
        docs.append(statement(world, pid, i, rng))
    return docs
