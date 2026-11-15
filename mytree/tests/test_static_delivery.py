"""Static delivery compression/validation must never cache or bypass private data."""
import gzip,hashlib,json,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
import test_auth
from app import server

class StaticDeliveryTests(unittest.TestCase):
 setUp=test_auth.AuthTests.setUp
 tearDown=test_auth.AuthTests.tearDown
 login=test_auth.AuthTests.login
 req=test_auth.AuthTests.req
 def get(self,path,cookie='',headers=None):
  request=urllib.request.Request(self.base+path,headers={'Cookie':cookie,**(headers or {})})
  try:r=urllib.request.build_opener(test_auth.NoRedirect).open(request,timeout=10)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,r.read(),r.headers
 def test_gzip_static_etag_variants_and_no_stale_body(self):
  code,raw,identity=self.get('/commerce.css');self.assertEqual(code,200)
  code,compressed,h=self.get('/commerce.css',headers={'Accept-Encoding':'gzip'})
  self.assertEqual(code,200);self.assertEqual(gzip.decompress(compressed),raw)
  self.assertLess(len(compressed),len(raw)//2);self.assertEqual(h['Content-Encoding'],'gzip');self.assertEqual(h['Vary'],'Accept-Encoding')
  self.assertNotEqual(h['ETag'],identity['ETag']);self.assertEqual(h['Cache-Control'],'public, max-age=0, must-revalidate')
  code,body,fresh=self.get('/commerce.css',headers={'Accept-Encoding':'gzip','If-None-Match':h['ETag']})
  self.assertEqual(code,304);self.assertEqual(body,b'');self.assertIsNone(fresh.get('Content-Length'))
  self.assertEqual(self.get('/commerce.css',headers={'If-None-Match':h['ETag']})[0],200)
  server._static_representation.cache_clear()
  self.assertEqual(self.get('/commerce.css',headers={'Accept-Encoding':'gzip'})[2]['ETag'],h['ETag'])
 def test_pages_and_private_api_are_never_cached(self):
  for path in ['/welcome','/login','/pricing']:
   code,body,h=self.get(path,headers={'Accept-Encoding':'gzip','If-None-Match':'*'})
   self.assertEqual(code,200);self.assertEqual(h['Cache-Control'],'no-store');self.assertIsNone(h.get('ETag'))
   self.assertIn(b'<!doctype html>',gzip.decompress(body).lower())
  a,cookie=self.login();code,data,h=self.get('/api/auth/me',cookie,{'Accept-Encoding':'gzip','If-None-Match':'*'})
  self.assertEqual(code,200);self.assertEqual(json.loads(data)['user']['profile_id'],a['profile_id'])
  self.assertEqual(h['Cache-Control'],'no-store');self.assertIsNone(h.get('ETag'));self.assertIsNone(h.get('Content-Encoding'))
 def test_authorization_precedes_private_asset_304(self):
  a,cookie=self.login();code,_,h=self.get('/app.js',cookie);self.assertEqual(code,200);self.assertTrue(h['Cache-Control'].startswith('private,'))
  self.assertEqual(self.get('/app.js',headers={'If-None-Match':h['ETag']})[0],401)
  self.req('/api/auth/logout',{},cookie=cookie)
  code,_,r=self.get('/app.js',cookie,{'If-None-Match':h['ETag']})
  self.assertEqual(code,401);self.assertEqual(r['Cache-Control'],'no-store');self.assertIsNone(r.get('ETag'))
 def test_updated_file_changes_validator_and_font_is_not_recompressed(self):
  p=Path(self.temp.name)/'commerce.css';p.write_text('body{color:red}')
  with patch.object(server,'STATIC',self.temp.name):
   _,old,h=self.get('/commerce.css');p.write_text('body{color:green}')
   code,body,r=self.get('/commerce.css',headers={'If-None-Match':h['ETag']})
   self.assertEqual(code,200);self.assertNotEqual(body,old);self.assertNotEqual(r['ETag'],h['ETag'])
  code,data,h=self.get('/fonts/Sora.woff2',headers={'Accept-Encoding':'gzip'})
  self.assertEqual(code,200);self.assertIsNone(h.get('Content-Encoding'))
  self.assertEqual(self.get('/fonts/Sora.woff2',headers={'If-None-Match':h['ETag']})[0],304)
 def test_encoding_negotiation_respects_q_zero(self):
  for value,expected in [('gzip',True),('gzip;q=0, br',False),('*;q=1,gzip;q=0',False),('br, gzip;q=0.5',True),('gzip;q=oops',False),('identity',False)]:self.assertEqual(server._accepts_gzip(value),expected)
