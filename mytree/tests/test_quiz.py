"""Qualification gates tested over real HTTP with synthetic algebra sources."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import cards, contract, profile, quiz, store
from app.schedule import TZ
from test_all import _req,_serve


class QuizTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch('app.profile._PATH',self.temp.name+'/profiles.json');self.patch.start()
        self.httpd,self.base=_serve();self.sequence=0
        self.source=cards.study('owner',{'problem':'x^2-9','steps':['(x-3)^2']},'source',strict=False)['output']['wrong_card']

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.patch.stop();self.temp.cleanup()

    def call(self,operation,params,identity=None,student='owner',status=200):
        self.sequence+=1
        envelope={'schema_version':'1.0','request_id':identity or 'req'+str(self.sequence),'operation':operation,
                  'client':{'type':'web','name':'test','version':'1'},'subject':{'profile_id':student},'input':params}
        code,raw=_req(self.base,'POST','/api/agent',envelope)
        self.assertEqual(code,status,raw);result=json.loads(raw);contract.response(result);return result

    def start(self,identity=None):
        return self.call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[self.source['id']]},identity)['output']

    def answer(self,group,index,correct=True,identity=None):
        item=store.read('owner')['quizzes'][group['quiz_id']]['items'][group['items'][index]['id']]
        return self.call('quiz.answer',{'quiz_id':group['quiz_id'],'exercise_id':item['id'],
                         'answer':item['answer_latex'] if correct else '999'},identity)['output']

    def solve(self,group,correct=(True,True,True)):
        return [self.answer(group,i,yes) for i,yes in enumerate(correct)]

    def unlock(self,group):return self.call('card.unlock',{'quiz_id':group['quiz_id']})['output']

    def hint(self,group,index,level=3):
        code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':self.source['diagnosis_id'],
             'quiz_id':group['quiz_id'],'exercise_id':group['items'][index]['id'],'level':level})
        self.assertEqual(code,200,raw);return json.loads(raw)

    def test_start_saves_three_items_with_transfer_and_no_private_answers_or_hints(self):
        group=self.start('start1');saved=store.read('owner')['quizzes'][group['quiz_id']]
        self.assertEqual(len(saved['items']),3);self.assertEqual(len(group['items']),3)
        self.assertTrue(group['items'][-1]['is_transfer']);self.assertIn('面积',group['items'][-1]['prompt'])
        for item in group['items']:
            self.assertEqual(set(item),set(quiz.PUBLIC_ITEM))
            self.assertNotIn('answer_latex',item);self.assertNotIn('hints',item)
        again=self.start('start1');self.assertEqual(group,again)
        self.assertEqual(len(store.read('owner')['quizzes']),1)

    def test_u1_through_u5_unlock_and_same_knowledge_never_creates_another_card(self):
        group=self.start();self.solve(group);result=self.unlock(group)
        self.assertTrue(result['unlocked']);self.assertTrue(all(result['checks'].values()))
        contract.definition('KnowledgeCard',result['card'])
        self.assertEqual(result['card']['source_wrong_card_ids'],[self.source['id']])
        again=self.unlock(group);self.assertTrue(again['reused_existing'])
        second=self.start();self.solve(second);reused=self.unlock(second)
        self.assertTrue(reused['unlocked']);self.assertTrue(reused['reused_existing'])
        self.assertEqual(reused['card']['id'],result['card']['id']);self.assertEqual(len(store.read('owner')['knowledge_cards']),1)

    def test_u1_only_one_correct_does_not_unlock(self):
        group=self.start();self.solve(group,(False,False,True));result=self.unlock(group)
        self.assertFalse(result['unlocked']);self.assertFalse(result['checks']['U1'])
        self.assertFalse(store.read('owner')['knowledge_cards'])

    def test_u2_two_correct_without_correct_transfer_does_not_unlock(self):
        group=self.start();self.solve(group,(True,True,False));result=self.unlock(group)
        self.assertTrue(result['checks']['U1']);self.assertFalse(result['checks']['U2']);self.assertFalse(result['unlocked'])

    def test_u3_ai_review_anywhere_in_group_blocks_unlock(self):
        group=self.start()
        def change(value):value['quizzes'][group['quiz_id']]['items'][group['items'][0]['id']]['verification']={'level':'ai_review','label':'待复核'}
        store.update('owner',change);self.solve(group);result=self.unlock(group)
        self.assertFalse(result['checks']['U3']);self.assertFalse(result['unlocked'])

    def test_u4_full_solution_is_recorded_on_quiz_exercise_and_blocks_unlock(self):
        group=self.start();hint=self.hint(group,0)
        self.assertEqual(hint['scope'],'quiz_exercise');self.assertEqual(hint['max_hint_level_recorded'],3)
        self.assertEqual(self.hint(group,0,1)['max_hint_level_recorded'],3)
        answers=self.solve(group);self.assertEqual(answers[0]['max_hint_level'],3)
        self.assertFalse(self.unlock(group)['checks']['U4'])
        self.assertEqual(len([v for v in store.read('owner')['hint_views'] if v.get('quiz_id')]),2)

    def test_original_solution_does_not_taint_a_new_quiz(self):
        code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':self.source['diagnosis_id'],'level':3})
        self.assertEqual(code,200,raw)
        group=self.start();self.solve(group);self.assertTrue(self.unlock(group)['unlocked'])
        self.assertEqual(store.max_hint_level('owner',self.source['diagnosis_id']),3)

    def test_u5_incomplete_group_does_not_unlock(self):
        group=self.start();self.answer(group,0);self.answer(group,2)
        result=self.unlock(group);self.assertTrue(result['checks']['U1']);self.assertFalse(result['checks']['U5'])
        self.assertFalse(result['unlocked'])

    def test_client_cannot_self_report_correctness_hint_level_or_score(self):
        group=self.start();params={'quiz_id':group['quiz_id'],'exercise_id':group['items'][0]['id'],'answer':'9'}
        for extra in ({'correct':True},{'score':3},{'max_hint_level':0}):
            self.assertEqual(self.call('quiz.answer',{**params,**extra},status=400)['error']['code'],'INVALID_INPUT')
        self.assertFalse(store.read('owner')['quiz_answers'])

    def test_answer_is_immutable_and_replays_across_new_request_ids_and_concurrency(self):
        group=self.start();first=self.answer(group,0)
        second=self.answer(group,0,False)
        self.assertTrue(second['duplicate']);self.assertTrue(second['correct']);self.assertEqual(first['evidence_id'],second['evidence_id'])
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.answer(group,1),range(2)))
        self.assertEqual(results[0]['evidence_id'],results[1]['evidence_id'])
        self.assertEqual(len(store.read('owner')['quiz_answers']),2)

    def test_groups_and_hints_cannot_cross_profiles_or_source_diagnoses(self):
        group=self.start()
        self.assertEqual(self.call('card.unlock',{'quiz_id':group['quiz_id']},student='other',status=404)['error']['code'],'NOT_FOUND')
        code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':'foreign','quiz_id':group['quiz_id'],'exercise_id':group['items'][0]['id'],'level':3})
        self.assertEqual(code,404,raw);self.assertEqual(store.read('owner')['quizzes'][group['quiz_id']]['items'][group['items'][0]['id']]['hint_max'],0)

    def test_difficulty_up_hold_down_and_two_low_groups_stop(self):
        group=self.start();result=self.solve(group)[-1]
        self.assertEqual(result['next_step'],'up');higher=self.start()
        self.assertGreater(higher['items'][0]['difficulty_level'],group['items'][0]['difficulty_level'])
        self.assertIn('面积',higher['items'][0]['prompt'])
        result=self.solve(higher,(True,False,True))[-1];self.assertEqual(result['next_step'],'hold')
        lower=self.start();result=self.solve(lower,(False,False,True))[-1];self.assertEqual(result['next_step'],'down_with_scaffold')
        again=self.start();self.assertEqual(self.solve(again,(False,False,True))[-1]['next_step'],'stop_and_explain')

    def test_full_correct_with_hint_holds_difficulty(self):
        group=self.start();self.hint(group,0,1)
        self.assertEqual(self.solve(group)[-1]['next_step'],'hold')

    def pause_knowledge(self):
        first=self.start('low-start-one');self.solve(first,(False,False,True))
        second=self.start('low-start-two');result=self.solve(second,(False,False,True))[-1]
        self.assertEqual(result['next_step'],'stop_and_explain')
        return first,second

    def test_two_low_groups_block_new_ids_and_concurrent_starts_without_writes(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,19,30,tzinfo=TZ)):
            first,_=self.pause_knowledge();before=Path(profile._PATH).read_bytes()
            params={'knowledge_id':'F2','source_wrong_card_ids':[self.source['id']]}
            with ThreadPoolExecutor(max_workers=3) as pool:
                results=list(pool.map(lambda rid:self.call('quiz.start',params,rid,status=409),('third-a','third-b','third-c')))
            self.assertTrue(all(r['error']['code']=='CONFLICT' for r in results))
            self.assertEqual(Path(profile._PATH).read_bytes(),before)
            saved=store.read('owner');self.assertEqual(len(saved['quizzes']),2)
            self.assertEqual(saved['quiz_levels']['F2']['pause_until'],'2026-11-15')
            replay=self.start('low-start-one');self.assertEqual(replay['quiz_id'],first['quiz_id'])
            self.assertEqual(len(store.read('owner')['quizzes']),2)

    def test_pause_recovers_at_shanghai_midnight_even_when_clock_is_utc(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,15,59,59,tzinfo=timezone.utc)):
            self.pause_knowledge()
            self.call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[self.source['id']]},'before-midnight',status=409)
        before=store.read('owner');old_groups=copy.deepcopy(before['quizzes'])
        with patch('app.quiz.now',return_value=datetime(2026,11,14,16,0,0,tzinfo=timezone.utc)):
            resumed=self.start('after-midnight')
        value=store.read('owner');state=value['quiz_levels']['F2']
        self.assertEqual(state['low_streak'],0);self.assertNotIn('pause_until',state)
        self.assertEqual(len(value['quizzes']),3);self.assertEqual(resumed['items'][0]['difficulty_level'],before['quiz_levels']['F2']['level'])
        self.assertEqual({key:value['quizzes'][key] for key in old_groups},old_groups)

    def test_pausing_one_knowledge_does_not_block_another_or_another_profile(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,19,30,tzinfo=TZ)):
            self.pause_knowledge()
            other_knowledge=cards.study('owner',{'problem':'3*x^2+6*x','steps':['x*(x+2)']},'source-f1',strict=False)['output']['wrong_card']
            result=self.call('quiz.start',{'knowledge_id':'F1','source_wrong_card_ids':[other_knowledge['id']]})
            self.assertEqual(result['output']['knowledge_id'],'F1')
            other_profile=cards.study('other',{'problem':'x^2-9','steps':['(x-3)^2']},'other-source',strict=False)['output']['wrong_card']
            result=self.call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[other_profile['id']]},student='other')
            self.assertEqual(result['output']['knowledge_id'],'F2')

    def test_correct_old_group_keeps_answers_and_cannot_clear_todays_pause(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,19,30,tzinfo=TZ)):
            old=self.start('already-open');self.pause_knowledge()
            self.assertEqual(self.solve(old)[-1]['next_step'],'stop_and_explain')
            self.assertTrue(self.unlock(old)['unlocked'])
            self.assertEqual(store.read('owner')['quiz_levels']['F2']['pause_until'],'2026-11-15')
            before=Path(profile._PATH).read_bytes()
            self.call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[self.source['id']]},'after-old-win',status=409)
            self.assertEqual(Path(profile._PATH).read_bytes(),before)

    def test_old_counter_migrates_from_last_completion_and_does_not_extend_yesterday(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,23,59,tzinfo=TZ)):
            self.pause_knowledge()
            def legacy(value):
                value['quiz_levels']['F2'].pop('pause_until')
                for saved in value['quizzes'].values():saved.pop('completed_at',None)
            store.update('owner',legacy);before=Path(profile._PATH).read_bytes()
            self.call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[self.source['id']]},'legacy-today',status=409)
            self.assertEqual(Path(profile._PATH).read_bytes(),before)
        with patch('app.quiz.now',return_value=datetime(2026,11,15,0,0,tzinfo=TZ)):
            self.start('legacy-tomorrow')
        self.assertEqual(store.read('owner')['quiz_levels']['F2']['low_streak'],0)

    def test_failed_last_answer_cannot_persist_a_phantom_pause(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,19,30,tzinfo=TZ)):
            self.solve(self.start(),(False,False,True));second=self.start()
            self.answer(second,0,False);self.answer(second,1,False)
            before=Path(profile._PATH).read_bytes()
            with patch('app.profile.os.replace',side_effect=OSError('private')):
                self.call('quiz.answer',{'quiz_id':second['quiz_id'],'exercise_id':second['items'][2]['id'],'answer':'999'},'last-answer-fail',status=503)
            self.assertEqual(Path(profile._PATH).read_bytes(),before)
            self.assertNotIn('pause_until',store.read('owner')['quiz_levels']['F2'])
            self.assertEqual(self.answer(second,2,False)['next_step'],'stop_and_explain')

    def lesson(self,params=None,status=200,extra_query=''):
        params=params or {'student':'owner','source_wrong_card_id':self.source['id'],'knowledge_id':'F2'}
        code,raw=_req(self.base,'GET','/api/quiz/lesson?'+urlencode(params)+extra_query)
        self.assertEqual(code,status,raw);output=json.loads(raw)
        contract.definition('QuizLessonOutput' if status==200 else 'QuizLessonError',output)
        return output

    def test_lesson_is_read_only_omits_h3_and_models_and_reads_real_pause_deadline(self):
        with patch('app.quiz.now',return_value=datetime(2026,11,14,19,30,tzinfo=TZ)):
            self.pause_knowledge()
            store.update('owner',lambda value:value['wrong_cards'][self.source['id']]['_analysis'].update(hints=['H1','H2','PRIVATE_H3_SENTINEL']))
            before=Path(profile._PATH).read_bytes()
            with patch('app.ai.complete') as model:result=self.lesson();model.assert_not_called()
            self.assertEqual(before,Path(profile._PATH).read_bytes())
            self.assertTrue(result['paused']);self.assertEqual(result['resume_on'],'2026-11-15')
            self.assertEqual(result['title'],'平方差公式');self.assertEqual(result['problem'],self.source['problem'])
            self.assertEqual(result['student_steps'],self.source['student_steps'])
            for private in ('PRIVATE_H3_SENTINEL','answer_latex','hints','_analysis'):self.assertNotIn(private,json.dumps(result))
        with patch('app.quiz.now',return_value=datetime(2026,11,15,0,0,tzinfo=TZ)):
            result=self.lesson();self.assertFalse(result['paused']);self.assertIsNone(result['resume_on'])
            self.assertEqual(before,Path(profile._PATH).read_bytes())

    def test_lesson_rejects_missing_unknown_duplicate_and_blank_query_fields(self):
        defaults={'student':'owner','source_wrong_card_id':self.source['id'],'knowledge_id':'F2'}
        for params in ({'student':'owner'}, {**defaults,'unknown':'x'}, {**defaults,'knowledge_id':''}, {**defaults,'student':'bad/id'}):
            self.assertEqual(self.lesson(params,status=400)['code'],'INVALID_INPUT')
        for extra in ('&knowledge_id=F1','&source_wrong_card_id='+self.source['id'],'&unknown='):
            self.assertEqual(self.lesson(defaults,status=400,extra_query=extra)['code'],'INVALID_INPUT')

    def test_lesson_rejects_foreign_source_or_wrong_knowledge_without_writes(self):
        before=Path(profile._PATH).read_bytes()
        self.lesson({'student':'other','source_wrong_card_id':self.source['id'],'knowledge_id':'F2'},status=404)
        self.lesson({'student':'owner','source_wrong_card_id':'missing','knowledge_id':'F2'},status=404)
        for key in ('F1','unknown'):
            self.lesson({'student':'owner','source_wrong_card_id':self.source['id'],'knowledge_id':key},status=400)
        self.assertEqual(before,Path(profile._PATH).read_bytes())

    def test_lesson_storage_failure_is_safe_503(self):
        with patch('app.store.read',side_effect=store.StorageFailed()):
            result=self.lesson(status=503)
        self.assertEqual(result['code'],'STORAGE_FAILED');self.assertNotIn('Traceback',str(result))

    def test_lesson_missing_or_overlong_saved_content_fails_output_as_safe_503(self):
        for mode in ('missing','too-long'):
            def corrupt(value):
                card=value['wrong_cards'][self.source['id']]
                if mode=='missing':card.pop('problem',None)
                else:card['problem']='x'*6001
            store.update('owner',corrupt);before=Path(profile._PATH).read_bytes()
            result=self.lesson(status=503)
            self.assertEqual(result['code'],'STORAGE_FAILED');self.assertEqual(before,Path(profile._PATH).read_bytes())
            self.assertNotIn('Traceback',str(result));self.assertNotIn('x'*6001,str(result))

    def test_verifiable_templates_accept_latex_and_expanded_factorization_does_not_pass(self):
        for knowledge in sorted(quiz.SUPPORTED):
            for level in (1,2,15):
                group=quiz._group(knowledge,level,'templates')
                self.assertEqual(len({item['q'] for item in group}),3,knowledge)
                for item in group:self.assertTrue(quiz._check(item,item['answer_latex']),knowledge)
        group=self.start();private=store.read('owner')['quizzes'][group['quiz_id']]['items'][group['items'][0]['id']]
        self.assertFalse(quiz._check(private,private['q']))

    def test_invalid_sources_and_unverifiable_topics_fail_without_quiz(self):
        self.call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':['unknown']},status=404)
        self.call('quiz.start',{'knowledge_id':'F1','source_wrong_card_ids':[self.source['id']]},status=400)
        result=self.call('quiz.start',{'knowledge_id':'G9','source_wrong_card_ids':[self.source['id']]},status=422)
        self.assertEqual(result['error']['code'],'UNSUPPORTED');self.assertFalse(store.read('owner')['quizzes'])

    def test_write_failure_cannot_return_an_answer_fact_or_unlock(self):
        group=self.start()
        with patch('app.profile.os.replace',side_effect=OSError('private')):
            self.call('quiz.answer',{'quiz_id':group['quiz_id'],'exercise_id':group['items'][0]['id'],'answer':'9'},status=503)
        self.assertFalse(store.read('owner')['quiz_answers']);self.assertFalse(store.read('owner')['quizzes'][group['quiz_id']]['answers'])


if __name__=='__main__':unittest.main(verbosity=2)
