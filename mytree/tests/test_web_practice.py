"""User-reported MCQ sources, actual HTTP dispatch, finite facts and compatibility."""
import json,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sympy as sp
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import matching,source_patterns,event_practice,junior_practice,profile,store,quiz,contract
from app.errors import DomainError
from test_all import _serve,_req
P4='4．下列事件是确定事件的是（　）\nA．打开手机正好显示8点 B．抛掷正方体骰子一次出现4点 C．明天会下雨 D．任意画一个三角形，它内角和等于360°'
P6=r'6．若$m-n=4$，且$m>3$，$n<2$，则$m(n+2)$的值可能是（　） A．$-1$ B．$-2$ C．$0$ D．$4$'

class WebPracticeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(profile,'_PATH',self.temp.name+'/profiles.json');self.patch.start()
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def source(self,problem,topic,identity='source'):
  analysis={'lesson_kp':topic,'knowledge_ids':[topic],'question_type':'probability' if topic=='P1' else 'inequality','first_error':None}
  source={'id':identity,'type':'wrong','problem':problem,'student_steps':[],'knowledge_ids':[topic],'diagnosis_id':identity+'_diagnosis','_analysis':analysis}
  def commit(v):
   v['wrong_cards'][identity]=source
   v['events'].append({'id':source['diagnosis_id'],'type':'lesson','cause':None,'problem':problem,'analysis':analysis})
  store.update('owner',commit);return source
 def test_both_received_sources_and_existing_numbered_formula_match(self):
  self.assertEqual(matching.classify({'problem':P4},'P1')['family'],'event-certainty')
  m=matching.classify({'problem':P6},'I1');self.assertEqual(m['source_format'],'choice')
  self.assertEqual(matching.range_answer(4,2,3,6),sp.Interval.open(3,24))
  # Independent witness for original D=4: m=1+sqrt(5), n=m-4.
  m0=1+sp.sqrt(5);self.assertTrue(3<m0<6);self.assertEqual(sp.expand(m0*(m0-2)),4)
  self.assertEqual(matching.classify({'problem':'1．因式分解：$x^{2}-9$','_analysis':{'problem_latex':'x^2-9'}},'F2')['family'],'verified-topic-template')
 def test_page_normalization_routes_new_family_to_probability(self):
  from app import page_reading
  row={'problem':P4,'steps':[],'question_type':'probability','topic_id':'N1','supported':True,'multiple_questions':False,'printed_number':'4','region':[0,0,1,1],'problem_complete':True,'diagram_complete':True,'answer_presence':'absent','association_status':'clear','association_evidence':'完整第4题题号和题干。','uncertain_lines':[],'warnings':[],'alternatives':[],'diagram_description':'','fragments':[{'role':'problem','script_kind':'printed','text':P4,'region':[0,0,1,1]}]}
  output=page_reading.normalize_page({'items':[row],'unassigned_fragments':[],'overflow':False,'warnings':[]},1,'page-generation')
  self.assertEqual(output['items'][0]['topic_id'],'P1');self.assertTrue(output['items'][0]['auto_ready'])
 def test_range_equivalent_presentation_and_renamed_variables(self):
  for source in (P6.replace('m(n+2)','m（n+2）'),P6.replace('m','a').replace('n','b'),P6.replace('$','').replace('．','。')):
   self.assertEqual(matching.classify({'problem':source},'I1')['family'],'eliminate-quadratic-range')
 def test_extra_constraints_ambiguous_options_and_changed_target_stay_rejected(self):
  for source in (P6.replace('且','且m<4，且'),P6.replace('若','若m为整数且'),P6.replace('m(n+2)','-m(n+2)'),P6.replace('m(n+2)','m(n+2)^2'),P6.replace('A．$-1$','A．$5$'),P6.replace('D．$4$','D．$24$'),P6+'，且m≠4',P6.replace('n<2','n<k')):
   with self.assertRaises(DomainError,msg=source):matching.classify({'problem':source},'I1')
  with self.assertRaises(DomainError):matching.classify({'problem':P4.split('等于')[0]},'P1')
 def test_explicit_event_facts_include_impossible_and_inevitable(self):
  examples={'抛掷正方体骰子一次出现4点':'random','抛掷正方体骰子一次出现7点':'impossible','任意画一个三角形，它内角和等于360°':'impossible','任意画一个平面三角形，它的内角和等于180°':'certain','袋中有0个红球和3个蓝球，任取1个球，取到红球':'impossible','袋中有2个红球和0个蓝球，任取1个球，取到红球':'certain','袋中有2个红球和3个蓝球，任取1个球，取到红球':'random'}
  for text,expected in examples.items():self.assertEqual(event_practice.event_kind(text),expected)
  self.assertIsNone(event_practice.event_kind('袋中有0个红球和0个蓝球，任取1个球，取到红球'))
 def test_three_complete_distinct_choices_across_seeds_and_wrong_answers(self):
  for raw,topic in [(P4,'P1'),(P6,'I1')]:
   match=matching.classify({'problem':raw},topic)
   for seed in map(str,range(8)):
    items=matching.range_items(match,2,seed) if topic=='I1' else source_patterns.generate(match,1,seed)
    self.assertEqual(len({i['prompt'] for i in items}),3)
    for item in items:
     self.assertEqual(set(item['choice_options']),set('ABCD'));self.assertEqual(item['answer_kind'],'choice')
     results=[junior_practice.check(item,label)[0] for label in 'ABCD'];self.assertEqual(sum(results),1)
     self.assertTrue(junior_practice.check(item,item['answer_latex'].lower())[0])
     self.assertFalse(junior_practice.check(item,'AB')[0]);self.assertFalse(junior_practice.check(item,'180')[0])
    if topic=='P1':
     corrects=[event_practice.event_kind(i['choice_options'][i['answer_latex']]) for i in items]
     self.assertEqual(corrects,['certain','impossible','random'])
 def test_http_ai_practice_for_owned_sources_is_reference_and_idempotent(self):
  http,base=_serve()
  generated={'items':[{'question':f'完整合成练习 {n}，求结果。','answer':str(n),'solution':f'按完整条件计算得到{n}。','relation':'原题考点延伸','answer_kind':'text'} for n in (1,2,3)]}
  try:
   for index,(problem,topic) in enumerate([(P4,'P1'),(P6,'I1'),('因式分解x^2-9','F2')]):
    source=self.source(problem,topic,'source'+str(index));before=store.read('owner')
    with patch('app.ai.complete',return_value=(generated,{})) as model:
     code,raw=_req(base,'POST','/api/practice',{'student':'owner','diagnosis_id':source['diagnosis_id']})
    self.assertEqual(code,200,raw);self.assertEqual(problem,json.loads(model.call_args.args[1][-1]['content'])['problem'])
    public=json.loads(raw);self.assertEqual(len(public['items']),3);self.assertNotIn('reference_answer',raw.decode())
    for item in public['items']:
     with patch('app.ai.complete',return_value=({'feedback':'核对条件与运算。'},{})):
      code,raw=_req(base,'POST','/api/practice/check',{'student':'owner','exercise_id':item['id'],'answer':'1'})
     self.assertEqual(code,200,raw);self.assertIsNone(json.loads(raw)['correct'])
    again=json.loads(_req(base,'POST','/api/practice/check',{'student':'owner','exercise_id':item['id'],'answer':'1'})[1]);self.assertTrue(again['duplicate'])
    code,_=_req(base,'POST','/api/practice/check',{'student':'stranger','exercise_id':item['id'],'answer':'1'});self.assertNotEqual(code,200)
    after=store.read('owner')
    for key in ('lit','kp_correct','practice_correct','events','reviews','quiz_answers'):self.assertEqual(before[key],after[key])
  finally:http.shutdown();http.server_close()
 def test_quiz_choice_contract_legacy_answer_and_idempotence(self):
  source=self.source(P4,'P1')
  result=quiz.start('owner',{'knowledge_id':'P1','source_wrong_card_ids':[source['id']]},'start')['output']
  self.assertTrue(all(i['answer_kind']=='choice' for i in result['items']));self.assertNotIn('answer_latex',json.dumps(result))
  legacy=json.loads(json.dumps(result));legacy['items'][0].pop('answer_kind');contract.definition('QuizStartOutput',legacy)
  invalid=json.loads(json.dumps(result));invalid['items'][0]['answer_kind']='anything'
  with self.assertRaises(contract.ContractError):contract.definition('QuizStartOutput',invalid)
  saved=store.read('owner')['quizzes'][result['quiz_id']]
  for item in saved['items'].values():
   params={'quiz_id':result['quiz_id'],'exercise_id':item['id'],'answer':item['answer_latex']}
   first=quiz.answer('owner',params,'answer'+item['id'])['output'];self.assertTrue(first['correct'])
   self.assertTrue(quiz.answer('owner',params,'again'+item['id'])['output']['duplicate'])
   with self.assertRaises(DomainError):quiz.answer('stranger',params,'foreign')
  params['answer_kind']='math'
  with self.assertRaises(contract.ContractError):quiz.answer('owner',params,'forged')
 def test_unlocked_probability_classic_and_variants_are_non_scoring(self):
  from app import card_learning
  source=self.source(P4,'P1');group=quiz.start('owner',{'knowledge_id':'P1','source_wrong_card_ids':[source['id']]},'classic-start')['output']
  for item in store.read('owner')['quizzes'][group['quiz_id']]['items'].values():quiz.answer('owner',{'quiz_id':group['quiz_id'],'exercise_id':item['id'],'answer':item['answer_latex']},'classic-'+item['id'])
  unlocked=quiz.unlock('owner',{'quiz_id':group['quiz_id']},'classic-unlock')['output'];self.assertTrue(unlocked['unlocked']);card=unlocked['card']['id']
  before=store.read('owner')
  for variant in range(4):
   opened=card_learning.handle('owner',{'card_id':card,'action':'next' if variant else 'open','variant':variant});self.assertEqual(opened['answer_kind'],'choice');self.assertNotIn('answer_latex',opened)
   solution=card_learning.handle('owner',{'card_id':card,'action':'solution','variant':variant});self.assertGreaterEqual(len(solution['steps']),2)
   answer=card_learning.handle('owner',{'card_id':card,'action':'answer','variant':variant,'answer':solution['answer_latex']});self.assertTrue(answer['correct'])
  after=store.read('owner')
  for key in ('knowledge_cards','quizzes','quiz_answers','growth_events','reviews'):self.assertEqual(before[key],after[key])
 def test_untemplated_event_concept_can_generate_complete_ai_exercises(self):
  source=self.source('计算某个未知随机事件的概率。','P1')
  values=[('均匀六面骰掷一次，点数至少为5的概率？','1/3','两个有利点数除以六。'),('袋中3个红球7个蓝球，等可能摸一球，红球概率？','3/10','三个有利结果除以十。'),('公平硬币独立抛两次，恰好一次正面概率？','1/2','四种等可能结果中有两种。')]
  output={'items':[{'question':q,'answer':a,'solution':r,'relation':'等可能事件计数','answer_kind':'text'} for q,a,r in values]}
  with patch('app.ai.complete',return_value=(output,{})) as model:result=profile.create_exercises('owner',diagnosis_id=source['diagnosis_id'])
  self.assertEqual(len(result['items']),3);self.assertEqual(model.call_count,1)
  self.assertTrue(all(row['verification']['level']=='unverified' for row in result['items']))
