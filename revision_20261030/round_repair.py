"""Capacity rebalance then randomized conflict-reducing moves/swaps.
Uses only the LP solution and public instance, never a planted grouping.
Hard-conflict pair count is a repair merit function, not the omission objective.
"""
import time, math
import numpy as np

def repair(d,p,lp,rng,deadline,max_steps=12000):
    n,m=d['n'],d['m'];bad=p['bad'];labels=np.argmax(lp,axis=1).astype(int)
    groups=[set(np.flatnonzero(labels==g)) for g in range(m)]
    # Move excess resources out of overfull groups. Every resource remains assigned.
    for g in range(m):
        while len(groups[g])>=d['K']+1:
            options=[]
            for i in groups[g]:
                for h in range(m):
                    if len(groups[h])<=d['K']-1:
                        options.append((sum(bad[i,j] for j in groups[h]),-float(lp[i,h]-lp[i,g]),int(i),h))
            if not options:return None,{'reason':'capacity_rebalance_failed'}
            _,_,i,h=min(options);groups[g].remove(i);groups[h].add(i);labels[i]=h
    def count():return sum(int(bad[i,j]) for group in groups for i in group for j in group if i+1<=j)
    H=count();bestH=H;stall=0;accepted=0
    for step in range(max_steps):
        if H==0:return labels.tolist(),dict(steps=step,accepted=accepted,final_conflict_pairs=0)
        if time.perf_counter()>=deadline:break
        offenders=[i for i in range(n) if any(bad[i,j] for j in groups[labels[i]] if j!=i)]
        i=int(rng.choice(offenders));g=int(labels[i]);old=sum(bad[i,j] for j in groups[g] if j!=i);choices=[]
        for h in range(m):
            if h==g:continue
            if len(groups[h])<=d['K']-1:
                delta=int(sum(bad[i,k] for k in groups[h])-old)
                choices.append((delta,-float(lp[i,h]),h,-1))
            for j in groups[h]:
                dh=sum(bad[j,k] for k in groups[h] if k!=j)
                delta=int(sum(bad[i,k] for k in groups[h] if k!=j)+sum(bad[j,k] for k in groups[g] if k!=i)-old-dh)
                choices.append((delta,-float(lp[i,h]+lp[j,g]),h,int(j)))
        if not choices:break
        if rng.random()<=.08:delta,_,h,j=choices[int(rng.integers(len(choices)))]
        else:
            val=min(c[0] for c in choices);opts=[c for c in choices if c[0]==val]
            # LP alignment guides choices but retains randomness to escape ties.
            if rng.random()<=.8:
                bv=min(c[1] for c in opts);opts=[c for c in opts if abs(c[1]-bv)<=1e-10]
            delta,_,h,j=opts[int(rng.integers(len(opts)))]
        temp=max(.15,2*(.9995**step))
        if delta<=0 or rng.random()<=math.exp(-delta/temp):
            groups[g].remove(i);groups[h].add(i);labels[i]=h
            if j!=-1:groups[h].remove(j);groups[g].add(j);labels[j]=g
            H+=delta;accepted+=1
        if H<=bestH-1:bestH=H;stall=0
        else:stall+=1
        if stall>=1500:break
    assert H==count()
    if H==0:return labels.tolist(),dict(steps=step+1,accepted=accepted,final_conflict_pairs=0)
    return None,dict(steps=step+1,accepted=accepted,final_conflict_pairs=H,best_conflict_pairs=bestH)
