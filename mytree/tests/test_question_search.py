"""Official-bank adapter boundaries with synthetic sources; no live API call."""
import base64
import concurrent.futures
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import question_search as bank, page_reading, contract
from app.errors import DomainError
from app.reading_registry import registry, ConfirmationError
from test_multiocr import raw_page


def reply(content='x^2-9',**extra):
 return {'errorCode':'0','data':{'questions':[{'id':'provider_1','content':content,'answer':'ANSWER_SECRET_SENTINEL','analysis':'ANALYSIS_SECRET_SENTINEL',**extra}]}}


class SearchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'MYTREE_QUESTIONBANK_CONFIG':self.temp.name+'/absent','MYTREE_YOUDAO_APP_KEY':'fixture-key','MYTREE_YOUDAO_APP_SECRET':'fixture-secret','MYTREE_QUESTIONBANK_DAILY_LIMIT':'20','MYTREE_QUESTIONBANK_DB':self.temp.name+'/quota.sqlite3'});self.env.start();bank._CACHE.clear()
  self.page=page_reading.normalize_page(raw_page(),1,'fixture');registry.remember_page('owner','req','digest',self.page)
  self.body={'batch_id':self.page['batch_id'],'reading_id':self.page['items'][0]['reading_id'],'source_revision':1,'request_id':'lookup'}
 def tearDown(self):self.env.stop();self.temp.cleanup();bank._CACHE.clear()
 def search(self,response=None,**body):
  with patch.object(bank,'provider_query',return_value=response or reply()) as call:
   output=bank.search('owner',{**self.body,**body})
  return output,call
 def register(self,text):
  item=raw_page()['items'][0];item.update(problem=text,problem_latex='',problem_complete=True,diagram_complete=True,diagram_description='',fragments=[{'role':'problem','script_kind':'printed','text':text,'region':[0,0,1,1]}],steps=[],answer_presence='absent')
  self.page=page_reading.normalize_page({'items':[item],'overflow':False},1,'g');registry.remember_page('owner','r','d',self.page);self.body.update(batch_id=self.page['batch_id'],reading_id=self.page['items'][0]['reading_id'])
 def test_no_config_is_distinct_and_does_not_call_provider(self):
  with patch.dict(os.environ,{'MYTREE_YOUDAO_APP_KEY':'','MYTREE_YOUDAO_APP_SECRET':''}):
   output,call=self.search();self.assertEqual(output['status'],'not_configured');call.assert_not_called()
 def test_lookup_sends_only_server_stem_and_never_answers(self):
  output,call=self.search();call.assert_called_once_with(self.page['items'][0]['problem'],'fixture-key','fixture-secret')
  self.assertEqual(output['status'],'candidates');self.assertNotIn('ANSWER_SECRET_SENTINEL',json.dumps(output));self.assertNotIn('ANALYSIS_SECRET_SENTINEL',json.dumps(output));self.assertNotIn('answer',output['candidates'][0]);self.assertIsNone(output['candidates'][0]['source_url'])
 def test_49_50_and_empty_boundary_no_truncation(self):
  for count in (49,50,0):
   self.register('数'*count);output,call=self.search()
   self.assertEqual(output['status'],'candidates' if count==49 else 'unsupported')
   if count==49:self.assertEqual(call.call_args.args[0],'数'*49)
   else:call.assert_not_called()
 def test_internal_problem_fragment_conflict_and_latex_conflict_never_leave_server(self):
  for field,value in [('problem','x^2-16'),('problem_latex','x^2-16')]:
   corrupted=copy.deepcopy(self.page);corrupted['items'][0][field]=value;registry.remember_page('owner','r','d',corrupted)
   output,call=self.search();self.assertEqual(output['status'],'unsupported');call.assert_not_called()
 def test_only_work_ambiguity_does_not_block_reliable_stem(self):
  changed=copy.deepcopy(self.page);changed['items'][0]['association_status']='uncertain';changed['items'][0]['auto_ready']=False;registry.remember_page('owner','r','d',changed)
  output,call=self.search();call.assert_called_once();self.assertEqual(output['status'],'candidates');self.assertFalse(registry.page_reading('owner',self.body['batch_id'],self.body['reading_id'],1)['auto_ready'])
 def test_diagram_and_unclear_problem_not_silently_searched(self):
  for text in ('如图求角A。','已知x=?，求y。'):
   self.register(text);output,call=self.search();self.assertEqual(output['status'],'unsupported');call.assert_not_called()
 def test_cache_single_flight_new_request_id_and_source_authorization(self):
  with patch.object(bank,'provider_query',return_value=reply()) as call:
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda n:bank.search('owner',{**self.body,'request_id':str(n)}),range(4)))
   self.assertEqual(call.call_count,1);self.assertEqual(sum(x['cached'] for x in results),3)
   with self.assertRaises(ConfirmationError):bank.search('foreign',self.body)
   with self.assertRaises(ConfirmationError):bank.search('owner',{**self.body,'source_revision':2})
 def test_expired_cache_and_errors_are_retryable(self):
  self.search()
  with patch.object(bank.time,'monotonic',return_value=10**12):output,call=self.search();call.assert_called_once()
  bank._CACHE.clear()
  with patch.object(bank,'provider_query',side_effect=DomainError('QUESTIONBANK_UNAVAILABLE','失败',503)):
   with self.assertRaises(DomainError):bank.search('owner',self.body)
  output,call=self.search();call.assert_called_once();self.assertFalse(output['cached'])
 def test_no_results_is_short_cached_not_failed(self):
  output,call=self.search({'errorCode':'0','data':{'questions':[]}});self.assertEqual(output['status'],'no_results');cached,call=self.search();call.assert_not_called();self.assertTrue(cached['cached'])
 def test_comparison_never_uses_similarity_and_keeps_conditions(self):
  self.register('x≤1.5米，求x。')
  for text,expected in [('x≤1.5米，求x。','text_equal'),('x≥1.5米，求x。','different'),('x≤1.6米，求x。','different'),('x≤1.5，求x。','different'),('x≤1.5米','different'),('x≤1.5米，求x。<img src="http://127.0.0.1/a">','incomplete_or_unchecked')]:
   bank._CACHE.clear();out,_=self.search(reply(text));self.assertEqual(out['candidates'][0]['comparison'],expected);self.assertFalse(out['candidates'][0]['verified'])
 def test_html_images_and_active_content_are_plain_unfetched_data(self):
  content=bank.plain('<script>evil()</script><iframe src="http://127.0.0.1">secret</iframe><p onclick="evil()">x<sup>2</sup></p><img src="javascript:evil()"><img src="file:///etc/passwd">')
  self.assertNotIn('evil',content['text']);self.assertNotIn('secret',content['text']);self.assertIn('x^{2}',content['text']);self.assertTrue(content['has_images']);self.assertEqual(content['images'],[])
 def test_bad_output_and_duplicate_candidates_bounded(self):
  result=reply();result['data']['questions']*=20;out,_=self.search(result);self.assertEqual(len(out['candidates']),1)
  for response in ({'data':{}},reply('x'*10001),reply(id='javascript:bad')):
   with self.assertRaises(DomainError):bank.candidates(response,self.page['items'][0])
 def test_daily_and_minute_quotas_persist(self):
  bank.reserve('owner',2);bank.reserve('other',2)
  with self.assertRaises(DomainError) as e:bank.reserve('new',2)
  self.assertEqual(e.exception.code,'QUESTIONBANK_DAILY_LIMIT')
  for _ in range(5):bank.reserve('owner',100)
  with self.assertRaises(DomainError) as e:bank.reserve('owner',100)
  self.assertEqual(e.exception.code,'QUESTIONBANK_BUSY')
 def test_normalized_expansion_is_rejected_without_cache_and_retry_recovers(self):
  with patch.object(bank,'provider_query',return_value=reply('<img>'*2000)):
   with self.assertRaises(DomainError) as e:bank.search('owner',self.body)
   self.assertEqual(e.exception.code,'QUESTIONBANK_INVALID_OUTPUT');self.assertEqual(e.exception.status,503)
  self.assertEqual(len(bank._CACHE),0)
  output,call=self.search();call.assert_called_once();self.assertFalse(output['cached'])
 def test_mixed_oversized_normalized_candidate_preserves_valid_candidate(self):
  value=reply('<img>'*2000);value['data']['questions'].append({'id':'good_id','content':'x^2-9'})
  output,_=self.search(value);self.assertEqual(len(output['candidates']),1);self.assertEqual(output['candidates'][0]['provider_item_id'],'good_id')
 def test_input_cannot_replace_stem_or_endpoint(self):
  for extra in ({'q':'bad'},{'problem':'bad'},{'steps':[]},{'endpoint':'http://127.0.0.1'}):
   with self.assertRaises(contract.ContractError):bank.search('owner',{**self.body,**extra})
 def test_fixed_v2_signature_wire_payload_and_no_student_data(self):
  vectors=[('x≤1.5米','eOKJpDEuNeexsw==','c2b7cbf141a5a91ed8557e3f064dbb9e7048c8a6a383c9374fb4004388cd0249'),('已知x≤1.5米，求x的取值范围。','5bey55+leOKJpDEuNeexs++8jOaxgnjnmoTlj5blgLzojIPlm7TjgII=','12610872c07aa33f1c604c4a39395b5ec085f6ad675eeae97aed885b49385adf')]
  for text,q,expected in vectors:
   response=io.BytesIO(json.dumps(reply()).encode())
   with patch.object(bank.uuid,'uuid4') as uid,patch.object(bank.time,'time',return_value=1700000000),patch.object(bank.urllib.request,'build_opener') as build:
    uid.return_value.hex='salt-fixed';build.return_value.open.return_value=response;bank.provider_query(text,'key','secret')
    request=build.return_value.open.call_args.args[0];form=urllib.parse.parse_qs(request.data.decode())
    self.assertEqual(form['sign'],[expected]);self.assertEqual(form['q'],[q]);self.assertEqual(form['searchType'],['text']);self.assertEqual(request.full_url,bank.ENDPOINT)
 def test_upstream_errors_invalid_json_and_oversize_are_not_no_results(self):
  values=[b'not-json',b' '*1048577]+[json.dumps({'errorCode':x}).encode() for x in ('401','202','110','411')]
  for raw in values:
   with patch.object(bank.urllib.request,'build_opener') as build:
    build.return_value.open.return_value=io.BytesIO(raw)
    with self.assertRaises(DomainError) as e:bank.provider_query('x=1','key','secret')
    self.assertEqual(e.exception.status,503);self.assertNotIn('secret',str(e.exception))
  with patch.object(bank.urllib.request,'build_opener') as build:
   build.return_value.open.side_effect=TimeoutError('secret')
   with self.assertRaises(DomainError) as e:bank.provider_query('x','key','secret')
   self.assertNotIn('secret',str(e.exception))

if __name__=='__main__':unittest.main()
