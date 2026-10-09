# Finding: the Tellurium wrapper at its default tolerances misses a suite case (W-1)

Status: **recorded; draft report is pbg/upstream/W-1.md (not filed).**  Observed 2026-10-09, viva-tellurium 0.1.2, libroadrunner 2.10.0.

`--wrappers strict --backend roadrunner` runs 30 suite cases in `TelluriumUTCStep` or `TelluriumSteadyStateStep`.  Of the 22 that
produce data (8 are refused while running with W-7), 21 agree with the canonical data within the case tolerances.  Case 00119
(harmonic oscillator) does not: 5.9e-6 against an allowed 5.4e-7 at one row.  The step ignores `absolute_tolerance` and
`relative_tolerance` (W-1) and so integrates with roadrunner's own defaults (1e-12 absolute, 1e-6 relative); the host runtime
sets 1e-12 / 1e-10 unless the task says otherwise and agrees with the analytic solution.

The translator does nothing about it: it does not set the tolerance in some other way, and the case is not changed.  The
disagreement is listed in `tests/providers/expected_gaps.json` (`roadrunner`, `00119`, run `FAIL`), and the test fails the day the
wrapper changes behaviour either way.
