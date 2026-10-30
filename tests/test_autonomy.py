import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from orchestrator import autonomy,core,permissions

CWD='/home/enok/srv_projetos/workspace/test-project'

class AutonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.cwd=Path(self.tmp.name)/'workspace';self.cwd.mkdir()
        self.patch=patch.object(core,'DEV',self.cwd);self.patch.start()
        self.global_patch=patch(__name__+'.CWD',str(self.cwd));self.global_patch.start()
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.patch.stop);self.addCleanup(self.global_patch.stop)

    def test_unattended_accepts_real_inspection_and_dependency_install_without_whitelist(self):
        commands=[
            'cat package.json | sed -n 1,40p; sed -n 1,30p apps/web/package.json; find apps/web -name "*.test.*" | head -20',
            'ls node_modules >/dev/null 2>&1 && echo deps-ok',
            'time (timeout 500 corepack pnpm install --frozen-lockfile --prefer-offline --ignore-scripts 2>&1 | tail -8)',
            'python3 - <<\'PY\'\nfrom pathlib import Path\nprint(Path("package.json").exists())\nPY',
        ]
        with patch.object(core,'autonomy_policy',return_value={'unattended_development':True}):
            for command in commands:self.assertEqual(autonomy.shell_decision(command,CWD),'allow',command)
            for command in ['docker restart production','git push origin main','sudo apt install x','cat /home/enok/.claude/.credentials.json']:
                self.assertEqual(autonomy.shell_decision(command,CWD),'deny',command)
            self.assertFalse(autonomy.enabled('/home/enok/Documentos/projetos/Ajust_ERP'))

    def test_unattended_never_leaves_a_question_or_protected_action_waiting_for_human(self):
        snapshot={'id':'app-chat','provider':'claude','cwd':CWD,'labels':{},'pendingPermissions':[
            {'id':'question','name':'AskUserQuestion','kind':'question'},
            {'id':'protected','name':'Bash','kind':'tool','input':{'command':'docker restart production'}},
            {'id':'routine','name':'Bash','kind':'tool','input':{'command':'cat package.json | sed -n 1,40p'}},
        ]}
        with patch.object(core,'autonomy_policy',return_value={'unattended_development':True,'auto_approve_development_plans':True}),patch.object(core,'bridge',return_value={}) as native,patch.object(core,'event'):
            self.assertEqual(permissions.approve_routine(snapshot,db=object()),3)
        self.assertEqual([c.kwargs['response']['behavior'] for c in native.call_args_list],['deny','deny','allow'])
