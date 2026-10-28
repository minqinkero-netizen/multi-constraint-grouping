"""Exact diagrams and plots from saved recovery output; no invented data."""
from pathlib import Path
import csv
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib import font_manager
from matplotlib.colors import ListedColormap

ROOT = Path(__file__).resolve().parent
local_font = Path('/usr/local/share/fonts/NotoSansCJKsc-Regular.otf')
if local_font.is_file():
    font_manager.fontManager.addfont(str(local_font))
font_candidates = ['Noto Sans CJK SC', 'Microsoft YaHei', 'SimHei', 'SimSun', 'Source Han Sans SC']
for font_name in font_candidates:
    try:
        font_manager.findfont(font_manager.FontProperties(family=[font_name]), fallback_to_default=False)
        break
    except ValueError:
        continue
else:
    raise RuntimeError('Install a Chinese font such as Noto Sans CJK SC to regenerate figures')
plt.rcParams.update({'font.family': font_name, 'font.size': 11,
                     'axes.unicode_minus': False, 'savefig.dpi': 220})
BLUE, GREEN, ORANGE, RED, GRAY = '#275D8C', '#268374', '#D68D32', '#AE4B43', '#5B6470'
DATA = json.loads((ROOT/'recovery_checks.json').read_text())
FIG = ROOT/'figures'


def save(fig, name):
    fig.savefig(FIG/name, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def flow():
    fig, ax = plt.subplots(figsize=(9.1, 3.35))
    ax.set(xlim=(0, 10), ylim=(0, 5)); ax.axis('off')
    def box(x,y,w,h,title,body,color=BLUE):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.08',
                                   fc='#F5F8FB',ec=color,lw=1.2))
        ax.text(x+w/2,y+h*.69,title,ha='center',va='center',color=color,fontsize=12)
        ax.text(x+w/2,y+h*.29,body,ha='center',va='center',fontsize=10.2)
    def arrow(a,b):
        ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','lw':1.4,'color':GRAY})
    box(.15,3.25,2.8,1.25,'1  求解替代模型 P2','保存状态、整数候选、下界')
    box(3.65,3.25,2.7,1.25,'2  检查整数分组','唯一归属、容量、距离\n重要轮次相容性')
    box(7.1,3.25,2.7,1.25,'3  恢复逐轮调用','每组每轮选一个目标或闲置')
    box(7.1,.65,2.7,1.25,'4  独立检查原模型 P1','检查调用规则并重算遗漏量')
    box(3.65,.65,2.7,1.25,'5  输出可执行方案','分组表、调用表\n遗漏表、目标上下界',GREEN)
    arrow((3.04,3.88),(3.54,3.88)); arrow((6.44,3.88),(6.99,3.88))
    arrow((8.45,3.16),(8.45,2.02)); arrow((6.99,1.27),(6.46,1.27))
    ax.text(1.55,2.43,'无整数候选：报告未找到\n求解器判无解：单独报告',ha='center',va='center',color=RED,fontsize=10.7)
    ax.text(5.0,2.42,'任一检查失败：拒绝输出\n分数松弛解不能直接进入恢复',ha='center',va='center',color=RED,fontsize=10.7)
    save(fig,'recovery_flow.png')


