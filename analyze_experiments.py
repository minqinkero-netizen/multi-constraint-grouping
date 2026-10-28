"""Audit all outcomes; derive every table/figure number from stored runs."""
from pathlib import Path
from itertools import combinations
import csv
import json
import math
import statistics
import numpy as np
from solve_and_restore import restore

ROOT=Path(__file__).resolve().parent;EXP=ROOT/'experiments'
METHODS=['G','LS','P1','P2']

def avg(v):return float(np.mean(v)) if v else None
def med(v):return float(np.median(v)) if v else None

def main():
    data=json.loads((EXP/'results.json').read_text());cases=data['cases']
    assert len(cases)==24 and all(len(c['results'])==4 for c in cases)
    rows=[];geometry=[]
    for case in cases:
        d=case['instance'];F=[t for t in range(32) if t not in d['strict']]
        MF=sum(len(d['targets'][t]) for t in F)
        count=sum(max(len(d['targets'][t])-d['m'],0) for t in F)
        D={(i,j) for i,j in combinations(range(d['n']),2) if math.dist(d['points'][i],d['points'][j])>d['r']}
        S=set()
        for t in d['strict']:S.update(combinations(sorted(d['targets'][t]),2))
        denom=math.comb(d['n'],2)
        geometry.append({'name':case['name'],'family':case['family'],'n':d['n'],'r':d['r'],
                         'distance_edge_density':len(D)/denom,'strict_edge_density':len(S)/denom,
                         'distance_only_density':len(D-S)/denom,'strict_only_density':len(S-D)/denom})
        good=[r['L'] for r in case['results'].values() if r['feasible']]
        best=min(good) if good else None
        bounds=[float(count)]+[r['lower_bound'] for r in case['results'].values() if r['lower_bound'] is not None]
        B=max(bounds)
        if best is not None:assert B<=best+1e-6,(case['name'],best,B)
        for method in METHODS:
            r=case['results'][method]
            if r['feasible']:
                _,_,_,audit=restore(d,np.eye(d['m'],dtype=int)[r['labels']])
                assert audit['feasible'] and audit['L']==r['L']
                assert all(audit['checks'].values())
            row={'case':case['name'],'family':case['family'],'n':d['n'],'m':d['m'],'seed':case['seed'],
                 'method':method,'feasible':r['feasible'],'L':r['L'],'MF':MF,
                 'best_known_L':best,'common_numeric_lower_bound':B,
                 'best_known_attained':r['feasible'] and r['L']==best,
                 'certified_with_shared_bound':r['feasible'] and abs(r['L']-B)<=1e-6,
                 'certified_by_own_bounds':r['certified_by_own_bounds'],
                 'regret_percent_to_best_known':100*(r['L']-best)/max(MF,1) if r['feasible'] else None,
                 'absolute_gap_to_common_bound':max(0.,r['L']-B) if r['feasible'] else None,
                 'solver_status':r.get('solver_status'),'total_seconds':r['total_seconds'],
                 'build_seconds':r['build_seconds'],'search_seconds':r['search_seconds']}
            rows.append(row)
    aggregate={}
    for method in METHODS:
        r=[x for x in rows if x['method']==method];good=[x for x in r if x['feasible']]
        aggregate[method]={'feasible':len(good),'best_known':sum(x['best_known_attained'] for x in r),
                           'shared_certified':sum(x['certified_with_shared_bound'] for x in r),
                           'own_certified':sum(x['certified_by_own_bounds'] for x in r),
                           'mean_seconds_all_runs':avg([x['total_seconds'] for x in r]),
                           'median_seconds_all_runs':med([x['total_seconds'] for x in r]),
                           'max_seconds':max(x['total_seconds'] for x in r),
                           'conditional_mean_regret_percent':avg([x['regret_percent_to_best_known'] for x in good])}
    blocks=[]
    for family in ['U','C']:
        for n in [16,32,64]:
            b={'family':family,'n':n,'count':4,'methods':{}}
            these=[c for c in cases if c['family']==family and c['n']==n]
            common=[c for c in these if all(c['results'][a]['feasible'] for a in METHODS)]
            b['all_four_common_feasible']=len(common)
            for method in METHODS:
                r=[x for x in rows if x['method']==method and x['family']==family and x['n']==n]
                b['methods'][method]={'feasible':sum(x['feasible'] for x in r),
                                      'own_certified':sum(x['certified_by_own_bounds'] for x in r),
                                      'shared_certified':sum(x['certified_with_shared_bound'] for x in r),
                                      'mean_L_on_all_four_common':avg([c['results'][method]['L'] for c in common]),
                                      'mean_time':avg([x['total_seconds'] for x in r])}
            blocks.append(b)
    pairs={}
    for other in ['P1','G','LS']:
        common=[c for c in cases if c['results']['P2']['feasible'] and c['results'][other]['feasible']]
        differences=[]
        for c in common:
            MF=sum(len(c['instance']['targets'][t]) for t in range(16,32))
            differences.append({'case':c['name'],'family':c['family'],'n':c['n'],
                                'P2_minus_other':c['results']['P2']['L']-c['results'][other]['L'],
                                'normalized_percent':100*(c['results']['P2']['L']-c['results'][other]['L'])/max(MF,1)})
        pairs[other]={'common':len(common),'P2_better':sum(d['P2_minus_other']<0 for d in differences),
                     'ties':sum(d['P2_minus_other']==0 for d in differences),
                     'P2_worse':sum(d['P2_minus_other']>0 for d in differences),
                     'mean_difference':avg([d['P2_minus_other'] for d in differences]),
                     'mean_normalized_percent':avg([d['normalized_percent'] for d in differences]),
                     'differences':differences}
    statuses={a:{str(s):sum(c['results'][a]['solver_status']==s for c in cases) for s in range(5)} for a in ['P1','P2']}
    summary={'protocol':data['protocol'],'environment':data['environment'],'case_count':24,'run_count':96,
             'aggregate':aggregate,'blocks':blocks,'paired_comparisons_P2':pairs,
             'solver_status_counts':statuses,'rows':rows,'geometry':geometry,
             'cases_with_any_solution':sum(any(c['results'][m]['feasible'] for m in METHODS) for c in cases),
             'cases_with_shared_optimal_value':sum(any(r['case']==c['name'] and r['certified_with_shared_bound'] for r in rows) for c in cases)}
    (EXP/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (EXP/'results_table.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({k:summary[k] for k in ['aggregate','blocks','solver_status_counts','cases_with_any_solution','cases_with_shared_optimal_value']},ensure_ascii=False,indent=2))
    print('PAIRS',json.dumps({a:{k:v for k,v in d.items() if k!='differences'} for a,d in pairs.items()},ensure_ascii=False))

if __name__=='__main__':main()
