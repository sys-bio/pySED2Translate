import tellurium as te, cobra
from cobra import Model, Reaction, Metabolite
# ---------- ODE model: Monod consumer-resource, as in crm_dfba MonodCRM, with the FBA results entering as parameters
ant = """
model monod_CRM_mock
  species glucose, acetate, biomass;
  glucose = 11.1; acetate = 0; biomass = 0.01;
  Vmax_glc = 10; Km_glc = 0.5; Vmax_ac = 2; Km_ac = 0.5;      # same kinetic parameters as crm_dfba's monod demo
  u_glc := Vmax_glc*glucose/(Km_glc + glucose + 1e-12);       # prescribed uptake (mmol/gDW/h): becomes the FBA lower bound
  u_ac  := Vmax_ac*acetate/(Km_ac + acetate + 1e-12);
  mu = 0; v_glc = 0; v_ac = 0;                                # set from the FBA solution between intervals
  gr: => biomass;   mu*biomass;
  eg: glucose => ;  -v_glc*biomass*glucose/(glucose + 1e-9);  # v_glc <= 0 is an uptake; the limiter keeps S >= 0
  ea: acetate => ;  -v_ac*biomass*piecewise(1, v_ac > 0, acetate/(acetate + 1e-9));  # secretion always, uptake limited by availability
end
"""
r = te.loada(ant)
open('monod_CRM_mock.xml','w').write(r.getSBML())
# ---------- toy FBA model with FBC: respiration (capacity limited), fermentation with acetate overflow, acetate use
m = Model('toy_overflow')
glc, ac, bm = Metabolite('glc_e', compartment='e'), Metabolite('ac_e', compartment='e'), Metabolite('bm', compartment='c')
G = Metabolite('glc_c', compartment='c'); A = Metabolite('ac_c', compartment='c')
def rxn(id, mets, lb, ub, name=''):
    x = Reaction(id); x.name=name or id; x.lower_bound=lb; x.upper_bound=ub; x.add_metabolites(mets); return x
m.add_reactions([
  rxn('EX_glc__D_e', {glc:-1}, -10, 1000, 'glucose exchange'),
  rxn('EX_ac_e', {ac:-1}, -2, 1000, 'acetate exchange'),
  rxn('GLCt', {glc:-1, G:1}, 0, 1000),
  rxn('ACt', {ac:-1, A:1}, -1000, 1000),
  rxn('RESP', {G:-1, bm:0.024}, 0, 6, 'respiration, capacity limited'),
  rxn('FERM', {G:-1, A:2, bm:0.006}, 0, 1000, 'fermentation with acetate overflow'),
  rxn('ACUSE', {A:-1, bm:0.012}, 0, 1.0, 'acetate to biomass'),
  rxn('BIOMASS', {bm:-1}, 0, 1000, 'biomass drain'),
])
m.objective = 'BIOMASS'
cobra.io.write_sbml_model(m, 'toy_FBA_mock.xml')
print('ODE:', [x for x in r.getFloatingSpeciesIds()], 'params', r.getGlobalParameterIds())
m2 = cobra.io.read_sbml_model('toy_FBA_mock.xml')
print('FBA growth', round(m2.optimize().objective_value,4))
