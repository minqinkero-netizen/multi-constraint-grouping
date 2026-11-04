"""Resume only the thirteen audited main tasks; pause for a saved checkpoint after each."""
from pathlib import Path
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import zipfile

BASE = Path(__file__).resolve().parent
ROOT = BASE / "recovery_20261102"
CODE = ROOT / "code"
CONTROL = BASE / "controller"
CHECKPOINTS = BASE / "checkpoints"
CONTROL.mkdir(exist_ok=True)
(CONTROL / "acks").mkdir(exist_ok=True)
CHECKPOINTS.mkdir(exist_ok=True)
sys.dont_write_bytecode = True
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
dependencies = ROOT / "runtime_dependencies"
if not dependencies.exists():
    shutil.copytree(Path('/workspace/scratch/3cb61f3de35c/revision_20261031/runtime_dependencies'),
                    dependencies, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
os.environ["PYTHONPATH"] = str(dependencies)
sys.path[:0] = [str(CODE), str(dependencies)]
import highspy
import numpy as np
import scipy
from benchmark import execute, dump

if hasattr(os, "sched_setaffinity"):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()


protocol = read(CODE / "protocol.json")
baseline = read(ROOT / "audit/preflight_uniqueness.json")
baseline_audit = read(ROOT / "audit/recovery_audit.json")
manifest = read(CODE / "data/input_manifest.json")
methods = protocol["main_methods"]
core_files = ["benchmark.py", "solver_backend.py", "round_repair.py", "grouping_core.py"]
expected_impl = baseline_audit["implementation_sha256"]
expected_protocol = baseline_audit["protocol_sha256"]
tasks = baseline_audit["missing_or_interrupted"]
assert len(tasks) == 13 and Counter(t["method"] for t in tasks) == {"MIP": 12, "LPR": 1}
assert highspy.Highs().version() == "1.13.1"
assert (sys.version_info.major, sys.version_info.minor) == (3, 12)
assert np.__version__ == "2.3.5" and scipy.__version__ == "1.17.0"
assert len({(x['instance'], x['method']) for x in tasks}) == 13
tasks.sort(key=lambda t: (int(t["instance"].split('_')[1]), t["instance"], t["method"]))
dump(ROOT / "orchestration/resume_tasks.json", tasks)
dump(ROOT / "orchestration/resume_environment.json", {
    "started_at": now(), "python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
    "highspy": highspy.Highs().version(), "platform": platform.platform(), "workers": 1,
    "execution_cpu": sorted(os.sched_getaffinity(0)), "solver_threads": 1,
    "main_budget_seconds": 600, "exit_reserve_seconds": 30,
    "core_unchanged": True, "supplemental_execution_authorized_in_this_controller": False,
    "public_upload_authorized": False,
})
for name in ["CHECKPOINT_SHA256.json", "snapshot_manifest.json"]:
    path = ROOT / name
    if path.exists() and not (ROOT / ("baseline_" + name)).exists():
        path.rename(ROOT / ("baseline_" + name))
archive = ROOT / "orchestration/original_aggregate_71.json"
if not archive.exists():
    shutil.copyfile(CODE / "data/results.json", archive)
for task in tasks:
    path = CODE / task["path"].removeprefix("code/")
    if path.exists() and "total_seconds" not in read(path):
        target = ROOT / "orchestration/interrupted_before_resume" / task["instance"] / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)


def verify_frozen():
    digest = hashlib.sha256("".join(sha(CODE / name) for name in core_files).encode()).hexdigest()
    assert digest == expected_impl and sha(CODE / "protocol.json") == expected_protocol
    assert all(sha(ROOT / row["path"]) == row["sha256"] for row in baseline["baseline_records"])


