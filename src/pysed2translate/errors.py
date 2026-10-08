"""Exceptions raised by the translator, and the command-line exit status each one maps to."""
from __future__ import annotations

EXIT_OK = 0
EXIT_USAGE = 2          # bad command line (argparse's own status)
EXIT_INVALID = 10       # the SED2 document is unreadable or does not validate
EXIT_UNSUPPORTED = 11   # the chosen backend cannot perform a task in the document (a skip, not a failure)
EXIT_TRANSLATION = 12   # anything else that went wrong while translating


class PySED2TranslateError(Exception):
    """Base class.  `exit_code` is what the command-line program exits with."""

    exit_code = EXIT_TRANSLATION


class InvalidDocumentError(PySED2TranslateError):
    """The document could not be read or has validation errors.

    problems: list of (rule_id, location, message); rule_id is '' for read errors.
    """

    exit_code = EXIT_INVALID

    def __init__(self, path: str, problems: list):
        self.path = path
        self.problems = list(problems)
        first = "; ".join(f"{r + ' ' if r else ''}{m}" for r, _loc, m in self.problems[:3])
        more = f" (and {len(self.problems) - 3} more)" if len(self.problems) > 3 else ""
        super().__init__(f"{path}: invalid SED2 document: {first}{more}")


class UnsupportedTaskError(PySED2TranslateError):
    """A backend cannot perform a task.  Names the backend, the task and the reason."""

    exit_code = EXIT_UNSUPPORTED

    def __init__(self, backend: str, task: str, reason: str):
        self.backend = backend
        self.task = task
        self.reason = reason
        super().__init__(f"backend '{backend}' cannot perform {task}: {reason}")


class TranslationError(PySED2TranslateError):
    """The document is valid but the translator could not turn part of it into code."""

    exit_code = EXIT_TRANSLATION
