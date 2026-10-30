"""Small independent checks and the three preserved explanatory scenarios.
These inputs are separate from the performance study. No P1 solver is called.
"""
from pathlib import Path
import json,itertools,time,platform,sys,os
import numpy as np
from benchmark import generate,execute,dump,violations,prepare,objective
from grouping_core import restore
ROOT=Path(__file__).resolve().parent
CONFIGS=[(8,2,4),(12,3,8),(20,5,12)]
def main():
 out=ROOT/'scenario_data';out.mkdir(exist_ok=True)
 protocol=dict(configs=CONFIGS,replicates=3,methods=['MIP','LPR'],budget_seconds=600,family='U',seed_base=52000,role='separate small consistency checks, not performance-study inputs',execution_cpu=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None)
 dump(out/'protocol.json',protocol);rows=[]
 for k,(n,m,T) in enumerate(CONFIGS):
  for rep in range(3):
   seed=52000+k*100+rep;name=f'U_{n}_{m}_{T}_{rep+1}';work=out/name
   d,w=generate('U',n,m,T,seed);dump(work/'instance.json',d);dump(work/'witness.json',w)
   row=dict(name=name,config=[n,m,T],results={})
   for method in protocol['methods']:
    fp=work/f'{method}.json'
    r=json.loads(fp.read_text()) if fp.exists() and 'total_seconds' in json.loads(fp.read_text()) else execute(d,method,600,seed,work)
    row['results'][method]=r
    print(name,method,r.get('feasible'),r.get('L'),round(r['total_seconds'],4),flush=True)
   rows.append(row)
 # All labeled allocations of the eight-resource input, no optimization of P1.
 d=json.loads((ROOT/'solutions/base8_input.json').read_text());valid=[];mismatches=0;p=prepare(d)
 for labels in itertools.product(range(d['m']),repeat=d['n']):
  if violations(d,labels)['H']==0:
   q,_=objective(p,labels,d['m']);x=np.eye(d['m'],dtype=int)[list(labels)]
   _,_,_,audit=restore(d,x);mismatches+=int(q!=audit['L']);valid.append(q)
 exact=dict(candidates=2**8,feasible_labeled=len(valid),mismatches=mismatches,minimum=min(valid))
 assert exact==dict(candidates=256,feasible_labeled=32,mismatches=0,minimum=0)
 tight=dict(d);tight['r']=.1
 tight_count=sum(violations(tight,labels)['H']==0 for labels in itertools.product(range(d['m']),repeat=d['n']))
 assert tight_count==0
 exact['tight_distance_feasible_labeled']=tight_count
 special=[]
 for name in ['base8','seed66','round32']:
  d=json.loads((ROOT/f'solutions/{name}_input.json').read_text());work=out/name;rec=dict(name=name,config=[d['n'],d['m'],len(d['targets'])],results={})
  for method in protocol['methods']:
   fp=work/f'{method}.json'
   r=json.loads(fp.read_text()) if fp.exists() and 'total_seconds' in json.loads(fp.read_text()) else execute(d,method,600,53000,work)
   rec['results'][method]=r;print(name,method,r.get('feasible'),r.get('L'),round(r['total_seconds'],4),flush=True)
  # Recheck the fixed explanatory arrangement even if a solver uses different labels.
  old=json.loads((ROOT/f'solutions/{name}_solution.json').read_text())
  labels=old.get('labels')
  if labels is None:
   x=np.array(old['x']);labels=np.argmax(x,axis=1).tolist()
  audit=violations(d,labels);assert audit['H']==0
  x=np.eye(d['m'],dtype=int)[labels];_,_,_,ad=restore(d,x)
  rec['fixed_scenario']=dict(labels=labels,L=ad['L'],audit=ad['checks'],calls=ad['round_records'])
  special.append(rec)
 result=dict(protocol=protocol,independent=rows,special=special,enumeration=exact,complete=True)
 dump(out/'results.json',result);print('SCENARIOS COMPLETE',flush=True)
if __name__=='__main__':main()
