"""Golden documents of engine v1 (tests/v1/golden): exact text, determinism, the engine keys, and construction as a Composite.

After an intended change: `python tests/v1/golden/golden.py`, read the differences, keep them."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "golden"))
import golden  # noqa: E402

CASES = golden.all_cases()
MODULE = "pysed2translate_pbg.engines.v1."


@pytest.mark.parametrize("name,backend,wrappers", CASES)
def test_document_is_the_recorded_one(name, backend, wrappers):
    fn, text = golden.render(name, backend, wrappers)
    recorded = golden.read(fn)
    assert recorded is not None, f"{fn} is missing: run tests/v1/golden/golden.py"
    assert text == recorded, f"{fn} differs from what the translator writes now"


def test_no_stray_golden_files():
    assert golden.stray_files() == []


@pytest.mark.parametrize("name,backend,wrappers", CASES[:6])
def test_translation_is_deterministic(name, backend, wrappers):
    assert golden.render(name, backend, wrappers) == golden.render(name, backend, wrappers)


def documents():
    for name, backend, wrappers in CASES:
        fn, text = golden.render(name, backend, wrappers)
        if fn.endswith(".json"):
            yield fn, json.loads(text)


def steps_of(state):
    """Every step/process node in a state, however deep."""
    if isinstance(state, dict):
        if state.get("_type") in ("step", "process"):
            yield state
        for v in state.values():
            yield from steps_of(v)
    elif isinstance(state, list):
        for v in state:
            yield from steps_of(v)


@pytest.mark.parametrize("fn,doc", list(documents()), ids=[fn for fn, _ in documents()])
def test_documents_say_which_engine_made_them_and_their_addresses_are_the_engines(fn, doc):          # rule M6
    assert doc["sed2"]["engine"] == "v1" and doc["sed2"]["engineVersion"]
    for node in steps_of(doc["state"]):
        address = node["address"]
        assert address.startswith("local:!" + MODULE) or address.startswith(("local:!viva_tellurium.", "local:!viva_copasi.")), address


@pytest.mark.parametrize("fn,doc", [(fn, d) for fn, d in documents() if "wrappers" not in d["sed2"]],
                         ids=[fn for fn, d in documents() if "wrappers" not in d["sed2"]])
def test_every_document_builds_as_a_composite(fn, doc):
    from process_bigraph import Composite, allocate_core

    state = json.loads(json.dumps(doc["state"]))
    Composite({"state": state}, core=allocate_core())          # constructed, not run: the models are not there
