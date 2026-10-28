"""Exact diagrams from the explanatory example and its checked model solution."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
D=json.loads((ROOT/'example.json').read_text())
V=json.loads((ROOT/'verification.json').read_text())
plt.rcParams.update({'font.family':'Noto Sans CJK SC','font.size':10,
                     'axes.unicode_minus':False,'pdf.fonttype':42})

def save(fig,name):
    fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight')
    fig.savefig(OUT/(name+'.png'),dpi=210,bbox_inches='tight')
    plt.close(fig)

a=np.zeros((4,8),dtype=int)
for t,row in enumerate(D['rounds']):
    for i in row['targets']:a[t,i-1]=1
x=np.array(V['fixed_B']['x']).T
y=np.array(V['fixed_B']['y'])[:,2,:].T
fig,axes=plt.subplots(1,3,figsize=(9.3,3.2),gridspec_kw={'width_ratios':[1.2,1,1]})
for ax,array,title,labels in zip(axes,[a,x,y],
 ['目标矩阵 $a_{it}$','固定分组矩阵 $x_{ig}$','第3轮启用矩阵 $y_{i3g}$'],
 [['轮1（重要）','轮2（重要）','轮3（近似）','轮4（近似）'],['组1','组2'],['组1','组2']]):
    ax.imshow(array,cmap='Blues',vmin=0,vmax=1,aspect='equal')
    ax.set_xticks(range(8),range(1,9));ax.set_yticks(range(len(array)),labels)
    ax.set_xlabel('资源编号 $i$',fontsize=11);ax.set_title(title,pad=11,fontsize=12)
    ax.tick_params(labelsize=11)
    ax.set_xticks(np.arange(-.5,8,1),minor=True)
    ax.set_yticks(np.arange(-.5,len(array),1),minor=True)
    ax.grid(which='minor',color='white',linewidth=1.3)
    ax.tick_params(which='minor',bottom=False,left=False)
    for row,col in np.ndindex(array.shape):
        ax.text(col,row,str(array[row,col]),ha='center',va='center',
                color='white' if array[row,col] else '#333333',fontsize=11)
    for s in ax.spines.values():s.set_visible(False)
fig.subplots_adjust(wspace=.45,bottom=.19,top=.84,left=.09,right=.99)
save(fig,'variables_example')

fig,axes=plt.subplots(1,2,figsize=(9.7,3.2))
for ax,ids,title,color in [(axes[0],[1,4],'距离0.6：允许同组','#286B9F'),
                           (axes[1],[1,8],'距离约0.7211：禁止同组','#B53232')]:
    coords=[D['coordinates'][str(i)] for i in ids]
    xx,yy=zip(*coords)
    ax.plot(xx,yy,color=color,linestyle='--',linewidth=1.8)
    ax.scatter(xx,yy,color=color,s=150,zorder=3)
    for i,(px,py) in zip(ids,coords):
        ax.text(px,py,str(i),ha='center',va='center',color='white',fontsize=9)
    ax.set_title(title,pad=10);ax.set_xlim(-.10,.70);ax.set_ylim(-.10,.50)
    ax.set_xticks([0,.2,.4,.6]);ax.set_yticks([0,.2,.4]);ax.grid(alpha=.18)
    ax.set_xlabel('横坐标');ax.set_aspect('equal')
axes[0].set_ylabel('纵坐标')
fig.subplots_adjust(left=.08,right=.99,bottom=.21,top=.85,wspace=.23)
save(fig,'distance_constraint')

fig,ax=plt.subplots(figsize=(9.3,1.25));ax.set_xlim(0,12);ax.set_ylim(.32,1.68);ax.axis('off')
steps=[('明确输入','坐标与任务'),('定义变量','分组与逐轮启用'),
       ('建立模型','约束与遗漏目标'),('核对一致性','检查与小例穷举')]
for k,(title,sub) in enumerate(steps):
    xx=k*3+.08
    box=FancyBboxPatch((xx,.48),2.55,1.05,boxstyle='round,pad=0.04,rounding_size=0.08',
                       facecolor='#F2F5F8',edgecolor='#586A7D',linewidth=1)
    ax.add_patch(box);ax.text(xx+1.275,1.18,title,ha='center',va='center',fontsize=14)
    ax.text(xx+1.275,.82,sub,ha='center',va='center',fontsize=11)
    if k<3:ax.add_patch(FancyArrowPatch((xx+2.6,1.0),(xx+2.93,1.0),
                        arrowstyle='-|>',mutation_scale=12,color='#586A7D'))
save(fig,'modeling_flow')
print('Three model figures generated from the checked constructed example.')
