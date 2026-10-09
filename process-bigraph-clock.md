# SED2 and Process Bigraph's clock: what SED2 cannot say, and how to extend it

Status: analysis and proposals.  Nothing here is implemented, and nothing here has been put into the SED2 repository
(those files belong to the SED2 author; per CLAUDE.md a proposal goes in a new section at the end of `SED2/TODO.md`,
which is a later step, phase R6 of `process-bigraph-to-sed2.md`).  All SED2 snippets are sketches in the current
`_type` syntax and have **not** been checked with libsed2.
Researched 2026-10-09 against process-bigraph 1.8.5 (git e5325c1).  "Tested" means run in a scratch environment
(experiments listed in `process-bigraph.md`, section 2.9); "read" means found in the source or documentation only.

The paper (arXiv:2512.23754v2) and its two supplements were read on 2026-10-09; what they say about orchestration is
folded into section 2 below and into `process-bigraph.md`, section 2.10.

Companion files: `process-bigraph.md` (SED2 -> PBG plan, including the cosimulation test case, section 5.1) and
`process-bigraph-to-sed2.md` (the reverse plan, set aside for now).

## 1. Summary

1. **What works.**  A SED2 `Loop` really is a clock.  Its range is the tick sequence, `.index` and `.range` are the clock
   readings, `loopVariables` are the state handed from tick to tick, and the sub-tasks are what runs at a tick.  The
   attached cosimulation document therefore translates to a process-bigraph clock loop (`process-bigraph.md`, 3.8 and
   5.1) with the sub-tasks as steps.  That is the case where **sequential operator splitting** is wanted, and SED2
   already says it.
2. **Parallelism is also already there.**  (Corrected after your question about Scatter.)  Tasks that do not reference
   each other are independent by construction, so a SED2 task graph is already a parallel-friendly DAG; `Scatter` says
   "these iterations are independent, run them in parallel if you like" for many copies of one body; and any task may sit
   inside a Loop or a Scatter.  So *simultaneous coupling* of the process-bigraph kind is expressible today: in each
   Loop iteration the branches read only the loop variables (not each other), either as sibling sub-tasks or as a
   Scatter, and a Calculation merges their results into the next loop variable.  Tested: a Scatter nested in a Loop that
   reads the loop variable validates with libsed2 (0 problems).  Many identical processes (Spatio-Flux's per-cell
   `DynamicFBA`) are exactly Scatter-in-Loop.
3. **What SED2 cannot say about the clock** is therefore narrower than first written: (G1) several processes with
   *different* intervals on one timeline, (G3) a process that chooses its own next step (adaptive interval), (G4)
   running until a condition rather than for a fixed count, and (G5) a process that keeps internal state between ticks.
   (G2) *simultaneous coupling* is expressible but not *nameable*: nothing says "these branches read one snapshot and
   their changes add", the merge is an explicit Calculation, and for a model-valued loop variable that merge is
   heavy.  Two more (G6 dynamic structure, G7 event-driven steps) are not worth importing.
4. **The distinction that still matters** is semantic: the same two models give different numbers when chained
   sequentially and when run as parallel branches on one snapshot (tested: after one tick the second state is 0.125
   sequentially and 0.25 in parallel, section 2).  Both are writable in SED2; a reader (or a reverse translator) can
   only tell them apart by inspecting which references the sub-tasks make.  A label would help (P1, now optional).
5. **Proposals** (section 5), ordered by value for the cost: P2 a `Clock` as a range with a *time* meaning and
   per-sub-task periods (G1); P3 `Loop.until` with a mandatory `maxIterations` (G4); P1 an optional `evaluation` label
   and `combine` rule for parallel branches (G2, convenience and recognisability, not expressiveness); P4 a `nextRange`
   expression for adaptive steps (G3); P5 continuation state as a first-class task output (G5).  P6 and P7 are listed
   as "do not add".  Each proposal keeps the SED2 invariant that the shape of the result is known before running (rows
   padded to `maxIterations`, plus a count).

## 2. What Process Bigraph's clock is

The facts that matter, with their status.

