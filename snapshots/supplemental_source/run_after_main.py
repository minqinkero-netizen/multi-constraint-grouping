"""Queue supplemental measurements after the main batch, not alongside it."""
from pathlib import Path
import json,time,subprocess,sys
root=Path(__file__).resolve().parent
while True:
    p=root/'code/data/results.json'
    if p.exists() and json.loads(p.read_text()).get('complete'):break
    time.sleep(10)
for script,args,name in [('run_extra.py',['run'],'extra_execution'),('run_scenarios.py',[],'scenario_execution')]:
    with (root/f'qa/{name}.log').open('w') as log:
        subprocess.run([sys.executable,str(root/'code'/script),*args],stdout=log,stderr=subprocess.STDOUT,check=True)
print('ALL BATCHES COMPLETE',flush=True)
