"""Re-audit saved runs, then create all paper tables and performance figures.
Never launches a solver. With --paper, writes generated TeX into that directory.
"""
from pathlib import Path
import argparse,json,csv,itertools,math
import numpy as np
from benchmark import METHODS,prepare,objective,violations,dump
from grouping_core import restore
ROOT=Path(__file__).resolve().parent
NAMES={'G':'受约束贪心','LS':'贪心与局部搜索','MIP':'分支割整数规划','LPR':'连续松弛—取整修复'}
def fmt(x,places=1):return '--' if x is None else f'{x:.{places}f}'
def avg(xs):return float(np.mean(xs)) if xs else None
def tex_table(caption,label,headers,rows,spec):
 body='\n'.join(' & '.join(map(str,r))+r' \\' for r in rows)
 return '\\begin{table}[htbp]\n\\centering\\small\n'+f'\\caption{{{caption}}}\\label{{{label}}}\n'+f'\\begin{{tabular}}{{{spec}}}\\toprule\n'+' & '.join(headers)+r' \\\midrule'+'\n'+body+'\n\\bottomrule\\end{tabular}\n\\end{table}\n'
def metric_table(caption,label,items):
 head=r'''\begin{table}[htbp]
\centering\footnotesize\setlength{\tabcolsep}{3pt}
\caption{CAPTION}\label{LABEL}
\resizebox{\textwidth}{!}{\begin{tabular}{l*{4}{rrr}}\toprule
 & \multicolumn{3}{c}{G} & \multicolumn{3}{c}{LS} & \multicolumn{3}{c}{MIP} & \multicolumn{3}{c}{LPR}\\
\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}\cmidrule(lr){11-13}
输入 & obj & infeas & time & obj & infeas & time & obj & infeas & time & obj & infeas & time\\\midrule
'''.replace('CAPTION',caption).replace('LABEL',label)
 return head+'\n'.join(' & '.join(r)+r' \\' for r in items)+'\n\\bottomrule\\end{tabular}}\n\\end{table}\n'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data',default='data');ap.add_argument('--paper');ap.add_argument('--scenarios-only',action='store_true');args=ap.parse_args()
 if args.scenarios_only:
  gen=Path(args.paper)/'generated' if args.paper else ROOT/'generated';gen.mkdir(exist_ok=True);materialize_scenarios(gen);print('Small-scenario tables and audit complete.');return
 source=ROOT/args.data;raw=json.loads((source/'results.json').read_text());assert raw['complete'] and len(raw['instances'])==18
 cases=raw['instances'];allrows=[];checks=[]
 for rec in cases:
  if 'input' not in rec:rec['input']=json.loads((source/rec['name']/'instance.json').read_text())
  if 'results' not in rec:rec['results']={m:json.loads((source/rec['name']/f'{m}.json').read_text()) for m in METHODS}
 for rec in cases:
  d=rec['input'];p=prepare(d);w=json.loads((source/rec['name']/'witness.json').read_text())
  assert violations(d,w['labels'])['H']==0
  for method in METHODS:
   r=rec['results'][method];lab=r.get('labels');H=None;L=None
   assert r==json.loads((source/rec['name']/f'{method}.json').read_text()), 'aggregate differs from per-run original record'
   assert r.get('solver_status') not in (2,3), 'solver contradicted saved feasible witness'
   if r.get('status')=='optimal':assert r['feasible']
   if lab is not None:
    assert len(lab)==d['n'] and all(isinstance(g,int) and 0<=g<=d['m']-1 for g in lab)
    H=violations(d,lab)['H'];assert H==r['H']
    if H==0:
     L,cnt=objective(p,lab,d['m']);x=np.eye(d['m'],dtype=int)[lab];_,_,_,ad=restore(d,x)
     assert L==ad['L']==r['L'] and all(ad['checks'].values())
     assert ad['round_records']==r['calls']
   assert r['feasible']==(H==0) and r['L']==L
   if L is not None:
    assert r['lower_bound']<=L+2e-6
    if r.get('status')=='optimal':assert abs(r['lower_bound']-L)<=1e-5
   assert r['total_seconds']>=0
   if method=='LPR' and 'lp_rows' in r:
    x=np.zeros((d['n'],d['m']))
    for i,row in enumerate(r['lp_rows']):
     for g,v in row:x[i,g]=v
    tol=2e-6
    assert abs(x.sum(1)-1).max()<=tol and x.min()>=-tol and x.max()<=1+tol
    assert x.sum(0).max()<=d['K']+tol
    di,dj=np.where(np.triu(~(p['dist']<=d['r']),1))
    if len(di):assert np.max(x[di]+x[dj])<=1+tol
    for t in d['strict']:
     if d['targets'][t]:assert x[d['targets'][t]].sum(0).max()<=1+tol
    lower=float(np.maximum(p['soft']@x-1,0).sum())
    assert abs(lower-r['lp_objective'])<=1e-4
    assert abs(r['lp_objective']-p['lower'])<=1e-4
    assert violations(d,r['raw_rounding_labels'])['H']==r['raw_rounding_H']
   allrows.append(dict(instance=rec['name'],family=rec['family'],n=d['n'],m=d['m'],T=len(d['targets']),method=method,feasible=r['feasible'],obj=L,infeas=H,time=r['total_seconds'],status=r['status'],lower_bound=r.get('lower_bound'),solver_status=r.get('solver_status'),raw_rounding_H=r.get('raw_rounding_H'),watchdog_timeout=r.get('watchdog_timeout'),groups_min=min(map(len,r['groups'])) if r.get('feasible') else None,groups_max=max(map(len,r['groups'])) if r.get('feasible') else None))
   checks.append(dict(instance=rec['name'],method=method,checked=True,feasible=r['feasible']))
 with (source/'results_table.csv').open('w',newline='',encoding='utf-8-sig') as f:
  wr=csv.DictWriter(f,fieldnames=list(allrows[0]));wr.writeheader();wr.writerows(allrows)
 blocks=[]
 for n,m,T in raw['protocol']['configs']:
  for family in raw['protocol']['families']:
   selected=[r for r in allrows if r['n']==n and r['family']==family];stats={}
   for method in METHODS:
    rr=[r for r in selected if r['method']==method];fe=[r for r in rr if r['feasible']];ca=[r for r in rr if r['infeas'] is not None]
    stats[method]=dict(success=len(fe),candidate=len(ca),total=len(rr),obj=avg([r['obj'] for r in fe]),infeas=avg([r['infeas'] for r in ca]),time=avg([r['time'] for r in rr]),time_std=float(np.std([r['time'] for r in rr],ddof=1)))
   blocks.append(dict(n=n,m=m,T=T,family=family,methods=stats))
 totals={m:dict(success=sum(r['feasible'] for r in allrows if r['method']==m),candidates=sum(r['infeas'] is not None for r in allrows if r['method']==m),time_mean=avg([r['time'] for r in allrows if r['method']==m]),optimal=sum(rec['results'][m].get('status')=='optimal' and rec['results'][m]['feasible'] for rec in cases)) for m in METHODS}
 pairs=[]
 for a,b in [('LS','G'),('MIP','LS'),('LPR','LS'),('MIP','LPR')]:
  rr=[rec for rec in cases if rec['results'][a]['feasible'] and rec['results'][b]['feasible']]
  diffs=[rec['results'][a]['L']-rec['results'][b]['L'] for rec in rr]
  pairs.append(dict(a=a,b=b,total=len(rr),win=sum(z<0 for z in diffs),tie=sum(z==0 for z in diffs),loss=sum(z>0 for z in diffs),mean_difference=avg(diffs)))
 rounding=[]
 for block in blocks:
  rr=[rec['results']['LPR'] for rec in cases if rec['family']==block['family'] and rec['config'][0]==block['n']]
  rounding.append(dict(n=block['n'],family=block['family'],LP_solved=sum('lp_rows' in r for r in rr),raw_feasible=sum(r.get('raw_rounding_feasible',False) for r in rr),repaired=sum(r.get('status')=='repaired' for r in rr),reconstructed=sum(r['feasible'] and r.get('status') in ['completed','deadline','watchdog_timeout'] for r in rr),final_feasible=sum(r['feasible'] for r in rr),raw_H_mean=avg([r['raw_rounding_H'] for r in rr if 'raw_rounding_H' in r])))
 quality=[]
 for rec in cases:
  count=prepare(rec['input'])['lower']
  lower=max([float(count)]+[float(rec['results'][m]['lower_bound']) for m in METHODS if rec['results'][m].get('lower_bound') is not None])
  feasible=[rec['results'][m]['L'] for m in METHODS if rec['results'][m]['feasible']]
  upper=min(feasible) if feasible else None
  if upper is not None:assert lower<=upper+2e-6
  count=prepare(rec['input'])['lower']
  witness=json.loads((source/rec['name']/'witness.json').read_text())
  witness_loss=objective(prepare(rec['input']),witness['labels'],rec['input']['m'])[0]
  assert lower<=witness_loss+2e-6
  quality.append(dict(instance=rec['name'],family=rec['family'],n=rec['config'][0],count_bound=count,witness_loss=witness_loss,best_lower=lower,best_upper=upper,gap=None if upper is None else max(0.,upper-lower),matched=upper is not None and abs(upper-lower)<=1e-6))
 maxover=max(r['time'] for r in allrows);over=[r for r in allrows if r['time']>600]
 summary=dict(protocol=raw['protocol'],inputs=len(cases),runs=len(allrows),blocks=blocks,totals=totals,pairs=pairs,rounding=rounding,quality_bounds=quality,maximum_measured_seconds=maxover,over_600=len(over),audit_checks=len(checks),audit_success=True)
 dump(source/'summary.json',summary);dump(source/'audit.json',dict(checks=checks,all_consistent=True))
 gen=Path(args.paper)/'generated' if args.paper else ROOT/'generated';gen.mkdir(exist_ok=True)
 table_rows=[]
 for b in blocks:
  row=[f"{b['family']}({b['n']},{b['m']},{b['T']})"]
  for m in METHODS:
   v=b['methods'][m];row.extend([fmt(v['obj']),fmt(v['infeas']),fmt(v['time'],2)])
  table_rows.append(row)
 (gen/'main_table.tex').write_text(metric_table('各参数组的平均结果：obj为可行方案遗漏量，infeas为返回整数候选的违反量，time为全部运行的总耗时（秒）；每行3个独立输入','tab:main-results',table_rows))
 successrows=[]
 for b in blocks:
  row=[f"{b['family']}({b['n']},{b['m']},{b['T']})"]
  for m in METHODS:
   s=b['methods'][m];row.append(f"{s['success']}/3 ({s['candidate']}/3)")
  successrows.append(row)
 (gen/'success_table.tex').write_text(tex_table('可行成功数与整数候选数；括号内为有候选的次数，分母均为3','tab:success',['输入','G','LS','MIP','LPR'],successrows,'lrrrr'))
 (gen/'pair_table.tex').write_text(tex_table('共同可行输入上的目标值配对；优、平、劣均指前一方法相对后一方法','tab:paired',['方法对','共同可行数','优','平','劣','平均差'],[[f"{p['a']} / {p['b']}",p['total'],p['win'],p['tie'],p['loss'],fmt(p['mean_difference'])] for p in pairs],'lrrrrr'))
 (gen/'rounding_table.tex').write_text(tex_table('各阶段成功次数与初次取整的平均违反量；每组3次，平均只统计取得LP最优解的输入','tab:rounding-outcomes',['输入','LP最优','初次可行','初次平均$H$','冲突修复','重构','最终可行'],[[f"{b['family']}{b['n']}",b['LP_solved'],b['raw_feasible'],fmt(b['raw_H_mean']),b['repaired'],b['reconstructed'],b['final_feasible']] for b in rounding],'lrrrrrr'))
 (gen/'per_instance_table.tex').write_text(metric_table('18个独立输入的逐例结果；目标与违反量未定义时记为--，耗时保留两位小数','tab:all-results',[[rec['name'].replace('_',r'\_')]+[val for m in METHODS for val in [fmt(rec['results'][m]['L'],0),fmt(rec['results'][m]['H'],0),fmt(rec['results'][m]['total_seconds'],2)]] for rec in cases]))
 geometry=[]
 for n,m,T in raw['protocol']['configs']:
  for fam in ['U','C']:
   rr=[rec for rec in cases if rec['family']==fam and rec['config'][0]==n];rvals=[];dens=[];spatial=[]
   for rec in rr:
    pp=prepare(rec['input']);rvals.append(rec['input']['r']);dens.append(np.triu(pp['bad'],1).sum()/(n*(n-1)/2));spatial.append(np.triu(~(pp['dist']<=rec['input']['r']),1).sum()/(n*(n-1)/2))
   sizes=[next((rec['results'][method]['model_size']['rows'] for method in ['MIP','LPR'] if 'model_size' in rec['results'][method]),None) for rec in rr]
   geometry.append([f'{fam}({n},{m},{T})',fmt(avg(rvals),3),fmt(100*avg(spatial),1)+r'\%',fmt(100*avg(dens),1)+r'\%',fmt(avg([v for v in sizes if v is not None]),0)])
 (gen/'geometry_table.tex').write_text(tex_table('输入的平均距离阈值、冲突密度与约束矩阵规模；行数不含变量上下界','tab:geometry',['输入','平均$r$','距离边比例','合并硬冲突边比例','线性约束行数'],geometry,'lrrrr'))
 qrows=[]
 for block in blocks:
  rr=[q for q in quality if q['n']==block['n'] and q['family']==block['family']];known=[q for q in rr if q['best_upper'] is not None]
  qrows.append([f"{block['family']}{block['n']}",f'{len(known)}/3',fmt(avg([q['count_bound'] for q in rr])),fmt(avg([q['best_lower'] for q in rr])),fmt(avg([q['witness_loss'] for q in rr])),fmt(avg([q['best_upper'] for q in known])),fmt(avg([q['gap'] for q in known])),f"{sum(q['matched'] for q in rr)}/3"])
 (gen/'bound_table.tex').write_text(tex_table('比较方法的上下界与生成见证；U仅取四种方法返回的可行目标，不计见证。U及差值仅在有返回方案的输入上平均','tab:bounds',['输入','有解数','$B_{\\mathrm{count}}$','$B$','见证目标','$U$','$U-B$','界相合数'],qrows,'lrrrrrrr'))

 # Narrative generated only from the preserved real records.
 texts=[]
 texts.append('18个独立输入共完成72次比较运行。G、LS、MIP和LPR分别取得'+ '、'.join(str(totals[m]['success']) for m in METHODS)+'例可行方案；相应平均总耗时分别为'+ '、'.join(fmt(totals[m]['time_mean'],2) for m in METHODS)+'秒。所有接受方案均通过原模型规则检查，恢复遗漏量与分组评价一致。')
 texts.append(f"其中MIP有{totals['MIP']['optimal']}次正常返回最优状态。其他已取得的可行候选按其遗漏量报告，不由可行性直接推定最优。")
 p=next(p for p in pairs if p['a']=='MIP' and p['b']=='LPR')
 texts.append(f"在MIP与LPR共同可行的{p['total']}个输入上，MIP取得{p['win']}优、{p['tie']}平、{p['loss']}劣。该配对比较只说明两者均成功时的目标质量；两种方法的失败输入仍计入表\\ref{{tab:success}}的分母。")
 pg=next(q for q in pairs if q['a']=='LS' and q['b']=='G')
 pl=next(q for q in pairs if q['a']=='LPR' and q['b']=='LS')
 texts.append(f"LS相对G在{pg['total']}个共同可行输入上取得{pg['win']}优、{pg['tie']}平、{pg['loss']}劣，平均目标差为{fmt(pg['mean_difference'])}。但LS的可行总数未超过G，说明已找到分组的局部改善与从头构造可行分组是两个不同环节。LPR相对LS在{pl['total']}个共同可行输入上取得{pl['win']}优、{pl['tie']}平、{pl['loss']}劣，平均目标差为{fmt(pl['mean_difference'])}；本次结果未支持LP取整修复具有更好的遗漏质量。")
 hard=[rec for rec in cases if rec['family']=='C' and rec['config'][0]==320]
 failedall=sum(not any(rec['results'][m]['feasible'] for m in METHODS) for rec in hard)
 texts.append(f"C类320资源的{len(hard)}个输入中，有{failedall}个在四种方法下均未得到合格方案。各输入的生成见证已通过相同规则检查，因此这些记录反映当前求解流程的局限，不能作为输入无解的依据。")
 if maxover>600:texts.append(f"单次实测最大耗时为{maxover:.2f}秒，有{len(over)}次略超过600秒。外部监控按600秒发出终止；进程退出和最终校验的耗时继续计入表中，不将超出部分截断。")
 else:texts.append(f"单次实测最大耗时为{maxover:.2f}秒，全部运行均在600秒内退出。提前停止可能来自最优状态、启发式工作量上限或停滞条件，不代表所有方法具有相同的证明状态。")
 solved=sum(b['LP_solved'] for b in rounding);rawok=sum(b['raw_feasible'] for b in rounding);repok=sum(b['repaired'] for b in rounding);fallback=sum(b['reconstructed'] for b in rounding)
 texts.append(f"LPR中有{solved}次LP取得最优状态，其中{rawok}次最大分量取整直接可行，{repok}次经容量与冲突修复取得可行分组，另有{fallback}次经受约束重构成功。初次取整和最终检查分别记录，避免将LP可行误记为整数分组可行。")
 (gen/'main_interpretation.tex').write_text('\n\n'.join(texts)+'\n')
 (gen/'abstract_results.tex').write_text('实验采用两类几何分布、80至320个资源和20至80名管理者的18个独立输入，比较受约束贪心、局部搜索、分支割整数规划和连续松弛取整修复四种方法，单次运行上限均为600秒。四种方法分别取得'+ '、'.join(str(totals[m]['success']) for m in METHODS)+'例可行方案。')
 (gen/'conclusion_results.tex').write_text('在18个独立输入的72次比较中，G、LS、MIP与LPR的可行数分别为'+ '、'.join(str(totals[m]['success']) for m in METHODS)+f"。在{p['total']}个共同可行输入上，MIP相对LPR取得{p['win']}优、{p['tie']}平、{p['loss']}劣。数值结果需要结合可行成功数、遗漏量和耗时评价；固定时间上限下的失败不构成原问题无解的证明。")
 materialize_scenarios(gen)
 # Summary overview and tables are derived; raw input and per-run files remain untouched.
 print(json.dumps(summary,ensure_ascii=False,indent=2))
 make_figures(cases,blocks,source,Path(args.paper)/'figures' if args.paper else ROOT/'figures')

