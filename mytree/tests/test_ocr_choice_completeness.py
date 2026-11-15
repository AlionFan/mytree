"""Choice completeness guards preserve source roles and mathematical conditions."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import page_reading as page
from test_multiocr import item,raw_page

FULL='下列事件是确定事件的是（ ） A. 打开手机正好显示8点 B. 抛掷正方体骰子一次出现4点 C. 明天会下雨 D. 任意画一个三角形，它内角和等于360°'
class ChoiceCompletenessTests(unittest.TestCase):
 def source(self,problem,**changes):
  return item(problem=problem,problem_latex='',steps=[],question_type='probability',topic_id='P1',**changes)
 def out(self,source):return page.normalize_page(raw_page([source]),1,'completeness')['items'][0]
 def test_bare_explicit_choice_stems_are_not_complete(self):
  for problem in ['下列计算正确的是','下列事件是确定事件的是','以下说法正确的是','下面运算错误的是','下列计算正确的是 A. 1+1=2 B. 1+1=3','以下说法正确的是：A. 一个不完整选项','下列正确的是（ ）','若m-n=4，且m>3，n<2，则m(n+2)的值可能是（ ）']:
   with self.subTest(problem=problem):
    output=self.out(self.source(problem))
    self.assertFalse(output['problem_complete']);self.assertFalse(output['auto_ready']);self.assertFalse(output['lesson_ready'])
 def test_nonchoice_sentences_are_not_newly_classified_as_missing(self):
  for text in ['在三角形ABC中，AB=AC，求角B。','以下是计算过程，请检查。','下列数据的平均数是多少？','求下列方程的解：x+1=2。','任意举例，判断这个等式是否正确。']:
   self.assertFalse(page._missing_choice_options({'problem':text,'fragments':[]}),text)
 def test_missing_labels_and_empty_options_remain_incomplete(self):
  for problem in [FULL.rsplit(' D.',1)[0],FULL.rsplit(' D.',1)[0]+' D.',FULL.replace(' B.',' D.')]:
   output=self.out(self.source(problem));self.assertFalse(output['auto_ready']);self.assertFalse(output['lesson_ready'])
 def test_complete_choices_are_preserved_in_problem_and_fragments(self):
  output=self.out(self.source(FULL))
  self.assertTrue(output['auto_ready']);self.assertEqual(output['problem'],FULL)
  self.assertEqual(output['fragments'][0]['text'],FULL)
 def test_diagram_notes_never_supply_missing_choices(self):
  source=self.source('下列事件是确定事件的是（ ）');source['diagram_description']=FULL
  output=self.out(source)
  self.assertEqual(output['problem'],source['problem']);self.assertFalse(output['auto_ready']);self.assertFalse(output['lesson_ready'])
 def test_graphical_options_allow_individual_visible_descriptions(self):
  source=self.source('下列图形为轴对称图形的是（ ） A. 正方形 B. 一般平行四边形 C. 不等边三角形 D. 一般四边形')
  source.update(question_type='geometry',topic_id='G7',diagram_description='每个选项各有一个可见图形。')
  self.assertTrue(self.out(source)['auto_ready'])
 def test_options_missing_from_problem_fragments_stay_blocked(self):
  source=self.source(FULL);source['fragments'][0]['text']='下列事件是确定事件的是（ ）'
  output=self.out(source);self.assertFalse(output['auto_ready']);self.assertFalse(output['lesson_ready'])
 def test_inline_student_filling_remains_work_and_is_not_added_to_problem(self):
  problem='从三个信息选两个作为条件，另一个为结论。条件是____，结论是____，并证明。'
  source=self.source(problem);source.update(question_type='geometry',topic_id='G7',answer_presence='present',steps=['①②，③'])
  source['fragments'].append({'role':'student_work','script_kind':'handwritten','text':'①②，③','region':[.2,.2,.3,.1]})
  output=self.out(source);self.assertTrue(output['auto_ready'])
  self.assertEqual(output['problem'],problem);self.assertEqual(output['steps'],['①②，③'])
  source['steps']=[]
  output=self.out(source);self.assertFalse(output['auto_ready'])
  self.assertIn('作答步骤与原样笔迹片段不一致，先跳过这题。',output['attention_reasons'])
 def test_changed_conditions_or_student_work_cannot_be_equalized(self):
  for old,new in [('360°','180°'),('确定事件','随机事件')]:
   source=self.source(FULL);source['fragments'][0]['text']=FULL.replace(old,new)
   self.assertFalse(self.out(source)['auto_ready'])
  source=self.source(FULL);source['fragments'][0]['text']=FULL+' D为正确答案'
  self.assertFalse(self.out(source)['auto_ready'])
 def test_prompt_requires_all_source_options_and_inline_work(self):
  self.assertIn('不能代替题干中的选项',page.PAGE_PROMPT)
  self.assertIn('①②、③',page.PAGE_PROMPT)
  self.assertIn('不按解题结果倒改笔迹',page.PAGE_PROMPT)

if __name__=='__main__':unittest.main()
