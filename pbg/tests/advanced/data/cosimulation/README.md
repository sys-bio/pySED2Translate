# Mock models for the cosimulation test case

Built by `build_mock.py` (needs tellurium and cobra); the two XML files are its output and are kept so that tests need neither.

* `monod_CRM_mock.xml` - Monod consumer-resource ODE (species glucose, acetate, biomass).  Uptake `Vmax S / (Km + S)` with the
  kinetic parameters of the CRM-FBA Monod demo (glucose Vmax 10, Km 0.5; acetate Vmax 2, Km 0.5).  `mu`, `v_glc` and `v_ac` are
  parameters that the FBA solution sets between intervals; `u_glc` and `u_ac` are the uptake rates that become the FBA lower bounds.
* `toy_FBA_mock.xml` - 8 reactions, FBC: respiration (capacity limited), fermentation with acetate overflow, acetate re-use,
  biomass drain.  Exchange ids `EX_glc__D_e`, `EX_ac_e` (same as iAF1260). 
* `refloop.py` - plain-Python ODE -> FBA -> ODE loop (41 intervals of 1) on the mock pair.  Sanity check only; **not** an
  expected-data source.  Last lines: t = 40: glucose 0, acetate 0.103, biomass 0.3056.
* `refloop_real.py PATH/iAF1260.xml` - the same loop with the real model from vivarium-collective/CRM-FBA (not stored here: the
  repository has no licence file that I found).  41 solves in about 3 s; at about t = 7 glucose is exhausted and the FBA becomes
  **infeasible** (iAF1260 needs ATP for maintenance), after which the script sets growth to zero.
