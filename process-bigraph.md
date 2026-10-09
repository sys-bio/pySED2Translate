# Translating SED2 to Process Bigraph

Status: a plan. Nothing in this file is implemented yet (the research prototypes in `pbg/research/` are not the product).
Updated 2026-10-09 with your second round of answers (section 8): FBA in the main group with per-kind backend switches (3.14),
`--wrappers strict` as the default, nothing filed upstream by me, tier C built now by the scheduler exporter (section 7), real models tried (3.13).
Researched 2026-10-08 against process-bigraph 1.8.5 (git e5325c1) with bigraph-schema 1.7.0, Python 3.13.
Sources are listed at the end.  The paper and both supplements were read on 2026-10-09 (section 2.10).  Everything marked "tested" was run in a scratch environment (see section 2.9);
everything else was read in the source or the documentation.

## 1. Summary

**What a "Process Bigraph input file" is.**  process-bigraph runs a *composite document*: one JSON object whose
`state` tree holds plain values (stores) and typed `process` / `step` nodes.  A node names a Python class (its
`address`), a `config`, and *wires* (paths into the state tree) for each input and output port.  Two nodes are
coupled only by naming the same path.  The runtime orders the steps by those wires, runs them, and an *emitter* node
records what it is wired to.  A document is plain JSON, so a translator can emit it as text, as pySED2Translate
already does for Python.

**Standing constraint: modularity (from you).**  Everything must be modular enough that throwing it all away and
starting over is easy.  So the target is **not** a new format inside pySED2Translate.  It is a separate package in the
same repository (`pbg/`, distribution `pysed2translate-pbg`), with one module that touches the host
(`host.py`), versioned *engines* side by side (`engines/v1`, a future `engines/v2`), engine-agnostic acceptance tests, and
a written kill list; nothing existing is edited.  Section 3.11 has the rules, the checks and the removal procedure.

**Recommendation.**

1. Add a second output format, written by a new command `pysed2translate-pbg` (not a flag on the existing one, section
   3.11): `pysed2translate-pbg translate X.sed2.json` writes `NNNNN.pbg.composite.json`.  `--backend` keeps its meaning
   (which simulator does the work).
2. Map the SED2 task graph, task for task: every SED2 task becomes a **Step** node, every task output becomes a
   **store**, and every `#tasks:...` / `#constants:...` reference becomes a **wire**.  Process-bigraph then orders
   the tasks from the wires, which matches how SED2 tasks depend on each other through references.  (Tested: chains
   and a diamond.)
3. Ship the Step classes in engine `v1` of that package (`pysed2translate_pbg.engines.v1`).  Where no wrapper can do the
   job they call the **existing** `pysed2translate.runtime` (AnnotatedData, SbmlModel, the three backends, the writers)
   through `host.py`.  The new
   target is then a second front end over the same runtime, so it must give the same numbers as the Python scripts, and the
   sed2-test-suite acceptance rule (|a-e| <= abs + rel*|e|) applies unchanged.
4. **Use the community wrappers (viva-tellurium, viva-copasi) when possible**, and own steps over the host's `runtime` as
   the fallback (section 3.12).  Every wrapper gap that stops a SED2 setting from being passed (no tolerance, no start
   time, no model input, no OpenCOR wrapper) is recorded in a ledger (W-1 to W-10) and **drafted** as an issue text for
   the wrapper maintainers (`pbg/upstream/`).  I never file anything; you report them.  Confirmed by running: viva-tellurium's UTC
   step accepts tolerances and a seed and ignores them (W-1); viva-copasi cannot start at a time other than 0 (W-2), cannot
   choose a method or tolerances (W-3), cannot take SBML text (W-4); both UTC steps continue from their previous end state when
   fired twice (W-10).  Mode `--wrappers strict|prefer|off`, **default `strict`** (your answer).
5. Translate **Loop in the clock form** (default): the loop's sub-tasks become steps of an *inner* composite, a
   generic `SedClock` **process** ticks once per iteration and publishes the range value, the index and the loop
   variables, and the whole inner composite sits inside one outer Step so that tasks downstream of the loop fire once
   (section 3.8).  This is the form in which SED2's loop index *is* process-bigraph's clock, and it is the form of the
   cosimulation test case (section 5.1).  Scatter and ParameterScan keep the **nested-repeat** form (one Step that runs
   a copy of the inner document per iteration, as `SimulationStep` does).  Both tested.  What SED2 cannot say about the
   clock is collected in `process-bigraph-clock.md`.
6. **FBA is a backend of the host** (your answer), with **per-kind backend selection** because two FBA tools and combinations
   such as COPASI with COBRApy are wanted: `--backend roadrunner --backend fba=cobra`, `suite --matrix ode=roadrunner,copasi
   --matrix fba=cobra:glpk,cobra:scipy` (section 3.14).
7. **Tier C is built now**, without waiting for the reverse direction: a small scheduler exporter turns a PBG document into a
   plain Python script (section 7, test tiers).  Prototype results: it reproduces process-bigraph exactly when the scheduling rule is
   read as the implementation does, and differs under the other reading when intervals are unequal.
8. Leave the "native" form (a SED2 time course as a `process` node that advances by `interval` and feeds an
   emitter) for a later, optional pass.  It is what makes a SED2 file *couple* with other bigraph processes, but it
   cannot express most of SED2 (section 3.9).

Sections: 2 what process-bigraph is, 3 the design (3.14: backends per task kind), 4 element-by-element mapping, 5 a worked example and the
cosimulation test case, 6 risks and gaps, 7 implementation plan, 8 questions for you.  Section 3.11 (modularity) governs
the rest.  Companion file:
`process-bigraph-clock.md` (where SED2 cannot express process-bigraph's clock, and proposed extensions).

## 2. Research: the Process Bigraph format

### 2.1 The two layers

process-bigraph is the execution layer.  bigraph-schema (a separate package) owns types and documents "at rest".
Everything a translator emits is a document; everything it relies on at run time is process-bigraph.  The
architecture notes in the repository (`docs/architecture.md`) add things this project does not need: content-addressed
artifacts, the `git:` address protocol, templates with holes ("sites"), Nextflow export, and distributed runtimes.

### 2.2 The document

A document is a dict (JSON-able).  The keys the `Composite` class reads (`Composite.config_schema`):

| Key | Meaning |
|---|---|
| `state` | The tree.  Required in practice. |
| `schema` | Optional type declarations for parts of the tree. |
| `bridge` | Optional `{inputs, outputs}` wires, used when a composite is itself a node of a bigger one. |
| `global_time_precision` | Optional number of decimals for the clock. |
| `run_steps_on_init` | Optional; run the ready steps while the composite is being built. |
| others | `parallel_steps`, `parallel_processes`, `parallel_workers`, `contract_strict`, `skip_process_state`, `interface`. |

Other top-level keys (tested with `name`, `description`, `requires` and `sed2`) do not raise; `sed2` was not copied
into the state.  The repository's own convention for a stored composite is a file called `*.composite.json` (or `.yaml`) with
`name`, `description`, `requires`, `parameters` (for `${name}` placeholders) and `state`.

### 2.3 Nodes

* A **store** is any value in `state`: a number, string, list, or a nested dict of stores.
* A **step** is a dict `{"_type": "step", "address", "config", "inputs", "outputs"}`.  It has no time; it runs when
  the data it reads is ready.
* A **process** is the same plus `"interval"`.  It advances state by `interval` each time it is scheduled.
* **Addresses.**  `local:Name` looks the class up in the core's link registry (filled by `allocate_core()` from the
  installed packages, or by `core.register_link`).  `local:!package.module.Class` imports the class by dotted path;
  this works from a plain JSON file (tested) and needs no registry, so it is the better choice for generated
  documents.  `git:owner/repo@ref#module:callable` runs pinned remote code (not needed here).
* Keys that start with `_` are schema keys, not store names.  `global_time` is a reserved store holding the clock.

### 2.4 Wires

`inputs` and `outputs` map a **port name** to a **path**: a list of keys from the container that holds the node
(`["constants", "tol"]`).  A port may also map to a nested dict of paths.  Reading a path gives the step its input;
what the step returns is merged into the output path.  The step network is built from these paths: if step B reads a
path that step A writes, B runs after A.  Nothing else connects nodes.

### 2.5 Types and updates

Port types are strings from bigraph-schema: `float`, `integer`, `string`, `boolean`, `list[float]`, `map[float]`,
`node` (anything), `maybe[T]`, `overwrite[T]` and others.  **The output port's type decides how a returned value is
merged**: a plain `float` output is *added* to the store (a delta), `overwrite[float]` replaces it, `map[float]`
merges per key.  This is why a process returns changes while a step usually returns `overwrite[...]` values.

Tested pitfalls:

* Arbitrary Python objects (numpy arrays, class instances) pass through a `node` / `overwrite[node]` port untouched.
* Two ports on the same store must have compatible wrappers.  An `overwrite[float]` output and a `maybe[float]` input
  on one path failed with `cannot resolve two different wrappings`.  Use `node` on both sides for data and model
  stores, and plain `float` for constants.

### 2.6 How a composite runs

* **Steps** run in dependency order.  A step is triggered when any input path is updated (`Step.triggers()`
  defaults to all inputs).  Tested: `Composite(doc).run(0.0)` ran a two-step chain once in order, and a four-step
  diamond (a -> b, c -> d) once each with the right values.  A later `run(1.0)` did not run them again.
* **Processes** are scheduled by `interval`; `Composite.run(T)` advances the clock to `T`.  Tested: a process with
  `interval` 0.25 run for 1.0 gave 5 emitter rows (t = 0, 0.25, ..., 1.0), matching the analytic solution.
* **Emitters** are steps that read some paths and record them.  `RAMEmitter` keeps a list of dicts, one per tick,
  starting at t = 0 (tested); `emitter.query()` returns it.  Others (console, JSON, SQLite, Parquet) share the API.
  They record rows of values with no labels; n-dimensional labelled arrays are not their job.

### 2.7 Running a document

```python
from process_bigraph import Composite, allocate_core
composite = Composite(json.load(open("doc.composite.json")), core=allocate_core())
composite.run(0.0)          # 0.0 is enough for a document that is only steps
```

or from the shell (tested, `--steps 0`):

```
python -m process_bigraph.run_composite --document doc.composite.json --steps 0 [--state-out out.json]
```

Constructing a `Composite` already checks part of the document before anything runs: a type clash between ports raised
at construction (tested, section 2.5).  I did not test what a misspelt address or a wire to a missing path does.
`--state-out` is documented as best effort.

### 2.8 What exists around it

* **viva-tellurium** (formerly pbg-tellurium): `TelluriumProcess` (a process that advances a RoadRunner model by
  `interval`), `TelluriumUTCStep` (one-shot time course), `TelluriumSteadyStateStep`.
* **viva-copasi** (formerly pbg-copasi): `CopasiUTCStep`, `CopasiUTCProcess`, `CopasiSteadyStateStep`,
  `ParameterEstimationStep`, built on basico.
* I found **no OpenCOR / CellML wrapper** and **no existing SED-ML or SED2 to process-bigraph translator**.
  (A web search turned up none; this is absence of evidence, not proof.)
* Why they do not fit SED2, from reading their source:
  * `CopasiUTCStep` always starts at time 0 and has no tolerance, integrator or step-size settings.
  * `TelluriumUTCStep` inherits `absolute_tolerance` / `relative_tolerance` in its config but, as read, never applies
    them to the integrator (only `TelluriumProcess` does).  The suite requires tolerances to be set explicitly on
    every backend (build.md).  **Confirmed by running on 2026-10-09** (tellurium 2.2.13.1): requested 1e-3 / 1e-2, the
    integrator had 1e-12 / 1e-6; a Gillespie `seed` is ignored too.  Ledger item W-1 in 3.12.
  * Neither returns labelled tables, a Jacobian, or SED2's `.model` end state.
  * They would give a different code path from the scripts, so a disagreement could come from the wrapper instead of
    the simulator.  The plan now accepts that (section 3.12): a disagreement is a finding about the wrapper, reported
    upstream, and the `runtime` provider remains the reference.
  * All three packages are on PyPI (viva-tellurium 0.1.2, viva-copasi 0.1.2, viva-superpowers 0.23.0).
* The README and tutorial 3 advertise `MathExpressionStep`, but there is no such module in the 1.8.5 checkout
  (`grep` finds only the README line).  This plan does not use it.  It would be a small upstream documentation issue.

### 2.9 What was tested

All in a throw-away venv with process-bigraph 1.8.5 from a clone of the repository, on Python 3.13.16.

