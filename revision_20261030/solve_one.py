"""Run a single published method with the same external watchdog as the study."""
from pathlib import Path
import argparse,json
from benchmark import execute,METHODS
from grouping_core import validate_input

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--method',choices=METHODS,default='LPR');ap.add_argument('--budget',type=float,default=600);ap.add_argument('--out',default='my_run');ap.add_argument('--seed',type=int,default=9001);a=ap.parse_args()
 if not 0<a.budget<=600:ap.error('budget must be in (0, 600] seconds')
 d=json.loads(Path(a.input).read_text(encoding='utf-8'));validate_input(d)
 work=Path(a.out).resolve()
 if (work/f'{a.method}.json').exists():ap.error('output already exists; choose a new --out directory')
 r=execute(d,a.method,a.budget,a.seed,work)
 print(json.dumps({k:r.get(k) for k in ['method','feasible','L','H','status','total_seconds','process_error']},ensure_ascii=False,indent=2))
 print('Full result:',work/f'{a.method}.json')
if __name__=='__main__':main()
