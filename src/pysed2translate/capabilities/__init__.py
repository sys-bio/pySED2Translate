"""What each backend can do.  The data is capabilities.json (validated by capabilities.schema.json).

    table = load_table()
    table.check_task("opencor", "j1", "jacobianFull", task_json)     # raises UnsupportedTaskError
    table.check_document("opencor", doc_json)                         # checks every task, nested ones too
"""
from __future__ import annotations

import json
import os
from typing import Optional

from ..errors import TranslationError, UnsupportedTaskError
from .checks import CHECKS

_HERE = os.path.dirname(os.path.abspath(__file__))
TABLE_PATH = os.path.join(_HERE, "capabilities.json")
SCHEMA_PATH = os.path.join(_HERE, "capabilities.schema.json")


def _lookup(task_json: dict, path: str):
    node = task_json
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def validate_table(data: dict) -> list:
    """Problems in a capability table as a list of strings (empty if fine)."""
    import jsonschema

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    problems = []
    for err in sorted(jsonschema.Draft202012Validator(schema).iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        problems.append("/".join(str(p) for p in err.absolute_path) + ": " + err.message)
    if problems:
        return problems
    backends = data["backends"]
    for task, entries in data["tasks"].items():
        for b in backends:
            if b not in entries:
                problems.append(f"tasks/{task}: no entry for backend {b!r}")
        for b in entries:
            if b not in backends:
                problems.append(f"tasks/{task}: {b!r} is not a listed backend")
            for name in [entries[b].get("check")]:
                if name is not None and name not in CHECKS:
                    problems.append(f"tasks/{task}/{b}: check {name!r} is not registered in checks.py")
    return problems


class CapabilityTable:
    def __init__(self, data: dict):
        self._data = data

    @property
    def backends(self) -> list:
        return list(self._data["backends"])

    @property
    def task_types(self) -> list:
        return sorted(self._data["tasks"])

    def entry(self, backend: str, task_type: str) -> Optional[dict]:
        return self._data["tasks"].get(task_type, {}).get(backend)

    def verdict(self, backend: str, task_type: str, task_json: Optional[dict] = None) -> Optional[str]:
        """None if the backend can perform the task, otherwise the reason it cannot."""
        if backend not in self._data["backends"]:
            raise TranslationError(f"unknown backend {backend!r}")
        entry = self.entry(backend, task_type)
        if entry is None:
            return f"the capability table has no entry for task type {task_type!r}"
        task_json = task_json or {}
        for cond in entry.get("conditions", []):
            if all(_lookup(task_json, path) in allowed for path, allowed in cond["when"].items()):
                return None if cond["supported"] else cond["reason"]
        if not entry["supported"]:
            return entry["reason"]
        if "check" in entry:
            return CHECKS[entry["check"]](task_json, backend)
        return None

    def check_task(self, backend: str, task_id: str, task_type: str, task_json: Optional[dict] = None) -> None:
        reason = self.verdict(backend, task_type, task_json)
        if reason is not None:
            raise UnsupportedTaskError(backend, f"task '{task_id}' ({task_type})", reason)

    def check_document(self, backend: str, doc_json: dict) -> None:
        """Check every task in a document (given as its JSON), including nested subTasks."""
        def walk(tasks: dict) -> None:
            for tid, t in tasks.items():
                if not isinstance(t, dict):
                    continue
                ttype = t.get("_type")
                if isinstance(ttype, str):
                    self.check_task(backend, tid, ttype, t)
                sub = t.get("subTasks")
                if isinstance(sub, dict):
                    walk(sub)

        walk(doc_json.get("tasks", {}) or {})


def load_table(path: Optional[str] = None) -> CapabilityTable:
    with open(path or TABLE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    problems = validate_table(data)
    if problems:
        raise TranslationError("invalid capability table: " + "; ".join(problems[:5]))
    return CapabilityTable(data)
