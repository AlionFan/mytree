"""Strict teaching levels and retry transactions; no live model calls."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,cards,junior,page_reading,profile,store
from app.reading_registry import ReadingRegistry
from test_multiocr import item,raw_page

VALID={'hints':{'level_1':'先回忆确定事件的定义。','level_2':'注意必然发生和不可能发生都属于确定事件。','level_3':'三角形内角和为180度，内角和为360度是不可能事件，因此选择D。'},
 'card':{'title':'事件分类','body':'确定事件包括必然事件与不可能事件，随机事件的结果不能事先确定。','tip':'注意不可能事件也属于确定事件。'},'answer_latex':'D','assessment':'尚未作答','knowledge_ids':['P1']}
BODY={'problem':'说明确定事件和随机事件的区别。','steps':[], 'recognition':{'question_type':'probability','topic_id':'P1'}}

class TeachingOutputTests(unittest.TestCase):
 def test_explicit_levels_are_ordered_by_key_not_json_insertion(self):
  value=copy.deepcopy(VALID);value['hints']=dict(reversed(list(value['hints'].items())))
  with patch('app.ai.complete',return_value=(value,{})):
   result=junior.study(BODY)['analysis']
  self.assertEqual(result['hints'],list(VALID['hints'].values()))
  self.assertEqual(result['status'],'not_attempted');self.assertEqual(result['verification']['status'],'unavailable')
 def test_legacy_three_levels_remain_compatible(self):
  value=copy.deepcopy(VALID);value['hints']=list(value['hints'].values())
  self.assertEqual(junior._teaching_fields(value)[0],value['hints'])
 def test_four_unlabelled_steps_are_rejected_without_paid_retry(self):
  value=copy.deepcopy(VALID);value['hints']=['定义','分析A','分析B','分析C与D']
  with patch('app.ai.complete',return_value=(value,{})) as model:
   with self.assertRaises(ai.ModelError) as error:junior.study(BODY)
  self.assertEqual(model.call_count,1);self.assertEqual(error.exception.code,'TEACHING_OUTPUT_INVALID')
  self.assertIn('只重试这道题',str(error.exception));self.assertIn('无需重新识别',str(error.exception))
 def test_missing_or_extra_levels_and_blank_fields_are_rejected(self):
  values=[]
  for hints in [{'level_1':'方向','level_2':'步骤'}, {**VALID['hints'],'level_4':'多余'}, {**VALID['hints'],'level_3':''}, ['方向','步骤']]:
   value=copy.deepcopy(VALID);value['hints']=hints;values.append(value)
  for k in ['title','body','tip']:
   value=copy.deepcopy(VALID);value['card'][k]=' ';values.append(value)
  for value in values:
   with self.subTest(value=value),self.assertRaises(ai.ModelError):junior._teaching_fields(value)
 def test_oversize_and_control_delimiters_remain_rejected(self):
  value=copy.deepcopy(VALID);value['hints']['level_3']='x'*1801
  with self.assertRaises(ai.ModelError):junior._teaching_fields(value)
  value=copy.deepcopy(VALID);value['hints']['level_1']='x\x00x'
  with self.assertRaises(ai.ModelError) as error:junior._teaching_fields(value)
  self.assertEqual(error.exception.code,'TEACHING_MATH_FORMAT_INVALID')
 def test_program_truth_still_overrides_model(self):
  body={'problem':'计算2+3','problem_latex':'2+3','steps':['4'],'recognition':{'question_type':'calculate','topic_id':'N1'}}
  with patch('app.ai.complete',return_value=(VALID,{})):
   result=junior.study(body)['analysis']
  self.assertEqual(result['target_latex'],'5');self.assertEqual(result['status'],'wrong_step')
 def test_failed_reading_can_retry_without_ocr_or_progress_and_success_is_idempotent(self):
  with tempfile.TemporaryDirectory() as folder,patch('app.profile._PATH',folder+'/p.json'):
   registry=ReadingRegistry()
   with patch('app.page_reading.registry',registry),patch('app.cards.readings',registry):
    row=item(problem=BODY['problem'],problem_latex='',steps=[],question_type='probability',topic_id='P1')
    page=page_reading.normalize_page(raw_page([row]),1,'generation');registry.remember_page('owner','r','image-digest',page)
    params={'batch_id':page['batch_id'],'reading_id':page['items'][0]['reading_id'],'source_revision':1,'request_id':'first'}
    before=store.read('owner')
    broken=copy.deepcopy(VALID);broken['hints']=list(VALID['hints'].values())+['extra']
    with patch('app.ai.complete',return_value=(broken,{})) as model:
     with self.assertRaises(ai.ModelError):page_reading.study('owner',params)
     model.assert_called_once()
    self.assertEqual(before,store.read('owner'))
    self.assertEqual(registry.page_reading('owner',page['batch_id'],params['reading_id'],1)['problem'],BODY['problem'])
    with patch('app.ai.complete',return_value=(VALID,{})) as model:
     result=page_reading.study('owner',{**params,'request_id':'retry'});model.assert_called_once()
    with patch('app.ai.complete',side_effect=AssertionError('must not reread or re-teach')):
     replay=page_reading.study('owner',{**params,'request_id':'again'})
    self.assertEqual(result['diagnosis_id'],replay['diagnosis_id'])
    after=store.read('owner');self.assertEqual(len(after['wrong_cards']),1)
    for key in ['quiz_answers','knowledge_cards','growth_events']:
     self.assertEqual(before[key],after[key])

if __name__=='__main__':unittest.main()
