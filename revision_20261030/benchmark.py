"""Four-method benchmark. Inputs and witnesses are stored separately.
The 600 s watchdog includes Python startup, construction, solve and audit.
No full-P1 optimization is used. Checkpoint results survive a watchdog stop.
"""
from pathlib import Path
import argparse, json, math, os, platform, subprocess, sys, time, warnings
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
import scipy
from scipy.optimize import milp, linprog, Bounds, LinearConstraint
from scipy.sparse import coo_matrix, csr_matrix, vstack
from scipy.spatial.distance import cdist
from grouping_core import restore
from round_repair import repair
ROOT=Path(__file__).resolve().parent
METHODS=['G','LS','MIP','LPR']

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
    else:
        side=math.ceil(math.sqrt(m));s=1/side
        centers=np.array([[(g%side+.5)*s,(g//side+.5)*s] for g in range(m)])
        pts=np.vstack([centers[g]+rng.uniform(-.18*s,.18*s,(size,2)) for g,size in enumerate(sizes)])
        groups=[];start=0
        for size in sizes:groups.append(list(range(start,start+size)));start+=size
        r=1.35*s
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

def worker(d,method,budget,seed,checkpoint):
    start=time.perf_counter();deadline=start+budget-.25;p=prepare(d);rng=np.random.default_rng(seed)
    out=dict(method=method,feasible=False,L=None,H=None,labels=None,budget=budget,lower_bound=p['lower'],status='started',seed=seed,trace=[])
    def save():out['worker_seconds']=time.perf_counter()-start;dump(checkpoint,out)
    save();lp=None;best=None;bestq=math.inf
    if method in ('MIP','LPR'):
        c,A,b,ub,meta=model(d,p);out['model_size']=meta;out['build_seconds']=time.perf_counter()-start;save();t0=time.perf_counter()
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            if method=='MIP':
                res=milp(c,integrality=np.r_[np.ones(d['n']*d['m']),np.zeros(len(c)-d['n']*d['m'])],bounds=Bounds(np.zeros(len(c)),ub),constraints=LinearConstraint(A,np.r_[np.ones(d['n']),np.full(A.shape[0]-d['n'],-np.inf)],b),options={'time_limit':max(.01,deadline-time.perf_counter()),'mip_rel_gap':0.,'threads':1,'presolve':True})
            else:
                res=linprog(c,A_ub=A[d['n']:],b_ub=b[d['n']:],A_eq=A[:d['n']],b_eq=b[:d['n']],bounds=np.column_stack((np.zeros(len(c)),ub)),method='highs-ds',options={'time_limit':max(.01,deadline-time.perf_counter()),'threads':1,'presolve':True})
        out.update(node_count=int(getattr(res,'mip_node_count',0) or 0),solver_seconds=time.perf_counter()-t0,solver_status=int(res.status),solver_message=str(res.message),warnings=[str(w.message) for w in ws]);save()
        if method=='MIP':
            bd=getattr(res,'mip_dual_bound',None)
            if bd is not None and math.isfinite(float(bd)):out['lower_bound']=max(p['lower'],float(bd))
            if res.x is not None:
                x=res.x[:d['n']*d['m']].reshape(d['n'],d['m'])
                if np.max(abs(x-np.rint(x)))<=1e-6 and np.all(np.rint(x).sum(1)==1):best=np.argmax(x,axis=1).tolist()
            out['status']='optimal' if res.status==0 else 'time_or_other_stop';out=finish(d,best,out);save();return
        if res.status!=0 or res.x is None:out['status']='LP_not_solved';save();return
        lp=res.x[:d['n']*d['m']].reshape(d['n'],d['m']);out['lp_objective']=float(res.fun);out['lower_bound']=max(p['lower'],float(res.fun))
        out['lp_rows']=[[[int(g),float(lp[i,g])] for g in np.flatnonzero(abs(lp[i])>=1e-10)] for i in range(d['n'])]
        raw=np.argmax(lp,axis=1).tolist();out['raw_rounding_labels']=raw;out['raw_rounding_H']=violations(d,raw)['H'];out['raw_rounding_feasible']=out['raw_rounding_H']==0
        if out['raw_rounding_feasible']:
            out=finish(d,raw,out);out['status']='raw_rounding_feasible';save();return
        save()
        rt=time.perf_counter();repaired,repair_info=repair(d,p,lp,rng,deadline);out['repair_info']=repair_info;out['repair_seconds']=time.perf_counter()-rt
        if repaired is not None:
            out=finish(d,repaired,out);out['status']='repaired';save();return
    attempts=0;stall=0
    max_attempts={'G':128,'LS':32,'LPR':64}[method]
    while time.perf_counter()<deadline and attempts<max_attempts and stall<12:
        attempts+=1;labels=construct(d,p,rng,deadline,lp)
        if labels is None:continue
        q,_=objective(p,labels,d['m'])
        if method=='LS':labels,q,moves=improve(d,p,labels,deadline);out['local_moves']=out.get('local_moves',0)+moves
        if q<=bestq-1:
            bestq=q;best=labels.copy();stall=0;out=finish(d,best,out);out['trace'].append(dict(seconds=time.perf_counter()-start,L=q));save()
        else:stall+=1
        if q<=p['lower']:break
    out['attempts']=attempts;out['status']='completed' if time.perf_counter()<deadline else 'deadline'
    if best is None and method=='LPR':best=out.get('raw_rounding_labels')
    out=finish(d,best,out);save()

def execute(d,method,budget,seed,work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);inp=work/'input.json';checkpoint=work/f'{method}.json';dump(inp,d)
    start=time.perf_counter();cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--input',str(inp),'--output',str(checkpoint),'--method',method,'--budget',str(max(.01,budget-.5)),'--seed',str(seed)]
    timedout=False
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=budget)
        error=(proc.stderr or '')[-1500:] if proc.returncode else None
    except subprocess.TimeoutExpired:
        timedout=True;error='watchdog stopped process'
    result=json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(method=method,feasible=False,L=None,H=None,labels=None,status='no_checkpoint')
    if result.get('labels') is not None:result=finish(d,result['labels'],result)
    result.update(total_seconds=time.perf_counter()-start,watchdog_timeout=timedout,process_error=error,end_to_end_limit=budget)
    if timedout:result['status']='watchdog_timeout'
    dump(checkpoint,result);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['worker','pilot']);ap.add_argument('--input');ap.add_argument('--output');ap.add_argument('--method',default='LPR');ap.add_argument('--budget',type=float,default=600);ap.add_argument('--seed',type=int,default=3001);ap.add_argument('--n',type=int,default=40);ap.add_argument('--family',default='C');args=ap.parse_args()
    if args.command=='worker':worker(json.loads(Path(args.input).read_text()),args.method,args.budget,args.seed,args.output)
    else:
        d,w=generate(args.family,args.n,args.n//4,32,args.seed);work=ROOT/'pilot'/f'{args.family}{args.n}_{args.seed}';dump(work/'witness.json',w)
        for k,method in enumerate(METHODS):
            r=execute(d,method,args.budget,args.seed+k,work);print(method,r.get('status'),r.get('feasible'),r.get('L'),r.get('H'),round(r['total_seconds'],3),flush=True)
if __name__=='__main__':main()
