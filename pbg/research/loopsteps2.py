import copy
from process_bigraph import Step, Process, Composite
import loopsteps
CALLS = []

class Count(Step):
    """a task downstream of the loop"""
    def inputs(self): return {'d': 'float'}
    def outputs(self): return {'seen': 'overwrite[float]'}
    def update(self, st):
        CALLS.append(st['d']); return {'seen': st['d']}

class LoopHost(Step):
    """outer node: builds an inner clock document, runs it to completion, returns the last d and all rows"""
    config_schema = {'document': 'quote', 'ticks': 'integer'}
    def inputs(self): return {}
    def outputs(self): return {'d': 'overwrite[float]', 'rows': 'overwrite[node]'}
    def update(self, st):
        c = Composite({'state': copy.deepcopy(self.config['document'])}, core=self.core)
        c.run(float(self.config['ticks']))
        rows = c.state['emitter']['instance'].query()[1:]      # drop the t=0 row
        return {'d': rows[-1]['d'], 'rows': [r['d'] for r in rows]}

# Two coupled processes sharing stores
class P1(Process):
    def inputs(self): return {'x': 'float', 'y': 'float'}
    def outputs(self): return {'x': 'float'}
    def update(self, s, interval): return {'x': 0.5 * (s['y'] - s['x'])}
class P2(Process):
    def inputs(self): return {'x': 'float', 'y': 'float'}
    def outputs(self): return {'y': 'float'}
    def update(self, s, interval): return {'y': 0.25 * (s['x'] - s['y'])}
