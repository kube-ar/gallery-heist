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

| # | Milestone | Course chapter | Needs |
|---|---|---|---|
| 1 | [The timeline board](https://kube.ar/graphrag/project/gallery-heist/timeline-board): seven systems in one graph | GraphRAG · Why a graph | Python only |
| 2 | [The case ontology](https://kube.ar/graphrag/project/gallery-heist/case-ontology): RDF, shapes, open-world alibis, the sign-in sheet | GraphRAG · Designing the graph | Python only |
| 3 | [Reading the statements](https://kube.ar/graphrag/project/gallery-heist/reading-the-statements): a lexical graph, linked mentions, LLM-extracted claims checked against the log | GraphRAG · Building the graph | a model (one check) |
| 4 | [Ask the board](https://kube.ar/graphrag/project/gallery-heist/ask-the-board): Neo4j, four retrieval routes, global search | GraphRAG · Storing and querying | Neo4j, and a model (two checks) |
| 5 | [Solve rate](https://kube.ar/graphrag/project/gallery-heist/solve-rate): name the thief, then measure it like the evaluation lesson | GraphRAG · Measuring quality | Python only |

Then the detective (the [Agentic GraphRAG](https://kube.ar/agentic-graphrag) course): an agent
that doesn't get the files. It works the case at the precinct's desk (`heist.precinct`), where
every record, log and interview costs minutes from the night's budget, and asks the chief for a
warrant when it's sure. This part needs no GraphRAG code: you can start here. The planned agents (d4, d8) ask the evidence board, the
GraphRAG part's graph, through the desk's `board` tool; the desk loads it with the course's own
solutions, and it needs Neo4j.

| # | Milestone | Course chapter | Needs |
|---|---|---|---|
| d1 | [The rookie](https://kube.ar/agentic-graphrag/project/gallery-heist/the-rookie): a baseline agent, and its failures named | Agentic GraphRAG · Overview | a model (one check) |
| d2 | [The rulebook](https://kube.ar/agentic-graphrag/project/gallery-heist/the-rulebook): rules in the graph, one `describe` for every record, a distraction | What the agent knows | a model (one check) |
| d3 | [The notebook](https://kube.ar/agentic-graphrag/project/gallery-heist/the-notebook): a memory with two times, observed vs claimed | Agent memory | a model (one check) |
| d4 | [The investigation plan](https://kube.ar/agentic-graphrag/project/gallery-heist/the-investigation-plan): a workflow graph, phases, meaning checks | How the agent acts | Neo4j, and a model (one check) |
| d5 | [The precinct](https://kube.ar/agentic-graphrag/project/gallery-heist/the-precinct): 59 tools, retrieval, chaining by type, a planted instruction | Agent tools | a model (one check) |
| d6 | [Case review](https://kube.ar/agentic-graphrag/project/gallery-heist/case-review): execution graph, diagnosis, safe shipping | Evaluation and self-improvement | Python only |
| d7 | [Budget and clearance](https://kube.ar/agentic-graphrag/project/gallery-heist/budget-and-clearance): routing, cost per solved case, access, audit, erasure | Running in production | Python only |
| d8 | [The hard case](https://kube.ar/agentic-graphrag/project/gallery-heist/the-hard-case): your best detective on the hard pack, and an ablation | Putting it together | Neo4j, and a model (one check) |

"A model (one check)" means one check calls your model and the others are plain Python: you can
build and check those first, without a key (`--no-llm`, below).

## Setup

1. Click **Use this template** on GitHub to get your own copy, and clone it.
2. Install [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync
uv run heist cases                  # the case packs
uv run heist show practice/case-01  # a case's briefing
```

Python 3.12 or newer. Milestones 1, 2 and 5, d6 and d7 need nothing else. Milestone 4 needs
Neo4j (below). The fast paths embed text with a small model (`heist.vectors`, about 30 MB),
downloaded from Hugging Face the first time it's used, so that first run needs the network.

### A model, for milestones 3 and 4 and the agent milestones

Milestones 3 and 4 and the agent milestones d1 to d5 and d8 call a language model. Use whichever
provider you have a key for: Claude (`anthropic`), OpenAI, Fireworks or OpenRouter. The agent
milestones need a model that calls tools.

```sh
cp .env.example .env     # then set HEIST_LLM_PROVIDER, HEIST_LLM_MODEL and that provider's key
uv run heist llm         # checks the setup: a text answer, a JSON answer and one tool call
```

`.env` is gitignored: never commit a key. In your code, `from heist.llm import get_llm` gives
you `llm.text(prompt)` and `llm.json(prompt, schema)` on whichever provider `.env` names, so your
solution works for anyone who clones it with a different provider. For the agents,
`heist.llm.Conversation(llm, tools, system=...)` runs a tool-calling conversation on the same
provider (its docstring has the loop).

**What it costs.** The model check of an agent milestone runs whole investigations: dozens of
model calls each time you run it. A smaller model costs much less than the default (Claude's
Opus). After a `check` that called your model, a line says what it used (these numbers are
illustrative):

```text
LLM use: 64 calls (12 answers from the cache), 812,400 tokens in, 21,950 out
```

One-shot answers (`llm.text`, `llm.json`) are cached in `.heist-cache/llm`,
so asking the same prompt again is free; set `HEIST_LLM_CACHE=0` to always call the provider.
Conversations aren't cached: an agent check pays for its runs every time.

### Neo4j, for milestone 4 and the planned agents (d4, d8)

```sh
docker compose up -d     # starts Neo4j with the password in .env (default heist-password)
```

The browser is at http://localhost:7474 (user `neo4j`). `docker compose down` stops it.

## How a milestone works

1. Finish the chapter on the site and open its milestone page.
2. Write your code in the milestone's file, for example `src/heist/graphrag/m1_timeline_board.py`.
   The docstrings say exactly what each function must return.
3. Run the checks:

```sh
uv run heist check 1             # links to the lessons in English
uv run heist check 1 --lang es   # ...or in Spanish
uv run heist check d3 --no-llm   # ...without the checks that call your model
```

Each check says what's right, what isn't, and which lesson explains it. `--no-llm` marks the
model checks "not started" and says they were skipped: use it while you work on the plain
functions, and run the full check once they pass.

**Fast or deep.** Every milestone can be built two ways. The fast path uses a library
(networkx, a vector index, later Neo4j) and gets you to a working result in a few hours. The deep
path writes the same piece yourself. The checks are the same either way, so pick per milestone,
and come back to go deeper whenever you're curious.

**Each milestone starts from the case data.** No check uses your code from an earlier milestone,
so you can do them in any order. `uv run heist check 1 --reference` shows what passing looks like.
`uv run heist use-reference 1` swaps your file for the reference solution (yours is kept as
`.mine.py`; `--undo` puts it back): a working version of a milestone you skipped, to read or to
compare with.

## Troubleshooting

- **`store()` raised, "Couldn't connect to localhost:7687" or ServiceUnavailable** (milestone 4):
  Neo4j isn't running. Start Docker (Docker Desktop on macOS and Windows), then
  `docker compose up -d`, and wait until http://localhost:7474 answers: the first start can take
  half a minute.
- **Neo4j says the credentials are wrong**: `NEO4J_PASSWORD` in `.env` has to be the password
  Neo4j had when it first started, because its data volume keeps it. Put that one back, or start
  over with `docker compose down -v` (it deletes the stored case) and `docker compose up -d`.
- **The first run hangs or fails while loading the embedding model**: it's downloading
  `minishlab/potion-base-8M` (about 30 MB) from Hugging Face. Run it once with the network; after
  that it's read from Hugging Face's cache (`~/.cache/huggingface`).
- **`uv run heist llm` says the model didn't call the tool**, or the agent checks fail with a
  "tools" error from the API: that model doesn't support tool calling. Text and JSON still work for
  milestones 3 and 4; for the agent milestones, pick a model your provider lists with tool (function)
  calling.
- **An agent check costs more than you expected**: use `--no-llm` until the plain checks pass,
  and a smaller model for the runs.

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
