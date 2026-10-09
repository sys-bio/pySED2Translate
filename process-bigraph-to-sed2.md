# Translating Process Bigraph to SED2

Status: a plan.  No survey, code or SED2 proposal has been written.  This is the reverse companion of
`process-bigraph.md` (SED2 to Process Bigraph); the two share a mapping table and a test harness, see section 7.
Written 2026-10-08; pointer to the clock analysis added 2026-10-09.  Facts about process-bigraph come from the research recorded in that file (version 1.8.5,
git e5325c1) plus the small check described in section 4.1.

## 1. Goals and what "success" means

1. **An importer**, `pbg2sed2`: read a Process Bigraph document and write a valid SED2 document when its content has a
   SED2 equivalent.  Where it does not, say exactly what, instead of producing a plausible approximation.
2. **A corpus survey**: find the process-bigraph documents that exist in the vivarium GitHub projects, normalize them,
   and count what they contain.  The survey is a result in itself and drives everything else.
3. **A gap analysis**: list the things process-bigraph models do that SED2 cannot say, ranked by how often they occur,
   and turn the most important into a proposal file in the SED2 repository describing tasks (processes) that SED2
   might add.

Success is not "convert as many documents as possible".  Following CLAUDE.md, a document is in exactly one of three
classes, and the importer says which, with reasons:

| Class | Meaning | Output |
|---|---|---|
| Translatable | Every node has a SED2 equivalent | A valid SED2 document |
| Partly translatable | A core experiment can be extracted, but named parts cannot | A SED2 document only with `--allow-loss`, plus a report listing every dropped node, wire and setting; never silent |
| Not translatable | The behaviour is in code or in coupling SED2 cannot express | No SED2; a report with the reasons (these feed the gap ledger) |

A SED2 document that the importer writes must pass libsed2 validation, run on the backends the capability table
allows, and agree with running the original document (section 6).  Anything else is a bug or a recorded disagreement.

## 2. Why the reverse is a different kind of problem

SED2 describes an experiment on a model: which model, which simulation, which outputs.  A process-bigraph document is
a *program*: a wiring of Python classes that are looked up by name and carry their own behaviour.  So:

* The forward direction is total on the supported subset of SED2.  The reverse is partial by nature.
* The meaning of a node is in the class named by its `address`, not in the JSON.  The JSON for a `TelluriumProcess`
  says nothing about what it does; knowing the class does.  The importer therefore recognizes nodes by a **table of
  known classes** (package, class name, version range), and treats every other address as opaque.
* A document does not say how long to run.  The run length is the argument of `Composite.run(T)`, the
  `--steps` option of `process_bigraph.run_composite`, or a spec's `default_n_steps`.  SED2 needs an end time.
* A document may not carry its model.  Wrappers take an Antimony string inline, an SBML file path relative to the
  working directory, or a URL.
* Process-bigraph is built for coupling: several processes advance together and exchange state through shared stores.
  SED2 runs independent tasks and passes whole results between them.  This is the largest conceptual gap and probably
  the main finding of the gap analysis.

Documents fall into tiers that decide how hard the job is:

| Tier | What it is | Expected outcome |
|---|---|---|
| A | One or more known SBML/Antimony simulator nodes (viva-tellurium, viva-copasi) with their emitters | Mostly translatable: modelImport, simulation, report |
| B | Stores and declarative math/calculation steps, with emitters | Translatable to constants and calculations, if the step classes are known |
| C | Documents produced by this project's own forward translator (`pysed2translate.pbg`) | Exactly invertible; our best test, and it needs no external corpus |
| D | Several coupled models, spatial, agent-based, or multiscale composites (the bulk of the ecosystem, judging by repository names) | Not translatable; feeds the gap ledger |
| E | Custom Python processes, generators that need code to run, anything opaque | Not translatable; counted, not analysed |

## 3. Reading documents safely

The corpus is other people's code.  Building a `Composite` imports and runs the classes a document names, so:

* **Static first.**  The reader parses JSON/YAML and never imports a process class.  Addresses are matched against the
  known-class table by name.  This is the default and the only mode in the first phases.
