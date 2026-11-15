"""Milestone 5 · Solve rate: a reference solution. Spoilers: `heist use-reference 5` copies it.

The solver reasons over the graph with plain code, no LLM: the cameras that went dark mark the
theft window; whoever sat in the Security Office then is the accomplice candidate; whoever they
phoned around the window is the thief; the badge that opened the room (if any) tells how.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from heist.case import Case

SECURITY_OFFICE = "R34"


def _intervals(case: Case) -> dict[str, list[tuple[str, datetime, datetime | None]]]:
    out: dict[str, list] = {}
    by_badge: dict[str, list] = {}
    for s in sorted(case.swipes, key=lambda s: s.time):
        if s.granted:
            by_badge.setdefault(s.badge_id, []).append(s)
    for badge, rows in by_badge.items():
        out[badge] = [(s.to_room, s.time, n.time if n else None) for s, n in zip(rows, [*rows[1:], None])]
    return out


def solve(case: Case) -> dict:
    room = case.meta["room"]["id"]
    wing = case.meta["room"]["wing"]
    last_seen, discovered = case.at(case.meta["last_seen"][11:]), case.at(case.meta["discovered"][11:])
    rooms_in = {r.room_id for r in case.rooms if r.wing == wing}
    watched = {c.camera_id for c in case.cameras if c.room_id in rooms_in | {"R32"}}
    holder = {b.badge_id: b.holder_id for b in case.badges}
    phone_of = {s.phone: s.employee_id for s in case.staff} | {g.phone: g.guest_id for g in case.guests}
    phone_of |= {w.phone: w.contractor_id for w in case.contractors}
    evidence = []

    # 1. The window: cameras watching the wing (or the loading dock) that went dark in between.
    dark = [
        e
        for e in case.camera_log
        if e.status == "offline" and e.camera_id in watched and last_seen <= e.time <= discovered
    ]
    if dark:
        start = min(e.time for e in dark)
        back = [e.time for e in case.camera_log if e.status == "online" and e.camera_id in {d.camera_id for d in dark}
                and e.time > start]  # fmt: skip
        end = max(back) if back else discovered
        evidence.append(f"cameras {sorted({e.camera_id for e in dark})} dark from {start:%H:%M} to {end:%H:%M}")
    else:
        start, end = last_seen, discovered

    # 2. Who sat in the Security Office when they went dark.
    spans = _intervals(case)
    in_office = sorted({holder[b] for b, rows in spans.items() for r, a, z in rows
                        if r == SECURITY_OFFICE and a <= start and (z is None or z > start)})  # fmt: skip

    # 3. Who phoned whom around the window.
    lo, hi = start - timedelta(minutes=20), end + timedelta(minutes=15)
    talks: dict[tuple[str, str], int] = {}
    for c in case.calls:
        if lo <= c.start <= hi:
            a, b = phone_of.get(c.caller), phone_of.get(c.callee)
            if a and b:
                key = tuple(sorted((a, b)))
                talks[key] = talks.get(key, 0) + 1
    pairs = sorted(((n, pair) for pair, n in talks.items() if set(pair) & set(in_office)), reverse=True)
    accomplice = culprit = None
    if pairs:
        _, pair = pairs[0]
        accomplice = next(p for p in pair if p in in_office)
        culprit = next(p for p in pair if p != accomplice)
        evidence.append(f"{accomplice} was in the Security Office and phoned {culprit} around the window")

    # 4. How: did a badge open the room during the window, and whose?
    opened = [s for s in case.swipes if s.granted and s.to_room == room and start <= s.time <= end]
    if opened:
        badge_holder = holder[opened[0].badge_id]
        evidence.append(f"badge {opened[0].badge_id} ({badge_holder}) opened the room at {opened[0].time:%H:%M}")
        if culprit is None:
            culprit = badge_holder
        method = "insider" if badge_holder == culprit else "borrowed_badge"
    else:
        method = "fire_door"
        evidence.append("no badge opened the room: someone came in through a door that logs nothing")
    return {"culprit": culprit, "accomplice": accomplice, "method": method, "evidence": evidence}


# ── Measuring ─────────────────────────────────────────────────────────────────


def triple_scores(predicted: list[tuple], gold: list[tuple]) -> dict[str, float]:
    p, g = set(map(tuple, predicted)), set(map(tuple, gold))
    tp = len(p & g)
    precision = tp / len(p) if p else 0.0
    recall = tp / len(g) if g else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


LAYERS = ("graph", "retrieval", "answer")


def bottom_up(scores: dict[str, float], bars: dict[str, float]) -> str | None:
    for layer in LAYERS:
        if scores[layer] < bars[layer]:
            return layer
    return None


def pairwise(question: str, a: str, b: str, judge: Callable[[str, str, str], str]) -> str:
    """Ask twice with the order swapped, at equal length; a winner only if both orders agree."""
    n = min(len(a), len(b))
    a_, b_ = a[:n], b[:n]
    first = judge(question, a_, b_)  # "first" or "second"
    second = judge(question, b_, a_)
    if first == "first" and second == "second":
        return "a"
    if first == "second" and second == "first":
        return "b"
    return "tie"


def _fingerprint(case: Case) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in case.path.rglob("*") if p.is_file() and p.name != "truth.json"):
        h.update(path.relative_to(case.path).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def manifest(case: Case, **config: Any) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        commit = None
    return {
        "case": case.id,
        "case_fingerprint": _fingerprint(case),
        "code": commit,
        "model": os.environ.get("HEIST_LLM_MODEL") or None,
        "provider": os.environ.get("HEIST_LLM_PROVIDER") or None,
        "config": dict(sorted(config.items())),
        "created": datetime.now().isoformat(timespec="seconds"),
    }


def diff(a: dict, b: dict) -> dict:
    flat_a = {**{k: v for k, v in a.items() if k not in ("config", "created")}, **a.get("config", {})}
    flat_b = {**{k: v for k, v in b.items() if k not in ("config", "created")}, **b.get("config", {})}
    return {
        k: (flat_a.get(k), flat_b.get(k)) for k in sorted(set(flat_a) | set(flat_b)) if flat_a.get(k) != flat_b.get(k)
    }
