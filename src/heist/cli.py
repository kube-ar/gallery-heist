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
    mine, backup, ref = ROOT / m.file, ROOT / m.file.replace(".py", ".mine.py"), ROOT / m.reference
    if args.undo:
        if not backup.exists():
            sys.exit(f"No backup at {backup.relative_to(ROOT)}")
        shutil.move(backup, mine)
        print(f"Restored your {m.file}")
        return
    if backup.exists():
        sys.exit(f"{backup.relative_to(ROOT)} already exists: run with --undo first, or remove it")
    shutil.copy(mine, backup)
    shutil.copy(ref, mine)
    print(f"Your code is in {backup.relative_to(ROOT)}; {m.file} is now the reference solution.")


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
