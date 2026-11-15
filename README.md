# Gallery Heist

A painting vanished during a museum gala. Every system in the building recorded part of the
night: the keycard readers, the cameras, the phone company, the bank, the events team. None of
them knows who did it, because none of them can see the others.

In this project you connect them. First as a **knowledge graph** that answers questions no single
system can (the [Knowledge Graphs & GraphRAG](https://kube.ar/graphrag) course). Later as an
**agent** that investigates a case on its own and names the thief, with evidence (the
[Agentic GraphRAG](https://kube.ar/agentic-graphrag) course).

Every case is generated from a seed by a simulation of the whole night, so the truth is always
known. That's what lets the checks score your work exactly.

## Milestones

Each milestone closes a chapter of a course on [kube.ar](https://kube.ar). The instructions live
on the site, next to the lessons they use. This repo holds the code, the cases and the checks.

| # | Milestone | Course chapter | Status |
|---|---|---|---|
| 1 | [The timeline board](https://kube.ar/graphrag/project/gallery-heist/timeline-board): seven systems in one graph | GraphRAG · Why a graph | ready |
| 2 | [The case ontology](https://kube.ar/graphrag/project/gallery-heist/case-ontology): RDF, shapes, open-world alibis, the sign-in sheet | GraphRAG · Designing the graph | ready |
| 3 | [Reading the statements](https://kube.ar/graphrag/project/gallery-heist/reading-the-statements): a lexical graph, linked mentions, LLM-extracted claims checked against the log | GraphRAG · Building the graph | ready (needs an LLM) |
| 4 | [Ask the board](https://kube.ar/graphrag/project/gallery-heist/ask-the-board): Neo4j, four retrieval routes, global search | GraphRAG · Storing and querying | ready (Neo4j; two checks need an LLM) |
| 5 | [Solve rate](https://kube.ar/graphrag/project/gallery-heist/solve-rate): name the thief, then measure it like the evaluation lesson | GraphRAG · Measuring quality | ready |

The detective agent (Agentic GraphRAG) follows once the board is complete.

## Setup

1. Click **Use this template** on GitHub to get your own copy, and clone it.
2. Install [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync
uv run heist cases                  # the case packs
uv run heist show practice/case-01  # a case's briefing
```

Python 3.12 or newer. Milestones 1 and 2 need no API key and no database; milestone 4 runs Neo4j
(`docker compose up -d`). The first run downloads a
small embedding model (about 30 MB), so it needs the network once.

### An LLM, from milestone 3 on

Milestones 3 and later call a language model. Use whichever provider you have a key for:
Claude (`anthropic`), OpenAI, Fireworks or OpenRouter.

```sh
cp .env.example .env     # then set HEIST_LLM_PROVIDER, HEIST_LLM_MODEL and that provider's key
uv run heist llm         # checks the setup with two tiny calls
```

`.env` is gitignored: never commit a key. In your code, `from heist.llm import get_llm` gives
you `llm.text(prompt)` and `llm.json(prompt, schema)` on whichever provider `.env` names, so your
solution works for anyone who clones it with a different provider.

## How a milestone works

1. Finish the chapter on the site and open its milestone page.
2. Write your code in the milestone's file, for example `src/heist/graphrag/m1_timeline_board.py`.
   The docstrings say exactly what each function must return.
3. Run the checks:

```sh
uv run heist check 1             # links to the lessons in English
uv run heist check 1 --lang es   # ...or in Spanish
```

Each check says what's right, what isn't, and which lesson explains it.

**Fast or deep.** Every milestone can be built two ways. The fast path uses a library
(networkx, a vector index, later Neo4j) and gets you to a working result in a few hours. The deep
path writes the same piece yourself. The checks are the same either way, so pick per milestone,
and come back to go deeper whenever you're curious.

**Stuck, or skipping ahead?** `uv run heist check 1 --reference` shows what passing looks like.
`uv run heist use-reference 1` swaps your file for the reference solution (yours is kept as
`.mine.py`; `--undo` puts it back), so the next milestone has something to build on.

## The cases

| Pack | Cases | What changes |
|---|---|---|
| `practice` | 3 | Small cast; the thief works inside the museum |
| `easy` | 4 | A few more people, the same kind of theft |
| `medium` | 4 | A bigger cast, money going around in loops, and in some cases a borrowed badge that makes the keycard log name the wrong person |
| `hard` | 4 | A fire door that logs nothing, and loops in the money that mean nothing at all |
| `final` | 3 | All of it, from a seed the code doesn't contain. The answers are hashed so you can't read them by accident (a hash stops accidents, not a determined cheat) |

Each case folder holds one export per system (`hr/`, `events/`, `vendors/`, `security/`,
`facilities/`, `telecom/`, `finance/`), the front desk's handwritten sign-in sheet (`frontdesk/`),
the statements, emails and reports written after the theft (`documents/`), a briefing (`case.md`)
and `case.json` with the questions the checks ask. `truth.json` is what really happened: the checks read it, you shouldn't.

Want more? `uv run heist generate --seed 7 --level hard` builds a new case in `cases/mine/`.

## License

Code: MIT. Case packs: CC BY 4.0. All people, places, companies and artworks are fictional.
