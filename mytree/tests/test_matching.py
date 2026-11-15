"""Source-based matching and independently checked bounded quadratic ranges."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sympy as sp
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import matching,quiz,junior_practice,profile,store,cards
from app.errors import DomainError

SOURCE='已知实数m,n满足m-n=4，且m>3，n<2，求m(n+2)的取值范围。'

class MatchingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(profile,'_PATH',self.temp.name+'/profiles.json');self.patch.start()
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def source(self,knowledge='I1',problem=SOURCE):
  saved={'id':'source-card','type':'wrong','problem':problem,'student_steps':['m(n+2)=m^2-2m','(3,20)'],'knowledge_ids':[knowledge],'diagnosis_id':'source-diagnosis','_analysis':{'lesson_kp':knowledge,'question_type':'inequality','first_error':None}}
  store.update('owner',lambda value:value['wrong_cards'].__setitem__('source-card',saved))
  return saved
 def test_user_example_matches_skill_chain_despite_broad_wrong_topic(self):
  for topic in ('I1','N1','U4'):
   match=matching.classify(self.source(topic),topic)
   self.assertEqual(match['family'],'eliminate-quadratic-range');self.assertEqual(match['initial_level'],2)
   self.assertEqual(match['focus'],'巩固这道题的方法')
  self.assertEqual(matching.range_answer(4,2,3,6),sp.Interval.open(3,24))
  self.assertIsNotNone(matching.range_source(SOURCE.rstrip('。')+'？'))
 def test_latex_source_and_closed_endpoints(self):
  raw=r'实数 \(m,n\) 满足 \(m-n=4\)，\(m\ge 3\)，\(n\le 2\)，求 \(m\left(n+2\right)\) 的范围。'
  m=matching.range_source(raw);self.assertFalse(m['left_open']);self.assertFalse(m['right_open'])
  self.assertEqual(matching.range_answer(4,2,3,6,False,False),sp.Interval(3,24))
 def test_interior_vertex_extrema_are_included_even_when_endpoints_open(self):
  self.assertEqual(matching.range_answer(4,2,-1,3),sp.Interval.Ropen(-1,3))
  self.assertEqual(matching.range_answer(4,2,-1,3,True,True,-1),sp.Interval.Lopen(-3,1))
 def test_unsupported_or_conflicting_features_do_not_fallback(self):
  for raw in ('求几何图形的面积。',SOURCE+'且m<4。',SOURCE.replace('实数','整数'),SOURCE.replace('m(n+2)','m(n+2)^2'),SOURCE.replace('m>3','m>8'),SOURCE.replace('n<2','n<k')):
   if '^2' in raw:
    # Non-quadratic target must be rejected rather than matched as a prefix.
    pass
   with self.assertRaises(DomainError,msg=raw):matching.classify({'problem':raw,'_analysis':{'problem_latex':'4x+2>10'}},'I1')
 def test_all_source_conditions_and_outer_target_operators_are_consumed(self):
  for raw in (SOURCE.replace('求','且m≠4，求'),SOURCE.replace('求',r'且m\neq4，求'),SOURCE.replace('求',r'且m\ne4，求'),SOURCE.replace('m(n+2)','2m(n+2)'),SOURCE.replace('m(n+2)','1/(m(n+2))'),SOURCE.replace('m(n+2)',r'\frac{1}{m(n+2)}'),SOURCE.replace('m(n+2)','m(n+2)^2'),SOURCE.replace('m(n+2)','m(n+2)+1'),SOURCE.replace('m-n=4','2m-n=4'),SOURCE.replace('n<2','n<2，m是偶数')):
   with self.assertRaises(DomainError,msg=raw):matching.classify({'problem':raw},'I1')
 def test_complete_quiz_uses_source_and_changes_transfer_structure(self):
  source=self.source();group=quiz.start('owner',{'knowledge_id':'I1','source_wrong_card_ids':[source['id']]},'request')['output']
  self.assertEqual(len(group['items']),3);saved=store.read('owner')['quizzes'][group['quiz_id']]
  for item in saved['items'].values():
   self.assertIn('m-n=',item['prompt']);self.assertIn('取值范围',item['prompt']);self.assertTrue(junior_practice.check(item,item['answer_latex'])[0]);self.assertEqual(item['matching']['source_id'],source['id'])
  self.assertIn('-n)',group['items'][-1]['prompt']);self.assertTrue(group['items'][-1]['is_transfer'])
  self.assertEqual(saved['level'],2);self.assertNotIn('answer_latex',json.dumps(group))
 def test_three_parameter_samples_with_independent_point_checks(self):
  match=matching.classify(self.source(),'I1')
  prompts=set()
  for seed in ('sample1','sample2','sample3'):
   for item in matching.range_items(match,2,seed):
    prompts.add(item['prompt']);p=item['matching']['parameters'];lo,hi=sp.Rational(p['lower']),sp.Rational(p['upper']);c,d=sp.Rational(p['difference']),sp.Rational(p['shift'])
    expected=sp.sympify(item['expected'])
    for j in range(1,10):
     m=lo+(hi-lo)*sp.Rational(j,10);n=m-c;value=m*(d-n) if item['is_transfer'] else m*(n+d)
     self.assertTrue(expected.contains(value))
  self.assertGreaterEqual(len(prompts),7)
 def test_foreign_source_and_unknown_source_rejected_without_data(self):
  self.source()
  with self.assertRaises(DomainError) as e:quiz.start('other',{'knowledge_id':'I1','source_wrong_card_ids':['source-card']},'other')
  self.assertEqual(e.exception.status,404);self.assertFalse(store.read('other')['quizzes'])
 def test_ordinary_practice_and_quiz_share_source_matching(self):
  source=self.source('N1')
  store.update('owner',lambda v:v['events'].append({'id':'source-diagnosis','type':'diagnosis','cause':'J-N1','problem':SOURCE,'analysis':{'lesson_kp':'N1','knowledge_ids':['N1']}}))
  ordinary=profile.create_exercises('owner',diagnosis_id=source['diagnosis_id'])
  for item in ordinary['items']:
   self.assertIn('取值范围',item['question_md']);self.assertIn('先消元',item['match_reason']);self.assertNotIn('answer_latex',item)
 def test_higher_level_adds_coefficient_and_sign_work(self):
  match=matching.classify(self.source(),'I1')
  self.assertIn('2m-2n=',matching.range_items(match,3,'advanced')[0]['prompt'])
  self.assertIn('-2m<',matching.range_items(match,4,'advanced')[0]['prompt'])
 def test_incompatible_equation_or_missing_conditions_is_not_a_topic_match(self):
  for knowledge,problem in [('E1','x^2-9=0'),('E3','2x+1=5'),('E4','2x=4'),('I1','x^2>4')]:
   with self.assertRaises(DomainError):matching.classify({'problem':problem},knowledge)
 def test_simple_inequality_remains_distinct_from_composite(self):
  source={'problem':'解不等式4x+2>10','_analysis':{'problem_latex':'4x+2>10'}}
  match=matching.classify(source,'I1');self.assertEqual(match['family'],'verified-topic-template')
  self.assertNotEqual(match['family'],matching.classify(self.source(),'I1')['family'])
 def test_unlock_message_uses_actual_h3_evidence(self):
  for mode in ('none-correct','correct-h3','wrong-h3'):
   student=mode
   source=cards.study(student,{'problem':'x^2-9','steps':['(x-3)^2']},'source',strict=False)['output']['wrong_card']
   group=quiz.start(student,{'knowledge_id':'F2','source_wrong_card_ids':[source['id']]},'start')['output']
   if mode!='none-correct':quiz.hint(student,{'diagnosis_id':source['diagnosis_id'],'quiz_id':group['quiz_id'],'exercise_id':group['items'][0]['id'],'level':3})
   saved=store.read(student)['quizzes'][group['quiz_id']]
   for i,item in enumerate(saved['items'].values()):
    correct=mode!='none-correct' and (mode!='wrong-h3' or i>0)
    quiz.answer(student,{'quiz_id':group['quiz_id'],'exercise_id':item['id'],'answer':item['answer_latex'] if correct else '999'},'answer'+str(i))
   result=quiz.unlock(student,{'quiz_id':group['quiz_id']},'unlock')['output']
   if mode=='none-correct':self.assertFalse(result['unlocked']);self.assertNotIn('使用过完整解法',''.join(result['reasons']))
   elif mode=='correct-h3':self.assertFalse(result['unlocked']);self.assertIn('使用过完整解法',''.join(result['reasons']))
   else:self.assertTrue(result['unlocked'])
 def test_legacy_unmatched_group_cannot_unlock_composite_skill(self):
  source=self.source();group=quiz.start('owner',{'knowledge_id':'I1','source_wrong_card_ids':[source['id']]},'start')['output']
  def legacy(value):
   for item in value['quizzes'][group['quiz_id']]['items'].values():item.pop('matching')
  store.update('owner',legacy)
  with self.assertRaises(DomainError) as error:quiz.unlock('owner',{'quiz_id':group['quiz_id']},'unlock')
  self.assertEqual(error.exception.status,422);self.assertFalse(store.read('owner')['knowledge_cards'])
 def test_composite_lesson_does_not_show_broad_topic_rule(self):
  self.source();result=quiz.lesson('owner','source-card','I1')
  self.assertIn('消元',result['title']);self.assertIn('顶点',result['rule'])
 def test_ordinary_source_matches_only_supported_template_method(self):
  for knowledge,raw in [('F2','x^3-8'),('E3','x^2+2x+2=0'),('N2',r'\sqrt{2}+\sqrt{8}'),('F2','x^2-2'),('F1','x^3+2x^2'),('F1','6x^2+9x'),('E1','2*(x+3)=10'),('I1','2*(x+3)>10'),('E4','2/(x+1)=3'),('F2','(x^3-9x)/x'),('E3','(x^3-9x)/x=0'),('E4','6*(x-1)/(x*(x-1))=2')]:
   with self.assertRaises(DomainError,msg=raw):matching.classify({'problem':raw},knowledge)
  for source in ({'problem':'分解因式x^2-9，且x>0','_analysis':{'problem_latex':'x^2-9'}},{'problem':'求x^2-9但x不等于3','_analysis':{'problem_latex':'x^2-9'}}):
   with self.assertRaises(DomainError):matching.classify(source,'F2')
  self.assertEqual(matching.classify({'problem':'3*x^2+6*x','_analysis':{'problem_latex':r'3x^{2}+6x'}},'F1')['family'],'verified-topic-template')
  for knowledge,raw in [('F2','x^2-9'),('F1','3*x^2+6*x'),('E3','x^2-9=0'),('N2',r'\sqrt{4}+\sqrt{9}')]:
   self.assertEqual(matching.classify({'problem':raw},knowledge)['family'],'verified-topic-template')
 def test_ordinary_r2_r3_use_their_actual_templates_and_grade_correctly(self):
  for knowledge,problem,cause in [('R2','(x^2-9)/(x^2+6x+9)','R-CANCEL-TERM'),('R3','(3-x)/(x^2-9)','R-SIGN')]:
   with self.subTest(knowledge=knowledge):
    profile._save({});source=self.source(knowledge,problem)
    store.update('owner',lambda value:value['events'].append({'id':'source-diagnosis','type':'diagnosis','cause':cause,'problem':problem,'analysis':{'lesson_kp':knowledge,'knowledge_ids':[knowledge],'problem_latex':problem}}))
    items=profile.create_exercises('owner',diagnosis_id=source['diagnosis_id'])['items']
    self.assertEqual(len(items),3)
    saved=store.read('owner')['exercises']
    for item in items:
     self.assertEqual(saved[item['id']]['matching']['knowledge_id'],knowledge)
     self.assertTrue(profile.submit_answer('owner',item['id'],saved[item['id']]['answer_latex'])['correct'])
    if knowledge=='R2':self.assertIn('x^2+',items[0]['q'].split('/')[1])
    else:self.assertTrue(items[0]['q'].startswith('(') and '-x)' in items[0]['q'])
 def test_downshift_keeps_full_chain_with_visible_scaffold(self):
  match=matching.classify(self.source(),'I1')
  for item in matching.range_items(match,1,'low'):
   self.assertIn('取值范围',item['prompt']);self.assertIn('先练这条完整方法链',item['difficulty_features'][1]);self.assertEqual(item['grading'],'set')

if __name__=='__main__':unittest.main(verbosity=2)
