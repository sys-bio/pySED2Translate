"""A small helper for building Python source text with correct indentation."""
from __future__ import annotations

from contextlib import contextmanager


class CodeBuilder:
    def __init__(self, indent: str = "    "):
        self._lines: list[str] = []
        self._level = 0
        self._indent = indent

    def line(self, text: str = "") -> None:
        """Add one line at the current indentation (blank lines carry no trailing spaces)."""
        self._lines.append(self._indent * self._level + text if text else "")

    def lines(self, text: str) -> None:
        for t in text.splitlines():
            self.line(t)

    @contextmanager
    def block(self, header: str):
        """`with cb.block("def f():"):` writes the header and indents what follows."""
        self.line(header)
        self._level += 1
        start = len(self._lines)
        try:
            yield self
        finally:
            if len(self._lines) == start:
                self.line("pass")
            self._level -= 1

    def text(self) -> str:
        return "\n".join(self._lines) + "\n"
