"""The recorded gaps of the viva wrappers over the whole suite (tools/provider_gaps.py; tests/providers/expected_gaps.json).

A difference in either direction is news: a case that is now translated or refused differently, or that now runs differently, is
read, explained (a ledger entry in pbg/upstream, or a change of ours) and recorded in the file.  Nothing is absorbed.
The translation check takes seconds; the run check (all wrapper-backed cases, minutes) runs with PBG_RUN_VIVA=1."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", "..", "tools"))
sys.path.insert(0, TOOLS)
pytest.importorskip("viva_tellurium")
pytest.importorskip("viva_copasi")
import provider_gaps  # noqa: E402


@pytest.fixture(scope="module")
def expected():
    with open(provider_gaps.EXPECTED, encoding="utf-8") as f:
        return json.load(f)


def strip(entry):
    return {k: v for k, v in entry.items() if k != "run"}


def test_the_versions_are_the_ones_recorded(expected):
    now = provider_gaps.versions()
    for name in ("viva-tellurium", "viva-copasi", "process-bigraph", "bigraph-schema"):
        assert now[name] == expected["versions"][name], f"{name} changed: re-run tools/provider_gaps.py --write and read the differences"


def test_translation_outcomes_are_as_recorded(suite, expected):
    found = provider_gaps.survey(suite)
    for backend in found:
        want = {c: strip(e) for c, e in expected["backends"][backend].items()}
        got = {c: strip(e) for c, e in found[backend].items()}
        assert got == want, [c for c in sorted(set(got) | set(want)) if got.get(c) != want.get(c)]


@pytest.mark.skipif(not os.environ.get("PBG_RUN_VIVA"), reason="set PBG_RUN_VIVA=1 to run the wrapper-backed cases")
def test_run_outcomes_are_as_recorded(suite, expected):
    found = provider_gaps.survey(suite)
    provider_gaps.run_wrapped(suite, found)
    for backend in found:
        assert found[backend] == expected["backends"][backend]
