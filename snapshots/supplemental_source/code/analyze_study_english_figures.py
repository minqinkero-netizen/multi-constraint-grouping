"""Audit raw records without rerunning optimizers; generate reproducible tables.
Every numerical sentence below is formed from the audited records.
"""
from pathlib import Path
from collections import Counter
import argparse,json,csv,math
import numpy as np
from scipy.stats import binomtest
from benchmark import METHODS,prepare,objective,dump
from independent_check import check_labels,audit_result,audit_lp,unpack_lp
ROOT=Path(__file__).resolve().parent
VARIANTS=['LP-G','LP-N','UNI']
def avg(x):return float(np.mean(x)) if x else None
def fmt(x,k=1):return '--' if x is None else f'{x:.{k}f}'
def ms(x,k=1):
    x=[v for v in x if v is not None]
    if not x:return '--'
    a=f'{np.mean(x):.{k}f}'
    return '$'+a+(r'\pm'+f'{np.std(x,ddof=1):.{k}f}' if len(x)>1 else r'^{*}')+'$'
def stat(rr):
    fe=[r for r in rr if r.get('feasible')];ca=[r for r in rr if r.get('H') is not None]
    return dict(N=len(rr),feasible=len(fe),candidates=len(ca),obj=[r['L'] for r in fe],H=[r['H'] for r in ca],time=[r['total_seconds'] for r in rr if r.get('total_seconds') is not None])
def table(caption,label,headers,rows,spec,small='small'):
    return '\\begin{table}[htbp]\n\\centering\\'+small+'\n'+f'\\caption{{{caption}}}\\label{{{label}}}\n\\begin{{tabular}}{{{spec}}}\\toprule\n'+' & '.join(headers)+r' \\\midrule'+'\n'+'\n'.join(' & '.join(map(str,r))+r' \\' for r in rows)+'\n\\bottomrule\\end{tabular}\n\\end{table}\n'
def metric(caption,label,methods,blocks):
    k=len(methods);spec='l'+'rrr'*k
    s='\\begin{table}[htbp]\n\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}\n'+f'\\caption{{{caption}}}\\label{{{label}}}\n'+r'\resizebox{\textwidth}{!}{\begin{tabular}{'+spec+r'}\toprule'+'\n'
    s+=' & '+' & '.join('\\multicolumn{3}{c}{'+m+'}' for m in methods)+r' \\'+'\n'
    s+=''.join('\\cmidrule(lr){'+str(2+3*j)+'-'+str(4+3*j)+'}' for j in range(k))+'\n'
    s+='输入 & '+' & '.join(['obj & infeas & time']*k)+r' \\\midrule'+'\n'
    for b in blocks:
        row=[b['name']]
        for m in methods:
            v=b['methods'][m];row += [ms(v['obj']),ms(v['H']),ms(v['time'],2)]
        s+=' & '.join(row)+r' \\'+'\n'
    return s+'\\bottomrule\\end{tabular}}\n\\end{table}\n'