| Check | Result |
|---|---|
| Steps wired through `local:!module.Class`, loaded from a JSON file, `run(0.0)` | Run once, in dependency order |
| Diamond dependency (4 steps) | Each ran once, correct order and values |
| Process + RAMEmitter, `interval` 0.25, `run(1.0)` | 5 rows from t = 0; equals the analytic solution |
| numpy arrays and class instances through `overwrite[node]` | Unchanged |
| A step whose config holds a nested document (`quote` type) and runs an inner `Composite` per value of a list | Works; inner results equal the analytic values |
| Extra top-level keys (`name`, `description`, `requires`, `sed2`) | Accepted |
| `python -m process_bigraph.run_composite --document ... --steps 0` | Runs |
| numpy pinned to 2.2.6 (roadrunner needs `numpy~=2.2`) | process-bigraph and bigraph-schema import and pass the above; `pip check` clean |
| The example document in section 5, with stub steps | Loads and runs |
| Loop as a clock process in the *same* composite as a downstream task (`run(3.0)`, 3 iterations) | The downstream task fired on **every tick** (4 times, counting t = 0), not once |
| The same loop inside a host Step that runs the inner composite and returns only the final result | Downstream task fired **once**, with the last iteration's value |
| Clock process carrying a loop variable (previous iteration's output fed back as the next iteration's input), 3 iterations | Iteration k is visible at tick k + 1; the t = 0 row is a dummy and is dropped |
| Clock loop whose loop variable and sub-task outputs are Python objects (a stand-in for the cosimulation chain ODE -> FBA -> model change) | Correct values per iteration; objects pass through `overwrite[node]` stores |
| Inner steps whose inputs are only produced by the clock process | They **run once at the start of `run()` with default (empty) inputs**, even with `run_steps_on_init: false`.  Fix: every inner step gets an `index` input (initially -1) and returns `{}` while it is negative |
| A Scatter nested in a Loop, a Loop in a Loop (inner loop seeded from the outer loop variable) and a Scatter in a Scatter (`libsed2` validation only, no run) | 0 problems each |
| Two processes with the same `interval` sharing stores | Both read the state as it was at the start of the interval (Jacobi coupling); matches a hand-computed parallel update, not a sequential one |
| Two processes with intervals 1 and 2 | The slower one reads a stale snapshot and its update lands at the end of its longer interval |
| A cycle of steps | Not an error: broken silently by priority, giving arbitrary values.  Never emit one |
| viva-tellurium `TelluriumUTCStep` with `absolute_tolerance` 1e-3, `relative_tolerance` 1e-2, integrator gillespie, seed 5 | Integrator kept roadrunner's 1e-12 / 1e-6; Gillespie was selected, the seed was not applied (W-1).  `TelluriumProcess` applies the tolerances |
| viva-copasi `CopasiUTCStep` with `start_time` 2, `relative_tolerance` 1e-3, `method` stochastic, SBML text as `model_source` | The first three run and are ignored (W-2, W-3); SBML text is refused, only a path or URL is accepted (W-4) |
| Either UTC step fired twice | The second firing continues from the first one's end state (W-10); a Step that may fire more than once must not be stateful |
| Scheduler exporter prototype (`pbg/research/pbg2py.py`): two coupled processes, intervals 1 and 1, then 1 and 2 | Generated plain script, reading inputs at the start of each interval, matches process-bigraph exactly in both cases.  Reading inputs at the event time matches for equal intervals and differs for 1 and 2 (at t = 4: x 0.25 / y 0.25 against 0.15625 / 0.140625).  See upstream/P-3.md |
| Mock ODE (Monod, roadrunner) + FBA (toy overflow model, COBRApy) in a plain Python loop, 41 intervals | Glucose is consumed, acetate is secreted then re-used, biomass grows; behaves as designed (`pbg/tests/advanced/data/cosimulation/refloop.py`) |
| The same loop with the real iAF1260 model of CRM-FBA (2382 reactions) | 0.07 s per solve (41 solves in 3 s); growth 0.868 and acetate secretion 0.77 at the start; **once glucose is exhausted the FBA is infeasible** (maintenance requirement), see 3.13 and section 6 |

Not tested: real simulators inside Steps, large documents, `parallel_steps`, the command line plumbing, a loop that
carries a real SBML model through roadrunner / COPASI / OpenCOR.

### 2.10 What the paper and its two supplements add

Read 2026-10-09: Agmon and Spangler, arXiv:2512.23754v2 (main text), Supplement 1 (formal framework) and Supplement 2
(Spatio-Flux).  Points that bear on this plan:

1. **The task-document-as-a-Step architecture is the intended pattern.**  S1 3.8.4: with `interval = 0` "scheduling
   reduces to a directed acyclic graph evaluation over these step nodes", and "an entire composite simulation can itself
   appear as a single step in a larger DAG", with parameter estimation and analysis as the examples.  The main text
   (section 3.2) says SBML and CellML models "can be executed through infrastructure such as BioSimulators following
   SED-ML workflows, while remaining coupled to other processes".  Mapping a SED2 task graph to a step DAG is therefore
   the framework's own reading of a workflow, and the "native" form (3.9) is the authors' stated direction for coupling.
2. **Equal-interval processes in parallel is by design.**  S1 3.8.2: all processes due at the same event time are updated
   "conceptually in parallel when their deltas commute"; S1 3.8.3 adds *reconcilers*: deltas to one store are combined,
   reconciled (a type-specific rule, for structural edits a canonical order) and applied.  The Jacobi behaviour measured in
   2.9 is therefore specified behaviour, not an accident (see `process-bigraph-clock.md`, G2).
3. **A difference between the formal rule and the implementation, for unequal intervals.**  The small-step rule reads a
   process's inputs at the event time `t*` at which it is due.  The implementation (tested, 2.9) reads them at the *start*
   of the process's interval and applies the result at its end.  With equal intervals both agree; with intervals 1 and 2
   they give different numbers.  I could not tell from the text which one the authors mean (S1 3.8.6 says the engine
   "stashes" each delta "together with the simulated time reached by the process", which fits the implementation).  This
   plan only depends on the equal-interval and step cases; it is a question for upstream before anything is built on
   multi-rate behaviour.
4. **Cycles.**  S1 3.8.4 says cycles of steps "are disallowed"; 1.8.5 breaks them silently by priority (tested, 2.9).  The
   plan's rule "the translator proves the step graph acyclic" stands, and it is a possible upstream note.
5. **Serialization.**  S1 3.2 shows the canonical JSON with `schema` and `state` trees and `stores` / `processes`
   sub-trees, and says JSON and a linearized one-line syntax parse to the same composite, losslessly.  The documents the
   1.8.5 package loads in 2.9 are different in shape (one `state` tree whose process and step nodes carry `_type`).  I did
   not test whether 1.8.5 also accepts the supplement's layout.  For this plan (emit what 1.8.5 loads, tested) it does not
   matter; for the reverse direction it does (a corpus may hold both shapes).
6. **An FBA wrapper exists and has a published interface.**  S2 1.2.1: Spatio-Flux `DynamicFBA` uses COBRApy (GLPK by
   default) and is configured with `model file`, `kinetic params` (Km, Vmax per substrate, giving uptake bounds by
   Michaelis-Menten kinetics), `substrate update reactions` (substrate id -> exchange reaction id) and `bounds`.  That is
   what the cosimulation test case (5.1) leaves unspecified: the id mapping and the rate law between the ODE state and the
   FBA bounds.  In process-bigraph the mapping is a config of the FBA process; in SED2 it would have to be explicit
   Calculation and ModelChange tasks.  It also makes COBRApy the natural FBA backend for pySED2Translate (section 3.13) and
   gives the survey in `process-bigraph-to-sed2.md` a concrete corpus (the Spatio-Flux repository and its composites).
7. **Modularity is also what the authors stress.**  Documents run unchanged under local, multiprocessing, Ray and REST
   protocols (S1 3.10; S2 2.1, four execution modes), which supports keeping every engine behind a two-function interface
   (3.11).

## 3. Design

### 3.1 Constraints from build.md and CLAUDE.md

* The output depends only on the document, the backend and the options.  No timestamps, no versions, no absolute
  paths unless given.  Two runs give identical text.
* A backend that cannot do a task is a **refusal with a reason, exit status 11**, from the same capability table.
  The PBG target must not get its own table; it asks `capabilities.json` exactly as the script target does.
* No workarounds for simulator, libsed2 or specification gaps.  Anything process-bigraph cannot express is refused
  or deferred and written down (section 6), not patched around.
* ASCII only in files.  Do not commit.
* **Nothing is filed upstream by the assistant** (your rule, 2026-10-09).  A wrapper gap, a framework question or a simulator
  disagreement becomes a drafted file (`pbg/upstream/` for other projects' trackers; `pbg/findings/` for this project's own
  `disagreements.json` and SED2/TODO.md entries), and you decide whether and where to report it.

### 3.2 Command line and files

```
pysed2translate-pbg translate 00001.sed2.json --backend roadrunner -o 00001.pbg.composite.json
pysed2translate-pbg translate 00002.sed2.json --backend copasi --backend fba=cobra:glpk       # per-kind backends, see 3.14
pysed2translate-pbg run 00001.pbg.composite.json --input-dir . --output-dir results/    # see 3.10
pysed2translate-pbg engines                                                              # lists the engines found
pysed2translate-pbg translate ... --engine v1 --loop-form nested --wrappers strict        # engine and engine options
```

The existing `pysed2translate` command is not touched, so nothing changes for existing users (section 3.11).  The file
name is `NNNNN.pbg.composite.json`: it ends in the framework's own `*.composite.json`, which its discovery globs
(`*.composite.json`, checked in `composite_discovery.py`) match with any prefix, and `.pbg.` says where it came from, so it
sits beside `NNNNN.sed2.json` in a suite directory without confusion.  (The framework derives the document name from the
stem, `NNNNN.pbg`, which is harmless; the `name` key is written explicitly anyway.)  Exit statuses 0, 2, 10, 11, 12 keep their meaning.
`--loop-form {clock,nested}` (default `clock`) is an option of engine `v1`, not of the command: it chooses how a Loop is
written (section 3.8).  `--backend` is repeatable and takes `name` or `kind=name[:variant]` (section 3.14).

### 3.3 Layout of the generated document

```
{
  "name": "<prefix>",
  "description": "Translated from <source> by pysed2translate",
  "sed2": {"version": "v1.0.0", "source": "<file>", "backend": "<backend>", "engine": "v1", "engineVersion": "<x.y>"},
  "state": {
    "constants": { "<id>": <JSON value>, ... },
    "context":   { "inputDir": ".", "outputDir": "results", "prefix": "<prefix>" },   // 3.10
    "tasks":     { "<id>": { "data": {}, "model": {}, "strings": {} }, ... },   // only the outputs a task has
    "task_<id>":   { step node },
    "output_<id>": { step node }
  }
}
```

* `constants` holds the SED2 constants as JSON.  A constant that refers to another constant is refused, as it is now
  (docs/deferred.md).
* `tasks.<id>.data / .model / .strings` are the stores for `#tasks:id`, `#tasks:id.model`, `#tasks:id.strings`.
* Step nodes sit at the top level, so wire paths start at the top.  Their keys are `task_<id>` and `output_<id>`.  The
  prefixes cannot collide with each other or with `constants` / `tasks`.  Keys must not start with `_` and must not be
  `global_time`; the translator checks every id and refuses if an id cannot be used (the id syntax comes from the SED2
  specification, which I could not read from this session).
* Document order of the SED2 file is kept for readability; execution order comes from the wires.
* No `emitter` nodes in the default document (see 3.6).

### 3.4 What flows through the stores

Values are the runtime's own objects, carried in `node` ports (tested): `AnnotatedData` for `#tasks:id`, `SbmlModel`
for `.model`, a list for `.strings`.  Consequences:

* Initial state contains only JSON (constants).  Everything else is created while the steps run.
* The state at the end is not JSON-serializable, so `--state-out` is not a useful output.  Results leave through
  report and plot files (3.6), exactly as in the script contract.
* Steps pass models by reference (an `SbmlModel` is immutable: `with_values`, `without` and `with_state` return new
  objects).  This is what `ModelChange` and `.model` of a simulation already rely on.

### 3.5 References become wires; accessors become config

| SED2 reference | Wire (input port reads) | Where the rest goes |
|---|---|---|
| `#constants:c` | `["constants", "c"]` | accessors in config |
| `#tasks:t` | `["tasks", "t", "data"]` | accessors in config |
| `#tasks:t.model` | `["tasks", "t", "model"]` | none |
| `#tasks:t.strings` | `["tasks", "t", "strings"]` | none |
| `#tasks:t[0:5, 'S1']` | as `#tasks:t` | `index` in config, built from `libsed2.parse_reference` |

A step gets one input port per distinct reference it uses (`r0`, `r1`, ...), and a `refs` map in its config says which
port is which reference and which accessors to apply.  Every dependency is therefore a wire, so the scheduler sees all
of them.  `index` uses the same bracket groups that `core.index_literal` produces for scripts, written as JSON.

Attributes that can be a literal or a reference ("OrRef", for example `relativeTolerance: "#constants:tol"`) are
config values when literal and input ports when they are references.

### 3.6 Math

`Calculation.math` is parsed at translation time with `libsed2.parse_math` and written into the config as a small JSON
tree (`{"op": "add", "args": [...]}`, `{"ref": "r0"}`, `{"num": 2}`), plus the original text for readers.  At run time
the step evaluates the tree with `pysed2translate.runtime.mathfn`, the same functions the scripts call.  Two reasons
for a tree over the raw string: the document is self-contained and the runtime keeps not needing libsed2 (as the
script contract promises), and the tree has already been checked for syntax by the translator.

### 3.7 Reports and plots

* `Report` -> `output_<id>`: a step whose input is the report's data and whose job is to write
  `<prefix>.<id>.csv` (or `.h5` for 3 or more dimensions) using `runtime.writers.write_report`.  It has no output
  port.  The files are therefore byte-identical to what the script target writes, and the suite's comparator needs no
  change.
* Why not only an emitter: `RAMEmitter` and the others record one row of unlabelled values per tick.  A SED2 report is
  one labelled n-dimensional array, with the label and format rules of the suite.  An emitter cannot be the primary
  path.
