import unittest
import tempfile
from pathlib import Path
from orchestrator import core
from unittest.mock import patch
from orchestrator.permissions import safe_command,authorized_request

CWD='/home/enok/srv_projetos/workspace/acceptance-a8e215cef8c3'

class PermissionTests(unittest.TestCase):
    def setUp(self):
        policy=patch.object(core,'autonomy_policy',return_value={});policy.start();self.addCleanup(policy.stop)
        self.tmp=tempfile.TemporaryDirectory()
        self.cwd=Path(self.tmp.name)/'workspace';self.cwd.mkdir()
        self.patch=patch.object(core,'DEV',self.cwd);self.patch.start()
        self.global_patch=patch(__name__+'.CWD',str(self.cwd));self.global_patch.start()
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.patch.stop);self.addCleanup(self.global_patch.stop)

    def test_native_wrapped_supervisor_entries_receive_automatic_approvals(self):
        from orchestrator import permissions
        with patch.object(permissions.core,'bridge',return_value={'entries':[{'agent':{'id':'manager','labels':{'flow.role':'supervisor'},'pendingPermissions':[{'id':'request'}]}}]}),patch.object(permissions.core,'native_snapshot',return_value={'id':'manager'}) as snapshot,patch.object(permissions,'approve_routine') as approve:
            permissions.supervisors()
        snapshot.assert_called_once_with('manager')
        approve.assert_called_once_with({'id':'manager'})

    def test_app_chat_without_labels_is_covered_only_in_development(self):
        from orchestrator import permissions
        with patch.object(permissions.core,'autonomy_policy',return_value={'auto_approve_development_plans':True}):
            self.assertTrue(permissions.covered_by_autonomy({'cwd':CWD,'provider':'claude','labels':{}}))
            self.assertFalse(permissions.covered_by_autonomy({'cwd':'/home/enok/Documentos/projetos/Ajust_ERP','provider':'claude'}))
        with patch.object(permissions.core,'autonomy_policy',return_value={}):
            self.assertFalse(permissions.covered_by_autonomy({'cwd':CWD,'provider':'claude'}))

    def test_mobile_pending_inspection_chain_is_automatic(self):
        command=f"cd {CWD} && git log --oneline | head -40 && ls && git ls-files | grep -iE 'analist|gerent|manager|analyst' | head -80"
        self.assertTrue(safe_command(command,CWD))
        self.assertFalse(safe_command('cd /etc && cat passwd',CWD))
        self.assertFalse(safe_command(f'cd {CWD} && rm -rf data',CWD))
    def test_compound_inspection_is_routine(self):
        self.assertTrue(safe_command('ls -la && cat README* && ls tests && cat tests/*.py && git ls-files',CWD))
        self.assertTrue(safe_command('python3 -m unittest tests.test_sum',CWD))
        self.assertTrue(safe_command('cat .paseo-disposable-demo average.py sum_values.py summary.py; which paseo-flow; paseo-flow --help 2>&1 | head -30',CWD))
        self.assertTrue(safe_command('for p in /AGENTS.md /home/AGENTS.md AGENTS.md; do if [ -f "$p" ]; then cat "$p"; fi; done\ncat README.md',CWD))

    def test_protected_effects_are_never_approved_as_routine(self):
        for command in ['rm -rf data','git push origin main','git merge task/example','docker stop painel_api',
                        'systemctl restart app','curl http://localhost:8092/admin','ls; rm -rf data',
                        'cat /home/enok/.claude/.credentials.json','ls $(curl http://example.com)',
                        'npm publish','python3 -c "import os;os.remove(\"data\")"']:
            self.assertFalse(safe_command(command,CWD),command)
        self.assertFalse(safe_command('ls # note\nrm -rf data',CWD))

    def test_approval_proof_remains_controller_responsibility(self):
        self.assertTrue(safe_command('paseo-flow approve abc --message-id def',CWD))
        self.assertFalse(safe_command('paseo-flow serve',CWD))
        self.assertFalse(safe_command('paseo-flow project /production --name x',CWD))

    def test_questions_and_plan_decisions_remain_human(self):
        snapshot={'cwd':CWD}
        self.assertFalse(authorized_request(snapshot,{'name':'AskUserQuestion','kind':'question'})[0])
        self.assertFalse(authorized_request(snapshot,{'name':'ExitPlanMode','kind':'plan'})[0])
        self.assertTrue(authorized_request(snapshot,{'name':'ToolSearch','kind':'tool'})[0])

    def test_codex_native_shell_detail_is_checked_without_outer_shell_wrapper(self):
        request={'name':'CodexBash','kind':'tool',
                 'input':{'command':'/bin/bash -lc "pwd; rg --files"','cwd':CWD},
                 'detail':{'type':'shell','command':'pwd; rg --files','cwd':CWD}}
        self.assertTrue(authorized_request({'cwd':CWD},request)[0])
        request['detail']['command']='rm -rf data'
        self.assertFalse(authorized_request({'cwd':CWD},request)[0])