* **Introspection later, sandboxed, opt-in.**  Reading a class's ports (`inputs()` / `outputs()`) would improve
  classification but needs importing the package.  If it is ever done: a separate environment per repository, pinned
  to a commit, no network, and clearly flagged in the report.  The `git:` address protocol in process-bigraph already
  isolates foreign code this way; reusing it is an option to evaluate, not to assume.
* Cloned repositories are untrusted data: each goes into its own new directory and is read, not executed.

Source forms to handle, in the order they will be added:

1. `*.composite.json|yaml|yml`: the repository's own convention.  Header fields `name`, `description`, `requires`,
   `parameters` (with `${name}` placeholders and defaults), then `state`.  The importer resolves placeholders to their
   defaults and records that it did.
2. Saved documents (`Composite.save`, bundles) and `*.template.*` files with unfilled "sites" (holes).  A document with
   an open site is not runnable and is classified "not translatable: template".
3. Document literals inside Python and notebooks (`{'_type': 'process', 'address': ...}`), found by pattern or by Python's
   `ast` module.  Many are built from helper functions (`make_tellurium_document(...)`, `emitter_from_wires(...)`), which
   a static reader cannot evaluate without running them.  First pass: extract only literals; record the rest.
4. Generators (`@composite_generator`): code that builds a document.  Needs execution; phase R7, sandboxed, optional.

## 4. The corpus survey

### 4.1 What is already known

* process-bigraph's own design note (docs/superpowers/specs/2026-06-28-composite-spec-unified-declaration-design.md)
  says an audit covered "93 `*.composite.{yaml,json}` files across ~20 pbg-* repos", 13 `@composite_generator`
  generators in v2ecoli, and about 12 `study.yaml` files.  It names the repositories (autopoiesis, bioreactordesign,
  membrane-actin, tyssue, copasi, tellurium, smoldyn, martini, comets, mem3dg, cellpack, yalla, biomodels, nfsim,
  readdy, medyan, lammps, compucell3d, parsimony, caspule).  Most are not SBML simulators, which already predicts that
  tier D is the majority.
* A quick count in the three clones I have (process-bigraph, viva-tellurium, viva-copasi): 6 standalone composite
  files (3 + 3), but about 30 files containing document literals in Python or notebooks.  So many documents live in
  code, and a survey that reads only `*.composite.*` files will undercount.
* The `pbg-*` repositories were renamed `viva-*`, with import shims (`pbg_tellurium` redirects to `viva_tellurium`).
  Recognition must accept both names.
* The paper's Supplement 1 (read 2026-10-09) shows the canonical JSON as a `schema` tree plus a `state` tree with
  `stores` and `processes` sub-trees; the 1.8.5 documents examined here are one `state` tree whose nodes carry `_type`.
  The importer must expect both shapes (whether 1.8.5 loads the supplement's shape is untested).  Supplement 2 and the
  Spatio-Flux repository are a ready corpus of real composites (metabolic, field, particle processes, `DynamicFBA` with
  COBRApy); add it to the survey list.  Everything here is subordinate to the modularity rule of
  `process-bigraph.md`, 3.11: the reverse direction is its own package.

### 4.2 Enumeration, and a constraint found while researching

Listing the organisation's repositories through the GitHub API was **refused in this session** (organisation endpoints
and GraphQL are blocked; the session is bound to named repositories).  Cloning a named public repository and fetching
its web page both worked.  So the list has to come from one of:

* the user's own machine (`gh repo list vivarium-collective --limit 300`), saved as a file this plan reads;
* a seed list assembled by hand from the names above plus the organisation's web page, repository by repository;
* attaching repositories to the session one at a time.

Open question 2 asks which.  Whatever is chosen, the list is stored as part of the corpus manifest so the survey can be
repeated.  Do not retry anything that answers 429 (CLAUDE.md).

### 4.3 Procedure (phase R1, no translation)

1. Build the repository list (including archived and forked repositories, marked as such).  Decide the scope beyond
   `vivarium-collective`: for example `CovertLab/vEcoli`, which builds on process-bigraph (question 2).
