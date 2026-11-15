"""DESIGN-001 receipt handling, entirely local and without paid calls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,profile
from app.reading_registry import ReadingRegistry, ConfirmationError
from test_ai import Upstream,sample_image
from test_all import _req,_serve


class ConfirmationRegistryTests(unittest.TestCase):
    def test_receipts_are_owned_bounded_and_expire_without_mutating_source(self):
        tick=[0]
        registry=ReadingRegistry(limit=2,lifetime=10,clock=lambda:tick[0])
        value={'reading_id':'a','supported':True,'multiple_questions':False,'steps':['2']}
        registry.remember('owner',value);value['steps'][0]='7'
        self.assertEqual(registry.get('owner','a')['steps'],['2'])
        with self.assertRaises(ConfirmationError):registry.get('other','a')
        tick[0]=11
        with self.assertRaises(ConfirmationError):registry.get('owner','a')
        for identity in ('b','c','d'):registry.remember('owner',{**value,'reading_id':identity})
        with self.assertRaises(ConfirmationError):registry.get('owner','b')

    def test_new_receipt_requires_confirmation_but_legacy_is_explicitly_marked(self):
        registry=ReadingRegistry()
        registry.remember('owner',{'reading_id':'a','supported':True,'multiple_questions':False})
        self.assertTrue(registry.confirm('owner',{})['legacy_compat'])
        with self.assertRaises(ConfirmationError):registry.confirm('owner',{},strict=True)
        with self.assertRaises(ConfirmationError):registry.confirm('owner',{'recognition':{'reading_id':'a'}})
        self.assertFalse(registry.confirm('owner',{'confirmed_reading_id':'a'})['legacy_compat'])


class ConfirmationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        self.upstream.requests=[];self.upstream.replies=[]
        threading.Thread(target=self.upstream.serve_forever,daemon=True).start()
        cfg=ai.Settings('http://127.0.0.1:'+str(self.upstream.server_address[1])+'/v1','TEST_SECRET','gpt-6.1-sol','gpt-6.1-sol',5,'low')
        self.patches=[patch('app.ai.settings',return_value=cfg),patch('app.ai.USAGE_PATH',Path(self.temp.name,'usage.jsonl')),
                      patch('app.profile._PATH',self.temp.name+'/profiles.json')]
        for item in self.patches:item.start()
        self.httpd,self.base=_serve()

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.upstream.shutdown();self.upstream.server_close()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def reply(self,value):
        self.upstream.replies.append((200,{'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}]}))

    def recognize(self, value=None):
        self.reply(value or {'problem':'x^2-9','steps':['(x-3)^2'],'supported':True,'multiple_questions':False,'uncertain_lines':[],'warnings':[]})
        status,raw=_req(self.base,'POST','/api/recognize',{'student':'owner','image_data':sample_image()})
        self.assertEqual(status,200,raw)
        return json.loads(raw)

    def test_confirmation_is_required_before_new_reading_can_change_history(self):
        reading=self.recognize()
        request={'student':'owner','problem':reading['problem'],'steps':reading['steps'],'recognition':reading}
        status,raw=_req(self.base,'POST','/api/study',request)
        self.assertEqual(status,409);self.assertEqual(json.loads(raw)['code'],'NEEDS_CONFIRMATION')
        self.assertEqual(profile.get('owner')['history'],0)
        self.assertEqual(len(self.upstream.requests),1)
        status,raw=_req(self.base,'POST','/api/study',{**request,'confirmed_reading_id':reading['reading_id']})
        self.assertEqual(status,200,raw)
        self.assertEqual(json.loads(raw)['analysis']['status'],'wrong_step')
        self.assertEqual(profile.get('owner')['history'],1)

    def test_foreign_unknown_or_mismatched_receipts_do_not_call_tutor(self):
        reading=self.recognize()
        request={'problem':'x^2-9','steps':['(x-3)^2'],'recognition':reading,'confirmed_reading_id':reading['reading_id']}
        status,_=_req(self.base,'POST','/api/study',{'student':'other',**request})
        self.assertEqual(status,404)
        status,_=_req(self.base,'POST','/api/study',{'student':'owner',**request,'confirmed_reading_id':'other'})
        self.assertEqual(status,409)
        self.assertEqual(len(self.upstream.requests),1)
        self.assertEqual(profile.get('owner')['history'],0)

    def test_legacy_study_still_runs_and_marks_compatibility(self):
        status,raw=_req(self.base,'POST','/api/study',{'student':'owner','problem':'x^2-9','steps':['(x-3)^2']})
        self.assertEqual(status,200,raw)
        self.assertTrue(json.loads(raw)['legacy_confirmation'])

    def candidate_reading(self, quote=None, clear=False):
        from test_readings import candidates
        return {'problem':r'解不等式 $-2<x\le 2$。','problem_latex':r'-2<x\le2',
                'question_type':'inequality','topic_id':'I2','steps':[r'$-2<x\le7$' if clear else r'$-2<x\le ?$']+([quote] if quote else []),
                'supported':True,'multiple_questions':False,'uncertain_lines':[] if clear else [1],
                'warnings':[],'alternatives':candidates(quote)}

    def test_d1_fake_upstream_uses_student_integer_context(self):
        reading=self.recognize(self.candidate_reading('整数解为 -1,0,1,2'))
        self.assertTrue(reading['inferred']);self.assertEqual(reading['steps'][0],r'$-2<x\le 2$')
        self.assertIn('整数解',reading['reading_evidence']);self.assertTrue(reading['needs_confirmation'])
        self.assertEqual(profile.get('owner')['history'],0)

    def test_d2_wrong_inferred_seven_is_later_detected_by_math_check(self):
        reading=self.recognize(self.candidate_reading('整数解为 -1,0,1,2,3,4,5,6,7'))
        self.assertTrue(reading['inferred']);self.assertEqual(reading['steps'][0],r'$-2<x\le 7$')
        self.reply({'hints':['看条件。','再检查。','完整思路。'],'card':{'title':'不等式','body':'核对边界。','tip':'保留条件。'},
                    'assessment':'待核对。','knowledge_ids':['I2'],'answer_latex':''})
        status,raw=_req(self.base,'POST','/api/study',{'student':'owner','problem':reading['problem'],
            'problem_latex':reading['problem_latex'],'steps':reading['steps'],'recognition':reading,
            'confirmed_reading_id':reading['reading_id']})
        self.assertEqual(status,200,raw)
        result=json.loads(raw);self.assertEqual(result['analysis']['status'],'wrong_step')
        self.assertEqual(result['analysis']['first_error'],1)

    def test_d3_no_context_stays_unverified_and_offers_two_choices(self):
        reading=self.recognize(self.candidate_reading())
        self.assertFalse(reading['inferred']);self.assertEqual(len(reading['alternatives']),2)
        self.assertTrue(all(item['consistency']=='unverified' for item in reading['alternatives']))

    def test_d4_clear_contradictory_line_is_not_silently_changed(self):
        reading=self.recognize(self.candidate_reading('整数解为 -1,0,1,2',clear=True))
        self.assertFalse(reading['inferred']);self.assertEqual(reading['steps'][0],r'$-2<x\le7$')
        self.assertIn('矛盾',reading['reading_evidence'])

    def test_d5_crossed_ink_does_not_enter_work(self):
        value={'problem':'1+1','problem_latex':'1+1','question_type':'calculate','topic_id':'N1',
               'steps':['[划掉:7]2'],'supported':True,'multiple_questions':False,'uncertain_lines':[],'warnings':[]}
        reading=self.recognize(value)
        self.assertEqual(reading['steps'],['2'])


if __name__=='__main__':unittest.main(verbosity=2)
