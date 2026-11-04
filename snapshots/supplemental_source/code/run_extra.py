"""Controlled LP-guidance ablation and paired radius scan.
One LP per input is shared; its setup cost is reported separately. Random
repeats are not treated as additional independent problem instances.
"""
from pathlib import Path
import argparse,json,time,sys,subprocess,os,copy
from concurrent.futures import ProcessPoolExecutor,as_completed
import multiprocessing as mp
import numpy as np
from benchmark import generate,prepare,model,dump,violations,finish,improve,execute
from solver_backend import solve_highs
from round_repair import repair
ROOT=Path(__file__).resolve().parent
def init_cpu():
    if hasattr(os,'sched_setaffinity'):
        cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[min((mp.current_process()._identity[0]-1)%3,len(cpus)-1)]})
def lp_worker(d,fp,deadline):
    start=time.perf_counter();p=prepare(d);arrays=model(d,p)
    out=dict(status='building',feasible=False,count_bound=p['lower'],model_size=arrays[-1]);dump(fp,out)
    info,x=solve_highs(d,arrays,False,deadline-6);out.update(info)
    if x is not None and info['optimal']:
        out.update(status='optimal',x=x.tolist(),objective=info['solver_objective'])
    else:out['status']='LP_limit_no_optimum'
    out['worker_seconds']=time.perf_counter()-start;dump(fp,out)
def post_worker(d,lp,variant,seed,fp,deadline):
    start=time.perf_counter();p=prepare(d);rng=np.random.default_rng(seed);deadline-=1.5
    scores=np.full((d['n'],d['m']),1/d['m']) if variant=='UNI' else np.array(lp['x'])
    raw=np.argmax(scores,axis=1).tolist();out=dict(variant=variant,seed=seed,feasible=False,L=None,H=None,labels=None,
        raw_labels=raw,raw_H=violations(d,raw)['H'],status='repair_started',before_local_L=None,after_local_L=None)
    dump(fp,out);begin=time.perf_counter()
    if out['raw_H']==0:labels=raw;info=dict(feasible=True,steps=0)
    else:labels,info=repair(d,p,scores,rng,deadline,guidance=variant!='LP-N',initial_labels=raw)
    out.update(repair_info=info,repair_seconds=time.perf_counter()-begin,repair_labels=labels,repair_H=violations(d,labels)['H'])
    if out['repair_H']==0:
        out=finish(d,labels,out);out.update(before_local_L=out['L'],before_local_labels=labels,status='repair_feasible');dump(fp,out)
        begin=time.perf_counter();best,q,moves=improve(d,p,labels,deadline)
        out=finish(d,best,out);out.update(after_local_L=out['L'],local_moves=moves,local_seconds=time.perf_counter()-begin,status='repair_and_local_complete')
    else:out=finish(d,labels,out);out['status']='repair_failed'
    out['worker_seconds']=time.perf_counter()-start;dump(fp,out)
def subrun(command,d,fp,seconds,**kwargs):
    fp=Path(fp)
    if fp.exists():
        r=json.loads(fp.read_text())
        if 'total_seconds' in r:return r
        raise RuntimeError('Incomplete previous result: '+str(fp))
    inp=fp.parent/'input.json';dump(inp,d);start=time.perf_counter()
    args=[sys.executable,__file__,command,'--input',str(inp),'--output',str(fp),'--deadline',str(start+seconds)]
    for k,v in kwargs.items():args+=['--'+k,str(v)]
    forced=False
    try:
        pr=subprocess.run(args,capture_output=True,text=True,timeout=seconds);error=pr.stderr[-2000:] if pr.returncode else None
    except subprocess.TimeoutExpired:forced=True;error='outer watchdog'
    r=json.loads(fp.read_text()) if fp.exists() else dict(status='no_checkpoint')
    if r.get('labels') is not None:r=finish(d,r['labels'],r)
    r.update(total_seconds=time.perf_counter()-start,watchdog_timeout=forced,process_error=error,budget_seconds=seconds)
    if forced:r['status']='forced_stop_checkpoint' if r.get('feasible') else 'forced_stop_unknown'
    elif error:r['status']='process_error'
    dump(fp,r);return r
def input_job(arg):
    ci,fi,rep=arg;protocol=json.loads((ROOT/'protocol.json').read_text());n,m,T=protocol['extra_configs'][ci];family=protocol['extra_families'][fi]
    seed=61000+ci*1000+fi*100+rep;name=f'{family}_{n}_{m}_{T}_{rep+1}';folder=ROOT/'extra'/name
    d,w=generate(family,n,m,T,seed);assert violations(d,w['labels'])['H']==0;dump(folder/'instance.json',d);dump(folder/'witness.json',w)
    print('EXTRA',name,flush=True);lp=subrun('lp',d,folder/'lp.json',120)
    record=dict(name=name,config=[n,m,T],family=family,replicate=rep+1,seed=seed,input=d,lp=lp,repeats=[])
    for k in range(3):
        algseed=seed+90000+k;rr=dict(repeat=k+1,algorithm_seed=algseed,results={})
        for variant in ['LP-G','LP-N','UNI']:
            if variant!='UNI' and lp.get('status')!='optimal':
                r=dict(status='shared_LP_unavailable',feasible=False,L=None,H=None,total_seconds=None)
                dump(folder/f'{variant}_{k+1}.json',r)
            else:r=subrun('post',d,folder/f'{variant}_{k+1}.json',30,lp=folder/'lp.json',variant=variant,seed=algseed)
            rr['results'][variant]=r
        record['repeats'].append(rr);dump(folder/'record.json',record)
    scans=[]
    if ci==0 and rep<3:
        for factor in [1.0,1.15,1.30]:
            dd=copy.deepcopy(d);dd['r']*=factor;work=folder/f'radius_{factor:.2f}';row=dict(factor=factor,r=dd['r'],results={})
            dump(work/'instance.json',dd)
            for method in ['LS','SLS']:
                fp=work/f'{method}.json'
                if fp.exists() and 'total_seconds' in json.loads(fp.read_text()):r=json.loads(fp.read_text())
                else:r=execute(dd,method,30,seed+100000,work)
                row['results'][method]=r
            scans.append(row)
    record['radius_scan']=scans;record['execution_cpu']=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None
    dump(folder/'record.json',record);print('EXTRA END',name,flush=True);return record
def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['run','lp','post']);ap.add_argument('--input');ap.add_argument('--output');ap.add_argument('--deadline',type=float);ap.add_argument('--lp');ap.add_argument('--variant');ap.add_argument('--seed',type=int);a=ap.parse_args()
    if a.command=='lp':return lp_worker(json.loads(Path(a.input).read_text()),a.output,a.deadline)
    if a.command=='post':return post_worker(json.loads(Path(a.input).read_text()),json.loads(Path(a.lp).read_text()),a.variant,a.seed,a.output,a.deadline)
    out=ROOT/'extra';out.mkdir(exist_ok=True);rows=[];protocol=json.loads((ROOT/'protocol.json').read_text());dump(out/'protocol.json',protocol)
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn'),initializer=init_cpu) as pool:
        jobs=[pool.submit(input_job,(ci,fi,r)) for ci in range(2) for fi in range(2) for r in range(5)]
        for f in as_completed(jobs):
            rows.append(f.result());rows.sort(key=lambda r:(r['config'][0],r['family'],r['replicate']));dump(out/'results.json',dict(protocol=protocol,instances=rows,complete=len(rows)==20))
    print('EXTRA COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
