"""Reclaim rebuildable dependencies from completed task worktrees only."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess


def reclaim_completed_dependencies(db, target_free_gib=8):
    from . import core
    removed=[]
    rows=db.execute("SELECT tasks.* FROM tasks JOIN jobs ON jobs.id=tasks.job_id WHERE tasks.state='done' AND jobs.state IN ('running','done','blocked') AND tasks.cwd IS NOT NULL ORDER BY tasks.updated").fetchall()
    for task in rows:
        if removed and shutil.disk_usage(core.STATE).free >= target_free_gib*1024**3:break
        cwd=Path(task['cwd'])
        if cwd.is_symlink() or not cwd.is_dir() or not cwd.resolve().is_relative_to(core.WORKTREES.resolve()):continue
        if db.execute("SELECT 1 FROM tasks WHERE cwd=? AND state<>'done'",(str(cwd),)).fetchone():continue
        if db.execute('SELECT 1 FROM jobs WHERE repo=?',(str(cwd),)).fetchone():continue
        # A user may have opened an unrelated agent in this completed worktree.
        try:
            response=core.bridge('agents',options={'cwd':str(cwd),'includeArchived':False,'includeBackground':True})
            agents=[entry.get('agent',entry) for entry in response.get('entries',response.get('agents',[]))]
            if any(not a.get('archivedAt') and a.get('cwd') and Path(a['cwd']).resolve()==cwd.resolve() for a in agents):continue
        except Exception:continue # Unknown ownership is not permission to delete.
        paths=[]
        for directory,dirs,_ in os.walk(cwd,followlinks=False):
            if 'node_modules' in dirs:
                path=Path(directory)/'node_modules';relative=str(path.relative_to(cwd))
                if not path.is_symlink() and path.resolve().is_relative_to(cwd.resolve()):
                    tracked=core.git(cwd,'ls-files','--',relative)
                    ignored=subprocess.run(['git','-c','core.hooksPath=/dev/null','-C',str(cwd),'check-ignore','-q','--',relative],capture_output=True,timeout=15).returncode==0
                    if not tracked and ignored:paths.append(path)
            dirs[:]=[name for name in dirs if name not in {'node_modules','.git','.cache','dist','build','data','uploads'} and not Path(directory,name).is_symlink()]
        cache=core.STATE/'test-caches'/hashlib.sha256(str(cwd.resolve()).encode()).hexdigest()[:20]
        if cache.is_dir() and not cache.is_symlink():paths.append(cache)
        if not paths:continue
        before=shutil.disk_usage(core.STATE).free
        for path in paths:
            try:
                def writable_remove(function,name,exc):
                    os.chmod(name,0o700);function(name)
                shutil.rmtree(path,onerror=writable_remove)
                removed.append(str(path))
            except OSError as error:
                core.event(db,'dependency_cleanup_deferred',{'path':str(path),'error':str(error)[-500:]},task['job_id'],task['id'])
        core.event(db,'completed_dependencies_reclaimed',{'paths':[str(p) for p in paths],'free_bytes_delta':shutil.disk_usage(core.STATE).free-before,'source_and_commits_preserved':True},task['job_id'],task['id'])
        db.commit()
    return {'removed_paths':removed}
