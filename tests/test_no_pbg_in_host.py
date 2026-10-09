"""Rule M1 of process-bigraph.md (3.11): the host never imports the process-bigraph target, and knows nothing about it.

The only host-side trace of the target is this test; it only reads files and is removed together with the target (`pbg/`)."""
import os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def test_host_source_does_not_mention_the_pbg_target():
    for root, _dirs, files in os.walk(SRC):
        if "__pycache__" in root:
            continue
        for name in files:
            if not name.endswith((".py", ".json", ".toml")):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as f:
                text = f.read()
            for needle in ("pysed2translate_pbg", "process_bigraph", "process-bigraph"):
                assert needle not in text, f"{os.path.join(root, name)} mentions {needle!r}"
