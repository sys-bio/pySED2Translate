# Lessons that survive a rewrite

**process-bigraph 1.8.5 / bigraph-schema 1.7.0**

* Steps fire once when a run starts, whatever their inputs.  A step inside a repeat therefore reads a `guard` store (-1 until the
  repeat's clock has ticked) and does nothing when it is negative.
* A store has one type.  A reader of a store that a wrapper writes as `overwrite[list]` must declare `overwrite[list]` too; `quote`
  clashes ("cannot resolve two different wrappings").  `quote` is used for everything the translator owns.
* `Composite.state` after a run holds what steps wrote; `composite.run(0.0)` fires the steps once.  Constructing a Composite calls
  `initial_state()` of every node, so a wrapper loads its model when the Composite is built.
* A state key is a path element: ids with `:` are fine inside the document, but not in file names on Windows.
* Unknown config keys are accepted silently (P-1) and a cycle of steps is broken silently (P-2): the translator never relies on
  either, and its tests build every golden document.
* Processes with different intervals: the framework reads the state at the start of the interval (`start`); the specification text
  reads like `event` (P-3).  Tier C pins the framework's behaviour.
* The paper's wording and the code differ in places (P-4: `MathExpressionStep`); the code is the authority.

**The wrappers (viva-tellurium 0.1.2, viva-copasi 0.1.2)**

* The model is a path or text in the step's config, fixed when the document is written (W-6).  The translator writes it as the
  location below the input directory it was translated for, and the runner refuses a run with another input directory.
* The COPASI steps need `viva_copasi.composites.register_copasi(core)` (W-12); a Tellurium step and a COPASI step cannot share a
  process (W-13); neither reports parameters that are not rule-driven (W-7); the UTC steps are stateful (W-10), so they are not put in repeats.
* Their output ports have types the adapter must repeat (`steps.RAW_TYPES`).

**Scheduling a loop**

* The clock form (an inner composite with a clock process and a collect step) gives the loop index the framework's own clock and
  lets downstream tasks fire once.  The nested form (one inner composite per iteration) is kept as `--loop-form nested` for
  comparison; both give the same data (tests/v1/test_loops.py).

**Method**

* The Python-script target is the oracle for the suite, the suite's canonical data for the rest; tier C scripts are translated from the
  documents (`tools/pbg2py.py`), never written by hand.
* Nothing is worked around: a gap becomes a ledger entry, a refusal with its id, and a line in `tests/providers/expected_gaps.json`.
