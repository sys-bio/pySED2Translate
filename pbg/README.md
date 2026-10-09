# pbg/ - SED2 to Process Bigraph (`pysed2translate-pbg`)

A second target of pySED2Translate, as a separate package: it translates a SED2 document into a process-bigraph composite
document (`NNNNN.pbg.composite.json`) and runs it.  The plan and the reasoning are in `../process-bigraph.md`; nothing here has been
committed, and nothing has been reported to any other project (`upstream/` holds drafts for you to report).

    pysed2translate-pbg translate X.sed2.json --backend roadrunner --wrappers off -o X.pbg.composite.json
    pysed2translate-pbg run X.pbg.composite.json --input-dir . --output-dir results
    pysed2translate-pbg suite [CASES] -b roadrunner [--matrix fba=cobra:glpk,cobra:scipy] [--script] [--crosscheck]
    pysed2translate-pbg --backend-list
    pysed2translate-pbg engines

Install (after the host, see `../README.md`): `pip install -r pbg/requirements-lock.txt && pip install -e pbg --no-deps`.
Only `process-bigraph` and `bigraph-schema` are needed for `--wrappers off`; `viva-tellurium` and `viva-copasi` for the wrappers
(`pip install ./pbg[viva]`).  Exit statuses are the host's: 0 done, 1 a task failed, 2 usage, 10 invalid document, 11 the chosen
backend (or, in strict mode, the wrapper) cannot do it, 12 other translation error.

## Who runs the simulations: `--wrappers`

| Mode | Meaning |
|---|---|
| `strict` (default) | simulation tasks run in the community wrappers (viva-tellurium for `roadrunner`, viva-copasi for `copasi`); a task a wrapper cannot do is refused (exit 11) with the ledger ids of its gaps.  Nothing is run elsewhere silently |
| `prefer` | the wrapper where it can, else the host runtime; each fallback is a note on stderr and in the manifest |
| `off` | the host runtime only (the code the generated Python scripts use) |

The ledger is `engines/v1/providers.py` (`LEDGER`): `W-n` are gaps in the wrappers (drafts in `upstream/W-n.md`), `L-n` are limits of
this provider.  Over the 282 suite cases `tests/providers/expected_gaps.json` records, for each case, whether strict mode
translates it or refuses it and with which ids, and what the wrapped cases did when run; `tools/provider_gaps.py --check [--run]`
compares, and the test fails on any difference.  Current picture (roadrunner / copasi): 30 / 28 cases run a wrapper; the rest are
refused with W-5 (output points not uniform or chosen by the solver), W-6 (a changed model cannot be handed over), W-10 (inside a
repeat), W-1/W-3 (settings), W-8 (steady-state options, Jacobian), W-11 (flux balance analysis has no wrapper), and so on.  Of the
wrapped cases, 1 (roadrunner, case 00119: the wrapper cannot set tolerances, W-1) misses the canonical data and 5 (copasi) fail inside
the wrapper on models without species (W-14); all are recorded, none is worked around.

## Layout and the kill list

| Path | What |
|---|---|
| `src/pysed2translate_pbg/host.py` | the only module that imports `pysed2translate` (rule M2) |
| `src/pysed2translate_pbg/cli.py`, `suite.py`, `api.py`, `engines/__init__.py` | commands, suite runner, engine interface and discovery |
| `src/pysed2translate_pbg/engines/v1/` | engine v1: `builder.py` (SED2 -> document), `steps.py` (the Step classes), `loop.py` (clock form, repeats), `providers.py` (wrapper rules and ledger), `runner.py` |
| `tests/contract/` | engine-agnostic: translate, run, compare with the suite's canonical data; the modularity rules |
| `tests/v1/` | engine v1: golden documents (`golden/`, `golden.py`), loops, seams, documents |
| `tests/providers/` | the wrapper provider: rules, documents, runs, `expected_gaps.json` |
| `tests/native/` | tier C: process-bigraph documents with scripts translated from them (see its README) |
| `tests/advanced/` | the real iAF1260 model through a Scatter (needs the model, which is not in the repository) |
| `tools/` | `pbg2py.py` (scheduler exporter), `make_tier_c.py`, `provider_gaps.py` |
| `research/` | the experiments the plan's findings come from (see its README) |
| `upstream/` | 18 drafted issue texts (W-1 to W-14, P-1 to P-4).  **None filed.**  You report them |
| `findings/` | drafts for this project's own bookkeeping (SED2 questions, wrapper findings).  Nothing added to SED2/TODO.md except the FBA section |
| `../.github/workflows/pbg.yml` | the CI workflow for this package (host alone, target, target with wrappers) on many platforms; runs only when `pbg/`, `src/` or the workflow change; the host's own tests are in `../.github/workflows/ci.yml` |
| `NOTES.md` | lessons that survive a rewrite |

**To remove the target:** (1) delete this folder; (2) delete `../process-bigraph*.md` if the notes are no longer wanted (`NOTES.md` and
`research/` are the part worth keeping); (3) delete `../.github/workflows/pbg.yml`; nothing else: the host does not import this package, and its tests do not need it.  The
host's own additions for flux balance analysis (the `cobra` backend, `kinds` and `serves` in the capability table) are the host's.