* Optional: `--emit-ram` adds a `RAMEmitter` wired to the same data so that a Python caller can read results from
  `composite.state["emitter"]["instance"].query()`.  Not needed for the suite.
* `Plot2D` / `Plot3D` -> `output_<id>` steps that write the `_as_data` files and, when matplotlib is present, the PNG,
  via the existing `runtime.plots`.

### 3.8 Repeats: Loop (clock form), Scatter, ParameterScan

**Loop - the clock form (default).**  A SED2 Loop is a chain of iterations over a range, each reading the previous one
through `loopVariables`.  That is a clock: one tick per iteration, state carried from tick to tick.  The translation
keeps that shape.

`task_<id>` is a Step, `SedLoop`, whose `config.document` is an **inner composite** (a complete document with its own
stores) and whose `config.ticks` is the number of iterations.  Inside the inner document:

* one **process** node, `clock`, of class `SedClock`, with `interval` 1.0.  Its config holds the range (the explicit
  values, or the start/end/steps/scale/log description when they are known at translation time) and, per loop variable,
  which store holds the initial value and which holds the subsequent value.  Its ports are generic:
  outputs `range` (the current range value), `index` (the iteration number), one output store per loop variable;
  inputs the initial-value and subsequent-value stores.  At tick k it writes `range[k]`, `k`, and each loop variable
  (the initial value when k = 0, otherwise the subsequent value left by iteration k - 1);
* one **step** per sub-task, named `subtask_<id>`, wired exactly as the outer tasks are (references -> wires).  The
  references `#tasks:<loop>.range`, `.index`, `#tasks:<loop>:loopVariables:<name>` are wires to the clock's output
  stores.  Sub-task outputs are stores inside the inner document;
* the `outputVariableMap` entries are collected by a RAM emitter wired to the stores they name.

The outer Step ports are the **free references**: anything a sub-task reads from outside the loop (`#tasks:m.model`,
`#constants:ode_interval`, the initial values of loop variables) becomes an input port of `task_<id>`, so the outer
scheduler still orders the loop after those tasks.  Its output ports are the loop's results (`.data` assembled with
`runtime.ops.repeat_table`, `.aggregates`, the final loop variables).

Why the inner document is hosted by a Step and not left flat in the outer one (tested, section 2.9):

* in a flat document every task downstream of the clock re-fires on every tick, which breaks "the loop finishes, then the
  next task runs once".  Hosting the clock in a Step makes the whole loop one node of the outer graph, which is the
  framework's own rule ("a simulation is one node of its outer graph", `SimulationStep`, `RunProcess`);
* a clock in the outer document would also advance global time, which would then run any other process of the document.

Rules the translator must follow (each cost a failed experiment):

1. **Offset.**  Iteration k becomes visible at tick k + 1 (a process update lands at the end of its interval).  Run the
   inner composite for `ticks` time units and drop the emitter's t = 0 row.
2. **Init guard.**  All inner steps fire once at the start of `run()` with default inputs, even with
   `run_steps_on_init: false`.  The `index` store starts at -1; every inner step has an `index` input and returns `{}`
   while it is negative.  The step base class `SedStep` does this once.
3. **Object stores.**  Stores that hold models or data are typed `overwrite[node]` through the document's `schema` key and
   are not pre-filled with `null`; the initial model enters through the outer Step's input port and is placed in the
   inner state by the host before the run.
4. **One tick, one iteration.**  Steps inside the iteration run in dependency order within the tick, so the order
   SED2's references give is preserved: chained sub-tasks run in sequence, and sub-tasks that do not reference each other
   are independent (they may share a dependency layer and could run concurrently; not exercised).  Any task may be a
   sub-task, including a Scatter or another Loop (SED2 allows any task inside a Loop or a Scatter; a Scatter nested in a
   Loop, a Loop in a Loop and a Scatter in a Scatter were each checked with libsed2: 0 problems): a nested Scatter becomes a `SedRepeat` step
   inside the inner composite, a nested Loop becomes another `SedLoop` step with its own inner composite, recursively.
   The only *processes* in an inner document are the clocks; SED2's parallel branches are steps, not coupled processes,
   so the coupling semantics stay those of SED2 (see `process-bigraph-clock.md`, G2).
5. **Number of iterations.**  `numericRange` with only `numberOfSteps` has numberOfSteps + 1 entries; the translator
   uses the length of the evaluated range, not `numberOfSteps`.  A range computed at run time is evaluated by the host
   Step before it builds the inner document, which is why the clock takes its values from config at run time.

Cost: one inner `Composite` build per Loop, not per iteration.  The nested-repeat form below rebuilds one per iteration.

**Scatter and ParameterScan - nested repeat.**  Their iterations are independent, so there is no state to carry and no
clock.  `task_<id>` is a Step, `SedRepeat`, with `config.document` (the sub-task graph as a nested document) and the same
free-reference input ports.  At run time, per iteration, it copies the document, fills the inner `constants` with the
iteration values (`.range`, `.index`, `.ranges[...]`, `.indexes[...]`, `.model` of a ParameterScan), builds an inner
`Composite`, runs it with `run(0.0)`, and collects the `outputVariableMap` entries.  Assembling the result table
(`scan_table`) and the labels reuse `runtime.ops`.  `SedRepeat` can later run its iterations in parallel (they share
nothing).  A flag `--loop-form nested` makes Loop use `SedRepeat` too (per-iteration `run(0.0)`, loop variables
copied by the host); it exists for comparison and as a fallback, and must give the same numbers.

Rejected alternatives:

* Unrolling the iterations into separate nodes: the number of iterations may come from a reference computed at run time.
* A flat clock in the outer document: downstream tasks fire every tick (tested).
* The framework's `_cardinality: 'per_match'` scatter ports (a step that loops its `update()` over a match set): they
  could serve Scatter, but not a Loop (each iteration reads the previous one) or a ParameterScan's multi-dimensional
  result.

### 3.9 Backends, capabilities, and the "native process" form

* Every simulation node is produced by a provider (3.12): a community wrapper when it can take the task, otherwise our own
  step, which calls the same `runtime.backends.*` classes as the scripts.  Tolerances and solver settings are set
  explicitly in the `runtime` provider, as now; in the `viva` provider they are passed through only if the wrapper accepts
  them, and a wrapper that cannot is a ledger entry.
* `capabilities.json` is consulted at translation time (`check_document`), and the runtime can still raise
  `BackendCannotRun` for run-time findings; the runner turns both into exit status 11 and the line
  `skip: <backend> cannot run the model: <reason>`.  `--wrappers strict` adds the wrapper ledger ids to the reasons.  The table
  is keyed by task class and backend, so the per-kind selection of 3.14 needs no new table, only a grouping of task classes into kinds.
* A **native** form would turn an explicit uniform ODE time course into a `process` node with
  `interval = (end - start) / numberOfSteps`, run for `end - start`, and an emitter.  It would let a SED2 model be
  wired to other bigraph processes.  It cannot represent: bounded simulations (non-uniform output points), a start time
  other than 0 (the clock starts at 0), steady states, Jacobians, and anything after a `ModelChange`.  (Repeats are
  not part of the native form: the clock of a Loop, section 3.8, counts iterations inside a Step and is unrelated to
  the simulated time of the document.  Putting the *simulation* clock and the *loop* clock on one timeline is the
  open question analysed in `process-bigraph-clock.md`.)
  This is a separate engine (3.11), not a mode of `v1`, and it is where `TelluriumProcess` and `CopasiUTCProcess` are the
  natural building blocks.  It stays optional (phase 5).

### 3.10 Running a generated document

Needs the `pysed2translate-pbg` package (its own dependencies: `process-bigraph==1.8.5`, `bigraph-schema==1.7.0`, and,
for the `viva` provider, the wrappers) and the simulator.  `process_bigraph.run_composite` can run the file; a small
runner in engine `v1` adds what that command does not know: exit status 11 and the manifest.  It builds a
`Context(input_dir, output_dir, prefix)` from `runtime/context.py` (through `host.py`), calls `Composite(doc).run(0.0)`,
writes the manifest, and exits 0, 1 or 11 as the script contract says.

**Input and output directories live in the document, with defaults (your answer to question 4).**  The document has a
`context` store, `{"inputDir": ".", "outputDir": "results", "prefix": "<NNNNN>"}`, and every step that reads or writes a file
has an input port wired to `["context"]`, so the document is complete on its own: `python -m process_bigraph.run_composite
--document X.pbg.composite.json` works from the right directory.  `--input-dir` / `--output-dir` of the runner overwrite those
values in the loaded state before the run (they are the same as the script's flags).  Consequences, each handled once in
the step base class `SedStep`: (a) the paths are relative to the current directory unless absolute, as the script's are;
(b) a Step builds its `Context` object from the store value when it fires, so nothing is held in module state; (c) a
Loop host copies the `context` store into the inner composite, and a nested repeat does the same; (d) the translator never
writes an absolute path of the translating machine.  Exit status 11 and the manifest still need the runner; running the
document with the framework's own command gives exit status 1 on a refused task, with the same message.

### 3.11 Modularity: built to be thrown away

**Requirement (from you).**  The whole translation must be modular enough that discarding it and starting over is
easy.  Everything in this plan is therefore subordinate to one test: *can the PBG work be deleted, or replaced by a
second attempt, without touching pySED2Translate's existing code and without losing what was learned?*  The answers
below are design rules, each with a mechanical check, so that the property does not erode while the code grows.

**Shape: a separate package in the same repository, with one seam to the host.**

```
pbg/                                   # its own distribution: "pysed2translate-pbg"; the ONLY new top-level folder
  pyproject.toml                       # own dependencies (process-bigraph, bigraph-schema), own entry points
  requirements-lock.txt                # its own pins; the host's lock file is not edited
  README.md                            # what it is, how to remove it (the kill list, below)
  NOTES.md                             # lessons that survive a rewrite (the rules in 3.8, pitfalls in 2.5, 2.9)
  research/                            # the scratch experiments as runnable scripts, with their expected output
  src/pysed2translate_pbg/
    __init__.py
    host.py                            # the ONLY module that imports pysed2translate (the seam)
    cli.py                             # `pysed2translate-pbg`: translate / run / engines; picks an engine by name
    engines/
      __init__.py                      # discovers engines by scanning this folder; no registration lines
      v1/                              # the engine of this plan: document.py steps.py loop.py runner.py
      v2/                              # a restart would begin here, beside v1, never inside it
  tests/
    contract/                          # engine-agnostic: runs EVERY engine through translate -> run -> compare
    v1/                                # tests of v1 internals and v1's golden documents; deleted with v1
```

Nothing is added to `src/pysed2translate/` or the host's `pyproject.toml`; the only host change is the one small M1 test below (approved).
Installing the target is `pip install -e ./pbg`; uninstalling it is `pip uninstall pysed2translate-pbg`.

**Rules, and how each is checked.**

| # | Rule | Check |
|---|---|---|
| M1 | The host never imports the target.  No `if fmt == "process-bigraph"` anywhere in `src/pysed2translate/`. | Host test (one small file, approved by you): scan `src/` for the target's package name and for the string `process_bigraph`; fail on a hit. |
| M2 | Only `host.py` imports the host.  It re-exports the handful of host functions the engines use (the seams below) under stable names; if the host changes, one file changes. | Target test: AST scan of `src/pysed2translate_pbg/`; any `pysed2translate` import outside `host.py` fails. |
| M3 | Engines are independent.  `engines/v1` never imports `engines/v2` or the reverse.  Code needed by two engines moves to `host.py` or a new `common.py` only when a *second* engine actually needs it (rule of two); until then each engine copies. | Target test: AST scan across engine folders. |
| M4 | An engine is a folder with a fixed small interface (below).  Adding one is adding a folder; removing one is deleting a folder; no list to edit. | Test: engine discovery finds exactly the folders present; a test deletes `engines/v1` in a temp copy and checks `pysed2translate-pbg engines` still runs. |
| M5 | The acceptance tests do not know any engine's internals.  They call only the interface (`translate`, `run`) and compare results with the suite's canonical data.  Internals (golden documents, step tests) live under `tests/<engine>/` and are deleted with it. | `tests/contract/` imports nothing from `engines.*` except through the discovery function. |
| M6 | Generated documents say which engine made them (`sed2.engine`, `sed2.engineVersion`), and step addresses contain the engine folder name (`local:!pysed2translate_pbg.engines.v1.steps.SedOdeSimulation`).  Two engines' documents can coexist in one directory and in one process. | Test: every golden document has both keys and every address starts with its engine's module path. |
| M7 | No change to the host `runtime/` for the target's sake.  If an engine needs a function that does not exist, it is first tried as a wrapper in `host.py`; only a function that is useful to the Python-script path as well is proposed to the host as its own change. | Review rule; recorded in `NOTES.md` when it happens. |
| M8 | The target's dependencies are the target's.  `process-bigraph` and `bigraph-schema` appear only in `pbg/pyproject.toml`; the host's `requirements-lock.txt` is untouched.  A test environment without them still runs the whole host suite. | CI job, on **as many platforms as possible** (your answer 5): Linux, Windows and macOS, x86_64 and arm64 where runners exist, Python 3.13: install the host alone and run its tests; then install `./pbg` and run `pbg/tests`, once with `--wrappers off`, once with the wrappers installed. |
| M9 | One default, in one place.  `DEFAULT_ENGINE = "v1"` in `cli.py`, overridable by `--engine` or `PYSED2TRANSLATE_PBG_ENGINE`. | Contract tests run all engines regardless of the default. |

**The interface of an engine** (a module or class in the engine folder named in `engines/__init__.py` by convention, not by
a registry): a `NAME`, a list of the options it adds (for example v1's `--loop-form`), and two functions.

```
translate(document, options) -> TranslationResult   # {file name: text} for every file written, plus a manifest of the
                                                   # tasks it could and could not translate (reasons included)
run(translated_dir, input_dir, output_dir) -> int   # 0, 1 or 11, with the script contract's skip line for 11
```

Two functions are all `tests/contract/` needs.  `document` is the host's validated document object (from
`host.load_document`), so an engine never parses SED2 itself.

**The seams to the host** (what `host.py` re-exports; each name is checked against the host in phase 0, and `host.py`
is the place to fix if a name has changed):

* `load_document(path)`: the validated libsed2 document (host: `translate.load_document`);
* `check_document(backend, document)`: the capability-table check (host: `capabilities.load_table().check_document`);
* the error classes (host: `errors`);
* the runtime classes the steps call (host: `runtime.*`: AnnotatedData, SbmlModel, the backends, the writers, `Context`);
* the suite locating and comparison helpers used only by `tests/contract/` (host: parts of `suite_runner`); some of those
  are script-specific (`run_script`), so the contract tests carry their own small runner and reuse only the suite
  location and the canonical-data comparison.

What is deliberately **not** shared: the host's code generator (`core.Translator`, the `tasks*.py` handlers, `codegen`),
because it emits Python lines and a PBG engine has no use for it; the mapping is rebuilt per element in the engine.  That
duplication is the price of independence, and it is small (the mapping table in section 4 is the list).

**The kill list** (goes into `pbg/README.md`, and is the whole procedure for removing the target):

1. `pip uninstall pysed2translate-pbg`;
2. delete the `pbg/` folder;
3. delete `process-bigraph*.md` if the notes are no longer wanted.  `pbg/NOTES.md` and `pbg/research/` are the part worth
   keeping: they hold the experiments and rules that cost effort (init guard, offsets, object stores, silent cycle
   breaking, flat-versus-hosted clock).

No line elsewhere changes.  **Restarting** is: add `pbg/src/pysed2translate_pbg/engines/v2/`, implement the two
functions, run `pbg/tests/contract/` against it (it picks up the folder automatically), and delete `v1/` and `tests/v1/`
when `v2` passes.  v1 and v2 can be compared head to head with the cross-check, because the contract tests give both the
same inputs and expectations.

**What this costs.**  A second `pyproject.toml` and install step; `host.py` is a thin layer that must be kept in step
with the host; some code is copied between engines instead of shared; no `--format` flag on the host's own command (it
could be added later as a ~15-line shim that, if `pysed2translate_pbg` is importable, forwards to it; the shim would be the
only host change and would be removable on its own, but nothing needs it).  The alternative, a subpackage
`pysed2translate.pbg` selected by a `--format` flag, is simpler to install but makes the host import-aware of the target
and puts three kinds of file (code, tests, goldens) in three host folders; its removal is a longer list.  This plan takes
the separate package.

