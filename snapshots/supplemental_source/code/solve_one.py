"""Solve one public input into a new directory; does not overwrite paper data."""
import argparse,json
from pathlib import Path
from benchmark import execute,METHODS
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--method',choices=METHODS,default='LPR');ap.add_argument('--budget',type=float,default=600);ap.add_argument('--seed',type=int,default=70001);ap.add_argument('--out',required=True);a=ap.parse_args()
    out=Path(a.out)
    if out.exists():raise SystemExit('Choose a new output directory to preserve existing records.')
    if a.budget<2:raise SystemExit('Use at least 2 seconds.')
    r=execute(json.loads(Path(a.input).read_text()),a.method,a.budget,a.seed,out)
    print(json.dumps({k:r.get(k) for k in ['method','feasible','L','H','status','total_seconds']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
