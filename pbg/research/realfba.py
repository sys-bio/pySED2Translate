import sys, time, cobra
for n in sys.argv[1:]:
    t=time.time(); m=cobra.io.read_sbml_model(n); t1=time.time()-t
    t=time.time(); s=m.optimize(); t2=time.time()-t
    ex=[r.id for r in m.exchanges if r.id in ('EX_glc__D_e','EX_ac_e','EX_o2_e')]
    print(n.split('/')[-1], len(m.reactions),'rxns', len(m.metabolites),'mets', 'load %.1fs'%t1, 'solve %.2fs'%t2, s.status, round(s.objective_value,4), m.objective.expression, ex,
      [(r.id,r.lower_bound) for r in m.exchanges if r.id in ('EX_glc__D_e','EX_ac_e')])
