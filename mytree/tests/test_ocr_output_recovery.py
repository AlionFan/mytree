"""Output budgets and eventual OCR metadata recovery, no upstream calls."""
import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,junior,page_reading,contract
from test_multiocr import item,raw_page
from test_teaching_output import VALID

class TeachingBudgetTests(unittest.TestCase):
 def test_multi_part_visual_geometry_uses_bounded_6400_once(self):
  body={'problem':'(1)从条件证明切线；(2)已知长度，求线段长。','steps':[],'recognition':{'question_type':'geometry','topic_id':'G7'},'_source_image':'fixture-image'}
  with patch('app.ai.complete',return_value=(VALID,{})) as model:
   result=junior.study(body)
  model.assert_called_once();self.assertEqual(model.call_args.kwargs['limit'],6400)
  self.assertEqual(model.call_args.args[0],'vision');self.assertTrue(result['ok'])
 def test_budget_does_not_expand_regular_text_or_simple_visual_questions(self):
  for kind,problem,image in [('geometry','(1)求角A；(2)求角B。',False),('geometry','求角A。',True),('probability','下列事件是确定事件的是（）',True)]:
   self.assertEqual(junior._teaching_budget({'question_type':kind,'problem':problem},image),3200)
 def test_long_visual_context_has_room_but_remains_bounded(self):
  for kind in ['geometry','function','word_problem']:
   self.assertEqual(junior._teaching_budget({'question_type':kind,'problem':'题'*400},True),6400)
 def test_self_reported_partial_solution_cannot_be_saved_as_complete(self):
  for status in ['partial','needs_clarification','unsupported-status']:
   generated=copy.deepcopy(VALID);generated['solution_status']=status
   body={'problem':'证明三角形全等。','steps':[],'recognition':{'question_type':'geometry','topic_id':'G7'}}
   with patch('app.ai.complete',return_value=(generated,{})) as model:
    with self.assertRaises(ai.ModelError) as error:junior.study(body)
   model.assert_called_once()
   self.assertIn(error.exception.code,['TEACHING_SOLUTION_INCOMPLETE','TEACHING_OUTPUT_INVALID'])
 def test_truncated_result_remains_a_failure_without_hidden_retry(self):
  body={'problem':'(1)证明；(2)求值。','steps':[],'recognition':{'question_type':'geometry','topic_id':'G7'},'_source_image':'fixture-image'}
  with patch('app.ai.complete',side_effect=ai.ModelError('回复截断','MODEL_OUTPUT_TRUNCATED')) as model:
   with self.assertRaises(ai.ModelError) as error:junior.study(body)
  model.assert_called_once();self.assertEqual(error.exception.code,'MODEL_OUTPUT_TRUNCATED')

class UnassignedLocationTests(unittest.TestCase):
 def raw(self,affected=None,role='unknown'):
  raw=raw_page()
  raw['unassigned_fragments']=[{'role':role,'script_kind':'handwritten','text':'m=n+4；条件①②，结论③','region':{'x':.55,'y':.76,'width':.4,'height':.25},'affected_orders':[2] if affected is None else affected}]
  return raw
 def test_bad_unassigned_location_preserves_text_role_and_affected_orders(self):
  raw=self.raw();before=copy.deepcopy(raw);out=page_reading.normalize_page(raw,1,'unknown-location')
  fragment=out['unassigned_fragments'][0]
  self.assertIsNone(fragment['region']);self.assertEqual(fragment['location_status'],'unknown')
  for key in ['text','role','affected_orders']:self.assertEqual(fragment[key],raw['unassigned_fragments'][0][key])
  self.assertEqual(raw,before);self.assertTrue(out['warnings'])
  self.assertTrue(out['items'][0]['auto_ready']);self.assertFalse(out['items'][1]['auto_ready']);self.assertTrue(out['items'][2]['auto_ready'])
  contract.definition('PageRecognitionOutput',out)
 def test_no_affected_orders_conservatively_blocks_all_auto_assessment(self):
  out=page_reading.normalize_page(self.raw([]),1,'unknown-whole-page')
  self.assertTrue(all(not i['auto_ready'] for i in out['items']))
 def test_original_nonunknown_role_is_preserved_but_cannot_hide_unknown_position(self):
  out=page_reading.normalize_page(self.raw(role='teacher_annotation'),1,'annotation-location')
  self.assertEqual(out['unassigned_fragments'][0]['role'],'teacher_annotation')
  self.assertFalse(out['items'][1]['auto_ready'])
 def test_normal_work_fragments_keep_strict_coordinates(self):
  raw=raw_page();raw['items'][0]['fragments'][1]['region']={'x':.55,'y':.76,'width':.4,'height':.25}
  out=page_reading.normalize_page(raw,1,'strict-work')
  self.assertFalse(out['items'][0]['auto_ready']);self.assertTrue(out['items'][1]['auto_ready'])
 def test_malformed_or_unsafe_coordinates_do_not_get_silently_accepted(self):
  for region in [{'x':0,'y':0,'right':1,'bottom':1},[0,0,True,1],[0,0,float('nan'),1],'not-a-region']:
   raw=self.raw();raw['unassigned_fragments'][0]['region']=region
   with self.subTest(region=region),self.assertRaises(ai.ModelError):page_reading.normalize_page(raw,1,'bad-unknown')
 def test_null_region_requires_explicit_location_metadata_in_schema(self):
  fragment={'role':'unknown','script_kind':'handwritten','text':'保留笔迹','region':None,'affected_orders':[]}
  with self.assertRaises(Exception):contract.definition('UnassignedFragment',fragment)
  fragment.update(location_status='unknown',location_reason='位置未知')
  contract.definition('UnassignedFragment',fragment)
  ordinary={key:value for key,value in fragment.items() if key in ('role','script_kind','text','region')}
  with self.assertRaises(Exception):contract.definition('PageFragment',ordinary)

if __name__=='__main__':unittest.main()