**Where the other decisions of this plan sit under the rule.**  The native-process form (3.9) is a different engine
(`v2`-style, or `native`), not a flag of `v1`.  The reverse direction (`process-bigraph-to-sed2.md`) is a different
package again, as you said; the only thing it may share with this one is the mapping table, and that sharing stays a
document (section 4) until a second implementation actually needs code.  The viva-wrapper approach (section 2.8), if you
ever want it, is another engine with the same two functions.

### 3.12 Community wrappers first, own runtime as the fallback

**Decision (yours).**  Use the community wrappers (viva-tellurium, viva-copasi) when possible.  When a wrapper cannot take
a setting that SED2 needs, such as a tolerance, that is a bug or feature request for the wrapper maintainers, recorded and
submitted, and not something the translator quietly works around.  This reverses the first draft of this plan, which built
its own steps only (section 1, recommendation 4, is rewritten).  **Filing is yours:** every ledger entry is drafted as a text file
under `pbg/upstream/` and the assistant files nothing, anywhere, on its own.

**Providers.**  Inside engine `v1` (so the rule of 3.11 holds: nothing outside `pbg/` knows about this), every task that
runs a simulator is produced by a *provider*, selected by `--wrappers {strict,prefer,off}` (default `strict`):

| Provider | What it is | Used for |
|---|---|---|
| `viva` | A thin adapter over the community wrappers: builds the wrapper's step or process node from a SED2 task, and an adapter step that turns the wrapper's output into labelled `AnnotatedData` | Tasks whose every setting the wrapper can take (decided by a small capability table, below) |
| `runtime` | Our own steps over the host's `runtime` (the first draft of this plan) | OpenCOR (no wrapper exists), and any task a wrapper cannot take |

* `strict` (**default**, your answer 2026-10-09: "start with --strict"): use `viva` when its table says the wrapper can take the
  task; otherwise refuse the task (exit 11, with the ledger ids as the reason).  This is the mode that measures wrapper coverage
  and produces evidence for upstream reports.  Consequence: with the default, a document using a loop that carries a model, a
  start time other than 0 on COPASI, or any OpenCOR task is refused, so the way to translate it is to ask for the fallback.
* `prefer`: use `viva` when its table says the wrapper can take the task; otherwise use `runtime` and record the
  fallback and its ledger id (W-n, below) in the translation manifest and on stderr, so nothing is silent.
* `off`: `runtime` only.  This is the reference behaviour, and it must match the Python scripts bit for bit (same code).
* Results from `viva` are compared with the suite's canonical data at the suite's tolerance, not bit for bit with the
  scripts.  A disagreement is then a *finding* about the wrapper (or the simulator), recorded and reported, not a failed test
  of the translator.  Contract tests keep a list of expected gaps (by ledger id), and fail on an *unexpected* pass or an
  *unexpected* failure, so the list cannot rot.

**What limits wrapper use, from the structure of the wrappers (read), independent of any bug.**

* A wrapper step takes its model as a **config string or path**, fixed when the document is written.  SED2 models flow at
  run time (after a `ModelChange`, as a loop variable).  So the wrapper path covers the *static* pattern: `ModelImport` ->
  simulation -> report, with `ModelChange` folded into config only where the wrapper has overrides (viva-tellurium has
  `species_overrides` / `parameter_overrides`; viva-copasi does not).  Everything after a runtime model change, every Loop
  that carries a model, and steady-state / Jacobian tasks the wrappers do not offer, use `runtime`.  That is not a
  failure: it is the same fallback, with the ledger id W-6.
* A wrapper returns plain lists and maps, not SED2's labelled tables, so an adapter step per wrapper is part of the
  provider and is tested on its own.

**Gap ledger for the wrapper maintainers.**  Found by reading the source of viva-tellurium 0.1.2 and viva-copasi 0.1.2, and,
where marked, confirmed by running them (2026-10-09, tellurium 2.2.13.1 / roadrunner 2.10.0, basico 0.87):

| Id | Wrapper | Gap | SED2 need | Evidence |
|---|---|---|---|---|
| W-1 | viva-tellurium `TelluriumUTCStep`, `TelluriumSteadyStateStep` | `absolute_tolerance`, `relative_tolerance` and `seed` are accepted in the config (inherited schema) but never applied; the integrator keeps roadrunner's defaults.  `TelluriumProcess` does apply them. | The suite requires tolerances to be set explicitly on every backend | **Confirmed by running**: requested 1e-3 / 1e-2, integrator had 1e-12 / 1e-6; requested Gillespie with seed 5, got a random seed.  Bug. |
| W-2 | viva-copasi `CopasiUTCStep`, `CopasiUTCProcess` | Start time is hard-coded `start_time=0.0`; the config has only `time` and `n_points` / `intervals`. | SED2 time courses start anywhere (`start`, `independentVariableInit`) | **Confirmed by running** (`start_time` accepted, ignored) |
| W-3 | viva-copasi (all steps) | No method, tolerance or step-size settings; `run_time_course` is called with defaults.  Config is `model_source`, `time`, `n_points` only. | Algorithm by KiSAO id, tolerances, maximum steps | **Confirmed by running** (such keys accepted, ignored) |
| W-4 | viva-copasi | The model must be a file path or URL (`model_source`); no SBML text or in-memory model. | Models from `ModelImport` and from `ModelChange` | **Confirmed by running** (SBML text refused) |
| W-5 | both UTC steps | Only uniformly spaced output (`n_points`); no explicit time vector. | `BoundedODESimulation`, vector ranges, `independentVariableRange` with `values` | Source |
| W-6 | both | No end-state model output (SED2's `.model`), and no model *input* port, so a simulation cannot continue from a previous task's model.  (`TelluriumProcess.get_sbml()` exists as a method, not as a port.) | `OneStepODESimulation`, `ModelChange` chains, Loops carrying a model | Source |
| W-7 | both | Output selection is the wrapper's own: tellurium returns floating species only (default `simulate` columns); no selection of parameters, rates or other variables; copasi columns are SBML ids. | `outputVariables` of any model element | Source |
| W-8 | both | Steady state: no solver, tolerance or time-limit settings; no Jacobian step in either.  (COPASI's step is read, not run.) | `SteadyState`, `JacobianFull`, `JacobianReduced` | Source |
| W-9 | (no wrapper) | No OpenCOR / CellML wrapper exists. | The third backend of this project | Search (absence of evidence) |
| W-10 | both UTC steps | Not idempotent: a second firing continues from the first one's end state, and a process-bigraph Step can fire more than once. | A task's result must not depend on how often the scheduler fires it | **Confirmed by running** |

Four framework items found on the way (P-1 unknown config keys accepted silently, P-2 step cycles broken silently, P-3 which time
the longer-interval process reads the state at, P-4 `MathExpressionStep` documented but absent) are drafted the same way for the
process-bigraph maintainers.  All 14 drafts are in `pbg/upstream/` with an index (`README.md`) and the order I would suggest.
Each W-id is a short issue text under `pbg/upstream/` (title, minimal reproduction, expected behaviour, environment), **drafted,
not filed**; you report them.  W-1 is a plain bug and can go first, then W-10, P-1, W-2, W-3.  The ledger lives in the repository so the table above is regenerated from
it (and from the `strict` run), not edited by hand.

**Consequences for the rest of the plan.**  Phase 2 is split (section 7).  The "bit-identical to the scripts" claim of the
first draft now applies to the `runtime` provider only.  Packaging: viva-tellurium, viva-copasi and their dependency
viva-superpowers are all on PyPI (0.1.2, 0.1.2, 0.23.0); they are pinned in `pbg/requirements-lock.txt` together with
tellurium and basico versions that match the host's lock, and checked in CI (M8).  Wrapper API churn is a risk (section 6):
the `pbg_*` -> `viva_*` rename already happened once.  The `viva` provider imports the wrappers lazily, so an environment
without them still runs `--wrappers off`.

### 3.13 FBA: COBRApy

You asked for a good FBA to pull in for the cosimulation tests.  I looked at one candidate, COBRApy, because Spatio-Flux's
`DynamicFBA` is built on it (paper, Supplement 2, 1.2.1); I did not survey others, so "good" here means "checked and
fit for purpose", not "best of all".  Tested 2026-10-09 in the scratch environment:

| Check | Result |
|---|---|
| Version and licence | cobra 0.32.1; LGPL-2.0-or-later OR GPL-2.0-or-later (read from the package metadata); you judged this fine for a dependency (answer 4) |
| Python 3.13, numpy 2.2.x (the roadrunner pin) | Installs and runs; `pip check` reports nothing for cobra (its one line, about `phrasedml`, comes from tellurium) |
| Wheels | cobra is pure Python; its compiled dependencies `swiglpk` and `python-libsbml` have Python 3.13 wheels for Windows (win_amd64), macOS (arm64) and Linux (manylinux x86_64), so a CI matrix can install it everywhere |
| Coexists with roadrunner in one process | Yes: tellurium / roadrunner 2.10.0 and cobra imported and run together, no conflict (each bundles or links its own libsbml; only this combination was tried) |
| Offline test model | `cobra.io.load_model("textbook")` is bundled: E. coli core, 95 reactions, 72 metabolites; growth 0.8739 on default bounds, 0.4156 with glucose uptake limited to 5; 2 ms per solve |
| Solver | GLPK by default (via optlang); a scipy solver is also available |
| Alternate optima | At glucose -5, 2 of 95 reactions have a non-unique optimal flux (flux variability range above 1e-6).  Tests must compare the objective value and the uniquely determined fluxes, or fix a tie-break (parsimonious FBA), never the full flux vector blindly |

Where it lives (your answer 1: **in the main group**).  FBA is a fourth, FBA-only backend of the host `pysed2translate`, with a
`capabilities.json` entry for `fluxBalanceAnalysis` and its line removed from `docs/deferred.md`, so the script target gains it at
the same time and the PBG engine picks it up through the `runtime` provider (rule M7: nothing FBA-specific is PBG-only).  The host
work, each part a host edit that I do when that phase starts (section 7, phase 3b) and not before:

| Part | What |
|---|---|
| H-1 | `runtime/backends/cobra_backend.py`: FBA-only backend over COBRApy (objective, bounds, flux table, `.model`) |
| H-2 | `capabilities.json`: the `fluxBalanceAnalysis` entries, and the additive `kinds` grouping of task classes (3.14) |
| H-3 | `ModelChange` on an FBC model: reaction bounds and objective (the id mapping the original cosimulation file leaves out) |
| H-4 | `--backend` per kind in `cli.py` and `suite_runner` (3.14); the existing single-name form keeps working |
| H-5 | tests, `docs/capability-table.md`, `docs/deferred.md` |

Until H-1 exists, nothing in the PBG engine mentions FBA.  Spatio-Flux's `DynamicFBA` is a *dynamic* FBA (kinetic uptake bounds,
biomass update) and is a different thing from SED2's instantaneous FBA; it is a model of what the cosimulation does around the FBA
call, not a replacement for it.  What SED2's `FluxBalanceAnalysis` needs mapped (objective, bounds from a `ModelChange`, the flux
table, `.model` as an FBC-aware model) is the first task of that phase.

