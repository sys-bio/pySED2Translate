"""Golden scripts: what the translator generates must not change by accident (see tests/golden/golden.py)."""
import difflib
import os
import sys

import pytest

pytest.importorskip("libsed2")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden"))

import golden  # noqa: E402

HINT = "If the change is intended, review it and run `python scripts/update_golden.py`."


@pytest.mark.parametrize("name, backend", golden.all_cases(), ids=lambda v: v)
def test_generated_script_matches_the_golden_file(name, backend):
    file_name, text = golden.render(name, backend)
    expected = golden.read(file_name)
    assert expected is not None, f"{file_name} does not exist. {HINT}"
    if expected != text:
        diff = "".join(list(difflib.unified_diff(expected.splitlines(True), text.splitlines(True),
                                                 f"golden/{file_name}", "generated", n=2))[:60])
        pytest.fail(f"{file_name} differs from what is generated now:\n{diff}\n{HINT}")
    assert golden.read(file_name.replace(".py", ".skip.txt") if file_name.endswith(".py")
                       else file_name.replace(".skip.txt", ".py")) is None, "a golden file of the other kind exists too"


def test_no_stray_golden_files():
    assert golden.stray_files() == []


def test_golden_scripts_compile_and_are_deterministic():
    for name, backend in golden.all_cases():
        file_name, text = golden.render(name, backend)
        if file_name.endswith(".py"):
            compile(text, file_name, "exec")
        assert golden.render(name, backend) == (file_name, text)


def test_golden_set_covers_every_task_the_translator_handles():
    """Every task and output type with a handler appears in some golden document, so a new handler needs a golden document."""
    import json
    from pysed2translate.core import OUTPUT_HANDLERS, TASK_HANDLERS

    seen = set()

    def walk(node):
        if isinstance(node, dict):
            if "_type" in node:
                seen.add(node["_type"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for name in golden.document_names():
        with open(os.path.join(golden.DOCS, f"{name}.sed2.json"), encoding="utf-8") as f:
            walk(json.load(f))
    assert sorted((set(TASK_HANDLERS) | set(OUTPUT_HANDLERS)) - seen) == []


def test_update_command_reports_up_to_date(capsys):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    import update_golden

    assert update_golden.main(["--check"]) == 0
    assert "up to date" in capsys.readouterr().out
