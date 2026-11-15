"""Non-scoring examples: ownership, actual template answers, replay and method parity."""
import copy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import card_learning as lesson,quiz,store,cards
from app.errors import DomainError
from test_all import _serve,_req
import json

class CardLearningTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.temp.name+'/profiles.json');self.patch.start()
  self.source=cards.study('owner',{'problem':'x^2-9','steps':['(x-3)^2']},'source',strict=False)['output']['wrong_card']
  def create(v):v['knowledge_cards']['card1']={'id':'card1','type':'knowledge','knowledge_id':'F2','title':'平方差','rule':r'\(a^2-b^2=(a-b)(a+b)\)','status':'active','source_wrong_card_ids':[self.source['id']]}
  store.update('owner',create)
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def call(self,action,**kw):return lesson.handle('owner',{'action':action,'card_id':'card1',**kw})
 def test_all_unlockable_topics_have_correct_classics_and_worked_steps(self):
  self.assertEqual(set(lesson.EXAMPLES),quiz.SUPPORTED|quiz.COMPOSITE_SUPPORTED)
  for key,item in lesson.EXAMPLES.items():
   with self.subTest(key=key):
    self.assertTrue(quiz._check(item,item['answer_latex']));self.assertGreaterEqual(len(item['worked_steps']),2)
 def test_open_has_no_answer_and_replay_is_stable(self):
  a=self.call('open');b=self.call('open');self.assertEqual(a,b);self.assertTrue(a['practice_only']);self.assertNotIn('answer_latex',a)
  self.assertEqual(len(store.read('owner')['card_lessons']),1)
 def test_same_method_variants_and_cannot_self_award_mastery(self):
  before=store.read('owner')
  a=self.call('open');b=self.call('next',variant=1);self.assertEqual(a['knowledge_id'],b['knowledge_id']);self.assertNotEqual(a['prompt'],b['prompt'])
  answer=self.call('solution')['answer_latex'];self.assertTrue(self.call('answer',answer=answer)['correct']);self.assertFalse(self.call('answer',answer='999')['correct'])
  after=store.read('owner')
  for key in ['knowledge_cards','quizzes','quiz_answers','growth_events','reviews']:self.assertEqual(before[key],after[key])
 def test_hint_then_solution_are_explicit(self):
  self.call('open');hint=self.call('hint');self.assertNotIn('answer_latex',hint)
  solved=self.call('solution');self.assertEqual(solved['answer_latex'],r'\left(x - 3\right) \left(x + 3\right)')
 def test_foreign_or_removed_card_is_not_accessible(self):
  with self.assertRaises(DomainError):lesson.handle('other',{'action':'open','card_id':'card1'})
  store.update('owner',lambda v:v['knowledge_cards']['card1'].update(status='removed'))
  with self.assertRaises(DomainError):self.call('open')
 def test_invalid_and_missing_lesson_do_not_write(self):
  before=store.read('owner')
  for body in [{'action':'answer','card_id':'card1','answer':'x-3'},{'action':'next','card_id':'card1','variant':51},{'action':'open','card_id':'card1','model':'bad'},{'action':'next','card_id':'card1','variant':True}]:
   with self.assertRaises((ValueError,DomainError)):lesson.handle('owner',body)
  self.assertEqual(before,store.read('owner'))
 def test_cache_expiration_and_source_removal_fail_explicitly(self):
  self.call('open')
  store.update('owner',lambda v:v.update(card_lessons={str(i):{} for i in range(200)}))
  self.call('next',variant=50)
  self.assertEqual(len(store.read('owner')['card_lessons']),200)
  with self.assertRaises(DomainError) as expired:self.call('solution')
  self.assertIn('过期',str(expired.exception))
  store.update('owner',lambda v:v['wrong_cards'].clear())
  for action in ('next','solution','answer'):
   with self.assertRaises(DomainError):self.call(action,variant=50,answer='0')
 def test_http_endpoint_and_cross_profile_isolation(self):
  http,base=_serve()
  try:
   status,raw=_req(base,'POST','/api/knowledge/learn',{'student':'owner','action':'open','card_id':'card1'});self.assertEqual(status,200);self.assertTrue(json.loads(raw)['practice_only'])
   status,_=_req(base,'POST','/api/knowledge/learn',{'student':'other','action':'solution','card_id':'card1'});self.assertEqual(status,404)
  finally:http.shutdown();http.server_close()
