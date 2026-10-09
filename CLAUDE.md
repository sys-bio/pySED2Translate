# Notes for Claude

## Never hide a problem; expose it

One of the main goals of this project is to improve the field of simulators: to find bugs and fix them wherever
they are, in the simulators, in libsed2, in the SED2 specification, and in this translator.  A result that looks
right because a problem was covered up defeats that goal.

* Do not work around a bug or a gap in a simulator (roadrunner, COPASI, OpenCOR), in libsed2, or in the SED2
  specification inside the translator or its runtime.  No silent compensation (such as substituting a different
  step size, perturbing a value, or recomputing a quantity ourselves because the simulator gets it wrong), no
  special case that makes a test pass, and no loosening of a tolerance to make a disagreement go away.
* When a backend cannot do something, or does it wrongly, the translator says so: an error or a skip with the real
  reason (the capability table in `src/pysed2translate/capabilities`, exit status 11, or a failing script).  A clear
  refusal is always better than a plausible wrong answer.  The COPASI Jacobian at a zero-valued species is the
  example: COPASI returns 0 for it, so the backend refuses (disagreement D-001 in sed2-test-suite).
* Record every problem where it can be found and acted on:
  * a libsed2 or specification gap or question: `GAPS.md` (the SED2 author maintains libsed2 and the specification;
    report there, do not patch around it, and propose specification changes rather than make them);
  * a simulator bug or a disagreement between backends: `disagreements.json` in sed2-test-suite, with the size of
    the difference, the diagnosis (solver setting, translator bug, simulator bug, spec ambiguity) and the
    resolution; and, when it is a bug in someone else's software, say so plainly and, if asked, draft an upstream
    report with a minimal reproduction;
  * a translator bug: fix it, with a test that fails without the fix.
* A test case is not changed to avoid a problem unless the change leaves what the test is about intact, and the log
  entry says that it was changed and why (case 00005 starts with B = 0.5 for this reason, and keeps the
  zero-valued variant documented as unsupported).  Keep the evidence: do not delete failing cases or expected
  results to make a run green.
* If it is unclear whether something is a bug in a simulator, a bug in the translator, or an ambiguity in the
  specification, find out (minimal reproduction, a second simulator, the specification text) and say which it is
  and how sure you are, before choosing how to handle it.

## Standing rules

* **Do not commit or push** anything, in any repository, unless asked to.  Leave changes in the working tree.
* **libsed2 and the SED2 specification belong to someone else.**  They are maintained in the SED2 repository (see
  its `Claude.md`) by the SED2 author.  Report gaps in `GAPS.md` and stop there: never patch libsed2, never work
  around a gap in the translator.  Specification changes are made by the user; propose them, do not make them.
  `GAPS.md` keeps only unresolved items (resolved ones are removed, their ids stay unused).
* **ASCII only** in files (source, documentation, data, JSON, tests).  Write non-ASCII characters in tests as escapes.
* **Ask only when blocked.**  Make the call and say what was decided, unless a gap or a real question about intent
  stops the work.  Decisions that are made but not yet in the specification are tracked in `SED2/TODO.md`.
* **Keep the user informed in short messages** while working on long tasks; the finished work is reported briefly:
  what came out, where it is, one next step.
* **Do not retry a rate-limited site** (for example EBI OLS4 answers 429): note it and carry on without it.
* **Tests:** run the full suite before calling work done (`docs/testing.md`; long runs are best split into chunks).
  Do not weaken a test to make it pass.