2. For each repository: shallow clone into a new directory, record the commit SHA and the licence file, and never
   execute anything.
3. Find candidates: `*.composite.*`, `*.template.*`, `study.yaml`, saved bundles, notebooks and Python files matching
   `'_type'`/`"_type"` with `process` or `step`, `composite_generator`, `Composite(`, `emitter_from_wires`.
4. Extract each document into a normalized form: JSON, parameters resolved to defaults, with a manifest entry
   (repository, SHA, path, source form, licence, how it was extracted).
5. Inventory each document with a script: node counts by kind; the address histogram; port types; emitters used; config
   keys by class; intervals; nesting and bridges; sites; whether there is a model reference; and which tier it is.
6. Generate `SURVEY.md` from the inventory (never written by hand): counts per tier, top addresses, top config keys,
   and a table of the repositories with no extractable documents.

Deliverables of R1: the manifest, the normalized documents (or only hashes and extraction scripts where the licence
does not allow copying; question 1), `SURVEY.md`, and gap ledger v0 (section 5.2).  R1 needs none of the forward
translator, so it can run alongside forward phases 0 and 1.

## 5. Importer design and the gap ledger

### 5.1 Pipeline

```
load  ->  normalize (resolve ${...}, unify yaml/json)  ->  classify nodes (known / opaque)  ->  tier the document
      ->  map (section 5.3)  ->  emit SED2 + report, or refuse with reasons
```

Command line: a separate program, `pbg2sed2 DOC --out NNNNN.sed2.json --report NNNNN.import.json`, because the direction
and inputs differ from `pysed2translate`.  Exit statuses mirror the forward program: 0 written, 10 unreadable, 11 not
translatable (reasons printed and in the report), 12 other error, plus 13 for "partly translatable, nothing written
because `--allow-loss` was not given".  The report is JSON with three lists: mapped, dropped, unsupported, each entry
naming the node path and the reason.

### 5.2 The gap ledger

Every refusal and every dropped item is also a row in `gaps.json` (machine-written, curated later): the construct, how
many documents and repositories contain it, one example path, why SED2 cannot say it, the nearest SED2 element, a
candidate addition, and a category (task, data type, model language, output, run semantics, out of scope).  Keeping it
as data from the first run means the proposal file in section 6 is a curated view of evidence, not an opinion.

### 5.3 Planned mapping (to be confirmed on real documents)

| Process-bigraph construct | SED2 | Notes |
|---|---|---|
| Plain store value never written by any node | `constants` | |
| Declarative math step (known class) | `calculation` | Expression syntax converted to SED2 math; unsupported functions refuse. |
| `TelluriumUTCStep`, `CopasiUTCStep` (start, end or time, n_points) | `modelImport` + `explicitODESimulation` + `report` | n_points versus numberOfSteps differ by one; test explicitly. COPASI wrapper starts at 0. |
| `TelluriumProcess`, `CopasiUTCProcess` with `interval` | `explicitODESimulation` with a uniform range | Only when the run length is known (section 2) and no other node is wired to the same stores. Otherwise tier D. |
| `TelluriumSteadyStateStep`, `CopasiSteadyStateStep` | `steadyState` | |
| `species_overrides`, `parameter_overrides` | `modelChange` `setValues` | |
| `integrator: cvode` and tolerances | KiSAO algorithm and tolerances of the simulation | `gillespie` is a stochastic task, deferred in SED2 tests. |
| `model_file`, `model_source` | `modelImport.location`, language SBML | Antimony inline: converted to SBML with libAntimony at import (decided, section 11). |
| `RAMEmitter` and similar, wired to some paths | `report` over references to the task outputs | Rows per tick become a time-course table; labels from port names. Other emitters (JSON, SQLite, Parquet) are storage choices SED2 does not model; recorded as a gap. |
| Declarative visualization steps | `plot2D` | Only where the data wired in is a simulation output. |
| Parameter sweeps inside a document (`RunProcess` and similar) | `parameterScan` / `loop` | Check against the actual classes in the corpus. |
| Anything wired between two simulator nodes, dynamic structure, spatial fields, agents | none | Gap ledger. |