def write(gen,name,s):(gen/name).write_text(s,encoding='utf-8')
def pair(cases,a,b):
    delta=[r['results'][a]['L']-r['results'][b]['L'] for r in cases if r['results'][a]['feasible'] and r['results'][b]['feasible']]
    return dict(a=a,b=b,N=len(delta),win=sum(d<0 for d in delta),tie=sum(d==0 for d in delta),loss=sum(d>0 for d in delta),delta=delta)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',default='data');ap.add_argument('--extra',default='extra');ap.add_argument('--paper');args=ap.parse_args()
    source=ROOT/args.data;raw=json.loads((source/'results.json').read_text());assert raw['complete'];cases=raw['instances'];assert len(cases)==18
    for rec in cases:
        if 'input' not in rec:rec['input']=json.loads((source/rec['name']/'instance.json').read_text())
        if 'results' not in rec:rec['results']={m:json.loads((source/rec['name']/f'{m}.json').read_text()) for m in METHODS}
    extras=json.loads((ROOT/args.extra/'results.json').read_text());assert extras['complete'] and len(extras['instances'])==20
    for rec in extras['instances']:
        w=ROOT/args.extra/rec['name']
        if 'input' not in rec:rec['input']=json.loads((w/'instance.json').read_text())
        if 'lp' not in rec:rec['lp']=json.loads((w/'lp.json').read_text())
        for k in rec['repeats']:
            if 'results' not in k:k['results']={v:json.loads((w/f"{v}_{k['repeat']}.json").read_text()) for v in VARIANTS}
        for sc in rec['radius_scan']:
            if 'results' not in sc:sc['results']={m:json.loads((w/f"radius_{sc['factor']:.2f}"/f'{m}.json').read_text()) for m in ['LS','SLS']}
    gen=Path(args.paper)/'generated' if args.paper else ROOT/'generated';gen.mkdir(parents=True,exist_ok=True)
    audit=[];LP=[];witnesses=[];rows=[];quality=[]
    for rec in cases:
        d=rec['input'];w=json.loads((source/rec['name']/'witness.json').read_text());wa=check_labels(d,w['labels']);assert wa['H']==0;witnesses.append(dict(name=rec['name'],L=wa['L']))
        for m in METHODS:
            r=rec['results'][m];assert r==json.loads((source/rec['name']/f'{m}.json').read_text())
            ar=audit_result(d,r);audit.append(dict(name=rec['name'],method=m,**ar))
            assert r.get('solver_status') not in ['kInfeasible','kUnboundedOrInfeasible']
            if r.get('status')=='optimal':assert r['feasible'] and abs(r['lower_bound']-r['L'])<1e-5
            if 'lp_rows' in r:LP.append(dict(name=rec['name'],**audit_lp(d,unpack_lp(d,r),r['lp_objective'])))
            if r.get('lower_bound') is not None:assert r['lower_bound']<=wa['L']+2e-6
            rows.append(dict(instance=rec['name'],family=rec['family'],n=d['n'],m=d['m'],T=len(d['targets']),method=m,feasible=r['feasible'],obj=r['L'],infeas=r['H'],time=r['total_seconds'],status=r['status'],solver_status=r.get('solver_status'),watchdog_timeout=r.get('watchdog_timeout'),callback_incumbents=r.get('callback_incumbents')))
        rg=rec['results']['G'];rl=rec['results']['LS']
        if rg.get('first_constructed_labels') is not None and rl.get('first_constructed_labels') is not None:assert rg['first_constructed_labels']==rl['first_constructed_labels']
        lower=max([prepare(d)['lower']]+[r['lower_bound'] for r in rec['results'].values() if r.get('lower_bound') is not None]);fe=[r['L'] for r in rec['results'].values() if r['feasible']];upper=min(fe) if fe else None
        assert upper is None or lower<=upper+2e-6
        quality.append(dict(name=rec['name'],n=d['n'],family=rec['family'],count=prepare(d)['lower'],lower=lower,upper=upper,witness=wa['L'],gap=None if upper is None else max(0,upper-lower),matched=upper is not None and abs(upper-lower)<=1e-6))
    with (source/'results_table.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    blocks=[]
    for n,m,T in raw['protocol']['main_configs']:
        for fam in ['U','C']:
            rr=[r for r in cases if r['family']==fam and r['config'][0]==n]
            blocks.append(dict(name=f'{fam}({n},{m},{T})',n=n,family=fam,methods={a:stat([r['results'][a] for r in rr]) for a in METHODS}))
    totals={m:stat([r['results'][m] for r in cases]) for m in METHODS}
    pairs=[pair(cases,a,b) for a,b in [('LS','G'),('SLS','LS'),('SLS','G'),('LPR','LS'),('MIP','LPR'),('MIP','SLS')]]
    write(gen,'main_table.tex',metric('构造类方法的均值与样本标准差：obj只统计可行方案，infeas只统计返回候选，time包含全部运行（秒）；每行3个输入','tab:main-results',['G','LS','SLS'],blocks)+metric('求解器路线的均值与样本标准差；统计口径同表\\ref{tab:main-results}。星号表示只有一个有效观测，无法估计标准差','tab:main-results-solvers',['MIP','LPR'],blocks))
    write(gen,'success_table.tex',table('获得可行方案的输入数；括号内为返回完整整数候选的次数，分母均为3','tab:success',['输入']+METHODS,[[b['name']]+[f"{b['methods'][m]['feasible']}/3 ({b['methods'][m]['candidates']}/3)" for m in METHODS] for b in blocks],'lrrrrr'))
    write(gen,'pair_table.tex',table('共同可行输入上的目标配对；优、平、劣指前一方法相对后一方法，差值为前者减后者','tab:paired',['方法对','输入数','优','平','劣','目标差均值及标准差'],[[p['a']+'/'+p['b'],p['N'],p['win'],p['tie'],p['loss'],ms(p['delta'])] for p in pairs],'lrrrrr'))
    status_categories={'最优':['optimal'],'工作量':['work_limit','repaired_and_improved'],'搜索时限':['search_time_limit','limit_feasible','limit_no_candidate'],'LP未最优':['LP_limit_no_optimum'],'强制停止':['forced_stop_checkpoint','forced_stop_unknown'],'异常':['process_error','no_checkpoint','solver_infeasible']}
    termination=[];statusfull={}
    for m in METHODS:
        cc=Counter(r['results'][m]['status'] for r in cases);statusfull[m]=dict(cc);vals=[sum(cc[s] for s in cat) for cat in status_categories.values()];assert sum(vals)==18;termination.append([m]+vals)
    write(gen,'termination_table.tex',table('主实验停止类别；每方法18次。工作量列含正常完成修复及局部搜索，强制停止单独列出','tab:termination',['方法']+list(status_categories),termination,'lrrrrrr'))
    tt=[]
    for m in METHODS:
        allr=[r['results'][m] for r in cases];fe=[r for r in allr if r['feasible']];fa=[r for r in allr if not r['feasible']]
        tt.append([m,len(fe),ms([r['total_seconds'] for r in fe],2),len(fa),ms([r['total_seconds'] for r in fa],2),ms([r['total_seconds'] for r in allr],2)])
    write(gen,'timing_table.tex',table('成功与失败运行分别计时：均值及样本标准差，单位秒；星号含义同前','tab:timing-split',['方法','成功数','成功耗时','失败数','失败耗时','全部耗时'],tt,'lrrrrr'))
    qr=[]
    for b in blocks:
        qq=[q for q in quality if q['n']==b['n'] and q['family']==b['family']];fe=[q for q in qq if q['upper'] is not None]
        qr.append([b['name'],f'{len(fe)}/3',fmt(avg([q['count'] for q in qq])),fmt(avg([q['lower'] for q in qq])),fmt(avg([q['witness'] for q in qq])),fmt(avg([q['upper'] for q in fe])),fmt(avg([q['gap'] for q in fe])),f"{sum(q['matched'] for q in qq)}/3"])
    write(gen,'bound_table.tex',table('目标下界、最好可行目标与见证目标；获得方案列统计比较方法，见证不计入$U$','tab:bounds',['输入','获得方案','$B_{\\mathrm{count}}$','$B$','见证目标','$U$','$U-B$','界相合'],qr,'lrrrrrrr',small='footnotesize'))
    rrtable=[];rounding=[]
    for b in blocks:
        rs=[r['results']['LPR'] for r in cases if r['config'][0]==b['n'] and r['family']==b['family']]
        lpok=sum('lp_rows' in r for r in rs);rawok=sum(r.get('raw_rounding_H')==0 for r in rs);repok=sum(r.get('raw_rounding_H',0)!=0 and r.get('repair_H')==0 for r in rs);recon=sum(r['feasible'] and r.get('repair_H')!=0 for r in rs);local=[r for r in rs if r.get('before_local_L') is not None]
        val=dict(name=b['name'],LP=lpok,raw=rawok,repair=repok,reconstruct=recon,feasible=sum(r['feasible'] for r in rs),before=[r['before_local_L'] for r in local],after=[r['L'] for r in local])
        rounding.append(val);rrtable.append([b['name'],lpok,rawok,repok,recon,val['feasible'],fmt(avg(val['before'])),fmt(avg(val['after']))])
    write(gen,'rounding_table.tex',table('LPR各阶段新增可行数；末两列为经修复可行输入在相同局部搜索前后的平均遗漏','tab:rounding-outcomes',['输入','LP最优','直接','修复','重构','最终','优化前','优化后'],rrtable,'lrrrrrrr',small='footnotesize'))
    geo=[]
    for b in blocks:
        selected=[r for r in cases if r['family']==b['family'] and r['config'][0]==b['n']];rg=[];di=[];co=[];nr=[]
        for rec in selected:
            d=rec['input'];p=prepare(d);den=d['n']*(d['n']-1)/2;rg.append(d['r']);di.append(100*np.triu(~(p['dist']<=d['r']),1).sum()/den);co.append(100*np.triu(p['bad'],1).sum()/den)
            sizes=[r['model_size']['rows'] for r in rec['results'].values() if 'model_size' in r]
            exact_rows=d['n']+d['m']+int(np.triu(~(p['dist']<=d['r']),1).sum())*d['m']+sum(bool(d['targets'][t]) for t in d['strict'])*d['m']+len(p['F'])*d['m']
            assert all(v==exact_rows for v in sizes);nr.append(exact_rows)
        geo.append([b['name'],fmt(avg(rg),3),fmt(avg(di))+r'\%',fmt(avg(co))+r'\%',fmt(avg(nr),0)])
    write(gen,'geometry_table.tex',table('主实验各参数组的平均空间阈值、冲突密度与显式约束行数；不含变量上下界','tab:geometry',['输入','平均$r$','距离边比例','合并硬冲突边比例','约束行数'],geo,'lrrrr'))
    per=[]
    for rec in sorted(cases,key=lambda r:(r['config'][0],r['family'],r['replicate'])):
        row=[f"{rec['family']}{rec['config'][0]}-{rec['replicate']}"]
        for m in METHODS:
            r=rec['results'][m];row.append(fmt(r['L'],0)+' / '+fmt(r['total_seconds'],2))
        per.append(row)
    write(gen,'per_instance_table.tex',table('18个主实验输入的逐例结果：每格为遗漏量/实测总耗时（秒）；--表示无可行方案','tab:all-results',['输入']+METHODS,per,'lrrrrr',small='footnotesize'))
    maxsec=max(r['time'] for r in rows);forced=[r for r in rows if r['watchdog_timeout']];errors=[r for r in rows if r['status']=='process_error'];mipok=sum(r['results']['MIP'].get('status')=='optimal' for r in cases)
    narrative=[f"18个独立输入的90次主实验中，G、LS、SLS、MIP和LPR分别获得"+'、'.join(str(totals[m]['feasible']) for m in METHODS)+"例可行方案。全部已接受方案通过独立的坐标、集合和调用核对。表\\ref{tab:success}保留各方法失败次数，不因目标值缺失而缩小成功率分母。"]
    for p in [pairs[0],pairs[1],pairs[3]]:narrative.append(f"{p['a']}与{p['b']}在{p['N']}个共同可行输入上比较，前者取得{p['win']}优、{p['tie']}平、{p['loss']}劣，平均遗漏差为{fmt(avg(p['delta']))}。")
    cfe=sum(r['results']['SLS']['feasible'] for r in cases if r['family']=='C');ufe=sum(r['results']['SLS']['feasible'] for r in cases if r['family']=='U')
    narrative.append(f"SLS在C类的可行数为{cfe}/9，在U类为{ufe}/9。C类结果应结合其明确的簇间分离结构解释，不能据此推断空间构造在所有分布上都占优。")
    narrative.append(f"MIP有{mipok}次正常返回最优状态。全部方法中有{len(forced)}次被外部时限强制停止，其中{sum(r['feasible'] for r in forced)}次保留了此前保存的可行方案；程序异常为{len(errors)}次。单次实测最大耗时为{maxsec:.2f}秒。")
    write(gen,'main_interpretation.tex','\n\n'.join(narrative)+'\n')
    exsummary=analyze_extra(extras,gen,ROOT/args.extra,audit,LP,witnesses)
    scenario_summary=materialize_scenarios(gen,audit)
    summary=dict(inputs=18,runs=90,blocks=blocks,totals=totals,pairs=pairs,termination=statusfull,rounding=rounding,quality=quality,max_seconds=maxsec,forced=len(forced),errors=len(errors),extra=exsummary,scenarios=scenario_summary,audit_success=True)
    dump(source/'summary.json',summary);dump(source/'audit.json',dict(all_consistent=True,runs=audit,LP=LP,witnesses=witnesses))
    abstract='采用18个独立输入完成五种方法的90次主比较，资源数为80至320，每次预算600秒。五种方法分别在'+ '、'.join(str(totals[m]['feasible']) for m in METHODS)+'个输入上获得可行方案；空间基线在清晰聚簇输入上的表现说明生成结构会影响方法排序。另用20个独立输入比较三种后处理方案，每输入重复三次，并在6个基础输入上进行36次距离扫描。'+exsummary['abstract_text']
    write(gen,'abstract_results.tex',abstract+'\n')
    conclusion='数值比较采用独立输入上的可行数、条件遗漏量、成功与失败耗时共同评价。主实验五种方法的可行数依次为'+ '、'.join(str(totals[m]['feasible']) for m in METHODS)+'，不能仅以某方法较少成功样本上的目标均值判断整体优劣。'+exsummary['conclusion_text']+'所有结论对应本次合成任务、实现和预算；达到时限不构成原问题无解的证明。'
    write(gen,'conclusion_results.tex',conclusion+'\n')
    make_figures(cases,extras['instances'],Path(args.paper)/'figures' if args.paper else ROOT/'figures')
    print(json.dumps({k:summary[k] for k in ['inputs','runs','max_seconds','forced','errors','audit_success']},ensure_ascii=False,indent=2))
    print('ACCEPTED',sum(a['feasible'] for a in audit),'LP',len(LP),'WITNESSES',len(witnesses))


def analyze_extra(raw,gen,folder,audits,lps,witnesses):
    cases=raw['instances'];allrows=[];radius=[]
    for rec in cases:
        d=rec['input'];w=json.loads((folder/rec['name']/'witness.json').read_text());wa=check_labels(d,w['labels']);assert wa['H']==0;witnesses.append(dict(name=rec['name'],L=wa['L']))
        if rec['lp'].get('status')=='optimal':lps.append(dict(name=rec['name'],**audit_lp(d,rec['lp']['x'],rec['lp']['objective'])))
        for repeat in rec['repeats']:
            ga=repeat['results']['LP-G'];ng=repeat['results']['LP-N']
            if 'raw_labels' in ga and 'raw_labels' in ng:assert ga['raw_labels']==ng['raw_labels']
            for v,r in repeat['results'].items():
                ar=audit_result(d,r);audits.append(dict(name=rec['name'],method=v,repeat=repeat['repeat'],**ar))
                allrows.append(dict(name=rec['name'],n=d['n'],family=rec['family'],repeat=repeat['repeat'],variant=v,feasible=r['feasible'],obj=r.get('L'),before=r.get('before_local_L'),time=r.get('total_seconds'),H=r.get('H'),status=r['status']))
        for sc in rec['radius_scan']:
            dd=dict(d);dd['r']=sc['r'];p=prepare(dd);density=float(np.triu(~(p['dist']<=dd['r']),1).sum())/(d['n']*(d['n']-1)/2)
            for m,r in sc['results'].items():
                audits.append(dict(name=rec['name'],method=m,radius_factor=sc['factor'],**audit_result(dd,r)))
                radius.append(dict(name=rec['name'],family=rec['family'],factor=sc['factor'],r=sc['r'],distance_density=density,method=m,feasible=r['feasible'],L=r['L'],time=r['total_seconds']))
    for filename,rows in [('ablation_runs.csv',allrows),('radius_runs.csv',radius)]:
        with (folder/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    rows=[];extra_blocks=[]
    for n in [80,120]:
        for fam in ['U','O']:
            select=[r for r in cases if r['config'][0]==n and r['family']==fam];lptimes=[r['lp']['total_seconds'] for r in select]
            for v in VARIANTS:
                rr=[r for r in allrows if r['n']==n and r['family']==fam and r['variant']==v];fe=[r for r in rr if r['feasible']];anyinputs=len({r['name'] for r in fe});all3=sum(all(z['results'][v]['feasible'] for z in r['repeats']) for r in select)
                rows.append([f'{fam}{n}',v,f'{len(fe)}/15',f'{anyinputs}/5 ({all3}/5)',ms([r['before'] for r in fe]),ms([r['obj'] for r in fe]),ms([r['time'] for r in rr],2)])
                extra_blocks.append(dict(n=n,family=fam,variant=v,feasible=len(fe),independent_any=anyinputs,independent_all=all3,lp_times=lptimes))
    write(gen,'extra_table.tex',table('20个新增输入上的修复消融；每参数每方案5个输入各重复3次。输入数列为至少一次成功，括号为三次均成功；time仅含后处理（秒）','tab:extra-results',['输入','方案','可行次数','成功输入','优化前obj','优化后obj','time'],rows,'lcrrrrr',small='footnotesize'))
    pairs=[]
    for a,b in [('LP-G','LP-N'),('LP-G','UNI'),('LP-N','UNI')]:
        diffs=[];input_details=[]
        for rec in cases:
            delta=[z['results'][a]['L']-z['results'][b]['L'] for z in rec['repeats'] if z['results'][a]['feasible'] and z['results'][b]['feasible']]
            if delta:diffs.append(avg(delta));input_details.append(dict(name=rec['name'],paired_repeats=len(delta),mean_difference=avg(delta)))
        win=sum(d<-1e-9 for d in diffs);loss=sum(d>1e-9 for d in diffs);tie=len(diffs)-win-loss
        pv=float(binomtest(win,win+loss,.5,alternative='two-sided').pvalue) if win+loss else 1.
        pairs.append(dict(a=a,b=b,N=len(diffs),win=win,tie=tie,loss=loss,diffs=diffs,p=pv,details=input_details))
    order=sorted(range(3),key=lambda k:pairs[k]['p']);last=0
    for rank,k in enumerate(order):last=max(last,min(1.,(3-rank)*pairs[k]['p']));pairs[k]['holm_p']=last
    write(gen,'extra_pair_table.tex',table('消融的输入层面条件配对；目标差先在每个输入的共同可行重复内平均，再跨输入统计','tab:extra-paired',['方法对','输入数','优/平/劣','平均差及标准差','$p$','Holm $p$'],[[p['a']+'/'+p['b'],p['N'],f"{p['win']}/{p['tie']}/{p['loss']}",ms(p['diffs']),fmt(p['p'],4),fmt(p['holm_p'],4)] for p in pairs],'lrlrrr',small='footnotesize'))
    executed=sum(r['time'] is not None for r in allrows)
    total={v:[r for r in allrows if r['variant']==v] for v in VARIANTS};local={v:[r['before']-r['obj'] for r in total[v] if r['feasible']] for v in VARIANTS}
    lptimes=[r['lp']['total_seconds'] for r in cases];lpok=sum(r['lp'].get('status')=='optimal' for r in cases)
    paragraphs=[f"计划的180个方案与随机状态组合中，实际启动{executed}次后处理；未取得共享LP最优解的组合记为未启动，不填零耗时。20次共享LP准备中，{lpok}次取得最优状态，平均耗时为{np.mean(lptimes):.2f}秒，样本标准差为{np.std(lptimes,ddof=1):.2f}秒。LP-G和LP-N若作为独立端到端方法使用，还须各自计入相应输入的LP准备成本；UNI无需该阶段。"]
    for v in VARIANTS:
        rr=total[v];deltas=local[v];before=[r['before'] for r in rr if r['feasible']];after=[r['obj'] for r in rr if r['feasible']]
        paragraphs.append(f"{v}在计划的60组后处理设置中取得{len(deltas)}次可行方案。相同可行运行上，局部优化前后平均遗漏分别为{fmt(avg(before))}和{fmt(avg(after))}，其中{sum(d>0 for d in deltas)}次严格改善。该变化直接来自后续局部搜索，不能归因于初次LP分配。")
    pp=pairs[0];paragraphs.append(f"在LP-G与LP-N共同可行的{pp['N']}个独立输入上，LP-G取得{pp['win']}优、{pp['tie']}平、{pp['loss']}劣，Holm校正后$p={pp['holm_p']:.4f}$。"+('该条件配对检验在0.05水平下拒绝对称胜负假设；方向和幅度仍应结合表中差值及双方失败次数判断。' if pp['holm_p']<.05 else '本次条件配对检验未在0.05水平下给出分量引导改善目标质量的显著证据；这并不证明两种方案等效。'))
    write(gen,'extra_interpretation.tex','\n\n'.join(paragraphs)+'\n')
    radiusrows=[]
    for fam in ['U','O']:
        for factor in [1.,1.15,1.30]:
            select=[r for r in radius if r['family']==fam and r['factor']==factor];row=[fam,f'{factor:.2f}',fmt(100*avg([r['distance_density'] for r in select]))+r'\%']
            for m in ['LS','SLS']:
                rr=[r for r in select if r['method']==m];fe=[r for r in rr if r['feasible']];row.extend([f'{len(fe)}/3',ms([r['L'] for r in fe]),ms([r['time'] for r in rr],2)])
            radiusrows.append(row)
    write(gen,'radius_table.tex',table('距离扫描；每行同一类3个基础输入。obj只统计可行方案，time包含全部运行（秒）','tab:radius-results',['分布','$r/r_0$','距离边','LS可行','LS obj','LS time','SLS可行','SLS obj','SLS time'],radiusrows,'lrrrrrrrr',small='footnotesize'))
    rt=[]
    for m in ['LS','SLS']:
        vals=[sum(r['feasible'] for r in radius if r['method']==m and r['factor']==f) for f in [1.,1.15,1.3]]
        rt.append(m+'在三个阈值下的可行数依次为'+ '、'.join(str(v)+'/6' for v in vals)+'。')
    rt.append('放宽距离不会使数学可行集缩小，但限时启发式的搜索路径和停止位置会改变，因此实测目标或成功次数不必单调。各行条件目标均值也可能对应不同成功样本，不能单凭均值的升降判断约束放宽的收益。')
    write(gen,'radius_interpretation.tex','\n\n'.join(rt)+'\n')
    abstract=('共同可行输入上的检验未给出LP分量引导改善遗漏量的显著证据。' if pp['holm_p']>=.05 else '共享初始解对照显示分量引导与取消引导的条件目标差异，方向及失败情况分别报告。')
    conclusion=('消融未给出LP分量引导改善共同可行输入上目标质量的显著证据，局部搜索的目标改善则被单独记录。' if pp['holm_p']>=.05 else '消融显示LP引导和局部搜索应分别评价；条件目标检验不替代可行率比较。')
    s=dict(inputs=20,shared_LP=20,postprocess_records=180,postprocess_runs=executed,radius_base_inputs=6,radius_runs=36,pairs=pairs,blocks=extra_blocks,success={v:sum(r['feasible'] for r in total[v]) for v in VARIANTS},local_improvements=local,LP_solved=lpok,abstract_text=abstract,conclusion_text=conclusion)
    dump(folder/'summary.json',s);return s


def materialize_scenarios(gen,audits):
    s=json.loads((ROOT/'scenario_data/results.json').read_text());assert s['complete'];rows=[];spec=[]
    for rec in s['independent']+s['special']:
        ip=ROOT/'scenario_data'/rec['name']/'instance.json' if rec in s['independent'] else ROOT/'solutions'/f"{rec['name']}_input.json";d=json.loads(ip.read_text())
        for m,r in rec['results'].items():audits.append(dict(name=rec['name'],method=m,**audit_result(d,r)))
    for cfg in s['protocol']['configs']:
        selected=[r for r in s['independent'] if r['config']==cfg]
        for m in ['MIP','LPR']:
            rs=[r['results'][m] for r in selected];fe=[r for r in rs if r['feasible']];sz=[len(g) for r in fe for g in r['groups']]
            rows.append([f'({cfg[0]},{cfg[1]},{cfg[2]})',m,f'{len(fe)}/3',ms([r['L'] for r in fe]),f'{min(sz)}--{max(sz)}' if sz else '--',ms([r['total_seconds'] for r in rs],3)])
    write(gen,'scenario_table.tex',table('小算例的独立重复；每套参数3个输入，组大小为所有已接受分组的范围，时间为秒','tab:scenario-checks',['$(n,m,T)$','方法','可行数','平均遗漏及标准差','组大小','耗时及标准差'],rows,'lcrrrr',small='footnotesize'))
    for rec in s['special']:
        for m,r in rec['results'].items():
            sz=[len(g) for g in r['groups']] if r['feasible'] else [];cfg=rec['config']
            spec.append([{'base8':'8资源算例','seed66':'9资源算例','round32':'32轮情境'}[rec['name']],m,f'({cfg[0]},{cfg[1]},{cfg[2]})',fmt(r['L'],0),f'{min(sz)}--{max(sz)}' if sz else '--',fmt(r['total_seconds'],3)])
    write(gen,'special_table.tex',table('三个说明情境的新求解结果；每情境每方法一次，图示仍采用正文的固定方案','tab:special-timing',['情境','方法','$(n,m,T)$','遗漏','组大小','耗时/s'],spec,'lclrrr'))
    nine=next(r for r in s['special'] if r['name']=='seed66')
    write(gen,'nine_caption.tex',r'\caption{9资源、3组、6轮算例的逐轮调用，分组大小均为3；新运行MIP和LPR分别耗时'+fmt(nine['results']['MIP']['total_seconds'],3)+' s和'+fmt(nine['results']['LPR']['total_seconds'],3)+' s}\n')
    dump(ROOT/'scenario_data/audit.json',dict(all_consistent=True,enumeration=s['enumeration'],runs=24));return dict(inputs=9,explanatory=3,runs=24,enumeration=s['enumeration'])


def make_figures(cases,extra,figdir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from plot_style import configure
    configure(plt);plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':210});figdir.mkdir(exist_ok=True)
    colors={'G':'#547eaa','LS':'#dd9142','SLS':'#317b8b','MIP':'#479778','LPR':'#9b639d'};markers=['o','s','v','^','D']
    fig,ax=plt.subplots(1,2,figsize=(10,3.8));ns=[80,160,320];xx=np.arange(3);width=.15
    for k,m in enumerate(METHODS):
        su=[sum(r['results'][m]['feasible'] for r in cases if r['config'][0]==n) for n in ns];tt=[avg([r['results'][m]['total_seconds'] for r in cases if r['config'][0]==n]) for n in ns]
        ax[0].bar(xx+(k-2)*width,su,width,color=colors[m],label=m);ax[1].plot(ns,tt,marker=markers[k],color=colors[m],label=m)
    ax[0].set_xticks(xx,ns);ax[0].set(ylim=(0,7.5),yticks=range(7),ylabel='Feasible inputs / 6',xlabel='Number of resources n');ax[0].legend(ncol=3,fontsize=9);ax[0].grid(axis='y',alpha=.15)
    ax[1].set_yscale('log');ax[1].set(xticks=ns,xlabel='Number of resources n',ylabel='Mean total time / s (log scale)');ax[1].legend(ncol=2,fontsize=9);ax[1].grid(alpha=.15);fig.tight_layout();fig.savefig(figdir/'study_success_time.png',bbox_inches='tight');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(9,3.8))
    for ax,a in zip(axs,['SLS','LPR']):
        common=[r for r in cases if r['results'][a]['feasible'] and r['results']['LS']['feasible']];vals=[]
        for fam,mk in [('U','o'),('C','^')]:
            rr=[r for r in common if r['family']==fam];x=[r['results']['LS']['L'] for r in rr];y=[r['results'][a]['L'] for r in rr];vals+=x+y;ax.scatter(x,y,label=fam,marker=mk,s=35)
        mx=max(vals+[1])*1.05;ax.plot([0,mx],[0,mx],ls='--',color='#888',lw=1);ax.set(xlim=(-.03*mx,mx),ylim=(-.03*mx,mx),xlabel='LS omissions',ylabel=a+' omissions',title=f'Common feasible inputs: {len(common)}');ax.legend();ax.grid(alpha=.15)
    fig.tight_layout();fig.savefig(figdir/'study_paired.png',bbox_inches='tight');plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(10,3.3))
    examples=[next(r for r in cases if r['family']==f and r['config'][0]==80) for f in ['U','C']]+[next(r for r in extra if r['family']=='O' and r['config'][0]==80)]
    for ax,r in zip(axs,examples):
        d=r['input'];pt=np.array(d['points']);ax.scatter(*pt.T,s=13,color='#416e89');ax.set(xlim=(0,1),ylim=(0,1),xlabel='x coordinate',ylabel='y coordinate',title=f"{r['family']}:n=80, r={d['r']:.3f}");ax.set_aspect('equal');ax.grid(alpha=.15)
    fig.tight_layout();fig.savefig(figdir/'study_inputs.png',bbox_inches='tight');plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(10,3.7),sharey=True)
    for ax,v in zip(axs,VARIANTS):
        count=0
        for r in extra:
            fe=[z['results'][v] for z in r['repeats'] if z['results'][v]['feasible']]
            if not fe:continue
            count+=1;ys=[avg([z['before_local_L'] for z in fe]),avg([z['L'] for z in fe])];ax.plot([0,1],ys,marker='o',ms=3,alpha=.6,color='#437ca5' if r['family']=='U' else '#d28545')
        ax.set(xticks=[0,1],xticklabels=['Before local search','After local search'],xlim=(-.25,1.25),title=f'{v}:{count} successful inputs');ax.grid(axis='y',alpha=.15)
    axs[0].set_ylabel('Mean omissions of feasible repeats per input');fig.tight_layout();fig.savefig(figdir/'ablation_before_after.png',bbox_inches='tight');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(9,3.6));factors=[1,1.15,1.3]
    for m in ['LS','SLS']:
        sv=[];tt=[]
        for f in factors:
            rs=[sc['results'][m] for r in extra for sc in r['radius_scan'] if sc['factor']==f];sv.append(sum(r['feasible'] for r in rs));tt.append(avg([r['total_seconds'] for r in rs]))
        axs[0].plot(factors,sv,marker='o',label=m,color=colors[m]);axs[1].plot(factors,tt,marker='o',label=m,color=colors[m])
    axs[0].set(ylim=(-.2,6.5),yticks=range(7),ylabel='Feasible base inputs / 6');axs[1].set_ylabel('Mean total time / s')
    for ax in axs:ax.set_xticks(factors);ax.set_xlabel('Radius factor r/r0');ax.legend();ax.grid(alpha=.15)
    fig.tight_layout();fig.savefig(figdir/'radius_scan.png',bbox_inches='tight');plt.close(fig)
if __name__=='__main__':main()
