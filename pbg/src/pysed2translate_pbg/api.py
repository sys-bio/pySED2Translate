"""The interface every engine implements (rule M4), and the types it exchanges with the commands.

An engine is a folder `engines/<name>/` whose `__init__.py` defines:

    NAME: str                      the folder name, e.g. "v1"
    VERSION: str
    def add_arguments(parser)      options of this engine (for example --loop-form); may add nothing
    def translate(document, options) -> TranslationResult
    def run(document_path, input_dir, output_dir, png=True, manifest=None) -> int     # 0, 1 or 11 (the script contract)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Options:
    """What the command line tells an engine.

    backend    {kind or "*": backend name}: "*" is the default for every kind (section 3.14 of the plan); the kinds are
               ode, steady, jacobian, fba
    prefix     prefix of the result file names (default: the document's file name up to .sed2.json)
    source_name  the document's file name, for the header only
    input_dir / output_dir  defaults written into the document's `context` store (None: "." and "results")
    engine     engine-specific options by name (as parsed from the engine's own arguments)
    """
    backend: dict = field(default_factory=dict)
    prefix: str = ""
    source_name: str = ""
    input_dir: Optional[str] = None
    output_dir: Optional[str] = None
    engine: dict = field(default_factory=dict)


@dataclass
class TranslationResult:
    """files      {file name: text} for every file the translation produced (the document, normally one)
    manifest   {"engine", "engineVersion", "backends": {kind: {"backend", "provider", "variant"}}, "notes": [...]}"""
    files: dict
    manifest: dict = field(default_factory=dict)