### 5.4 Recognition table

`known_classes.json` maps (package, class, version range) to a handler.  It is the reverse of the forward translator's
table of step classes (section 7).  Both names of a renamed package are listed.  An address not in the table is opaque:
the node and everything wired only to it are reported as unsupported.

## 6. Verification

For every document the importer translates (not only tier C):

1. **Validate** the SED2 output with libsed2; refuse to write one with errors.
2. **Run the original** document with its original packages, in an environment prepared for that tier (heavy: COPASI,
   Tellurium; tier A only), and keep its emitter output.
3. **Run the SED2** through `pysed2translate` on every backend the capability table allows.
4. **Compare** with the suite's rules (|a-e| <= abs + rel*|e|, labels, shape).  The original's tolerances are mapped
   explicitly into the SED2, so differences are not hidden by defaults (CLAUDE.md: tolerances are set, not left
   alone).
5. A disagreement is analysed, not tuned away: is it the wrapper, the simulator, the importer, or a specification
   ambiguity?  Wrapper and simulator disagreements go to `sed2-test-suite/disagreements.json`; specification
   questions go to `SED2/TODO.md` (new section at the end); an importer bug is fixed with a test that fails without
   the fix.  A reasonable first suspect list is the off-by-one in output points, the initial time, and COPASI/roadrunner
   default tolerances.

Note on names: "tier C" in this section is an *importer* test tier (our own forward output).  The forward plan's *test* tier C
(`process-bigraph.md`, section 7) is different: PBG-native documents whose expected data comes from a Python script
**translated** from the document.  The importer is route 1 for those scripts (PBG -> SED2 -> host script), which makes the
importer's output the oracle for the forward engine and the forward engine's output the check on the importer; a second,
smaller translator (a scheduler exporter) covers documents SED2 cannot express.  So the importer gains a customer before
the survey finishes.

Tier C (our own forward output) is invertible by construction, so `SED2 -> PBG -> SED2` must be the identity up to a
canonical form (ids, key order, defaults).  That test needs only the forward translator and runs in CI without any
external package, which makes it the first test the importer passes.

## 7. Parallels with the forward plan

| Forward (SED2 to PBG) | Reverse (PBG to SED2) | Shared |
|---|---|---|
| Phase 0: skeleton, runner | R0 and R1: decisions, survey | A manifest-and-golden-files habit |
| Step classes `pysed2translate.pbg.steps` | `known_classes.json` | **One mapping module**, `pbg/mapping.py`, from which both are generated or checked; a test fails if a step class has no reverse entry or the reverse names a class that does not exist |
| Capability table says which backend runs a task | Same table decides which imported tasks are runnable | `capabilities.json` unchanged |
| Golden PBG documents in `tests/golden/pbg/` | The same documents are the tier C inputs | One set of goldens, two directions |
| Exit status 11 = skip with reason | Exit status 11 = not translatable with reasons | Same reporting style |
| Gaps found go to SED2/TODO.md | Gaps found go to the ledger, then the proposal file | CLAUDE.md rules apply to both |

Dependencies: R1 and R2 are independent of the forward work.  R3 needs the SED2 side of the capability table only.  R5 (tier C)
needs forward phase 2.

## 8. Phases

Each phase ends with passing tests and a short report to you; no phase starts before the one it depends on is green.

* **R0 - decisions and scaffolding.**  Answer the questions in section 11.  Fix the manifest format, the report format and the file
  layout.  No external access.
* **R1 - survey.**  Section 4.3.  Output: manifest, normalized documents, `SURVEY.md`, gap ledger v0.  Review point: do the numbers
  match the "mostly tier D" prediction?  This decides how much of R3 onward is worth doing.
* **R2 - reader.**  Static loader for `*.composite.*` with parameter resolution and node classification; tier assignment.  Tests on the
  six viva-tellurium and viva-copasi files and on synthetic documents for each tier.