def rebuild():
    verify_frozen()
    cases, flat = [], []
    for source in manifest:
        row = {k: source[k] for k in ['name', 'config', 'family', 'replicate', 'seed', 'input']}
        row['method_order'] = source.get('method_order', methods)
        row['results'] = {}
        for method in methods:
            path = CODE / "data" / source['name'] / (method + '.json')
            if path.exists() and 'total_seconds' in read(path):
                result = read(path)
                row['results'][method] = result
                flat.append(dict(instance=source['name'], method=method, feasible=result['feasible'],
                                 L=result['L'], H=result['H'], status=result['status'],
                                 total_seconds=result['total_seconds'], seed=result['seed'],
                                 budget_seconds=600, watchdog_timeout=result['watchdog_timeout']))
        dump(CODE / 'data' / source['name'] / 'record.json', row)
        cases.append(row)
    p = read(CODE / 'data/protocol.json')
    p['recovery_resume'] = read(ROOT / 'orchestration/resume_environment.json')
    complete = len(flat) == 90
    dump(CODE / 'data/protocol.json', p)
    dump(CODE / 'data/results.json', dict(protocol=p, instances=cases, complete=complete))
    proc = subprocess.run([sys.executable, '-B', str(ROOT / 'audit_recovery.py')],
                          capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError('Independent audit failed: ' + proc.stdout + proc.stderr)
    audit = read(ROOT / 'audit/recovery_audit.json')
    assert audit['verified_completed_runs'] == len(flat) and not audit['audit_errors']
    summary = {'updated_at': now(), 'expected_runs': 90, 'completed_runs': len(flat),
               'remaining_runs': 90 - len(flat), 'complete': complete,
               'baseline_77_unchanged': True, 'duplicate_run_count': 0, 'methods': {}}
    for method in methods:
        rows = [r for r in flat if r['method'] == method]
        feasible = [r for r in rows if r['feasible']]
        times = [r['total_seconds'] for r in rows]
        values = [r['L'] for r in feasible]
        summary['methods'][method] = dict(completed=len(rows), feasible=len(feasible),
            mean_seconds=statistics.mean(times) if times else None,
            feasible_mean_L=statistics.mean(values) if values else None,
            status_counts=dict(Counter(r['status'] for r in rows)))
    dump(CODE / 'data/summary.json', summary)
    dump(CODE / 'data/audit.json', audit)
    target = CODE / 'data/results_table.csv'
    tmp = target.with_suffix('.csv.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    tmp.replace(target)
    dump(ROOT / 'CURRENT_STATUS.json', summary)
    text = '# 主实验续跑状态\n\n'
    text += f"更新时间：{summary['updated_at']}\n\n主实验已完成并通过独立核验 {len(flat)}/90 次；剩余 {90-len(flat)} 次。原77份结果保持逐字节不变。\n\n"
    text += '本检查点只包含主实验续跑；尚未启动补充实验，没有公开上传GitHub，没有修改main或论文正式版本。\n\n'
    text += '当前汇总：code/data/results.json、summary.json、results_table.csv、audit.json。基线快照的旧汇总保留在orchestration/original_aggregate_71.json。\n\n'
    text += '本批独立核验已通过；下一次运行须在本批检查点保存成功后开始。\n'
    (ROOT / 'CURRENT_STATUS.md').write_text(text, encoding='utf-8')
    return summary


def checkpoint(number, summary, task, result):
    completed = summary['completed_runs']
    filename = f'challenge_cup_main_checkpoint_{completed}of90.zip'
    path = CHECKPOINTS / filename
    assert not path.exists()
    entries = [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': sha(p)}
               for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name != 'CHECKPOINT_SHA256.json'
               and '__pycache__' not in p.parts]
    dump(ROOT / 'CHECKPOINT_SHA256.json', {'created_at': now(), 'completed_runs': completed, 'files': entries})
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for item in entries:
            z.write(ROOT / item['path'], 'recovery_20261102/' + item['path'])
        z.write(ROOT / 'CHECKPOINT_SHA256.json', 'recovery_20261102/CHECKPOINT_SHA256.json')
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read('recovery_20261102/' + item['path'])).hexdigest() == item['sha256'] for item in entries)
    state = dict(phase='awaiting_checkpoint_save', batch=number, total_batches=13,
                 completed_runs=completed, remaining_runs=90-completed, task=task,
                 result={k: result.get(k) for k in ['status','feasible','L','H','total_seconds','solver_status','watchdog_timeout']},
                 archive=str(path), archive_sha256=sha(path), archive_bytes=path.stat().st_size,
                 ready_at=now(), pid=os.getpid())
    dump(CONTROL / 'status.json', state)
    print('CHECKPOINT_READY ' + json.dumps(state, ensure_ascii=False), flush=True)
    ack = CONTROL / 'acks' / f'{number:03d}.json'
    while not ack.exists():
        time.sleep(2)
    saved = read(ack)
    assert saved['sha256'] == state['archive_sha256'] and saved['status'] == 'succeeded'
    assert saved['library_file_id'].startswith('libfile_')
    history_path = ROOT / 'orchestration/checkpoint_history.json'
    history = read(history_path) if history_path.exists() else []
    history.append({**state, 'saved': saved})
    dump(history_path, history)


def main():
    summary = rebuild()
    assert summary['completed_runs'] == 77
    for number, task in enumerate(tasks, 1):
        verify_frozen()
        folder = CODE / 'data' / task['instance']
        fp = folder / (task['method'] + '.json')
        assert not fp.exists(), 'Do not repeat an existing completed or partial attempt'
        dump(CONTROL / 'status.json', dict(phase='running', batch=number, total_batches=13,
             completed_runs=77+number-1, remaining_runs=14-number, task=task,
             started_at=now(), started_epoch=time.time(), pid=os.getpid()))
        print('START', number, task['instance'], task['method'], 'seed', task['algorithm_seed'], flush=True)
        result = execute(read(folder/'instance.json'), task['method'], 600, task['algorithm_seed'], folder)
        result.update(run_key=dict(input_sha256=sha(folder/'instance.json'),
                                   implementation_sha256=expected_impl, protocol_sha256=expected_protocol),
                      execution_cpu=sorted(os.sched_getaffinity(0)))
        dump(fp, result)
        summary = rebuild()
        assert summary['completed_runs'] == 77+number
        print('END', number, task['instance'], task['method'], result['status'], result.get('L'), round(result['total_seconds'],3), flush=True)
        checkpoint(number, summary, task, result)
    summary = rebuild()
    assert summary['complete'] and summary['completed_runs'] == 90
    dump(CONTROL/'status.json', dict(phase='complete', completed_runs=90, remaining_runs=0,
                                   total_batches=13, completed_at=now(), summary=summary,
                                   supplemental_started=False, public_uploads=0))
    print('MAIN_COMPLETE_90_OF_90', flush=True)


if __name__ == '__main__':
    if os.name == 'posix':
        import fcntl
        lock = (CONTROL/'controller.lock').open('w')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        main()
    except Exception as exc:
        dump(CONTROL/'failure.json', dict(time=now(), error=repr(exc)))
        raise
