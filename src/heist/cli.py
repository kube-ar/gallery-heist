"""`heist`: run checks, look at cases, generate new ones.

heist cases                 list the case packs
heist show practice/case-01 print a case's briefing
heist check 1               run milestone 1's checks on your code
heist check 1 --reference   ...on the reference solution, to see what passing looks like
heist check d3 --no-llm     ...without the checks that call your model (they cost money)
heist use-reference 1       replace your file with the reference (yours is kept as .mine.py)
heist use-reference 1 --undo
heist llm                   check your model setup (.env): text, JSON and one tool call
heist generate --seed 7 --level hard   a brand-new case in cases/mine/
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path

from .case import CASES, ROOT, list_cases, load_case
from .milestones import MILESTONES


def _milestone(mid: str):
    if mid not in MILESTONES:
        sys.exit(f"No milestone {mid!r}. Available: {', '.join(MILESTONES)}")
    return MILESTONES[mid]


def cmd_cases(args) -> None:
    current = None
    for name in list_cases(args.pack):
        pack, case_id = name.split("/")
        if pack != current:
            print(f"\n{pack}")
            current = pack
        meta = load_case(name).meta
        print(f"  {case_id}  {meta['artwork']['title']}, {meta['room']['name']} ({meta['level']})")
    print()


def cmd_show(args) -> None:
    print(load_case(args.case).briefing)


def cmd_check(args) -> None:
    from . import llm

    m = _milestone(args.milestone)
    llm.NO_LLM = args.no_llm
    if args.reference:
        path = ROOT / m.reference
        spec = importlib.util.spec_from_file_location(f"reference_{m.id}", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses in the module look themselves up here
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(m.module)
    checks = importlib.import_module(m.checks)
    from .checks.core import report

    print(f"Running milestone {m.id} on {'the reference solution' if args.reference else m.file}…")
    try:
        results = checks.run(module)
    except llm.LLMError as e:  # your code called a model where no check expects one
        sys.exit(f"A model call failed during a check that doesn't need one: {e}")
    ok = report(m, results, args.lang)
    used = llm.SESSION
    if used.calls or used.cached:  # what the run cost, so you can see it before your provider's bill does
        print(f"LLM use: {used.calls} calls ({used.cached} answers from the cache), "
              f"{used.input_tokens:,} tokens in, {used.output_tokens:,} out")  # fmt: skip
    if args.no_llm:
        print("The checks that call your model were skipped (--no-llm).")
    sys.exit(0 if ok else 1)


def cmd_use_reference(args) -> None:
    m = _milestone(args.milestone)
    mine_dir, ref_dir = (ROOT / m.file).parent, (ROOT / m.reference).parent
    pairs = [(ROOT / m.file, ROOT / m.reference)] + [(mine_dir / f, ref_dir / f) for f in m.extra]

    def backup(path: Path) -> Path:
        return path.with_name(path.stem + ".mine" + path.suffix)

    if args.undo:
        if not backup(pairs[0][0]).exists():
            sys.exit(f"No backup at {backup(pairs[0][0]).relative_to(ROOT)}")
        for mine, _ in pairs:
            if backup(mine).exists():
                shutil.move(backup(mine), mine)
        print(f"Restored your files for milestone {m.id}")
        return
    if backup(pairs[0][0]).exists():
        sys.exit(f"{backup(pairs[0][0]).relative_to(ROOT)} already exists: run with --undo first, or remove it")
    for mine, ref in pairs:
        if mine.exists():
            shutil.copy(mine, backup(mine))
        shutil.copy(ref, mine)
    names = ", ".join(str(p.relative_to(ROOT)) for p, _ in pairs)
    print(f"Replaced {names} with the reference; yours are kept as *.mine.* (--undo puts them back).")


def cmd_generate(args) -> None:
    from .world.packs import PACKS, build_case, build_pack

    if args.pack:
        if args.pack not in PACKS:
            sys.exit(f"Unknown pack {args.pack!r}: {', '.join(PACKS)}")
        for folder in build_pack(args.pack):
            print(f"wrote {folder.relative_to(ROOT)}")
        return
    folder = Path(args.out) if args.out else CASES / "mine" / f"case-{args.seed}"
    build_case(args.seed, args.level, folder, folder.name, folder.parent.name, method=args.method)
    name = folder.relative_to(CASES).as_posix() if folder.is_relative_to(CASES) else str(folder)
    print(f"wrote {folder} · load it with load_case({name!r})")


ADD = {
    "name": "add",
    "description": "Adds two whole numbers.",
    "parameters": {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
        "additionalProperties": False,
    },
}


def _add(arguments: dict) -> dict:
    try:
        return {"sum": int(arguments["a"]) + int(arguments["b"])}
    except (KeyError, TypeError, ValueError):
        return {"error": "add takes two whole numbers, a and b"}


def cmd_llm(args) -> None:
    from .llm import Conversation, LLMError, get_llm

    os.environ["HEIST_LLM_CACHE"] = "0"  # a setup check has to reach the provider, not read last time's answers
    try:
        llm = get_llm()
        print(f"Provider {llm.provider.name}, model {llm.model}" + (f", effort {llm.effort}" if llm.effort else ""))
        print("text:", llm.text("Reply with the single word: ready").strip()[:80])
        answer = llm.json(
            "Is a fire door an archway? Answer in the JSON format given.",
            schema={
                "type": "object",
                "properties": {"answer": {"type": "boolean"}, "why": {"type": "string"}},
                "required": ["answer", "why"],
                "additionalProperties": False,
            },
        )
        print("json:", answer)
    except LLMError as e:
        sys.exit(f"LLM setup problem: {e}")
    # The agent milestones talk to the model through tool calls: try one round trip.
    no_tools = ("The model works for text and JSON (milestones 3 and 4), but the agent milestones (d1-d5, d8) "
                "need one that calls tools: pick another HEIST_LLM_MODEL.")  # fmt: skip
    try:
        convo = Conversation(llm, [ADD], system="You answer arithmetic with the add tool.")
        turn = convo.send("What is 17 + 25? Use the add tool, then reply with the number.")
        if turn.done:
            sys.exit(f"LLM setup problem: the model answered {turn.text.strip()[:60]!r} without calling the "
                     f"tool. {no_tools}")  # fmt: skip
        asked = ", ".join(f"{c.name}({c.arguments})" for c in turn.tool_calls)
        turn = convo.reply({c.id: _add(c.arguments) for c in turn.tool_calls})
        print(f"tools: called {asked}, then replied {turn.text.strip()[:60]!r}")
    except LLMError as e:
        sys.exit(f"LLM setup problem with a tool call: {e}\n{no_tools}")
    print(f"OK: {llm.usage.calls} calls, {llm.usage.input_tokens} tokens in, {llm.usage.output_tokens} out.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="heist", description="Gallery Heist: checks and cases.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cases", help="list the case packs")
    p.add_argument("pack", nargs="?")
    p.set_defaults(fn=cmd_cases)

    p = sub.add_parser("show", help="print a case's briefing")
    p.add_argument("case")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("check", help="run a milestone's checks")
    p.add_argument("milestone")
    p.add_argument("--reference", action="store_true", help="check the reference solution instead of your code")
    p.add_argument("--lang", default="en", choices=["en", "es"], help="language of the links to the lessons")
    p.add_argument("--no-llm", action="store_true", help="skip the checks that call your model (they cost money)")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("use-reference", help="swap your file for the reference solution")
    p.add_argument("milestone")
    p.add_argument("--undo", action="store_true", help="put your own file back")
    p.set_defaults(fn=cmd_use_reference)

    p = sub.add_parser("llm", help="check your LLM provider setup (.env): text, JSON and a tool call")
    p.set_defaults(fn=cmd_llm)

    p = sub.add_parser("generate", help="build a new case (or rebuild a shipped pack)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--level", default="medium", choices=["practice", "easy", "medium", "hard", "final"])
    p.add_argument("--method", choices=["insider", "borrowed_badge", "fire_door"])
    p.add_argument("--out", help="folder to write (default: cases/mine/case-<seed>)")
    p.add_argument("--pack", help="rebuild one of the shipped packs instead")
    p.set_defaults(fn=cmd_generate)

    args = parser.parse_args(argv)
    from . import llm

    llm._load_env()  # before anything runs: the model settings, and NEO4J_* for store(), come from .env
    args.fn(args)


if __name__ == "__main__":
    main()
