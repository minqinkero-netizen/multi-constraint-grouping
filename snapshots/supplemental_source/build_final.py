"""Compile verified source and package precisely the files needed by Overleaf."""
from pathlib import Path
import argparse,subprocess,shutil,time,re,json,hashlib,zipfile
import fitz
root=Path(__file__).resolve().parent;paper=root/'paper';out=root/'deliverables';out.mkdir(exist_ok=True);qa=root/'qa';qa.mkdir(exist_ok=True)
ap=argparse.ArgumentParser();ap.add_argument('--commit',required=True);args=ap.parse_args();sha=args.commit;assert re.fullmatch('[0-9a-f]{40}',sha)
summary=json.loads((root/'code/data/summary.json').read_text());assert summary['runs']==90 and summary['inputs']==18 and summary['audit_success']
assert summary['extra']['inputs']==20 and summary['extra']['postprocess_records']==180 and summary['extra']['radius_runs']==36
assert json.loads((root/'code/scenario_data/audit.json').read_text())['all_consistent']
repo='https://github.com/minqinkero-netizen/multi-constraint-grouping/tree/'+sha+'/revision_20261031'
(paper/'generated/repository.tex').write_text('\\begin{quote}\\small\n\\href{'+repo+'}{\\texttt{'+sha+'}}\n\\end{quote}\n该链接直接打开本稿的程序与数据目录。版本日期：2026年10月31日。\n')
(paper/'README.md').write_text('# LaTeX source\n\n在Overleaf中新建项目并上传整个ZIP，选择XeLaTeX编译器，以main.tex为主文件。字体及插图已随包提供。\n\n固定代码与数据版本：'+repo+'\n\n作者：闵芹、宋沁曦、陈紫菡（排序不分先后）；指导教师：肖亮海。\n')
job='final_'+str(int(time.time()))
for i in range(4):
    with (qa/f'{job}_{i}.txt').open('wb') as log:
        subprocess.run(['xelatex','-no-pdf','-interaction=nonstopmode','-halt-on-error','-jobname='+job,'main.tex'],cwd=paper,stdout=log,stderr=subprocess.STDOUT,check=True)
    logtext=(paper/(job+'.log')).read_text(errors='replace')
    if i>=2 and 'Label(s) may have changed' not in logtext and 'Rerun to get' not in logtext:break
for term in ['Missing character:','Overfull \\hbox','Overfull \\vbox','There were undefined references','Citation `','Reference `']:
    assert term not in logtext,term
buildpdf=qa/(job+'.pdf')
with (qa/(job+'_pdf.txt')).open('wb') as log:subprocess.run(['xdvipdfmx','-o',str(buildpdf),job+'.xdv'],cwd=paper,stdout=log,stderr=subprocess.STDOUT,check=True)
assert b'%%EOF' in buildpdf.read_bytes()[-100:]
finalpdf=out/'paper_body_with_appendices.pdf';shutil.copyfile(buildpdf,finalpdf)
doc=fitz.open(finalpdf);txt='\n'.join(p.get_text() for p in doc)
for name in ['肖亮海','闵芹','宋沁曦','陈紫菡','致谢','目录',sha]:assert name in txt,name
for stale in ['72次比较','四种方法的比较结果','linprog(method','80资源组首先单独完成']:assert stale not in txt,stale
uris={link['uri'] for page in doc for link in page.get_links() if 'uri' in link};assert repo in uris
assert 'https://www.chaspark.com/#/questions/1144431169898635264?sub=1145403943946309633' in uris
stage=root/'source_package'
if stage.exists():shutil.rmtree(stage)
stage.mkdir();used_tex=set();used_fig=set()
def collect(rel):
    if rel in used_tex:return
    used_tex.add(rel);content=(paper/rel).read_text();dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(paper/rel,dest)
    for name in re.findall(r'\\input\{([^}]+)\}',content):collect(name if name.endswith('.tex') else name+'.tex')
    used_fig.update(re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',content))
collect('main.tex')
for name in used_fig:
    dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(paper/name,dest)
shutil.copytree(paper/'fonts',stage/'fonts')
for name in ['README.md','REVISION_NOTES.md','team_information.json']:
    if (paper/name).exists():shutil.copyfile(paper/name,stage/name)
manifest=dict(version='2026-10-31',git_commit=sha,repository=repo,pdf_pages=len(doc),main_inputs=18,main_runs=90,additional_inputs=20,additional_LP_setups=20,postprocess_records=180,postprocess_runs=summary['extra']['postprocess_runs'],radius_base_inputs=6,radius_runs=36,small_runs=24,main_methods=['G','LS','SLS','MIP','LPR'],all_accepted_solutions_reaudited=True,source_figures=sorted(used_fig),tex_files=sorted(used_tex))
(stage/'revision_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
hashes=[hashlib.sha256(fp.read_bytes()).hexdigest()+'  '+fp.relative_to(stage).as_posix() for fp in sorted(stage.rglob('*')) if fp.is_file()]
(stage/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n')
zipname=out/'paper_body_appendices_latex.zip'
with zipfile.ZipFile(zipname,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for fp in sorted(stage.rglob('*')):
        if fp.is_file():z.write(fp,fp.relative_to(stage).as_posix())
with zipfile.ZipFile(zipname) as z:assert z.testzip() is None and 'main.tex' in z.namelist()
validation=dict(manifest=manifest,pdf_bytes=finalpdf.stat().st_size,zip_bytes=zipname.stat().st_size,pdf_sha256=hashlib.sha256(finalpdf.read_bytes()).hexdigest(),zip_sha256=hashlib.sha256(zipname.read_bytes()).hexdigest(),unresolved_references=False,overfull=False,missing_glyphs=False)
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n');print(json.dumps(validation,ensure_ascii=False,indent=2))
