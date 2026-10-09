# needs: pip install viva-tellurium==0.1.2 (or put a clone on PYTHONPATH)
import sys
from process_bigraph import allocate_core
from viva_tellurium.processes import TelluriumUTCStep, TelluriumProcess
core = allocate_core()
ant = "model m; S1 = 1; S2 = 0; k = 0.5; J1: S1 -> S2; k*S1; end"
for cls, kw in ((TelluriumUTCStep, {}), (TelluriumProcess, {})):
    cfg = {'model': ant, 'absolute_tolerance': 1e-3, 'relative_tolerance': 1e-2}
    inst = cls(cfg, core=core)
    if cls is TelluriumUTCStep:
        inst.update({}); rr = inst._rr
    else:
        inst._build(); rr = inst._rr
    print(cls.__name__, 'requested abs/rel 1e-3/1e-2 -> integrator has', rr.integrator.absolute_tolerance, rr.integrator.relative_tolerance)
# does UTC step honour the integrator name/seed?
inst = TelluriumUTCStep({'model': ant, 'integrator': 'gillespie', 'seed': 5}, core=core); inst.update({})
print('UTC gillespie requested ->', inst._rr.integrator.getName(), 'seed', getattr(inst._rr.integrator,'seed',None))
