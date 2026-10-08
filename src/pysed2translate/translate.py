"""Turn a SED2 document into the text of a Python script."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from .backends import BACKENDS
from .capabilities import load_table
from . import outputs, tasks, tasks_repeat, tasks_sim  # noqa: F401  (importing them registers the element handlers)
from .core import Translator
from .errors import InvalidDocumentError, TranslationError

log = logging.getLogger("pysed2translate")


@dataclass
class Options:
    backend: str
    prefix: str = ""
    source_name: str = ""
    input_dir: Optional[str] = None   # default for the script's --input-dir; None means the script's own directory
    output_dir: Optional[str] = None  # default for the script's --output-dir; None means the current directory


def default_prefix(path: str) -> str:
    """'cases/00001/00001.sed2.json' -> '00001'."""
    name = os.path.basename(path)
    for suffix in (".sed2.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def load_document(path: str):
    """Read and validate a SED2 file with libsed2.  Raises InvalidDocumentError on any validation error."""
    import libsed2

    try:
        doc = libsed2.read_from_file(path)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise InvalidDocumentError(path, [("", "", f"cannot read the file: {e}")]) from e
    except Exception as e:  # libsed2 may raise its own error types for malformed content
        raise InvalidDocumentError(path, [("", "", f"cannot parse the document: {e}")]) from e
    problems = doc.validate()
    errors = []
    for p in problems:
        if str(p.severity).lower().startswith("warn"):
            log.warning("%s %s: %s", p.rule_id, p.location, p.message)
        else:
            errors.append((p.rule_id, p.location, p.message))
    if errors:
        raise InvalidDocumentError(path, errors)
    return doc


def emit_script(doc, options: Options) -> str:
    """The text of the generated script for a validated document."""
    return Translator(doc, options).build()


def translate_file(path: str, backend: str, prefix: Optional[str] = None, input_dir: Optional[str] = None,
                   output_dir: Optional[str] = None) -> str:
    doc = load_document(path)
    if backend in BACKENDS:  # an unknown backend is reported by emit_script
        load_table().check_document(backend, doc.to_json_value())
    options = Options(backend=backend, prefix=prefix if prefix is not None else default_prefix(path),
                      source_name=os.path.basename(path), input_dir=input_dir, output_dir=output_dir)
    return emit_script(doc, options)
