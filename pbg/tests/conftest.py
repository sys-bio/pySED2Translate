import os

import pytest

from pysed2translate_pbg import host


@pytest.fixture(scope="session")
def suite():
    """The sed2-test-suite folder (SED2SUITE, or the sibling folder of the repository); tests skip without it."""
    try:
        return host.locate_suite(os.environ.get("SED2SUITE"))
    except FileNotFoundError:
        pytest.skip("sed2-test-suite not found (set SED2SUITE)")


def simulator_available(name: str) -> bool:
    mods = {"roadrunner": "roadrunner", "copasi": "basico", "opencor": "libopencor"}
    try:
        __import__(mods[name])
        return True
    except ImportError:
        return False
