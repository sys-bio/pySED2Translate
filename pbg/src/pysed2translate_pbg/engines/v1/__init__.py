"""Engine v1: SED2 task graph -> process-bigraph document, one Step per task (process-bigraph.md, section 3).

The interface of an engine (see ../../api.py): NAME, VERSION, add_arguments, translate, run.
"""
from __future__ import annotations

import json

from pysed2translate_pbg import host
from pysed2translate_pbg.api import Options, TranslationResult

from . import providers

NAME = "v1"
VERSION = "0.1"


def add_arguments(parser) -> None:
    parser.add_argument("--wrappers", choices=providers.MODES, default=providers.DEFAULT_MODE,
                        help="v1: who runs the simulation tasks: 'strict' (default) the community wrappers (viva-tellurium for "
                             "roadrunner, viva-copasi for copasi) and nothing else - a task a wrapper cannot do is refused, with "
                             "the ledger ids of pbg/upstream; 'prefer' the wrappers where they can, else the host runtime, with "
                             "a note for each fallback; 'off' the host runtime only")
    parser.add_argument("--loop-form", choices=("clock", "nested"), default="clock",
                        help="v1: how a Loop is written: 'clock' (a clock process in an inner composite; default) or 'nested' "
                             "(one inner composite per iteration)")


def engine_options(args) -> dict:
    return {"loop_form": getattr(args, "loop_form", "clock"), "wrappers": getattr(args, "wrappers", providers.DEFAULT_MODE)}


def translate(document, options: Options) -> TranslationResult:
    from .builder import Builder

    if not any(options.backend.values()):
        raise host.TranslationError("no backend chosen (use --backend NAME)")
    default = options.backend.get("*")
    overrides = {k: v for k, v in options.backend.items() if k != "*"}
    if default is None:
        table = host.capability_table()
        missing = sorted(k for k in host.kinds_in(document) if k not in overrides and len(table.serving(k)) != 1)
        if missing:
            raise host.TranslationError(f"no backend chosen for tasks of kind {', '.join(repr(k) for k in missing)} "
                                        "(use --backend NAME or --backend KIND=NAME)")
        default = next(iter(overrides.values()), "")
    host.check_document(default, document, overrides)          # raises UnsupportedTaskError with the reason
    mode = (options.engine or {}).get("wrappers", providers.DEFAULT_MODE)
    if mode not in providers.MODES:
        raise host.TranslationError(f"--wrappers must be one of {', '.join(providers.MODES)}, not {mode!r}")
    excluded: set = set()
    while True:
        builder = Builder(document, options, excluded)
        try:
            doc = builder.build()
            break
        except providers.WrapperModelUse as e:
            if mode == "prefer" and e.tid not in excluded:
                excluded.add(e.tid)       # that task runs on the host runtime; translate again
                continue
            raise providers.WrapperRefusal(", ".join(sorted({v for v in options.backend.values() if v})),
                                           {e.tid: [providers.gap("W-6", f"{e.reference} uses the model the task would hand on")]}) from e
    text = json.dumps(doc, indent=2, ensure_ascii=True) + "\n"
    manifest = {"engine": NAME, "engineVersion": VERSION, "backends": dict(options.backend), "notes": list(builder.notes),
                "wrappers": mode}
    return TranslationResult({f"{options.prefix}.pbg.composite.json": text}, manifest)


def run(document_path: str, input_dir: str, output_dir: str, png: bool = True, manifest=None) -> int:
    from .runner import run_document

    return run_document(document_path, input_dir, output_dir, png=png, manifest=manifest)
