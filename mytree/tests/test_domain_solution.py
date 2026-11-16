import tempfile,unittest
from unittest.mock import patch
from app import visual,profile,store
class DomainSolutionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  p=patch('app.profile._PATH',self.tmp.name+'/p.json');p.start();self.addCleanup(p.stop)
 def run_lesson(self,problem,hints=None):
  analysis={'problem':problem,'hints':hints or ['先列条件。','条件取交集。','完整解法。'],'knowledge_ids':['N2'],'diagram_description':''}
  store.update('owner',lambda p:p['wrong_cards'].update(source={'id':'source','diagnosis_id':'diag','problem':problem,'knowledge_ids':['N2'],'_analysis':analysis}))
  with patch('app.ai.complete',side_effect=AssertionError('must not call drawing model')),patch('app.source_images.for_diagnosis',side_effect=AssertionError('saved text must not require original photo')):
   return visual.diagram_lesson('owner',{'diagnosis_id':'diag'})
 def test_denominator_root_requires_strict_endpoint_and_no_model(self):
  out=self.run_lesson(r'若式子 \(\frac{1}{\sqrt{x-1}}\) 在实数范围内有意义，则x的取值范围是____。')
  self.assertEqual(out['rendering'],'program_domain_solution');self.assertIn('(1,',str(out));self.assertNotIn('[1,',str(out));self.assertTrue(all('lines'in s for s in out['steps'][:3]));self.assertIn('svg',out['steps'][-1]);self.assertEqual(out['max_hint_level_recorded'],3)
 def test_plain_root_includes_endpoint(self):
  out=self.run_lesson(r'求式子 \(\sqrt{x-1}\) 的定义域。');self.assertIn('[1,',str(out))
 def test_negative_coefficient_domain_and_cache_replay(self):
  problem=r'求式子 \(\frac{2}{\sqrt{3-2x}}\) 的定义域。'
  a=self.run_lesson(problem);b=self.run_lesson(problem);self.assertEqual(a['steps'],b['steps']);self.assertIn(r'\frac{3}{2}',str(a).replace('\\\\','\\'))
 def test_unknown_geometry_uses_saved_text_not_new_drawing(self):
  out=self.run_lesson('证明两个三角形全等。',['先对应边角。','找全等条件。',r'由已知两边及夹角对应相等，按SAS得到两三角形全等。'])
  self.assertEqual(out['rendering'],'stored_text_solution');self.assertIn('SAS',str(out));self.assertIn('AI参考',out['verification']['label'])
 def test_extra_conditions_are_not_silently_ignored(self):
  problem=r'已知x是整数，求 \(1/\sqrt{x-1}\) 有意义的条件。'
  self.assertIsNone(visual._domain_solution_template({'problem':problem}))
 def test_single_final_numberline_checks_exact_domain_not_closed_radicand(self):
  import copy
  problem=r'求式子 \(1/\sqrt{x-1}\) 的定义域。'
  template=visual._domain_solution_template({'problem':problem})
  visual.validate_source_diagram(visual.validate_diagram(template),{'problem':problem})
  for field,value in [('left_open',False),('left',2)]:
   wrong=copy.deepcopy(template);wrong['steps'][-1]['shapes'][0][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):visual.validate_source_diagram(visual.validate_diagram(wrong),{'problem':problem})
 def test_extra_discrete_sign_and_membership_conditions_reject_program_branch(self):
  for problem in [r'若x为偶数，式子 \(1/\sqrt{x-1}\) 有意义，求x的取值范围。',
                  r'若x为正实数，式子 \(\sqrt{4-x}\) 有意义，求x的范围。',
                  r'若式子 \(1/\sqrt{x-1}\) 有意义，且x∈[2,3]，求x的范围。',
                  r'求式子 \(1/\sqrt{x-1}\) 有意义的条件，另满足 \(x<3\)。']:
   with self.subTest(problem=problem):self.assertIsNone(visual._domain_solution_template({'problem':problem}))
 def test_standard_question_number_and_wording_keep_exact_program_solution(self):
  for problem in [r'7. 若式子 \(\frac{1}{\sqrt{x-1}}\) 在实数范围内有意义，则x的取值范围是____。',
                  r'求使式子 $\sqrt{2x+4}$ 有意义的自变量x的范围。']:
   with self.subTest(problem=problem):self.assertIsNotNone(visual._domain_solution_template({'problem':problem}))
 def test_stored_text_preserves_math_and_full_solution(self):
  out=self.run_lesson('求一次函数的函数值。',['代入已知量。','注意运算顺序。',r'代入 \(y=2\times2+1\)。计算得 \(y=5\)。'])
  self.assertIn(r'\times',str(out).replace('\\\\','\\'));self.assertEqual(out['rendering'],'stored_text_solution')
  expressions=[line['expression'] for step in out['steps'] for line in step.get('lines',[])]
  self.assertTrue(any(r'\(y=2\times2+1\)' in line for line in expressions))
  self.assertTrue(all(line.count(r'\(')==line.count(r'\)') for line in expressions))
if __name__=='__main__':unittest.main()
