"""Five-method benchmark. Inputs and witnesses are stored separately.
The 600 s watchdog includes Python startup, construction, solve and audit.
No full-P1 optimization is used. Checkpoint results survive a watchdog stop.
"""
from pathlib import Path
import argparse, json, math, os, platform, subprocess, sys, time, warnings
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.spatial.distance import cdist
from grouping_core import restore
from round_repair import repair
import highspy
from solver_backend import solve_highs
ROOT=Path(__file__).resolve().parent
METHODS=['G','LS','SLS','MIP','LPR']

def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False),encoding='utf-8');tmp.replace(path)

def generate(family,n,m,T,seed):
    rng=np.random.default_rng(seed); K=5
    sizes=np.full(m,n//m,int);sizes[:n%m]+=1
    if max(sizes)>K:raise ValueError('capacity')
    if family=='U':
        pts=rng.random((n,2));remaining=list(range(n));groups=[]
        for size in sizes:
            i=remaining.pop(0);near=sorted(remaining,key=lambda j:np.sum((pts[i]-pts[j])**2))[:size-1]
            groups.append([i]+near);remaining=[j for j in remaining if j not in near]
        r=1.02*max(math.dist(pts[i],pts[j]) for g in groups for i in g for j in g)
    elif family in ('C','O'):
        side=math.ceil(math.sqrt(m));s=1/side
        centers=np.array([[(g%side+.5)*s,(g//side+.5)*s] for g in range(m)])
        pts=np.vstack([centers[g]+rng.uniform(-(.18 if family=='C' else .45)*s,(.18 if family=='C' else .45)*s,(size,2)) for g,size in enumerate(sizes)])
        groups=[];start=0
        for size in sizes:groups.append(list(range(start,start+size)));start+=size
        r=1.35*s if family=='C' else 1.02*max(math.dist(pts[i],pts[j]) for g in groups for i in g for j in g)
    else:raise ValueError('unknown family')
    labels=np.empty(n,int)
    for g,ids in enumerate(groups):labels[ids]=g
    perm=rng.permutation(n);pts=pts[perm];labels=labels[perm]
    groups=[np.flatnonzero(labels==g) for g in range(m)]
    strict=list(range(T//2));targets=[]
    for t in range(T):
        targets.append(sorted([int(rng.choice(g)) for g in groups if rng.random()<=.55]) if t in strict else np.flatnonzero(rng.random(n)<=.25).tolist())
    d=dict(n=n,m=m,K=K,r=float(r),points=pts.tolist(),targets=targets,strict=strict)
    return d,dict(labels=labels.tolist(),note='feasible witness; never passed to a method')

def prepare(d):
    n,m=d['n'],d['m'];dist=cdist(d['points'],d['points']);bad=np.logical_not(dist<=d['r']);np.fill_diagonal(bad,False)
    a=np.zeros((len(d['targets']),n),int)
    for t,ids in enumerate(d['targets']):a[t,ids]=1
    for t in d['strict']:
        ids=d['targets'][t];bad[np.ix_(ids,ids)]=True
    np.fill_diagonal(bad,False)
    F=[t for t in range(len(a)) if t not in d['strict']]
    return dict(dist=dist,bad=bad,a=a,soft=a[F],F=F,lower=sum(max(len(d['targets'][t])-m,0) for t in F))

def violations(d,labels):
    n,m=d['n'],d['m'];issues={'assignment':0,'capacity':0,'distance':0,'important':0}
    if labels is None:return None
    labels=np.asarray(labels);issues['assignment']=int(np.sum((labels<0)|(labels>=m)))
    for g in range(m):
        ids=np.flatnonzero(labels==g);issues['capacity']+=max(len(ids)-d['K'],0)
        for k,i in enumerate(ids):
            for j in ids[k+1:]:issues['distance']+=int(not(math.dist(d['points'][i],d['points'][j])<=d['r']))
        group=set(ids.tolist())
        for t in d['strict']:issues['important']+=max(len(group.intersection(d['targets'][t]))-1,0)
    issues['H']=sum(issues.values());return issues

def finish(d,labels,out):
    out['labels']=labels;out['H']=None;out['L']=None;out['feasible']=False
    if labels is None:return out
    audit=violations(d,labels);out['violation_counts']=audit;out['H']=audit['H']
    if audit['H']==0:
        x=np.eye(d['m'],dtype=int)[labels];_,_,groups,audit2=restore(d,x)
        out.update(feasible=True,L=audit2['L'],groups=[[i+1 for i in g] for g in groups],calls=audit2['round_records'],audit=audit2['checks'])
    return out

def model(d,p):
    n,m=d['n'],d['m'];nx=n*m;nf=len(p['F']);nv=nx+nf*m
    rr=[];cc=[];vv=[];rhs=[];nr=0
    # All inequalities have <= form. Equalities are the first n rows.
    def block(r,c,v,b):
        nonlocal nr
        rr.append(np.asarray(r,dtype=np.int32)+nr);cc.append(np.asarray(c,dtype=np.int32));vv.append(np.asarray(v,dtype=float));rhs.extend(b);nr+=len(b)
    block(np.repeat(np.arange(n),m),np.arange(nx),np.ones(nx),np.ones(n))
    block(np.tile(np.arange(m),n),np.arange(nx),np.ones(nx),np.full(m,d['K']))
    di,dj=np.where(np.triu(np.logical_not(p['dist']<=d['r']),1));ne=len(di)
    if ne:
        ids=np.arange(ne*m);g=np.tile(np.arange(m),ne)
        block(np.repeat(ids,2),np.column_stack((np.repeat(di,m)*m+g,np.repeat(dj,m)*m+g)).ravel(),np.ones(2*ne*m),np.ones(ne*m))
    for t in d['strict']:
        ids=np.asarray(d['targets'][t],int)
        if len(ids):block(np.tile(np.arange(m),len(ids)),(ids[:,None]*m+np.arange(m)).ravel(),np.ones(len(ids)*m),np.ones(m))
    for k,t in enumerate(p['F']):
        ids=np.asarray(d['targets'][t],int)
        block(np.r_[np.tile(np.arange(m),len(ids)),np.arange(m)],np.r_[(ids[:,None]*m+np.arange(m)).ravel(),nx+k*m+np.arange(m)],np.r_[np.ones(len(ids)*m),-np.ones(m)],np.ones(m))
    A=coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(nr,nv)).tocsr();b=np.array(rhs)
    c=np.r_[np.zeros(nx),np.ones(nf*m)];ub=np.r_[np.ones(nx),np.full(nf*m,d['K']-1.)]
    # One harmless label symmetry: some optimum can label resource 1's group as group 1.
    # Do NOT apply it here: all algorithms search the same labeled feasible set.
    return c,A,b,ub,dict(binary=nx,continuous=nf*m,rows=nr,nonzeros=int(A.nnz),distance_pairs=ne)

def objective(p,labels,m):
    cnt=np.zeros((m,len(p['F'])),int)
    for i,g in enumerate(labels):cnt[g]+=p['soft'][:,i]
    return int(np.maximum(cnt-1,0).sum()),cnt

def construct(d,p,rng,deadline,lp=None):
    n,m=d['n'],d['m'];labels=np.full(n,-1,int);groups=[set() for _ in range(m)];sz=np.zeros(m,int);cnt=np.zeros((m,len(p['F'])),int)
    # MRV construction: fractional scores guide allowed placements, never replace hard checks.
    remaining=set(range(n));rank=rng.permutation(n);degree=p['bad'].sum(1)
    while remaining:
        if time.perf_counter()>=deadline:return None
        chosen=None;allowed=None;key=None
        for i in rank:
            if i not in remaining:continue
            cand=[g for g in range(m) if sz[g]<=d['K']-1 and not any(p['bad'][i,j] for j in groups[g])]
            if not cand:return None
            conf=0 if lp is None else float(np.max(lp[i]))
            ik=(len(cand),-int(degree[i]),-conf)
            if key is None or ik<key:chosen=int(i);allowed=cand;key=ik
        i=chosen
        scores={g:((0. if lp is None else -round(float(lp[i,g]),8)),int(np.sum((cnt[g]>=1)&(p['soft'][:,i]==1))),int(sz[g])) for g in allowed}
        val=min(scores.values());ties=[g for g in allowed if scores[g]==val];g=int(rng.choice(ties))
        labels[i]=g;groups[g].add(i);sz[g]+=1;cnt[g]+=p['soft'][:,i];remaining.remove(i)
    return labels.tolist()

def improve(d,p,labels,deadline):
    labels=labels.copy();n,m=d['n'],d['m'];q,cnt=objective(p,labels,m);groups=[set(np.flatnonzero(np.array(labels)==g)) for g in range(m)];moves=0
    while time.perf_counter()<deadline:
        changed=False
        for i in range(n):
            g=labels[i]
            for h in range(m):
                if time.perf_counter()>=deadline:return labels,q,moves
                if h==g or len(groups[h])>=d['K'] or any(p['bad'][i,j] for j in groups[h]):continue
                delta=int(np.sum(((cnt[h]>=1).astype(int)-(cnt[g]>=2).astype(int))*p['soft'][:,i]))
                if delta<=-1:
                    groups[g].remove(i);groups[h].add(i);labels[i]=h;cnt[g]-=p['soft'][:,i];cnt[h]+=p['soft'][:,i];q+=delta;moves+=1;changed=True;break
            if changed:break
        if changed:continue
        for i in range(n):
            g=labels[i]
            for j in range(i+1,n):
                if time.perf_counter()>=deadline:return labels,q,moves
                h=labels[j]
                if g==h or any(p['bad'][i,k] for k in groups[h] if k!=j) or any(p['bad'][j,k] for k in groups[g] if k!=i):continue
                diff=p['soft'][:,i]-p['soft'][:,j]
                delta=int((np.maximum(cnt[g]-diff-1,0)+np.maximum(cnt[h]+diff-1,0)-np.maximum(cnt[g]-1,0)-np.maximum(cnt[h]-1,0)).sum())
                if delta<=-1:
                    groups[g].remove(i);groups[g].add(j);groups[h].remove(j);groups[h].add(i);labels[i],labels[j]=h,g;cnt[g]-=diff;cnt[h]+=diff;q+=delta;moves+=1;changed=True;break
            if changed:break
        if not changed:break
    assert objective(p,labels,m)[0]==q
    return labels,q,moves

def spatial_construct(d,p,rng,deadline,deterministic=False):
    """Nearest compatible points around an anchor; no hidden group labels.
    Target size balances remaining resources across remaining managers.
    """
    remaining=set(range(d['n']));labels=[-1]*d['n'];groups=[]
    for g in range(d['m']):
        if not remaining:break
        if time.perf_counter()>=deadline:return None
        anchor=min(remaining) if deterministic else int(rng.choice(sorted(remaining)))
        target=min(d['K'],math.ceil(len(remaining)/(d['m']-g)))
        members=[anchor];remaining.remove(anchor)
        nearby=sorted(remaining,key=lambda j:(p['dist'][anchor,j],j))
        for j in nearby:
            if len(members)>=target:break
            if all(not p['bad'][j,k] for k in members):members.append(j);remaining.remove(j)
        for i in members:labels[i]=g
        groups.append(members)
        if len(remaining)>(d['m']-g-1)*d['K']:return None
    return labels if not remaining else None

def worker(d,method,budget,seed,checkpoint,parent_deadline):
    start=time.perf_counter();reserve=min(30.,max(1.,budget*.05))
    deadline=parent_deadline-reserve
    p=prepare(d);rng=np.random.default_rng(seed)
    out=dict(version='2026-10-31-r1',method=method,feasible=False,L=None,H=None,labels=None,
             budget=budget,seed=seed,lower_bound=p['lower'],count_bound=p['lower'],status='started',
             trace=[],reserve_seconds=reserve,normal_return=False)
    best=None;bestq=math.inf
    def save():out['worker_seconds']=time.perf_counter()-start;dump(checkpoint,out)
    def accept(labels,phase):
        nonlocal best,bestq,out
        if labels is None:return
        v=violations(d,labels)
        if v['H']!=0:return
        q,_=objective(p,labels,d['m'])
        if q<bestq:
            best=labels.copy();bestq=q
            out=finish(d,best,out)
            out['trace'].append(dict(seconds=time.perf_counter()-start,L=q,phase=phase))
            save()
    def incumbent(x,solver_obj):
        if not np.isfinite(x).all():return
        xx=np.rint(x)
        if np.max(abs(xx-x))>1e-6 or not np.all(xx.sum(1)==1) or xx.min()<0 or xx.max()>1:return
        accept(np.argmax(xx,axis=1).tolist(),'MIP_incumbent_callback')
    def bound(v):
        if math.isfinite(v) and abs(v)<1e25:
            out['solver_lower_bound']=v
            # Count is exact; solver bounds are explicitly numerical.
            out['lower_bound']=max(p['lower'],v)
            save()
    save();lp=None
    if method in ('MIP','LPR'):
        arrays=model(d,p);out['model_size']=arrays[-1];out['build_seconds']=time.perf_counter()-start;save()
        info,xx=solve_highs(d,arrays,method=='MIP',deadline,incumbent if method=='MIP' else None,bound if method=='MIP' else None)
        out.update(info);save()
        if method=='MIP':
            if xx is not None:incumbent(xx,out.get('solver_objective'))
            out['status']='optimal' if info['optimal'] else ('limit_feasible' if out['feasible'] else 'limit_no_candidate')
            if info['solver_status'] in ('kInfeasible','kUnboundedOrInfeasible'):out['status']='solver_infeasible'
            save();return
        if not info['optimal'] or xx is None:
            out['status']='LP_limit_no_optimum';save();return
        lp=xx
        out['lp_objective']=info['solver_objective']
        # The proved closed-form value is used instead of an approximate primal bound.
        out['lower_bound']=p['lower']
        out['lp_rows']=[[[int(g),float(lp[i,g])] for g in np.flatnonzero(abs(lp[i])>=1e-10)] for i in range(d['n'])]
        raw=np.argmax(lp,axis=1).tolist();out['raw_rounding_labels']=raw;out['raw_rounding_H']=violations(d,raw)['H'];save()
        rt=time.perf_counter()
        if out['raw_rounding_H']==0:repaired=raw;ri={'feasible':True,'steps':0,'reason':'raw_feasible'}
        else:repaired,ri=repair(d,p,lp,rng,deadline)
        out['repair_seconds']=time.perf_counter()-rt;out['repair_info']=ri
        out['repair_labels']=repaired;out['repair_H']=violations(d,repaired)['H'] if repaired is not None else None;save()
        if repaired is not None and violations(d,repaired)['H']==0:
            accept(repaired,'LP_repair')
            out['before_local_L']=bestq;out['before_local_labels']=repaired;save()
            lt=time.perf_counter();improved,q,moves=improve(d,p,repaired,deadline)
            out.update(local_seconds=time.perf_counter()-lt,local_moves=moves)
            accept(improved,'LP_repair_local_search');out['status']='repaired_and_improved';save();return
    attempts=0;stall=0;max_attempts=64 if method=='LPR' else 128
    while time.perf_counter()<deadline and attempts<max_attempts and stall<12:
        attempts+=1
        labels=spatial_construct(d,p,rng,deadline,attempts==1) if method=='SLS' else construct(d,p,rng,deadline,lp)
        if labels is None:continue
        q,_=objective(p,labels,d['m'])
        if 'first_constructed_labels' not in out:out.update(first_constructed_labels=labels.copy(),first_constructed_L=q)
        old_best=bestq
        accept(labels,'construction')  # Save BEFORE the local search starts.
        if method in ('LS','SLS','LPR'):
            labels,q,moves=improve(d,p,labels,deadline)
            out['local_moves']=out.get('local_moves',0)+moves
            accept(labels,'local_search')
        stall=0 if bestq<old_best else stall+1
        if bestq<=p['lower']:break
    out['attempts']=attempts;out['normal_return']=True
    out['status']='work_limit' if time.perf_counter()<deadline else 'search_time_limit'
    if best is None and method=='LPR' and out.get('repair_labels') is not None:
        out=finish(d,out['repair_labels'],out)
    save()

def execute(d,method,budget,seed,work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    inp=work/'input.json';checkpoint=work/f'{method}.json';dump(inp,d)
    if checkpoint.exists():checkpoint.unlink()  # Explicit execution is a new run.
    start=time.perf_counter();parent_deadline=start+budget
    cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--input',str(inp),'--output',str(checkpoint),
         '--method',method,'--budget',str(budget),'--seed',str(seed),'--deadline',str(parent_deadline)]
    forced=False
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=budget)
        error=(proc.stderr or '')[-2500:] if proc.returncode else None
    except subprocess.TimeoutExpired:forced=True;error='outer watchdog stopped process; use preserved checkpoint only'
    result=json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(method=method,feasible=False,L=None,H=None,labels=None,status='no_checkpoint')
    if result.get('labels') is not None:result=finish(d,result['labels'],result)
    result.update(total_seconds=time.perf_counter()-start,watchdog_timeout=forced,process_error=error,end_to_end_limit=budget)
    if forced:result['status']='forced_stop_checkpoint' if result.get('feasible') else 'forced_stop_unknown'
    elif error:result['status']='process_error'
    dump(checkpoint,result);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['worker']);ap.add_argument('--input');ap.add_argument('--output');ap.add_argument('--method');ap.add_argument('--budget',type=float);ap.add_argument('--seed',type=int);ap.add_argument('--deadline',type=float)
    a=ap.parse_args();worker(json.loads(Path(a.input).read_text()),a.method,a.budget,a.seed,a.output,a.deadline)
if __name__=='__main__':main()

