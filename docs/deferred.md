# Deferred until the SED2 format is decided

pySED2Translate does not translate these; a document containing one is skipped with exit status 11 (the reason is in
`capabilities.json`).  Do not work around them.  Each item is revisited when the SED2 specification settles it.

| Feature | Waiting for | Where |
|---|---|---|
| `ModelChange.addElements`, `ModelChange.replaceElements` | The format of their entries and the order of changes (SED2/TODO.md) | `check` `model_change` |
| `AggregationCalculation`, `aggregateOutputVariables` of a repeat | The split of AggregationCalculation into one class per function (SED2/TODO.md) | `aggregationCalculation` entry, `repeat` check |
| `taskParameters` on any task | A definition of what their ids mean (SED2/TODO.md) | `ode_simulation`, `steady_state`, `jacobian`, `repeat`, `model_change`, `csv_import` checks |
| `DataImport`; `CsvImport.organization` other than "columns" | The new CsvImport attributes and DataImport formats (SED2/TODO.md) | `dataImport` entry, `csv_import` check |

Not format questions, but also deferred: stochastic simulations and DrawFromDistribution (a later phase).

Not supported because of a simulator, not the format: SteadyState on OpenCOR (libopencor issue 604,
https://github.com/opencor/libopencor/issues/604).

## Choices made where the specification is silent

The translator does something definite in these cases so that documents run, but the specification has not decided
them.  Each is a section at the end of SED2/TODO.md with a proposal; when the specification settles one, check that the
translator and the matching sed2-test-suite cases agree with it (docs/COVERAGE.md in that repository lists the cases).

| Topic | SED2/TODO.md section | What the translator does |
|---|---|---|
| Math results the text does not state | Math: results the specification does not state | See the section's bracketed notes. |
| Time courses: output points, solver settings | Time courses: points the specification does not state | See the section's bracketed notes. |
| JacobianReduced: which species are kept | Steady states and Jacobians | The first species of each conservation law, as roadrunner and COPASI do. |
| Jacobian in concentrations or amounts; boundary species | Steady states and Jacobians | Concentration based; floating species only. |
| `setValues` on a species | ModelChange for SBML, CsvImport and plots | The initial concentration (the initial amount if the species has only substance units); an initial assignment of the element is dropped. |
| `removeElements` | ModelChange for SBML, CsvImport and plots | Any element listed by id is removed and nothing else changes; an id the model lacks fails the task. |
| ModelChange of a simulation's `.model` | ModelChange for SBML, CsvImport and plots | Keeps the simulated end state and applies the change on top of it. |
| `.model['reaction']` | ModelChange for SBML, CsvImport and plots | The value of the kinetic law (amount per time). |
| CsvImport details | CsvImport: attributes based on Python's readers; ModelChange for SBML, CsvImport and plots | The header line is not counted in `nrows`; blank lines are skipped; a header wins over `columnNames`; limits larger than the file fail; an empty cell fails. |
| ModelElementList order and unknown ids | ModelElementList and the labels of repeats | Model order, grouped by kind; an unknown id is an error. |
| Repeated range values as labels | ModelElementList and the labels of repeats | A label index takes the first match. |
| References inside list and dictionary constants | References inside list and dictionary constants | Refused with a pointer to the section. |
| FluxBalanceAnalysis: `[id].model` | Flux balance analysis | The model that went in, unchanged: the analysis changes nothing in it. |
| FluxBalanceAnalysis: no feasible optimum | Flux balance analysis | The task fails (DataError "no optimum", solver status named); no values are reported. |
| FluxBalanceAnalysis: output variables | Flux balance analysis | A reaction gives its flux; a parameter, compartment or species gives the model's value; anything else fails the task. |
| FluxBalanceAnalysis: model without FBC | Flux balance analysis | Skipped (exit 11): without an objective and bounds there is nothing to optimize. |

Simulator limits, as opposed to format questions, are recorded in sed2-test-suite/disagreements.json (D-001: the COPASI
Jacobian of a species whose value is 0; D-002: OpenCOR running a model with SBML events) and in the capability table.

## To do

* **Translate the Monod consumer-resource model of CRM-FBA to SBML.**  The real CRM-FBA example couples iAF1260 (an SBML FBC
  file, which the translator can already run: pbg/tests/advanced/test_real_crm_fba.py) to a Monod model that exists only as
  Python code (`crm_dfba/crms/monod.py`).  Until that model is written as SBML (species, uptake rates as parameters that the
  FBA bounds are set from, growth and exchange fluxes as parameters set from the FBA solution, as in
  sed2-test-suite/cases/semantic/00282), the real cosimulation (templates/cosimulation.sed2.json) cannot be run.  The real
  files are not stored in any repository here.
* **cobra's `scipy` solver is much slower than `glpk` on genome-scale models**: three solves of iAF1260 took 4 minutes with
  `cobra:scipy` and 21 seconds with `cobra:glpk` (both gave the same fluxes to 6 digits).  Recorded, not worked around.
