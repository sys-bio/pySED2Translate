#!/usr/bin/env bash
# Create a Python 3.13 virtual environment with every simulator backend installed.
# Usage: scripts/setup_env.sh [VENV_DIR]     (default: .venv)
# Requires uv (https://docs.astral.sh/uv/).  Run from the pySED2Translate directory.
set -euo pipefail
VENV="${1:-.venv}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
uv python install 3.13
uv venv --python 3.13 "$VENV"
uv pip install --python "$VENV/bin/python" -r "$HERE/requirements.txt"
WHEEL="$(ls "$HERE"/libsed2-*.whl 2>/dev/null | sort | tail -n 1 || true)"
if [ -n "$WHEEL" ]; then
  uv pip install --python "$VENV/bin/python" --force-reinstall --no-deps "$WHEEL"
else
  echo "NOTE: no libsed2-*.whl found in $HERE; download one from https://github.com/sys-bio/SED2/releases/"
fi
# The roadrunner wheel links libpython dynamically.  On Linux, uv-managed Pythons keep it
# outside the default loader path, so write an activation helper that sets it.
LIBDIR="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
cat > "$VENV/env.sh" <<EOT
# source this file after activating the environment
export LD_LIBRARY_PATH="$LIBDIR\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
EOT
echo "Done.  Activate with:  source $VENV/bin/activate && source $VENV/env.sh   (Linux)"
echo "Then run:              python scripts/smoke_test.py"
