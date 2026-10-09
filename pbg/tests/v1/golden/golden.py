"""Golden documents of engine v1: the exact text the translator writes for a set of SED2 documents, backends and wrapper modes.

    golden/docs/NAME.sed2.json                          the SED2 documents (copies of the host's golden documents)
    golden/documents/NAME.BACKEND.WRAPPERS.pbg.composite.json     the process-bigraph document
    golden/documents/NAME.BACKEND.WRAPPERS.skip.txt     what the translator says when the wrappers or the backend cannot do it

`tests/v1/test_document.py` compares fresh output with these files.  After an intended change, read the differences and refresh:

    python tests/v1/golden/golden.py            # rewrite everything that changed
    python tests/v1/golden/golden.py --check    # exit 1 if anything is out of date (what the test does)

The input directory written into the documents is the fixed text `models`, so the files do not depend on the machine.
"""
from __future__ import annotations

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))

from pysed2translate_pbg import host  # noqa: E402
from pysed2translate_pbg.api import Options  # noqa: E402
from pysed2translate_pbg.engines import v1  # noqa: E402

DOCS = os.path.join(HERE, "docs")
OUT = os.path.join(HERE, "documents")
SKIP_HEADER = "# The translator skips this document (exit status 11):\n"
DYNAMIC = ("roadrunner", "copasi")


def document_names() -> list:
    return sorted(os.path.basename(p)[: -len(".sed2.json")] for p in glob.glob(os.path.join(DOCS, "*.sed2.json")))


def all_cases() -> list:
    """(name, backend, wrappers): every document for the dynamic simulators with the host runtime and with the wrappers; the flux
    balance analysis document for cobra."""
    out = []
    for name in document_names():
        for backend in (("cobra",) if name.startswith("fba") else DYNAMIC):
            for wrappers in ("off", "strict"):
                out.append((name, backend, wrappers))
    return out


def file_name(name, backend, wrappers, skipped) -> str:
    return f"{name}.{backend}.{wrappers}." + ("skip.txt" if skipped else "pbg.composite.json")


def render(name: str, backend: str, wrappers: str) -> tuple:
    path = os.path.join(DOCS, f"{name}.sed2.json")
    try:
        document = host.load_document(path)
        result = v1.translate(document, Options(backend={"*": backend}, prefix=name, source_name=name + ".sed2.json",
                                                input_dir="models", output_dir="results", engine={"wrappers": wrappers}))
        return file_name(name, backend, wrappers, False), next(iter(result.files.values()))
    except host.UnsupportedTaskError as e:
        return file_name(name, backend, wrappers, True), SKIP_HEADER + str(e) + "\n"


def read(fn: str):
    path = os.path.join(OUT, fn)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def stray_files() -> list:
    expected = set()
    for name, backend, wrappers in all_cases():
        expected.add(render(name, backend, wrappers)[0])
    return sorted(set(os.path.basename(p) for p in glob.glob(os.path.join(OUT, "*"))) - expected)


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    os.makedirs(OUT, exist_ok=True)
    stale = []
    for name, backend, wrappers in all_cases():
        fn, text = render(name, backend, wrappers)
        if read(fn) != text:
            stale.append(fn)
            if not check:
                with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
    strays = stray_files()
    for fn in strays:
        stale.append(fn + " (not produced any more)")
        if not check:
            os.remove(os.path.join(OUT, fn))
    print(("out of date: " if check else "rewrote: ") + (", ".join(stale) if stale else "nothing, all as recorded"))
    return 1 if (check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
