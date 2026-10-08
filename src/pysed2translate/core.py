"""The translation core: walk a validated SED2 document in file order and build the text of a Python script.

A `Translator` owns the code builder and the symbol tables.  Handlers for tasks and outputs register in
TASK_HANDLERS / OUTPUT_HANDLERS, keyed by the document's `_type` string; a handler is called as
`handler(translator, element_id, element)` and writes its lines with `translator.cb`.  A task handler must also
call `translator.register_task(id, TaskValues)` so that references to the task can be translated.

Reference translation (`Translator.ref`) turns "#constants:x['a'][1:3]" or "#tasks:t.model" into a Python
expression that evaluates to AnnotatedData (or a model handle for `.model`).
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from . import mathgen
from .backends import BACKENDS
from .codegen import CodeBuilder
from .errors import TranslationError

TASK_HANDLERS: dict = {}
OUTPUT_HANDLERS: dict = {}


def task_handler(type_name: str):
    def deco(fn: Callable) -> Callable:
        TASK_HANDLERS[type_name] = fn
        return fn
    return deco


def output_handler(type_name: str):
    def deco(fn: Callable) -> Callable:
        OUTPUT_HANDLERS[type_name] = fn
        return fn
    return deco


def index_literal(accessors) -> str:
    """Python source for AnnotatedData.index(...) from libsed2 bracket accessors: a list of brackets, each a list of
    the indices written in it (`[a:b, n]` is one bracket with two indices; `[a:b][n]` is two brackets)."""
    groups: list = []
    for kind, ix in accessors:
        if kind != "index":
            raise TranslationError(f"unexpected accessor {kind!r} in an index chain")
        if not groups or not ix.same_bracket:
            groups.append([])
        groups[-1].append(f"({ix.kind!r}, {ix.value!r})")
    return "[" + ", ".join("[" + ", ".join(g) + "]" for g in groups) + "]"


class TaskValues:
    """What a task makes available to references.  `expr_for(suffix)` returns the Python expression for
    `#tasks:id` (suffix None), `#tasks:id.model`, or `#tasks:id.strings` before any bracket indices."""

    def __init__(self, exprs: dict):
        self._exprs = exprs

    def expr_for(self, suffix: Optional[str]) -> Optional[str]:
        return self._exprs.get(suffix)


class Translator:
    def __init__(self, doc, options):
        if options.backend not in BACKENDS:
            raise TranslationError(f"unknown backend {options.backend!r}; choose from {', '.join(BACKENDS)}")
        self.doc = doc
        self.options = options
        self.backend = options.backend
        self.cb = CodeBuilder()
        self._tasks: dict = {}
        self._idents: dict = {}
        self.constants: dict = {}

    # ------------------------------------------------------------------ names

    def ident(self, prefix: str, element_id: str) -> str:
        """A unique Python identifier for a document id: ident('task', 'sim 1') -> 'task_sim_1'."""
        key = (prefix, element_id)
        if key not in self._idents:
            base = prefix + "_" + re.sub(r"\W", "_", element_id)
            name, n = base, 1
            used = set(self._idents.values())
            while name in used:
                n += 1
                name = f"{base}_{n}"
            self._idents[key] = name
        return self._idents[key]

    def register_task(self, task_id: str, values: TaskValues) -> None:
        self._tasks[task_id] = values

    def unregister_tasks(self, prefix: str) -> None:
        """Forget the values of the elements below a repeat (`rep:subTasks:x`, `rep:loopVariables:v`, ...): they exist
        only while the repeat runs."""
        for key in [k for k in self._tasks if k.startswith(prefix + ":")]:
            del self._tasks[key]

    def translate_task(self, task_id: str, element) -> None:
        """Translate one task (a sub-task of a repeat is given the id `repeat:subTasks:id`)."""
        self._dispatch(TASK_HANDLERS, "task", task_id, element)

    # ------------------------------------------------------------------ references and math

    def ref(self, text: str, _seen: tuple = ()) -> str:
        import libsed2

        if not libsed2.is_reference(text):
            raise TranslationError(f"{text!r} is not a reference")
        pr = libsed2.parse_reference(text)
        if pr.collection == "constants":
            return self._constant_ref(pr, _seen)
        if pr.collection == "tasks":
            return self._task_ref(pr)
        raise TranslationError(f"reference {text!r}: only #constants: and #tasks: references can be used as data")

    def _constant_ref(self, pr, seen: tuple) -> str:
        cid = pr.path[0]
        if len(pr.path) != 1:
            raise TranslationError(f"reference {pr.raw!r}: a constant has no sub-elements")
        if cid in seen:
            raise TranslationError(f"constants refer to each other in a cycle: {' -> '.join(seen + (cid,))}")
        if cid not in self.constants:
            raise TranslationError(f"reference {pr.raw!r}: no constant {cid!r}")
        value = self.constants[cid]
        import libsed2

        if isinstance(value, str) and libsed2.is_reference(value):
            base = self.ref(value, seen + (cid,))
        else:
            base = f"rt.AnnotatedData.from_constant(CONSTANTS[{cid!r}])"
        if pr.accessors:
            return f"{base}.index({index_literal(pr.accessors)})"
        return base

    def _task_ref(self, pr) -> str:
        tid = pr.path[0] if len(pr.path) == 1 else ":".join(pr.path)   # `rep:subTasks:x`, `loop:loopVariables:v`
        if tid not in self._tasks:
            raise TranslationError(f"reference {pr.raw!r}: task {tid!r} produces no values here "
                                   "(not translated yet, a reference to a later task, or to the inside of a repeat)")
        accessors = list(pr.accessors)
        suffix = None
        if accessors and accessors[0][0] == "dot":
            suffix = accessors.pop(0)[1]
        base = self._tasks[tid].expr_for(suffix)
        if base is None:
            raise TranslationError(f"reference {pr.raw!r}: task {tid!r} has no output {suffix or '[id]'!r}")
        if accessors:
            if any(k != "index" for k, _ in accessors):
                raise TranslationError(f"reference {pr.raw!r}: .loc/.isel/.sel accessors are not implemented yet")
            return f"{base}.index({index_literal(accessors)})"
        return base

    def math(self, text: str) -> str:
        return mathgen.math_to_python(text, self.ref)

    # ------------------------------------------------------------------ the script

    def build(self) -> str:
        cb, doc, opt = self.cb, self.doc, self.options
        for cid in doc.get_constants():
            self.constants[cid] = doc.get_constants_item(cid)
        cb.line("#!/usr/bin/env python3")
        cb.line(f"# Generated by pysed2translate from {opt.source_name or 'a SED2 document'} (backend: {self.backend}).")
        cb.line("# Do not edit: regenerate from the SED2 document instead.")
        cb.line('"""Run the simulation experiment and write its report files."""')
        cb.line("import argparse")
        cb.line("import os")
        cb.line("import sys")
        cb.line("import traceback")
        cb.line()
        cb.line("from pysed2translate import runtime as rt")
        cb.line()
        cb.line(f"BACKEND = {self.backend!r}")
        cb.line(f"PREFIX = {opt.prefix!r}")
        cb.line(f"DEFAULT_INPUT_DIR = {None if opt.input_dir is None else repr(opt.input_dir)}")
        cb.line(f"DEFAULT_OUTPUT_DIR = {None if opt.output_dir is None else repr(opt.output_dir)}")
        cb.line()
        self._emit_constants()
        cb.line()
        with cb.block("def run(ctx):"):
            for tid in doc.get_tasks():
                self._dispatch(TASK_HANDLERS, "task", tid, doc.get_tasks_item(tid))
            for oid in doc.get_outputs():
                self._dispatch(OUTPUT_HANDLERS, "output", oid, doc.get_outputs_item(oid))
        cb.line()
        cb.line()
        with cb.block("def main(argv=None):"):
            cb.line("ap = argparse.ArgumentParser(description=__doc__)")
            cb.line("ap.add_argument('--input-dir', default=DEFAULT_INPUT_DIR or os.path.dirname(os.path.abspath(__file__)),")
            cb.line("                help='directory that relative model and data locations are resolved against')")
            cb.line("ap.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR or '.',")
            cb.line("                help='directory the result files are written to')")
            cb.line("ap.add_argument('--no-png', action='store_true', help='do not draw pictures of the plots')")
            cb.line("args = ap.parse_args(argv)")
            cb.line("ctx = rt.Context(args.input_dir, args.output_dir, PREFIX, png=not args.no_png)")
            with cb.block("try:"):
                cb.line("run(ctx)")
            with cb.block("except Exception:  # a failed task stops the experiment"):
                cb.line("traceback.print_exc()")
                cb.line("return 1")
            cb.line("return ctx.exit_status()")
        cb.line()
        cb.line()
        with cb.block("if __name__ == '__main__':"):
            cb.line("sys.exit(main())")
        return cb.text()

    def _emit_constants(self) -> None:
        cb = self.cb
        if not self.constants:
            cb.line("CONSTANTS = {}")
            return
        cb.line("CONSTANTS = {")
        for cid, value in self.constants.items():
            cb.line(f"    {cid!r}: {value!r},")
        cb.line("}")

    def _dispatch(self, table: dict, what: str, element_id: str, element) -> None:
        type_name = element.get_type()
        handler = table.get(type_name)
        if handler is None:
            raise TranslationError(f"{what} {element_id!r}: translating '{type_name}' is not implemented yet")
        handler(self, element_id, element)
