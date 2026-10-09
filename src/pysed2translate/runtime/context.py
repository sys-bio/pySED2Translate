"""Where a generated script reads its inputs from and writes its results to, and how it records failures."""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager


class Context:
    """input_dir  : relative `location` values in the SED2 document are resolved against this directory
    output_dir : result files are written here (created if needed)
    prefix     : result file names are `<prefix>.<output id>.<extension>`
    png        : draw pictures of plots (the plot data files are always written)
    failures   : (step name, message) for each output step that raised; the script exits non-zero if any
    manifest   : what was written, by output id (file, format, kind, shape, labels); the script writes it with
                 --manifest FILE, which the suite runner uses to describe results it promotes to expected results
    """

    def __init__(self, input_dir: str, output_dir: str, prefix: str, png: bool = True):
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.prefix = prefix
        self.png = png
        self.failures: list = []
        self.manifest: dict = {"reports": {}, "plots": {}}

    def input_path(self, location: str) -> str:
        if os.path.isabs(location):
            return location
        return os.path.normpath(os.path.join(self.input_dir, location))

    def output_path(self, name: str) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        return os.path.join(self.output_dir, f"{self.prefix}.{name}")

    @contextmanager
    def step(self, name: str):
        """Run one output.  An error is reported and remembered, and the remaining outputs still run."""
        try:
            yield
        except Exception as e:  # noqa: BLE001 - any failure of one output must not stop the others
            self.failures.append((name, f"{type(e).__name__}: {e}"))
            print(f"error in {name}: {type(e).__name__}: {e}", file=sys.stderr)

    def write_manifest(self, path: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.manifest, f, indent=2, sort_keys=True)
            f.write("\n")

    def exit_status(self) -> int:
        return 1 if self.failures else 0
