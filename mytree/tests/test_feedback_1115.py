import base64,copy,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app import junior,profile,source_patterns,quiz,matching,teaching_memory,store,visual,page_reading

class FeedbackTests(unittest.TestCase):
 def test_three_source_families_generate_correct_and_nontrivial_exercises(self):
  cases=[(r'若式子 \(\frac{1}{\sqrt{x-1}}\) 在实数范围内有意义，求x取值范围。','expression-domain'),(r'因式分解：\(a^2-4ab+4b^2\)。','perfect-square-polynomial'),(r'两个相似图形的面积比为 \(4:9\)，较大图形周长100 cm，求较小周长。','similar-area-perimeter'),('数据1750亿用科学计数法表示。','scientific-notation')]
  for problem,family in cases:
   match=source_patterns.classify(problem);self.assertEqual(match['family'],family)
   for seed in ['a','b','c']:
    items=quiz._group('F3',1,seed,match);self.assertEqual(len(items),3)
    self.assertTrue(items[-1]['is_transfer'])
    for item in items:
     self.assertTrue(quiz._check(item,item['answer_latex']));self.assertFalse(quiz._check(item,'1234567'))
     self.assertEqual(item['matching']['family'],family)
 def test_owned_source_ai_practice_uses_original_without_mastery_writes(self):
  cases=[('若1/sqrt(x-1)有意义，求x范围。','N2'),('因式分解a^2-4ab+4b^2。','F3'),('相似三角形面积比4:9，小周长100，求另一周长。','G5'),('1750亿用科学计数法表示。','N4')]
  generated={'items':[{'question':f'合成条件变式{n}，求解。','answer':str(n),'solution':f'使用对应方法得到{n}。','relation':'合成协议夹具','answer_kind':'text'} for n in (1,2,3)]}
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/profiles.json'):
   for index,(problem,kp) in enumerate(cases):
    owner='case'+str(index)
    store.update(owner,lambda p:p['wrong_cards'].update(source={'id':'source','diagnosis_id':'diag','problem':problem,'knowledge_ids':[kp]}))
    before=store.read(owner)
    with patch('app.ai.complete',return_value=(generated,{})) as call:result=profile.create_exercises(owner,diagnosis_id='diag')
    self.assertEqual(len(result['items']),3);self.assertIn(problem,call.call_args.args[1][-1]['content'])
    for public in result['items']:
     self.assertNotIn('reference_answer',public)
     with patch('app.ai.complete',return_value=({'feedback':'请核对条件。'},{})):
      self.assertIsNone(profile.submit_answer(owner,public['id'],'1')['correct'])
    after=store.read(owner)
    for key in ('lit','kp_correct','practice_correct','events','reviews','quiz_answers'):self.assertEqual(before[key],after[key])
 def test_source_geometry_rejects_wrong_endpoints_and_coefficients(self):
  line={'type':'numberline','x':8,'y':55,'w':84,'min':-2,'max':5,'left':1,'right':None,'left_open':False,'right_open':True,'color':1,'label':'x≥1'}
  spec={'title':'定义域','steps':[{'caption':'根式限制','shapes':[line]},{'caption':'分母限制','shapes':[{**line,'left_open':True,'label':'x>1'}]}]}
  source={'problem':r'若式子 \(\frac{1}{\sqrt{x-1}}\) 在实数范围内有意义，求x的取值范围。'}
  visual.validate_source_diagram(visual.validate_diagram(spec),source)
  wrong=copy.deepcopy(spec);wrong['steps'][-1]['shapes'][0]['left_open']=False
  with self.assertRaises(ValueError):visual.validate_source_diagram(visual.validate_diagram(wrong),source)
  pair={'type':'similar_pair','x':8,'y':20,'w':84,'h':60,'area_small':4,'area_large':9,'label':'4:9','color':1}
  spec={'title':'相似','steps':[{'caption':'条件','shapes':[pair]}]*2}
  source={'problem':'两个相似图形面积比4:9，较小周长100，求较大周长。'}
  visual.validate_source_diagram(visual.validate_diagram(spec),source)
  wrong=copy.deepcopy(spec);wrong['steps'][0]['shapes'][0]['area_large']=16
  with self.assertRaises(ValueError):visual.validate_source_diagram(visual.validate_diagram(wrong),source)
 def test_no_similarity_is_not_guessed_from_ratio_and_perimeter(self):
  self.assertIsNone(source_patterns.classify('两个不规则图形面积比4:9，周长100，求另一周长。'))
 def test_memory_owner_retrieval_revocation_and_source_withdrawal(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/profiles.json'),patch.dict(os.environ,{'MYTREE_MEMORY_DB':d+'/memory.db'}):
   original=store.read('one')
   store.update('one',lambda v:v['wrong_cards'].update(a={'id':'a','problem':'test','knowledge_ids':['F2'],'study_status':'ai_review','student_steps':['x']}))
   before=store.read('one');teaching_memory.remember_preference('one','visual');v=teaching_memory.retrieve('one','F2')
   self.assertEqual(len(v['records']),2);self.assertFalse(v['training']);self.assertTrue(v['knowledge_sources'])
   self.assertFalse(teaching_memory.retrieve('two','F2')['records'])
   fact=next(r for r in v['records'] if r['type']=='fact');self.assertIn('ai_review',fact['content']);self.assertEqual(fact['source_event_ids'][0],'a')
   teaching_memory.forget('one',fact['id']);self.assertEqual(len(teaching_memory.retrieve('one','F2')['records']),1)
   self.assertEqual(before,store.read('one'))
   teaching_memory.remember_preference('one','steps');self.assertEqual(teaching_memory.retrieve('one')['records'][0]['content'],'分步思考')
   store.update('one',lambda v:v['wrong_cards'].clear());self.assertEqual(len(teaching_memory.retrieve('one','F2')['records']),1)
 def test_ocr_views_keep_full_anchor_and_overlapping_global_coordinates(self):
  im=Image.new('RGB',(1600,2400),'white');out=io.BytesIO();im.save(out,format='JPEG');views=page_reading.vision_views('data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode());self.assertEqual(sum(x['type']=='image_url' for x in views),3);self.assertIn('0.42',views[4]['text']);self.assertIn('只输出一次',views[4]['text'])
 def test_lesson_uncertain_work_is_not_recalled_as_a_student_fact(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'),patch.dict(os.environ,{'MYTREE_MEMORY_DB':d+'/m.db'}):
   store.update('one',lambda v:v['wrong_cards'].update(a={'id':'a','type':'lesson','problem':'known original','knowledge_ids':['F2'],'student_steps':['uncertain work'],'verification':{'level':'ai_review'},'_source':{'mode':'lesson_only'}}))
   fact=json.loads(teaching_memory.retrieve('one','F2')['records'][0]['content']);self.assertEqual(fact['student_steps'],[]);self.assertEqual(fact['original_work_status'],'unreliable');self.assertEqual(fact['study_mode'],'lesson_only');self.assertEqual(fact['verification']['level'],'ai_review')
 def test_topic_correction_expires_old_memory_key(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'),patch.dict(os.environ,{'MYTREE_MEMORY_DB':d+'/m.db'}):
   store.update('one',lambda v:v['wrong_cards'].update(a={'id':'a','problem':'known original','knowledge_ids':['F2'],'student_steps':[]}))
   self.assertEqual(len(teaching_memory.retrieve('one','F2')['records']),1)
   store.update('one',lambda v:v['wrong_cards']['a'].update(knowledge_ids=['U3']))
   self.assertEqual(teaching_memory.retrieve('one','F2')['records'],[]);self.assertEqual(len(teaching_memory.retrieve('one','U3')['records']),1)
 def test_chat_preserves_lesson_mode_and_memory_source_context(self):
  a={'problem':'known original','status':'not_attempted','study_mode':'lesson_only','hints':['方向','关键','完整'],'teaching_memory':{'records':[{'source_event_ids':['actual_source'],'content':'unreliable original work excluded'}]}}
  with patch('app.ai.complete',return_value=({'reply':'先看题目条件。','equations':[]},{})) as model:junior.chat(a,'怎么想？')
  context=json.loads(model.call_args.args[1][1]['content']);self.assertEqual(context['study_mode'],'lesson_only');self.assertEqual(context['teaching_memory']['records'][0]['source_event_ids'],['actual_source'])
 def test_removed_meta_does_not_remove_real_parameter_conditions(self):
  text='若a=0，三个函数值相等。以上是依据图片作出的判断，程序校验不可用，尚待核对。'
  self.assertEqual(junior.clean_teaching_meta(text),'若a=0，三个函数值相等。')
 def test_original_triangle_form_area_ratio_and_missing_similarity(self):
  import xml.etree.ElementTree as ET
  for p,q in [(4,9),(9,16),(25,49)]:
   pair={'type':'similar_pair','x':8,'y':20,'w':84,'h':60,'area_small':p,'area_large':q,'label':f'{p}:{q}','color':1}
   spec={'title':'相似三角形','steps':[{'caption':'面积比确定相似比。','shapes':[pair]}]*2};source={'problem':f'如果两个相似三角形的面积之比为{p}:{q}，较小三角形周长100cm，求另一个周长。'}
   valid=visual.validate_source_diagram(visual.validate_diagram(spec),source);self.assertEqual(valid['steps'][0]['shapes'][0]['form'],'triangle')
   svg=visual.diagram_svg(valid['steps'][0],valid['title']);root=ET.fromstring(svg);polygons=root.findall('.//{http://www.w3.org/2000/svg}polygon');self.assertEqual(len(polygons),2);self.assertNotIn('<rect',svg)
   def area(poly):
    v=[tuple(map(float,x.split(','))) for x in poly.attrib['points'].split()];return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(v,v[1:]+v[:1])))/2
   self.assertAlmostEqual(area(polygons[0])/area(polygons[1]),p/q,places=4)
   bad=copy.deepcopy(spec);bad['steps'][0]['shapes'][0]['form']='square'
   with self.assertRaises(ValueError):visual.validate_source_diagram(visual.validate_diagram(bad),source)
   with self.assertRaises(ValueError):visual.validate_source_diagram(visual.validate_diagram(spec),{'problem':'两个图形面积比4:9，较小周长100cm。'})
 def test_triangle_cache_second_open_keeps_source_form(self):
  pair={'type':'similar_pair','x':8,'y':20,'w':84,'h':60,'area_small':4,'area_large':9,'label':'4:9','color':1}
  spec={'title':'相似三角形','steps':[{'caption':'面积比确定相似比。','shapes':[pair]}]*2}
  problem='如果两个相似三角形的面积之比为4:9，较小三角形周长100cm，求另一个周长。'
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'):
   record=profile.record('triangle',{'problem':problem,'status':'not_attempted','lesson_kp':'G5','knowledge_ids':['G5'],'hints':['方向','关键','完整']},problem)
   with patch('app.ai.complete',return_value=(spec,{})) as model:
    first=visual.diagram_lesson('triangle',{'diagnosis_id':record['id']});second=visual.diagram_lesson('triangle',{'diagnosis_id':record['id']})
   self.assertEqual(model.call_count,0);self.assertEqual(first,second);self.assertEqual(second['rendering'],'stored_text_solution');self.assertEqual(second['problem'],problem);self.assertIn('完整',str(second['steps']))
 def test_numberline_svg_and_text_only_rejection(self):
  line={'type':'numberline','x':8,'y':55,'w':84,'min':-2,'max':5,'left':1,'right':None,'left_open':True,'right_open':True,'color':1,'label':'x>1'}
  spec={'title':'定义域','steps':[{'caption':'根式与分母限制','shapes':[line]}]*2};valid=visual.validate_diagram(spec);svg=visual.diagram_svg(valid['steps'][0],valid['title']);self.assertIn('data-open="true"',svg);self.assertIn('data-numberline',svg)
  spec['steps']=[{'caption':'文字','shapes':[{'type':'text','x':50,'y':50,'color':0,'label':'x>1'}]}]*2
  with self.assertRaises(ValueError):visual.validate_diagram(spec)
if __name__=='__main__':unittest.main()
