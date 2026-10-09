# sanity check with the REAL genome-scale model (iAF1260 from CRM-FBA); the ODE side is the mock Monod model (ids glucose, acetate)
# usage: python refloop_real.py path/to/iAF1260.xml
import sys, time, roadrunner, cobra
rr = roadrunner.RoadRunner('monod_CRM_mock.xml'); rr.integrator.absolute_tolerance=1e-12; rr.integrator.relative_tolerance=1e-10
fba = cobra.io.read_sbml_model(sys.argv[1])
t=0.0; dt=1.0; T0=time.time(); nopt=0
for k in range(41):
    fba.reactions.EX_glc__D_e.lower_bound = -rr['u_glc']; fba.reactions.EX_ac_e.lower_bound = -rr['u_ac']
    sol = fba.optimize(); nopt+=1
    mu = sol.objective_value if sol.status=='optimal' else 0.0
    rr['mu']=mu; rr['v_glc']=sol.fluxes['EX_glc__D_e']; rr['v_ac']=sol.fluxes['EX_ac_e']
    if k%8==0: print(f"t={t:5.1f} glc={rr['glucose']:7.3f} ac={rr['acetate']:7.3f} X={rr['biomass']:9.4f} mu={mu:.3f} v_glc={rr['v_glc']:.2f} v_ac={rr['v_ac']:.2f} status={sol.status}")
    rr.simulate(t, t+dt, 2); t+=dt
print('%d solves in %.1f s' % (nopt, time.time()-T0))