def materialize_scenarios(gen):
 scenario=json.loads((ROOT/'scenario_data/results.json').read_text());assert scenario['complete']
 scenario_checks=[]
 for item in scenario['independent']+scenario['special']:
  dp=(ROOT/'scenario_data'/item['name']/'instance.json') if item in scenario['independent'] else (ROOT/'solutions'/f"{item['name']}_input.json")
  dd=json.loads(dp.read_text())
  for method in ['MIP','LPR']:
   rr=item['results'][method];ll=rr.get('labels');hh=None
   if ll is not None:
    hh=violations(dd,ll)['H'];assert hh==rr['H']
    if hh==0:
     xx=np.eye(dd['m'],dtype=int)[ll];_,_,_,aa=restore(dd,xx);assert aa['L']==rr['L'] and aa['round_records']==rr['calls']
   assert rr['feasible']==(hh==0)
   scenario_checks.append(dict(input=item['name'],method=method,checked=True,feasible=rr['feasible']))
 dump(ROOT/'scenario_data/audit.json',dict(runs=scenario_checks,all_consistent=True,enumeration=scenario['enumeration']))
 srows=[]
 for cfg in scenario['protocol']['configs']:
  selected=[r for r in scenario['independent'] if r['config']==cfg]
  for method in ['MIP','LPR']:
   rr=[r['results'][method] for r in selected];fe=[r for r in rr if r['feasible']]
   for r in fe:
    sizes=[len(g) for g in r['groups']];assert max(sizes)<=5
   sizes=[len(g) for r in fe for g in r['groups']]
   srows.append([f"({cfg[0]},{cfg[1]},{cfg[2]})",method,f'{len(fe)}/3',fmt(avg([r['L'] for r in fe])),('--' if not sizes else f'{min(sizes)}--{max(sizes)}'),fmt(avg([r['total_seconds'] for r in rr]),3)])
 (gen/'scenario_table.tex').write_text(tex_table('小算例的独立重复结果；每套参数3个输入，组大小为所有已接受分组的范围','tab:scenario-checks',['$(n,m,T)$','方法','可行数','平均遗漏','实际组大小','平均耗时/s'],srows,'lcrrrr'))
 spec=[]
 for rec in scenario['special']:
  label={'base8':'8资源算例','seed66':'9资源算例','round32':'32轮情境'}[rec['name']]
  for method in ['MIP','LPR']:
   r=rec['results'][method];cfg=rec['config'];sz=[len(g) for g in r['groups']] if r['feasible'] else []
   spec.append([label,method,f'({cfg[0]},{cfg[1]},{cfg[2]})',fmt(r['L'],0),('--' if not sz else f'{min(sz)}--{max(sz)}'),fmt(r['total_seconds'],3)])
 (gen/'special_table.tex').write_text(tex_table('三个说明情境的新求解记录；每情境每方法运行一次，逐轮展示采用正文列出的固定方案','tab:special-timing',['情境','方法','$(n,m,T)$','遗漏','组大小','耗时/s'],spec,'lclrrr'))
 nine=next(r for r in scenario['special'] if r['name']=='seed66')
 (gen/'nine_caption.tex').write_text(r'\caption{9资源、3组、6轮算例的逐轮调用；分组大小均为3。实测总耗时：MIP '+fmt(nine['results']['MIP']['total_seconds'],3)+' s，LPR '+fmt(nine['results']['LPR']['total_seconds'],3)+' s}\n')

