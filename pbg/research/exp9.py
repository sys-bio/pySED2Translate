import sys, json, subprocess, os; sys.path.insert(0,'.')
from process_bigraph import Composite, allocate_core
import pbg2py
core = allocate_core(); A='local:!loopsteps2.'
def doc(i2):
    return {"x":1.0,"y":0.0,
      "p1":{"_type":"process","address":A+"P1","interval":1.0,"inputs":{"x":["x"],"y":["y"]},"outputs":{"x":["x"]}},
      "p2":{"_type":"process","address":A+"P2","interval":i2,"inputs":{"x":["x"],"y":["y"]},"outputs":{"y":["y"]}},
      "emitter":{"_type":"step","address":"local:RAMEmitter","config":{"emit":{"t":"float","x":"float","y":"float"}},
                 "inputs":{"t":["global_time"],"x":["x"],"y":["y"]}}}
def pbg(i2, end):
    c=Composite({"state":doc(i2)},core=core); c.run(end)
    return [(r['t'],round(r['x'],6),round(r['y'],6)) for r in c.state['emitter']['instance'].query()]
def script(i2, end, mode):
    src=pbg2py.export(doc(i2), end, mode, ['x','y'])
    open(f'gen_{mode}_{i2}.py','w').write(src)
    out=subprocess.run([sys.executable,f'gen_{mode}_{i2}.py'],capture_output=True,text=True,env={**os.environ,'PYTHONPATH':'.'})
    if out.returncode: print(out.stderr[-400:]); return None
    return [(r[0],round(r[1],6),round(r[2],6)) for r in json.loads(out.stdout.strip().splitlines()[-1])]
for i2,end in ((1.0,3.0),(2.0,4.0)):
    p=pbg(i2,end); s=script(i2,end,'start'); e=script(i2,end,'event')
    print(f'intervals 1 and {i2:g}')
    print('  process-bigraph      ', p)
    print('  export, start-of-int.', s, 'agrees' if s==p else 'DIFFERS')
    print('  export, event-time   ', e, 'agrees' if e==p else 'differs')
