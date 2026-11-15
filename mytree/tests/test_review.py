"""T3: due work, per-day reminder suppression and server-owned evidence."""
from datetime import datetime,timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,contract,profile,review,store
from app.schedule import TZ
from test_all import _req,_serve


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.clock=datetime(2026,11,14,19,35,tzinfo=TZ)
        self.patches=[patch('app.profile._PATH',self.temp.name+'/profiles.json'),
                      patch('app.review.now',side_effect=lambda:self.clock),patch('app.ai.settings',return_value=ai.Settings(key=''))]
        for item in self.patches:item.start()
        self.httpd,self.base=_serve()
        def seed(value):
            value['availability']={'days':[1,2,3,4,5,6,7],'time':'19:30'}
            value['reviews']['F2']={'id':'F2','kp':'F2','cause':'F-MIX-FORMULA','title':'平方差公式',
                                    'due':(self.clock-timedelta(days=1)).isoformat(),'stage':0,'completed':0}
        store.update('learner',seed)

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def get(self):
        status,raw=_req(self.base,'GET','/api/review/today?student=learner')
        self.assertEqual(status,200,raw);value=json.loads(raw);contract.definition('ReviewTodayOutput',value);return value

    def post(self,path,body,status=200):
        code,raw=_req(self.base,'POST',path,{'student':'learner',**body})
        self.assertEqual(code,status,raw);return json.loads(raw)

    def agent(self,operation,params,rid='review1',status=200):
        body={'schema_version':'1.0','request_id':rid,'operation':operation,'client':{'type':'tool'},
              'subject':{'profile_id':'learner'},'input':params}
        code,raw=_req(self.base,'POST','/api/agent',body);self.assertEqual(code,status,raw)
        value=json.loads(raw);contract.response(value);return value

    def test_due_task_has_concrete_content_and_read_only_query(self):
        before=Path(profile._PATH).read_bytes();value=self.get()
        self.assertTrue(value['reminder_allowed']);self.assertEqual(len(value['items']),1)
        self.assertEqual(value['timezone'],'Asia/Shanghai');self.assertIn('平方差',value['message'])
        self.assertTrue(value['items'][0]['task']['prompt']);self.assertTrue(value['items'][0]['based_on'])
        self.assertEqual(Path(profile._PATH).read_bytes(),before)
        self.assertEqual(self.agent('review.today',{})['output'],value)

    def test_ack_suppresses_today_and_repeated_ack_is_idempotent(self):
        key=self.get()['reminder_key'];first=self.post('/api/review/ack',{'reminder_key':key})
        self.assertTrue(first['ok']);self.assertFalse(self.get()['reminder_allowed'])
        saved=store.read('learner')['reminders']
        second=self.post('/api/review/ack',{'reminder_key':key})
        self.assertTrue(second['duplicate']);self.assertEqual(store.read('learner')['reminders'],saved)
        self.clock+=timedelta(days=1)
        self.assertTrue(self.get()['reminder_allowed'])

    def test_snooze_suppresses_today_and_next_day_recovers(self):
        key=self.get()['reminder_key'];self.post('/api/review/snooze',{'reminder_key':key})
        self.assertFalse(self.get()['reminder_allowed'])
        self.clock+=timedelta(days=1)
        self.assertTrue(self.get()['reminder_allowed'])

    def test_three_consecutive_snoozes_reduce_frequency(self):
        for _ in range(3):
            self.post('/api/review/snooze',{'reminder_key':self.get()['reminder_key']})
            self.clock+=timedelta(days=1)
        self.assertFalse(self.get()['reminder_allowed'])
        self.clock+=timedelta(days=1)
        self.assertTrue(self.get()['reminder_allowed'])

    def test_four_due_items_rotate_the_fourth_into_next_day(self):
        def seed(value):
            for key in ('F1','F3','R1'):
                value['reviews'][key]={'id':key,'kp':key,'due':(self.clock-timedelta(days=1)).isoformat()}
        store.update('learner',seed)
        first={item['id'] for item in self.get()['items']};self.assertEqual(len(first),3)
        self.clock+=timedelta(days=1)
        second={item['id'] for item in self.get()['items']}
        self.assertEqual(first|second,{'F1','F2','F3','R1'})

    def test_unavailable_weekday_or_outside_window_never_reminds(self):
        for instant in (self.clock.replace(hour=19,minute=29),self.clock.replace(hour=20,minute=1)):
            self.clock=instant;value=self.get();self.assertFalse(value['reminder_allowed']);self.assertTrue(value['items'])
        self.clock=self.clock.replace(hour=19,minute=35)
        store.update('learner',lambda value:value['availability'].update(days=[2]))
        self.assertFalse(self.get()['reminder_allowed'])

    def test_no_due_work_and_unknown_or_stale_keys_do_not_remind(self):
        current=self.get()['reminder_key']
        self.post('/api/review/ack',{'reminder_key':'forged'},status=400)
        self.clock+=timedelta(days=1)
        self.post('/api/review/snooze',{'reminder_key':current},status=400)
        store.update('learner',lambda value:value['reviews'].clear())
        value=self.get();self.assertFalse(value['items']);self.assertFalse(value['reminder_allowed'])

    def test_failed_ack_write_does_not_suppress_notification(self):
        key=self.get()['reminder_key'];before=Path(profile._PATH).read_bytes()
        with patch('app.profile.os.replace',side_effect=OSError('injected')):
            result=self.post('/api/review/ack',{'reminder_key':key},status=503)
        self.assertEqual(result['code'],'STORAGE_FAILED');self.assertEqual(Path(profile._PATH).read_bytes(),before)
        self.assertTrue(self.get()['reminder_allowed'])

    def evidence(self,correct=True,level='verified',knowledge='F2',identity='proof1'):
        store.update('learner',lambda value:value['quiz_answers'].update({identity:{
            'id':identity,'knowledge_id':knowledge,'correct':correct,'verification':{'level':level},
            'at':self.clock.isoformat()}}))

    def test_only_server_verified_correct_evidence_completes_review(self):
        self.evidence()
        params={'review_id':'F2','evidence_ids':['proof1'],'self_report':'forgot'}
        first=self.agent('review.complete',params)
        self.assertTrue(first['output']['completed']);self.assertFalse(first['output']['knowledge_card_eligible'])
        self.assertEqual(store.read('learner')['reviews']['F2']['completed'],1)
        duplicate=self.agent('review.complete',params,'other-request')
        self.assertEqual(first['output'],duplicate['output']);self.assertEqual(duplicate['effects'],[])
        self.assertEqual(store.read('learner')['reviews']['F2']['completed'],1)
        self.assertFalse(store.read('learner')['knowledge_cards'])

    def test_subjective_report_and_ai_review_never_count_as_verified(self):
        for correct,level in ((False,'verified'),(True,'ai_review')):
            identity='proof-'+level
            self.evidence(correct,level,identity=identity)
            result=self.agent('review.complete',{'review_id':'F2','evidence_ids':[identity],'self_report':'remembered'},'attempt-'+level)
            self.assertFalse(result['output']['completed'])
            self.assertEqual(store.read('learner')['reviews']['F2']['completed'],0)

    def test_unknown_cross_knowledge_and_forged_correctness_are_rejected(self):
        result=self.agent('review.complete',{'review_id':'F2','evidence_ids':['missing']},'missing',status=404)
        self.assertEqual(result['error']['code'],'NOT_FOUND')
        self.evidence(knowledge='F1')
        self.agent('review.complete',{'review_id':'F2','evidence_ids':['proof1']},'foreign',status=400)
        self.agent('review.complete',{'review_id':'F2','evidence_ids':['proof1'],'correct':True},'forged',status=400)


if __name__=='__main__':unittest.main(verbosity=2)