def make_figures(cases,blocks,source,figdir):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib import font_manager
 figdir.mkdir(exist_ok=True)
 from plot_style import configure
 configure(plt)
 plt.rcParams.update({'axes.unicode_minus':False,'font.size':11.5,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':200})
 cols={'G':'#547eaa','LS':'#dd9142','MIP':'#479778','LPR':'#9b639d'}
 fig,ax=plt.subplots(1,2,figsize=(9,3.5));ns=[80,160,320];xx=np.arange(3);width=.18
 for k,m in enumerate(METHODS):
  successes=[sum(rec['results'][m]['feasible'] for rec in cases if rec['config'][0]==n) for n in ns]
  means=[np.mean([rec['results'][m]['total_seconds'] for rec in cases if rec['config'][0]==n]) for n in ns]
  ax[0].bar(xx+(k-1.5)*width,successes,width,color=cols[m],label=m)
  ax[1].plot(ns,means,marker={'G':'o','LS':'s','MIP':'^','LPR':'D'}[m],linestyle={'G':'-','LS':'--','MIP':'-.','LPR':':'}[m],color=cols[m],label=m)
 ax[0].set_xticks(xx,ns);ax[0].set_ylim(0,7.3);ax[0].set_yticks(range(7));ax[0].set_ylabel('可行输入数 / 6');ax[0].set_xlabel('资源数 n');ax[0].legend(ncol=4,fontsize=11,loc='upper center');ax[0].grid(axis='y',alpha=.15)
 ax[1].set_yscale('log');ax[1].set_xticks(ns);ax[1].set_xlabel('资源数 n');ax[1].set_ylabel('平均总耗时 / s（对数轴）');ax[1].legend(ncol=2,fontsize=11);ax[1].grid(alpha=.15)
 fig.tight_layout();fig.savefig(figdir/'study_success_time.png',bbox_inches='tight');plt.close(fig)
 fig,axs=plt.subplots(1,2,figsize=(8.7,3.8))
 for ax,(a,b) in zip(axs,[('LPR','LS'),('MIP','LS')]):
  common=[rec for rec in cases if rec['results'][a]['feasible'] and rec['results'][b]['feasible']]
  vals=[]
  for fam,mk in [('U','o'),('C','^')]:
   rr=[r for r in common if r['family']==fam]
   x=[r['results'][b]['L'] for r in rr];y=[r['results'][a]['L'] for r in rr];vals+=x+y
   ax.scatter(x,y,label=fam,marker=mk,s=36,alpha=.8)
  mx=max(vals+[1])*1.04;ax.plot([0,mx],[0,mx],color='#777777',ls='--',lw=1)
  ax.set_xlim(-.03*mx,mx);ax.set_ylim(-.03*mx,mx);ax.set_xlabel(f'{b} 遗漏量');ax.set_ylabel(f'{a} 遗漏量');ax.set_title(f'共同可行输入 {len(common)} 个');ax.legend(fontsize=11);ax.grid(alpha=.15)
 fig.tight_layout();fig.savefig(figdir/'study_paired.png',bbox_inches='tight');plt.close(fig)
 fig,axs=plt.subplots(2,2,figsize=(7.6,6.8))
 for ax,(fam,n) in zip(axs.ravel(),[('U',80),('C',80),('U',320),('C',320)]):
  rec=next(r for r in cases if r['family']==fam and r['config'][0]==n);d=rec['input'];pts=np.array(d['points']);ax.scatter(*pts.T,s=10 if n==320 else 16,color='#466c88',alpha=.8)
  ax.set_xlim(0,1);ax.set_ylim(0,1);ax.set_aspect('equal');ax.set_title(f"{fam}: n={n}, m={d['m']}, r={d['r']:.3f}");ax.set_xlabel('横坐标');ax.set_ylabel('纵坐标');ax.grid(alpha=.12)
 fig.tight_layout();fig.savefig(figdir/'study_inputs.png',bbox_inches='tight');plt.close(fig)
if __name__=='__main__':main()
