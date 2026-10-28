from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
D=json.loads((ROOT/'reduction_checks.json').read_text())
plt.rcParams.update({'font.family':'Noto Sans CJK SC','font.size':12,'axes.unicode_minus':False})
def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=240,bbox_inches='tight');plt.close(fig)

fig,ax=plt.subplots(figsize=(8.2,3.25));ax.axis('off');ax.set_xlim(-.3,5.5);ax.set_ylim(-.6,3.3)
rows=[(1,8,'距离与重要轮次冲突重合','#3F4650'),(4,5,'仅距离冲突','#286B9F'),
      (2,7,'仅重要轮次冲突','#A95724')]
for y,(i,j,label,color) in zip([2.7,1.7,.7],rows):
    ax.plot([0,1.4],[y,y],color=color,linewidth=2)
    ax.scatter([0,1.4],[y,y],s=520,color='#DCE8F1',edgecolors='#365A73',zorder=3)
    for x,k in [(0,i),(1.4,j)]:ax.text(x,y,str(k),ha='center',va='center',fontsize=14,zorder=4)
    ax.text(1.95,y,label,va='center',fontsize=13)
for x,k in [(0,3),(1.4,6)]:
    ax.scatter([x],[-.2],s=520,color='#DCE8F1',edgecolors='#365A73',zorder=3)
    ax.text(x,-.2,str(k),ha='center',va='center',fontsize=14)
ax.text(1.95,-.2,'资源3和6在此硬冲突图中为孤立点',va='center',fontsize=12)
save(fig,'hard_conflicts')

fig,axes=plt.subplots(1,2,figsize=(8.6,3.4),gridspec_kw={'width_ratios':[.85,1.4]})
ax=axes[0];ax.set_xlim(-.2,1.2);ax.set_ylim(-.15,1.2);ax.axis('off')
p=np.array([[0,0],[1,0],[.5,1]])
for i,j in [(0,1),(0,2),(1,2)]:ax.plot(p[[i,j],0],p[[i,j],1],color='#A95724',linewidth=1.8)
ax.scatter(p[:,0],p[:,1],s=410,color='#DCE8F1',edgecolors='#365A73',zorder=3)
for pos,k in zip(p,[1,2,3]):ax.text(*pos,str(k),ha='center',va='center',fontsize=13)
ax.set_title('硬冲突图中的三角形',fontsize=12)
ax.text(.5,-.11,'两组无法容纳三个两两冲突的资源',ha='center',va='top',fontsize=10)
ax=axes[1];x=np.array(D['tight_distance_results']['LP']['x']).T
ax.imshow(x,cmap='Blues',vmin=0,vmax=1,aspect='equal')
ax.set_xticks(range(8),range(1,9));ax.set_yticks([0,1],['组1','组2']);ax.set_xlabel('资源编号')
ax.set_title('连续松弛允许的分数分配',fontsize=12)
for row,col in np.ndindex(x.shape):ax.text(col,row,'0.5',ha='center',va='center',fontsize=11)
ax.set_xticks(np.arange(-.5,8,1),minor=True);ax.set_yticks(np.arange(-.5,2,1),minor=True)
ax.grid(which='minor',color='white',linewidth=1.2);ax.tick_params(which='minor',bottom=False,left=False)
for spine in ax.spines.values():spine.set_visible(False)
fig.subplots_adjust(wspace=.35,left=.04,right=.99,bottom=.18,top=.82)
save(fig,'fractional_counterexample')

fig,ax=plt.subplots(figsize=(8.5,1.45));ax.axis('off');ax.set_xlim(0,12);ax.set_ylim(0,2)
items=[('完整模型 P1','分组与逐轮启用'),('等价替代 P2','分组与遗漏下界'),('恢复实际调用','每组每轮选一个目标')]
for k,(title,sub) in enumerate(items):
    x=.1+k*4
    ax.add_patch(FancyBboxPatch((x,.27),3.2,1.38,boxstyle='round,pad=.04',
                 facecolor='#F2F5F8',edgecolor='#586A7D'))
    ax.text(x+1.6,1.18,title,ha='center',va='center',fontsize=14)
    ax.text(x+1.6,.70,sub,ha='center',va='center',fontsize=11)
    if k<2:ax.add_patch(FancyArrowPatch((x+3.3,.98),(x+3.86,.98),
                         arrowstyle='-|>',mutation_scale=13,color='#586A7D'))
save(fig,'reduction_route')
print('Three explanatory figures saved as PNG to preserve Chinese labels across PDF readers.')
