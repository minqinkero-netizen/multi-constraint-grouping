"""Predeclared 24-instance, 4-method benchmark for the paper's P1/P2 model.

No industrial acceptance claims. Feasible witnesses stay outside algorithm
inputs. Each method has a 3-second soft end-to-end deadline; auditing overhead
and solver overshoot are measured, not hidden. Trials are run sequentially.
"""
from pathlib import Path
from itertools import combinations, product
import argparse
import json
import math
import os
import platform
import time
import warnings
import numpy as np
import scipy
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix
from solve_and_restore import build_p2, restore, audit_p1, normalize_integer_x

ROOT = Path(__file__).resolve().parent
EXP = ROOT/'experiments'
METHODS = ['G', 'LS', 'P1', 'P2']
PROTOCOL = {'families':['U','C'], 'sizes':[16,32,64], 'seeds':[1001,1002,1003,1004],
            'T':32, 'strict_rounds':16, 'K':5, 'resources_per_witness_group':4,
            'strict_group_inclusion_probability':.55, 'soft_target_probability':.25,
            'soft_deadline_seconds':3., 'solver_threads':1, 'mip_rel_gap':0.,
            'methods':METHODS, 'heuristic_rng_seed_rule':'700000 + 1000*family_index + 10*n + seed',
            'execution_order_seed_rule':'800000 + 1000*family_index + 10*n + seed',
            'repetitions_per_instance_method':1,
            'scope':'24 independent synthetic inputs; 96 method runs; no tuning or discarding by result'}


