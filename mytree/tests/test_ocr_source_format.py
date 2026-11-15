"""Presentation/coordinate changes cannot manufacture mathematical agreement."""
import copy,math,unittest
from app import page_reading as page
from test_multiocr import item,raw_page

class SourceFormatTests(unittest.TestCase):
 def test_named_boxes_all_levels_external_arrays(self):
  value=item();value['region']={'x':0,'y':0,'width':1,'height':.4}
  for f in value['fragments']:
   x,y,w,h=f['region'];f['region']=dict(x=x,y=y,width=w,height=h)
  raw=raw_page([value]);raw['unassigned_fragments']=[dict(role='teacher_annotation',script_kind='printed',text='阅',region=dict(x=0,y=.8,width=.1,height=.1))]
  out=page.normalize_page(raw,1,'named')
  self.assertTrue(out['items'][0]['auto_ready'])
  self.assertEqual(out['items'][0]['region'],[0,0,1,.4])
  self.assertTrue(all(isinstance(f['region'],list) for f in out['items'][0]['fragments']+out['unassigned_fragments']))
 def test_boxes_do_not_guess_unmarked_xyxy(self):
  self.assertEqual(page._box([.1,.2,.3,.4]),[.1,.2,.3,.4])
  for box in ([.35,.42,.88,.58],dict(x=.35,y=.42,right=.88,bottom=.58),dict(x=0,y=0,width=1,height=1,format='xyxy')):
   with self.assertRaises(ValueError):page._box(box)
 def test_invalid_coordinates(self):
  for box in ([-.1,0,1,1],[0,0,0,1],[0,0,1,-1],[0,.9,1,.2],[0,0,float('nan'),1],[0,0,True,1],dict(x=0,y=0,width=1),dict(x=0,y=0,width=1,height=2)):
   with self.subTest(box=box),self.assertRaises(ValueError):page._box(box)
 def test_safe_presentation_equivalence(self):
  pairs=[('21．（本题满分10分）已知$a_{1}\\leq 26$。','已知$a_1≤26$'),(r'在$\triangle ABC$中，$\angle A=\alpha$，$a\bot b$。','在△ABC中，∠A=α，a⊥b'),(r'$\sin\alpha\approx0.5$','sinα≈0.5')]
  for a,b in pairs:self.assertEqual(page._transcript_key(a,'21',True),page._transcript_key(b,'21',True))
 def test_true_changes_control_damage_and_role_remain_blocked(self):
  for a,b in [('x=26','x=71'),(r'\sqrt{5}',r'\sqrt{15}'),('x<2','x≤2'),('x=1且y=2','x=1'),('x=0.5','x=05'),('x+1','x-1'),('任意三角形内角和360°','任意三角形内角和180°'),('\triangle ABC','△ABC'),('\bot','⊥')]:
   self.assertNotEqual(page._transcript_key(a,problem=True),page._transcript_key(b,problem=True))
  value=item();value['fragments'][0]['text']='x^2-16'
  self.assertFalse(page.normalize_page(raw_page([value]),1,'bad')['items'][0]['auto_ready'])
  value=item();value['fragments'][1]['role']='teacher_annotation'
  self.assertFalse(page.normalize_page(raw_page([value]),1,'roles')['items'][0]['auto_ready'])
 def test_chinese_question_punctuation_not_math_placeholders(self):
  for text in ['此次改造是否符合安全要求?', '为什么这样做？', '共有多少种方法?', r'已知$x=2$，面积是多少?']:
   self.assertFalse(page._unclear_symbols(text),text)
  for text in ['x=?', '面积是多少??', '面积是多少�', r'$是否x=?$', r'\(多少?\)', 'x+?=2', '请核对?', '是否x?', '是否等于2?', '是否成立?x=2', r'$x=2 面积是多少?']:
   self.assertTrue(page._unclear_symbols(text),text)
  value=item(problem='这个等式是否成立?',problem_latex='',question_type='other',steps=[])
  value['uncertain_lines']=[0]
  self.assertFalse(page.normalize_page(raw_page([value]),1,'uncertain')['items'][0]['auto_ready'])
 def test_saved_p4_question22_replay_without_raw_changes(self):
  from pathlib import Path
  import json
  source=Path(__file__).resolve().parents[2]/'docs/evidence/ocr-source-format/named/p4-raw.json'
  if not source.exists():self.skipTest('local authorized real-source evidence unavailable')
  raw=json.loads(source.read_text());out=page.normalize_page(raw,1,'replay')
  self.assertTrue(next(v for v in out['items'] if v['printed_number']=='22')['auto_ready'])
 def test_choice_options_cannot_be_replaced_by_diagram_notes(self):
  value=item(problem='下列事件是确定事件的是（）',problem_latex='',steps=[],question_type='probability',topic_id='P1')
  value['diagram_description']='选项A: 打开手机正好显示8点；选项B: 掷骰子出现4点；选项C: 明天会下雨；选项D: 三角形内角和360°'
  out=page.normalize_page(raw_page([value]),1,'missing')['items'][0]
  self.assertFalse(out['problem_complete']);self.assertFalse(out['auto_ready']);self.assertFalse(out['lesson_ready'])
  self.assertEqual(out['problem'],value['problem'])
  value['problem']+=' A. 打开手机8点 B. 掷骰子4点 C. 明天下雨 D. 三角形内角和360°'
  value['fragments'][0]['text']=value['problem']
  self.assertTrue(page.normalize_page(raw_page([value]),1,'full')['items'][0]['auto_ready'])
 def test_graph_choices_and_nonchoice_geometry(self):
  value=item(problem='下列图形为轴对称图形的是（） A. 正方形 B. 一般平行四边形 C. 不等边三角形 D. 一般四边形',problem_latex='',steps=[],question_type='geometry',topic_id='G7')
  self.assertTrue(page.normalize_page(raw_page([value]),1,'graphs')['items'][0]['auto_ready'])
  self.assertFalse(page._missing_choice_options({'problem':'三角形ABC中，AB=AC，求角B。','diagram_description':'点A、B、C位于三角形的三个顶点。','fragments':[]}))
  for text in ['下列说法正确的是（）','单项选择题：任意一题','下列是（） A.一 B.二 C.三 D.']:
   self.assertTrue(page._missing_choice_options({'problem':text,'fragments':[]}))
 def test_prompt_all_regions_named_and_json_escaping(self):
  self.assertNotIn('"region":[',page.PAGE_PROMPT)
  self.assertIn('"width":1',page.PAGE_PROMPT)
  self.assertIn(r'\\triangle',page.PAGE_PROMPT)

if __name__=='__main__':unittest.main()
