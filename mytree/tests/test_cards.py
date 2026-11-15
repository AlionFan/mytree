"""T2: real local HTTP + fake model upstream, no paid API or real photos."""
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,contract,profile,store
from test_ai import Upstream,sample_image
from test_all import _req,_serve


class CardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        self.upstream.requests=[];self.upstream.replies=[]
        threading.Thread(target=self.upstream.serve_forever,daemon=True).start()
        cfg=ai.Settings('http://127.0.0.1:'+str(self.upstream.server_address[1])+'/v1','TEST_SECRET','gpt-6.1-sol','gpt-6.1-sol',5,'low')
        self.patches=[patch('app.ai.settings',return_value=cfg),patch('app.ai.USAGE_PATH',Path(self.temp.name,'usage.jsonl')),
                      patch('app.profile._PATH',self.temp.name+'/profiles.json'),patch('app.agent._read_cache',OrderedDict())]
        for item in self.patches:item.start()
        self.httpd,self.base=_serve()

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.upstream.shutdown();self.upstream.server_close()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def reply(self,value):
        self.upstream.replies.append((200,{'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}]}))

    def envelope(self,operation,input,request_id='request1',student='owner'):
        return {'schema_version':'1.0','request_id':request_id,'operation':operation,
                'client':{'type':'web','name':'test','version':'1'},'subject':{'profile_id':student},'input':input}

    def call(self,operation,input,request_id='request1',student='owner',status=200):
        code,raw=_req(self.base,'POST','/api/agent',self.envelope(operation,input,request_id,student))
        self.assertEqual(code,status,raw)
        result=json.loads(raw);contract.response(result)
        return result

    def recognize(self,steps=None,problem='x^2-9',kind='factor',request_id='photo1'):
        self.reply({'problem':problem,'problem_latex':problem,'steps':['(x-3)^2'] if steps is None else steps,
                    'question_type':kind,'topic_id':'F2' if kind=='factor' else 'N1',
                    'supported':True,'multiple_questions':False,'warnings':[],'uncertain_lines':[]})
        return self.call('recognize',{'image_data':sample_image()},request_id)['output']

    def study_input(self,reading):
        return {'confirmed_reading_id':reading['reading_id'],'problem':reading['problem'],
                'problem_latex':reading['problem_latex'],'steps':reading['steps'],
                'recognition':{key:reading[key] for key in ('question_type','topic_id')}}

    def study(self,steps=None,request_id='study1'):
        return self.call('study',self.study_input(self.recognize(steps)),request_id)

    def test_confirmed_study_creates_one_versioned_card_and_idempotent_effects(self):
        reading=self.recognize();params=self.study_input(reading)
        self.assertFalse(Path(profile._PATH).exists())
        first=self.call('study',params,'study1');second=self.call('study',params,'study1')
        card=first['output']['wrong_card']
        self.assertEqual(card['problem'],params['problem'])
        self.assertEqual(card['student_steps'],params['steps'])
        self.assertEqual(card['revision'],0);self.assertEqual(card['study_status'],'wrong_step')
        self.assertTrue(card['knowledge_ids']);self.assertEqual(card['diagnosis_id'],first['output']['diagnosis_id'])
        self.assertEqual(card['id'],second['output']['wrong_card']['id'])
        self.assertTrue(second['output']['duplicate'])
        self.assertTrue(all(effect['idempotent_replay'] for effect in second['effects']))
        self.assertEqual(len(store.read('owner')['wrong_cards']),1)
        self.assertEqual(profile.get('owner')['history'],1)

    def test_unconfirmed_reading_cannot_create_cards(self):
        reading=self.recognize();params=self.study_input(reading);del params['confirmed_reading_id']
        result=self.call('study',params,'study1',status=400)
        self.assertEqual(result['error']['code'],'INVALID_INPUT')
        self.assertFalse(store.read('owner')['wrong_cards'])
        self.assertEqual(len(self.upstream.requests),1)

    def test_learning_card_does_not_become_a_mistake(self):
        result=self.study(steps=[])
        self.assertEqual(result['output']['wrong_card']['study_status'],'not_attempted')
        self.assertEqual(profile.get('owner')['history'],0)
        self.assertFalse(profile.get('owner')['causes'])
        self.assertFalse(store.read('owner')['knowledge_cards'])

    def test_same_id_with_changed_text_conflicts_without_mutating_data(self):
        reading=self.recognize();params=self.study_input(reading)
        self.call('study',params,'same')
        before=Path(profile._PATH).read_bytes()
        result=self.call('study',{**params,'steps':['(x-3)(x+3)']},'same',status=409)
        self.assertEqual(result['error']['code'],'CONFLICT');self.assertEqual(result['effects'],[])
        self.assertEqual(Path(profile._PATH).read_bytes(),before)

    def test_simultaneous_study_retries_commit_once(self):
        params=self.study_input(self.recognize())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.call('study',params,'same'),range(2)))
        self.assertEqual(results[0]['output']['diagnosis_id'],results[1]['output']['diagnosis_id'])
        self.assertEqual(len(store.read('owner')['wrong_cards']),1)

    def test_model_prepare_is_not_repeated_for_idempotent_study(self):
        reading=self.recognize(steps=['4'],problem='2+3',kind='calculate')
        self.reply({'hints':['先看条件。','再看运算。','PRIVATE_H3_SENTINEL'],
                    'card':{'title':'运算','body':'按顺序计算。','tip':'核对符号。'},
                    'knowledge_ids':['N1'],'assessment':'需要再核对。','answer_latex':'5'})
        params=self.study_input(reading);first=self.call('study',params,'calc')
        second=self.call('study',params,'calc')
        self.assertEqual(len(self.upstream.requests),2)
        self.assertNotIn('PRIVATE_H3_SENTINEL',json.dumps(first))
        self.assertEqual(len(first['output']['analysis']['hints']),2)
        self.assertEqual(first['output']['analysis']['hint_levels_available'],3)
        self.assertTrue(second['output']['duplicate'])
        diagnosis_id=first['output']['diagnosis_id']
        code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':diagnosis_id,'level':3})
        self.assertEqual(code,200,raw);hint=json.loads(raw)
        self.assertIn('PRIVATE_H3_SENTINEL',hint['text']);self.assertEqual(hint['max_hint_level_recorded'],3)

    def test_child_note_edit_survives_list_refresh_without_changing_diagnosis(self):
        first=self.study();card=first['output']['wrong_card'];diagnosis=profile.diagnosis_for('owner',card['diagnosis_id'])
        edited=self.call('card.edit',{'card_id':card['id'],'expected_revision':0,'learner_note':'我想先检查符号。'},'edit1')
        self.assertEqual(edited['output']['revision'],1)
        listed=self.call('card.list',{'type':'wrong'},'list1')['output']['items']
        self.assertEqual(listed[0]['learner_note'],'我想先检查符号。')
        self.assertEqual(listed[0]['revision'],1)
        self.assertEqual(profile.diagnosis_for('owner',card['diagnosis_id']),diagnosis)
        self.assertNotIn('_analysis',listed[0]);self.assertNotIn('hints',listed[0])

    def test_editing_system_fields_or_foreign_card_is_rejected(self):
        card=self.study()['output']['wrong_card']
        for extra in ({'problem':'forged'},{'analysis':{}},{'title':'new title'}):
            result=self.call('card.edit',{'card_id':card['id'],'expected_revision':0,**extra},'bad'+str(len(extra))+next(iter(extra)),status=400)
            self.assertEqual(result['error']['code'],'INVALID_INPUT')
        result=self.call('card.edit',{'card_id':card['id'],'expected_revision':0,'learner_note':'x'},'foreign',student='other',status=404)
        self.assertEqual(result['error']['code'],'NOT_FOUND')

    def test_stale_edit_reports_current_revision_without_overwrite(self):
        card=self.study()['output']['wrong_card']
        self.call('card.edit',{'card_id':card['id'],'expected_revision':0,'learner_note':'first'},'edit1')
        result=self.call('card.edit',{'card_id':card['id'],'expected_revision':0,'learner_note':'stale'},'edit2',status=409)
        self.assertEqual(result['error']['code'],'CONFLICT')
        self.assertEqual(result['error']['current_revision'],1)
        self.assertEqual(store.read('owner')['wrong_cards'][card['id']]['learner_note'],'first')

    def test_failed_commit_cannot_leave_diagnosis_without_its_card(self):
        params=self.study_input(self.recognize())
        with patch('app.profile.os.replace',side_effect=OSError('private filesystem details')):
            result=self.call('study',params,'fail',status=503)
        self.assertEqual(result['error']['code'],'STORAGE_FAILED');self.assertEqual(result['effects'],[])
        self.assertFalse(store.read('owner')['wrong_cards']);self.assertEqual(profile.get('owner')['history'],0)
        self.assertNotIn('private filesystem',json.dumps(result))

    def test_hint_access_is_monotone_and_request_cannot_supply_the_text(self):
        diagnosis_id=self.study()['output']['diagnosis_id']
        for level in (1,2,1):
            code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':diagnosis_id,'level':level})
            self.assertEqual(code,200,raw)
        self.assertEqual(json.loads(raw)['max_hint_level_recorded'],2)
        for extra in ({'text':'answer'},{'answer':'5'},{'quiz_id':'missing'}):
            code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':diagnosis_id,'level':3,**extra})
            self.assertEqual(code,400,raw)
        self.assertEqual(store.max_hint_level('owner',diagnosis_id),2)

    def test_duplicate_recognition_keeps_receipt_without_new_upstream_call(self):
        first=self.recognize(request_id='samephoto')
        result=self.call('recognize',{'image_data':sample_image()},'samephoto')
        self.assertEqual(result['output']['reading_id'],first['reading_id'])
        self.assertEqual(len(self.upstream.requests),1)
        self.assertFalse(Path(profile._PATH).exists())


if __name__=='__main__':unittest.main(verbosity=2)