if __name__=='__main__':unittest.main()

class AllTopicLessonTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.temp.name+'/profiles.json');self.patch.start()
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def test_nineteen_topics_open_derive_replay_and_preserve_source(self):
  import sympy as sp
  from app.formulas import parse_math,answer_set
  sources={'F1':'2*x^2+6*x','F2':'x^2-9','F3':'x^2+6*x+9','F4':'x^4-16','F5':'2*(x-3)-4*(3-x)',
   'R1':'(x^2-9)/(x+3)','R2':'(x^2-9)/(x^2+6*x+9)','R3':'(3-x)/(x^2-9)','N1':'3*4-2','N2':r'\sqrt{9}+\sqrt{16}','N3':'x^2*x^3','N4':'360000',
   'E1':'2*x+3=11','E2':r'\begin{cases}x+y=7\\x-y=1\end{cases}','E3':'x^2-9=0','E4':r'\frac{6}{x}=2','I1':'2*x+1>7','I2':'-2<x<=3',
   'U4':'已知实数m,n满足m-n=4，且m>3，n<2，求m(n+2)的取值范围。'}
  evidence=[]
  for topic,problem in sources.items():
   with self.subTest(topic=topic):
    sid='source_'+topic;cid='card_'+topic
    def create(v):
     v['wrong_cards'][sid]={'id':sid,'problem':problem,'knowledge_ids':[topic]}
     v['knowledge_cards'][cid]={'id':cid,'type':'knowledge','knowledge_id':topic,'title':topic,'rule':quiz.RULES.get(topic,'公式与原式条件。'),'status':'active','source_wrong_card_ids':[sid]}
    store.update('owner',create)
    classic=lesson.handle('owner',{'action':'open','card_id':cid})
    for variant in (0,1,2,5,50):
     item=lesson.handle('owner',{'action':'open' if variant==0 else 'next','card_id':cid,'variant':variant})
     replay=lesson.handle('owner',{'action':'open' if variant==0 else 'next','card_id':cid,'variant':variant});self.assertEqual(item,replay);self.assertEqual(item['knowledge_id'],topic)
     record=store.read('owner')['card_lessons'][cid+':'+str(variant)]
     self.assertGreaterEqual(len(record['worked_steps']),2 if variant==0 else 3)
     self.assertTrue(quiz._check(record,record['answer_latex']))
     # Independent checks derive numerical/algebraic results from actual prompt/q,
     # rather than treating the stored answer as proof of the question's meaning.
     if topic.startswith(('F','R')):
      expected=sp.factor(parse_math(record['q']));self.assertEqual(sp.cancel(parse_math(record['answer_latex'])-expected),0)
      if topic.startswith('R'):self.assertIn('原式条件',record['prompt']);self.assertTrue(variant==0 or '原分母' in record['worked_steps'][0])
     if topic.startswith(('N','E','I')):
      import re
      formula=record['prompt'].split(r'\(')[1].split(r'\)')[0]
      if topic.startswith('N'):
       self.assertEqual(sp.simplify(parse_math(formula)-parse_math(record['answer_latex'])),0)
      elif topic=='E2':
       body=formula.replace(r'\begin{cases}','').replace(r'\end{cases}','')
       yy=sp.Symbol('y');equations=[]
       for eq in body.split(r'\\'):
        lhs,rhs=eq.split('=');equations.append(parse_math(lhs)-parse_math(rhs))
       solution=sp.solve(equations,[sp.Symbol('x'),yy]);given=record['answer_latex'].replace(r'\left','').replace(r'\right','').strip('()').split(',')
       self.assertEqual([parse_math(v.strip()) for v in given],[solution[sp.Symbol('x')],solution[yy]])
      elif topic.startswith('E'):
       lhs,rhs=formula.split('=');eq=parse_math(lhs)-parse_math(rhs);roots=sp.solve(eq,sp.Symbol('x'))
       roots=[v for v in roots if sp.denom(sp.together(parse_math(lhs))).subs(sp.Symbol('x'),v)!=0]
       self.assertEqual(sp.FiniteSet(*roots),answer_set(record['answer_latex']))
      else:
       body=formula.replace(r'\begin{cases}','').replace(r'\end{cases}','').replace(r'\le','<=').replace(r'\ge','>=')
       actual=sp.S.Reals;xx=sp.Symbol('x')
       for rel in body.split(r'\\'):
        parts=re.split('(<=|>=|<|>)',rel);left,right=parse_math(parts[0]),parse_math(parts[2]);relation={'<':sp.Lt,'>':sp.Gt,'<=':sp.Le,'>=':sp.Ge}[parts[1]](left,right)
        actual=actual.intersect(sp.solve_univariate_inequality(relation,xx,relational=False))
       self.assertEqual(actual,answer_set(record['answer_latex']))
     if topic=='U4':
      p=record['matching']['parameters'];lo,hi,c,d=map(sp.Rational,[p['lower'],p['upper'],p['difference'],p['shift']]);interval=answer_set(record['answer_latex'])
      for j in range(1,12):
       m=lo+(hi-lo)*sp.Rational(j,12);self.assertTrue(interval.contains(m*(m-c+d)))
      self.assertTrue(any('顶点' in step for step in record['worked_steps']));self.assertTrue(any('端点' in step for step in record['worked_steps']))
     if topic=='I1' and variant%2:self.assertIn('不等号变向',''.join(record['worked_steps']))
     evidence.append({'knowledge':topic,'variant':variant,'prompt':record['prompt'],'answer':record['answer_latex'],'steps':record['worked_steps']})
    self.assertFalse(store.read('owner')['growth_events']);self.assertFalse(store.read('owner')['quizzes'])
  self.assertEqual(len(evidence),95)
  import os,json
  if os.environ.get('MYTREE_LESSON_EVIDENCE'):Path(os.environ['MYTREE_LESSON_EVIDENCE']).write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
 def test_composite_source_under_broad_topic_never_becomes_simple_arithmetic(self):
  def create(v):
   v['wrong_cards']['composite']={'id':'composite','knowledge_ids':['N1'],'problem':'已知实数m,n满足m-n=4，且m>3，n<2，求m(n+2)的取值范围。'}
   v['knowledge_cards']['card']={'id':'card','knowledge_id':'N1','title':'数的运算','rule':'先乘后加','status':'active','source_wrong_card_ids':['composite']}
  store.update('owner',create)
  for action,variant in [('open',0),('next',1)]:
   out=lesson.handle('owner',{'action':action,'card_id':'card','variant':variant});self.assertIn('取值范围',out['title']);self.assertIn('m',out['prompt']);self.assertIn('二次',out['rule'])
 def test_missing_or_unmatched_source_fails_without_fallback(self):
  def create(v):
   v['wrong_cards']['bad']={'id':'bad','knowledge_ids':['F2'],'problem':'求图形面积并证明辅助线关系'}
   v['knowledge_cards']['card']={'id':'card','knowledge_id':'F2','title':'F2','rule':'rule','status':'active','source_wrong_card_ids':['bad']}
  store.update('owner',create)
  with self.assertRaises(DomainError):lesson.handle('owner',{'action':'open','card_id':'card'})
  self.assertFalse(store.read('owner').get('card_lessons'))


class AuthenticatedLessonIsolationTests(unittest.TestCase):
 def test_authenticated_client_cannot_borrow_another_accounts_card(self):
  from test_auth import AuthTests
  fixture=AuthTests();fixture.setUp()
  try:
   owner,owner_cookie=fixture.login('lesson-owner@example.test');other,other_cookie=fixture.login('lesson-other@example.test')
   def create(v):
    v['wrong_cards']['source']={'id':'source','problem':'x^2-9','knowledge_ids':['F2']}
    v['knowledge_cards']['card']={'id':'card','knowledge_id':'F2','title':'平方差','rule':'平方差公式','status':'active','source_wrong_card_ids':['source']}
   store.update(owner['profile_id'],create)
   status,_,_=fixture.req('/api/knowledge/learn',{'student':owner['profile_id'],'action':'open','card_id':'card'},cookie=other_cookie);self.assertEqual(status,404)
   status,data,_=fixture.req('/api/knowledge/learn',{'student':other['profile_id'],'action':'open','card_id':'card'},cookie=owner_cookie);self.assertEqual(status,200);self.assertTrue(data['practice_only'])
   self.assertFalse(store.read(other['profile_id']).get('card_lessons'))
  finally:fixture.tearDown()
