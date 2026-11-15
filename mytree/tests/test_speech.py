"""Audio request validation, multipart protocol, safe errors and no raw logs."""
import base64
import io
import wave
import math
import struct
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,speech

class AudioUpstream(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']));self.server.requests.append((self.path,body,self.headers))
  code,mime,result=self.server.reply;self.send_response(code);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(result)

class SpeechTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.up=ThreadingHTTPServer(('127.0.0.1',0),AudioUpstream);self.up.requests=[];self.up.reply=(200,'application/json',b'{"text":"What is that?"}')
  threading.Thread(target=self.up.serve_forever,daemon=True).start();cfg=ai.Settings('http://127.0.0.1:'+str(self.up.server_address[1])+'/v1','TEST_SECRET')
  self.patches=[patch('app.ai.settings',return_value=cfg),patch('app.ai.USAGE_PATH',Path(self.temp.name)/'usage.jsonl')]
  for p in self.patches:p.start()
 def tearDown(self):
  self.up.shutdown();self.up.server_close()
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def audio(self):
  out=io.BytesIO()
  with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b''.join(struct.pack('<h',int(4000*math.sin(i*.1))) for i in range(9600)))
  return 'data:audio/wav;base64,'+base64.b64encode(out.getvalue()).decode()
 def test_asr_uses_multipart_with_server_selected_model_and_file(self):
  result=speech.handle({'action':'transcribe','audio_data':self.audio()});self.assertEqual(result['text'],'What is that?')
  path,body,headers=self.up.requests[0];self.assertEqual(path,'/v1/audio/transcriptions');self.assertIn(b'gpt-4o-mini-transcribe',body);self.assertIn(b'filename="recording.wav"',body);self.assertEqual(headers['Authorization'],'Bearer TEST_SECRET')
 def test_tts_uses_fixed_english_voice_and_returns_only_audio(self):
  self.up.reply=(200,'audio/mpeg',b'ID3'+b'\x00'*40);result=speech.handle({'action':'speak','text':'A green tree.'})
  self.assertTrue(result['synthetic']);payload=json.loads(self.up.requests[0][1]);self.assertEqual(payload['model'],'qwen3-tts-flash');self.assertEqual(payload['voice'],'Cherry');self.assertNotIn('instructions',payload);self.assertEqual(result['language'],'en')
 def test_bad_audio_or_url_is_rejected_before_network(self):
  for value in ('https://private.invalid/audio','data:audio/wav;base64,AA==',self.audio().replace('wav','webm')):
   with self.assertRaises(ValueError):speech.handle({'action':'transcribe','audio_data':value})
  self.assertFalse(self.up.requests)
 def test_client_cannot_select_upstream_model_voice_or_url(self):
  for extra in ({'model':'other'},{'voice':'other'},{'instructions':'override'},{'url':'http://private.invalid'}):
   with self.assertRaises(ValueError):speech.handle({'action':'speak','text':'Hello.',**extra})
  self.assertFalse(self.up.requests)
 def test_auth_quota_and_bad_upstream_body_are_safe(self):
  for status,expected in ((401,'MODEL_AUTH'),(429,'MODEL_BUSY'),(500,'MODEL_UPSTREAM')):
   self.up.reply=(status,'application/json',b'{"error":"TEST_SECRET private upstream detail"}')
   with self.assertRaises(ai.ModelError) as raised:speech.handle({'action':'speak','text':'Hello.'})
   self.assertEqual(raised.exception.code,expected);self.assertNotIn('private',str(raised.exception));self.assertNotIn('TEST_SECRET',str(raised.exception))
 def test_transcription_must_be_nonempty_and_bounded(self):
  for text in ('','x'*801):
   self.up.reply=(200,'application/json',json.dumps({'text':text}).encode())
   with self.assertRaises(ai.ModelError):speech.handle({'action':'transcribe','audio_data':self.audio()})
 def test_tts_json_disguised_as_success_is_not_playable(self):
  self.up.reply=(200,'application/json',b'{"error":"bad upstream"}')
  with self.assertRaises(ai.ModelError):speech.handle({'action':'speak','text':'Hello.'})
 def test_logs_omit_spoken_text_audio_and_key(self):
  speech.handle({'action':'transcribe','audio_data':self.audio()});log=(Path(self.temp.name)/'usage.jsonl').read_text()
  for value in ('What is that','TEST_SECRET','base64','RIFF'):self.assertNotIn(value,log)
 def test_tts_rejects_empty_or_overlong(self):
  for text in ('','x'*1201):
   with self.assertRaises(ValueError):speech.handle({'action':'speak','text':text})

if __name__=='__main__':unittest.main(verbosity=2)
