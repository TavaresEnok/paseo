#!/usr/bin/env python3
"""Consistent private configuration, OAuth, controller and source recovery."""
from pathlib import Path
import datetime,fcntl,json,os,sqlite3,tarfile,tempfile,subprocess
HOME=Path('/home/enok');BASE=HOME/'srv_projetos';DEST=HOME/'.local/state/paseo-backups'
SKIP={'node_modules','.cache','__pycache__','.next','test-caches','labs','validation-operations','backups','logs','telemetry','tmp'}
def main():
 os.umask(0o077);DEST.mkdir(parents=True,exist_ok=True,mode=0o700)
 with (DEST/'backup.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');pending=DEST/(stamp+'.pending');target=DEST/(stamp+'.tar.gz')
  sources=[BASE/'config.json',BASE/'config',BASE/'agents',BASE/'workspaces',BASE/'orchestration',BASE/'runtime/isolated',HOME/'.local/share/paseo-policy',HOME/'.local/share/paseo-orchestrator',HOME/'.local/share/paseo-gemini-account2-provider',HOME/'.local/share/paseo-gemini-usage',HOME/'.local/share/paseo-gemini-accounts/account2',HOME/'.config/systemd/user']
  sources.extend(BASE/glob for glob in ['projects','schedules','agent-requests','creations','server-id','daemon-keypair.json','local-credential','cli-client-id','push-tokens.json','finish-subscriptions.json'])
  sources.extend(BASE.glob('*.sqlite*'));sqlites={};members=set()
  def select(info):
   parts=Path(info.name).parts
   if SKIP.intersection(parts) or info.name.endswith(('.log','.log.jsonl','.sqlite3-wal','.sqlite3-shm','.sqlite-wal','.sqlite-shm','.db-wal','.db-shm')):return None
   if info.name in members:return None
   members.add(info.name)
   if info.isfile():
    path=HOME/info.name
    if path.suffix in ('.sqlite','.sqlite3','.db'):
     with path.open('rb') as f:header=f.read(16)
     if header==b'SQLite format 3\0':sqlites[str(path)]=info.name;return None
   return info
  try:
   with tempfile.TemporaryDirectory(dir=DEST) as staging:
    with tarfile.open(pending,'w:gz',compresslevel=1) as archive:
     for source in sources:
      if source.exists():archive.add(source,arcname=str(source.relative_to(HOME)),filter=select)
     project=HOME/'Documentos/projetos'
     for name in ['AGENTS.md','CLAUDE.md','.paseo-context.md','.paseo-plan.json']:
      path=project/name
      if path.is_file():archive.add(path,arcname=str(path.relative_to(HOME)),filter=select)
     repos=set()
     for parent in [project,BASE/'workspace',BASE/'worktrees']:
      for directory,dirs,files in os.walk(parent):
       root=Path(directory)
       dirs[:]=[d for d in dirs if d not in SKIP and d!='.git']
       if (root/'.git').exists():repos.add(root);dirs[:]=[]
       elif len(root.relative_to(parent).parts)>3:dirs[:]=[]
     for repo in sorted(repos):
      if repo.is_symlink():continue
      result=subprocess.run(['git','-c','core.hooksPath=/dev/null','-C',str(repo),'ls-files','-z','--cached','--others','--exclude-standard'],capture_output=True,check=True,timeout=60)
      archive.add(repo/'.git',arcname=str((repo/'.git').relative_to(HOME)),filter=select)
      tracked=subprocess.run(['git','-C',str(repo),'ls-files','-z','--cached'],capture_output=True,check=True,timeout=60)
     tracked_names=set(tracked.stdout.decode().split('\0'))
     def source_filter(info):
      if info.name in members:return None
      members.add(info.name);return info
     for name in sorted(set(result.stdout.decode().split('\0'))):
       if not name or Path(name).is_absolute() or '..' in Path(name).parts:continue
       path=repo/name
       if path.is_file() or path.is_symlink():archive.add(path,arcname=str(path.relative_to(HOME)),recursive=False,filter=source_filter if name in tracked_names else select)
     for i,(source,name) in enumerate(sqlites.items()):
      snapshot=Path(staging)/(str(i)+'.sqlite3')
      with sqlite3.connect('file:'+source+'?mode=ro',uri=True,timeout=15) as src:
       with sqlite3.connect(snapshot) as dst:src.backup(dst)
      archive.add(snapshot,arcname=name)
    pending.replace(target)
    (DEST/'latest.json').write_text(json.dumps({'archive':str(target),'created_utc':stamp,'sqlite_snapshots':len(sqlites),'custom_policy_and_providers':True,'gemini_account':3}))
    (DEST/'last-failure.json').unlink(missing_ok=True)
   for old in sorted(DEST.glob('*.tar.gz'),reverse=True)[3:]:old.unlink()
   print('Backup privado concluído:',target.name)
  except Exception as error:
   (DEST/'last-failure.json').write_text(json.dumps({'at':stamp,'error':str(error)}));raise
  finally:pending.unlink(missing_ok=True)
if __name__=='__main__':main()
