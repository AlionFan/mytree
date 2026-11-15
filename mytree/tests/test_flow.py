"""业务闭环回归：真实 HTTP、档案持久化、排期、幂等与数学边界。"""
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import ai, profile
from app.mathcheck import ParseError, analyze, domain_notes, parse
from app.practice import check_answer
from app.schedule import TZ, next_slot, validate
from test_all import _req, _serve


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.ai_patch = patch('app.ai.settings', return_value=ai.Settings(key=''))
        self.ai_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = profile._PATH
        profile._PATH = self.temp.name + '/profiles.json'
        self.httpd, self.base = _serve()
        self.student = 'closed_loop'

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        profile._PATH = self.old_path
        self.temp.cleanup()
        self.ai_patch.stop()

    def post(self, route, **data):
        status, content = _req(self.base, 'POST', route, {'student': self.student, **data})
        self.assertEqual(status, 200, content)
        return json.loads(content)

    def diagnose(self):
        return self.post('/api/diagnose', problem='x^2-9', steps=['(x-3)^2'], request_id='first')

    def answer_set(self, items):
        for item in items:
            answer = profile._load()[self.student]['exercises'][item['id']]['a']
            self.assertTrue(self.post('/api/practice/check', exercise_id=item['id'], answer=answer)['correct'])

    def test_full_learning_loop_and_reload(self):
        diag = self.diagnose()
        self.assertEqual(diag['analysis']['cause'], 'F-MIX-FORMULA')
        self.assertEqual(profile.get(self.student)['reviews'][0]['stage'], 0)
        # 重试同一次诊断不会重复记录卡点。
        self.assertTrue(self.diagnose()['duplicate'])
        self.assertEqual(profile.get(self.student)['history'], 1)
        practice = self.post('/api/practice', diagnosis_id=diag['diagnosis_id'])
        self.assertEqual(len(practice['items']), 3)
        self.assertNotIn('a', practice['items'][0])
        self.assertNotIn('answer', practice['items'][0])
        self.assertEqual(practice, self.post('/api/practice', diagnosis_id=diag['diagnosis_id']))
        item = practice['items'][0]
        wrong = self.post('/api/practice/check', exercise_id=item['id'], answer=item['q'])
        self.assertFalse(wrong['correct'])
        self.assertEqual(profile.get(self.student)['practice_correct'], 0)
        self.answer_set(practice['items'])
        saved = profile.get(self.student)
        self.assertEqual(saved['practice_correct'], 3)
        self.assertTrue(next(k for k in saved['tree'] if k['id']=='F2')['lit'])
        self.assertEqual(saved['reviews'][0]['stage'], 1)
        answer = profile._load()[self.student]['exercises'][item['id']]['a']
        self.assertTrue(self.post('/api/practice/check', exercise_id=item['id'], answer=answer)['duplicate'])
        self.assertEqual(profile.get(self.student)['practice_correct'], 3)
        self.assertEqual(json.loads(Path(profile._PATH).read_text())[self.student]['practice_correct'], 3)
        # 新一轮复习能继续推进，复习任务编号相同也不会被误当成旧组。
        next_round = self.post('/api/practice', review_id='F2')
        self.answer_set(next_round['items'])
        saved = profile.get(self.student)
        self.assertEqual(saved['reviews'][0]['stage'], 2)
        self.assertEqual(saved['reviews'][0]['completed'], 2)
        self.assertFalse(saved['pending'])

    def test_availability_reschedules_persistently(self):
        self.diagnose()
        self.post('/api/availability', availability={'days':[2,5], 'time':'18:15'})
        p = profile.get(self.student)
        self.assertEqual(p['availability'], {'days':[2,5], 'time':'18:15'})
        due = datetime.fromisoformat(p['reviews'][0]['due'])
        self.assertIn(due.isoweekday(), [2,5])
        self.assertEqual((due.hour,due.minute), (18,15))
        self.assertEqual(due.utcoffset().total_seconds(), 28800)

    def test_malformed_requests_and_unconfigured_ai(self):
        for data in ([], None, {'student':True}, {'student':'../x'}, {'problem':'x','steps':['x']*13}, {'problem':'x'*121,'steps':['x']}, {'problem':'x','steps':[{}]}):
            status,_ = _req(self.base, 'POST', '/api/diagnose', data)
            self.assertEqual(status, 400, data)
        status, content = _req(self.base,'POST','/api/recognize',{})
        self.assertEqual(status,503)
        self.assertEqual(json.loads(content)['code'],'MODEL_NOT_CONFIGURED')
        status,_ = _req(self.base,'POST','/api/practice/check',{'exercise_id':'missing','answer':'x'})
        self.assertEqual(status,400)
        for path in ['/plan','/app.js','/style.css','/favicon.svg','/healthz']:
            self.assertEqual(_req(self.base,'GET',path)[0],200)

    def test_new_student_has_no_fake_progress(self):
        p = profile.get(self.student)
        self.assertFalse(p['reviews'])
        self.assertFalse(p['causes'])
        self.assertFalse(any(k['lit'] for k in p['tree']))
        self.assertEqual(p['practice_correct'],0)


class MathBoundaryTests(unittest.TestCase):
    def test_no_credit_for_unfinished_equal_expression(self):
        for question, answer in [('x^2-9','x^2-9'),('2x^2-8','2(x^2-4)'),('(x^2-9)/(x+3)','(x^2-9)/(x+3)')]:
            self.assertFalse(check_answer(question,answer)[0], (question,answer))
        self.assertTrue(check_answer('2x^2-8','2(x-2)(x+2)')[0])

    def test_preserves_domain_after_cancellation(self):
        result = analyze('(x^2-9)/(x+3)', ['x-3'])
        self.assertEqual(result['status'],'correct')
        self.assertIn('x+3 ≠ 0',result['domain'])
        self.assertEqual(analyze('x+1',['x(x+1)/x'])['cause'],'R-DOMAIN')
        self.assertTrue(domain_notes('(x+1)/((x-2)/(x+3))'))
        ev = analyze('(x^2-4)/(x-2)', ['x+3'])['evidence']
        self.assertNotEqual(ev['at']['x'], 2)
        self.assertNotEqual(analyze('x^2+5x+6', ['(x+2)^2'])['cause'], 'F-MIX-FORMULA')

    def test_bounded_parser_and_no_evaluation(self):
        for source in ['__import__(os)','(x-3)^99999999','x^(2+2)','(x^8)^8','1/(x-x)','1/0','x^x','x..real','x+','x^2-9=0','('*14+'x'+')'*14]:
            with self.assertRaises(ParseError,msg=source): parse(source)
        self.assertEqual(str(parse('-x^2')), '-x**2')
        self.assertEqual(str(parse('2（x＋1）')), '2*x + 2')
        self.assertEqual(analyze('x^2-81',['(x-9)^2'])['cause'],'F-MIX-FORMULA')

    def test_schedule_skips_to_selected_weekday(self):
        # 11月14日是周六；选择周二，下一个可用时段是 11月17日。
        after=datetime(2026,11,14,20,0,tzinfo=TZ)
        slot=datetime.fromisoformat(next_slot({'days':[2],'time':'18:00'},0,after))
        self.assertEqual(slot.isoformat(timespec='minutes'),'2026-11-17T18:00+08:00')
        for invalid in ({'days':[],'time':'18:00'},{'days':[8],'time':'18:00'},{'days':[True],'time':'18:00'},{'days':[2],'time':'25:00'}):
            with self.assertRaises(ValueError):validate(invalid)

if __name__=='__main__': unittest.main(verbosity=2)
