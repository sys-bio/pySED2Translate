"""Make the sibling sed2-test-suite tools importable (for cross-checking against its reader), if present."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [os.environ.get("SED2SUITE_TOOLS", ""), os.path.join(_HERE, "..", "..", "sed2-test-suite", "tools")]
for _c in _CANDIDATES:
    if _c and os.path.isdir(os.path.join(_c, "sed2suite")):
        sys.path.insert(0, os.path.abspath(_c))
        break
