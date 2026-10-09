"""Golden scripts: the exact text the translator generates for a set of documents and backends.

    tests/golden/docs/NAME.sed2.json              the documents
    tests/golden/scripts/NAME.BACKEND.py           the script generated for a backend
    tests/golden/scripts/NAME.BACKEND.skip.txt     what the translator says when the backend cannot run the document

`tests/test_golden.py` compares fresh output with these files.  After an intended change to the generated code,
review the differences and refresh the files with

    python scripts/update_golden.py            # rewrite everything that changed
    python scripts/update_golden.py --check    # exit 1 if anything is out of date (what the test does)
"""
from __future__ import annotations

import glob
import os

from pysed2translate.backends import BACKENDS
from pysed2translate.errors import UnsupportedTaskError
from pysed2translate.translate import translate_file

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
SCRIPTS = os.path.join(HERE, "scripts")
SKIP_HEADER = "# The translator skips this document for this backend (exit status 11):\n"


def document_names() -> list:
    return sorted(os.path.basename(p)[: -len(".sed2.json")] for p in glob.glob(os.path.join(DOCS, "*.sed2.json")))


def all_cases() -> list:
    return [(name, backend) for name in document_names() for backend in BACKENDS]


def render(name: str, backend: str) -> tuple:
    """(file name, text) of the golden file for a document and backend."""
    path = os.path.join(DOCS, f"{name}.sed2.json")
    try:
        return f"{name}.{backend}.py", translate_file(path, backend)
    except UnsupportedTaskError as e:
        return f"{name}.{backend}.skip.txt", SKIP_HEADER + str(e) + "\n"


def read(file_name: str):
    path = os.path.join(SCRIPTS, file_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def stray_files() -> list:
    expected = set()
    for name, backend in all_cases():
        expected.add(f"{name}.{backend}.py")
        expected.add(f"{name}.{backend}.skip.txt")
    return sorted(f for f in (os.listdir(SCRIPTS) if os.path.isdir(SCRIPTS) else []) if f not in expected)


def out_of_date() -> list:
    """Golden files that are missing or differ, and files that should not be there: (kind, file name)."""
    problems = []
    for name, backend in all_cases():
        file_name, text = render(name, backend)
        other = file_name.replace(".py", ".skip.txt") if file_name.endswith(".py") else file_name.replace(".skip.txt", ".py")
        if read(file_name) != text:
            problems.append(("differs" if read(file_name) is not None else "missing", file_name))
        if read(other) is not None:
            problems.append(("stale", other))
    problems += [("stray", f) for f in stray_files() if all(f != p[1] for p in problems)]
    return problems


def update() -> list:
    """Rewrite the golden files; returns (kind, file name) for what changed."""
    os.makedirs(SCRIPTS, exist_ok=True)
    changed = []
    for kind, file_name in out_of_date():
        if kind in ("stale", "stray"):
            os.remove(os.path.join(SCRIPTS, file_name))
            changed.append((kind + " removed", file_name))
    for name, backend in all_cases():
        file_name, text = render(name, backend)
        if read(file_name) != text:
            with open(os.path.join(SCRIPTS, file_name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            changed.append(("written", file_name))
    return changed