**A second FBA tool.**  Candidates, none yet installed or run: COBRApy itself with another LP solver (GLPK and the scipy solver
are both available through optlang today, so `cobra:glpk` against `cobra:scipy` tests the switching logic and the solver, and
costs nothing); CBMPy (PyPI `cbmpy` 0.8.8.1, from the PySCeS group, an FBA tool of its own); others if you name them.  You wrote
"tellurium-with-PySCeS": as far as I know PySCeS is a kinetic-modelling tool (ODE and steady state), not an FBA tool, but I have
not checked.  If you mean a second ODE and steady-state simulator, it is a new backend of kind `ode` / `steady` and the same
switches apply (3.14).  I will check both before building anything on them.

**Real models (your answer 6).**  The page https://vivarium-collective.github.io/CRM-FBA/ is the site of the repository
vivarium-collective/CRM-FBA (cloned at commit 4eba24c).  What is there, and what the cosimulation file's names correspond to:

| In the cosimulation file | Found | Notes |
|---|---|---|
| `ecoli_GSM.xml` (FBA) | `crm_dfba/models/iAF1260.xml`, E. coli iAF1260, SBML with FBC, 10.2 MB, 2382 reactions, 1668 metabolites; exchange ids `EX_glc__D_e`, `EX_ac_e`, `EX_o2_e` | Loads in 2 s, solves in 0.3 s (first) to about 0.07 s; growth 0.737 on its default bounds (glucose -8) |
| (other genome-scale models, same folder) | iJN746 (P. putida), iMM904 (yeast), iCN900, iNF517 (L. lactis), 0.9 to 7 MB | iCN900 has glucose lower bound 0 and growth 0 on its defaults: needs bounds set before use |
| `monod_CRM.xml` (ODE) | **Not an SBML file.**  The CRMs are Python classes (`crm_dfba/crms/monod.py`, `macarthur.py`, `mcrm.py`, `adaptive.py`); the Monod one is `Vmax S / (Km + S)` per resource | The mock ODE model of 5.1 uses the same kinetics and the same parameters as the repository's Monod demo (Vmax 10, Km 0.5 for glucose) |

Run with the real model (research script `pbg/tests/advanced/data/cosimulation/refloop_real.py`, plain Python, not an expected-data
source): the mock ODE feeds iAF1260's glucose and acetate bounds; growth 0.868 and acetate secretion 0.77 at the start; about 3 s
for 41 solves.  Two findings: (1) once glucose is exhausted (about t = 7) iAF1260 is **infeasible**, because its maintenance
reaction needs ATP that cannot be made, and a document must decide what that means (the script above sets growth to 0; SED2's
`FluxBalanceAnalysis` has no stated result for an infeasible problem, section 6); (2) the repository states no licence in the files I
looked at, so its models are not copied into this project.  A test downloads them at a pinned commit with a checksum and
skips when offline or when the checksum differs; if you want them stored in the repository, that needs the authors' licence first.
The mock pair stays as the offline, always-on test, as you asked.

### 3.14 Backends per task kind, and combinations of backends

Your answer 1 added a requirement: eventually two FBA simulators, to test them against each other and in combinations (COPASI
with COBRApy, and so on).  `--backend roadrunner` (one name for everything) is then too coarse.  The capability table is already
keyed by task class and backend, so what is missing is a *grouping* and a *grammar*.

**Kinds.**  A kind is a group of task classes served by the same sort of simulator.  The grouping is an additive `kinds` map in
`capabilities.json` (host edit H-2; until then a table in `pbg/`):

| Kind | Task classes | Backends today |
|---|---|---|
| `ode` | ExplicitODESimulation, OneStepODESimulation, BoundedODESimulation | roadrunner, copasi, opencor |
| `steady` | SteadyState | roadrunner, copasi, opencor |
| `jacobian` | JacobianFull, JacobianReduced | roadrunner, copasi, opencor |
| `fba` | FluxBalanceAnalysis | `cobra` (COBRApy, after H-1); a second one later |
| (none) | everything else: calculations, data, repeats, `ModelChange`, reports, plots | run in the host, no backend choice |

**Grammar.**  `--backend` is repeatable.

