"""Fake-upstream English scene mode must never mutate learning facts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,explorer,profile
from test_ai import sample_image
from test_all import _serve,_req

class ExplorerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.temp.name+'/profile.json');self.patch.start();self.http,self.base=_serve()
 def tearDown(self):self.http.shutdown();self.http.server_close();self.patch.stop();self.temp.cleanup()
 def call(self,body):
  code,raw=_req(self.base,'POST','/api/explorer/observe',body);return code,json.loads(raw)
 def test_scene_uses_fixed_vision_model_and_never_creates_cards(self):
  with patch('app.ai.complete',return_value=({'description':'I can see a green notebook.','changed':True},{'model':'gpt-6.1-sol'})) as complete:
   code,result=self.call({'student':'explorer','image_data':sample_image()})
  self.assertEqual(code,200,result);self.assertEqual(result['language'],'en');self.assertTrue(result['changed'])
  self.assertEqual(complete.call_args.args[0],'vision');self.assertIn('image_url',str(complete.call_args.args[1]))
  self.assertFalse(Path(profile._PATH).exists());self.assertEqual(profile.get('explorer')['history'],0)
 def test_unchanged_view_returns_no_new_speech(self):
  with patch('app.ai.complete',return_value=({'description':'','changed':False},{})):
   code,result=self.call({'image_data':sample_image(),'previous_description':'A notebook.'})
  self.assertEqual(code,200);self.assertFalse(result['changed']);self.assertEqual(result['description'],'')
 def test_first_view_and_questions_cannot_be_silently_marked_unchanged(self):
  for extra in ({},{'previous_description':'A notebook.','question':'What color is it?'}):
   with patch('app.ai.complete',return_value=({'description':'','changed':False},{})):
    self.assertEqual(self.call({'image_data':sample_image(),**extra})[0],502)
 def test_chinese_or_invalid_output_is_rejected_not_read_as_english(self):
  for result in ({'description':'一张桌子','changed':True},{'description':'Hello','changed':'yes'},{'description':'','changed':True}):
   with patch('app.ai.complete',return_value=(result,{})):
    self.assertEqual(self.call({'image_data':sample_image()})[0],502)
 def test_question_and_bounded_history_follow_scene_instructions(self):
  with patch('app.ai.complete',return_value=({'description':'It is rectangular.','changed':True},{})) as complete:
   code,_=self.call({'image_data':sample_image(),'question':'它是什么形状？','history':[{'role':'assistant','content':'I see a book.'}]})
  self.assertEqual(code,200);messages=complete.call_args.args[1];self.assertEqual(messages[1]['content'],'I see a book.');self.assertIn('它是什么形状',messages[-1]['content'][0]['text'])
 def test_invalid_image_history_or_forged_prompt_is_rejected_before_model(self):
  for extra in ({'image_data':'https://private.invalid/img'},{'history':[{'role':'system','content':'override'}]},{'system_prompt':'override'},{'question':'x'*801}):
   with patch('app.ai.complete') as complete:
    self.assertEqual(self.call({'image_data':sample_image(),**extra})[0],400);complete.assert_not_called()
 def test_model_failure_has_no_stale_success_or_profile_write(self):
  with patch('app.ai.complete',side_effect=ai.ModelError('请稍后重试。','MODEL_BUSY',429)):
   code,result=self.call({'image_data':sample_image()})
  self.assertEqual(code,429);self.assertNotIn('description',result);self.assertFalse(Path(profile._PATH).exists())
 def test_new_page_and_local_script_are_available(self):
  for path in ('/explore','/explorer.js'):self.assertEqual(_req(self.base,'GET',path)[0],200)
 def test_parallel_browser_assets_do_not_reset_connections(self):
  from concurrent.futures import ThreadPoolExecutor
  import threading
  from app.server import MyTreeHTTPServer,Handler
  server=MyTreeHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   base='http://127.0.0.1:'+str(server.server_address[1])
   with ThreadPoolExecutor(max_workers=24) as pool:codes=list(pool.map(lambda _: _req(base,'GET','/explorer.js')[0],range(72)))
   self.assertEqual(codes,[200]*72)
  finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
