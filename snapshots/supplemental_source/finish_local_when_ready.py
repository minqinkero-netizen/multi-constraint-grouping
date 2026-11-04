"""Wait for recorded experiments, audit, regenerate figures, stage publication."""
from pathlib import Path
import json,subprocess,sys,time,shutil
root=Path(__file__).resolve().parent;code=root/'code'
while True:
    paths=[code/x/'results.json' for x in ['data','extra','scenario_data']]
    if all(p.exists() and json.loads(p.read_text()).get('complete') for p in paths):break
    time.sleep(10)
with (root/'qa/final_analysis.log').open('w') as log:
    subprocess.run([sys.executable,str(code/'analyze_study.py'),'--paper',str(root/'paper')],stdout=log,stderr=subprocess.STDOUT,check=True)
if (code/'figures').exists():shutil.rmtree(code/'figures')
shutil.copytree(root/'paper/figures',code/'figures')
subprocess.run([sys.executable,str(root/'prepare_publish.py')],check=True)
print('AUDIT AND PUBLICATION STAGE READY',flush=True)
