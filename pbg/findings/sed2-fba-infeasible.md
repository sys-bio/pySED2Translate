# Draft question for the SED2 author: what does a FluxBalanceAnalysis task return when the problem is infeasible?

Status: **draft, not added to SED2/TODO.md** (CLAUDE.md: propose only, in a new section at the end; your call).

Found 2026-10-09 while looping the real E. coli model iAF1260 (vivarium-collective/CRM-FBA, `crm_dfba/models/iAF1260.xml`) with a Monod
ODE: once glucose is exhausted (uptake bound 0), the FBA problem is infeasible, because the model's ATP maintenance reaction has a
positive lower bound that cannot be supplied.  COBRApy reports `status = 'infeasible'` and an objective value of None/NaN.

In a Loop (the cosimulation case) the next iteration needs a value.  The specification does not say what `FluxBalanceAnalysis`
produces.  Options: (a) the task fails, and so does the document; (b) the flux table is empty / NaN, and a Calculation maps it to
what the author wants; (c) the task has a status output.  Without a rule, the translator would have to invent one (it must not).

Related, smaller: `numericRange` with only `numberOfSteps: 100` gives 101 loop iterations in the cosimulation file (noted in
`../../process-bigraph.md`, 5.1).
