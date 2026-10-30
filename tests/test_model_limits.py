import unittest
import copy
import json
from pathlib import Path
from unittest.mock import patch
import orchestrator.model_limits as model_limits
from orchestrator.model_limits import allowed_model,thinking_for,load_limits,constrain_catalog
from orchestrator.routing import select_for_task,select_model

ROOT = Path(__file__).resolve().parents[1]
model_limits.LIMITS_FILE = ROOT / '.maintenance-model-limits.json'
NEW_LIMITS = ROOT / '.new-role-model-limits.json'

def model(model_id,provider='codex'):
    return {'id':model_id,'provider':provider,'available':True,'authenticated':True,
            'observed_at':1800000000,'cost':{'verified':True,'kind':'subscription','additional_cost':0,'source':'fixture'},
            'capabilities':{},'quota':{},'preferred_specialties':['backend','research']}

class ModelLimitTests(unittest.TestCase):
    def test_sol_supervisor_fallback_is_high_and_review_stays_medium(self):
        limits=copy.deepcopy(load_limits())
        limits['supervision']={'fallback_model':'codex/gpt-6.1-sol','fallback_thinking':'high'}
        with patch('orchestrator.model_limits.load_limits',return_value=limits):
            result=select_for_task([model('gpt-6.1-sol')],{'specialty':'planning','difficulty':3,'supervisor_role':'fallback'},now=1800000000)
            self.assertEqual(result['selected']['thinking_option_id'],'high')
            result=select_for_task([model('gpt-6.1-sol')],{'specialty':'review','difficulty':5},now=1800000000)
            self.assertEqual(result['selected']['thinking_option_id'],'medium')
    def test_opencode_blocks_all_models_except_grok_47(self):
        for name in ['opencode/glm-5.3-flash-free','opencode/some-free-model','anthropic/claude-opus','grok/grok-4.7']:
            self.assertFalse(allowed_model('opencode',name))
        self.assertFalse(allowed_model('opencode','xai/grok-4.7'))
        self.assertTrue(allowed_model('grok','grok-4.7'))

    def test_review_uses_only_sol_medium_at_every_difficulty_and_retry(self):
        candidates=[model('gpt-6.1-sol'),model('claude-opus-5-5','claude'),model('opencode/glm-5.3-flash-free','opencode')]
        for difficulty in [1,3,5]:
            for attempt in [0,2,4]:
                result=select_for_task(candidates,{'specialty':'review','difficulty':difficulty},phase='review',attempt=attempt,now=1800000000)
                self.assertEqual(result['selected']['key'],'codex/gpt-6.1-sol')
                self.assertEqual(result['selected']['thinking_option_id'],'medium')
        result=select_for_task(candidates[1:],{'specialty':'review'},phase='review',now=1800000000)
        self.assertIsNone(result['selected'])
        result=select_for_task(candidates,{'specialty':'backend','required_provider':'opencode','allowed_models':['grok/grok-4.7']},phase='review',now=1800000000)
        self.assertEqual(result['selected']['key'],'codex/gpt-6.1-sol')
        self.assertEqual(result['selected']['thinking_option_id'],'medium')

    def test_sonnet_only_frontend_even_as_fallback(self):
        sonnet=model('claude-sonnet-5-5','claude')
        for specialty in ['planning','backend','review','coding']:
            result=select_for_task([sonnet],{'specialty':specialty,'difficulty':3},now=1800000000)
            self.assertIsNone(result['selected'])
        result=select_for_task([sonnet],{'specialty':'frontend','difficulty':3},now=1800000000)
        self.assertIsNone(result['selected'])

    def test_opus_manager_remains_medium_even_for_difficult_planning(self):
        opus=model('claude-opus-5-5','claude')
        opus['safe_thinking_options']=['medium','high']
        for specialty in ['planning','coordination']:
            result=select_for_task([opus],{'specialty':specialty,'difficulty':5},now=1800000000)
            self.assertEqual(result['selected']['thinking_option_id'],'medium')

    def test_astra_forbidden_even_on_direct_base_router(self):
        self.assertFalse(allowed_model('codex','gpt-6-astra'))
        self.assertIsNone(select_model([model('gpt-6-astra')],{},now=1800000000)['selected'])

    def test_codex_only_three_named_models(self):
        for name in ['gpt-6.1-sol','gpt-6-luna','gpt-5.6-terra']:self.assertTrue(allowed_model('codex',name))
        for name in ['gpt-6.1-terra','gpt-5.6-sol','gpt-6-sol']:self.assertFalse(allowed_model('codex',name))

    def test_normal_code_cannot_consume_sol_even_as_only_fallback(self):
        result=select_for_task([model('gpt-6-luna'),model('gpt-5.6-terra'),model('gpt-6.1-sol')],{'specialty':'backend','difficulty':2},now=1800000000)
        self.assertIsNone(result['selected'])

    def test_routine_backend_prefers_grok_high_over_higher_scoring_models(self):
        grok=model('grok-4.7','grok')
        claude=model('claude-sonnet-5-5','claude')
        claude['capabilities']={'backend':{'value':1,'source':'fixture'}}
        with patch('orchestrator.grok_usage.current_evidence',return_value={}), patch('orchestrator.grok_usage.safe_subscription',return_value=True):
            for specialty in ['backend','coding']:
                result=select_for_task([model('gpt-6.1-sol'),grok,claude],{'specialty':specialty,'difficulty':3},now=1800000000)
                self.assertEqual(result['selected']['id'],'grok-4.7')
                self.assertEqual(result['selected']['thinking_option_id'],'high')

    def test_complex_backend_uses_only_grok_high(self):
        grok=model('grok-4.7','grok')
        with patch('orchestrator.grok_usage.current_evidence',return_value={}), patch('orchestrator.grok_usage.safe_subscription',return_value=True):
            result=select_for_task([grok,model('gpt-6.1-sol')],{'specialty':'backend','difficulty':4},now=1800000000)
        self.assertEqual(result['selected']['id'],'grok-4.7')
        self.assertEqual(result['selected']['thinking_option_id'],'high')

    def test_hard_work_caps_sol_at_high(self):
        result=select_for_task([model('gpt-6-astra'),model('gpt-6.1-sol')],{'specialty':'backend','difficulty':5},now=1800000000,attempt=4)
        self.assertIsNone(result['selected'])

    def test_all_programming_stays_grok_on_retries_without_fallback(self):
        grok=model('grok-4.7','grok')
        candidates=[grok,model('gpt-6.1-sol'),model('claude-opus-5-5','claude')]
        with patch('orchestrator.grok_usage.current_evidence',return_value={}), patch('orchestrator.grok_usage.safe_subscription',return_value=True):
            for specialty in load_limits()['programming']['specialties']:
                for difficulty in [1,3,5]:
                    for attempt in [0,1,2,4]:
                        result=select_for_task(candidates,{'specialty':specialty,'difficulty':difficulty},attempt=attempt,previous_model='grok/grok-4.7',now=1800000000)
                        self.assertEqual(result['selected']['key'],'grok/grok-4.7')
                        self.assertEqual(result['selected']['thinking_option_id'],'high')
            grok['available']=False
            self.assertIsNone(select_for_task(candidates,{'specialty':'backend','difficulty':5},now=1800000000)['selected'])

    def test_economy_allowed_only_for_small_low_risk_tasks(self):
        candidates=[model('gpt-6-luna'),model('gpt-5.6-terra')]
        self.assertIsNotNone(select_for_task(candidates,{'specialty':'research','difficulty':1},now=1800000000)['selected'])
        self.assertIsNone(select_for_task(candidates,{'specialty':'research','difficulty':4},now=1800000000)['selected'])
        self.assertIsNone(select_for_task(candidates,{'specialty':'research','difficulty':1,'criticality':'high'},now=1800000000)['selected'])

    def test_grok_stays_disabled_until_real_ids_and_login_are_validated(self):
        self.assertFalse(allowed_model('opencode','xai/grok-unverified'))

    def test_only_grok_47_can_be_permitted_even_if_other_ids_enter_allowlist(self):
        limits=copy.deepcopy(load_limits())
        limits['grok']['allowed_models']=['grok-4.7','grok-4.6','grok-4.7-heavy']
        self.assertTrue(allowed_model('grok','grok-4.7',limits))
        self.assertFalse(allowed_model('grok','grok-4.6',limits))
        self.assertFalse(allowed_model('grok','grok-4.7-heavy',limits))

    def test_old_policy_fixture_keeps_sol_review_and_sonnet_frontend_block(self):
        self.assertEqual(model_limits.LIMITS_FILE.name,'.maintenance-model-limits.json')
        limits=load_limits()
        self.assertEqual(limits['review']['model'],'codex/gpt-6.1-sol')
        self.assertFalse(limits['review'].get('fallback_allowed'))
        sonnet={'provider':'claude','id':'claude-sonnet-5-5'}
        blocked=constrain_catalog([sonnet],{'specialty':'review'},limits)[0]
        self.assertIs(blocked['restrictions']['allowed'],False)
        sol={'provider':'codex','id':'gpt-6.1-sol'}
        self.assertEqual(thinking_for(sol,{'specialty':'review','difficulty':5},4,limits),limits['review']['thinking_option'])

    def test_sol_primary_manager_stays_high_below_complex_threshold(self):
        limits=json.loads(NEW_LIMITS.read_text())
        sol={'provider':'codex','id':'gpt-6.1-sol'}
        with patch('orchestrator.model_limits.load_limits',return_value=limits):
            for difficulty in (1,3,5):
                result=select_for_task([model('gpt-6.1-sol')],{'specialty':'planning','difficulty':difficulty,'supervisor_role':'primary'},now=1800000000)
                self.assertEqual(result['selected']['key'],'codex/gpt-6.1-sol')
                self.assertEqual(result['selected']['thinking_option_id'],'high')
            self.assertEqual(thinking_for(sol,{'specialty':'planning','difficulty':1,'supervisor_role':'primary'},0,limits),'high')
            opus={'provider':'claude','id':'claude-opus-5-5','safe_thinking_options':['medium','high']}
            self.assertEqual(thinking_for(opus,{'specialty':'coordination','difficulty':5,'supervisor_role':'fallback'},4,limits),'medium')

    def test_review_effort_is_per_role_for_claude_and_codex(self):
        limits=json.loads(NEW_LIMITS.read_text())
        sonnet={'provider':'claude','id':'claude-sonnet-5-5','safe_thinking_options':['low','medium','high']}
        sol={'provider':'codex','id':'gpt-6.1-sol'}
        for difficulty in (1,5):
            for attempt in (0,4):
                self.assertEqual(thinking_for(sonnet,{'specialty':'review','difficulty':difficulty},attempt,limits),'high')
                self.assertEqual(thinking_for(sol,{'specialty':'review','review_role':'fallback','difficulty':difficulty},attempt,limits),'medium')
        open_sonnet=constrain_catalog([sonnet],{'specialty':'review'},limits)[0]
        self.assertNotIn('restrictions',open_sonnet)
