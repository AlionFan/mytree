"""扩大大纲后的判题边界与真实服务路由回归；不依赖付费 API。"""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sympy as sp
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,junior,profile
from app.formulas import parse_math,solution_set,answer_set,math_markdown
from app.junior_practice import generate,check
from app.curriculum import TOPICS
from test_all import _req,_serve

TEACHING={'hints':[r'先看已知条件。',r'把条件对应到通用规则。',r'再核对完整解法。'],
 'card':{'title':'本题知识','body':'先理解条件再运算。','tip':'核对边界与单位。'},'assessment':'模型认为正确，但这只是待核对意见。','knowledge_ids':['G9'],'answer_latex':'999'}

class FormulaTests(unittest.TestCase):
 def test_real_exam_arithmetic_and_exact_constants(self):
  value=parse_math(r'-1^{2024}+|2-\sqrt{3}|-\sqrt[3]{-27}+2\cos30^\circ')
  self.assertEqual(sp.simplify(value),4)
  self.assertEqual(sp.simplify(parse_math(r'\frac{7}{16}')),sp.Rational(7,16))
  self.assertEqual(sp.simplify(parse_math(r'1.75\times 10^{11}')),175000000000)
  self.assertFalse(parse_math(r'12\pi').free_symbols)
 def test_solution_sets_and_excluded_denominators(self):
  self.assertEqual(solution_set('x^2-5x+6=0'),sp.FiniteSet(2,3))
  self.assertEqual(solution_set(r'-2<x\le2'),sp.Interval.Lopen(-2,2))
  self.assertEqual(solution_set(r'\frac{x^2-1}{x-1}=2'),sp.EmptySet)
  self.assertNotIn(0,solution_set(r'\frac{x}{x}=1'))
 def test_parser_limits_and_no_commands(self):
  for source in [r'\href{https://x}{x}',r'\input{a}',r'\int x dx',r'x^{1000000}',r'\frac{1}{0}',r'2>1','__import__(os)']:
   with self.assertRaises(ValueError,msg=source):parse_math(source)
 def test_all_new_topic_templates_grade_their_expected_answers(self):
  for topic in TOPICS:
   for item in generate(topic,3):
    self.assertTrue(check(item,item['answer_latex'])[0],(topic,item['answer_latex']))
    self.assertFalse(check(item,'987654')[0],topic)
 def test_numeric_practice_requires_a_result_and_scientific_normalization(self):
  item={'grading':'number','answer_latex':'5'}
  self.assertFalse(check(item,'2+3')[0]);self.assertTrue(check(item,'5')[0])
  self.assertTrue(check({'grading':'number','answer_latex':'-2'},'-2')[0])
  item={'grading':'scientific','answer_latex':r'1.75\times10^{11}'}
  self.assertTrue(check(item,item['answer_latex'])[0]);self.assertFalse(check(item,r'0.175\times10^{12}')[0])
 def test_valid_individual_roots_are_not_falsely_marked_wrong(self):
  output=junior.program_check({'question_type':'equation','problem':'x^2-5x+6=0','steps':['x=2','x=3']})
  self.assertIsNone(output['first_error'])
 def test_copying_equivalent_original_is_incomplete(self):
  for kind,problem in [('calculate','2+3'),('equation','x^2-5x+6=0'),('inequality','2x+1>7')]:
   result=junior.program_check({'question_type':kind,'problem':problem,'steps':[problem]})
   self.assertEqual(result['rows'][-1]['ok'],'incomplete',(kind,result))
 def test_ocr_math_normalization_preserves_existing_delimiters_and_tables(self):
  self.assertEqual(math_markdown(r'当 $n\geq3$ 时'),r'当 $n\geq3$ 时')
  result=math_markdown(r'\begin{tabular}{|c|c|}时间&7时\\车流&18\\\end{tabular}')
  self.assertIn('| --- | --- |',result);self.assertNotIn('tabular',result)
 def test_known_final_answer_is_guarded_at_low_hint_levels(self):
  self.assertTrue(junior._reveals_final(r'所以 \(2+3=5\)','5'))
  self.assertFalse(junior._reveals_final(r'先看 \(2+3\) 的运算顺序。','5'))
 def test_partial_or_unparseable_work_stays_unchecked(self):
  output=junior.program_check({'question_type':'calculate','problem':'2+3','steps':['先把两个数相加','5']})
  self.assertIsNone(output['rows'][0]['ok']);self.assertTrue(output['rows'][1]['ok'])

class JuniorFlowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=profile._PATH;profile._PATH=self.temp.name+'/profile.json'
  self.httpd,self.base=_serve();self.student='junior-test'
  self.patch=patch('app.ai.complete',return_value=(TEACHING,{'model':'mock'}));self.patch.start()
 def tearDown(self):
  self.patch.stop();self.httpd.shutdown();self.httpd.server_close();profile._PATH=self.old;self.temp.cleanup()
 def post(self,path,**body):
  status,raw=_req(self.base,'POST',path,{'student':self.student,**body});self.assertEqual(status,200,raw);return json.loads(raw)
 def study(self,kind='geometry',topic='G9',problem='证明两个三角形全等。',steps=None,latex=''):
  return self.post('/api/study',problem=problem,steps=steps or [],problem_latex=latex,recognition={'question_type':kind,'topic_id':topic,'diagram_description':'图中给出一组对应角相等。'})
 def test_ai_cannot_certify_geometry_or_invent_wrong_history(self):
  result=self.study(steps=['由图可知两个三角形全等。']);a=result['analysis']
  self.assertEqual(a['status'],'ai_review');self.assertEqual(a['verification']['status'],'unavailable')
  self.assertIsNone(a['cause']);p=profile.get(self.student);self.assertFalse(p['causes']);self.assertFalse(any(k['lit'] for k in p['tree']))
 def test_no_work_is_not_a_mistake_and_all_topics_appear(self):
  result=self.study();self.assertEqual(result['analysis']['status'],'not_attempted')
  p=profile.get(self.student);self.assertEqual(p['history'],0);self.assertEqual(len(p['tree']),37);self.assertEqual(len(p['chapters']),9)
 def test_program_result_overrides_wrong_model_answer(self):
  result=self.study('calculate','N1',r'计算 \(2+3\)。',['4'],'2+3');a=result['analysis']
  self.assertEqual(a['target_latex'],'5');self.assertEqual(a['status'],'wrong_step');self.assertEqual(a['first_error'],1)
  self.assertEqual(profile.get(self.student)['reviews'][0]['kp'],'N1')
 def test_question_formula_can_be_extracted_from_single_markdown_block(self):
  result=self.study('calculate','N1',r'（1）计算：$2+3$。',[r'解：$=2+3=5$'])
  self.assertEqual(result['analysis']['problem_latex'],'2+3')
  self.assertEqual(result['analysis']['status'],'correct')
 def test_new_topic_practice_feedback_and_review_loop(self):
  result=self.study('calculate','N1',r'计算 \(2*3-1\)。',[], '2*3-1');rid=result['diagnosis_id']
  practice=self.post('/api/practice',diagnosis_id=rid)
  for item in practice['items']:
   self.assertNotIn('expected',item);self.assertNotIn('answer_latex',item)
   answer=profile._load()[self.student]['exercises'][item['id']]['answer_latex']
   self.assertTrue(self.post('/api/practice/check',exercise_id=item['id'],answer=answer)['correct'])
  self.post('/api/feedback',diagnosis_id=rid,rating='confusing')
  self.post('/api/feedback',diagnosis_id=rid,rating='incorrect')
  p=profile.get(self.student);self.assertEqual(p['practice_correct'],3);self.assertEqual(p['feedback_count'],2)
  self.assertEqual(profile.diagnosis_for(self.student,rid)['prompt_version'],junior.PROMPT_VERSION)
  self.assertEqual(profile._load()[self.student]['feedback'][-1]['review_status'],'unreviewed')
 def test_missing_probability_conditions_do_not_invent_practice(self):
  result=self.study('probability','P2','求至少一人选 D 的概率。');rid=result['diagnosis_id']
  status,raw=_req(self.base,'POST','/api/practice',{'student':self.student,'diagnosis_id':rid})
  self.assertEqual(status,422);self.assertEqual(json.loads(raw)['code'],'UNSUPPORTED')
  self.assertFalse(profile._load()[self.student]['exercises'])
  self.post('/api/feedback',diagnosis_id=rid,rating='confusing')
  self.assertEqual(profile.get(self.student)['feedback_count'],1)
 def test_ocr_warnings_do_not_grade_before_confirmation(self):
  from test_ai import sample_image
  value={'problem':r'计算 \(2+3\)。','problem_latex':'2+3','steps':['4'],'question_type':'calculate','topic_id':'N1',
         'supported':True,'multiple_questions':False,'warnings':['学生结果为4，正确应为5，因为2加3等于5。'*15], 'uncertain_lines':[]}
  with patch('app.ai.complete',return_value=(value,{})):
   recognized=ai.recognize(sample_image(),cfg=ai.Settings(key='mock'))
  self.assertEqual(recognized['steps'],['4'])
  self.assertNotIn('正确',str(recognized['warnings']));self.assertNotIn('应为',str(recognized['warnings']))
 def test_model_control_delimiters_are_rejected_before_display(self):
  value={**TEACHING,'hints':['方向\x00x^2\x00','关键','完整']}
  with patch('app.ai.complete',return_value=(value,{})):
   with self.assertRaises(ai.ModelError) as error:junior.study({'problem':'证明三角形全等。','steps':[],'recognition':{'question_type':'geometry','topic_id':'G9'}})
  self.assertEqual(error.exception.code,'TEACHING_MATH_FORMAT_INVALID')
 def test_math_assets_are_local_and_private_files_are_blocked(self):
  for path in ['/math-ui.js','/vendor/katex/katex.min.js','/vendor/mathlive/mathlive.min.js','/vendor/mathlive/fonts/KaTeX_Main-Regular.woff2']:
   self.assertEqual(_req(self.base,'GET',path)[0],200,path)
  for path in ['/vendor/../../.env.local','/.env.local','/data/evaluation/probability.jpg']:
   self.assertEqual(_req(self.base,'GET',path)[0],404,path)
 def test_correct_factorization_still_has_teaching_and_practice(self):
  result=self.study('factor','F2',r'因式分解 \(x^2-9\)。',['(x-3)(x+3)'],r'x^2-9')
  self.assertEqual(result['analysis']['status'],'correct');self.assertEqual(len(result['analysis']['hints']),2);self.assertEqual(result['analysis']['hint_levels_available'],3)
  self.assertTrue(self.post('/api/hint',diagnosis_id=result['diagnosis_id'],level=3)['text'])
  self.assertEqual(len(self.post('/api/practice',diagnosis_id=result['diagnosis_id'])['items']),3)
 def test_legacy_factorization_still_uses_the_verified_engine(self):
  result=self.study('factor','F2','因式分解',['(x-3)^2'],r'x^2-9')
  self.assertEqual(result['analysis']['engine'],'algebra');self.assertEqual(result['analysis']['cause'],'F-MIX-FORMULA')

if __name__=='__main__':unittest.main(verbosity=2)
