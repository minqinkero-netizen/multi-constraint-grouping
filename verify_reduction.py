"""P1 vs exact reduced P2 vs LP: formulation checks, not timing benchmarks."""
from pathlib import Path
from itertools import product,combinations
import json,math,platform
import numpy as np
import scipy
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix
ROOT=Path(__file__).resolve().parent

def solve(d,kind='P2',fixed=None):
    n,m,T,K=d['n'],d['m'],len(d['targets']),d['K']
    targets=[set(v) for v in d['targets']];S=set(d['strict']);F=[t for t in range(T) if t not in S]
    nx=n*m;nv=nx+(n*T*m if kind=='P1' else len(F)*m)
    ix=lambda i,g:i*m+g
    iy=lambda i,t,g:nx+(i*T+t)*m+g
    iz=lambda t,g:nx+F.index(t)*m+g
    c=np.zeros(nv);lo=np.zeros(nv);hi=np.ones(nv)
    integ=np.ones(nv,dtype=np.int32)
    if kind!='P1':hi[nx:]=np.inf;integ[nx:]=0;c[nx:]=1
    else:
        for i,t,g in product(range(n),F,range(m)):c[iy(i,t,g)]=-1
    if kind=='LP':integ[:]=0
    if fixed is not None:
        for i,g in product(range(n),range(m)):lo[ix(i,g)]=hi[ix(i,g)]=int(fixed[i]==g)
    rr=[];cc=[];vv=[];bl=[];bu=[]
    def add(items,l=-np.inf,u=np.inf):
        k=len(bl)
        for j,v in items:rr.append(k);cc.append(j);vv.append(v)
        bl.append(l);bu.append(u)
    for i in range(n):add([(ix(i,g),1) for g in range(m)],1,1)
    for g in range(m):add([(ix(i,g),1) for i in range(n)],u=K)
    for i,j in combinations(range(n),2):
        if math.dist(d['points'][i],d['points'][j])>d['r']:
            for g in range(m):add([(ix(i,g),1),(ix(j,g),1)],u=1)
    if kind=='P1':
        for i,t,g in product(range(n),range(T),range(m)):
            add([(iy(i,t,g),1),(ix(i,g),-1)],u=0)
        for i,t in product(range(n),range(T)):
            a=int(i in targets[t]);add([(iy(i,t,g),1) for g in range(m)],a if t in S else 0,a)
        for t,g in product(range(T),range(m)):add([(iy(i,t,g),1) for i in range(n)],u=1)
    else:
        for t,g in product(S,range(m)):add([(ix(i,g),1) for i in targets[t]],u=1)
        for t,g in product(F,range(m)):
            add([(ix(i,g),1) for i in targets[t]]+[(iz(t,g),-1)],u=1)
    A=coo_matrix((vv,(rr,cc)),shape=(len(bl),nv)).tocsc()
    res=milp(c,integrality=integ,bounds=Bounds(lo,hi),
             constraints=LinearConstraint(A,bl,bu),options={'time_limit':10,'mip_rel_gap':0})
    out={'status':int(res.status),'variables':nv,'constraint_rows':len(bl),'objective':None}
    if res.x is not None:
        val=float(res.fun)+(sum(len(targets[t]) for t in F) if kind=='P1' else 0)
        out.update(objective=val,x=res.x[:nx].reshape(n,m).tolist())
        if kind=='P1':out['y']=res.x[nx:].reshape(n,T,m).tolist()
        else:out['z']=res.x[nx:].reshape(len(F),m).tolist()
    return out

def direct(d,labels,restore=False):
    n,m,T,K=d['n'],d['m'],len(d['targets']),d['K'];S=set(d['strict'])
    groups=[[i for i in range(n) if labels[i]==g] for g in range(m)]
    if any(len(g)>K for g in groups):return None
    if any(math.dist(d['points'][i],d['points'][j])>d['r']+1e-12
           for group in groups for i,j in combinations(group,2)):return None
    loss=0;y=np.zeros((n,T,m),int)
    for t,ts in enumerate(d['targets']):
        for g,group in enumerate(groups):
            hit=sorted(set(group)&set(ts))
            if t in S and len(hit)>1:return None
            if hit:y[hit[0],t,g]=1
            if t not in S:loss+=max(len(hit)-1,0)
    # Independently check the restored P1 execution against all semantic constraints.
    for i,t,g in product(range(n),range(T),range(m)):
        assert y[i,t,g]<=int(labels[i]==g)
    for i,t in product(range(n),range(T)):
        a=int(i in d['targets'][t]);assert sum(y[i,t,:])<=a
        if t in S:assert sum(y[i,t,:])==a
    for t,g in product(range(T),range(m)):assert sum(y[:,t,g])<=1
    measured=sum(len(d['targets'][t])-int(y[:,t,:].sum()) for t in range(T) if t not in S)
    assert measured==loss
    return (loss,y.tolist()) if restore else loss

