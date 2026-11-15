import json,os,tempfile,unittest
from datetime import timedelta
from unittest.mock import patch
from app import cards,store,teaching_memory as tm,personal_review as pr,review,quiz
from app.schedule import now

class PersonalReviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.patches=[patch('app.profile._PATH',self.temp.name+'/p.json'),patch.dict(os.environ,{'MYTREE_MEMORY_DB':self.temp.name+'/m.db','MYTREE_MEM0_ENABLED':'0'})]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def source(self,owner='one'):
  return cards.study(owner,{'problem':'x^2-9','steps':['(x-3)^2']},'source',strict=False)['output']['wrong_card']
 def answer(self,id,correct,hint=0,kp='F2'):
  store.update('one',lambda p:p['quiz_answers'].update({id:{'evidence_id':id,'knowledge_id':kp,'correct':correct,'max_hint_level':hint,'verification':{'level':'verified'},'at':(now()+timedelta(minutes=int(id[-1]))).isoformat()}}))
 def test_recovery_and_hints_change_priority_without_mastery(self):
  self.source();self.answer('a1',False);before=store.read('one');p=pr.arrange('one');score=p['items'][0]['score'];self.answer('a2',True);q=pr.arrange('one');self.assertLess(q['items'][0]['score'],score);self.answer('a3',True,1);r=pr.arrange('one');self.assertGreater(r['items'][0]['score'],q['items'][0]['score']);self.assertEqual(before['lit'],store.read('one')['lit'])
 def test_lesson_and_ai_not_mistakes(self):
  store.update('one',lambda p:p['wrong_cards'].update(x={'id':'x','type':'lesson','problem':'x^2-9','knowledge_ids':['F2'],'study_status':'wrong_step','verification':{'level':'verified'}},y={'id':'y','problem':'x^2-9','knowledge_ids':['F2'],'study_status':'wrong_step','verification':{'level':'ai_review'}}))
  self.assertEqual(pr.arrange('one')['items'],[])
 def test_preserve_dates_pause_and_revoke(self):
  self.source();due=(now()+timedelta(days=4)).isoformat();store.update('one',lambda p:p['reviews']['F2'].update(due=due))
  p=pr.arrange('one');self.assertEqual(p['items'][0]['due_at'],due);self.assertEqual(review.today('one')['items'],[])
  tm.forget('one',p['items'][0]['memory_ids'][0]);self.assertEqual(pr.arrange('one')['items'],[])
 def test_completion_closed_loop_and_idempotence(self):
  source=self.source();store.update('one',lambda p:p['reviews']['F2'].update(due=(now()-timedelta(days=1)).isoformat()));pr.arrange('one')
  task=review.today('one')['items'][0];self.assertIn(source['id'],task['based_on']);self.assertIn('核验',task['reason'])
  group=quiz.start('one',{'knowledge_id':'F2','source_wrong_card_ids':[source['id']],'review_id':'F2'},'q')['output'];saved=store.read('one')['quizzes'][group['quiz_id']];ids=[]
  for i,item in enumerate(saved['items'].values()):ids.append(quiz.answer('one',{'quiz_id':saved['id'],'exercise_id':item['id'],'answer':item['answer_latex']},'a'+str(i))['output']['evidence_id'])
  completed=review.complete('one',{'review_id':'F2','evidence_ids':ids},'done')['output'];self.assertTrue(completed['completed']);count=store.read('one')['reviews']['F2']['completed'];review.complete('one',{'review_id':'F2','evidence_ids':ids},'done-again');self.assertEqual(store.read('one')['reviews']['F2']['completed'],count);pr.arrange('one');self.assertEqual(review.today('one')['items'],[])
 def test_distinct_owners_and_empty_tasks(self):
  self.source();self.assertTrue(pr.arrange('one')['items']);self.assertEqual(pr.arrange('two')['items'],[])
  store.update('one',lambda p:p['wrong_cards'].clear());self.assertEqual(pr.arrange('one')['items'],[])

 def test_vector_candidate_cannot_hide_later_recovery(self):
  self.source();self.answer('a1',True);self.answer('a2',True)
  only_card=[r for r in tm.snapshot('one')['records'] if r['id'].startswith('card_')]
  with patch('app.mem0_adapter.sync_search',return_value={'engine':'mem0','status':'ready','records':only_card}):
   self.assertEqual(pr.arrange('one')['items'],[])
 def test_pause_future_and_reminders_survive_personalization(self):
  self.source();store.update('one',lambda p:p['reviews']['F2'].update(due=(now()-timedelta(days=2)).isoformat()))
  store.update('one',lambda p:p.setdefault('quiz_levels',{}).update(F2={'pause_until':(now()+timedelta(days=1)).date().isoformat()}))
  self.assertEqual(pr.arrange('one')['items'],[]);self.assertEqual(review.today('one')['items'],[])
  store.update('one',lambda p:p['quiz_levels'].clear());pr.arrange('one');key=review.today('one')['reminder_key'];review.reminder_action('one',key,'snooze');pr.arrange('one');self.assertFalse(review.today('one')['reminder_allowed'])
 def test_new_slot_uses_available_day_and_preserves_manual_time(self):
  self.source();weekday=(now().isoweekday()%7)+1
  store.update('one',lambda p:(p['reviews'].clear(),p['availability'].update(days=[weekday],time='18:17')))
  plan=pr.arrange('one');from datetime import datetime
  due=datetime.fromisoformat(plan['items'][0]['due_at']);self.assertEqual(due.isoweekday(),weekday);self.assertEqual(due.strftime('%H:%M'),'18:17');self.assertGreater(due,now())
 def test_revocation_invalidates_cached_reason_before_rearrange(self):
  self.source();store.update('one',lambda p:p['reviews']['F2'].update(due=(now()-timedelta(days=1)).isoformat()));p=pr.arrange('one');self.assertIn('核验',review.today('one')['items'][0]['reason']);tm.forget('one',p['items'][0]['memory_ids'][0]);self.assertNotIn('核验',review.today('one')['items'][0]['reason'])

 def test_new_arrangements_limit_three_per_available_day(self):
  expressions={'F1':'2*x^2+4*x','F2':'x^2-9','F3':'x^2+6*x+9','F4':'x^4-16','F5':'3*(x-2)-2*(2-x)'}
  def seed(p):
   for kp,problem in expressions.items():p['wrong_cards'][kp]={'id':kp,'problem':problem,'knowledge_ids':[kp],'study_status':'wrong_step','verification':{'level':'verified'}}
  store.update('one',seed);items=pr.arrange('one')['items'];self.assertEqual(len(items),5)
  dates=[i['due_at'][:10] for i in items];self.assertLessEqual(max(dates.count(d) for d in dates),3);self.assertEqual(len(set(dates)),2)

if __name__=='__main__':unittest.main()
