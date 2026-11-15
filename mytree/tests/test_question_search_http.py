"""Email-session and source-version boundaries on the actual HTTP route."""
import json
import os
import unittest
from unittest.mock import patch
import test_auth
from test_question_search import reply
from test_multiocr import raw_page
from app import page_reading,question_search as bank,profile
from app.reading_registry import registry

class SearchHTTPTests(unittest.TestCase):
 def setUp(self):
  test_auth.AuthTests.setUp(self)
  self.bankenv=patch.dict(os.environ,{'MYTREE_QUESTIONBANK_CONFIG':self.temp.name+'/missing','MYTREE_YOUDAO_APP_KEY':'fixture-key','MYTREE_YOUDAO_APP_SECRET':'fixture-secret','MYTREE_QUESTIONBANK_DAILY_LIMIT':'20','MYTREE_QUESTIONBANK_DB':self.temp.name+'/quota.sqlite3'});self.bankenv.start();bank._CACHE.clear()
 def tearDown(self):self.bankenv.stop();bank._CACHE.clear();test_auth.AuthTests.tearDown(self)
 req=test_auth.AuthTests.req
 login=test_auth.AuthTests.login
 def source(self,account):
  result=page_reading.normalize_page(raw_page(),1,'fixture');registry.remember_page(account['profile_id'],'request','digest',result)
  return {'batch_id':result['batch_id'],'reading_id':result['items'][0]['reading_id'],'source_revision':1,'request_id':'lookup'}
 def test_account_source_version_cache_and_learning_unchanged(self):
  account,cookie=self.login();_,foreign=self.login('foreign@example.test');body=self.source(account)
  before=json.dumps(profile._load(),sort_keys=True)
  with patch.object(bank,'provider_query',return_value=reply()) as query:
   status,result,_=self.req('/api/questions/search',{**body,'student':'forged'},cookie=cookie);self.assertEqual(status,200,result)
   self.assertNotIn('ANSWER_SECRET_SENTINEL',json.dumps(result));self.assertEqual(result['status'],'candidates')
   self.assertTrue(self.req('/api/questions/search',{**body,'request_id':'another'},cookie=cookie)[1]['cached']);self.assertEqual(query.call_count,1)
   self.assertEqual(self.req('/api/questions/search',body,cookie=foreign)[0],404)
   self.assertEqual(self.req('/api/questions/search',{**body,'source_revision':2},cookie=cookie)[0],409)
   self.assertEqual(query.call_count,1)
  self.assertEqual(before,json.dumps(profile._load(),sort_keys=True))
 def test_unauth_cross_origin_and_client_fields_rejected(self):
  account,cookie=self.login();body=self.source(account)
  with patch.object(bank,'provider_query') as query:
   self.assertEqual(self.req('/api/questions/search',body)[0],401)
   self.assertEqual(self.req('/api/questions/search',body,cookie=cookie,origin='https://foreign.test')[0],403)
   for field in ('q','endpoint','answer','problem'):
    self.assertEqual(self.req('/api/questions/search',{**body,field:'forged'},cookie=cookie)[0],400)
   query.assert_not_called()
 def test_cancelled_expired_sources_and_not_configured(self):
  account,cookie=self.login();body=self.source(account)
  with patch.dict(os.environ,{'MYTREE_YOUDAO_APP_KEY':'','MYTREE_YOUDAO_APP_SECRET':''}):
   status,result,_=self.req('/api/questions/search',body,cookie=cookie);self.assertEqual(status,200,result);self.assertEqual(result['status'],'not_configured')
  registry.cancel_page(account['profile_id'],body['batch_id'],1)
  self.assertEqual(self.req('/api/questions/search',body,cookie=cookie)[0],409)
  registry.resume_page(account['profile_id'],body['batch_id'],1)
  with patch.object(registry,'clock',return_value=10**12):self.assertEqual(self.req('/api/questions/search',body,cookie=cookie)[0],409)

if __name__=='__main__':unittest.main()
