"""The project's milestones: where your code goes, where its checks live, where to read about it."""

from __future__ import annotations

from dataclasses import dataclass

SITE = "https://kube.ar"


@dataclass(frozen=True)
class Milestone:
    id: str
    course: str  # the course on the site this milestone closes a chapter of
    slug: str
    title: str
    module: str  # your code
    reference: str  # the reference solution, relative to the repo root
    checks: str  # the module with `run(module, lang)`

    @property
    def file(self) -> str:
        return "src/" + self.module.replace(".", "/") + ".py"

    def url(self, lang: str = "en") -> str:
        prefix = "" if lang == "en" else f"/{lang}"
        return f"{SITE}{prefix}/{self.course}/project/gallery-heist/{self.slug}"


MILESTONES = {
    m.id: m
    for m in [
        Milestone(
            id="1",
            course="graphrag",
            slug="timeline-board",
            title="The timeline board",
            module="heist.graphrag.m1_timeline_board",
            reference="reference/graphrag/m1_timeline_board.py",
            checks="heist.checks.m1",
        ),
    ]
}


def lesson_url(course: str, slug: str, lang: str = "en") -> str:
    prefix = "" if lang == "en" else f"/{lang}"
    return f"{SITE}{prefix}/{course}/{slug}"
