"""Helpers for engine v1 tests: write a SED2 document, translate it with v1, run it in this process."""
import json
import os

from process_bigraph import Composite, allocate_core

from pysed2translate_pbg import host
from pysed2translate_pbg.api import Options
from pysed2translate_pbg.engines import v1


def translate(tmp_path, doc: dict, backend="roadrunner", name="t", **engine):
    path = os.path.join(str(tmp_path), f"{name}.sed2.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    document = host.load_document(path)
    engine.setdefault("wrappers", "off")      # these tests are about the engine; the wrapper provider has its own tests
    opts = Options(backend={"*": backend}, prefix=name, source_name=os.path.basename(path), engine=engine)
    result = v1.translate(document, opts)
    text = next(iter(result.files.values()))
    return json.loads(text), text


def run_in_process(pbg_doc: dict, input_dir=".", output_dir=None, tmp_path=None):
    """Build the Composite and run it once; returns the final state."""
    state = json.loads(json.dumps(pbg_doc["state"]))
    state["context"].update({"inputDir": os.path.abspath(input_dir), "outputDir": str(output_dir or tmp_path), "png": False})
    c = Composite({"state": state}, core=allocate_core())
    c.run(0.0)
    return c.state


def data_of(state, task, out="data"):
    return state["tasks"][task][out]
