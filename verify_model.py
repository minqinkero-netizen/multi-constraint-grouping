"""Check the binary assignment-and-activation model on a constructed example.

These checks validate the formulation, not the performance of a proposed method.
"""
from pathlib import Path
from itertools import product, combinations
import json
import math
import platform
import numpy as np
import scipy
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT/'example.json').read_text())
POINTS = [tuple(DATA['coordinates'][str(i)]) for i in range(1,9)]
TARGETS = [set(r['targets']) for r in DATA['rounds']]
STRICT = [r['strict'] for r in DATA['rounds']]
N, M, T, K = 8, 2, 4, 5

def semantic_check(labels, radius):
    """Direct set/geometry definition; does not inspect MILP constraint rows."""
    groups = [{i+1 for i,g in enumerate(labels) if g==h} for h in range(M)]
    if any(len(g)>K for g in groups): return None
    for g in groups:
        for i,j in combinations(g,2):
            if math.dist(POINTS[i-1],POINTS[j-1]) > radius+1e-12: return None
    for targets, strict in zip(TARGETS, STRICT):
        if strict and any(len(targets & g)>1 for g in groups): return None
    return sum(max(len(targets & g)-1,0) for targets,strict in zip(TARGETS,STRICT)
               if not strict for g in groups)

def solve_model(radius=.65, fixed_groups=None):
    nx=N*M; nv=nx+N*T*M
    ix=lambda i,g:i*M+g
    iy=lambda i,t,g:nx+(i*T+t)*M+g
    objective=np.zeros(nv)
    for i,t,g in product(range(N),range(T),range(M)):
        if not STRICT[t]:objective[iy(i,t,g)]=-1
    rr=[];cc=[];vv=[];lower=[];upper=[]
    def row(terms, lo=-np.inf, hi=np.inf):
        rowid=len(lower)
        for col,val in terms:rr.append(rowid);cc.append(col);vv.append(val)
        lower.append(lo);upper.append(hi)
    for i in range(N):row([(ix(i,g),1) for g in range(M)],1,1)
    for g in range(M):row([(ix(i,g),1) for i in range(N)],hi=K)
    for i,j in combinations(range(N),2):
        if math.dist(POINTS[i],POINTS[j])>radius:
            for g in range(M):row([(ix(i,g),1),(ix(j,g),1)],hi=1)
    for i,t,g in product(range(N),range(T),range(M)):
        row([(iy(i,t,g),1),(ix(i,g),-1)],hi=0)
    for i,t in product(range(N),range(T)):
        a=int(i+1 in TARGETS[t])
        row([(iy(i,t,g),1) for g in range(M)],a if STRICT[t] else 0,a)
    for t,g in product(range(T),range(M)):
        row([(iy(i,t,g),1) for i in range(N)],hi=1)
    lb=np.zeros(nv);ub=np.ones(nv)
    if fixed_groups is not None:
        for i,g in product(range(N),range(M)):
            val=int(i+1 in fixed_groups[g]);lb[ix(i,g)]=val;ub[ix(i,g)]=val
    A=coo_matrix((vv,(rr,cc)),shape=(len(lower),nv)).tocsc()
    res=milp(objective,integrality=np.ones(nv,dtype=np.int32),
             bounds=Bounds(lb,ub),constraints=LinearConstraint(A,lower,upper),
             options={'time_limit':10.,'mip_rel_gap':0.})
    out={'status':int(res.status),'message':res.message,'binary_variables':nv,
         'constraint_rows':len(lower),'radius':radius,'loss':None}
    if res.x is not None:
        assert np.max(np.abs(res.x-np.rint(res.x)))<1e-6
        values=np.rint(res.x).astype(int)
        x=values[:nx].reshape(N,M);y=values[nx:].reshape(N,T,M)
        assert np.all(x.sum(axis=1)==1)
        labels=x.argmax(axis=1).tolist()
        semantic_loss=semantic_check(labels,radius)
        assert semantic_loss is not None
        missed=[]
        for t,targets in enumerate(TARGETS):
            assert all(y[i,t,g]<=x[i,g] for i,g in product(range(N),range(M)))
            assert all(y[i,t,:].sum()<=int(i+1 in targets) for i in range(N))
            assert all(y[:,t,g].sum()<=1 for g in range(M))
            if STRICT[t]:assert all(y[i,t,:].sum()==int(i+1 in targets) for i in range(N))
            missed.append(len(targets)-int(y[:,t,:].sum()))
        loss=sum(v for v,s in zip(missed,STRICT) if not s)
        assert loss==semantic_loss
        constant=sum(len(t) for t,s in zip(TARGETS,STRICT) if not s)
        assert abs(loss-(constant+res.fun))<1e-6
        out.update(loss=loss,groups=[[i+1 for i,h in enumerate(labels) if h==g]
                                   for g in range(M)],x=x.tolist(),y=y.tolist(),
                   round_losses=missed,mip_gap=float(res.mip_gap),
                   variable_part=float(res.fun),constant_part=constant)
    return out

def main():
    exact=[];canonical=set()
    for labels in product(range(M),repeat=N):
        loss=semantic_check(labels,.65)
        if loss is not None:
            exact.append(loss)
            canonical.add(tuple(g^labels[0] for g in labels))
    free=solve_model()
    fixed_a=solve_model(fixed_groups=DATA['partitions']['A'])
    fixed_b=solve_model(fixed_groups=DATA['partitions']['B'])
    infeasible=solve_model(radius=.1)
    assert free['status']==fixed_a['status']==fixed_b['status']==0
    assert free['loss']==min(exact)==0
    assert fixed_a['loss']==2 and fixed_b['loss']==0
    assert infeasible['status']==2
    assert all(semantic_check(labels,.1) is None for labels in product(range(M),repeat=N))
    assert len(exact)==32 and len(canonical)==16
    result={'purpose':'formulation consistency checks, not algorithm benchmarks',
            'environment':{'python':platform.python_version(),'numpy':np.__version__,
                           'scipy':scipy.__version__},
            'enumeration':{'labeled_assignments_tested':2**N,
                           'feasible_labeled_assignments':len(exact),
                           'feasible_unlabeled_partitions':len(canonical),
                           'best_loss':min(exact),'worst_best_execution_loss':max(exact)},
            'free':free,'fixed_A':fixed_a,'fixed_B':fixed_b,
            'infeasible_distance_case':infeasible}
    (ROOT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'enumeration':result['enumeration'],
                      'model_losses':{'free':free['loss'],'A':fixed_a['loss'],'B':fixed_b['loss']},
                      'infeasible_status':infeasible['status']},ensure_ascii=False))

if __name__=='__main__':main()
