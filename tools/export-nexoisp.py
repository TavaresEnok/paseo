import pathlib,shutil,json,hashlib,tarfile,datetime,re,os
H=pathlib.Path('/home/enok'); OUT=pathlib.Path('/tmp/paseo-source-export');OUT.mkdir(exist_ok=True)
manifest=[]
def scrub(s):
 s=re.sub(r'(?i)(Environment=PASEO_ACCOUNT_ID=)[^\s]+',r'\1ACCOUNT_ID_RECONFIGURE',s)
 s=re.sub(r'[\w.+-]{1,64}@[\w.-]{1,128}\.[A-Za-z]{2,20}',lambda m: m[0] if m[0].endswith('@localhost') else 'account@example.invalid',s)
 return s
def put(src,dst,transform=False):
 src=pathlib.Path(src);target=OUT/dst;target.parent.mkdir(parents=True,exist_ok=True)
 raw=src.read_bytes()
 if transform:
  try:raw=scrub(raw.decode()).encode()
  except UnicodeDecodeError:pass
 target.write_bytes(raw);target.chmod(0o755 if src.stat().st_mode&0o111 else 0o644)
 manifest.append({'source':str(src),'path':str(dst),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'export_sha256':hashlib.sha256(raw).hexdigest(),'sanitized':raw!=src.read_bytes()})
def tree(src,dst):
 for p in pathlib.Path(src).rglob('*'):
  if not p.is_file() or p.is_symlink():continue
  rel=p.relative_to(src)
  if any(x in {'__pycache__','node_modules','.git','bin'} for x in rel.parts) or '.bak-' in p.name:continue
  if p.suffix in {'.pyc','.sqlite3','.gz','.br','.onnx'}:continue
  put(p,pathlib.Path(dst)/rel,not str(dst).startswith('installed-paseo/'))
root=H/'.local/share/paseo-orchestrator'
for name in ['orchestrator','native','tests']:tree(root/name,name)
for name in ['flow.py','paseo-flow','VALIDATION_POLICY.md','test-policy-unrestricted.mjs','model-limits.fixture.json']:put(root/name,name,True)
tree(H/'.local/share/paseo-policy','policy')
for n in ['paseo-gemini-usage','paseo-gemini-account2-provider','paseo-gemini-new2-provider']:tree(H/'.local/share'/n,'plugins/'+n)
def sanitize(x):
 if isinstance(x,dict):
  return {k:('RECONFIGURE_BEFORE_USE' if (re.search(r'(token|secret|password|private.?key|authorization|account_id|host_id|client_id)',k,re.I) and not k.endswith(('_file','_path')) and isinstance(v,str)) else sanitize(v)) for k,v in x.items()}
 if isinstance(x,list):return [sanitize(v) for v in x]
 if isinstance(x,str):return scrub(x)
 return x
for n in ['model-limits.json','profiles.json','autonomy.json','account-capacity.json','seccomp-default.json']:
 src=H/'srv_projetos/config'/n;dst=OUT/'config'/n;dst.parent.mkdir(exist_ok=True)
 dst.write_text(json.dumps(sanitize(json.loads(src.read_text())),ensure_ascii=False,indent=2)+'\n')
put(H/'srv_projetos/config/manager-instructions.txt','config/manager-instructions.txt',True)
src=H/'srv_projetos/config.json';(OUT/'config/paseo.config.json').write_text(json.dumps(sanitize(json.loads(src.read_text())),ensure_ascii=False,indent=2)+'\n')
for p in (H/'.config/systemd/user').rglob('*'):
 if p.is_file() and not p.is_symlink() and 'paseo' in str(p):put(p,'deploy/systemd/'+str(p.relative_to(H/'.config/systemd/user')),True)
for n in ['runtime.Dockerfile','paseo-compat.c','install.sh']:put(H/'srv_projetos/install'/n,'deploy/runtime/'+n,True)
for p in (H/'.local/bin').glob('paseo*'):
 if p.is_file() and not p.is_symlink():put(p,'deploy/bin/'+p.name,True)
for n in ['AGENTS.md','CLAUDE.md']:put(H/'srv_projetos/workspace'/n,'config/workspace/'+n,True)
cli=H/'.local/share/node24/lib/node_modules/@getpaseo/cli'
for name,src in [('cli',cli),('server',cli/'node_modules/@getpaseo/server')]:
 tree(src,'installed-paseo/'+name)
 # the CLI entrypoint is part of the package rather than a runtime binary
 if name=='cli':
  for p in (src/'bin').glob('*'):
   if p.is_file():put(p,'installed-paseo/cli/bin/'+p.name,True)
versions={}
for p in [cli,cli/'node_modules/@getpaseo/server',cli.parent.parent/'@xai-official/grok',cli.parent.parent/'@openai/codex',cli.parent.parent/'@anthropic-ai/claude-code']:
 if (p/'package.json').exists():
  a=json.loads((p/'package.json').read_text());versions[a['name']]=a['version']
(OUT/'config/versions.json').write_text(json.dumps(versions,indent=2)+'\n')
(OUT/'SOURCE_MANIFEST.json').write_text(json.dumps({'collected_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_host':'nexoisp','files':manifest},indent=2)+'\n')
with tarfile.open('/tmp/paseo-nexo-source.tar.gz','w:gz') as t:t.add(OUT,arcname='.',recursive=True)
print('files',len(list(OUT.rglob('*'))),'archive_bytes',pathlib.Path('/tmp/paseo-nexo-source.tar.gz').stat().st_size)
