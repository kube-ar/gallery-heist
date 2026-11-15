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
    checks: str  # the module with `run(module)`
    extra: tuple[str, ...] = ()  # files next to your module that the reference also replaces

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
        Milestone(
            id="2",
            course="graphrag",
            slug="case-ontology",
            title="The case ontology",
            module="heist.graphrag.m2_case_ontology",
            reference="reference/graphrag/m2_case_ontology.py",
            checks="heist.checks.m2",
            extra=("m2_heist.ttl", "m2_shapes.ttl"),
        ),
        Milestone(
            id="3",
            course="graphrag",
            slug="reading-the-statements",
            title="Reading the statements",
            module="heist.graphrag.m3_reading_statements",
            reference="reference/graphrag/m3_reading_statements.py",
            checks="heist.checks.m3",
        ),
        Milestone(
            id="4",
            course="graphrag",
            slug="ask-the-board",
            title="Ask the board",
            module="heist.graphrag.m4_ask_the_board",
            reference="reference/graphrag/m4_ask_the_board.py",
            checks="heist.checks.m4",
        ),
        Milestone(
            id="5",
            course="graphrag",
            slug="solve-rate",
            title="Solve rate",
            module="heist.graphrag.m5_solve_rate",
            reference="reference/graphrag/m5_solve_rate.py",
            checks="heist.checks.m5",
        ),
        Milestone(
            id="d1",
            course="agentic-graphrag",
            slug="the-rookie",
            title="The rookie",
            module="heist.agent.d1_the_rookie",
            reference="reference/agent/d1_the_rookie.py",
            checks="heist.checks.d1",
        ),
        Milestone(
            id="d2",
            course="agentic-graphrag",
            slug="the-rulebook",
            title="The rulebook",
            module="heist.agent.d2_the_rulebook",
            reference="reference/agent/d2_the_rulebook.py",
            checks="heist.checks.d2",
        ),
        Milestone(
            id="d3",
            course="agentic-graphrag",
            slug="the-notebook",
            title="The notebook",
            module="heist.agent.d3_the_notebook",
            reference="reference/agent/d3_the_notebook.py",
            checks="heist.checks.d3",
        ),
    ]
}


def lesson_url(course: str, slug: str, lang: str = "en") -> str:
    prefix = "" if lang == "en" else f"/{lang}"
    return f"{SITE}{prefix}/{course}/{slug}"