| Fact | Status |
|---|---|
| A **process** is a node with an `interval`.  Global time is the `global_time` store; it advances to the earliest due process; a process due at t reads the state, runs `update(state, interval)` and its update is applied at the *end* of its interval. | Tested |
| Each process reads a **snapshot taken at the start of its interval**.  Two processes with equal intervals both read the state as it was before either update (Jacobi coupling).  A process with a longer interval reads a stale snapshot. | Tested |
| An update is **merged by the type of the output port**: `float` adds a delta, `overwrite[T]` replaces, `map[...]` merges per key.  So coupling by addition ("both processes change this store") is a property of the *type*, not of the process. | Tested (`float` delta, `overwrite`); other merges read |
| `Process.calculate_timestep(interval, state)` lets a process **shorten or choose** its own interval from the current state. | Read (hook in `composite.py`; not exercised) |
| **Steps** (no interval) run when an input path is updated, in dependency order, at every tick that updates it.  A step downstream of a process re-fires every tick. | Tested |
| All steps with no ready input fire once at the start of `run()`, even with `run_steps_on_init: false`. | Tested |
| `Composite.run(T)` runs until `global_time` reaches T; there is no "run until" a condition in the framework (a step or process could stop producing updates; nothing ends the run). | Read |
| A process is an **object with state between ticks** (the Python instance lives as long as the composite). | Tested (the clock keeps its counter) |
| **Dynamic structure**: updates may contain `_add`, `_remove` and `_divide` sentinels that create or delete nodes and stores while the run is in progress (cells appear and divide). | Read (`composite.py`, `processes/dynamic_structure.py`, `growth_division.py`) |
| **Specification versus implementation.**  The formal small-step rule (S1 3.8.2) updates all processes due at the same event time "conceptually in parallel when their deltas commute", reading inputs at the event time; deltas to one store are combined and *reconciled* by a type-specific rule before they are applied (S1 3.8.3).  So parallel reads for equal intervals are specified behaviour.  For unequal intervals the rule reads at the event time while the implementation reads at the start of the process's interval (row above); the text does not settle which is meant. | Read (S1) against tested (implementation) |
| A Composite is itself a Process, so clocks nest, and a Step may host a whole inner composite (`SimulationStep`, `RunProcess`). | Read; the hosting pattern tested |
| `ProcessEnsemble`, `BigraphicalReactiveSystem`, `ReactionStep`: reaction-like and rewrite-rule processes. | Read |

Numbers behind the second row (tested, `x' = x + 0.5 (y - x)`, `y' = y + 0.25 (x - y)`, start x = 1, y = 0):

| Scheme | After tick 1 (x, y) | After tick 2 (x, y) |
|---|---|---|
| Two processes, equal intervals (process-bigraph, measured) | 0.5, 0.25 | 0.375, 0.3125 |
| Same updates computed in parallel by hand | 0.5, 0.25 | 0.375, 0.3125 |
| Same updates in sequence, second reads the new x (what a SED2 loop with two chained sub-tasks does) | 0.5, 0.125 | 0.3125, 0.171875 |
| Intervals 1 and 2 (p2 slower) | t=1: 0.5, 0.0 | t=2: 0.25, 0.25 (p2 used the t=0 snapshot) |

## 3. What a SED2 Loop can already say about a clock

| Process-bigraph | SED2 | Fit |
|---|---|---|
| A tick, k = 0, 1, 2, ... | `Loop` iteration; `#tasks:loop.index` | exact |
| Time at tick k = k * interval | `#tasks:loop.range` (a `numericRange`) times a constant, via a Calculation | works, but nothing says the range *is* time |
| State handed to the next tick | `loopVariables` (`initialValue`, `subsequentValues`) | exact |
| What runs at a tick | `subTasks`: any task, in reference order; siblings that do not reference each other are independent; a `Scatter` for many copies of one body | exact, sequential or parallel as the references say |
| Several processes reading one snapshot and merging their changes | branches that read only loop variables (siblings or a nested Scatter) plus a Calculation that merges | expressible; the intent is not labelled and a model-valued merge is verbose (G2) |
| Observation of every tick (emitter) | `outputVariableMap` + `Report` | exact |
| A model advanced by an integrator for one interval | `explicitODESimulation` etc. restarting from the previous `.model` | exact; the integrator restarts (see G5) |
| Two models alternating (the cosimulation) | `ModelChange` with `setValues` from the other simulation's result | works; id mapping is the author's job |

So the single-clock, sequential case is covered.  Everything below is about leaving that case.

## 4. Where SED2 cannot express the clock

Each gap lists the process-bigraph behaviour, why SED2 cannot say it, what the translator does today, and which
proposal in section 5 addresses it.

