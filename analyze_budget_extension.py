"""Report the whole post-main C/64 block, including every failure."""
from pathlib import Path
import json
import numpy as np
from solve_and_restore import restore

ROOT=Path(__file__).resolve().parent;EXP=ROOT/'experiments'

def main():
    old=json.loads((EXP/'results.json').read_text());new=json.loads((EXP/'extension_results.json').read_text())
    assert len(new['cases'])==4 and all(len(c['results'])==4 for c in new['cases'])
    main_cases={c['name']:c for c in old['cases'] if c['family']=='C' and c['n']==64}
    summary={};lines=[]
    for method in ['G','LS','P1','P2']:
        r=[c['results'][method] for c in new['cases']]
        before=[c['results'][method] for c in main_cases.values()]
        for c in new['cases']:
            a=c['results'][method];d=main_cases[c['name']]['instance']
            if a['feasible']:
                _,_,_,audit=restore(d,np.eye(d['m'],dtype=int)[a['labels']])
                assert audit['feasible'] and audit['L']==a['L']
        s={'feasible_3':sum(v['feasible'] for v in before),'feasible_10':sum(v['feasible'] for v in r),
           'own_certified_10':sum(v['certified_by_own_bounds'] for v in r),
           'max_seconds_10':max(v['total_seconds'] for v in r),
           'L_values_10':[c['results'][method]['L'] for c in new['cases']]}
        summary[method]=s
        lines.append(f"{method} & {s['feasible_3']}/4 & {s['feasible_10']}/4 & {s['own_certified_10']}/4 & {s['max_seconds_10']:.3f} "+chr(92)*2)
    (EXP/'extension_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (EXP/'table_extension.tex').write_text('\n'.join(lines)+'\n')
    count_text='；'.join(f"{a}的可行数由{summary[a]['feasible_3']}/4变为{summary[a]['feasible_10']}/4" for a in ['G','LS','P1','P2'])
    no_gain=all(summary[a]['feasible_3']==summary[a]['feasible_10'] for a in summary)
    text=("预算增加后，"+count_text+"。未解决的输入也仍有独立保存的可行见证。"
          +("这一困难块的可行方案产出数没有提高。" if no_gain else "不同方法对预算增加的响应存在差异。")
          +"不能把未找到方案解释为不可行。"
          f"10秒设置下，P1最长实际耗时为{summary['P1']['max_seconds_10']:.3f}秒，P2为{summary['P2']['max_seconds_10']:.3f}秒，"
          "再次说明这里不能作严格等时限的速度保证。追加结果没有支持当前整数流程可直接处理该困难块；后续需改进可行初值、搜索或资源配置。\n")
    (EXP/'extension_interpretation.tex').write_text(text)
    # Reuse the same publication font setup as the main scientific figures.
    import make_experiment_figures as figs
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7.4,3.3));x=np.arange(4)
    for off,key,label,color in [(-.18,'feasible_3','3秒软预算','#5C799B'),(.18,'feasible_10','10秒软预算','#268374')]:
        vals=[summary[a][key] for a in ['G','LS','P1','P2']]
        ax.bar(x+off,vals,width=.34,color=color,label=label)
        for i,v in enumerate(vals):ax.text(i+off,v+.08,str(v),ha='center',fontsize=10)
    ax.set_xticks(x,['G','LS','P1-MIP','P2-MIP']);ax.set_yticks([0,1,2,3,4]);ax.set(ylim=(0,4.6),ylabel='可行实例数（共4例）',title='C类64资源：两种预算下的可行方案产出')
    ax.legend(frameon=False);figs.save(fig,'experiment_budget.png')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
