"""Figures from the independent B&B proof-check trace, not production history."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent
local_font = Path('/usr/local/share/fonts/NotoSansCJKsc-Regular.otf')
if local_font.exists(): font_manager.fontManager.addfont(str(local_font))
for name in ['Noto Sans CJK SC', 'Microsoft YaHei', 'SimHei', 'SimSun']:
    try:
        font_manager.findfont(font_manager.FontProperties(family=[name]), fallback_to_default=False)
        break
    except ValueError: continue
else: raise RuntimeError('A Chinese font is required to regenerate these figures')
plt.rcParams.update({'font.family': name, 'font.size': 11, 'axes.unicode_minus': False})
DATA = json.loads((ROOT/'convergence_checks.json').read_text())
CASE = next(c for c in DATA['cases'] if c['name']=='seed66')['result']
BLUE, GREEN, ORANGE = '#275D8C', '#268374', '#D68D32'

def tree():
    fig, ax = plt.subplots(figsize=(9.2,3.9))
    pos={0:(5.,3.9),1:(2.7,2.7),2:(7.5,2.7),3:(1.2,1.5),4:(4.,1.5),
         5:(6.7,1.5),6:(8.8,1.5),7:(.6,.3),8:(1.9,.3),9:(3.35,.3),10:(4.65,.3)}
    for node in CASE['nodes']:
        nid=node['id'];x,y=pos[nid]
        if node['parent'] is not None:
            parent=node['parent'];px,py=pos[parent]
            ax.plot([px,x],[py-.34,y+.34],color='#8A9299',lw=1,zorder=1)
            parent_fixed=CASE['nodes'][parent]['fixed']
            changed=set(node['fixed'])-set(parent_fixed)
            value=node['fixed'][changed.pop()]
            ax.text(.48*px+.52*x,.48*py+.52*y,str(value),ha='center',va='center',
                    bbox={'facecolor':'white','edgecolor':'none','pad':1.2},fontsize=9)
        leaf=node['action'].startswith('bound_prune')
        color=GREEN if leaf else BLUE
        ax.add_patch(FancyBboxPatch((x-.48,y-.32),.96,.64,boxstyle='round,pad=.035',
                                    fc='#F3F8F8' if leaf else '#F1F6FA',ec=color,lw=1.2,zorder=2))
        ax.text(x,y,f"N{nid}\nb = {node['lp_objective']:g}",ha='center',va='center',color=color,
                fontsize=10,zorder=3)
    ax.text(6.2,.32,'蓝框：继续分支\n绿框：下界达到上界6，剪枝',color='#404A53',fontsize=10.5,va='center')
    ax.set(xlim=(-.05,9.6),ylim=(-.15,4.5));ax.axis('off')
    ax.set_title('种子66的参考分支树（不表示HiGHS内部搜索树）',fontsize=12)
    fig.savefig(ROOT/'figures'/'reference_branch_tree.png',dpi=230,bbox_inches='tight')
    plt.close(fig)

def bounds():
    h=CASE['history']; k=np.arange(len(h))
    lower=np.array([v['lower_bound'] for v in h]);upper=np.array([v['upper_bound'] for v in h])
    fig,axes=plt.subplots(1,2,figsize=(9.2,3.45),gridspec_kw={'width_ratios':[1.5,1]})
    ax=axes[0]
    ax.step(k,upper,where='post',color=GREEN,lw=2.2,label='可行上界 U')
    ax.step(k,lower,where='post',color=BLUE,lw=2.2,ls='--',label='全局下界 B')
    ax.fill_between(k,lower,upper,step='post',color=ORANGE,alpha=.18)
    ax.set(xlabel='完成的节点处理步 k（0为根LP）',ylabel='遗漏量界',ylim=(4.75,6.65),xlim=(0,k[-1]))
    ax.set_yticks([5,6]);ax.set_xticks([0,2,4,6,8,10]);ax.legend(frameon=False,loc='upper left',ncol=2,fontsize=10)
    ax.text(5.15,5.25,'第5步：下界提高到6',fontsize=9.5,color=BLUE)
    ax.grid(alpha=.15)
    ax=axes[1]
    ax.step(k,upper-lower,where='post',color=ORANGE,lw=2.2)
    ax.set(xlabel='完成的节点处理步 k',ylabel='绝对间隙 U - B',ylim=(-.12,1.25),xlim=(0,k[-1]))
    ax.set_yticks([0,1]);ax.set_xticks([0,5,10]);ax.grid(alpha=.15)
    fig.suptitle('参考程序实测：上界保持6，最优性确认来自下界提高',fontsize=12,y=1.03)
    fig.tight_layout()
    fig.savefig(ROOT/'figures'/'reference_bound_trace.png',dpi=230,bbox_inches='tight')
    plt.close(fig)

if __name__=='__main__': tree();bounds()