### G1 - Several processes with different intervals

*PBG.*  A fast process (interval 0.1) and a slow one (interval 1.0) share a timeline; the slow one sees the fast one's
state as of the start of its interval (implementation; the formal rule in S1 3.8.2 may mean the state at its event
time, section 2).  The framework schedules by the earliest due time.  Because of that open point, P2's "stale read" rule
below is written against the implementation and should be confirmed with the process-bigraph authors before it goes into
a specification.

*SED2.*  A loop has one range.  A sub-task runs at every iteration.  One can emulate multi-rate by hand (an outer loop of
the slow clock with an inner loop of ten fast iterations), but only when the intervals are integer multiples, the
nesting is written out, and the stale-read behaviour (the slow task reads state from the start of its interval) is not
what the nested form gives (the fast loop finishes before the slow task reads).  Non-commensurate intervals (0.3 and
0.5) cannot be written at all.

*Translator today.*  Sequential loops only.  A PBG document with unequal intervals (reverse direction) is **not
translatable** except for commensurate cases, and then only if the author accepts a different numerical scheme.

*Proposal.*  P2.

### G2 - Simultaneous (parallel) coupling and additive updates

*PBG.*  Equal-interval processes read the same snapshot and their updates merge by type (deltas add).  This is
the standard way to couple models that act on shared state "at the same time", and it is order independent.  The
specification adds *reconcilers*: when several deltas hit one store they are combined by a type-specific rule (summed for
numbers, put in a canonical order for structural edits), so the merge is a property of the store's type.

*SED2.*  Expressible today, in three ways, all of which keep the parallelism visible in the reference graph:

1. **Sibling sub-tasks of a Loop that read only the loop variables** (never each other): by construction they are
   independent and see the same snapshot; the next loop variable is a Calculation that merges them, for numbers and
   arrays `x + (r1 - x) + (r2 - x)`.
2. **A `Scatter` inside the Loop** for many copies of one body (one per cell, particle or site): each iteration reads its
   own slice of the loop variable, the Scatter stacks the results, a Calculation or the stack itself becomes the next loop
   variable.  This is the Spatio-Flux per-cell pattern.  Tested: Scatter in Loop, Loop in Loop and Scatter in Scatter all validate (0 problems; validation only, nothing was run).
3. **A `Scatter` of Loops or a Loop of Scatters** as the problem requires; any task can be inside a Loop or a Scatter.

What SED2 does not have: (a) a statement of *intent* ("these branches are one coupling step; their changes add"), so a
reader cannot tell a parallel scheme from a sequential one without tracing references; (b) a merge for **model-valued**
loop variables: `ModelChange` replaces values, so merging two branches' changes to one model means extracting species or
parameter values (ModelElementList, Calculation, RelabelData), summing the changes, and writing the result back with a
ModelChange: possible, long, and easy to get wrong; (c) any notion of reconciling non-numeric updates.  The numbers differ
from the sequential scheme (section 2 table), so the choice between the two is a real modelling choice that the
document makes only implicitly.

*Translator today.*  Forward: the reference graph decides; sibling sub-tasks that do not reference each other are
independent and may run in dependency layers, a Scatter inside the Loop is a nested `SedRepeat` step inside the inner
composite (`process-bigraph.md`, 3.8).  Reverse: a PBG document with equal-interval processes sharing a store maps to a
Loop whose branches read the loop variables, plus an explicit merge Calculation; this is *translatable today* for
numeric and array stores, and the reverse translator must emit the explicit snapshot reads, never a plain sequential
chain (which would silently be a different scheme).  Model-valued merges are the hard case.

*Proposal.*  P1, now optional: a label and a merge rule, so that the pattern above is declared and not reverse
engineered.  Not an expressiveness gap.

### G3 - A process that chooses its next interval

*PBG.*  `calculate_timestep` can return a shorter step depending on state (adaptive coupling, event handling, error
control).  The clock then has non-uniform ticks decided during the run.

*SED2.*  The range of a Loop is fixed before the loop starts and "cannot end early".  SED2 ranges can be non-uniform
(an explicit `values` list, `log10` scale), but they cannot depend on results.

*Translator today.*  Not translatable; a PBG process whose `calculate_timestep` is overridden is refused.

*Proposal.*  P4 (and P3 is a prerequisite for open-ended runs).

### G4 - Run until a condition