* **R3 - importer for tiers A and B.**  Mapping of section 5.3, report, `--allow-loss`.  Tests: a golden SED2 and report per input.
* **R4 - verification harness.**  Section 6, steps 2 to 5, on tier A.  First entries in the disagreement log if any.
* **R5 - round trip.**  Tier C, after forward phase 2.
* **R6 - proposal file.**  Curate the ledger into the SED2 proposal (section 9).  You review it before it is written into the SED2 repository.
* **R7 - optional.**  Document literals found by `ast`; generators in a sandbox.

Files (in this project, all new):

```
src/pysed2translate/pbgimport/reader.py       # load, normalize, parameter resolution
src/pysed2translate/pbgimport/classify.py     # known/opaque nodes, tiers
src/pysed2translate/pbgimport/known_classes.json
src/pysed2translate/pbgimport/emit.py         # SED2 construction through libsed2; report writer
src/pysed2translate/pbgimport/cli.py          # pbg2sed2
scripts/pbg_survey.py                         # R1: clone, extract, inventory, SURVEY.md
tests/test_pbgimport_*.py
```

The corpus itself (manifest, normalized documents, SURVEY.md, gaps.json) does not belong in `src/`; see question 1.

## 9. The SED2 proposal file

A new file in the SED2 repository, name and folder to be chosen (suggestion: `SED2/proposals/process-bigraph-tasks.md`).
Per CLAUDE.md, the SED2 repository and specification are maintained by someone else.  This file is the one addition you
asked for; the plan does not change `TODO.md`, the specification or libsed2, and the file proposes, it does not
specify.  This session currently has only the pySED2Translate folder connected, so writing it needs the SED2 folder to
be connected.

Each candidate entry will contain: a proposed task name; the purpose in SED2 terms; inputs and outputs as SED2 data (what
AnnotatedData shape comes out); parameters; what process-bigraph does today (one real example from the corpus, with the
repository and commit); which simulators could implement it; how it could be tested with an analytic result in the suite;
and the open questions.  Entries are ordered by corpus evidence (how many documents and repositories), then by how well
they fit SED2's task model (a task with inputs and outputs and no hidden state).  Items that do not fit (distributed
execution, caching, UI) go in a short "considered and left out" section so they are not rediscovered.

Candidate topics to test against the corpus.  These are **hypotheses from reading process-bigraph and its wrappers, not
findings**, and I have not been able to read the current SED2 specification in this session to check each one:

1. Coupled simulation: several models advancing together and exchanging state each interval (operator splitting,
   multi-timestepping).  **Narrowed** after the clock analysis in `process-bigraph-clock.md` (read that file first):
   sequential operator splitting on one clock is already expressible as a SED2 Loop (the cosimulation test case,
   `process-bigraph.md` 5.1).  Parallel coupling with additive merge (same interval, shared state; measured to
   give different numbers from the sequential scheme) is *also* expressible today, as branches that read only the loop
   variables (sibling sub-tasks, or a Scatter nested in the Loop) plus an explicit merge Calculation; what is missing is
   a label for the scheme and a short merge for model-valued variables.  What SED2 cannot say is multiple intervals on
   one timeline, adaptive intervals, conditional termination and continuation state.  The survey (R1) should classify every document
   by which of these it uses; proposals P1 to P5 in that file are the candidate entries here.
2. Incremental stepping with state hand-off.  SED2 has `oneStepODESimulation` and `.model`; check whether that already
   covers it.
