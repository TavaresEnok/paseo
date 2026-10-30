import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from orchestrator import core,maintenance

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.dev=root/'workspace';self.dev.mkdir();self.worktrees=root/'worktrees';self.worktrees.mkdir()
        self.state=root/'state';self.repo=self.dev/'repo';self.repo.mkdir()
        for key,value in [('DEV',self.dev),('WORKTREES',self.worktrees),('STATE',self.state),('AUTONOMY_FILE',root/'policy.json')]:
            p=patch.object(core,key,value);p.start();self.addCleanup(p.stop)
        p=patch.object(core,'bridge',return_value={'entries':[]});p.start();self.addCleanup(p.stop)
        core.git(self.repo,'init');core.git(self.repo,'symbolic-ref','HEAD','refs/heads/main');(self.repo/'code.py').write_text('original source')
        (self.repo/'.gitignore').write_text('node_modules/\n')
        core.git(self.repo,'add','.');core.git(self.repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-m','baseline')
        plan={'objective':'fixture','repo':str(self.repo),'tasks':[{'id':'done','objective':'fixture','acceptance':['fixture'],'allowed_files':['code.py'],'tests':[['true']]}]}
        job=core.submit(plan)['job_id'];self.cwd=self.worktrees/'done'
        core.git(self.repo,'worktree','add','-b','done',str(self.cwd))
        with core.database() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?",(job,))
            db.execute("UPDATE tasks SET state='done',cwd=? WHERE job_id=?",(str(self.cwd),job))
        self.deps=self.cwd/'node_modules';self.deps.mkdir();(self.deps/'package.js').write_text('generated')

    def test_only_ignored_generated_dependencies_are_removed(self):
        with core.database() as db:result=maintenance.reclaim_completed_dependencies(db)
        self.assertIn(str(self.deps),result['removed_paths']);self.assertFalse(self.deps.exists())
        self.assertEqual((self.cwd/'code.py').read_text(),'original source')
        self.assertTrue((self.cwd/'.git').exists());self.assertEqual(core.git(self.cwd,'status','--porcelain'),'')

    def test_active_task_or_native_agent_keeps_its_dependencies(self):
        with core.database() as db:
            db.execute("UPDATE tasks SET state='running'");db.commit()
            self.assertEqual(maintenance.reclaim_completed_dependencies(db)['removed_paths'],[])
            db.execute("UPDATE tasks SET state='done'");db.commit()
            with patch.object(core,'bridge',return_value={'entries':[{'agent':{'cwd':str(self.cwd),'status':'idle'}}]}):
                self.assertEqual(maintenance.reclaim_completed_dependencies(db)['removed_paths'],[])
        self.assertTrue(self.deps.exists())

    def test_tracked_dependency_and_symlink_targets_are_preserved(self):
        core.git(self.cwd,'add','-f','node_modules/package.js')
        with core.database() as db:self.assertEqual(maintenance.reclaim_completed_dependencies(db)['removed_paths'],[])
        self.assertTrue((self.deps/'package.js').exists())
        outside=self.dev/'private';outside.mkdir();(outside/'keep').write_text('private')
        (self.cwd/'nested').mkdir();(self.cwd/'nested/node_modules').symlink_to(outside,target_is_directory=True)
        with core.database() as db:maintenance.reclaim_completed_dependencies(db)
        self.assertTrue((outside/'keep').exists())