def base_plot():
    base = DATA['cases'][0]['instance']
    ex = DATA['illustrated_partitions']['B']
    points = np.array(base['points']); x=np.array(ex['x']); y=np.array(ex['y'])
    labels=x.argmax(axis=1)
    fig, axes = plt.subplots(1,2,figsize=(9.2,3.9),gridspec_kw={'width_ratios':[1,1.17]})
    ax=axes[0]
    for g,color in enumerate([BLUE,GREEN]):
        ids=np.flatnonzero(labels==g); p=points[ids]
        ax.add_patch(Rectangle((p[:,0].min()-.045,p[:,1].min()-.055),
                               np.ptp(p[:,0])+.09,
                               np.ptp(p[:,1])+.11,fill=False,ec=color,lw=1.5,alpha=.65))
        ax.scatter(p[:,0],p[:,1],s=410,c=color,label=f'管理者{g+1}',zorder=3)
        for i in ids:ax.text(*points[i],str(i+1),ha='center',va='center',color='white',fontsize=12,zorder=4)
    ax.set(xlim=(-.09,.69),ylim=(-.11,.59),xlabel='横坐标',ylabel='纵坐标',title='固定归属：方案B')
    ax.set_aspect('equal'); ax.set_xticks([0,.2,.4,.6]); ax.set_yticks([0,.2,.4])
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.22),ncol=2,frameon=False,fontsize=10)
    ax=axes[1]
    matrix=np.zeros((4,8),int)
    for t in range(4):
        for i in range(8):
            if y[i,t,:].sum(): matrix[t,i]=labels[i]+1
    ax.imshow(matrix,cmap=ListedColormap(['#F1F4F7',BLUE,GREEN]),vmin=0,vmax=2,aspect='auto')
    for t in range(4):
        for i in range(8):
            ax.text(i,t,str(int(matrix[t,i]>0)),ha='center',va='center',
                    color='white' if matrix[t,i] else '#9DA7B0',fontsize=11)
    ax.set_xticks(range(8),range(1,9));ax.set_yticks(range(4),['第1轮 重要','第2轮 重要','第3轮 近似','第4轮 近似'])
    ax.set(xlabel='资源编号',title='恢复的实际调用（1为启用）')
    ax.set_xticks(np.arange(-.5,8,1),minor=True);ax.set_yticks(np.arange(-.5,4,1),minor=True)
    ax.grid(which='minor',color='white',lw=1.8);ax.tick_params(which='minor',bottom=False,left=False)
    fig.subplots_adjust(wspace=.44,bottom=.24)
    save(fig,'restored_base_solution.png')


def round32_plot():
    rec=DATA['round32_case']['result']['original_P1_audit']['round_records']
    t=np.arange(1,33)
    served=np.array([len(row['activated']) for row in rec])
    lost=np.array([row['omissions'] for row in rec])
    fig,ax=plt.subplots(figsize=(9.2,3.7))
    ax.bar(t[:16],served[:16],color=BLUE,label='实际完成：重要轮次',width=.74)
    ax.bar(t[16:],served[16:],color=GREEN,label='实际完成：近似轮次',width=.74)
    ax.bar(t,lost,bottom=served,color=ORANGE,label='目标遗漏：近似轮次',width=.74)
    ax.axvline(16.5,ls='--',color=GRAY,lw=1)
    ax.set(xlim=(.3,32.7),ylim=(0,15),xlabel='轮次',ylabel='目标调用次数',title='32轮合成算例：恢复后的逐轮完成与遗漏')
    ax.set_xticks([1,4,8,12,16,20,24,28,32]);ax.set_yticks([0,4,8,12])
    ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    ax.legend(loc='upper left',ncol=3,frameon=False,fontsize=9.6)
    ax.text(8.4,11.7,'16个重要轮次：50次目标调用全部完成',ha='center',fontsize=10,color=BLUE)
    save(fig,'round32_recovered.png')


def exports():
    folder=ROOT/'solutions';folder.mkdir(exist_ok=True)
    cases=DATA['cases']+[{'name':'round32','instance':DATA['round32_case']['instance'],
                         'result':DATA['round32_case']['result']}]
    for case in cases:
        name=case['name'];result=case['result']
        (folder/(name+'_input.json')).write_text(json.dumps(case['instance'],ensure_ascii=False,indent=2)+'\n')
        (folder/(name+'_solution.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        with (folder/(name+'_actions.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            fields=['round','type','manager','resource','omitted_resources']
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for r in result['original_P1_audit']['round_records']:
                for g,active in enumerate(r['by_manager']):
                    w.writerow({'round':r['round'],'type':'strict' if r['strict'] else 'approximate',
                                'manager':g+1,'resource':active[0] if active else '',
                                'omitted_resources':' '.join(map(str,r['missing'])) if g==0 else ''})


if __name__=='__main__':
    flow();base_plot();round32_plot();exports()
