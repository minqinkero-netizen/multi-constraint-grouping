"""Post-main budget sensitivity on ALL four C/n64 inputs, not a new sample."""
from pathlib import Path
import json
import numpy as np
from run_experiments import solve_mip, solve_heuristic, METHODS, environment

ROOT=Path(__file__).resolve().parent;EXP=ROOT/'experiments'
def main():
    main_data=json.loads((EXP/'results.json').read_text())
    selected=[c for c in main_data['cases'] if c['family']=='C' and c['n']==64]
    assert len(selected)==4
    protocol={'purpose':'post-main budget sensitivity, not independent new instances',
              'selection':'all four C/n64 instances regardless of individual outcome',
              'methods':METHODS,'soft_deadline_seconds':10.,'new_runs':16,
              'same_heuristic_seed_as_main':True,'order_seed':900000}
    (EXP/'extension_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    records=[]
    for c in selected:
        d=c['instance'];record={'name':c['name'],'results':{}}
        order=np.random.default_rng(900000+c['seed']).permutation(METHODS).tolist()
        record['execution_order']=order
        for a in order:
            r=solve_mip(d,a,10.) if a in ['P1','P2'] else solve_heuristic(d,a,10.,700000+1000+10*64+c['seed'])
            record['results'][a]=r
            print(json.dumps({'case':c['name'],'budget':10,'method':a,'feasible':r['feasible'],'L':r['L'],
                              'seconds':round(r['total_seconds'],3)},ensure_ascii=False),flush=True)
        records.append(record)
        (EXP/'extension_results.json').write_text(json.dumps({'protocol':protocol,'environment':environment(),
                                                             'cases':records},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
