"""Stage audited source/results for a new immutable repository snapshot."""
from pathlib import Path
import json,shutil,hashlib
root=Path(__file__).resolve().parent;code=root/'code';pub=root/'publish';dest=pub/'revision_20261031'
main=json.loads((code/'data/results.json').read_text());extra=json.loads((code/'extra/results.json').read_text());assert main['complete'] and extra['complete']
assert json.loads((code/'data/audit.json').read_text())['all_consistent']
assert json.loads((code/'scenario_data/audit.json').read_text())['all_consistent']
if pub.exists():shutil.rmtree(pub)
dest.mkdir(parents=True)
for p in code.glob('*.py'):shutil.copyfile(p,dest/p.name)
for name in ['README.md','requirements.txt','protocol.json','analysis_plan.json','scheduling_resume.json']:shutil.copyfile(code/name,dest/name)
for name in ['scenario_data','figures']:shutil.copytree(code/name,dest/name)
(dest/'solutions').mkdir()
for name in ['base8','seed66','round32']:
    for suffix in ['input.json','solution.json','actions.csv']:
        p=code/f'solutions/{name}_{suffix}'
        if p.exists():shutil.copyfile(p,dest/'solutions'/p.name)
(dest/'data').mkdir()
for name in ['protocol.json','input_manifest.json','summary.json','audit.json','results_table.csv']:shutil.copyfile(code/'data'/name,dest/'data'/name)
idx=[]
for rec in main['instances']:
    name=rec['name'];folder=dest/'data'/name;folder.mkdir()
    for filename in ['instance.json','witness.json','G.json','LS.json','SLS.json','MIP.json','LPR.json']:shutil.copyfile(code/'data'/name/filename,folder/filename)
    item={k:v for k,v in rec.items() if k not in ['input','results']};idx.append(item)
    (folder/'record.json').write_text(json.dumps(item,ensure_ascii=False)+'\n')
(dest/'data/results.json').write_text(json.dumps(dict(protocol=main['protocol'],instances=idx,complete=True,records_in_files=True),ensure_ascii=False)+'\n')
(dest/'extra').mkdir();idx=[]
for name in ['protocol.json','summary.json','ablation_runs.csv','radius_runs.csv']:shutil.copyfile(code/'extra'/name,dest/'extra'/name)
for rec in extra['instances']:
    name=rec['name'];folder=dest/'extra'/name;folder.mkdir()
    for filename in ['instance.json','witness.json','lp.json']+[f'{v}_{k}.json' for v in ['LP-G','LP-N','UNI'] for k in [1,2,3]]:
        p=code/'extra'/name/filename
        if p.exists():shutil.copyfile(p,folder/filename)
    for scan in rec['radius_scan']:
        dirname=f"radius_{scan['factor']:.2f}";shutil.copytree(code/'extra'/name/dirname,folder/dirname)
    item={k:v for k,v in rec.items() if k not in ['input','lp','repeats','radius_scan']}
    item['repeats']=[{k:v for k,v in r.items() if k!='results'} for r in rec['repeats']]
    item['radius_scan']=[{k:v for k,v in r.items() if k!='results'} for r in rec['radius_scan']]
    (folder/'record.json').write_text(json.dumps(item,ensure_ascii=False)+'\n');idx.append(item)
(dest/'extra/results.json').write_text(json.dumps(dict(protocol=extra['protocol'],instances=idx,complete=True,records_in_files=True),ensure_ascii=False)+'\n')
orchestr=dest/'orchestration';orchestr.mkdir()
for archive in ['interrupted_attempts','interrupted_attempts_resume2','resume_20261102_partial']:
    if (root/'qa'/archive).exists():shutil.copytree(root/'qa'/archive,orchestr/archive)
for name in ['main_execution.log','main_resumed.log','main_resume2.log','main_actual_resume.log','extra_execution.log','scenario_execution.log']:
    p=root/'qa'/name
    if p.exists():shutil.copyfile(p,orchestr/name)
(orchestr/'README.md').write_text('多次中断留下的未完成检查点单独归档，不进入正式统计；相应任务完整重跑。已完成记录保留匹配的算法实现、协议与输入摘要。初期最多三个工作进程，恢复后一个工作进程串行执行；每个求解器均为单线程，方法及预算保持不变。时序与并发负载变化可能影响耗时。恢复说明见 scheduling_resume.json；补充实验在主实验后执行。\n')
shutil.copyfile(root/'new_root_README.md',pub/'README.md')
manifest=[]
for fp in sorted(pub.rglob('*')):
    if not fp.is_file():continue
    data=fp.read_bytes();sha=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
    manifest.append(dict(path=fp.relative_to(pub).as_posix(),source=str(fp),bytes=len(data),git_blob_sha=sha,binary=fp.suffix.lower() in ['.png','.jpg','.jpeg']))
(root/'publish_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('Staged',len(manifest),'files;',sum(x['bytes'] for x in manifest),'bytes')