def generate(family,n,seed):
    rng=np.random.default_rng(seed+100*n+(100000 if family=='C' else 0));m=n//4
    if family=='U':
        points=rng.uniform(0,1,(n,2));remaining=list(range(n));groups=[]
        while remaining:
            first=remaining.pop(0)
            near=sorted(remaining,key=lambda j:(math.dist(points[first],points[j]),j))[:3]
            groups.append([first]+near)
            remaining=[j for j in remaining if j not in near]
        radius=max(math.dist(points[i],points[j]) for g in groups for i,j in combinations(g,2))*1.02
    else:
        side=math.ceil(math.sqrt(m));step=1/side
        centers=np.array([[(g%side+.5)*step,(g//side+.5)*step] for g in range(m)])
        points=np.vstack([centers[g]+rng.uniform(-.18*step,.18*step,(4,2)) for g in range(m)])
        groups=[list(range(4*g,4*g+4)) for g in range(m)];radius=1.35*step
    labels=np.zeros(n,int)
    for g,members in enumerate(groups):labels[members]=g
    perm=rng.permutation(n);points=points[perm];labels=labels[perm]
    groups=[np.flatnonzero(labels==g).tolist() for g in range(m)]
    targets=[]
    for t in range(32):
        if t<16:
            ts=[int(rng.choice(g)) for g in groups if rng.random()<.55]
        else:ts=np.flatnonzero(rng.random(n)<.25).tolist()
        targets.append(sorted(ts))
    d={'n':n,'m':m,'K':5,'r':radius,'points':points.tolist(),'targets':targets,'strict':list(range(16))}
    x=np.eye(m,dtype=int)[labels]
    _,_,_,a=restore(d,x)
    return d,{'labels_zero_based':labels.tolist(),'L':a['L'],'audit':a}


def full_p1(d):
    n,m,T=d['n'],d['m'],len(d['targets']);nx=n*m;nv=nx+n*T*m
    S=set(d['strict']);F=[t for t in range(T) if t not in S]
    ix=lambda i,g:i*m+g
    iy=lambda i,t,g:nx+(i*T+t)*m+g
    c=np.zeros(nv)
    for i,t,g in product(range(n),F,range(m)):c[iy(i,t,g)]=-1
    rr=[];cc=[];vv=[];lo=[];hi=[]
    def row(terms,l=-np.inf,u=np.inf):
        k=len(lo)
        for j,v in terms:rr.append(k);cc.append(j);vv.append(v)
        lo.append(l);hi.append(u)
    for i in range(n):row([(ix(i,g),1) for g in range(m)],1,1)
    for g in range(m):row([(ix(i,g),1) for i in range(n)],u=d['K'])
    for i,j in combinations(range(n),2):
        if math.dist(d['points'][i],d['points'][j])>d['r']:
            for g in range(m):row([(ix(i,g),1),(ix(j,g),1)],u=1)
    for i,t,g in product(range(n),range(T),range(m)):
        row([(iy(i,t,g),1),(ix(i,g),-1)],u=0)
    ts=[set(v) for v in d['targets']]
    for i,t in product(range(n),range(T)):
        a=int(i in ts[t]);row([(iy(i,t,g),1) for g in range(m)],a if t in S else 0,a)
    for t,g in product(range(T),range(m)):
        row([(iy(i,t,g),1) for i in range(n)],u=1)
    A=coo_matrix((vv,(rr,cc)),shape=(len(lo),nv)).tocsc()
    return c,np.ones(nv,int),Bounds(np.zeros(nv),np.ones(nv)),LinearConstraint(A,lo,hi),{
        'nx':nx,'variables':nv,'binary_variables':nv,'continuous_variables':0,'rows':len(lo),
        'objective_offset':sum(len(d['targets'][t]) for t in F)}


def finite(v):
    return float(v) if v is not None and math.isfinite(float(v)) else None


def solve_mip(d,kind,budget):
    start=time.perf_counter();deadline=start+budget
    if kind=='P1':c,integ,bounds,constraints,meta=full_p1(d)
    else:
        c,integ,bounds,constraints,md=build_p2(d)
        meta={'nx':md['nx'],'variables':len(c),'binary_variables':md['nx'],
              'continuous_variables':md['nz'],'rows':md['rows'],'objective_offset':0}
    built=time.perf_counter();remaining=max(.001,deadline-built)
    with warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter('always')
        res=milp(c,integrality=integ,bounds=bounds,constraints=constraints,
                 options={'presolve':True,'mip_rel_gap':0.,'time_limit':remaining,'threads':1})
    solved=time.perf_counter()
    out={'method':kind,'solver_status':int(res.status),'solver_message':res.message,
         'build_seconds':built-start,'search_seconds':solved-built,'model_size':meta,
         'warnings':[str(w.message) for w in ws],'solver_time_limit':remaining,
         'lower_bound':None,'solver_objective':None,'feasible':False,'L':None,
         'certified_by_own_bounds':False,'labels':None}
    offset=meta['objective_offset']
    rb=finite(getattr(res,'mip_dual_bound',None))
    out['lower_bound']=rb+offset if rb is not None else None
    rv=finite(res.fun);out['solver_objective']=rv+offset if rv is not None else None
    out['node_count']=int(res.mip_node_count) if getattr(res,'mip_node_count',None) is not None else None
    if res.x is not None and res.status in (0,1):
        x=normalize_integer_x(d,res.x[:meta['nx']].reshape(d['n'],d['m']))
        if kind=='P1':
            rawy=res.x[meta['nx']:].reshape(d['n'],len(d['targets']),d['m'])
            if np.max(abs(rawy-np.rint(rawy)))>1e-6:raise ValueError('fractional P1 incumbent y')
            raw_audit=audit_p1(d,x,np.rint(rawy).astype(int))
            if not raw_audit['feasible']:raise ValueError('P1 incumbent violates original constraints')
            out['raw_P1_L']=raw_audit['L']
        _,_,_,audit=restore(d,x)
        out.update(feasible=True,L=audit['L'],labels=x.argmax(axis=1).tolist(),audit=audit)
        F=[t for t in range(len(d['targets'])) if t not in d['strict']]
        count_bound=sum(max(len(d['targets'][t])-d['m'],0) for t in F)
        b=out['lower_bound']
        out['certified_by_own_bounds']=(audit['L']==count_bound) or (
            res.status==0 and b is not None and abs(audit['L']-b)<=1e-6)
    out['total_seconds']=time.perf_counter()-start
    return out


def heuristic_data(d):
    n,m=d['n'],d['m'];hard=[0]*n
    for i,j in combinations(range(n),2):
        if math.dist(d['points'][i],d['points'][j])>d['r']:
            hard[i]|=1<<j;hard[j]|=1<<i
    for t in d['strict']:
        for i,j in combinations(d['targets'][t],2):hard[i]|=1<<j;hard[j]|=1<<i
    F=[t for t in range(len(d['targets'])) if t not in d['strict']]
    st=[[] for _ in range(n)]
    for k,t in enumerate(F):
        for i in d['targets'][t]:st[i].append(k)
    return hard,st,len(F)


def construct(d,hard,st,nf,rng,deadline):
    n,m=d['n'],d['m'];groups=[0]*m;sizes=[0]*m;cnt=[[0]*nf for _ in range(m)]
    labels=[-1]*n;order=rng.permutation(n).tolist();remaining=set(order)
    for step in range(n):
        if time.perf_counter()>=deadline:return None
        chosen=None;allowed=None;key=None
        for i in order:
            if i not in remaining:continue
            cand=[g for g in range(m) if sizes[g]<d['K'] and not(hard[i]&groups[g])]
            if not cand:return None
            score=(len(cand),-hard[i].bit_count())
            if key is None or score<key:chosen,allowed,key=i,cand,score
        i=chosen
        score={g:(sum(cnt[g][t]>0 for t in st[i]),sizes[g]) for g in allowed}
        best=min(score.values());ties=[g for g in allowed if score[g]==best]
        g=int(rng.choice(ties));labels[i]=g;groups[g]|=1<<i;sizes[g]+=1
        for t in st[i]:cnt[g][t]+=1
        remaining.remove(i)
    return labels,groups,sizes,cnt


def qcounts(cnt):return sum(max(c-1,0) for group in cnt for c in group)


def improve(d,state,hard,st,rng,deadline):
    labels,groups,sizes,cnt=state;n,m=d['n'],d['m'];q=qcounts(cnt);accepted=0;proposals=0
    while time.perf_counter()<deadline:
        changed=False;ids=rng.permutation(n).tolist()
        for i in ids:
            g=labels[i]
            for h in rng.permutation(m).tolist():
                if time.perf_counter()>=deadline:return state,q,accepted,proposals
                if h==g or sizes[h]>=d['K'] or hard[i]&groups[h]:continue
                proposals+=1
                delta=sum(int(cnt[h][t]>0)-int(cnt[g][t]>1) for t in st[i])
                if delta<0:
                    groups[g]^=1<<i;groups[h]|=1<<i;sizes[g]-=1;sizes[h]+=1;labels[i]=h
                    for t in st[i]:cnt[g][t]-=1;cnt[h][t]+=1
                    q+=delta;accepted+=1;changed=True;break
            if changed:break
        if changed:
            assert q==qcounts(cnt)
            continue
        for k,i in enumerate(ids):
            g=labels[i]
            for j in ids[k+1:]:
                if time.perf_counter()>=deadline:return state,q,accepted,proposals
                h=labels[j]
                if g==h or hard[i]&(groups[h]^(1<<j)) or hard[j]&(groups[g]^(1<<i)):continue
                proposals+=1;si=set(st[i]);sj=set(st[j]);delta=0
                for t in si^sj:
                    move=1 if t in si else -1
                    delta+=max(cnt[g][t]-move-1,0)+max(cnt[h][t]+move-1,0)-max(cnt[g][t]-1,0)-max(cnt[h][t]-1,0)
                if delta<0:
                    groups[g]^=(1<<i)|(1<<j);groups[h]^=(1<<i)|(1<<j);labels[i],labels[j]=h,g
                    for t in st[i]:cnt[g][t]-=1;cnt[h][t]+=1
                    for t in st[j]:cnt[h][t]-=1;cnt[g][t]+=1
                    q+=delta;accepted+=1;changed=True;break
            if changed:break
        assert q==qcounts(cnt)
        if not changed:break
    return state,q,accepted,proposals


def solve_heuristic(d,kind,budget,seed):
    start=time.perf_counter();deadline=start+budget;rng=np.random.default_rng(seed)
    hard,st,nf=heuristic_data(d);built=time.perf_counter()
    F=[t for t in range(len(d['targets'])) if t not in d['strict']]
    lower=sum(max(len(d['targets'][t])-d['m'],0) for t in F)
    best=None;value=math.inf;attempts=0;complete=0;accepted=0;proposals=0;trace=[]
    while time.perf_counter()<deadline:
        attempts+=1;state=construct(d,hard,st,nf,rng,deadline)
        if state is None:continue
        complete+=1
        if kind=='LS':state,q,a,p=improve(d,state,hard,st,rng,deadline);accepted+=a;proposals+=p
        else:q=qcounts(state[3])
        if q<value:
            value=q;best=state[0].copy();trace.append({'seconds':time.perf_counter()-start,'L':q})
        if value==lower:break
    ended=time.perf_counter()
    out={'method':kind,'solver_status':None,'lower_bound':lower,'feasible':best is not None,'L':None,
         'certified_by_own_bounds':False,'labels':best,'seed':seed,'attempts':attempts,
         'completed_constructions':complete,'accepted_improvements':accepted,'neighborhood_proposals':proposals,
         'build_seconds':built-start,'search_seconds':ended-built,'improvement_trace':trace}
    if best is not None:
        _,_,_,audit=restore(d,np.eye(d['m'],dtype=int)[best])
        assert audit['L']==value
        out.update(L=value,audit=audit,certified_by_own_bounds=value==lower)
    out['total_seconds']=time.perf_counter()-start
    return out


def environment():
    cpu=platform.processor() or 'unknown'
    cpuinfo=Path('/proc/cpuinfo')
    for line in (cpuinfo.read_text().splitlines() if cpuinfo.is_file() else []):
        if line.startswith('model name'):cpu=line.split(':',1)[1].strip();break
    return {'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,
            'platform':platform.platform(),'cpu_model':cpu,'logical_cpu_count':os.cpu_count(),
            'affinity_cpu_count':len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
            'OMP_NUM_THREADS':os.environ.get('OMP_NUM_THREADS'),'OPENBLAS_NUM_THREADS':os.environ.get('OPENBLAS_NUM_THREADS')}


def main():
    EXP.mkdir(exist_ok=True)
    (EXP/'protocol.json').write_text(json.dumps(PROTOCOL,ensure_ascii=False,indent=2)+'\n')
    records=[]
    # Warm the backend once, with the same thread setting as measured calls.
    base=json.loads((ROOT/'reduction_checks.json').read_text())['base_instance']
    for kind in ['P1','P2']:
        v=solve_mip(base,kind,1.);assert v['feasible'] and v['L']==0 and v['certified_by_own_bounds']
    for fi,family in enumerate(PROTOCOL['families']):
        for n in PROTOCOL['sizes']:
            for seed in PROTOCOL['seeds']:
                d,w=generate(family,n,seed);name=f'{family}_n{n}_s{seed}'
                (EXP/(name+'_input.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
                (EXP/(name+'_witness.json')).write_text(json.dumps(w,ensure_ascii=False,indent=2)+'\n')
                order=np.random.default_rng(800000+1000*fi+10*n+seed).permutation(METHODS).tolist()
                case={'name':name,'family':family,'n':n,'seed':seed,'instance':d,'execution_order':order,'results':{}}
                for method in order:
                    if method in ['P1','P2']:result=solve_mip(d,method,PROTOCOL['soft_deadline_seconds'])
                    else:result=solve_heuristic(d,method,PROTOCOL['soft_deadline_seconds'],700000+1000*fi+10*n+seed)
                    case['results'][method]=result
                    assert result.get('solver_status')!=2,'Planted-feasible instance reported infeasible'
                    (EXP/(name+'_results.json')).write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
                    print(json.dumps({'case':name,'method':method,'feasible':result['feasible'],'L':result['L'],
                                      'optimal':result['certified_by_own_bounds'],'seconds':round(result['total_seconds'],3)},ensure_ascii=False),flush=True)
                records.append(case)
                (EXP/'results.json').write_text(json.dumps({'protocol':PROTOCOL,'environment':environment(),'cases':records},ensure_ascii=False,indent=2)+'\n')
    assert len(records)==24 and sum(len(c['results']) for c in records)==96


if __name__=='__main__':main()
