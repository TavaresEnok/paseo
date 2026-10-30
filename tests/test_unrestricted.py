import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from orchestrator import core,autonomy,permissions

class UnrestrictedToolsTests(unittest.TestCase):
    def test_explicit_override_allows_commands_without_path_or_shell_allowlist(self):
        with patch.object(core,'autonomy_policy',return_value={'unattended_development':True,'unrestricted_tools':True}):
            for command in ['ls','ls /home/enok/Documentos/projetos','paseo-flow report example','paseo-flow recover example --reason x','git push origin main','sudo systemctl status example','curl https://example.com','python3 -c "print(1)" > /tmp/check']:
                self.assertEqual(autonomy.shell_decision(command,'/tmp'),'allow',command)
            self.assertEqual(autonomy.shell_decision('','/tmp'),'deny')

    def test_shell_and_edits_are_automatically_authorized(self):
        snapshot={'id':'example','provider':'claude','cwd':'/tmp','labels':{},'pendingPermissions':[
            {'id':'ls','name':'Bash','input':{'command':'ls'}},
            {'id':'flow','name':'Bash','input':{'command':'paseo-flow status'}},
            {'id':'write','name':'Write','input':{'file_path':'/home/enok/Documentos/projetos/project/file.txt'}},
        ]}
        with patch.object(core,'autonomy_policy',return_value={'unrestricted_tools':True}),patch.object(core,'bridge',return_value={}) as bridge,patch.object(core,'event'):
            self.assertEqual(permissions.approve_routine(snapshot,db=object()),3)
            self.assertEqual([c.kwargs['response']['behavior'] for c in bridge.call_args_list],['allow']*3)

    def test_broader_mounts_do_not_create_duplicate_docker_mounts(self):
        spec=importlib.util.spec_from_file_location('isolated_provider',Path(__file__).parents[1]/'native/isolated-provider.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            args=[];module.mount(args,Path(tmp));module.mount(args,Path(tmp),readonly=True)
            self.assertEqual(args.count('--mount'),1)
            self.assertNotIn('readonly',args[1])
