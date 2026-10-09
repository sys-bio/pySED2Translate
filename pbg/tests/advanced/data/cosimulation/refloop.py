# sanity check of the mock pair only (NOT an expected-data source): sequential ODE -> FBA -> ODE loop, interval 1
import roadrunner, cobra, math
rr = roadrunner.RoadRunner('monod_CRM_mock.xml'); rr.integrator.absolute_tolerance=1e-12; rr.integrator.relative_tolerance=1e-10
fba = cobra.io.read_sbml_model('toy_FBA_mock.xml')
t=0.0; dt=1.0
for k in range(41):
    u = {'glc': rr['u_glc'], 'ac': rr['u_ac']}
    fba.reactions.EX_glc__D_e.lower_bound = -u['glc']; fba.reactions.EX_ac_e.lower_bound = -u['ac']
    sol = fba.optimize()
    mu = sol.objective_value if sol.status=='optimal' else 0.0
    rr['mu']=mu; rr['v_glc']=sol.fluxes['EX_glc__D_e']; rr['v_ac']=sol.fluxes['EX_ac_e']
    if k%8==0: print(f"t={t:5.1f} glc={rr['glucose']:7.3f} ac={rr['acetate']:7.3f} X={rr['biomass']:9.4f} mu={mu:.3f} v_glc={rr['v_glc']:.2f} v_ac={rr['v_ac']:.2f}")
    rr.simulate(t, t+dt, 2); t+=dt
