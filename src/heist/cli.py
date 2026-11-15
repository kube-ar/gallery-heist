"""`heist`: run checks, look at cases, generate new ones.

heist cases                 list the case packs
heist show practice/case-01 print a case's briefing
heist check 1               run milestone 1's checks on your code
heist check 1 --reference   ...on the reference solution, to see what passing looks like
heist use-reference 1       replace your file with the reference (yours is kept as .mine.py)
heist use-reference 1 --undo
heist generate --seed 7 --level hard   a brand-new case in cases/mine/
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
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
    m = _milestone(args.milestone)
    if args.reference:
        path = ROOT / m.reference
        spec = importlib.util.spec_from_file_location(f"reference_{m.id}", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(m.module)
    checks = importlib.import_module(m.checks)
    from .checks.core import report

    print(f"Running milestone {m.id} on {'the reference solution' if args.reference else m.file}…")
    ok = report(m, checks.run(module), args.lang)
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


def cmd_llm(args) -> None:
    from .llm import LLMError, get_llm

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
        print(f"OK: {llm.usage.calls} calls, {llm.usage.input_tokens} tokens in, {llm.usage.output_tokens} out.")
    except LLMError as e:
        sys.exit(f"LLM setup problem: {e}")


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
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("use-reference", help="swap your file for the reference solution")
    p.add_argument("milestone")
    p.add_argument("--undo", action="store_true", help="put your own file back")
    p.set_defaults(fn=cmd_use_reference)

    p = sub.add_parser("llm", help="check your LLM provider setup (.env) with two tiny calls")
    p.set_defaults(fn=cmd_llm)

    p = sub.add_parser("generate", help="build a new case (or rebuild a shipped pack)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--level", default="medium", choices=["practice", "easy", "medium", "hard", "final"])
    p.add_argument("--method", choices=["insider", "borrowed_badge", "fire_door"])
    p.add_argument("--out", help="folder to write (default: cases/mine/case-<seed>)")
    p.add_argument("--pack", help="rebuild one of the shipped packs instead")
    p.set_defaults(fn=cmd_generate)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
