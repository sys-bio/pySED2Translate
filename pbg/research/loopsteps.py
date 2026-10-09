from process_bigraph import Step, Process

class Double(Step):
    """subTask d: 1 * acc * 2"""
    def inputs(self): return {'acc': 'float'}
    def outputs(self): return {'d': 'overwrite[float]'}
    def update(self, st): return {'d': st['acc'] * 2.0}

class Carry(Step):
    """a step that copies d into acc (creates a cycle with Double)"""
    def inputs(self): return {'d': 'float'}
    def outputs(self): return {'acc': 'overwrite[float]'}
    def update(self, st): return {'acc': st['d']}

class Clock(Process):
    """one tick per iteration; carries the previous iteration's d into acc; publishes range value and index"""
    config_schema = {'values': 'list[float]', 'initial': 'float'}
    def initialize(self, config=None): self.k = -1
    def inputs(self): return {'d': 'float'}
    def outputs(self): return {'acc': 'overwrite[float]', 'range': 'overwrite[float]', 'index': 'overwrite[integer]'}
    def update(self, st, interval):
        self.k += 1
        acc = self.config['initial'] if self.k == 0 else st['d']
        return {'acc': acc, 'range': self.config['values'][self.k], 'index': self.k}
