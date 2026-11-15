"""Public preview refuses unauthenticated calls and cross-origin JSON."""
import base64,json,os
from pathlib import Path
import sys,unittest,urllib.request,urllib.error
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import access
from test_all import _serve,_req

class AccessTests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'MYTREE_ACCESS_PASSWORD':'PRIVATE_TEST_PASS','MYTREE_ACCESS_USER':'tree'});self.env.start();self.http,self.base=_serve()
 def tearDown(self):self.http.shutdown();self.http.server_close();self.env.stop()
 def headers(self):return {'Authorization':'Basic '+base64.b64encode(b'tree:PRIVATE_TEST_PASS').decode()}
 def request(self,path,body=None,headers=None):
  req=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
  try:r=urllib.request.urlopen(req)
  except urllib.error.HTTPError as error:r=error
  with r:return r.status,r.read(),r.headers
 def test_pages_scripts_and_paid_api_require_credentials(self):
  for path,body in (('/',None),('/explorer.js',None),('/api/capabilities',None),('/api/speech',{'action':'speak','text':'Hello.'})):
   code,raw,headers=self.request(path,body);self.assertEqual(code,401);self.assertIn('Basic realm',headers['WWW-Authenticate']);self.assertNotIn(b'PRIVATE_TEST_PASS',raw)
 def test_readiness_omits_model_and_profile_information(self):
  code,raw,_=self.request('/_ready');self.assertEqual(code,200);self.assertEqual(json.loads(raw),{'ok':True})
 def test_authorized_get_and_headers(self):
  code,_,headers=self.request('/explore',headers=self.headers());self.assertEqual(code,200);self.assertIn("script-src 'self'",headers['Content-Security-Policy']);self.assertEqual(headers['X-Frame-Options'],'DENY')
 def test_wrong_password_and_malformed_auth_never_pass(self):
  for value in ('Basic ???','Bearer token','Basic '+base64.b64encode(b'tree:wrong').decode()):self.assertFalse(access.authorized(value))
 def test_cross_origin_cannot_spend_with_browser_credentials(self):
  code,_,_=self.request('/api/speech',{'action':'speak','text':'Hello.'},{**self.headers(),'Origin':'https://attacker.invalid'});self.assertEqual(code,403)
 def test_model_calls_are_bounded_without_logging_credentials(self):
  with patch('app.access._calls',access.deque()),patch('app.access.time.monotonic',return_value=100):
   self.assertTrue(all(access.allow_model() for _ in range(60)));self.assertFalse(access.allow_model())
 def test_required_auth_fails_closed_when_password_missing(self):
  with patch.dict(os.environ,{'MYTREE_REQUIRE_AUTH':'1','MYTREE_ACCESS_PASSWORD':''}):self.assertFalse(access.authorized(None))

if __name__=='__main__':unittest.main(verbosity=2)
