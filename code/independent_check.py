"""Audit public inputs and saved outputs without importing the optimizer.
Integer checks are direct set operations on original coordinates and targets.
"""
from itertools import combinations
import math
import numpy as np

def check_labels(d,labels):
    n,m=d['n'],d['m']
    assert len(labels)==n and all(isinstance(g,int) and 0<=g<m for g in labels)
    groups=[{i for i,g in enumerate(labels) if g==j} for j in range(m)]
    capacity=sum(max(len(g)-d['K'],0) for g in groups)
    distance=sum(not(math.dist(d['points'][i],d['points'][j])<=d['r']) for g in groups for i,j in combinations(g,2))
    important=sum(max(len(g&set(d['targets'][t]))-1,0) for g in groups for t in d['strict'])
    L=sum(len(targets)-sum(bool(g&set(targets)) for g in groups) for t,targets in enumerate(d['targets']) if t not in d['strict'])
    return dict(H=capacity+distance+important,L=L,capacity=capacity,distance=distance,important=important,groups=groups)

def audit_result(d,r,check_trace=True):
    labels=r.get('labels');H=None;L=None
    if labels is not None:
        a=check_labels(d,labels);H=a['H'];assert H==r['H']
        if H==0:
            L=a['L'];assert L==r['L'];assert len(r['calls'])==len(d['targets'])
            assert r['groups']==[sorted(i+1 for i in g) for g in a['groups']]
            actual_total=0
            for t,c in enumerate(r['calls']):
                activated=[]
                assert len(c['by_manager'])==d['m']
                for g,active in enumerate(c['by_manager']):
                    assert len(active)<=1
                    for i1 in active:
                        i=i1-1;assert i in d['targets'][t] and labels[i]==g;activated.append(i)
                assert len(activated)==len(set(activated))
                assert set(i+1 for i in activated)==set(c['activated'])
                missed=set(d['targets'][t])-set(activated)
                assert {i+1 for i in missed}==set(c['missing']) and len(missed)==c['omissions']
                if t in d['strict']:assert not missed
                else:actual_total+=len(missed)
            assert actual_total==L
    assert bool(r.get('feasible'))==(H==0) and r.get('L')==L
    if L is not None:
        if r.get('lower_bound') is not None:assert r['lower_bound']<=L+2e-6
        if r.get('before_local_L') is not None:assert r['before_local_L']>=L
    if check_trace and r.get('trace'):
        values=[t['L'] for t in r['trace']]
        assert all(a>b for a,b in zip(values,values[1:]))
        assert values[-1]==L
    if r.get('raw_labels') is not None:assert check_labels(d,r['raw_labels'])['H']==r['raw_H']
    if r.get('before_local_labels') is not None:
        before=check_labels(d,r['before_local_labels']);assert before['H']==0 and before['L']==r['before_local_L']
    for field in ['raw_rounding','repair']:
        lab=r.get(field+'_labels')
        if lab is not None:assert check_labels(d,lab)['H']==r[field+'_H']
    return dict(checked=True,feasible=r.get('feasible',False),L=L,H=H)

def audit_lp(d,x,obj):
    x=np.asarray(x);tol=2e-6;n,m=d['n'],d['m']
    assert x.shape==(n,m) and np.isfinite(x).all()
    residual=max(float(abs(x.sum(1)-1).max()),float(np.maximum(x.sum(0)-d['K'],0).max()),float(max(-x.min(),x.max()-1,0)))
    for i,j in combinations(range(n),2):
        if not(math.dist(d['points'][i],d['points'][j])<=d['r']):residual=max(residual,float(np.maximum(x[i]+x[j]-1,0).max()))
    for t in d['strict']:
        if d['targets'][t]:residual=max(residual,float(np.maximum(x[d['targets'][t]].sum(0)-1,0).max()))
    assert residual<=tol
    count=sum(max(len(ts)-m,0) for t,ts in enumerate(d['targets']) if t not in d['strict'])
    convex=sum(float(np.maximum(x[ts].sum(0)-1,0).sum()) for t,ts in enumerate(d['targets']) if t not in d['strict'])
    assert abs(count-obj)<=1e-4 and abs(convex-obj)<=1e-4
    return dict(checked=True,max_constraint_residual=residual,lp_objective=obj,count_bound=count)

def unpack_lp(d,r):
    x=np.zeros((d['n'],d['m']))
    for i,row in enumerate(r['lp_rows']):
        for g,v in row:x[i,g]=v
    return x
