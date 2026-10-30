"""Fixed revised study. Methods and inputs are unchanged when resuming.
Scale jobs may use separate CPU cores; within a scale all runs are sequential.
"""
from pathlib import Path
import argparse,json,platform,sys,os,multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np,scipy
from benchmark import generate,execute,dump,METHODS,violations
ROOT=Path(__file__).resolve().parent
PROTOCOL={'version':'2026-10-30','configs':[[80,20,16],[160,40,32],[320,80,48]],'families':['U','C'],'replicates':3,'seed_base':41000,'methods':METHODS,'budget_seconds':600,'timing':'parent wall time: process startup, model preparation, solver, rounding, repair, restore and audit','witness_used_by_methods':False,'rounding':'row argmax, ties smallest group index; capacity rebalance and stochastic conflict-pair repair; fallback constrained LP-guided reconstruction','repair_max_steps':12000,'restart_limit_G':128,'restart_limit_LS':32,'restart_limit_LPR_fallback':64,'completed_stall_limit':12,'mip_rel_gap':0.,'LP_method':'highs-ds','tolerance':1e-6}

def run_scale(ci,outpath,budget,pinned):
 out=Path(outpath);n,m,T=PROTOCOL['configs'][ci];cpu=None
 if pinned and hasattr(os,'sched_setaffinity'):
  choices=sorted(os.sched_getaffinity(0));cpu=choices[min(ci,len(choices)-1)];os.sched_setaffinity(0,{cpu})
 records=[]
 for fi,family in enumerate(PROTOCOL['families']):
  for rep in range(3):
   name=f'{family}_{n}_{m}_{T}_{rep+1}';directory=out/name;directory.mkdir(exist_ok=True);seed=41000+ci*1000+fi*100+rep
   d,w=generate(family,n,m,T,seed);assert violations(d,w['labels'])['H']==0
   dump(directory/'instance.json',d);dump(directory/'witness.json',w)
   order=np.random.default_rng(seed+100000).permutation(METHODS).tolist();rec=dict(name=name,config=[n,m,T],family=family,replicate=rep+1,seed=seed,input=d,method_order=order,results={})
   for method in order:
    fp=directory/f'{method}.json';cached=json.loads(fp.read_text()) if fp.exists() else None
    if cached is not None and 'total_seconds' in cached:
     result=cached
     if 'execution_batch' not in result:result.update(execution_batch='initial_sequential',execution_cpu=None);dump(fp,result)
    else:
     print('START',name,method,'cpu',cpu,flush=True);result=execute(d,method,budget,seed+METHODS.index(method)*10000,directory)
     result.update(execution_batch='scale_jobs' if pinned else 'sequential',execution_cpu=cpu);dump(fp,result)
    rec['results'][method]=result
    print('END',name,method,'feasible',result.get('feasible'),'L',result.get('L'),'H',result.get('H'),'seconds',round(result['total_seconds'],3),flush=True)
    dump(directory/'record.json',rec)
   records.append(rec);dump(out/f'results_scale_{n}.json',records)
 return records

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--budget',type=float,default=600);ap.add_argument('--out',default='data');ap.add_argument('--workers',type=int,default=2);args=ap.parse_args();out=ROOT/args.out;out.mkdir(exist_ok=True)
 workers=max(1,min(3,args.workers)) if hasattr(os,'sched_setaffinity') else 1
 protocol=dict(PROTOCOL);protocol.update(budget_seconds=args.budget,scale_workers=workers,execution='sequential inside each scale; different scales on distinct pinned CPU cores; each solver one thread' if workers>=2 else 'sequential, one solver thread',resume_note='Resumed runs retain their recorded execution_batch and execution_cpu. Fresh runs use the execution setting above. Published preliminary execution records are documented under orchestration/. No algorithm, input, seed, work limit or time limit changes when resuming.')
 cpu=platform.processor()
 if Path('/proc/cpuinfo').exists():cpu=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),cpu)
 protocol['environment']=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,platform=platform.platform(),logical_cpus=os.cpu_count(),cpu=cpu)
 dump(out/'protocol.json',protocol);records=[]
 if workers==1:
  for ci in range(3):
   records.extend(run_scale(ci,str(out),args.budget,False));dump(out/'results.json',dict(protocol=protocol,instances=records,complete=len(records)==18))
 else:
  with ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn')) as pool:
   jobs=[pool.submit(run_scale,ci,str(out),args.budget,True) for ci in range(3)]
   for future in as_completed(jobs):
    records.extend(future.result());records.sort(key=lambda r:(r['config'][0],r['family'],r['replicate']))
    dump(out/'results.json',dict(protocol=protocol,instances=records,complete=len(records)==18))
 print('COMPLETE',len(records),'inputs',len(records)*4,'runs',flush=True)
if __name__=='__main__':main()
