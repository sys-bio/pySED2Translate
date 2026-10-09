"""Process and Step classes of the tier C documents (plain process-bigraph classes; the exporter's scripts import them too)."""
import os

from process_bigraph import Process, Step

HERE = os.path.dirname(os.path.abspath(__file__))


class P1(Process):
    def inputs(self): return {'x': 'float', 'y': 'float'}
    def outputs(self): return {'x': 'float'}
    def update(self, s, interval): return {'x': 0.5 * (s['y'] - s['x'])}


class P2(Process):
    def inputs(self): return {'x': 'float', 'y': 'float'}
    def outputs(self): return {'y': 'float'}
    def update(self, s, interval): return {'y': 0.25 * (s['x'] - s['y'])}


class Sum(Step):
    """a task that reads two process outputs (C4)"""
    def inputs(self): return {'x': 'float', 'y': 'float'}
    def outputs(self): return {'s': 'overwrite[float]'}
    def update(self, s): return {'s': s['x'] + s['y']}


def _model(name):
    from pysed2translate_pbg import host
    with open(os.path.join(HERE, 'data', name), encoding='utf-8') as f:
        return host.SbmlModel(f.read(), name)


class OdeProc(Process):
    """The one-substrate Monod culture of suite case 00282 as a process: advances S and B by `interval` with the uptake and growth
    rates it reads, and reports the uptake limit at the end."""
    def inputs(self): return {'S': 'float', 'B': 'float', 'u': 'float', 'mu': 'float'}
    def outputs(self): return {'S': 'float', 'B': 'float', 'lb': 'overwrite[float]'}

    def update(self, s, interval):
        from pysed2translate_pbg import host
        rt = host.rt
        model = _model('00282.ode.sbml').with_values({'S': s['S'], 'B': s['B'], 'R_EX_S': s['u'], 'R_BIOMASS': s['mu']})
        tc = rt.backends.TimeCourse(independent_variable='time', output_variables=['S', 'B', 'R_EX_S_lower_bound'],
                                    points=[0.0, float(interval)], settings={}, label='time')
        data, _ = rt.backends.get('roadrunner').time_course(model, tc)
        last = data.values[-1]
        return {'S': float(last[1]) - s['S'], 'B': float(last[2]) - s['B'], 'lb': float(last[3])}


class FbaProc(Process):
    """The growth network of case 00282 as a process: reads the uptake limit, reports the optimal uptake and growth."""
    def inputs(self): return {'lb': 'float'}
    def outputs(self): return {'u': 'overwrite[float]', 'mu': 'overwrite[float]'}

    def update(self, s, interval):
        from pysed2translate_pbg import host
        rt = host.rt
        model = _model('00282.fba.sbml').with_values({'R_EX_S_lower_bound': s['lb']})
        data, _ = rt.backends.get('cobra').fba(model, rt.backends.FbaRequest(output_variables=['R_EX_S', 'R_BIOMASS']))
        return {'u': float(data.values[0]), 'mu': float(data.values[1])}
