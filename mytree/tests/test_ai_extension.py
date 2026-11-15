import copy,os,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from app import ai_extension as ext,profile,store
from app.errors import DomainError

class ExtensionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  p=patch('app.profile._PATH',self.temp.name+'/p.json');p.start();self.addCleanup(p.stop)
  self.source={'id':'card','diagnosis_id':'diag','problem':r'求使 \\(1/\\sqrt{x-1}\\) 有意义的x范围。','knowledge_ids':['N2'],'student_steps':[],'revision':1}
  store.update('one',lambda p:p['wrong_cards'].update(card=self.source))
 def generated(self):return {'items':[{'question':f'求使 \\(1/\\sqrt{{x-{n}}}\\) 有意义的x范围。','relation':'根号非负与分母非零取交集','answer':f'x>{n}','solution':f'x-{n}>0，所以x>{n}。','answer_kind':'text'} for n in (2,3,4)]},{'model':'fake'}
 def test_three_hidden_answers_replay_and_cross_owner(self):
  with patch('app.ai.complete',return_value=self.generated()) as call:
   a=profile.create_exercises('one',diagnosis_id='diag');b=profile.create_exercises('one',diagnosis_id='diag')
   self.assertEqual(a,b);self.assertEqual(call.call_count,1);self.assertEqual(len(a['items']),3)
   self.assertNotIn('reference_answer',str(a));self.assertNotIn('reference_solution',str(a))
   with self.assertRaises(DomainError):profile.create_exercises('two',diagnosis_id='diag')
 def test_feedback_cannot_change_mastery_or_review_and_is_cached(self):
  with patch('app.ai.complete',return_value=self.generated()):group=profile.create_exercises('one',diagnosis_id='diag')
  before=store.read('one');eid=group['items'][0]['id']
  with patch('app.ai.complete',return_value=({'feedback':'步骤成立。'},{})) as call:
   result=profile.submit_answer('one',eid,'x>2');again=profile.submit_answer('one',eid,'x>2')
   self.assertIsNone(result['correct']);self.assertTrue(again['duplicate']);self.assertEqual(call.call_count,1)
  after=store.read('one')
  for key in ('lit','kp_correct','practice_correct','events','reviews','quiz_answers'):self.assertEqual(before[key],after[key])
  self.assertFalse(after['exercises'][eid]['correct'])
  with self.assertRaises(ValueError):profile.submit_answer('two',eid,'x>2')
 def test_source_revision_change_inflight_rejected(self):
  def changed(*a,**kw):
   store.update('one',lambda p:p['wrong_cards']['card'].update(revision=2));return self.generated()
  with patch('app.ai.complete',side_effect=changed),self.assertRaises(DomainError):profile.create_exercises('one',diagnosis_id='diag')
  self.assertEqual(store.read('one')['exercises'],{})
 def test_source_edit_rejects_old_answer(self):
  with patch('app.ai.complete',return_value=self.generated()):group=profile.create_exercises('one',diagnosis_id='diag')
  store.update('one',lambda p:p['wrong_cards']['card'].update(problem='新题'))
  with patch('app.ai.complete') as call,self.assertRaises(DomainError):profile.submit_answer('one',group['items'][0]['id'],'x>2')
  call.assert_not_called()
  self.assertEqual(profile.get('one')['pending'],[])
 def test_incomplete_duplicate_and_missing_options_rejected(self):
  for kind in ('missing','duplicate','options'):
   data,_=self.generated()
   if kind=='missing':data['items'].pop()
   elif kind=='duplicate':data['items'][1]=data['items'][0]
   else:data['items'][0]['answer_kind']='choice'
   with self.subTest(kind=kind),patch('app.ai.complete',return_value=(data,{})),self.assertRaises(DomainError):ext.generate(self.source)
 def test_parallel_generation_single_model_call(self):
  with patch('app.ai.complete',return_value=self.generated()) as call,ThreadPoolExecutor(max_workers=3) as pool:
   results=list(pool.map(lambda _:profile.create_exercises('one',diagnosis_id='diag'),range(3)))
  self.assertEqual(call.call_count,1);self.assertEqual(results[0],results[2])
 def test_failure_is_retryable_without_partial_items(self):
  with patch('app.ai.complete',side_effect=DomainError('UPSTREAM','重试',502)),self.assertRaises(DomainError):profile.create_exercises('one',diagnosis_id='diag')
  self.assertEqual(store.read('one')['exercises'],{})
  with patch('app.ai.complete',return_value=self.generated()):self.assertEqual(len(profile.create_exercises('one',diagnosis_id='diag')['items']),3)
 def test_feedback_invalid_input_never_calls_model(self):
  for answer in ('','   ','a'*481,None,{},5):
   with self.subTest(answer_type=type(answer).__name__),patch('app.ai.complete') as call,self.assertRaises(DomainError):ext.feedback({},answer)
   call.assert_not_called()
 def test_duplicate_choice_text_rejected(self):
  data,_=self.generated();row=data['items'][0];row.update(answer_kind='choice',answer='A',options={'A':'x > 2','B':'x>2','C':'x<2','D':'x=2'})
  with patch('app.ai.complete',return_value=(data,{})),self.assertRaises(DomainError):ext.generate(self.source)
 def test_pause_honored_without_model_call(self):
  from datetime import timedelta
  from app.schedule import now
  store.update('one',lambda p:p.setdefault('quiz_levels',{}).update(N2={'pause_until':(now()+timedelta(days=1)).date().isoformat()}))
  with patch('app.ai.complete') as call,self.assertRaises(DomainError):profile.create_exercises('one',diagnosis_id='diag')
  call.assert_not_called()

if __name__=='__main__':unittest.main()
