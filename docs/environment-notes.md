# Environment notes

* The `libroadrunner` wheel links `libpython3.13.so` dynamically.  On Linux with a uv-managed Python, set
  `LD_LIBRARY_PATH` to Python's lib directory (`scripts/setup_env.sh` writes `<venv>/env.sh` to do this; source it
  after activating the environment).  Windows is not affected.
* OpenCOR (`libopencor`) default solver tolerances are too loose for suite comparisons.  Set them explicitly in
  generated scripts (CVODE absolute 1e-12, relative 1e-10; see `scripts/smoke_test.py`).  Every backend's solver
  tolerances are set explicitly, never left at defaults.
* The libsed2 wheel is not on PyPI.  Put `libsed2-<version>-py3-none-any.whl` in this directory (it is
  git-ignored); `scripts/setup_env.sh` installs the newest one.  Current: 0.1.1.
