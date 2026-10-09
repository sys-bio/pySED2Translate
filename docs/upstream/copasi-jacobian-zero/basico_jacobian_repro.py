"""basico.get_jacobian_matrix(): two problems, shown with chain.xml (A -> B at k1*A, B -> at k2*B; k1 = 1, k2 = 2).

    python basico_jacobian_repro.py chain.xml

1. For a species whose value is 0 the column of its derivatives comes out as zeros (COPASI's calculateJacobian takes
   its step relative to the value).
2. The matrix is in COPASI's state order (here B, A: see CModel.getStateTemplate()) but basico labels its rows
   and columns in the model's user order (here A, B), so the labels are wrong whenever the two orders differ.
"""
import sys
import basico

path = sys.argv[1] if len(sys.argv) > 1 else "chain.xml"
dm = basico.load_model(path)
print("expected, whatever the value of B (rows: d/dt of ..., columns: with respect to ...):")
print("     A    B\nA -1.0  0.0\nB  1.0 -2.0\n")
for b0 in (0.0, 0.5):
    basico.set_species("B", initial_concentration=b0, model=dm)
    jac = basico.get_jacobian_matrix(apply_initial_values=True, model=dm)
    print(f"basico, B(0) = {b0}:")
    print(jac.to_string())
    print()