*PBG.*  The host decides how long to run; documents often run "until the population reaches N" or "until a steady
state" by wrapping `run()` in a Python driver, not in the document.  Within the document nothing ends the run
either, so this is mostly a gap of the *drivers around* process-bigraph, and of what the reverse translator sees as
intent.

*SED2.*  `Loop` has a required range and cannot end early; `SteadyState` is a separate simulation.  A converged
fixed-point iteration or "stop when the FBA growth rate falls below x" is impossible, or needs a worst-case range with
dead iterations that still run their sub-tasks.

*Proposal.*  P3, with a mandatory `maxIterations` so that the result keeps a known shape.

### G5 - A process with internal state between ticks

*PBG.*  A process instance is long-lived: an integrator keeps its step-size history, a stochastic simulator keeps its
random generator, a wrapped simulator keeps its Jacobian or factorisation.  Continuing is cheap and exact.

*SED2.*  State between iterations is whatever the `.model` carries (end values of the model).  A new simulation restarts
the integrator: the result of 100 intervals of length 20 is not identical to one interval of length 2000, at the
solver's tolerance.  For a stochastic simulation the generator state is not part of the model, so a loop of short
stochastic runs cannot be made equivalent to one long run, and cannot even be reproduced from a seed unless every
iteration is given a derived seed.

*Translator today.*  Restart semantics.  Differences are within tolerance for ODEs and are a real difference for
stochastic runs (stochastic is out of scope for now).

*Proposal.*  P5.

### G6 - Dynamic structure (not recommended)

*PBG.*  `_add`, `_remove`, `_divide` change the set of nodes during a run (a cell divides, an agent dies).  The size
of the output is not known in advance.

*SED2.*  The whole language assumes a static task graph and result shapes known before running.  Dynamic structure would
remove that, and with it the ability to check a document without running it.

