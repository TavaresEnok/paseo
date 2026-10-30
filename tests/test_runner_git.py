import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import core


def _commit(repo):
    (repo/'f.txt').write_text('a\n')
    subprocess.run(['git','-C',str(repo),'add','f.txt'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@localhost','commit','-m','baseline'],check=True,capture_output=True)


def _init(path):
    path.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','init','-q',str(path)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(path),'symbolic-ref','HEAD','refs/heads/main'],check=True,capture_output=True)
    _commit(path)
    return path


def _mounts(argv):
    return [argv[index+1] for index,value in enumerate(argv) if value=='--mount']


class RunnerGitMountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.dev=self.root/'workspace'
        self.worktrees=self.root/'worktrees'
        self.state=self.root/'state'
        self.dev.mkdir();self.worktrees.mkdir()
        self.patches=[patch.object(core,'DEV',self.dev),patch.object(core,'WORKTREES',self.worktrees),patch.object(core,'STATE',self.state)]
        for item in self.patches:item.start()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def _docker(self, cwd, commands):
        completed=subprocess.CompletedProcess([],0,stdout='',stderr='')
        with patch.object(core.subprocess,'run',return_value=completed) as run:
            core.test_commands(str(cwd),commands)
        return [c.args[0] for c in run.call_args_list if c.args[0][:2]==['docker','run']]

    def test_worktree_mounts_absolute_gitdir_readonly(self):
        repo=_init(self.dev/'NexoISP')
        worktree=self.worktrees/'task-1'
        subprocess.run(['git','-C',str(repo),'worktree','add','-q','-b','task',str(worktree)],check=True,capture_output=True)
        (worktree/'f.txt').write_text('a\nchanged\n')
        host=subprocess.run(['git','-C',str(worktree),'diff','--check'],capture_output=True)
        self.assertEqual(host.returncode,0,host.stderr.decode())
        pointer=(worktree/'.git').read_text().strip()
        self.assertTrue(pointer.startswith('gitdir: /'))
        gitdir=Path(pointer.split(':',1)[1].strip())
        raw=subprocess.check_output(['git','-C',str(worktree),'rev-parse','--git-common-dir'],text=True).strip()
        common=Path(raw)
        common=common.resolve() if common.is_absolute() else (worktree/common).resolve()
        self.assertEqual(common,(repo/'.git').resolve())
        self.assertEqual(gitdir.resolve(),(common/'worktrees'/worktree.name).resolve())
        mounts=core.git_check_mounts(worktree)
        self.assertEqual(mounts[0],(worktree/'.git',Path('/work/.git')))
        self.assertEqual(mounts[1:],[(common,common)])
        self.assertNotIn((repo,repo),mounts)
        launches=self._docker(worktree,[['git','diff','--check']])
        argv=launches[0]
        specs=_mounts(argv)
        self.assertIn(f'type=bind,src={worktree},dst=/work',specs)
        self.assertIn(f'type=bind,src={worktree}/.git,dst=/work/.git,readonly',specs)
        self.assertIn(f'type=bind,src={common},dst={common},readonly',specs)
        self.assertFalse(any(spec.split('src=',1)[1].split(',dst=',1)[0]==str(repo) for spec in specs))
        self.assertNotIn(str(self.root/'producao'),' '.join(argv))
        self.assertNotIn('docker.sock',' '.join(argv))
        self.assertEqual(argv[argv.index('--network')+1],'none')
        self.assertIn('seccomp=/home/enok/srv_projetos/config/seccomp-default.json',argv)
        self.assertIn('--pids-limit',argv);self.assertIn('256',argv)
        self.assertIn('384m',argv);self.assertIn('--read-only',argv)
        self.assertIn('1000:1000',argv);self.assertIn('no-new-privileges',argv)
        for dst in ('/tmp/.corepack','/tmp/.npm','/tmp/.pnpm-store','/tmp/.cache/prisma','/tmp/go-build','/tmp/go-mod','/tmp/go-tmp'):
            self.assertTrue(any(f'dst={dst}' in spec for spec in specs))
        self.assertEqual(argv[argv.index('nexoisp-paseo-runtime:20261027')+1:],['git','diff','--check'])
        self.assertIn('GIT_OPTIONAL_LOCKS=0',argv)
        self.assertIn('GIT_CONFIG_VALUE_0=*',argv)
        self.assertIn('GIT_CONFIG_VALUE_1=/dev/null',argv)

    def test_normal_repo_keeps_git_readonly_and_check_offline(self):
        repo=_init(self.dev/'plain')
        launches=self._docker(repo,[['npm','ci','--prefix','frontend'],['git','diff','--check']])
        setup,check=launches
        self.assertEqual(setup[setup.index('--network')+1],'host')
        self.assertIn('--ignore-scripts',setup)
        self.assertEqual(check[check.index('--network')+1],'none')
        self.assertNotIn('--ignore-scripts',check)
        self.assertEqual(check[check.index('nexoisp-paseo-runtime:20261027')+1:],['git','diff','--check'])
        for argv in launches:
            specs=_mounts(argv)
            self.assertIn(f'type=bind,src={repo},dst=/work',specs)
            self.assertIn(f'type=bind,src={repo}/.git,dst=/work/.git,readonly',specs)
            self.assertIn('seccomp=/home/enok/srv_projetos/config/seccomp-default.json',argv)
            self.assertIn('1536m' if argv is setup else '384m',argv)
            for dst in ('/tmp/.npm','/tmp/go-build','/tmp/go-mod'):
                self.assertTrue(any(f'dst={dst}' in spec for spec in specs))
            self.assertNotIn('docker.sock',' '.join(argv))
            self.assertFalse(any(',dst=/var/run/docker.sock' in spec or spec.endswith('dst=/var/run/docker.sock') for spec in specs))

    def test_rejects_production_credentials_and_socket_without_docker(self):
        production=_init(self.root/'producao'/'NexoISP')
        worktree=self.worktrees/'task-prod'
        subprocess.run(['git','-C',str(production),'worktree','add','-q','-b','task',str(worktree)],check=True,capture_output=True)
        with patch.object(core.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'fora dos clones de desenvolvimento'):
                core.test_commands(str(worktree),[['git','diff','--check']])
            run.assert_not_called()
        secret=_init(self.dev/'credentials')
        hidden=self.worktrees/'task-secret'
        subprocess.run(['git','-C',str(secret),'worktree','add','-q','-b','secret',str(hidden)],check=True,capture_output=True)
        with patch.object(core.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'sensíveis'):
                core.git_check_mounts(hidden)
            run.assert_not_called()
        (worktree/'.git').write_text('gitdir: /var/run/docker.sock\n')
        with self.assertRaisesRegex(RuntimeError,'sensíveis'):
            core.git_check_mounts(worktree)
        outside=self.root/'producao'
        with self.assertRaisesRegex(RuntimeError,'não produção'):
            core.git_check_mounts(outside)
