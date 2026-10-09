# needs: pip install viva-copasi==0.1.2 (or put a clone on PYTHONPATH)
import sys, traceback
from process_bigraph import allocate_core
core = allocate_core()
from viva_copasi.processes import CopasiUTCStep, CopasiSteadyStateStep
def trial(label, cfg):
    try:
        st = CopasiUTCStep(cfg, core=core)
        res = st.update({'species_counts': {}, 'species_concentrations': {}})['result']
        print(f"{label}: ran; time column {res['time'][0]}..{res['time'][-1]} ({len(res['time'])} rows)")
    except Exception as e:
        print(f"{label}: {type(e).__name__}: {str(e)[:160]}")
trial('(a) model_source path, time=5, n_points=6', {'model_source':'decay.xml','time':5.0,'n_points':6})
trial('(b) + start_time=2', {'model_source':'decay.xml','time':5.0,'n_points':6,'start_time':2.0})
trial('(c) + relative_tolerance=1e-3', {'model_source':'decay.xml','time':5.0,'n_points':6,'relative_tolerance':1e-3})
trial('(d) + method=Stochastic', {'model_source':'decay.xml','time':5.0,'n_points':6,'method':'stochastic'})
trial('(e) model_source = SBML text', {'model_source':open('decay.xml').read(),'time':5.0,'n_points':6})
# does a second call continue or restart (update_model=True)?
st = CopasiUTCStep({'model_source':'decay.xml','time':5.0,'n_points':2}, core=core)
a = st.update({'species_counts':{}})['result']['values'][-1]; b = st.update({'species_counts':{}})['result']['values'][-1]
print('(f) two successive update() calls end values:', a, b, '(equal => restarts; different => continues from the previous end state)')
