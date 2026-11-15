"""The simulator must produce nights that make sense, and the same night for the same seed."""

import filecmp
from collections import defaultdict

import pytest

from heist.case import CASES
from heist.world.packs import PACKS, build_case
from heist.world.simulate import LEVELS, simulate

METHODS = ("insider", "borrowed_badge", "fire_door")


def problems(w) -> list[str]:
    out = []
    v = w.venue
    stays = defaultdict(list)
    for s in w.stays:
        stays[s.person].append(s)
    for pid, ss in stays.items():
        ss.sort(key=lambda s: s.start)
        for a, b in zip(ss, ss[1:]):
            if a.end != b.start:
                out.append(f"{pid}: gap between {a} and {b}")
            if not any({a.room, b.room} == {d.a, d.b} for d in v.doors.values()):
                out.append(f"{pid}: walked from {a.room} to {b.room} without a door")

    def where(pid, t):
        return next((s.room for s in stays[pid] if s.start <= t < s.end), None)

    for sw in w.swipes:
        door = v.doors[sw.door]
        if sw.granted:
            if where(sw.carried_by, sw.time) != sw.to_room:
                out.append(f"swipe {sw} but {sw.carried_by} is in {where(sw.carried_by, sw.time)}")
            if door.zone not in w.people[w.badge_holders[sw.badge]].zones:
                out.append(f"badge {sw.badge} opened {sw.door} without access")
        elif where(sw.carried_by, sw.time) != door.other(sw.to_room):
            out.append(f"denied swipe {sw} from the wrong side")
    c = w.crime
    for s in w.stays:
        if s.room == c.room and s.start < c.end and s.end > c.start and s.person != c.culprit:
            out.append(f"{s.person} was in the room during the theft")
    if not any(s.person == c.culprit and s.room == c.room and s.start <= c.start and s.end >= c.end for s in w.stays):
        out.append("the culprit wasn't in the room for the whole theft")
    if c.method == "borrowed_badge":
        if not any(sw.carried_by == c.culprit and w.badge_holders[sw.badge] == c.victim for sw in w.swipes):
            out.append("the borrowed badge was never used")
        if any(sw.carried_by == c.victim and 1120 < sw.time < 1440 for sw in w.swipes):
            out.append("the victim swiped while their badge was gone")
    offline = {(e.camera, e.status, e.time) for e in w.camera_events if e.cause == "tampering"}
    if not offline:
        out.append("no camera was tampered with")
    return out


@pytest.mark.parametrize("level", sorted(LEVELS))
@pytest.mark.parametrize("method", METHODS)
def test_nights_make_sense(level, method):
    for seed in range(1, 9):
        assert problems(simulate(seed, level, method)) == [], (level, method, seed)


def test_same_seed_same_night():
    a, b = simulate(42, "hard"), simulate(42, "hard")
    assert a.stays == b.stays and a.swipes == b.swipes and a.transfers == b.transfers


@pytest.mark.parametrize("pack", sorted(PACKS))
def test_shipped_packs_are_reproducible(pack, tmp_path):
    level, methods, first_seed, hidden = PACKS[pack]
    build_case(first_seed, level, tmp_path / "case-01", "case-01", pack, hide_truth=hidden, method=methods[0])
    shipped = CASES / pack / "case-01"
    cmp = filecmp.dircmp(shipped, tmp_path / "case-01")
    stack, diffs = [cmp], []
    while stack:
        d = stack.pop()
        diffs += d.diff_files + d.left_only + d.right_only
        stack += d.subdirs.values()
    assert diffs == [], (
        f"cases/{pack}/case-01 differs from a fresh build: {diffs}. Rebuild with `heist generate --pack {pack}`."
    )