3. Parameter estimation and fitting (viva-copasi has a `ParameterEstimationStep`).
4. Dynamic and hybrid FBA (SED2 defers FBA itself; dynamic FBA couples it with an ODE environment).
5. Spatial and particle models (Smoldyn, ReaDDy, MEDYAN, LAMMPS, CompuCell3D, tyssue): model languages, spatial output types.
6. Rule-based and stochastic simulators (NFsim; Gillespie in the wrappers): relation to the deferred stochastic tasks.
7. Dynamic structure: growth, division, creation and removal of components during a run.
8. Event-driven and conditional execution, gating (process-bigraph's templates and sites).
9. Studies as tasks: sensitivity, uncertainty quantification, sweeps over a composed model (the "study" layer in
   viva-superpowers).
10. Unit-aware ports and automatic conversion (`_units`).
11. Output persistence and streaming (SQLite, Parquet, JSON emitters) versus SED2 reports.
12. Provenance: pinned code versions and content-addressed results versus SED2 annotations.

The corpus decides which of these survive; expect some to drop out and others to appear.

## 10. Risks

* **Sampling bias.**  The corpus is mostly written by one group, and many documents are demos.  Counts show what is in
  the ecosystem, not what scientists need.  `SURVEY.md` will say this.
* **Recognition by name is fragile.**  Renames, shims and subclassing can hide a known class.  Version ranges in the
  recognition table and a test per entry reduce, not remove, this.
* **Hidden semantics.**  Defaults inside wrapper code (tolerances, start time, how many points) are not in the document.  They are
  read from the wrapper's source for each version and written into the recognition table, then checked by the
  verification run, not assumed.
* **Run length** is outside the document (section 2).  Taking it from `default_n_steps` is a guess when only a spec
  provides it; the report records where each value came from.
* **Licences.**  Check before copying a document into any repository.
* **Rate limits and blocked endpoints** (section 4.2).  The survey must be restartable and must record what it could not reach.
* **Original packages are heavy** to install for the verification run; only tier A is attempted.
* **A moving target.**  Repositories change, which is why every item is pinned to a commit.

## 11. Questions for you, and answers so far

Answers given 2026-10-08.  This direction is set aside; the work now is SED2 to Process Bigraph
(`process-bigraph.md`).  Pick these up again when the reverse work starts.

| Question | Answer so far |
|---|---|
| 1. Where does the corpus live, and may copies be committed? | Probably a new GitHub repository (tentative). Whether copies may be committed is not decided; that needs the licence check. |
| 2. How is the repository list built, and what is the scope? | Open. |
| 3. Name and place of the SED2 proposal file | Open. The SED2 and sed2-test-suite folders are now connected to the session, so the file can be written when the time comes. |
| 4. Partial translation (`--allow-loss`) | Open. |
| 5. Inline Antimony models | **Decided:** translate them to SBML with libAntimony at import. |
| 6. Run length when the document gives none | Open; the plan's assumption stands until answered. |

The questions as asked:

1. **Where does the corpus live, and may copies be committed?**  Options: a new directory in this project, a separate
   repository, or only a manifest plus extraction scripts (nothing copied).  The last needs no licence check.
2. **How should the repository list be built?**  The API is blocked in this session.  Can you save the output of
   `gh repo list vivarium-collective --limit 300 --json name,description,isArchived,pushedAt,licenseInfo` on your machine into the
   project?  Also: is the scope only `vivarium-collective`, or also projects that merely use process-bigraph (for example
   `CovertLab/vEcoli`)?
3. **Name and place of the SED2 proposal file**, and will the SED2 folder be connected when R6 comes?
4. **Partial translation.**  Is "SED2 for the extractable core plus a loss report, only with `--allow-loss`" acceptable, or
   should the importer be all-or-nothing?
5. **Antimony models.**  SED2 imports models by location and language.  Should the importer convert an inline Antimony string to
   an SBML file (the suite already uses antimony for its inputs), or refuse?
6. **Run length.**  When a document does not give one, should the importer refuse, take `default_n_steps` if present, or take a
   `--duration` argument?  The plan assumes: `--duration` if given, else `default_n_steps` with the source recorded, else refuse.

## Sources

* process-bigraph repository (README, docs/, composite_spec.py, composite_discovery.py, the 2026-06-28 CompositeSpec design
  note): https://github.com/vivarium-collective/process-bigraph (git e5325c1, version 1.8.5)
* viva-tellurium: https://github.com/vivarium-collective/viva-tellurium
* viva-copasi: https://github.com/vivarium-collective/viva-copasi
* This project: `process-bigraph.md`, build.md, CLAUDE.md, docs/deferred.md, docs/libsed2-api-notes.md
