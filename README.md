# pySED2Translate
A translator from SED2 to a python script, using libSED2.

## Usage

```
pysed2translate 00001.sed2.json --backend roadrunner -o 00001.py
python 00001.py --input-dir . --output-dir results/
```

See `docs/generated-script-contract.md` for exit codes and what the generated script reads and writes, and
`build.md` for the project plan.  Setup: `scripts/setup_env.sh` (or `.ps1`), then
`pip install -e . --no-deps` inside the environment.  The libsed2 wheel is not on PyPI; put it in this directory.
