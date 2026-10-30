"""Exact explanatory diagrams; no generated raster content or inferred data."""
from pathlib import Path
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch,Rectangle
from matplotlib import font_manager
ROOT=Path(__file__).resolve().parent;PAPER=ROOT.parent/'paper';OUT=ROOT/'figures'
from plot_style import configure
configure(plt)
plt.rcParams.update({'font.size':11})
C=['#286b9f','#ae5723'];labels=np.array([0,0,1,1,0,0,1,1]);points=np.array([[0,0],[.2,0],[.4,0],[.6,0],[0,.4],[.2,.4],[.4,.4],[.6,.4]])

def save(fig,name):fig.savefig(OUT/(name+'.png'),dpi=220,bbox_inches='tight');plt.close(fig)

def variables():
 fig=plt.figure(figsize=(8.6,8.2));gs=fig.add_gridspec(4,2,height_ratios=[2.25,1.8,1.1,1.1],width_ratios=[1,1.45],hspace=.85,wspace=.5)
 ax=fig.add_subplot(gs[0,0]);ax.set_title('方案B：资源点与所属组',fontsize=12)
 for i,(x,y) in enumerate(points):
  ax.scatter(x,y,s=160,color=C[labels[i]],zorder=3);ax.text(x,y,str(i+1),color='white',ha='center',va='center',fontsize=11)
  if i in [0,2]:ax.scatter(x,y,s=245,facecolors='none',edgecolors='#bb3030',linewidths=1.5,zorder=4)
 ax.set(xlim=(-.10,.7),ylim=(-.08,.5),xticks=[0,.2,.4,.6],yticks=[0,.4]);ax.set_aspect('equal');ax.grid(alpha=.15)
 ax=fig.add_subplot(gs[0,1]);ax.axis('off');ax.set_title('每个资源点对应同编号的矩阵列',fontsize=12)
 for i in range(8):
  x=(i+.5)/8;ax.scatter(x,.65,s=160,color=C[labels[i]],transform=ax.transAxes);ax.text(x,.65,str(i+1),ha='center',va='center',color='white',transform=ax.transAxes)
  ax.annotate('',xy=(x,.27),xytext=(x,.5),xycoords='axes fraction',arrowprops=dict(arrowstyle='->',lw=1,color=C[labels[i]]));ax.text(x,.12,str(i+1),ha='center',transform=ax.transAxes)
 ax.text(.5,-.13,'资源编号 = 下方矩阵列号',ha='center',transform=ax.transAxes,fontsize=11)
 a=np.zeros((4,8),int)
 for t,ids in enumerate([[1,8],[2,7],[1,3],[5,7]]):a[t,np.array(ids)-1]=1
 x=np.eye(2,dtype=int)[labels].T;y=np.zeros((2,8),int);y[0,0]=y[1,2]=1
 for k,(arr,title,rows) in enumerate([(a,'目标矩阵：这一轮要求哪些资源',['轮1 重要','轮2 重要','轮3 近似','轮4 近似']),(x,'分组矩阵：每个资源由谁负责',['管理者1','管理者2']),(y,'第3轮启用矩阵：谁实际启用哪个资源',['管理者1','管理者2'])],1):
  ax=fig.add_subplot(gs[k,:]);ax.set_title(title,loc='left',fontsize=12,pad=16)
  for r in range(arr.shape[0]):
   for i in range(8):
    color=(C[labels[i]] if k>=2 else '#356e9b') if arr[r,i] else '#f1f3f5'
    ax.add_patch(Rectangle((i-.49,r-.47),.98,.94,facecolor=color,edgecolor='white'))
    ax.text(i,r,str(arr[r,i]),ha='center',va='center',color='white' if arr[r,i] else '#555',fontsize=12)
  ax.set(xlim=(-.5,7.5),ylim=(arr.shape[0]-.5,-.9),xticks=range(8),yticks=range(arr.shape[0]),yticklabels=rows)
  ax.set_xticklabels([str(i+1) for i in range(8)])
  for tick,i in zip(ax.get_xticklabels(),range(8)):tick.set_color(C[labels[i]]);tick.set_fontweight('bold')
  ax.tick_params(length=0);[sp.set_visible(False) for sp in ax.spines.values()]
  if k==3:ax.set_xlabel('资源编号（每个资源始终对应同一列）')
 save(fig,'variables_example')

def box(ax,xy,w,h,text,face='#f2f5f8'):
 x,y=xy;ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.035',facecolor=face,edgecolor='#66788a',lw=1));ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=12)
def arrow(ax,a,b):ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=13,lw=1.1,color='#526579'))

def routes():
 fig,ax=plt.subplots(figsize=(9.4,4));ax.axis('off');ax.set(xlim=(0,10),ylim=(0,4))
 box(ax,(.1,1.48),1.5,1,'P1\n完整模型');box(ax,(2.05,1.48),1.65,1,'P2\n精简整数模型');arrow(ax,(1.65,1.98),(2.0,1.98))
 box(ax,(4.25,2.85),2.15,.8,'整数规划求解');box(ax,(4.25,1.35),2.15,.8,'LP求解＋取整修复');arrow(ax,(3.75,2.2),(4.2,3.2));arrow(ax,(3.75,1.8),(4.2,1.75))
 box(ax,(7.1,2.07),2.65,.85,'检查合格的整数分组');arrow(ax,(6.45,3.2),(7.1,2.65));arrow(ax,(6.45,1.75),(7.1,2.35))
 box(ax,(7.1,.45),2.65,.85,'逐轮调用与遗漏清单');arrow(ax,(8.425,2.02),(8.425,1.35))
 ax.text(5.2,.55,'未取得合格分组：\n记录失败与状态',ha='center',fontsize=11,color='#985436')
 save(fig,'reduction_route')
 fig,ax=plt.subplots(figsize=(9.4,2.7));ax.axis('off');ax.set(xlim=(0,10),ylim=(0,3))
 steps=[('整数分组','检查容量、距离\n与重要轮次'),('本轮候选','负责名单与目标\n取交集'),('实际调用','选编号最小者\n无目标时闲置'),('结果输出','完成与遗漏清单\n附检查报告')]
 for i,(a,b) in enumerate(steps):
  box(ax,(i*2.5+.06,1.1),2.18,1.05,a+'\n'+b)
  if i<3:arrow(ax,(i*2.5+2.28,1.62),((i+1)*2.5+.02,1.62))
 save(fig,'recovery_flow')

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--paper');args=parser.parse_args()
 if args.paper:OUT=Path(args.paper)/'figures'
 OUT.mkdir(parents=True,exist_ok=True);variables();routes();print('model and route diagrams generated')
