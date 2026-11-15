"""Builds the case packs shipped in `cases/`, and new ones on demand (`heist generate`)."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

from ..answers import links, shortest_hops
from ..case import CASES, load_case
from .export import export
from .simulate import simulate

# pack -> (level, how the thefts are done in order, first seed, answers hidden)
PACKS = {
    "practice": ("practice", ("insider",) * 3, 101, False),
    "easy": ("easy", ("insider",) * 4, 201, False),
    "medium": ("medium", ("borrowed_badge", "insider", "borrowed_badge", "insider"), 301, False),
    "hard": ("hard", ("fire_door", "borrowed_badge", "fire_door", "borrowed_badge"), 401, False),
    "final": ("final", ("borrowed_badge", "fire_door", "insider"), 901, True),
}


def build_case(
    seed: int, level: str, folder: Path, case_id: str, pack: str, hide_truth: bool = False, method: str | None = None
) -> None:
    if folder.exists():
        if not (folder / "case.json").exists() and any(folder.iterdir()):
            raise SystemExit(f"{folder} exists and isn't a case folder: pick an empty or new folder")
        shutil.rmtree(folder)
    world = simulate(seed, level, method)
    export(world, folder, case_id, pack, hide_truth=hide_truth)
    _add_questions(folder, seed)


def build_pack(pack: str, out: Path = CASES) -> list[Path]:
    level, methods, first_seed, hidden = PACKS[pack]
    folders = []
    for i, method in enumerate(methods):
        folder = out / pack / f"case-{i + 1:02d}"
        build_case(first_seed + i, level, folder, f"case-{i + 1:02d}", pack, hide_truth=hidden, method=method)
        folders.append(folder)
    return folders


def _add_questions(folder: Path, seed: int) -> None:
    """Questions for milestone 1, written into case.json so you can run them yourself."""
    rng = random.Random(f"{seed}:questions")
    case = load_case(folder)
    meta = case.meta
    wing = meta["room"]["wing"]
    other = "west" if wing == "east" else "east"
    slots = {"20:00": "20:30", "20:30": "21:00", "21:00": "21:30", "21:30": "22:00", "22:00": "22:30", "22:30": "23:00"}
    slot, back = rng.sample(sorted(slots), 2)
    questions: dict = {
        "who_was_in": [
            {"wing": wing, "start": meta["last_seen"][11:], "end": meta["discovered"][11:]},
            {"wing": other, "start": slot, "end": slots[slot]},
            # Backstage: people who badged in long before the window and never swiped again.
            {"wing": "service", "start": back, "end": slots[back]},
        ],
        "connection": [],
    }
    people = sorted(
        [s.employee_id for s in case.staff]
        + [g.guest_id for g in case.guests]
        + [w.contractor_id for w in case.contractors]
    )
    full = links(case)
    no_money, no_outside = links(case, transfers=False), links(case, outsiders=False)

    def worse(a: str, b: str, adj) -> bool:
        """Is the pair farther apart (or cut off) without these links?"""
        best, without = shortest_hops(case, a, b, full), shortest_hops(case, a, b, adj)
        return best is not None and best >= 2 and (without is None or without > best)

    # One pair that needs a money link, one that runs through someone outside the museum, one at random.
    wanted = [lambda a, b: worse(a, b, no_money), lambda a, b: worse(a, b, no_outside), lambda a, b: True]
    pairs = [(a, b) for a in people for b in people if a < b]
    rng.shuffle(pairs)
    wanted += [lambda a, b: True] * 2  # fill up to three if a special pair doesn't exist
    for test in wanted:
        if len(questions["connection"]) == 3:
            break
        for a, b in pairs:
            hops = shortest_hops(case, a, b, full)
            pair = {"a": a, "b": b}
            if hops and hops >= 2 and pair not in questions["connection"] and test(a, b):
                questions["connection"].append(pair)
                break
    meta["questions"] = questions
    (folder / "case.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
