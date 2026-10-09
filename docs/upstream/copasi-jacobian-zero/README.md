# COPASI / basico: Jacobian findings

Found while testing pysed2translate's COPASI backend against sed2-test-suite (disagreement D-001).
Software: python-copasi 4.48.309, copasi-basico 0.87.

Files: `chain.ant` (Antimony), `chain.xml` (SBML L3V2), `copasi_jacobian_repro.py` (python-copasi only),
`basico_jacobian_repro.py` (basico).

1. **Zero-valued variable (COPASI).**  `CMathContainer::calculateJacobian(jac, factor, reduced, false)` returns zeros
   for the column of a variable whose value is 0, for any derivation factor; the step appears to be relative to the
   value.  Reproduced with python-copasi directly and through `basico.get_jacobian_matrix`.  No error or warning.
   Not checked against COPASI's steady-state task report.
2. **Row and column labels (basico).**  `basico.get_jacobian_matrix` labels the matrix with names in the model's
   user order (`getUserOrder()`), but `calculateJacobian` returns it in state order (independent variables, then
   dependent ones; `getStateTemplate()`).  Where the orders differ the labels are wrong: for chain.xml the state order
   is (B, A) and the user order (A, B), and with B(0) = 0.5 basico shows dA/dA = -2 where the answer is -1.
   Seen only for `get_jacobian_matrix`; `get_reduced_jacobian_matrix` builds its names the same way (not run).

