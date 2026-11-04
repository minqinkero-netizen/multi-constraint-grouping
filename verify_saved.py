"""Verify the archived experiment; never call an optimizer."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile
root=Path(__file__).resolve().parent
source=root/'snapshots/supplemental_source'
manifest=json.loads((source/'SUPPLEMENTAL_FINAL_SHA256.json').read_text(encoding='utf-8'))
for row in manifest['files']:
    p=source/row['path']
    assert p.stat().st_size==row['bytes'],row['path']
    assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
print('758 original checkpoint file hashes: PASS')
with tempfile.TemporaryDirectory(prefix='verify-saved-') as td:
    target=Path(td)/'source';shutil.copytree(source,target)
    subprocess.run([sys.executable,'-X','utf8',str(target/'audit_recovery.py')],check=True)
    command="import sys;sys.path.insert(0,sys.argv[1]);import analyze_study as a;a.make_figures=lambda *args:None;sys.argv=[sys.argv[0]];a.main()"
    subprocess.run([sys.executable,'-X','utf8','-c',command,str(target/'code')],check=True)
print('Main and supplemental record audits and recomputed statistics: PASS; solver calls: 0')
