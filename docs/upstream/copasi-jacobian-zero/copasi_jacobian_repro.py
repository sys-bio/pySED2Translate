"""COPASI: the Jacobian from CMathContainer::calculateJacobian has an all-zero column for a variable whose value is 0.

Model chain.xml: A -> B (k1*A), B -> (k2*B), k1 = 1, k2 = 2, A = 1, B = 0 (species concentrations, compartment size 1).
The Jacobian is [[dB'/dB, dB'/dA], [dA'/dB, dA'/dA]] = [[-k2, k1], [0, -k1]] = [[-2, 1], [0, -1]] in COPASI's order (B, A).
Only the column of the species with value 0 (B) is wrong: it comes out as zeros, for any derivation factor.
Setting B = 0.5 gives the correct matrix.
"""
import sys
import COPASI

path = sys.argv[1] if len(sys.argv) > 1 else "chain.xml"
dm = COPASI.CRootContainer.addDatamodel()
assert dm.importSBML(path)
model = dm.getModel()
for b0 in (0.0, 0.5):
    model.getMetabolite("B").setInitialConcentration(b0)
    model.updateInitialValues(COPASI.CCore.Framework_Concentration)
    model.applyInitialValues()
    t = model.getStateTemplate()
    names = [t.getIndependent(i).getObjectName() for i in range(t.getNumIndependent())] + \
            [t.getDependent(i).getObjectName() for i in range(t.getNumDependent())]
    for factor in (1e-3, 1e-6, 1e-9):
        jac = COPASI.FloatMatrix()
        model.getMathContainer().calculateJacobian(jac, factor, False, False)
        rows = [[round(jac.get(i, j), 8) for j in range(jac.numCols())] for i in range(jac.numRows())]
        print(f"B(0) = {b0}  factor {factor:g}  order {names}  Jacobian {rows}")
