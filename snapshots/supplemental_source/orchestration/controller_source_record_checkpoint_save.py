from pathlib import Path
import json,sys,hashlib,datetime
base=Path(__file__).resolve().parent
number=int(sys.argv[1]);assert 1<=number<=13
saved=json.load(sys.stdin)
state=json.loads((base/'controller/status.json').read_text())
assert state['phase']=='awaiting_checkpoint_save' and state['batch']==number
assert saved['sha256']==state['archive_sha256']
assert hashlib.sha256(Path(state['archive']).read_bytes()).hexdigest()==saved['sha256']
assert saved['status']=='succeeded' and saved['library_file_id'].startswith('libfile_')
saved['saved_at']=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
path=base/'controller/acks'/f'{number:03d}.json';assert not path.exists()
temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)
print(json.dumps({'checkpoint_acknowledged':number,'completed_runs':state['completed_runs'],'library_file_id':saved['library_file_id']}))
