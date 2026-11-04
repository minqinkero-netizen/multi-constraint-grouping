from pathlib import Path
import json,time
base=Path(__file__).resolve().parent
state=json.loads((base/'controller/status.json').read_text())
failure=base/'controller/failure.json'
if failure.exists():state['failure']=json.loads(failure.read_text())
if state['phase']=='running':
    state['elapsed_seconds']=round(time.time()-state['started_epoch'],1)
    state['budget_remaining_seconds']=round(max(0,600-state['elapsed_seconds']),1)
    path=base/'recovery_20261102/code/data'/state['task']['instance']/(state['task']['method']+'.json')
    if path.exists():
        try:
            r=json.loads(path.read_text())
            state['live_candidate']={k:r.get(k) for k in ['status','feasible','L','H','solver_status','worker_seconds']}
        except (OSError,json.JSONDecodeError):pass
print(json.dumps(state,ensure_ascii=False))
