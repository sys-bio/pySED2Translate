"""Run a v1 document: build the Composite, run it once (`run(0.0)`), write the manifest, return the script contract's status
(0 ok, 1 failure, 11 the backend cannot run the model)."""
from __future__ import annotations

import json
import os
import sys
import traceback

from pysed2translate_pbg import host


def _find(exc: BaseException, cls):
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, cls):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


def run_document(document_path: str, input_dir: str, output_dir: str, png: bool = True, manifest=None) -> int:
    from process_bigraph import Composite, allocate_core

    with open(document_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    state = doc["state"]
    wrappers = (doc.get("sed2") or {}).get("wrappers")
    if wrappers:
        wrong = [w for w in wrappers.get("modelFiles", [])
                 if os.path.abspath(w["modelFile"]) != os.path.abspath(os.path.join(input_dir, w["location"]))]
        if wrong:
            w = wrong[0]
            print(f"error: the wrapper for the model of task {w['task']!r} reads {os.path.abspath(w['modelFile'])} (fixed when the "
                  f"document was translated, W-6), but this run's input directory gives "
                  f"{os.path.abspath(os.path.join(input_dir, w['location']))}; translate with --input-dir {input_dir!r}",
                  file=sys.stderr)
            return 1
    state["context"].update({"inputDir": os.path.abspath(input_dir), "outputDir": os.path.abspath(output_dir), "png": bool(png)})
    backend = ", ".join(sorted({v for v in (doc.get("sed2", {}).get("backend") or {}).values() if v})) or "the backend"
    result = None
    try:
        core = allocate_core()
        if (wrappers or {}).get("family") == "copasi":
            from viva_copasi.composites import register_copasi    # registers the schema types the COPASI steps use (W-12)
            register_copasi(core)
        composite = Composite({"state": state}, core=core)
        composite.run(0.0)
        result = composite.state
    except BaseException as e:  # noqa: BLE001 - reported, then turned into a status
        cannot = _find(e, host.BackendCannotRun)
        if cannot is not None:
            print(f"skip: {getattr(cannot, 'backend', None) or backend} cannot run the model: {cannot}", file=sys.stderr)
            return host.EXIT_CANNOT_RUN
        if isinstance(e, KeyboardInterrupt):
            raise
        traceback.print_exc()
        return 1
    manifests = {"reports": {}, "plots": {}}
    failures = []
    for part in (result.get("manifest") or {}).values():
        for k in manifests:
            manifests[k].update(part.get(k, {}))
    for fl in (result.get("failures") or {}).values():
        failures += list(fl)
    if manifest:
        with open(manifest, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifests, f, indent=2, sort_keys=True)
            f.write("\n")
    return 1 if failures else 0