def planted(seed,n,m,T,geometric):
    rng=np.random.default_rng(seed);labels=np.arange(n)%m
    if geometric:
        points=np.c_[labels*.7,np.zeros(n)]+rng.uniform(-.05,.05,(n,2));r=.22
    else:points=rng.uniform(0,1,(n,2));r=1.5
    targets=[];S=list(range(T//2))
    for t in range(T):
        if t in S:
            ts=[int(rng.choice(np.flatnonzero(labels==g))) for g in range(m) if rng.random()<.7]
        else:ts=np.flatnonzero(rng.random(n)<.5).tolist()
        targets.append(ts)
    return {'n':n,'m':m,'K':5,'r':r,'points':points.tolist(),'targets':targets,'strict':S,'seed':seed}

def main():
    old=json.loads((ROOT/'example.json').read_text())
    base={'n':8,'m':2,'K':5,'r':.65,
          'points':[old['coordinates'][str(i)] for i in range(1,9)],
          'targets':[[i-1 for i in r['targets']] for r in old['rounds']],
          'strict':[t for t,r in enumerate(old['rounds']) if r['strict']]}
    checks=[]
    for labels in product(range(2),repeat=8):
        q=direct(base,labels)
        if q is None:continue
        a=solve(base,'P1',labels);b=solve(base,'P2',labels)
        assert a['status']==b['status']==0 and abs(a['objective']-q)<1e-7 and abs(b['objective']-q)<1e-7
        checks.append({'labels':list(labels),'closed_loss':q,'P1':a['objective'],'P2':b['objective']})
    base_results={kind:solve(base,kind) for kind in ['P1','P2','LP']}
    assert all(v['status']==0 and abs(v['objective'])<1e-7 for v in base_results.values())
    extra=[]
    for spec in [(11,6,2,4,False),(22,6,2,4,True),(33,5,2,3,False),
                 (44,7,2,5,True),(55,9,3,6,False),(66,9,3,6,True)]:
        d=planted(*spec);sols={k:solve(d,k) for k in ['P1','P2','LP']}
        assert all(v['status']==0 for v in sols.values())
        assert abs(sols['P1']['objective']-sols['P2']['objective'])<1e-7
        assert sols['LP']['objective']<=sols['P2']['objective']+1e-7
        x=np.array(sols['P2']['x']);assert np.max(abs(x-np.rint(x)))<1e-6
        labels=x.argmax(axis=1).tolist();q,y=direct(d,labels,True)
        assert abs(q-sols['P2']['objective'])<1e-7
        extra.append({'instance':d,'results':sols,'restored_labels':labels,'restored_y':y})
    tight={**base,'r':.1};bad={k:solve(tight,k) for k in ['P1','P2','LP']}
    assert bad['P1']['status']==bad['P2']['status']==2
    assert bad['LP']['status']==0 and abs(bad['LP']['objective'])<1e-7
    assert np.max(abs(np.array(bad['LP']['x'])-.5))<1e-7
    for k in ['P1','P2']:
        for case in extra:
            assert case['results'][k]['objective']>=-1e-7
    out={'purpose':'equivalence and relaxation checks; not a speed or quality benchmark',
         'environment':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
         'base_instance':base,'base_results':base_results,'fixed_partition_checks':checks,
         'extra_instances':extra,'tight_distance_instance':tight,'tight_distance_results':bad,
         'counts':{'fixed_feasible_assignments':len(checks),'extra_instances':len(extra),
                   'P1_binary_variables':80,'P2_binary_variables':16,'P2_continuous_variables':4}}
    (ROOT/'reduction_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'counts':out['counts'],'extra_optima':[r['results']['P2']['objective'] for r in extra],
                      'tight_statuses':{k:v['status'] for k,v in bad.items()}},ensure_ascii=False))
if __name__=='__main__':main()