| Form | Meaning |
|---|---|
| `--backend roadrunner` | the default for every kind this backend can take (today's meaning) |
| `--backend fba=cobra` | the backend of one kind |
| `--backend fba=cobra:scipy` | a *variant* of a backend (here the LP solver); a variant counts as a separate entry in matrices |
| `--backend copasi --backend fba=cobra` | COPASI for ODE, steady state and Jacobian; COBRApy for FBA |
| `--backend-list` | prints kinds x backends: supported (from the capability table), provider (`viva` / `runtime`), installed, version |

Rules.  (1) A kind with no choice made: if exactly one installed backend can take it, it is used and the choice is printed on
stderr and written to the manifest ("fba: cobra (only candidate)"); if several can, the command stops with a usage error that
lists them (exit 2).  Nothing is chosen silently among several.  (2) A named backend that cannot take a task of its kind is a
refusal with the capability table's reason, exit 11, as now.  (3) The chosen (kind, backend, variant, provider, version) is
written into the config of every step it affects and into the manifest, so a generated document is self-contained and `run`
needs no backend switch.  (4) A document that mixes kinds (the cosimulation) is the normal case, not a special one.

**Matrix runs.**  `pysed2translate-pbg suite --matrix ode=roadrunner,copasi,opencor --matrix fba=cobra:glpk,cobra:scipy` takes the
product of the lists over the kinds each case actually uses (a case without FBA is run once per ODE entry, not four times),
translates and runs each combination, and compares it with the canonical data.  `--crosscheck` also compares the combinations with
each other: ODE series at the suite's tolerance; FBA by the objective value and the *uniquely determined* fluxes (3.13), since
alternate optima make full flux vectors differ legitimately.  Output: a case x combination table.  A disagreement between two
combinations is written as a draft entry (for `disagreements.json`) under `pbg/findings/`, which you move or discard; nothing is
added to the suite's own files by the tool.  The cosimulation test case (5.1) is the main user: every ODE backend x every FBA
backend must agree within tolerance, which is the "test against each other and in combinations" you described.

**Providers.**  `--wrappers` (3.12) applies to the pairs (kind, backend) that have a community wrapper.  Today that is `ode` and
`steady` for roadrunner and copasi.  I looked for a wrapper for plain FBA in the two wrapper repositories and found none;
Spatio-Flux's `DynamicFBA` is a dynamic FBA in another package, not SED2's FBA, so `fba` goes straight to the `runtime` provider
and is not counted as a wrapper gap (strict mode does not refuse it).

**Where this lives.**  The grammar and matrix are implemented in `pbg/` first (they are part of the new command).  The host's own
`--backend` accepts one name today; extending it to the same grammar is host edit H-4, which keeps the single-name form working.
Until H-4, `pysed2translate` (Python scripts) cannot mix kinds, and a cross-check of script target against PBG target is limited
to single-backend documents.


## 4. Element-by-element mapping

"Same check" means the capability table entry for the script target is used unchanged.

| SED2 element | Process-bigraph construct | Notes |
|---|---|---|
| `constants` | values under `state.constants` | Constants that refer to constants: refused (as now). |
| `ModelImport` | `task_<id>` step `SedModelImport`; writes `tasks.<id>.model` | Reads and parses the file at run time, so a bad `location` fails as a task, not at load. Language check as now. |
| `ExplicitODESimulation`, `OneStepODESimulation`, `BoundedODESimulation` | step `SedOdeSimulation` from the provider (3.12): a community-wrapper node plus an adapter, or our own step; writes `.data` and `.model` | Config carries the range, KiSAO algorithm, tolerances; same check, so OpenCOR still refuses Bounded.  Wrapper only for a static model and settings the wrapper takes (ledger W-1 to W-8). |
| `SteadyState` | step `SedSteadyState`; `.data`, `.model` | OpenCOR refused as now (libopencor issue 604). |
| `JacobianFull`, `JacobianReduced` | step `SedJacobian`; `.data` | COPASI zero-value refusal (D-001) is unchanged because it is in the backend. |
| `ModelChange` | step `SedModelChange`; `.model` | `setValues` values may be references, which become input ports. `addElements` / `replaceElements` stay deferred. |
| `ModelElementList` | step `SedModelElementList`; `.strings` | |
| `Calculation` | step `SedCalculation`; `.data` | Math tree, section 3.6. |
| `CreateDataBlock`, `RelabelData`, `StringFormation` | steps of the same names; `.data` (`.strings` for StringFormation) | |
| `NumericRange`, `Range`, `ParameterRange` as tasks | step `SedRange`; `.data` | As embedded objects they stay in the config of the task that holds them. |
| `Loop` | step `SedLoop` hosting an inner composite with a `SedClock` process and one step per sub-task, section 3.8; `.data`, `.aggregates`, final loop variables | Default (clock form).  `--loop-form nested` uses `SedRepeat`.  `aggregateOutputVariables` deferred as now. |
| `Scatter`, `ParameterScan` | step `SedRepeat`, section 3.8; `.data`, `.aggregates`, ranges/indexes, `.model` for ParameterScan | Independent iterations, nested document per iteration. |
| `CsvImport` | step `SedCsvImport`; `.data` | Reads relative to the runner's input directory. `organization` other than "columns" deferred as now. |
| `DataImport`, `AggregationCalculation` | refused, exit 11 | Waiting for the specification (SED2/TODO.md). |
| `Report` | step `output_<id>`, section 3.7 | |
| `Plot2D`, `Plot3D` | step `output_<id>` | `_as_data` files always; PNG when matplotlib is available. |
| `taskParameters`, `outputParameters` | refused where the script target refuses them | The same open items. |
| `FluxBalanceAnalysis` | step `SedFba` over COBRApy (3.13) | Needs the FBA backend decision (section 8, open question 1); refused, exit 11, until then. |
| Stochastic simulations, `DrawFromDistribution` | refused, exit 11 | Later phase, as in build.md. |
| `name`, `description`, `notes`, `annotations` of any element | not translated | They do not affect results. The document `description` names the source file. |
| `version` | `sed2.version` | |

## 5. A worked example

Input: `tests/golden/docs/ode_time_courses.sed2.json` (a ModelImport, an explicit time course, a one-step simulation
that continues from the time course's end model, and three reports).  The document below is the proposed output
shape, written by hand.  Tested: it loads in process-bigraph 1.8.5 and runs in dependency order with **stub** Step
classes (analytic decay, plain dicts instead of AnnotatedData and SbmlModel, no files).  It is evidence for the shape
of the document, not for the simulation steps.  `maxNumberOfSteps` and the other solver settings are carried as config
and `relativeTolerance` is a wire because the SED2 file wrote it as a reference.  The index on `output_s1` shows the
idea only; the exact JSON for brackets comes from `parse_reference` when the translator is written.

```json
{
  "name": "ode_time_courses",
  "description": "Translated from ode_time_courses.sed2.json (backend: roadrunner)",
  "state": {
    "constants": {
      "tol": 1e-08
    },
    "tasks": {
      "m": {
        "model": {}
      },
      "explicit": {
        "data": {},
        "model": {}
      },
      "one": {
        "data": {},
        "model": {}
      }
    },
    "task_m": {
      "_type": "step",
      "address": "local:!sedstubs.SedModelImport",
      "config": {
        "location": "model.xml",
        "language": "urn:sedml:language:sbml",
        "backend": "roadrunner"
      },
      "inputs": {},
      "outputs": {
        "model": [
          "tasks",
          "m",
          "model"
        ]
      }
    },
    "task_explicit": {
      "_type": "step",
      "address": "local:!sedstubs.SedExplicitODE",
      "config": {
        "backend": "roadrunner",
        "independentVariable": "time",
        "outputVariables": [
          "S1",
          "S2"
        ],
        "range": {
          "start": 0,
          "end": 4,
          "numberOfSteps": 4
        },
        "maxNumberOfSteps": 5000
      },
      "inputs": {
        "model": [
          "tasks",
          "m",
          "model"
        ],
        "relativeTolerance": [
          "constants",
          "tol"
        ]
      },
      "outputs": {
        "data": [
          "tasks",
          "explicit",
          "data"
        ],
        "model": [
          "tasks",
          "explicit",
          "model"
        ]
      }
    },
    "task_one": {
      "_type": "step",
      "address": "local:!sedstubs.SedOneStepODE",
      "config": {
        "backend": "roadrunner",
        "independentVariable": "time",
        "outputVariables": [
          "S1"
        ],
        "independentStep": 2,
        "independentVariableInit": 1
      },
      "inputs": {
        "model": [
          "tasks",
          "explicit",
          "model"
        ]
      },
      "outputs": {
        "data": [
          "tasks",
          "one",
          "data"
        ],
        "model": [
          "tasks",
          "one",
          "model"
        ]
      }
    },
    "output_traj": {
      "_type": "step",
      "address": "local:!sedstubs.SedReport",
      "config": {
        "id": "traj"
      },
      "inputs": {
        "data": [
          "tasks",
          "explicit",
          "data"
        ]
      }
    },
    "output_step": {
      "_type": "step",
      "address": "local:!sedstubs.SedReport",
      "config": {
        "id": "step"
      },
      "inputs": {
        "data": [
          "tasks",
          "one",
          "data"
        ]
      }
    },
    "output_s1": {
      "_type": "step",
      "address": "local:!sedstubs.SedReport",
      "config": {
        "id": "s1",
        "index": [
          {
            "range": [
              0,
              5
            ]
          },
          {
            "label": "S1"
          }
        ]
      },
      "inputs": {
        "data": [
          "tasks",
          "explicit",
          "data"
        ]
      }
    }
  }
}
```

Differences from what the translator would write: the addresses would be `local:!pysed2translate_pbg.engines.v1.steps.<Class>`,
a `tasks.explicit.data` store would be typed `node` on both sides (section 2.5), and a `sed2` header would be present.

## 5.1 Test case: cosimulation with the loop as the clock

Source: an attachment from the SED2 author, written in an earlier syntax ("SED v2.0 alpha") and not tested then.  It is
the SED2 version of the process-bigraph cosimulation pattern in which a clock alternates two models, and the **indexes
of the Loop are the clock**.  An ODE model (a Monod consumer-resource model, `monod_CRM.xml`) is advanced for
`ode_interval` = 20 time units, its end state sets the bounds of a flux-balance model of E. coli (`ecoli_GSM.xml`), the
FBA fluxes are written back into the ODE model as rates, and the cycle repeats.  Each iteration's ODE time course is
collected.

**The document, corrected to the current syntax and with the ODE time continuing.**  The original did not load
(`versionStr`/`versionNum`, `kisaoID` and `outputModel` on simulations, and a `.model` suffix on loop-variable references).
Four syntax fixes and one change you asked for were made, and nothing else (checked with the project's loader: 0 problems).
The original is kept unchanged as the "as written" case (answer 6 in section 8); this is the "timed" case:

1. `"version": "v1.0.0"` instead of `versionStr` / `versionNum`;
2. `workingAlgorithms: [{"algorithm": "KISAO:..."}]` instead of `kisaoID` (ODE: KISAO:0000694, FBA: KISAO:0000437);
3. `outputModel` removed (`.model` is always available);
4. `#tasks:repeat:loopVariables:ODE_model` and `...:FBA_model` instead of `...:ODE_model.model` (a loop variable has the
   shape of its initial value, here a model);
5. (your change) the ODE time continues across iterations: two new Calculation sub-tasks, `t_start` =
   `#tasks:repeat.index * #constants:ode_interval` and `t_end` = `(#tasks:repeat.index + 1) * #constants:ode_interval`;
   `odesim` takes `independentVariableInit` and the range's `start` from `t_start` and the range's `end` from `t_end`, so
   iteration k covers [20k, 20(k+1)] and the traces no longer overlap.

```json
{
  "version": "v1.0.0",
  "constants": {
    "ode_interval": 20
  },
  "tasks": {
    "ODEmodel": {
      "_type": "modelImport",
      "location": "monod_CRM.xml",
      "language": "urn:sedml:language:sbml"
    },
    "FBAmodel": {
      "_type": "modelImport",
      "location": "ecoli_GSM.xml",
      "language": "urn:sedml:language:sbml"
    },
    "ODE_species": {
      "_type": "modelElementList",
      "model": "#tasks:ODEmodel.model",
      "includeTypes": [
        "species"
      ]
    },
    "FBA_rxns": {
      "_type": "modelElementList",
      "model": "#tasks:FBAmodel.model",
      "includeTypes": [
        "reactions"
      ]
    },
    "repeat": {
      "_type": "loop",
      "range": {
        "_type": "numericRange",
        "numberOfSteps": 100
      },
      "loopVariables": {
        "ODE_model": {
          "initialValue": "#tasks:ODEmodel.model",
          "subsequentValues": "#tasks:repeat:subTasks:new_ode.model"
        },
        "FBA_model": {
          "initialValue": "#tasks:FBAmodel.model",
          "subsequentValues": "#tasks:repeat:subTasks:fbasim.model"
        }
      },
      "subTasks": {
        "t_start": {
          "_type": "calculation",
          "math": "#tasks:repeat.index * #constants:ode_interval"
        },
        "t_end": {
          "_type": "calculation",
          "math": "(#tasks:repeat.index + 1) * #constants:ode_interval"
        },
        "odesim": {
          "_type": "explicitODESimulation",
          "model": "#tasks:repeat:loopVariables:ODE_model",
          "independentVariable": "urn:sedml:symbol:time",
          "independentVariableInit": "#tasks:repeat:subTasks:t_start",
          "independentVariableRange": {
            "_type": "numericRange",
            "start": "#tasks:repeat:subTasks:t_start",
            "end": "#tasks:repeat:subTasks:t_end",
            "numberOfSteps": 100,
            "scale": "linear"
          },
          "outputVariables": "#tasks:ODE_species.strings",
          "workingAlgorithms": [
            {
              "algorithm": "KISAO:0000694"
            }
          ]
        },
        "new_fba": {
          "_type": "modelChange",
          "inputModel": "#tasks:repeat:loopVariables:FBA_model",
          "setValues": "#tasks:repeat:subTasks:odesim[-1]"
        },
        "fbasim": {
          "_type": "fluxBalanceAnalysis",
          "model": "#tasks:repeat:subTasks:new_fba.model",
          "outputVariables": "#tasks:FBA_rxns.strings",
          "workingAlgorithms": [
            {
              "algorithm": "KISAO:0000437"
            }
          ]
        },
        "new_ode": {
          "_type": "modelChange",
          "inputModel": "#tasks:repeat:subTasks:odesim.model",
          "setValues": "#tasks:repeat:subTasks:fbasim"
        }
      },
      "outputVariableMap": {
        "species_trace": "#tasks:repeat:subTasks:odesim"
      }
    }
  },
  "outputs": {
    "cosim_output": {
      "_type": "report",
      "data": "#tasks:repeat['species_trace']"
    }
  }
}
```

**Translation, clock form.**  Outer document (stores and wires of the four preparatory tasks, the loop as one Step, the
report):

```json
{
  "name": "cosimulation",
  "description": "Translated from cosimulation.sed2.json (backend: roadrunner for the ODE; an FBA backend is needed)",
  "sed2": {"version": "v1.0.0", "engine": "v1", "engineVersion": "1.0"},
  "schema": {"tasks": {"_type": "map", "_value": "overwrite[node]"}},
  "state": {
    "constants": {"ode_interval": 20.0},
    "task_ODEmodel": {
      "_type": "step",
      "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelImport",
      "inputs": {"context": ["context"]},
      "outputs": {"model": ["tasks", "ODEmodel", "model"]},
      "config": {"location": "monod_CRM.xml", "language": "urn:sedml:language:sbml"}
    },
    "task_FBAmodel": {
      "_type": "step",
      "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelImport",
      "inputs": {"context": ["context"]},
      "outputs": {"model": ["tasks", "FBAmodel", "model"]},
      "config": {"location": "ecoli_GSM.xml", "language": "urn:sedml:language:sbml"}
    },
    "task_ODE_species": {
      "_type": "step",
      "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelElementList",
      "inputs": {"model": ["tasks", "ODEmodel", "model"]},
      "outputs": {"strings": ["tasks", "ODE_species", "strings"]},
      "config": {"includeTypes": ["species"]}
    },
    "task_FBA_rxns": {
      "_type": "step",
      "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelElementList",
      "inputs": {"model": ["tasks", "FBAmodel", "model"]},
      "outputs": {"strings": ["tasks", "FBA_rxns", "strings"]},
      "config": {"includeTypes": ["reactions"]}
    },
    "task_repeat": {
      "_type": "step",
      "address": "local:!pysed2translate_pbg.engines.v1.loop.SedLoop",
      "inputs": {
        "initial_ODE_model": ["tasks", "ODEmodel", "model"],
        "initial_FBA_model": ["tasks", "FBAmodel", "model"],
        "ODE_species_strings": ["tasks", "ODE_species", "strings"],
        "FBA_rxns_strings": ["tasks", "FBA_rxns", "strings"],
        "ode_interval": ["constants", "ode_interval"],
        "context": ["context"]
      },
      "outputs": {"data": ["tasks", "repeat", "data"]},
      "config": {"ticks": 101, "document": "<the inner document below>"}
    },
    "output_cosim_output": {
      "_type": "step",
      "address": "local:!pysed2translate_pbg.engines.v1.steps.SedReport",
      "inputs": {"data": ["tasks", "repeat", "data"], "context": ["context"]},
      "outputs": {},
      "config": {"id": "cosim_output", "select": "species_trace"}
    },
    "context": {"inputDir": ".", "outputDir": "results", "prefix": "cosimulation"}
  }
}
```

`document` in `task_repeat` is the inner composite.  The clock publishes `range`, `index` and the two loop variables; the
four sub-tasks are steps reading them; the previous iteration's `new_ode.model` and `fbasim.model` come back to the
clock as `next_*` inputs.  The `outer.*` stores in the wires are the free references, which the host copies in as input
ports.  Shape tested with stand-in classes (section 2.9); the real classes do not exist yet.

```json
{
  "index": -1,
  "range": 0.0,
  "clock": {
    "_type": "process",
    "address": "local:!pysed2translate_pbg.engines.v1.loop.SedClock",
    "interval": 1.0,
    "config": {"range": {"numberOfSteps": 100}, "loopVariables": ["ODE_model", "FBA_model"]},
    "inputs": {
      "initial_ODE_model": ["initial", "ODE_model"],
      "initial_FBA_model": ["initial", "FBA_model"],
      "next_ODE_model": ["subtasks", "new_ode", "model"],
      "next_FBA_model": ["subtasks", "fbasim", "model"]
    },
    "outputs": {
      "range": ["range"],
      "index": ["index"],
      "ODE_model": ["loopVariables", "ODE_model"],
      "FBA_model": ["loopVariables", "FBA_model"]
    }
  },
  "subtask_t_start": {
    "_type": "step",
    "address": "local:!pysed2translate_pbg.engines.v1.steps.SedCalculation",
    "inputs": {"index": ["index"], "ode_interval": ["outer", "ode_interval"]},
    "outputs": {"data": ["subtasks", "t_start", "data"]},
    "config": {"math": "index * ode_interval"}
  },
  "subtask_t_end": {
    "_type": "step",
    "address": "local:!pysed2translate_pbg.engines.v1.steps.SedCalculation",
    "inputs": {"index": ["index"], "ode_interval": ["outer", "ode_interval"]},
    "outputs": {"data": ["subtasks", "t_end", "data"]},
    "config": {"math": "(index + 1) * ode_interval"}
  },
  "subtask_odesim": {
    "_type": "step",
    "address": "local:!pysed2translate_pbg.engines.v1.steps.SedOdeSimulation",
    "inputs": {
      "index": ["index"],
      "model": ["loopVariables", "ODE_model"],
      "outputVariables": ["outer", "ODE_species_strings"],
      "init": ["subtasks", "t_start", "data"],
      "start": ["subtasks", "t_start", "data"],
      "end": ["subtasks", "t_end", "data"]
    },
    "outputs": {"data": ["subtasks", "odesim", "data"], "model": ["subtasks", "odesim", "model"]},
    "config": {"kind": "explicit", "numberOfSteps": 100, "scale": "linear", "kisao": "KISAO:0000694"}
  },
  "subtask_new_fba": {
    "_type": "step",
    "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelChange",
    "inputs": {
      "index": ["index"],
      "model": ["loopVariables", "FBA_model"],
      "setValues": ["subtasks", "odesim", "data"]
    },
    "outputs": {"model": ["subtasks", "new_fba", "model"]},
    "config": {"setValuesIndex": -1}
  },
  "subtask_fbasim": {
    "_type": "step",
    "address": "local:!pysed2translate_pbg.engines.v1.steps.SedFba",
    "inputs": {
      "index": ["index"],
      "model": ["subtasks", "new_fba", "model"],
      "outputVariables": ["outer", "FBA_rxns_strings"]
    },
    "outputs": {"data": ["subtasks", "fbasim", "data"], "model": ["subtasks", "fbasim", "model"]},
    "config": {"kisao": "KISAO:0000437"}
  },
  "subtask_new_ode": {
    "_type": "step",
    "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelChange",
    "inputs": {
      "index": ["index"],
      "model": ["subtasks", "odesim", "model"],
      "setValues": ["subtasks", "fbasim", "data"]
    },
    "outputs": {"model": ["subtasks", "new_ode", "model"]}
  },
  "emitter": {
    "_type": "step",
    "address": "local:RAMEmitter",
    "config": {"emit": {"index": "integer", "species_trace": "node"}},
    "inputs": {"index": ["index"], "species_trace": ["subtasks", "odesim", "data"]}
  }
}
```

**Things the test case shows, and what the plan does about them.**

| Observation | Consequence |
|---|---|
| `numericRange` with only `numberOfSteps: 100` has 101 entries, so the loop runs **101** iterations. | The clock takes its count from the evaluated range (rule 5 in 3.8); the test expects 101 rows.  If 100 was meant, the file needs `end`/`start` or a `numberOfSteps` of 99: a note for the SED2 author, not a translator choice. |
| In the file as written, the ODE sub-task restarts at time 0 in every iteration (`independentVariableInit: 0`); the traces overlap. | Fixed in the timed case (change 5 above).  The as-written case keeps it, and its translation holds 101 blocks of time 0..20, which is a test that the translator does not "fix" the document. |
| `new_fba` sets values from `odesim[-1]`: the last row of the time course, **including the time column**, and species ids that are not the FBA model's exchange-reaction ids. | `ModelChange.setValues` needs a mapping from ODE species to FBA bounds (CalculationTask for the uptake kinetics, RelabelData for the ids).  Written that way the file is only a sketch.  The translator would raise a clear error where ids do not resolve; it must not guess. |
| `new_ode` sets values from the whole `fbasim` result (fluxes), again with no id mapping or rate conversion. | Same; and rates versus fluxes need units. |
| The `FBA_model` loop variable is `fbasim.model`, but nothing reads the FBA model of iteration k - 1 other than the next `new_fba`, which changes it again. | Harmless; kept, because the translation of loop variables must not depend on whether the author needed them. |
| The report is 3-dimensional (iterations x time points x species). | The existing Report writer handles it as HDF5 only; the CSV writer refuses.  Same behaviour as the script target. |
| An FBA problem can be **infeasible** (found with iAF1260 once glucose is exhausted: the maintenance reaction cannot be supplied).  SED2 does not say what a `FluxBalanceAnalysis` task returns then. | The mock pair avoids it by construction.  The real-model case needs a rule in the document (a Calculation that maps "no solution" to zero growth) and the backend must report infeasibility as data or as a refusal, not as a made-up flux table.  Drafted as a question for the SED2 author in `pbg/findings/sed2-fba-infeasible.md`, not added to SED2/TODO.md by me. |
| `fluxBalanceAnalysis` is deferred on every backend in `capabilities.json`. | The case can be translated and structurally tested now, but cannot run end to end until an FBA backend exists.  The FBA to pull in is COBRApy (section 3.13).  Exit status 11 with the usual skip line until then. |
| Process-bigraph's own cosimulation couples **processes** with a clock; SED2's loop runs the sub-tasks **in sequence**, each reading the previous one's result.  In process-bigraph, two processes with the same interval read the state at the start of the interval (tested), so the same models wired as processes give different numbers. | The translation preserves SED2's sequential semantics (all sub-tasks are steps).  The coupled-process form is a different, parallel scheme; see `process-bigraph-clock.md`. |

**What is tested when.**  Both cases (as written and timed) are kept, as you asked, and both eventually run for real.

1. Now (plan phase 3): a structural test with stand-in sub-task classes, like the experiment in section 2.9: 101 ticks,
   iteration order, loop-variable hand-over, sub-tasks run once per iteration, the init guard, downstream tasks fire once,
   and (timed case) the ODE start and end times of iteration k.  The stand-ins are tiny classes defined in the test, so no
   simulator is needed.  Runs on both cases.
2. With an ODE backend and a stand-in FBA step (a closed-form "uptake limited by a bound"): the ODE half through roadrunner
   and COPASI (and OpenCOR where it can), compared against the same loop run by hand in Python.
3. With COBRApy (3.13): the **mock pair** replaces the two unavailable files.  Both are in
   `pbg/tests/advanced/data/cosimulation/` (built by `build_mock.py`, which also documents the numbers):
   `monod_CRM_mock.xml`, a Monod consumer-resource ODE in SBML (glucose, acetate, biomass; uptake `Vmax S / (Km + S)` with the
   parameters of the CRM-FBA Monod demo; growth rate and exchange fluxes enter as parameters set between intervals), and
   `toy_FBA_mock.xml`, a 8-reaction FBC model with respiration (capacity limited), fermentation with acetate overflow and acetate
   re-use, whose exchange ids are `EX_glc__D_e` and `EX_ac_e`.  `refloop.py` runs the cycle in plain Python (41 intervals of 1 time unit):
   glucose is consumed, acetate is secreted and then used, biomass grows.  It is a sanity check, not an expected-data source.
   The id mapping the original leaves out (uptake -> lower bound, flux -> rate) is written as Calculation tasks in the SED2 document.
   The timed case is the numerical test; the as-written case stays a translation-only test until its file is completed.
   Expected data: the Python-script equivalent (section 7, test tiers), then compared.
4. With the **real model** (3.13): the same mock ODE and iAF1260 downloaded at a pinned commit.  Runs in about 3 s for 41
   intervals in plain Python (`refloop_real.py`); the full 101-iteration SED2 document with 100 ODE steps per iteration is expected
   to take of the order of a minute (not measured).  Skipped when the download is unavailable.  Needs the infeasibility rule above.

## 6. Risks, gaps and things to report

Anything here that turns out to be a bug or a gap goes where CLAUDE.md says (SED2/TODO.md for the specification and
libsed2; `disagreements.json` for simulators).  None of these has been logged yet.

1. **A moving target.**  The 1.8 series already has six releases (1.8.0 to 1.8.5), the wrappers were renamed from
   `pbg-*` to `viva-*`, and the SQLite and Parquet emitters moved to another package.  Pin `process-bigraph==1.8.5` and
   `bigraph-schema==1.7.0` in `requirements-lock.txt`, and keep the translator's use of the framework to four
   things: the document keys, step nodes, wires and `Composite(...).run(0.0)`.
2. **Typing clashes.**  The `overwrite` / `maybe` mismatch (section 2.5) is easy to hit and the error text is
   opaque.  The translator chooses port types from one table, and a test builds every golden document.
3. **Silent unknown keys.**  A misspelt top-level key (`global_time_precison`) is accepted and ignored.  The
   translator should only write keys from a fixed list, and a test should compare them with `Composite.config_schema`.
4. **One run, many tasks.**  The scheduler may run a step again if a path it reads is updated again.  With
   steps only and `run(0.0)` that did not happen in the tests.  A flat clock *does* re-fire downstream steps every
   tick (tested), which is why a Loop is hosted in its own Step.  Step cycles are silently broken, not rejected, so the
   translator must prove the step graph acyclic before writing (the clock's feedback goes through the *process*, never
   through a step-to-step wire).  Cycles cannot occur in valid SED2 references.  Test with a wide, deep generated
   document before trusting it (phase 0).
5. **Process-bigraph overhead and install size.**  It pulls in matplotlib, scipy, pandas, sympy, pint and requests.
   That is why it is an optional extra.  `import process_bigraph` also prints a harmless line about the optional
   `fire` package.
6. **The viva wrappers' behaviour.**  W-1 to W-4 and W-10 are confirmed by running both wrappers; W-5 to W-8 are from reading
   the source and have not been run (the steady-state steps in particular).
7. **Specification gaps carry over.**  Everything in docs/deferred.md is still deferred.  The clock work adds a
   larger list of things SED2 cannot say about process-bigraph's clock (coupled and multi-rate processes, adaptive
   steps, conditional and open-ended loops, stateful continuation); they are written up with proposed SED2 extensions
   in `process-bigraph-clock.md`, and none is needed for the translation itself.
8. **Upstream notes** are drafted, not filed (P-1 to P-4 in `pbg/upstream/`): unknown config keys accepted silently, step cycles
   broken silently, the read time of longer-interval processes, `MathExpressionStep` documented but absent.  The opaque "two different
   wrappings" error is not drafted.  Reporting is yours.
9. **Wrapper churn and gaps.**  The wrappers are at 0.1.2 and were renamed once already; a wrapper update can change a
   result or close a ledger item.  Pins plus the `strict` run as a regular CI job catch both.  A wrapper that cannot pass a
   setting forces a fallback or a refusal (3.12); the plan never passes a setting that the wrapper then ignores (W-1 is
   exactly that case, and a test of the capability table runs each wrapper with a non-default value and reads the
   integrator back).
10. **FBA is unspecified.**  How SED2's `FluxBalanceAnalysis` maps to COBRApy (objective, bounds, outputs, the `.model`) is
   not worked out; FBA optima can be non-unique (3.13); an **infeasible** problem has no stated result (found with iAF1260).  Two FBA
   tools may legitimately return different flux vectors for the same optimum, so cross-checks compare the objective and the uniquely
   determined fluxes only.
11. **Backend combinations multiply.**  3 ODE backends x 2 FBA backends is 6 runs per cosimulation case, and iAF1260 is slow enough
   that the real-model case should run in the matrix only on request.  The matrix takes the product over the kinds a case uses,
   not over all kinds (3.14).
12. **Real model files** have no licence file in the repository I cloned (3.13); they are fetched, pinned and checksummed, never
   copied into this project.  A pinned commit can disappear: the test skips with a message instead of failing.
13. **Host edits.**  FBA in the main group (H-1 to H-5, 3.13/3.14) is the first plan item that touches the host beyond the M1 test.
   They are additive (a new backend, new capability entries, a `kinds` map, an extended `--backend` grammar that still accepts
   the single-name form), and none is made before phase 3b.

## 7. Implementation plan

Each phase ends with its tests passing; do not move on with a red test.

**Phase 0 - skeleton and spike (small).**  Modularity first (section 3.11), because it is cheap now and expensive later.
* Create `pbg/` with its own `pyproject.toml` and lock file; confirm `pip check` with the host's lock (roadrunner, copasi,
  libopencor, sbml2cellml, numpy 2.2.x).  CI first: a matrix over all the platforms the runners and wheels allow (section
  3.11, M8); you do not need to test on your own machine.  Only Linux has been exercised so far (this scratch environment),
  and the dependency check above (cobra's compiled dependencies have Windows, macOS and Linux wheels for Python 3.13) is the
  only cross-platform evidence.  No host file is edited except the approved M1 test; `git status` outside `pbg/` is clean
  (and the three docs `process-bigraph*.md`).
* `host.py` with the seam functions, each verified to exist with the expected signature; the AST test (M2); the host-side
  scan (M1: one small test in the host's `tests/`, which you approved; it is the only host edit, it only reads files, and it
  is removed together with the target); engine discovery (M4); the contract-test harness (M5) with a trivial engine that fails everything, to
  prove the harness fails.
* Engine `v1`: `document.py` (builder for the skeleton: stores, nodes, wires) and `runner.py`, with two real steps,
  `SedCalculation` and `SedReport`, and translate series 1 of the suite (constants and reports).
* Move the scratch experiments into `pbg/research/` with a README that says how to rerun each and what it showed, and write
  `NOTES.md` from section 2.9 and the rules in 3.8.
* Tests: a document with 200 chained and 50 fan-in tasks runs once each; a misspelt key is caught; deterministic text;
  the removal test (M4); the host suite passes in an environment without process-bigraph (M8).

**Phase 1 - data tasks.**  `SedCreateDataBlock`, `SedRelabelData`, `SedStringFormation`, `SedRange`,
`SedModelElementList`, accessors/`index`, math tree.  Acceptance: suite series "constants" and "calculations and data
manipulation" pass through the PBG target.

**Phase 2a - simulation, `runtime` provider.**  `SedModelImport`, `SedOdeSimulation` (explicit, one-step, bounded),
`SedSteadyState`, `SedJacobian`, `SedModelChange`.  All three backends.  Acceptance: ODE, steady-state, Jacobian and
ModelChange series.  Cross-check: output equals the script output on the same backend for every case (bit-identical,
because the code path is shared; a difference is a bug in one of the new layers).

**Phase 2b - simulation, `viva` provider (community wrappers).**  The capability table of the wrappers, the adapter steps
(wrapper output -> labelled `AnnotatedData`), `--wrappers strict|prefer|off` (default `strict`), and the ledger (3.12).  Acceptance: `strict`
run over the whole suite produces the list of tasks the wrappers can take and, for the rest, the W-ids; every task the
wrapper takes agrees with the canonical data at the suite's tolerance, or is a recorded finding.  Deliverable beside the code:
the drafted issue texts under `pbg/upstream/` (14 exist already; W-1 first), never filed by the assistant.

**Phase 3 - repeats and files.**  `SedLoop` with the `SedClock` process and the `SedStep` init guard (Loop, clock
form), `SedRepeat` (Scatter, ParameterScan, and Loop under `--loop-form nested`), `SedCsvImport`, `Plot2D`/`Plot3D`
steps.  Acceptance: ranges/repeats, CsvImport and plot-data series; the Loop series must give identical numbers in the
clock form and in the nested form.  Cosimulation test case (section 5.1), stages 1 and 2, on both the as-written and the
timed documents.  Extra tests: a downstream
task of a Loop fires exactly once; a Loop with a range computed at run time; a Loop whose loop variable is not a model
(a number, an array); a Scatter inside a Loop and a Loop inside a Loop (recursive hosting); parallel sibling sub-tasks; 0-iteration and 1-iteration loops; the translator rejects a step cycle.

**Phase 3b - FBA (3.13, 3.14).**  Host first: H-1 to H-5 (the `cobra` backend, capability entries and `kinds`, `ModelChange` on FBC models,
the per-kind `--backend` grammar, tests and docs), so the script target has FBA too; then the PBG side (`SedFba` through the `runtime`
provider, the `--backend` grammar in `pbg/`, `--backend-list`).  The matched mock pair, stage 3 of the cosimulation case on the
timed document, then the as-written one once its file is completed, then the real-model case (stage 4).  A second FBA entry
(`cobra:scipy` first, CBMPy if it checks out) exists before the phase is closed, so the matrix is exercised for real.

**Phase 4 - suite integration.**  Through the contract tests (M5), not by editing the host's `suite_runner`:
`pysed2translate-pbg suite [--engine v1] [--crosscheck] [--matrix kind=a,b ...]` runs the suite cases through an engine (for each backend
combination, 3.14) and compares with the canonical data; `--crosscheck` also compares with the Python-script target, whose runner is called through `host.py`.
All 273 cases on all admitted backends.  Documentation lives in `pbg/README.md`; the host README gets at most one sentence
that points to it (optional, and the only prose change outside `pbg/`).

**Phase 5 - optional.**  The native-process rewrite (3.9) as its own engine folder, with its own small tests and no role
in admitting suite cases.

Files (the layout of section 3.11; everything is under `pbg/`):

```
pbg/pyproject.toml, requirements-lock.txt, README.md, NOTES.md
pbg/research/                                   # experiments, runnable, with expected output (README says how to rerun)
pbg/upstream/                                   # drafted issue texts for other projects (14 files + README); never filed by the assistant
pbg/findings/                                   # drafts for this project's own disagreements.json / SED2 TODO; you move or discard them
pbg/tools/pbg2py.py                             # scheduler exporter for tier C (route 2); not imported by the engine
pbg/tests/advanced/data/cosimulation/           # mock ODE and FBA models, builder, plain-Python reference loops
pbg/tests/native/                               # tier C documents, translated scripts, expected output
pbg/src/pysed2translate_pbg/host.py             # the only import of pysed2translate
pbg/src/pysed2translate_pbg/cli.py              # translate / run / suite / engines
pbg/src/pysed2translate_pbg/engines/v1/document.py   # builds the JSON; one handler per element
pbg/src/pysed2translate_pbg/engines/v1/steps.py      # the Step classes; thin, they call the host runtime
pbg/src/pysed2translate_pbg/engines/v1/loop.py       # SedLoop (host step), SedClock (process), SedRepeat, init guard
pbg/src/pysed2translate_pbg/engines/v1/runner.py     # builds the Context, runs the Composite, exit codes, manifest
pbg/tests/contract/                             # engine-agnostic: translate -> run -> compare; imports/layout rules M1-M9
pbg/tests/v1/test_document.py                   # goldens in pbg/tests/v1/golden/, determinism, key check, Composite() builds
pbg/tests/v1/test_steps.py                      # each step on its own, with the runtime's test models
pbg/tests/v1/test_loop.py                       # clock form: ordering, hand-over, fires-once, init guard, cosimulation (5.1)
```

**Test tiers (your answer 3).**  Some cases map most cleanly to PBG alone (cosimulation is the example), but each should
have an equivalent Python script where that is possible, and the emphasis is on more advanced SED2 tests.

| Tier | What | Expected data | Runs on |
|---|---|---|---|
| A: shared suite | The 273 existing cases | the suite's canonical data, unchanged | script target and PBG target |
| B: advanced SED2 | New SED2 documents written for this: nested Loop in Loop, Scatter in Loop, Loop in Scatter, parallel sibling branches with a merge Calculation, a loop carrying a model, ranges from references, a downstream task of a loop, 0 and 1 iteration loops, the cosimulation (timed and as written) | produced by the Python-script target first and checked by hand or by closed form; where the script target cannot run it yet (FBA), by a hand-written Python script | script target where it can, PBG target always |
| C: PBG-native | Documents written directly in process-bigraph that have no direct SED2 form (for example processes coupled by interval) | a Python script **translated from the document** by a translator (see below), never written by hand | PBG engine, and the translated script; they must agree |

New tier B documents belong in the SED2 test suite (a proposal to its owner, outside this project), and in the meantime in
`pbg/tests/advanced/` with their own expected data.  Tier C is where the process-bigraph-only behaviour (stale reads,
equal-interval coupling) is pinned down, so that a change in the framework shows up as a failing test.

**Tier C scripts are translated, not hand-written (your correction), and built now (your answer 5).**  A hand-written oracle is slow to
produce, easy to get subtly different from the document, and does not scale.  You asked not to wait for the reverse direction, so the
order is reversed from the first draft: route 2 first, route 1 when it exists.

2. **PBG -> script (scheduler export) - built first.**  A small translator emits a plain Python script that contains the document's
   store values, the process classes' `update` calls, and a scheduler of about forty lines implementing a *stated reading* of the
   scheduling rule.  It does not use `Composite` or its scheduler.  (Correction to the first draft, which said "no process-bigraph
   import": the process classes themselves still import process-bigraph's `Process` base and `allocate_core`; only the composite
   machinery is avoided.)  The *scheduling* is therefore independent, and scheduling is what these cases test; the process code is
   shared, so it is less independent than route 1.  Two readings are options (`--reading start|event`), because the specification and
   the implementation differ for unequal intervals (section 2.10, item 3; `pbg/upstream/P-3.md`).
   **Prototype, run 2026-10-09** (`pbg/research/pbg2py.py`, `exp9.py`): for two coupled processes with intervals 1 and 1 the export agrees
   with process-bigraph under both readings; for intervals 1 and 2 it agrees exactly under `start` and differs under `event`.  The
   prototype handles processes only (no steps, no emitter nodes, no `overwrite` ports beyond the merge rule); the real tool adds
   them, driven by the cases below.
1. **PBG -> SED2 -> script - later, if the reverse direction is ever built.**  The importer (`process-bigraph-to-sed2.md`, set
   aside) turns the document into SED2, and the host's translator turns that into a script.  It would give a second, more
   independent oracle for the cases SED2 can say (one clock, chained or parallel processes, static models).

Tier C cases created now, each a `*.pbg.composite.json` document plus its translated script and the expected output of that script
(`pbg/tests/native/`; the first two exist as prototype documents):

| Case | What it pins down |
|---|---|
| C1 two processes, equal intervals, coupled through shared stores | Jacobi (parallel) coupling: both read the start-of-interval state |
| C2 intervals 1 and 2 | stale read of the slower process; the two readings in a table, with the framework's reading as the expected data and the other as a recorded difference |
| C3 ODE process and FBA process, equal intervals (the Spatio-Flux pattern), with the mock pair | the process-coupled counterpart of the SED2 cosimulation; compared with the sequential Loop result, which must differ in the stated way |
| C4 a Step reading a process output | step ordering relative to process events |
| C5 the cosimulation as a clock-form document | the same document the forward translator writes, so route 2 also checks the forward direction |

A hand-written script remains acceptable as a *unit test of the exporter* (does it reproduce this small case?), never as the expected
data of a case.  The exporter lives outside the forward package (`pbg/tools/`, rule M3: the engine never imports it), and
`pbg/tests/native/` skips when it is absent.

New tests worth stating explicitly: (a) every concrete task class in libsed2 has a PBG mapping *or* a deferred entry
(like `test_capabilities.py`); (b) every generated golden document constructs as a `Composite` without running;
(c) PBG and script outputs agree on every suite case, per backend; (d) a document with an id that cannot be a state
key is refused with a clear message; (f) the wrapper provider: every adapter on its own, `--wrappers strict` listing exactly the
ledger ids in the expected-gaps file; (e) the modularity rules M1 to M9 of section 3.11, as listed there.

## 8. Questions for you, and answers so far

| # | Question | Answer (2026-10-09) | Where it landed |
|---|---|---|---|
| 1 | File name | `NNNNN.pbg.composite.json`.  I think this is the best of both, not the worst: it ends in `.composite.json`, which the framework's discovery matches with any prefix (checked in `composite_discovery.py`), and `.pbg.` marks the origin next to `NNNNN.sed2.json`.  One wrinkle: the framework derives the document name `NNNNN.pbg` from the stem, harmless because the `name` key is written explicitly. | 3.2, summary |
| 2 | Own steps or community wrappers | Use the community wrappers when possible; a setting a wrapper cannot take is a bug or feature request for its maintainers.  Own steps are the fallback.  W-1 (tolerances and seed ignored by `TelluriumUTCStep`) was confirmed by running. | 3.12, summary, phases 2a/2b |
| 3 | Role in the suite | Some PBG-only cases (cosimulation), but try for equivalent Python scripts; definitely more advanced SED2 tests.  Follow-up: tier C scripts must be *translated* from the PBG documents, not hand-written. | Test tiers A/B/C, section 7 |
| 4 | How steps learn the directories | In the document, with defaults (a `context` store). | 3.10 |
| 5 | Windows | No need to test on your own machine; CI should cover as many platforms as possible. | 3.11 M8, phase 0 |
| 6 | The cosimulation file | Update it so the ODE times continue; both cases (as written and timed) eventually, once FBA exists. | 5.1 |
| 7 | An FBA backend | Pull in a good one if I can find it: COBRApy checked (3.13). | 3.13 |
| 8 | PBG to SED2 | Set aside: "let's see what we can do without it for now". | `process-bigraph-to-sed2.md` unchanged; tier C route 2 first (section 7) |
| 9 | Where FBA lives | In the main group (the host).  More sophisticated command-line switches are needed for two FBA simulators, for testing them against each other and in combinations (copasi with cobra, and so on). | 3.13 (H-1 to H-5), 3.14, phase 3b |
| 10 | Wrapper default | `--strict` for now. | 3.12, summary, phase 2b |
| 11 | Filing bug reports | Never by the assistant.  Always a file somewhere, and you report. | 3.1, 3.12, `pbg/upstream/` (14 drafts), `pbg/findings/` |
| 12 | COBRApy licence | Fine, as a dependency. | 3.13 |
| 13 | Tier C before the reverse direction | Do not wait: create tier C tests now. | Section 7 (scheduler exporter, cases C1 to C5) |
| 14 | The real CRM-FBA models | Look for them; mock something simple up regardless, and test the real ones too. | 3.13 (found: iAF1260 and four more; the CRMs are Python classes), 5.1 stages 3 and 4, mock pair delivered |

Earlier answers: the separate `pbg/` package and the small M1 host test were approved (3.11).

**Still open (none blocks the next step).**

1. **Start of the host work.**  H-1 to H-5 (3.13, 3.14) are host edits.  I read answer 9 ("in the main group") as the decision and will
   start them at phase 3b, additive and with tests, unless you want to approve each part first.
2. **The second FBA tool.**  `cobra:glpk` against `cobra:scipy` costs nothing and exercises the switches.  For a genuinely second tool, CBMPy is the
   candidate I know of; "PySCeS" as far as I know is a kinetic simulator (ODE and steady state), which would be a second *ode* backend
   instead.  Which did you mean?  (I will check both before relying on either.)
3. **The real models.**  The CRM-FBA repository has no licence file that I found, so the models are fetched at a pinned commit and not
   copied here.  If you prefer them stored in the repository, that needs the authors' permission first.
4. **Infeasible FBA.**  SED2 does not say what a `FluxBalanceAnalysis` task returns for an infeasible problem (found with iAF1260).  A
   draft question for the SED2 author is in `pbg/findings/sed2-fba-infeasible.md`; I did not add anything to SED2/TODO.md.

## Sources

* process-bigraph repository, README, `docs/architecture.md`, `docs/emitters.md`, `docs/tick_lifecycle.md`,
  `docs/concepts/composites-and-templates.md`, notebooks `tutorial_1` to `tutorial_3`, and the code of `composite.py`,
  `emitter.py`, `composite_spec.py`, `run_composite.py`, `processes/simulation.py`, `processes/parameter_scan.py`:
  https://github.com/vivarium-collective/process-bigraph (git e5325c1, version 1.8.5)
* viva-tellurium: https://github.com/vivarium-collective/viva-tellurium
* viva-copasi: https://github.com/vivarium-collective/viva-copasi
* viva-tellurium 0.1.2 and viva-copasi 0.1.2 (clones read; viva-tellurium run, 2026-10-09): https://github.com/vivarium-collective/viva-tellurium, https://github.com/vivarium-collective/viva-copasi
* COBRApy 0.32.1 (installed and run; package metadata for the licence): https://github.com/opencobra/cobrapy
* CRM-FBA (cloned at commit 4eba24c; models iAF1260, iJN746, iMM904, iCN900, iNF517 loaded and solved with COBRApy; CRM classes read): https://github.com/vivarium-collective/CRM-FBA, site https://vivarium-collective.github.io/CRM-FBA/
* CBMPy on PyPI (named as a candidate only; not installed or run): https://pypi.org/project/cbmpy/
* Agmon and Spangler, "Process bigraphs and the architecture of compositional systems biology", arXiv:2512.23754v2
  (14 Aug 2026), main text, S1 Text "Formal framework specification" (sections 3.2, 3.5, 3.7, 3.8) and S2 Text
  "Spatio-Flux worked example" (section 1.2.1 DynamicFBA, section 2 performance and COMETS comparison); read from PDFs
  supplied by you.  Summary in section 2.10.
* This project: build.md, CLAUDE.md, docs/libsed2-api-notes.md, docs/generated-script-contract.md, docs/deferred.md,
  docs/task-coverage-matrix.md, `src/pysed2translate/` (translate.py, core.py, runtime/), tests/golden/docs/
