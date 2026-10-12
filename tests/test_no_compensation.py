"""Guards against compensating for a simulator inside the runtime (CLAUDE.md, "Never hide a problem; expose it").

A backend returns what the simulator returns, or refuses.  It does not re-run, interpolate, re-time, relabel, rescale or otherwise
correct a result because the simulator gets it wrong.  Two tripwires:

1. Words that describe a correction in a comment of a backend (or of kisao.py) fail the test, unless the same place names the problem:
   a recorded disagreement (D-n, sed2-test-suite/disagreements.json), an upstream draft (R-n, W-n, ...), a known deviation
   (COMP-n, docs/compensations.md), or a refusal
   (a `raise` or the word "refus" within three lines).
2. The COMP-n ids used in the code and the ids in docs/compensations.md must be the same set, so that a deviation cannot be added
   without being listed, and a listed one cannot be forgotten after the code is gone.

This is a tripwire on words, not a proof: a correction written without those words passes.  The rule is in CLAUDE.md; a reviewer reads
the diff of every backend for it.  `test_roadrunner_span_is_the_plain_result` below checks the one place where the rule was broken.
"""
import glob
import json
import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src", "pysed2translate")
FILES = sorted(glob.glob(os.path.join(SRC, "runtime", "backends", "*.py"))) + [os.path.join(SRC, "kisao.py")]
REGISTER = os.path.join(ROOT, "docs", "compensations.md")

RED_FLAGS = re.compile(
    r"interpolat|less accurate|more accurate|inaccura|work(?:s|ing)? around|workaround|compensat|recomput|re-?integrat|re-?run|"
    r"on its own|loses |lose precision|wrong (?:value|answer|result|label)|to match|to agree|as (?:roadrunner|copasi|opencor) does|"
    r"substitut|patch(?:es|ed)? (?:over|up)|fudge|hack", re.IGNORECASE)
NAMED = re.compile(r"\b(?:D|COMP|R|W|P|C|B)-\d+\b")
REFUSAL = re.compile(r"\braise\b|refus", re.IGNORECASE)


def _lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().split("\n")


def unrecorded(lines):
    """Indices of lines that describe a correction without naming the recorded problem or being a refusal."""
    hits = []
    for i, line in enumerate(lines):
        if not RED_FLAGS.search(line):
            continue
        if any(NAMED.search(x) for x in lines[max(0, i - 3): i + 4]):
            continue
        if REFUSAL.search(line) or any(re.match(r"\s*raise\b", x) for x in lines[i + 1: i + 3]):
            continue
        hits.append(i)
    return hits


def test_no_unrecorded_correction_in_the_backends():
    found = []
    for path in FILES:
        lines = _lines(path)
        found += [f"{os.path.relpath(path, ROOT)}:{i + 1}: {lines[i].strip()}" for i in unrecorded(lines)]
    assert not found, ("a backend must return the simulator's result or refuse (CLAUDE.md).  If this is a correction, remove it, "
                       "record the problem (disagreements.json, an upstream draft) and refuse or return the plain result.  If the "
                       "text is not a correction, name the recorded problem (D-n) on the line.\n" + "\n".join(found))


# the correction that was removed from the roadrunner backend (disagreement D-003), as it was written
REMOVED_CORRECTION = """\
            rr.model.setTime(a)
            rr.integrator.setValue("variable_step_size", True)
            table = np.array(rr.simulate(a, b))
            # roadrunner's last variable-step row (at the span's end) is interpolated and less accurate than the
            # others (relative error ~5e-5 against tolerances of 1e-10), so the end point is integrated on its own
            rr.reset()
            rr.integrator.setValue("variable_step_size", False)
            rr.model.setTime(a)
            last = self._run(rr, [a, b])[-1]
            table = np.vstack([table[table[:, 0] < b], last])
"""


def test_the_tripwire_catches_the_correction_that_was_removed():
    lines = ["            if tc.start not in (None, 0.0) and tc.start != a:",
             '                raise DataError("independentVariableInit must equal the span\'s start")'] + REMOVED_CORRECTION.split("\n")
    assert unrecorded(lines), "the word tripwire no longer catches the D-003 correction"


def _used_comp_ids():
    used = {}
    for path in FILES:
        for i, line in enumerate(_lines(path)):
            for m in re.finditer(r"\bCOMP-\d+\b", line):
                used.setdefault(m.group(0), []).append(f"{os.path.relpath(path, ROOT)}:{i + 1}")
    return used


def _registered_comp_ids():
    with open(REGISTER, encoding="utf-8") as f:
        return set(re.findall(r"^\| (COMP-\d+) \|", f.read(), re.MULTILINE))


def test_known_deviations_in_the_code_and_in_the_register_are_the_same_set():
    used, registered = _used_comp_ids(), _registered_comp_ids()
    assert set(used) <= registered, f"deviations in the code but not in docs/compensations.md: {sorted(set(used) - registered)}"
    assert registered <= set(used), f"deviations in docs/compensations.md that no code mentions (remove them): {sorted(registered - set(used))}"


def test_recorded_disagreements_named_in_the_backends_exist():
    suite = os.environ.get("SED2SUITE")
    path = os.path.join(suite, "disagreements.json") if suite else None
    if not path or not os.path.exists(path):
        pytest.skip("sed2-test-suite is not available (SED2SUITE)")
    with open(path, encoding="utf-8") as f:
        known = {e["id"] for e in json.load(f)["entries"]}
    named = {m.group(0) for p in FILES for line in _lines(p) for m in re.finditer(r"\bD-\d+\b", line)}
    assert named <= known, f"disagreements named in the code but not recorded in sed2-test-suite: {sorted(named - known)}"
