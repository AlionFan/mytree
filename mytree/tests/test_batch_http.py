"""Actual authenticated HTTP paths, without mocking the business handler."""
import unittest
from unittest.mock import patch
import test_auth
from test_multiocr import raw_page

class BatchHTTPTests(unittest.TestCase):
 setUp=test_auth.AuthTests.setUp
 tearDown=test_auth.AuthTests.tearDown
 req=test_auth.AuthTests.req
 login=test_auth.AuthTests.login
 def recognize(self,cookie,**extra):
  with patch('app.page_reading.ai.complete',return_value=(raw_page(),{})):
   from test_ai import sample_image
   return self.req('/api/recognize/page',{'image_data':sample_image(),'request_id':'photo','client_generation':'gen',**extra},cookie=cookie)
 def test_real_auth_three_questions_auto_study_and_own_account_binding(self):
  account,cookie=self.login();_,other=self.login('second@example.test')
  status,page,_=self.recognize(cookie,student='forged-profile');self.assertEqual(status,200,page);self.assertEqual(len(page['items']),3)
  body={'batch_id':page['batch_id'],'reading_id':page['items'][0]['reading_id'],'source_revision':1,'request_id':'auto','student':'forged-profile'}
  status,result,_=self.req('/api/study/reading',body,cookie=cookie);self.assertEqual(status,200,result);self.assertEqual(result['analysis']['status'],'wrong_step')
  status,replay,_=self.req('/api/study/reading',{**body,'request_id':'new'},cookie=cookie);self.assertEqual(status,200,replay);self.assertTrue(replay['duplicate']);self.assertEqual(result['wrong_card']['id'],replay['wrong_card']['id'])
  self.assertEqual(self.req('/api/study/reading',body,cookie=other)[0],404)
  self.assertEqual(self.req('/api/study/reading',{**body,'source_revision':2},cookie=cookie)[0],409)
 def test_unknown_fields_and_cross_source_are_rejected(self):
  _,cookie=self.login();_,other=self.login('second@example.test');_,page,_=self.recognize(cookie)
  body={'batch_id':page['batch_id'],'reading_id':page['items'][0]['reading_id'],'source_revision':1,'request_id':'auto'}
  for extra in ({'steps':['forged']},{'auto_ready':True},{'problem':'forged'}):self.assertEqual(self.req('/api/study/reading',{**body,**extra},cookie=cookie)[0],400)
  cancel={'batch_id':page['batch_id'],'source_revision':1}
  self.assertEqual(self.req('/api/recognize/page/cancel',cancel,cookie=other)[0],404)
  self.assertEqual(self.req('/api/recognize/page/cancel',cancel,cookie=cookie)[0],200)
  self.assertEqual(self.req('/api/study/reading',body,cookie=cookie)[0],409)
 def test_unauth_and_cross_origin_do_not_call_model(self):
  with patch('app.page_reading.ai.complete') as complete:
   self.assertEqual(self.req('/api/recognize/page',{'image_data':'fake'})[0],401)
   self.assertEqual(self.req('/api/recognize/page',{'image_data':'fake'},origin='https://other.test')[0],403)
  complete.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
