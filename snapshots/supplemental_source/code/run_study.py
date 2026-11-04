"""Rerun the unchanged 18 historical inputs under one fixed new protocol.
Resume accepts only results with matching input and implementation digests.
"""
from pathlib import Path
import json,os,sys,hashlib,random,platform,multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np,scipy,highspy
from benchmark import execute,dump,violations,METHODS
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def initialize():
    if hasattr(os,'sched_setaffinity'):
        cpus=sorted(os.sched_getaffinity(0));idx=(mp.current_process()._identity[0]-1)%3
        os.sched_setaffinity(0,{cpus[min(idx,len(cpus)-1)]})
def job(task):
    name,method,seed,budget,digest=task;w=ROOT/'data'/name
    d=json.loads((w/'instance.json').read_text());fp=w/f'{method}.json'
    key=dict(input_sha256=sha(w/'instance.json'),implementation_sha256=digest,protocol_sha256=sha(ROOT/'protocol.json'))
    if fp.exists():
        r=json.loads(fp.read_text())
        if r.get('run_key')==key and 'total_seconds' in r:return name,method,r
        raise RuntimeError('Existing unmatched run: '+str(fp))
    print('START',name,method,flush=True)
    r=execute(d,method,budget,seed,w);r.update(run_key=key,execution_cpu=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None)
    dump(fp,r);print('END',name,method,r['status'],r.get('L'),round(r['total_seconds'],3),flush=True)
    return name,method,r
def main():
    out=ROOT/'data';out.mkdir(exist_ok=True);p=json.loads((ROOT/'protocol.json').read_text())
    records=json.loads((out/'input_manifest.json').read_text())
    rows={};tasks=[]
    digest=hashlib.sha256(''.join(sha(ROOT/f) for f in ['benchmark.py','solver_backend.py','round_repair.py','grouping_core.py']).encode()).hexdigest()
    for rec in records:
        name=rec['name'];w=out/name;w.mkdir(exist_ok=True);d=rec['input']
        if (w/'instance.json').exists():assert json.loads((w/'instance.json').read_text())==d
        else:dump(w/'instance.json',d)
        witness=json.loads((w/'witness.json').read_text());assert violations(d,witness['labels'])['H']==0
        seed=rec['seed']+70000;order=METHODS.copy();random.Random(seed).shuffle(order)
        rows[name]={k:rec[k] for k in ['name','config','family','replicate','seed','input']};rows[name].update(method_order=order,results={})
        tasks.extend((name,m,seed,p['main_budget_seconds'],digest) for m in order)
    dump(out/'input_manifest.json',[{k:v for k,v in r.items() if k!='results'} for r in rows.values()])
    random.Random(20261031).shuffle(tasks)
    # Scheduling only: finish lightweight methods before memory-intensive solver jobs.
    tasks.sort(key=lambda t: (t[1] in ('MIP','LPR'), t[1]=='MIP', int(t[0].split('_')[1]) if t[1] in ('MIP','LPR') else 0))
    p['environment']=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,highspy=highspy.Highs().version(),platform=platform.platform(),cpu=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'') if Path('/proc/cpuinfo').exists() else platform.processor(),memory_limit_bytes=int(Path('/sys/fs/cgroup/memory.max').read_text()) if Path('/sys/fs/cgroup/memory.max').exists() else None)
    p['scheduling_resume']=json.loads((ROOT/'scheduling_resume.json').read_text())
    dump(out/'protocol.json',p)
    with ProcessPoolExecutor(max_workers=1,mp_context=mp.get_context('spawn'),initializer=initialize) as pool:
        jobs=[pool.submit(job,t) for t in tasks]
        for f in as_completed(jobs):
            name,method,r=f.result();rows[name]['results'][method]=r
            dump(out/name/'record.json',rows[name])
            dump(out/'results.json',dict(protocol=p,instances=list(rows.values()),complete=all(len(x['results'])==len(METHODS) for x in rows.values())))
    print('COMPLETE',len(rows),'inputs',len(tasks),'runs',flush=True)
if __name__=='__main__':
    if os.name=='posix':
        import fcntl
        process_lock=(ROOT/'study.lock').open('w')
        fcntl.flock(process_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    main()
