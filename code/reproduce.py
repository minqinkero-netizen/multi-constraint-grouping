"""Copy necessary code and inputs to a new directory, then rerun there."""
from pathlib import Path
import shutil,argparse,subprocess,sys,json
ROOT=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--part',choices=['all','main','extra','scenarios'],default='all');a=ap.parse_args();out=Path(a.out).resolve()
    if out.exists():raise SystemExit('Output directory already exists; choose a new name.')
    out.mkdir(parents=True)
    for p in ROOT.glob('*.py'):shutil.copyfile(p,out/p.name)
    for name in ['protocol.json','analysis_plan.json','scheduling_resume.json','requirements.txt']:
        shutil.copyfile(ROOT/name,out/name)
    shutil.copytree(ROOT/'solutions',out/'solutions')
    (out/'data').mkdir();shutil.copyfile(ROOT/'data/input_manifest.json',out/'data/input_manifest.json')
    for rec in json.loads((ROOT/'data/input_manifest.json').read_text()):
        (out/'data'/rec['name']).mkdir();shutil.copyfile(ROOT/'data'/rec['name']/'witness.json',out/'data'/rec['name']/'witness.json')
    jobs={'main':['run_study.py'],'extra':['run_extra.py','run'],'scenarios':['run_scenarios.py']}
    for part in ['main','extra','scenarios'] if a.part=='all' else [a.part]:
        subprocess.run([sys.executable,*jobs[part]],cwd=out,check=True)
    if a.part=='all':subprocess.run([sys.executable,'analyze_study.py'],cwd=out,check=True)
    print('New results:',out)
if __name__=='__main__':main()
