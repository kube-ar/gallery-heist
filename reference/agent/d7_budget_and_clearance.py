"""Detective 7 · Budget and clearance: a reference solution. Spoilers: `heist use-reference d7`."""

from __future__ import annotations

from typing import Any

from heist.precinct import Precinct

RESTRICTED = {"junior": {"bank_records", "phone_records"}, "senior": set()}


def route_model(step: str, bars: dict[str, float], models: dict[str, tuple[float, float]]) -> str:
    bar = bars.get(step, 0.0)
    good = [(cost, -quality, name) for name, (quality, cost) in models.items() if quality >= bar]
    if good:
        return min(good)[2]
    return max(models, key=lambda n: models[n][0])


def cost_per_solved(runs: list[tuple[float, bool]]) -> float:
    solved = sum(1 for _, ok in runs if ok)
    return sum(c for c, _ in runs) / solved if solved else float("inf")


class _Restricted:
    def __init__(self, desk: Precinct, hidden: set[str]):
        self.desk, self.hidden = desk, hidden

    def tools(self) -> list[dict]:
        return [t for t in self.desk.tools() if t["name"] not in self.hidden]

    def call(self, name: str, arguments: dict | None = None) -> Any:
        if name in self.hidden:
            # Invisible, not "denied": the same answer as for a tool that doesn't exist.
            return self.desk._record(name, dict(arguments or {}), 0, False, {"error": f"no tool {name!r}"})
        return self.desk.call(name, arguments)


def restricted(desk: Precinct, role: str) -> _Restricted:
    return _Restricted(desk, RESTRICTED.get(role, set()))


def audit(desks: list[Precinct], person: str) -> list[tuple[str, int, str]]:
    out = []
    for desk in desks:
        for a in desk.log:
            if (
                a.ok
                and a.tool in ("phone_records", "bank_records", "interview")
                and a.arguments.get("person") == person
            ):
                out.append((desk.case.id, a.step, a.tool))
    return out


def erase(people: list[dict], person: str) -> list[dict]:
    return [{"id": p["id"], "kind": p["kind"]} if p["id"] == person else dict(p) for p in people]
