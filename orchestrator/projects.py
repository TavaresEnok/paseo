"""Host-side project discovery; publish names and paths, never secret contents."""
from pathlib import Path
import re
import shutil
import os
import subprocess
from . import core

PROJECTS = Path('/home/enok/Documentos/projetos')
EXCLUDED = {'_shared', 'paseo-orchestrator', 'paseo-policy'}
SNAPSHOT_SKIP={'node_modules','dist','build','.git','.cache','__pycache__','data','uploads','backups','logs','.npmrc','.yarnrc','.credentials.json'}

def snapshot_ignore(directory,names):
    skipped=[]
    for name in names:
        path=Path(directory,name)
        if (name in SNAPSHOT_SKIP or path.is_symlink() or
            (name.startswith('.env') and name not in {'.env.example','.env.sample'}) or
            name.endswith(('.sqlite','.sqlite3','.db','.db-wal','.db-shm','.pem','.key','.p12','.pfx'))):skipped.append(name)
    return skipped

def prepare_dependency_cache(source,destination):
    """Copy ignored dependency caches; keep each worktree independently writable."""
    source=core.dev_path(source);destination=core.dev_path(destination)
    copied=[]
    for directory,dirs,_ in os.walk(source,followlinks=False):
        if 'node_modules' in dirs:
            cached=Path(directory)/'node_modules';relative=cached.relative_to(source);target=destination/relative
            if not cached.is_symlink() and not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(cached,target,symlinks=True);copied.append(str(relative))
        dirs[:]=[name for name in dirs if name not in {'node_modules','.git','dist','build','data','.cache'} and not Path(directory,name).is_symlink()]
    return copied

def inventory():
    entries=[]
    for root,kind in [(PROJECTS,'source'),(core.DEV,'development')]:
        if not root.exists():continue
        for path in sorted(root.iterdir()):
            if path.is_symlink() or not path.is_dir() or path.name.startswith('.') or path.name in EXCLUDED:continue
            entries.append({'name':path.name,'path':str(path),'kind':kind,'git':(path/'.git').exists(),
                            'execution':'clone_required' if kind=='source' else 'development'})
    return {'default_directory':str(core.MANAGER_ROOT),'projects':entries,
            'notes':'Sources are inventory only. Execute in development clones. No secret files are listed or read.'}

@core.serialized
def prepare(name):
    """Prepare a development clone/sanitized snapshot without changing sources."""
    if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]+',name):raise ValueError('Nome de projeto inválido.')
    entries=[p for p in inventory()['projects'] if p['name']==name]
    development=next((p for p in entries if p['kind']=='development'),None)
    if development:return {'repo':development['path'],'existing':True}
    source=next((p for p in entries if p['kind']=='source'),None)
    if not source:raise ValueError('Projeto não encontrado no catálogo.')
    dest=core.DEV/name
    if source['git']:
        subprocess.run(['git','-c','core.hooksPath=/dev/null','clone','--no-hardlinks','--',source['path'],str(dest)],
                       check=True,capture_output=True,text=True,timeout=120)
    else:
        shutil.copytree(source['path'],dest,ignore=snapshot_ignore)
        with (dest/'.gitignore').open('a') as stream:
            stream.write('\nnode_modules/\ndist/\nbuild/\n.env\n.env.*\n!.env.example\n*.sqlite*\n*.db\n*.db-*\ndata/\nuploads/\n.paseo-*\n')
        core.git(dest,'init');core.git(dest,'symbolic-ref','HEAD','refs/heads/main');core.git(dest,'add','.')
        core.git(dest,'-c','user.name=Paseo Development','-c','user.email=paseo@localhost','commit','-m','Snapshot de desenvolvimento sem dados privados')
    exclude=dest/'.git/info/exclude'
    with exclude.open('a') as stream:
        stream.write('\n# Local orchestration metadata\n.paseo-plan.json\n.paseo-context.md\n.paseo-result.json\n.paseo-review.json\n')
    native=core.bridge('project-add',cwd=str(dest))
    return {'repo':str(dest),'existing':False,'native':native,'source_kind':'git' if source['git'] else 'sanitized_snapshot',
            'notes':'Committed Git state, or a new snapshot excluding credentials, databases, runtime data, dependencies and symlinks. Source is unchanged.'}
