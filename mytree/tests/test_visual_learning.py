"""Owned, bounded AI geometry: safe rendering is separate from mathematical truth."""
import copy,json,math,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,cards,profile,store,visual
from app.errors import DomainError
from test_all import _serve,_req

SPEC={'title':'平方差面积','steps':[{'caption':r'先找面积 \(x^2-9\)。','shapes':[{'type':'rect','x':10,'y':10,'w':60,'h':60,'color':0,'label':'x²'},{'type':'rect','x':50,'y':10,'w':20,'h':20,'color':2,'label':'9'}]}, {'caption':'剩下两块可以拼接。','shapes':[{'type':'rect','x':10,'y':20,'w':75,'h':30,'color':1,'label':'(x+3)(x−3)'}]}]}
class DiagramTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.tmp.name+'/profiles.json');self.patch.start()
  self.source=cards.study('owner',{'problem':'x^2-9','steps':['(x-3)^2']},'source',strict=False)['output']['wrong_card'];self.did=self.source['diagnosis_id']
  def generic(v):
   v['events'][-1]['analysis'].update(problem='已知三角形ABC，求角A。',knowledge_ids=['G1'],hints=[])
   v['wrong_cards'][self.source['id']].update(problem='已知三角形ABC，求角A。',knowledge_ids=['G1'])
  store.update('owner',generic)
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def call(self,**kw):return visual.diagram_lesson('owner',{'diagnosis_id':self.did,**kw})
 def test_derivation_is_validated_and_returned_without_arbitrary_geometry(self):
  raw={'title':'逐项核对','steps':[{'caption':'正确选项为B。','lines':[{'expression':r'\(a^3/a^2=a\)','reason':'除式有意义时 a≠0'}]}]*2}
  self.assertEqual(visual.validate_diagram(raw),raw)
  with patch('app.ai.complete',return_value=(raw,{})):
   result=self.call();self.assertIn('lines',result['steps'][0]);self.assertNotIn('svg',result['steps'][0])
  for line in [{'expression':'<img src=x onerror=alert(1)>','reason':'x'},{'expression':'x','reason':'<button>bad</button>'},{'expression':'x','reason':'ok','onclick':'evil'}]:
   bad=copy.deepcopy(raw);bad['steps'][0]['lines']=[line]
   with self.assertRaises(ValueError):visual.validate_diagram(bad)
 def test_text_solution_does_not_require_a_figure_for_geometric_families(self):
  raw={'title':'解题思路与步骤','steps':[
   {'caption':'先确定条件与方法。','lines':[{'expression':r'\(x-2\geq0\)','reason':'根号内非负'}]},
   {'caption':'再排除使分母为零的值，得到结论。','lines':[{'expression':r'\(x>2\)','reason':'分母不为零'}]}]}
  for problem in [r'求使式子 \(1/\sqrt{x-2}\) 有意义的x的取值范围。',
                  r'两个相似三角形的面积比为4:9，较大三角形周长为18，求较小三角形周长。',
                  r'已知一次函数 \(y=2x+1\)，求当x=2时的y值。']:
   # Tests acceptance of text-only structure, not mathematical correctness of this fixture.
   with self.subTest(problem=problem):
    self.assertEqual(visual.validate_source_diagram(visual.validate_diagram(raw),{'problem':problem}),raw)
 def test_optional_figure_keeps_source_validation(self):
  shape={'type':'linear_graph','x':8,'y':8,'w':84,'h':80,'a':3,'b':1,'x_min':-3,'x_max':3,'y_min':-5,'y_max':7,'label':'y=3x+1','color':1}
  raw={'title':'函数解法','steps':[{'caption':'先代入求值。','lines':[{'expression':r'\(y=2\times2+1=5\)','reason':'代入自变量'}]}, {'caption':'图像辅助观察对应点。','shapes':[shape]}]}
  with self.assertRaises(ValueError):
   visual.validate_source_diagram(visual.validate_diagram(raw),{'problem':r'已知函数 \(y=2x+1\)，求x=2时的y值。'})
 def test_no_figure_is_still_a_cached_full_solution(self):
  raw={'title':'解题思路与步骤','steps':[{'caption':'先由三角形内角和确定角的关系。','lines':[{'expression':r'\(A+B+C=180^\circ\)','reason':'三角形内角和'}]}, {'caption':'代入已知角，再求目标角。','lines':[{'expression':r'\(A=180^\circ-B-C\)','reason':'移项'}]}]}
  with patch('app.ai.complete',return_value=(raw,{})) as model:
   result=self.call();again=self.call()
   self.assertEqual(result,again);self.assertEqual(model.call_count,1)
   self.assertTrue(all('lines' in step and 'svg' not in step for step in result['steps']))
   self.assertEqual(result['max_hint_level_recorded'],3)
   self.assertTrue(all(key.startswith('v9:text-first:') for key in store.read('owner')['visual_lessons']))
 def test_algebra_choice_rejects_unrelated_geometry(self):
  problem='下列计算正确的是 A.(a-2)(a+2)=a²+4 B.a³÷a²=a C.(x+y)²=x²+xy+y² D.(ab²)³=a³b⁵'
  with self.assertRaises(ValueError):visual.validate_source_diagram(copy.deepcopy(SPEC),{'problem':problem})
 def test_screenshot_algebra_template_checks_original_options_without_model(self):
  problem=r'下列计算正确的是 A. \((a-2)(a+2)=a^2+4\) B. \(a^3÷a^2=a\) C. \((x+y)^2=x^2+xy+y^2\) D. \((ab^2)^3=a^3b^5\)'
  raw=visual._algebra_choice_template({'problem':problem})
  self.assertIsNotNone(raw);self.assertIn('B',raw['steps'][-1]['caption']);self.assertIn('a≠0',str(raw))
  visual.validate_diagram(raw)
  store.update('owner',lambda v:v['events'][-1]['analysis'].update(problem=problem,knowledge_ids=['F1'],hints=['现有条件无正确选项']))
  with patch('app.ai.complete') as model:
   result=self.call();model.assert_not_called();self.assertEqual(result['rendering'],'program_algebra_template')
 def test_numberline_label_cannot_contradict_interval_direction(self):
  shape={'type':'numberline','x':8,'y':55,'w':84,'min':-5,'max':1,'left':-2,'right':None,'left_open':True,'right_open':True,'label':'x < -2','color':1}
  raw={'title':'解集','steps':[{'caption':'向左','shapes':[shape]}]*2}
  with self.assertRaises(ValueError):visual.validate_source_diagram(visual.validate_diagram(raw),{'problem':'解不等式 -3x+2>8'})
 def test_negative_question_does_not_use_positive_identity_template(self):
  for prefix in ['下列计算不正确的是','下列计算错误的是','下列等式不成立的是']:
   p=prefix+' A.(a-2)(a+2)=a²+4 B.a³÷a²=a C.(x+y)²=x²+xy+y² D.(ab²)³=a³b⁵'
   self.assertIsNone(visual._algebra_choice_template({'problem':p}))
 def test_source_image_keeps_vision_role_and_text_uses_diagram_role(self):
  for image,role in [(None,'diagram'),('data:image/png;base64,SYNTHETIC','vision')]:
   store.update('owner',lambda v:v.update(visual_lessons={}))
   with patch('app.source_images.for_diagnosis',return_value=image),patch('app.ai.complete',return_value=(SPEC,{})) as model:
    self.call();self.assertEqual(model.call_args.args[0],role)
 def test_known_square_difference_uses_geometrically_consistent_program_template(self):
  for a in [1,3,20]:
   spec=visual._area_template({'problem':'分解因式：x^2-'+str(a*a)})
   self.assertIsNotNone(spec);visual.validate_diagram(spec)
   first=spec['steps'][0]['shapes'];remaining=spec['steps'][1]['shapes'];joined=spec['steps'][2]['shapes']
   area=lambda sh:sum(s['w']*s['h'] for s in sh if s['type']=='rect')
   self.assertAlmostEqual(first[0]['w']*first[0]['h']-first[1]['w']*first[1]['h'],area(remaining),places=6)
   self.assertAlmostEqual(area(remaining),area(joined),places=6)
   self.assertEqual(joined[0]['h'],joined[1]['h'])
 def test_cache_replay_records_explicit_full_access_without_awarding_progress(self):
  before=store.read('owner')
  with patch('app.ai.complete',return_value=(SPEC,{})) as model:
   a=self.call();b=self.call();self.assertEqual(a,b);self.assertEqual(model.call_count,1)
   content=json.loads(model.call_args.args[1][1]['content']);self.assertIn('三角形',content['problem']);self.assertEqual(model.call_args.args[0],'diagram')
  self.assertEqual(a['verification']['level'],'ai_review');self.assertEqual(a['max_hint_level_recorded'],3)
  after=store.read('owner')
  for key in ['quizzes','quiz_answers','growth_events','knowledge_cards','wrong_cards']:self.assertEqual(before[key],after[key])
  self.assertEqual(len(after['visual_lessons']),1);self.assertEqual(store.max_hint_level('owner',self.did),3)
 def test_source_context_change_invalidates_cache_and_foreign_id_rejected(self):
  with patch('app.ai.complete',return_value=(SPEC,{})) as model:
   self.call();store.update('owner',lambda v:v['events'][-1]['analysis'].update(domain=['x>3']))
   self.call();self.assertEqual(model.call_count,2)
   with self.assertRaises(DomainError):visual.diagram_lesson('other',{'diagnosis_id':self.did})
  for extra in [{'problem':'forged'},{'model':'evil'},{'url':'https://evil'},{'variant':1},{'quiz_id':'x'}]:
   with self.assertRaises(ValueError):self.call(**extra)
 def test_invalid_model_output_is_not_cached_or_recorded_and_retry_works(self):
  bad={**SPEC,'svg':'<script/>'}
  with patch('app.ai.complete',side_effect=[(bad,{}),(SPEC,{})]):
   with self.assertRaises(ai.ModelError):self.call()
   self.assertFalse(store.read('owner').get('visual_lessons'));self.assertEqual(store.max_hint_level('owner',self.did),0)
   self.assertTrue(self.call()['ok'])
 def test_refusal_and_network_failure_do_not_cache(self):
  for result in [{'unavailable':True},None]:
   with patch('app.ai.complete',side_effect=ai.ModelError('temporary') if result is None else None,return_value=(result,{})):
    with self.assertRaises(ai.ModelError):self.call()
   self.assertFalse(store.read('owner').get('visual_lessons'))
 def test_cache_limit_and_removed_source(self):
  store.update('owner',lambda v:v.update(visual_lessons={str(i):SPEC for i in range(40)}))
  with patch('app.ai.complete',return_value=(SPEC,{})):self.call()
  self.assertEqual(len(store.read('owner')['visual_lessons']),40)
  store.update('owner',lambda v:(v['events'].clear(),v['wrong_cards'].clear()))
  with self.assertRaises(DomainError):self.call()
 def test_singleflight_has_bounded_busy_result(self):
  lock=visual._DIAGRAM_LOCKS[int(visual.hashlib.sha256(('owner'+self.did).encode()).hexdigest()[:4],16)%16]
  lock.acquire()
  try:
   with self.assertRaises(ai.ModelError) as err:self.call()
   self.assertEqual(err.exception.status,429)
  finally:lock.release()
 def test_http_new_route_binds_profile(self):
  http,base=_serve()
  try:
   with patch('app.ai.complete',return_value=(SPEC,{})):
    status,raw=_req(base,'POST','/api/visual/lesson',{'student':'owner','diagnosis_id':self.did});self.assertEqual(status,200);self.assertTrue(json.loads(raw)['ok'])
    status,_=_req(base,'POST','/api/visual/lesson',{'student':'other','diagnosis_id':self.did});self.assertEqual(status,404)
  finally:http.shutdown();http.server_close()
 def test_authenticated_student_cannot_override_owner(self):
  from test_auth import AuthTests
  fixture=AuthTests();fixture.setUp()
  try:
   self.assertEqual(fixture.req('/api/visual/lesson',{'diagnosis_id':'not_owned'})[0],401)
   owner,oc=fixture.login('diagram-owner@example.test');other,fc=fixture.login('diagram-other@example.test')
   source=cards.study(owner['profile_id'],{'problem':'x^2-9','steps':['x^2']},'one',strict=False)['output']['wrong_card']
   with patch('app.ai.complete',return_value=(SPEC,{})) as model:
    status,_,_=fixture.req('/api/visual/lesson',{'student':owner['profile_id'],'diagnosis_id':source['diagnosis_id']},cookie=fc);self.assertEqual(status,404);model.assert_not_called()
    status,_,_=fixture.req('/api/visual/lesson',{'student':other['profile_id'],'diagnosis_id':source['diagnosis_id']},cookie=oc);self.assertEqual(status,200)
  finally:fixture.tearDown()
 def test_schema_bounds_nonfinite_unknown_fields_and_degenerate_shapes(self):
  cases=[]
  def mutate(shape):
   q=copy.deepcopy(SPEC);q['steps'][0]['shapes'][0]=shape;cases.append(q)
  for number in [True,-1,101,float('nan'),float('inf')]:mutate({'type':'point','x':number,'y':20,'label':'A','color':0})
  for shape in [{'type':'foreignObject','x':10,'y':20,'label':'x','color':0},{'type':'point','x':10,'y':20,'label':'x','color':0,'onclick':'evil'}, {'type':'circle','x':10,'y':10,'r':20,'label':'O','color':0},{'type':'rect','x':10,'y':10,'w':0,'h':20,'label':'x','color':0},{'type':'line','points':[[1,1],[1,1]],'label':'','color':0},{'type':'polygon','points':[[1,1],[2,2],[3,3]],'label':'','color':0}, {'type':'text','x':10,'y':20,'label':'x'*25,'color':0},{'type':'text','x':10,'y':20,'label':r'\frac{1}{x}','color':0}]:mutate(shape)
  q=copy.deepcopy(SPEC);q['steps'][0]['shapes']*=13;cases.append(q)
  for caption in ['<button data-quiz-card="evil">x</button>','https://evil.test/','[click](/api/secret)']:
   q=copy.deepcopy(SPEC);q['steps'][0]['caption']=caption;cases.append(q)
  for case in cases:
   with self.assertRaises((ValueError,TypeError)):visual.validate_diagram(case)
 def test_all_primitives_and_malicious_text_are_rendered_only_as_text(self):
  shapes=[{'type':'point','x':20,'y':20,'label':'<script>bad</script>','color':0},{'type':'text','x':50,'y':10,'label':'中文 ∠A x²','color':1},{'type':'circle','x':50,'y':50,'r':10,'label':'O','color':2},{'type':'line','points':[[10,20],[70,20]],'label':'6','color':3},{'type':'polyline','points':[[10,20],[20,30],[30,10]],'label':'','color':4},{'type':'polygon','points':[[10,20],[70,20],[40,70]],'label':'△ABC','color':0}]
  raw={'title':'<script>alert(1)</script>','steps':[{'caption':'辅助示意','shapes':shapes}]*2};spec=visual.validate_diagram(raw);svg=visual.diagram_svg(spec['steps'][0],spec['title'])
  self.assertNotIn('<script>',svg);self.assertNotIn('href=',svg);self.assertIn('&lt;script&gt;',svg);self.assertIn('circle',svg)
if __name__=='__main__':unittest.main()
