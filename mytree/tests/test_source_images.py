import base64,copy,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app import ai,cards,page_reading,profile,source_images,store
from app.errors import DomainError
from app.reading_registry import ReadingRegistry,ConfirmationError
from test_multiocr import item,raw_page

def image():
 out=io.BytesIO();Image.new('RGB',(500,800),'#87a472').save(out,format='JPEG');return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
class ImageCacheTests(unittest.TestCase):
 def test_absolute_ttl_owner_revision_and_byte_eviction(self):
  value=image();size=len(base64.b64decode(value.split(',')[1]));now=[0];cache=source_images.SourceImages(clock=lambda:now[0],ttl=10,owner_bytes=size*2+1,total_bytes=size*3+1)
  reading={'reading_id':'r','region':[0,.1,1,.3]};source={'batch_id':'a','source_revision':1,'reading_id':'r'}
  cache.put('one','a',1,value);cache.get('one',source,reading);now[0]=9;cache.get('one',source,reading);now[0]=10
  with self.assertRaises(DomainError):cache.get('one',source,reading)
  cache.put('one','a',1,value)
  with self.assertRaises(ValueError):cache.put('one','huge',1,'data:image/jpeg;base64,'+base64.b64encode(b'x'*4_500_001).decode())
  with self.assertRaises(DomainError):cache.get('two',source,reading)
  with self.assertRaises(DomainError):cache.get('one',{**source,'source_revision':2},reading)
  for batch in ['b','c']:cache.put('one',batch,1,value)
  with self.assertRaises(DomainError):cache.get('one',source,reading)
  for owner in ['two','three','four']:cache.put(owner,'a',1,value)
  self.assertLessEqual(cache.stats()['bytes'],size*3+1);cache.discard('four');self.assertEqual(cache.stats()['count'],2)
 def test_lesson_mode_preserves_work_without_scores_and_cancel_blocks_late_result(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'):
   registry=ReadingRegistry()
   with patch('app.page_reading.registry',registry),patch('app.cards.readings',registry):
    raw=raw_page([item()]);raw['unassigned_fragments']=[{'role':'unknown','script_kind':'handwritten','text':'ambiguous','region':[0,0,1,.2],'affected_orders':[1]}]
    page=page_reading.normalize_page(raw,1,'g');self.assertTrue(page['items'][0]['lesson_ready']);registry.remember_page('one','r','d',page)
    result=page_reading.study('one',{'batch_id':page['batch_id'],'reading_id':page['items'][0]['reading_id'],'source_revision':1,'request_id':'s'})
    self.assertEqual(result['wrong_card']['type'],'lesson');self.assertEqual(result['analysis']['study_mode'],'lesson_only');self.assertTrue(result['wrong_card']['student_steps']);saved=store.read('one');self.assertFalse(saved['lit']);self.assertFalse(saved['causes']);self.assertEqual(saved['history'],0)
    changed=copy.deepcopy(raw);changed['items'][0]['problem_complete']=False;self.assertFalse(page_reading.normalize_page(changed,1,'g')['items'][0]['lesson_ready'])
    changed=copy.deepcopy(raw);changed['items'][0]['fragments'][0]['text']='different printed condition';self.assertFalse(page_reading.normalize_page(changed,1,'g')['items'][0]['lesson_ready'])
    page=page_reading.normalize_page(raw,1,'g');registry.remember_page('one','r2','d2',page)
    original=cards.junior.study
    def late(body):
     value=original(body);registry.cancel_page('one',page['batch_id'],1);return value
    before=store.read('one')
    with patch('app.cards.junior.study',side_effect=late):
     with self.assertRaises(ConfirmationError):page_reading.study('one',{'batch_id':page['batch_id'],'reading_id':page['items'][0]['reading_id'],'source_revision':1,'request_id':'late'})
    self.assertEqual(before,store.read('one'))
 def test_legacy_picture_card_without_new_flag_requires_original(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'):
   store.update('one',lambda v:v['wrong_cards'].update(a={'id':'a','diagnosis_id':'old','problem':'如图，求俯视图。','_source':{}}))
   with self.assertRaises(DomainError):source_images.for_diagnosis('one','old')
 def test_visual_teacher_sees_image_and_expiry_never_falls_back_to_text(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'):
   registry=ReadingRegistry();cache=source_images.SourceImages()
   with patch('app.page_reading.registry',registry),patch('app.cards.readings',registry),patch('app.source_images.images',cache):
    q=item(problem='如图，长方体与圆柱组合体的俯视图是（ ） A. 宽矩形上接小矩形 B. 宽矩形上接窄矩形 C. 圆内有矩形 D. 矩形内有矩形',problem_latex='',steps=['C'],question_type='geometry',topic_id='G1',diagram_description='圆柱顶部有长方体，完整A-D选项。');q['fragments'][0]['text']=q['problem']
    page=page_reading.normalize_page(raw_page([q]),1,'g');registry.remember_page('one','r','d',page);cache.put('one',page['batch_id'],1,image());params={'batch_id':page['batch_id'],'reading_id':page['items'][0]['reading_id'],'source_revision':1,'request_id':'s'}
    result={'hints':['先看俯视方向。','对照投影关系。','上方的长方体投影落在圆内。'],'card':{'title':'投影','body':'从上往下观察。','tip':'保留内外轮廓。'},'answer_latex':'','assessment':'','knowledge_ids':['G1']}
    with patch('app.ai.complete',return_value=(result,{})) as model:
     page_reading.study('one',params);self.assertEqual(model.call_args.args[0],'vision');self.assertEqual(model.call_args.args[1][1]['content'][1]['type'],'image_url')
    page2=page_reading.normalize_page(raw_page([q]),1,'g');registry.remember_page('one','r2','d',page2)
    with patch('app.ai.complete') as model:
     with self.assertRaises(DomainError):page_reading.study('one',{**params,'batch_id':page2['batch_id'],'reading_id':page2['items'][0]['reading_id'],'request_id':'s2'})
     model.assert_not_called()
if __name__=='__main__':unittest.main()
