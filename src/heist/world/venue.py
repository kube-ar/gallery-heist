"""The museum: rooms, doors and cameras.

The layout is the same in every case (so a learner can get to know it), but gallery names,
which doors have card readers, and whether the fire door is propped open change per case.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

OUTSIDE = "R00"


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    wing: str  # outside | central | east | west | service
    public: bool


@dataclass(frozen=True)
class Door:
    id: str
    a: str
    b: str
    reader: bool
    zone: str | None  # access zone a badge needs, when the door has a reader
    kind: str = "door"  # door | archway | fire

    def other(self, room: str) -> str:
        return self.b if room == self.a else self.a


@dataclass(frozen=True)
class Camera:
    id: str
    room: str


EAST_GALLERIES = ["Map Room", "Portrait Gallery", "Silver Room", "Miniatures Room", "Tapestry Hall"]
WEST_GALLERIES = ["Sculpture Hall", "Print Room", "Textile Gallery", "Glass Room", "Lantern Gallery"]


@dataclass
class Venue:
    rooms: dict[str, Room]
    doors: dict[str, Door]
    cameras: dict[str, Camera]
    fire_door_propped: bool

    def wing(self, room: str) -> str:
        return self.rooms[room].wing

    def doors_of(self, room: str) -> list[Door]:
        return [d for d in self.doors.values() if room in (d.a, d.b)]

    def passable(self, door: Door, zones: frozenset[str]) -> bool:
        if door.kind == "fire":
            return self.fire_door_propped
        return not door.reader or (door.zone in zones)

    def route(self, start: str, goal: str, zones: frozenset[str], extra: frozenset[str] = frozenset()) -> list[Door]:
        """Shortest list of doors from start to goal, using only doors these zones open.

        `extra` holds door ids the walker may also use (a propped door it knows about, a
        borrowed badge's zones are passed in `zones` instead).
        """
        if start == goal:
            return []
        prev: dict[str, tuple[str, Door]] = {}
        seen = {start}
        queue = deque([start])
        while queue:
            room = queue.popleft()
            for door in sorted(self.doors_of(room), key=lambda d: d.id):
                if not (self.passable(door, zones) or door.id in extra):
                    continue
                nxt = door.other(room)
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = (room, door)
                if nxt == goal:
                    path: list[Door] = []
                    cur = goal
                    while cur != start:
                        cur, d = prev[cur]
                        path.append(d)
                    return list(reversed(path))
                queue.append(nxt)
        raise ValueError(f"no route from {start} to {goal} with zones {sorted(zones)}")


def build_venue(rng: random.Random, propped: bool) -> Venue:
    east = rng.sample(EAST_GALLERIES, 2)
    west = rng.sample(WEST_GALLERIES, 2)
    rooms = [
        Room(OUTSIDE, "Street", "outside", True),
        Room("R01", "Entrance Hall", "central", True),
        Room("R02", "Cloakroom", "central", True),
        Room("R03", "Grand Atrium", "central", True),
        Room("R04", "Dining Hall", "central", True),
        Room("R05", "Terrace", "central", True),
        Room("R10", "East Corridor", "east", False),
        Room("R11", east[0], "east", False),
        Room("R12", east[1], "east", False),
        Room("R13", "Restoration Lab", "east", False),
        Room("R20", "West Corridor", "west", False),
        Room("R21", west[0], "west", False),
        Room("R22", west[1], "west", False),
        Room("R23", "Archive", "west", False),
        Room("R30", "Service Corridor", "service", False),
        Room("R31", "Kitchen", "service", False),
        Room("R32", "Loading Dock", "service", False),
        Room("R33", "Storage Vault", "service", False),
        Room("R34", "Security Office", "service", False),
        Room("R35", "Staff Room", "service", False),
        Room("R36", "Offices", "service", False),
    ]
    doors = [
        Door("D01", OUTSIDE, "R01", False, None),  # main entrance, open for the gala
        Door("D02", OUTSIDE, "R32", True, "service"),  # staff entrance
        Door("D03", "R01", "R02", False, None),
        Door("D04", "R01", "R03", False, None),
        Door("D05", "R03", "R04", False, None),
        Door("D06", "R04", "R05", False, None),
        Door("D07", "R03", "R10", True, "east"),
        Door("D08", "R10", "R11", True, "east"),
        Door("D09", "R10", "R12", True, "east"),
        Door("D10", "R11", "R12", False, None, "archway"),
        Door("D11", "R10", "R13", True, "east"),
        Door("D12", "R13", "R32", False, None, "fire"),  # alarmed fire door, normally shut
        Door("D13", "R03", "R20", True, "west"),
        Door("D14", "R20", "R21", True, "west"),
        Door("D15", "R20", "R22", True, "west"),
        Door("D16", "R20", "R23", True, "west"),
        Door("D17", "R21", "R22", False, None, "archway"),
        Door("D18", "R04", "R31", False, None),
        Door("D19", "R31", "R30", False, None),
        Door("D20", "R30", "R32", True, "service"),
        Door("D21", "R30", "R33", True, "vault"),
        Door("D22", "R30", "R34", True, "security"),
        Door("D23", "R30", "R35", False, None),
        Door("D24", "R30", "R36", True, "offices"),
        Door("D25", "R30", "R10", True, "east"),
        Door("D26", "R30", "R20", True, "west"),
        Door("D27", "R03", "R30", True, "service"),
    ]
    cameras = [
        Camera("C01", "R01"),
        Camera("C02", "R10"),
        Camera("C03", "R11"),
        Camera("C04", "R12"),
        Camera("C05", "R20"),
        Camera("C06", "R21"),
        Camera("C07", "R22"),
        Camera("C08", "R32"),
        Camera("C09", "R33"),
    ]
    return Venue(
        rooms={r.id: r for r in rooms},
        doors={d.id: d for d in doors},
        cameras={c.id: c for c in cameras},
        fire_door_propped=propped,
    )
