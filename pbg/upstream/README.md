# Upstream issue drafts

Status: **drafted, none filed.**  These are texts for the maintainers of the community wrappers and of process-bigraph,
for you to review and report (or not).  Nothing here has been, or will be, filed by an assistant.

Environment of every observation: Python 3.13, process-bigraph 1.8.5, bigraph-schema 1.7.0, numpy 2.2.6; Linux (x86_64). Observed 2026-10-09.  viva-tellurium 0.1.2 with tellurium 2.2.13.1 / libroadrunner 2.10.0;
viva-copasi 0.1.2 with copasi-basico 0.87.

"Confirmed by running" means the reproduction below was executed and printed the stated result.  "Read" means the
statement comes from reading the source and has not been run.

| File | Repository | Title | Evidence |
|---|---|---|---|
| W-1.md | viva-tellurium | TelluriumUTCStep and TelluriumSteadyStateStep ignore tolerances and seed | confirmed by running |
| W-2.md | viva-copasi | Step and process cannot start a time course at a time other than 0 (start_time ignored) | confirmed by running |
| W-3.md | viva-copasi | No way to choose method or tolerances; such config keys are accepted and ignored | confirmed by running |
| W-4.md | viva-copasi | model_source accepts only a path or URL, not SBML text | confirmed by running |
| W-5.md | both | Output times must be uniform (n_points); no explicit time vector | read |
| W-6.md | both | No model input or end-state model output: a simulation cannot continue from a given model | read |
| W-7.md | both | No selection of output variables (parameters, rates, other model elements) | read |
| W-8.md | both | Steady-state step has no solver settings; no Jacobian step | read |
| W-9.md | vivarium-collective | Feature request: an OpenCOR / CellML wrapper | absence of evidence |
| W-10.md | both | The UTC steps are not idempotent: a second firing continues from the first one's end state | confirmed by running |
| P-1.md | process-bigraph | Unknown keys in a process or step config are accepted silently | confirmed by running |
| P-2.md | process-bigraph | A cycle of steps is broken silently, although the specification says cycles are disallowed | confirmed by running (earlier session) |
| P-3.md | process-bigraph | Question: do processes with different intervals read state at the event time or at the start of their interval? | confirmed by running; spec text is ambiguous |
| P-4.md | process-bigraph | Documentation: MathExpressionStep is documented but absent from 1.8.5 | read |

Order I would suggest: W-1 (a plain bug), W-10, P-1, W-2, W-3, then the rest as feature requests.
