#!/usr/bin/env python3
"""Refresh the golden scripts in tests/golden/scripts from the documents in tests/golden/docs.

    python scripts/update_golden.py            # rewrite what changed, say which files
    python scripts/update_golden.py --check    # change nothing; exit 1 if anything is out of date

Run it after an intended change to the generated code, look at `git diff tests/golden`, and commit the result
with the change.  See tests/golden/golden.py.
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests", "golden"))

import golden  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if anything is out of date")
    args = ap.parse_args(argv)
    if args.check:
        problems = golden.out_of_date()
        for kind, name in problems:
            print(f"{kind}: {name}")
        print(f"{len(problems)} golden file(s) out of date" if problems else "golden files are up to date")
        return 1 if problems else 0
    changed = golden.update()
    for kind, name in changed:
        print(f"{kind}: {name}")
    print(f"{len(changed)} change(s)" if changed else "nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
