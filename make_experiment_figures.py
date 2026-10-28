"""Scientific figures and TeX tables generated only from measured results."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parent;EXP=ROOT/'experiments';FIG=ROOT/'figures'
local=Path('/usr/local/share/fonts/NotoSansCJKsc-Regular.otf')
if local.exists():font_manager.fontManager.addfont(str(local))
for name in ['Noto Sans CJK SC','Microsoft YaHei','SimHei','SimSun']:
    try:font_manager.findfont(font_manager.FontProperties(family=[name]),fallback_to_default=False);break
    except ValueError:continue
else:raise RuntimeError('Chinese font required')
plt.rcParams.update({'font.family':name,'font.size':11,'axes.unicode_minus':False})
S=json.loads((EXP/'summary.json').read_text());D=json.loads((EXP/'results.json').read_text())
METHODS=['G','LS','P1','P2'];NAMES=['G','LS','P1-MIP','P2-MIP']
COLORS=['#8895A5','#D68D32','#5C799B','#268374']

def save(fig,name):
    fig.savefig(FIG/name,dpi=230,bbox_inches='tight',facecolor='white');plt.close(fig)

def inputs():
    fig,axes=plt.subplots(1,2,figsize=(8.8,3.7))
    for ax,fam,title in zip(axes,['U','C'],['U：先均匀采样坐标','C：网格中心附近采样']):
        case=next(c for c in D['cases'] if c['family']==fam and c['n']==32)
        pts=np.array(case['instance']['points'])
        witness=json.loads((EXP/(case['name']+'_witness.json')).read_text())
        ax.scatter(pts[:,0],pts[:,1],c=witness['labels_zero_based'],cmap='tab10',s=32)
        ax.set(title=title,xlabel='横坐标',ylabel='纵坐标',xlim=(-.02,1.02),ylim=(-.02,1.02));ax.set_aspect('equal')
        ax.set_xticks([0,.5,1]);ax.set_yticks([0,.5,1]);ax.grid(alpha=.12)
    fig.suptitle('两类合成输入示例（颜色仅展示生成时的可行见证）',fontsize=12)
    fig.tight_layout();save(fig,'experiment_inputs.png')

def outcomes():
    fig,axes=plt.subplots(1,2,figsize=(9.2,3.8),gridspec_kw={'width_ratios':[1,1.15]})
    cats=[]
    for a in METHODS:
        r=[v for v in S['rows'] if v['method']==a]
        cats.append([sum(v['certified_with_shared_bound'] for v in r),
                     sum(v['best_known_attained'] and not v['certified_with_shared_bound'] for v in r),
                     sum(v['feasible'] and not v['best_known_attained'] for v in r),
                     sum(not v['feasible'] for v in r)])
    cats=np.array(cats);bottom=np.zeros(4)
    ax=axes[0]
    for j,(label,color) in enumerate(zip(['已由公共界确认最优','达到本例最佳已知值','可行但高于最佳已知值','未取得可行方案'],
                                        ['#268374','#5C799B','#D68D32','#CED3DA'])):
        ax.bar(np.arange(4),cats[:,j],bottom=bottom,label=label,color=color,width=.65)
        for i,value in enumerate(cats[:,j]):
            if value:ax.text(i,bottom[i]+value/2,str(value),ha='center',va='center',fontsize=10)
        bottom+=cats[:,j]
    ax.set_xticks(range(4),NAMES,rotation=15);ax.set_yticks([0,8,16,24]);ax.set(ylabel='实例数（每种方法24例）',ylim=(0,26),title='全部输入的结果分类')
    ax.legend(loc='upper left',bbox_to_anchor=(-.09,-.28),frameon=False,fontsize=9)
    ax=axes[1];x=np.arange(3);w=.19
    for j,a in enumerate(METHODS):
        values=[sum(v['feasible'] for v in S['rows'] if v['method']==a and v['n']==n) for n in [16,32,64]]
        ax.bar(x+(j-1.5)*w,values,width=w,color=COLORS[j],label=NAMES[j])
        for i,value in enumerate(values):ax.text(x[i]+(j-1.5)*w,value+.13,str(value),ha='center',fontsize=8)
    ax.set_xticks(x,['16','32','64']);ax.set_yticks([0,2,4,6,8]);ax.set(xlabel='资源数 n',ylabel='可行实例数（各规模8例）',ylim=(0,9.2),title='规模增加后的可行方案产出')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.25),ncol=2,frameon=False,fontsize=9)
    fig.subplots_adjust(wspace=.35,bottom=.32);save(fig,'experiment_outcomes.png')

def paired():
    fig,ax=plt.subplots(figsize=(8.8,3.5))
    for j,a in enumerate(['P1','G','LS']):
        pair=S['paired_comparisons_P2'][a]
        vals=np.array([v['normalized_percent'] for v in pair['differences']])
        offsets=np.linspace(-.12,.12,len(vals)) if len(vals) else []
        colors=['#5C799B' if v['family']=='U' else '#D68D32' for v in pair['differences']]
        ax.scatter(j+np.array(offsets),vals,c=colors,s=30,alpha=.8)
        if len(vals):ax.plot([j-.21,j+.21],[np.median(vals)]*2,c='#202B36',lw=2.4)
    ax.axhline(0,color='#808890',lw=1,ls='--')
    labels=[f'P2 与 {a}\n共同可行 {S["paired_comparisons_P2"][a]["common"]}例' for a in ['P1','G','LS']]
    ax.set_xticks(range(3),labels);ax.set(ylabel='100 × (L(P2) - L(对比方法)) / 目标调用总数',title='同一实例配对：负值有利于P2，正值有利于对比方法')
    ax.scatter([],[],color='#5C799B',label='U输入');ax.scatter([],[],color='#D68D32',label='C输入')
    ax.plot([],[],color='#202B36',lw=2.4,label='中位数')
    ax.legend(frameon=False,ncol=3,loc='upper left',fontsize=9);ax.grid(axis='y',alpha=.15)
    save(fig,'experiment_paired_loss.png')

def timings():
    fig,axes=plt.subplots(1,2,figsize=(9.2,3.6));x=np.arange(3);w=.19
    for j,a in enumerate(METHODS):
        vals=[np.mean([v['total_seconds'] for v in S['rows'] if v['method']==a and v['n']==n]) for n in [16,32,64]]
        axes[0].bar(x+(j-1.5)*w,vals,width=w,color=COLORS[j],label=NAMES[j])
    axes[0].axhline(3,color='#8B4640',ls='--',lw=1,label='3秒软预算')
    axes[0].set_xticks(x,['16','32','64']);axes[0].set(xlabel='资源数 n',ylabel='实际总耗时均值（秒）',title='包含建模与校验的实测时间')
    axes[0].legend(frameon=False,fontsize=8,ncol=2)
    for j,a in enumerate(['P1','P2']):
        vals=[np.mean([v['build_seconds'] for v in S['rows'] if v['method']==a and v['n']==n]) for n in [16,32,64]]
        axes[1].bar(x+(j-.5)*.28,vals,width=.28,label=f'{a}-MIP',color=COLORS[j+2])
    axes[1].set_xticks(x,['16','32','64']);axes[1].set(xlabel='资源数 n',ylabel='构造矩阵耗时均值（秒）',title='两种表达的建模开销')
    axes[1].legend(frameon=False,fontsize=9);fig.tight_layout();save(fig,'experiment_timings.png')

def tables():
    def emit(filename,lines):
        normalized=[line.rstrip().rstrip(chr(92))+' '+chr(92)*2 for line in lines]
        (EXP/filename).write_text('\n'.join(normalized)+'\n')
    lines=[]
    for a in METHODS:
        v=S['aggregate'][a]
        lines.append(f"{a} & {v['feasible']}/24 & {v['best_known']}/24 & {v['shared_certified']}/24 & {v['median_seconds_all_runs']:.3f} & {v['max_seconds']:.3f} \\")
    emit('table_overall.tex',lines)
    lines=[]
    for b in S['blocks']:
        vals=[]
        for a in METHODS:
            v=b['methods'][a];val=v['mean_L_on_all_four_common']
            vals.append(f"{v['feasible']}/4; "+(f"{val:.2f}" if val is not None else '--'))
        lines.append(f"{b['family']} & {b['n']} & {b['all_four_common_feasible']} & "+' & '.join(vals)+r' \\')
    emit('table_blocks.tex',lines)
    lines=[]
    for a in ['P1','G','LS']:
        v=S['paired_comparisons_P2'][a]
        lines.append(f"P2--{a} & {v['common']} & {v['P2_better']} & {v['ties']} & {v['P2_worse']} & {v['mean_normalized_percent']:.2f} \\")
    emit('table_pairs.tex',lines)
    lines=[]
    for family in ['U','C']:
        for n in [16,32,64]:
            vals=[v for v in S['geometry'] if v['family']==family and v['n']==n]
            lines.append(f"{family} & {n} & {np.mean([v['r'] for v in vals]):.3f} & {np.mean([v['distance_only_density'] for v in vals]):.3f} & {np.mean([v['strict_only_density'] for v in vals]):.3f} \\")
    emit('table_geometry.tex',lines)

if __name__=='__main__':inputs();outcomes();paired();timings();tables()