*Recommendation.*  Do not extend SED2.  A PBG document that uses these constructs is simply out of scope for the reverse
direction, and the report should say so in one line.  A restricted case ("a fixed set of agents, some of them
inactive") is already a Scatter over a list with a mask.

### G7 - Event-driven steps (not recommended as a separate construct)

*PBG.*  Steps fire when inputs change: derivers, reaction steps, mass listeners.  In a SED2 loop a derived quantity is a
sub-task that runs at every iteration, which is the same thing, so nothing is missing inside a loop.  What SED2 lacks is
firing *between* ticks (on an event in the middle of an interval), which belongs to the simulation (SBML events), not
to the task layer.

*Recommendation.*  Nothing to add.  Note the difference in the reverse report: a PBG deriver downstream of a process
becomes a sub-task of the loop, and its firing count equals the tick count.

### G8 - Smaller points

* **Time is not a first-class value.**  `global_time` is a store anyone can read; in SED2 the nearest is the range of
  the loop, with no statement that it is time.  P2 fixes this.
* **Time precision.**  `global_time_precision` rounds times.  SED2 has no equivalent, and needs none until P2.
* **Where steps run at start.**  All steps fire once before the first tick with default inputs (tested).  Nothing in
  SED2 corresponds, and the translator hides it (the index guard in `process-bigraph.md`, 3.8).  A PBG document
  written for the framework's behaviour may *depend* on that first firing (initial values derived from other stores).
  The reverse translator needs a rule: a step with no process upstream is a task before the loop.

## 5. Proposed SED2 extensions

These are proposals for the SED2 author.  They are small on purpose, keep the "result shape is known in advance" rule,
and are ordered by value.  The sketches use the current syntax and are not validated.

### P1 - an `evaluation` label and `combine` rules for parallel branches (optional)

Parallel branches can already be written (G2).  This proposal only makes them *declared and checkable*.

Add to `Loop` an optional `evaluation`:

* `"sequential"` (default; today's meaning): each sub-task may read its siblings' results of the same iteration.
* `"parallel"`: sub-tasks read only the loop variables and outer tasks, never a sibling of the same iteration (a
  validation rule: a reference to a sibling's result is an error).  This is a *checkable assertion about a document that
  could be written today*, like Scatter's "iterations are independent", and lets a reader and a reverse translator
  recognise the coupling scheme without tracing references.

Add to each loop variable an optional `combine`, used only with `parallel`: how the results of several sub-tasks that
write the same variable are merged into `subsequentValues`.  This removes the long Calculation (and, for models, the
extract-sum-ModelChange chain).

```json
"repeat": {
  "_type": "loop",
  "evaluation": "parallel",
  "range": { "_type": "numericRange", "start": 0, "end": 2, "numberOfSteps": 2 },
  "loopVariables": {
    "x": { "initialValue": "#constants:x0", "combine": "sum-of-changes",
           "subsequentValues": ["#tasks:repeat:subTasks:p1.data", "#tasks:repeat:subTasks:p2.data"] }
  },
  "subTasks": { "p1": { "...": "reads #tasks:repeat:loopVariables:x" },
                "p2": { "...": "reads #tasks:repeat:loopVariables:x" } }
}
```

`combine` values to start with: `"replace"` (exactly one writer allowed), `"sum-of-changes"` (new = old + sum of
(result - old); for a model-valued variable, applied to the values of the model elements that changed), nothing else.
This is process-bigraph's `overwrite[T]` versus `float`-delta split, made explicit.

Cost: a new validation rule (no sibling reference in a parallel loop), one new field per loop variable.  Risk: low.
Value: moderate, because the pattern works without it; the largest benefit is model-valued merges and recognisability.
A smaller alternative with most of the benefit: a documented *pattern* in the SED2 specification (a worked example of
Scatter-in-Loop with a merge Calculation) and no new fields.

### P2 - Time-valued ranges and per-sub-task periods (a `Clock`)

Two small pieces:

1. A range may be declared as **time** (`"meaning": "time"`, with optional unit), exposing `#tasks:loop.time`.
   This is only a label, and gives the reverse translator something to map `global_time` onto.
2. A sub-task may carry `every` (an integer number of ticks) or `period` (a time, must be a multiple of the range step):
   it runs only at iterations whose time is a multiple, and reads the loop variables as they stood **at its last
   run** (stale read, as in process-bigraph).

```json
"subTasks": {
  "fast": { "...": "...", "every": 1 },
  "slow": { "...": "...", "every": 10 }
}
```

This covers commensurate multi-rate (G1) without a scheduler.  Non-commensurate intervals stay out of scope; they
need a least-common-tick range chosen by the author.  Cost: moderate (a sub-task may now not run at an iteration, so
its result for that iteration is absent or carried over; define it as "carried over", so shapes stay fixed).

### P3 - `until`, with `maxIterations`

An optional `until` on a Loop: a boolean expression over the iteration's results (`#tasks:...`), evaluated after each
iteration.  `maxIterations` becomes **required** whenever `until` is present.  Result blocks are padded to
`maxIterations` (a documented fill value) and the loop also outputs `.completedIterations`.  This keeps rows known in
advance (the invariant) and makes "stop when converged" expressible.  Cost: a boolean expression language (SED2
already has MathML-like Calculation, so a comparison of one scalar to a constant would be enough to start), padded
results.  Risk: medium; it is a change to "cannot end early" in the Loop specsheet, so it is the SED2 author's call.

### P4 - `nextRange`: adaptive steps

Only meaningful together with P3.  Instead of a fixed range, the Loop gives `initialRange` and `nextRange`, an
expression of loop variables and results producing the next range value (the next interval), with `maxIterations`.
This is the SED2 form of `calculate_timestep`.  Cost: high for the benefit, since adaptive coupling is rare in the SED2
domain (the simulators adapt internally).  **Recommend deferring** until a real use case shows up.

### P5 - Continuation state as a task output

Today `.model` carries the model's values.  Add an optional output `.state` to simulation tasks and a matching
`continueFrom` input: opaque simulator state (integrator history, random-generator state) that the next simulation
may pick up, with the rule that an implementation which cannot honour it must fall back to a restart *and say so*
(a documented capability, like the other `capabilities.json` entries).  For stochastic simulations it is the only
way to make a loop of short runs equal one long run.  Cost: depends on each backend (roadrunner and COPASI have
partial support; libopencor unknown).  Value: high for stochastic, small for ODEs.  Defer with the stochastic phase.

### P6 and P7 - not proposed

Dynamic structure (G6) and between-tick events (G7), for the reasons given there.

### Order of work and what each unlocks

| Proposal | Gap | Needs another proposal? | Unlocks in the forward direction | Unlocks in the reverse direction |
|---|---|---|---|---|
| P1 (optional) | G2 | no | declared parallel loops translate to equal-interval processes | equal-interval PBG documents are recognised, and model-valued merges become short |
| P2 | G1 | no (helps P1) | multi-rate loops translate to processes with intervals | commensurate multi-rate PBG documents map |
| P3 | G4 | no | `until` loops translate to a step with a stop flag | drivers of the form "run until x" map |
| P4 | G3 | P3 | adaptive loops | `calculate_timestep` processes map |
| P5 | G5 | no | stochastic continuation | stateful processes map |

With P1 and P2 in SED2, a SED2 Loop could be translated to process-bigraph's **native** form (processes with
intervals) as well as to the step form, so the two sections in `process-bigraph.md` (3.8 steps, 3.9 native) would merge
into one: the same document, written the way the framework is meant to be used when you want to *couple* it to other
processes.

## 6. What this means for the translators

**Forward (SED2 -> PBG).**  Nothing in this file blocks the plan.  The clock form (steps inside a hosted inner
composite) is exact for today's SED2, whether the sub-tasks are chained or parallel, because the order inside a tick
comes from the references; a Scatter inside a Loop becomes a nested `SedRepeat` step.  After P2 (and P1, if adopted) the
translator gains a second, native form in which parallel branches become equal-interval processes.  Multi-rate loops
cannot be written in SED2 until P2, so there is nothing to translate before then.

**Reverse (PBG -> SED2).**  Hypothesis 1 of `process-bigraph-to-sed2.md` ("coupled simulation is the largest gap")
should be narrowed to what is now known:

* One clock, one interval, processes with disjoint outputs and no process reading another's output: equals a sequential
  loop (order irrelevant), translatable today.
* One clock, one interval, processes that read each other's outputs or write the same store: *not* equal to a
  sequential loop (section 2 table); translatable today as a Loop whose branches (siblings or a Scatter) read only the
  loop variables, with an explicit merge Calculation (G2); the model-valued merge is the hard part, and P1 would shorten
  it.
* Different intervals: only with P2 (commensurate) and never for non-commensurate ones.
* `calculate_timestep`, `_add`/`_remove`/`_divide`: refused with a one-line reason.
* Steps between processes: sub-tasks of the loop, firing once per tick; steps with no process upstream: tasks before
  the loop.

A classifier for these cases is the natural first output of the reverse translator, before any SED2 is written: it
would also give a count, over the corpus, of how many PBG documents fall in each class.  That count is the evidence the
SED2 author needs to decide on P1 to P5.

## 7. Open questions

1. **Is the sequential scheme what you mean by a SED2 Loop?**  The cosimulation document says so (the sub-tasks read
   each other's results).  This file assumes yes for chained sub-tasks, and notes that parallel evaluation of independent branches (siblings and
   Scatter) is already available in SED2, so P1 is a label and a merge rule, not a capability.
2. **P3 versus "cannot end early".**  The Loop specsheet says a loop cannot end early.  Is that a design principle
   (results of known shape; documents that can be checked statically) or a first-version limit?  The padding rule in P3
   is meant to keep the principle, but it is your call.
3. **Should a range know that it is time?**  P2 part 1 is a label only.  It is cheap, but it adds a concept to the
   specification.
4. **Where should proposals go?**  CLAUDE.md says a new section at the end of `SED2/TODO.md`.  I have not written
   one.  Say when, and whether to include all five proposals or only P2 and P3 (P1 is optional, see G2).

## Sources

* Agmon and Spangler, arXiv:2512.23754v2, main text and Supplements S1 (sections 3.5, 3.8) and S2 (DynamicFBA).
* process-bigraph 1.8.5 (git e5325c1): `process_bigraph/composite.py` (`Process`, `Step`, `calculate_timestep`, `run`,
  structural sentinels), `process_bigraph/processes/` (`simulation.py`, `parameter_scan.py`, `dynamic_structure.py`,
  `growth_division.py`, `reaction.py`, `bigraphical_reactive_system.py`), `docs/tick_lifecycle.md`,
  `docs/architecture.md`: https://github.com/vivarium-collective/process-bigraph
* SED2 specsheets read: `tasks/Loop`, `tasks/Repeat`, `tasks/NumericRange`, `tasks/ModelChange`,
  `tasks/FluxBalanceAnalysis` (v1.0.0).
* The cosimulation document supplied by the SED2 author (earlier syntax), analysed in `process-bigraph.md`, 5.1.
* Experiments: see `process-bigraph.md`, section 2.9 (flat versus hosted clock, parallel versus sequential coupling,
  stale reads at different intervals, init firing, object loop variables).
