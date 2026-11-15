"""The official reading of a case's data: what the checks compare your answers with.

Spoiler warning: this file answers milestone 1's questions straight from the tables, with no
graph. Read it after you've built yours, if you want to compare.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime

from .case import Case


class Parties:
    """Maps any key you might return to one party.

    A party is a person in one of the museum's lists (staff, guests, contractors), named by
    their id there. Anyone else is named by their phone number. A badge belongs to its
    holder, a phone to whoever lists it, an account to whoever owns its contact phone.
    """

    def __init__(self, case: Case):
        self.by_key: dict[str, str] = {}
        self.names: dict[str, str] = {}
        for s in case.staff:
            self._add(s.employee_id, s.phone, s.full_name)
        for g in case.guests:
            last, _, first = g.name.partition(", ")
            self._add(g.guest_id, g.phone, f"{first} {last}")
        for w in case.contractors:
            self._add(w.contractor_id, w.phone, w.worker_name)
        for b in case.badges:
            self.by_key[b.badge_id] = b.holder_id
        phones = {c.caller for c in case.calls} | {c.callee for c in case.calls}
        phones |= {a.contact_phone for a in case.accounts}
        for p in phones:
            self.by_key.setdefault(p, p)
        for a in case.accounts:
            self.by_key[a.account_id] = self.by_key[a.contact_phone]
            self.names.setdefault(self.by_key[a.account_id], a.holder_name.title())

    def _add(self, native: str, phone: str, name: str) -> None:
        self.by_key[native] = native
        self.by_key[phone] = native
        self.names[native] = name

    def party(self, key: str) -> str | None:
        return self.by_key.get(str(key).strip())

    def label(self, party: str) -> str:
        name = self.names.get(party)
        return f"{party} ({name})" if name else party


def badge_intervals(case: Case) -> dict[str, list[tuple[str, datetime, datetime | None]]]:
    """Where each badge was, according to the keycard log alone.

    A badge is in the room it last swiped into (granted swipes only) until its next granted
    swipe. Before its first swipe, the log says nothing about it.
    """
    out: dict[str, list[tuple[str, datetime, datetime | None]]] = defaultdict(list)
    by_badge: dict[str, list] = defaultdict(list)
    for s in case.swipes:
        if s.granted:
            by_badge[s.badge_id].append(s)
    for badge, swipes in by_badge.items():
        swipes.sort(key=lambda s: s.time)
        for cur, nxt in zip(swipes, [*swipes[1:], None]):
            out[badge].append((cur.to_room, cur.time, nxt.time if nxt else None))
    return out


def in_wing(case: Case, wing: str, start: datetime, end: datetime) -> set[str]:
    """Parties whose badge was in a room of `wing` at some moment in [start, end)."""
    wings = {r.room_id: r.wing for r in case.rooms}
    parties = Parties(case)
    found = set()
    for badge, spans in badge_intervals(case).items():
        for room, since, until in spans:
            if wings[room] == wing and since < end and (until is None or until > start):
                found.add(parties.party(badge))
    return {p for p in found if p}


def links(case: Case, transfers: bool = True, outsiders: bool = True) -> dict[str, set[str]]:
    """Who is directly linked to whom.

    Two parties are linked when they called each other, sent each other money, sat at the
    same dinner table, one invited the other, or they work for the same company. Pass
    `transfers=False` or `outsiders=False` to leave out money links, or everyone known only by
    a phone number (the question generator uses this to pick pairs that need them).
    """
    parties = Parties(case)
    adj: dict[str, set[str]] = defaultdict(set)
    listed = {s.employee_id for s in case.staff} | {g.guest_id for g in case.guests}
    listed |= {w.contractor_id for w in case.contractors}

    def link(a: str | None, b: str | None) -> None:
        if not outsiders and (a not in listed or b not in listed):
            return
        if a and b and a != b:
            adj[a].add(b)
            adj[b].add(a)

    for c in case.calls:
        link(parties.party(c.caller), parties.party(c.callee))
    for t in case.transfers if transfers else []:
        link(parties.party(t.from_account), parties.party(t.to_account))
    tables: dict[int, list[str]] = defaultdict(list)
    for s in case.seating:
        tables[s.table].append(s.attendee_id)
    for members in tables.values():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                link(a, b)
    for g in case.guests:
        link(g.guest_id, g.invited_by)
    companies: dict[str, list[str]] = defaultdict(list)
    for w in case.contractors:
        companies[w.company].append(w.contractor_id)
    for members in companies.values():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                link(a, b)
    return adj


def shortest_hops(case: Case, a: str, b: str, adj: dict[str, set[str]] | None = None) -> int | None:
    """Fewest links between two parties, or None when nothing connects them."""
    adj = adj or links(case)
    parties = Parties(case)
    start, goal = parties.party(a), parties.party(b)
    if start is None or goal is None:
        return None
    seen, queue = {start: 0}, deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            return seen[cur]
        for nxt in sorted(adj[cur]):
            if nxt not in seen:
                seen[nxt] = seen[cur] + 1
                queue.append(nxt)
    return None


def canonical_loop(loop: list[str]) -> tuple[str, ...]:
    """The same loop written from its smallest account, so rotations compare equal."""
    i = loop.index(min(loop))
    return tuple(loop[i:] + loop[:i])


def money_loops(case: Case) -> set[tuple[str, ...]]:
    """Every directed loop in the account-to-account transfer graph (each account once)."""
    adj: dict[str, set[str]] = defaultdict(set)
    for t in case.transfers:
        if t.from_account != t.to_account:
            adj[t.from_account].add(t.to_account)
    loops: set[tuple[str, ...]] = set()
    nodes = sorted(set(adj) | {n for v in adj.values() for n in v})
    for s in nodes:
        # Only loops whose smallest account is `s`: each loop is found exactly once.
        stack = [(s, [s])]
        while stack:
            cur, path = stack.pop()
            for nxt in sorted(adj[cur]):
                if nxt == s:
                    loops.add(canonical_loop(path))
                elif nxt > s and nxt not in path:
                    stack.append((nxt, [*path, nxt]))
    return loops


def counts(case: Case) -> dict[str, int]:
    phones = {s.phone for s in case.staff} | {g.phone for g in case.guests} | {w.phone for w in case.contractors}
    phones |= {c.caller for c in case.calls} | {c.callee for c in case.calls} | {a.contact_phone for a in case.accounts}
    return {
        "people": len(case.staff) + len(case.guests) + len(case.contractors),
        "badges": len(case.badges),
        "rooms": len(case.rooms),
        "doors": len(case.doors),
        "phones": len(phones),
        "accounts": len(case.accounts),
        "swipes": len(case.swipes),
        "calls": len(case.calls),
        "transfers": len(case.transfers),
    }


# ── Milestone 2 ───────────────────────────────────────────────────────────────


def rooms_in_wing(case: Case, wing: str) -> set[str]:
    return {r.room_id for r in case.rooms if r.wing == wing}


def unguarded_ways_in(case: Case, wing: str) -> set[str]:
    """Doors from outside the wing into it that log nothing: no reader (archways, fire doors...)."""
    inside = rooms_in_wing(case, wing)
    return {d.door_id for d in case.doors if not d.has_reader and ((d.room_a in inside) != (d.room_b in inside))}


def swipes_at(case: Case, door_id: str, start: datetime, end: datetime) -> list[tuple[datetime, str, bool]]:
    return sorted(
        (s.time, s.badge_id, s.granted) for s in case.swipes if s.door_id == door_id and start <= s.time < end
    )


SOURCES = ("hr", "events", "vendors", "security", "telecom", "finance")


def sources_of(case: Case, person: str) -> set[str]:
    """Which systems hold a fact about this person (by their id, badge, phone or account)."""
    out = set()
    staff = {s.employee_id: s for s in case.staff}
    guests = {g.guest_id: g for g in case.guests}
    workers = {w.contractor_id: w for w in case.contractors}
    record = staff.get(person) or guests.get(person) or workers.get(person)
    if record is None:
        return out
    phone = record.phone
    if person in staff:
        out.add("hr")
    if (
        person in guests
        or any(g.invited_by == person for g in case.guests)
        or any(s.attendee_id == person for s in case.seating)
    ):
        out.add("events")
    if person in workers:
        out.add("vendors")
    if any(b.holder_id == person for b in case.badges):
        out.add("security")
    if any(phone in (c.caller, c.callee) for c in case.calls):
        out.add("telecom")
    if any(a.contact_phone == phone for a in case.accounts):
        out.add("finance")
    return out


def regions(case: Case) -> dict[str, frozenset[str]]:
    """Each room's region: every room you can walk to from it without passing a card reader.

    Archways and fire doors count as passable: a door that logs nothing can't prove nobody used it.
    """
    adj: dict[str, set[str]] = defaultdict(set)
    for d in case.doors:
        if not d.has_reader:
            adj[d.room_a].add(d.room_b)
            adj[d.room_b].add(d.room_a)
    out: dict[str, frozenset[str]] = {}
    for r in case.rooms:
        if r.room_id in out:
            continue
        seen, stack = {r.room_id}, [r.room_id]
        while stack:
            for nxt in adj[stack.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        region = frozenset(seen)
        for room in region:
            out[room] = region
    return out


def alibi(case: Case, person: str, wing: str, start: datetime, end: datetime) -> str:
    """'placed', 'elsewhere' or 'unknown', reading the keycard log under the open-world assumption.

    placed: their badge was in a room of the wing at some moment in [start, end).
    elsewhere: for the whole window their badge was somewhere the wing can't be reached from
      without swiping (assuming nobody walked in behind someone else).
    unknown: anything else: no badge, no swipe yet, or a way in that logs nothing.
    """
    badge = next((b.badge_id for b in case.badges if b.holder_id == person), None)
    if badge is None:
        return "unknown"
    inside = rooms_in_wing(case, wing)
    region = regions(case)
    spans = [s for s in badge_intervals(case).get(badge, []) if s[1] < end and (s[2] is None or s[2] > start)]
    if not spans or spans[0][1] > start:
        return "unknown"  # the window starts before the log knows where the badge is
    if any(room in inside for room, _, _ in spans):
        return "placed"
    if all(not (region[room] & inside) for room, _, _ in spans):
        return "elsewhere"
    return "unknown"


# ── Milestone 3 ───────────────────────────────────────────────────────────────


def contradicts(case: Case, person: str, room: str, at: datetime, slack_minutes: int = 10) -> bool:
    """Does the keycard log rule out that `person` was in `room` around `at`?

    Only if, for the whole span `at` ± `slack_minutes` (people round their times), their badge
    was somewhere `room` can't be reached from without a swipe. No badge, or a span the log knows
    nothing about, rules nothing out.
    """
    from datetime import timedelta

    badge = next((b.badge_id for b in case.badges if b.holder_id == person), None)
    if badge is None:
        return False
    start, end = at - timedelta(minutes=slack_minutes), at + timedelta(minutes=slack_minutes)
    spans = [s for s in badge_intervals(case).get(badge, []) if s[1] < end and (s[2] is None or s[2] > start)]
    if not spans or spans[0][1] > start:
        return False
    region = regions(case)
    return all(room not in region[r] for r, _, _ in spans)
