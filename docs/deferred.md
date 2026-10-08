# Deferred until the SED2 format is decided

pySED2Translate does not translate these; a document containing one is skipped with exit status 11 (the reason is in
`capabilities.json`).  Do not work around them.  Each item is revisited when the SED2 specification settles it.

| Feature | Waiting for | Where |
|---|---|---|
| `ModelChange.addElements`, `ModelChange.replaceElements` | The format of their entries and the order of changes (SED2/TODO.md; GAPS.md S-010) | `check` `model_change` |
| `AggregationCalculation`, `aggregateOutputVariables` of a repeat | The split of AggregationCalculation into one class per function (SED2/TODO.md; GAPS.md S-006) | `aggregationCalculation` entry, `repeat` check |
| `taskParameters` on any task | A definition of what their ids mean (GAPS.md S-011) | `ode_simulation`, `steady_state`, `jacobian`, `repeat`, `model_change`, `csv_import` checks |
| `DataImport`; `CsvImport.organization` other than "columns" | The new CsvImport attributes and DataImport formats (SED2/TODO.md; GAPS.md S-012) | `dataImport` entry, `csv_import` check |

Not format questions, but also deferred: stochastic simulations, DrawFromDistribution and flux balance analysis (a
later phase).

Not supported because of a simulator, not the format: SteadyState on OpenCOR (libopencor issue 604,
https://github.com/opencor/libopencor/issues/604).
