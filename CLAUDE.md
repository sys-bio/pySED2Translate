# Notes for Claude

## Who is who

The user is the author of Antimony and a maintainer of libSBML, roadrunner and Tellurium.  The user and Claude are the authors of everything SED2 related: SED2 (the specification and libsed2), pySED2Translate, sed2-test-suite and pbg2sed2.  These projects are developed in tandem, and more will be added in the coming months, so a change in one often has a consequence in the others.  A defect found in any of them is ours to fix, in the right repository; one in roadrunner, Tellurium, libSBML or Antimony is the user's own project (say which project it is in and record it as usual).  COPASI, OpenCOR, process-bigraph, the viva wrapper packages and every other project are other people's software.

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
  * a libsed2 or specification gap or question: `SED2/TODO.md` in the SED2 repository (libsed2 and the specification
    are ours; add a section at the end of that file and change nothing else there; do not patch around the gap in
    the translator, and propose specification changes rather than make them);
  * a simulator bug or a disagreement between backends: `disagreements.json` in sed2-test-suite, with the size of
    the difference, the diagnosis (solver setting, translator bug, simulator bug, spec ambiguity) and the
    resolution; and, when it is a bug in someone else's software, say so plainly and, if asked, draft an upstream
    report with a minimal reproduction;
  * a translator bug: fix it, with a test that fails without the fix.
* A test case is not changed to avoid a problem unless the change leaves what the test is about intact, and the log
  entry says that it was changed and why (case 00161 starts with B = 0.5 for this reason, and keeps the
  zero-valued variant documented as unsupported).  Keep the evidence: do not delete failing cases or expected
  results to make a run green.
* If it is unclear whether something is a bug in a simulator, a bug in the translator, or an ambiguity in the
  specification, find out (minimal reproduction, a second simulator, the specification text) and say which it is
  and how sure you are, before choosing how to handle it.

### A simulator's result is returned as it is (the rule that was broken once, and the guards)

The roadrunner backend once replaced roadrunner's inaccurate last variable-step row with a value it integrated separately, so a test passed and the simulator's bug stayed invisible (disagreement D-003).  That is the failure to prevent.  It is a recurring temptation because the correction looks like care.

* **Before writing any code in `src/pysed2translate/runtime/backends/` or `kisao.py`, ask: does the simulator's plain call give the right answer here?**  If it does not, write nothing that fixes it.  The backend returns the plain result, or refuses with the real reason.  Then record the problem (`disagreements.json`, a draft in `work/others/`) and tell the user in the same message.
* **Forbidden forms, whatever the reason and however small:** running a simulation again to replace a row or a value; interpolating, extrapolating, clipping or rounding a result; changing a step size, derivation factor, resolution or tolerance that the document did not set; trying other settings until a case passes; renaming, reordering, adding or dropping rows or columns to repair a simulator's output; substituting a value from another simulator.  Settings that are not the document's must be the simulator's own defaults (or the project's single stated default policy), never tuned to a case.
* **A comment of yours that says the simulator is inaccurate, wrong, lossy or interpolated, placed above a fix, is the alarm.**  That sentence belongs in `disagreements.json` and an upstream draft, not above code that hides it.  Likewise a case that passes only because of such a step is a failure of this rule, and a failing case is the evidence to keep.
* **When a plain call fails a test, do not search for a call that passes.**  Change nothing in the backend, record the problem, keep the assertion as it is (a strict `xfail` naming the disagreement is allowed; loosening it is not), and say so.
* **If you are unsure whether something is a correction, treat it as one and ask.**  If you find an existing one, say so at once; do not leave it for later.
* **The guards:** `tests/test_no_compensation.py` fails on words that describe a correction in a backend unless the same place names the recorded problem (`D-n`, or the id of a draft such as `R-2`) or is a refusal, and keeps the `COMP-n` markers in the code and `docs/compensations.md` in step; `test_roadrunner_span_is_the_plain_roadrunner_result` checks the one place that was broken.  They are tripwires on words, not proof: read the diff of every backend change for this rule.  Never edit a guard, add an exemption, or add a `COMP-n` entry to make a change pass; those need the user's decision.
* Before calling work on a backend done, say in the report what was checked: that every value comes straight from the simulator, and that `docs/compensations.md` is unchanged.

## Standing rules

* **Do not commit or push** anything, in any repository, unless asked to.  Leave changes in the working tree.
* **libsed2 and the SED2 specification are developed in the SED2 repository (see its `Claude.md`), not from this one.**  Report gaps in `SED2/TODO.md` (a new section at the end; change nothing else in
  that repository) and stop there: never patch libsed2 from here, never work around a gap in the translator.  Specification
  changes are decided by the user; propose them, do not make them.  What the translator skips because of an open item
  is listed in `docs/deferred.md`.
* **Our work notes and the notes about other people's bugs are local files, not part of the repository.**  The work items (`work/todo/`) and the drafts of reports for other projects and findings about them (`work/others/`) are in the git-ignored `work/` directory, which every repository (this one, SED2, sed2-test-suite) has; `work/INDEX.md` lists what is in it.  Nothing in the code, the tests, the workflows or the documentation that is committed may depend on them being present (a test that reads them skips when they are absent), and committed text names them by id (`W-7`, `R-2`, `T-3`), not by path.  Anything the repository itself needs (a deviation, a deferred feature, an expected failure) goes in a tracked file: `docs/compensations.md`, `docs/deferred.md`, `docs/environment-notes.md`, `pbg/tests/providers/expected_gaps.json`, or `disagreements.json` in sed2-test-suite.
* **ASCII only** in files (source, documentation, data, JSON, tests).  Write non-ASCII characters in tests as escapes.
* **Markdown files: no hard line breaks inside a paragraph or list item.**  Write each paragraph (and each list item) on one line and let the editor wrap it; the files are read in a text editor with word wrap.  Line breaks are for blank lines between paragraphs, list items, headings, table rows and code blocks.  Do not re-flow existing Markdown files unless asked.
* **Ask only when blocked.**  Make the call and say what was decided, unless a gap or a real question about intent
  stops the work.  Decisions that are made but not yet in the specification are tracked in `SED2/TODO.md`.
* **Keep the user informed in short messages** while working on long tasks; the finished work is reported briefly:
  what came out, where it is, one next step.
* **Do not retry a rate-limited site** (for example EBI OLS4 answers 429): note it and carry on without it.
* **Tests:** run the full suite before calling work done (`docs/testing.md`; long runs are best split into chunks).
  Do not weaken a test to make it pass.
