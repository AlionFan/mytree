"""Official provider routing/protocol tests against local synthetic upstreams."""
import base64
from dataclasses import replace
import importlib.util
import json
import io
import wave
import math
import struct
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,speech,mem0_adapter as ma
spec=importlib.util.spec_from_file_location('configure',Path(__file__).resolve().parents[1]/'scripts/configure_official_ai.py')
configure=importlib.util.module_from_spec(spec);spec.loader.exec_module(configure)
_wav=io.BytesIO()
with wave.open(_wav,'wb') as _w:
    _w.setnchannels(1);_w.setsampwidth(2);_w.setframerate(16000);_w.writeframes(b''.join(struct.pack('<h',int(4000*math.sin(i*.1))) for i in range(9600)))
WAV=_wav.getvalue()

class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.requests.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length']))),self.headers['Authorization']))
        self.send_response(self.server.status);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps(self.server.reply).encode())

class OfficialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.up=ThreadingHTTPServer(('127.0.0.1',0),Upstream);self.up.requests=[];self.up.status=200
        self.up.reply={'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}]}
        threading.Thread(target=self.up.serve_forever,daemon=True).start()
        self.base='http://127.0.0.1:'+str(self.up.server_address[1])
        self.cfg=ai.Settings(base='https://unused.invalid',key='LEGACY_SECRET',vision='qwen3.6-flash',tutor='deepseek-flash',diagram='qwen3.6-flash',asr='qwen3-asr-flash',endpoints={r:(self.base+('/api/v1' if r=='tts' else '/v1'),r+'_SECRET') for r in ('vision','tutor','diagram','asr','tts')},asr_protocol='qwen',tts_protocol='qwen',thinking='false')
        self.patches=[patch('app.ai.settings',return_value=self.cfg),patch('app.ai.USAGE_PATH',self.root/'usage.jsonl')]
        for p in self.patches:p.start()
    def tearDown(self):
        self.up.shutdown();self.up.server_close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_distinct_role_keys_and_qwen_non_thinking_without_gpt_fields(self):
        for role in ('vision','tutor','diagram'):
            ai.complete(role,[{'role':'user','content':'Return JSON.'}])
            path,payload,key=self.up.requests[-1]
            self.assertEqual(key,'Bearer '+role+'_SECRET');self.assertEqual(path,'/v1/chat/completions')
            self.assertEqual(payload['model'],getattr(self.cfg,role));self.assertIn('max_tokens',payload)
            self.assertNotIn('reasoning_effort',payload)
            if role!='tutor':self.assertIs(payload['enable_thinking'],False)
            else:
                self.assertNotIn('enable_thinking',payload)
                self.assertEqual(payload['thinking'],{'type':'disabled'})
    def test_qwen_asr_uses_audio_chat_not_multipart(self):
        self.up.reply={'choices':[{'message':{'content':'Hello tree.'}}]}
        audio='data:audio/wav;base64,'+base64.b64encode(WAV).decode()
        result=speech.handle({'action':'transcribe','audio_data':audio})
        path,payload,key=self.up.requests[-1]
        self.assertEqual(result['text'],'Hello tree.');self.assertEqual(key,'Bearer asr_SECRET')
        self.assertEqual(path,'/v1/chat/completions');self.assertEqual(payload['messages'][0]['content'][0]['input_audio']['data'],audio)
        self.assertNotIn('response_format',payload)
    def test_qwen_tts_native_protocol_inline_audio_and_existing_client_shape(self):
        self.up.reply={'output':{'audio':{'data':base64.b64encode(WAV).decode()}}}
        result=speech.handle({'action':'speak','text':'Hello tree.'})
        path,payload,key=self.up.requests[-1]
        self.assertEqual(path,'/api/v1/services/aigc/multimodal-generation/generation')
        self.assertEqual(key,'Bearer tts_SECRET');self.assertEqual(payload['input'],{'text':'Hello tree.','voice':'Cherry','language_type':'English'})
        self.assertTrue(result['audio_data'].startswith('data:audio/wav;base64,'));self.assertTrue(result['synthetic'])
    def test_qwen_tts_limit_before_upstream(self):
        with self.assertRaises(ValueError):speech.handle({'action':'speak','text':'a'*601})
        self.assertFalse(self.up.requests)
    def test_tts_download_rejects_internal_untrusted_urls(self):
        for url in ('http://127.0.0.1/x','https://evil.invalid/x','https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com.evil.invalid/x','https://user:pass@dashscope-result-bj.oss-cn-beijing.aliyuncs.com/x'):
            with patch('urllib.request.build_opener') as opener:
                with self.assertRaises(ai.ModelError):speech._qwen_audio(json.dumps({'output':{'audio':{'url':url}}}),self.cfg)
                opener.assert_not_called()
    def test_signed_result_fetch_has_no_key_and_forces_tls(self):
        response=SimpleNamespace(read=lambda limit:WAV)
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value=response
            result=speech._qwen_audio(json.dumps({'output':{'audio':{'url':'http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/x?Signature=synthetic'}}}),self.cfg)
            args,kwargs=opener.return_value.open.call_args
            self.assertTrue(args[0].startswith('https://'));self.assertEqual(set(kwargs),{'timeout'});self.assertEqual(result,WAV)
        self.assertIsNone(speech._NoRedirect().redirect_request(None,None,302,'',{},'http://127.0.0.1'))
    def test_native_error_and_fake_audio_do_not_escape_as_success(self):
        for value in ({'code':'SECRET_ERROR','output':{'audio':{}}},{'output':{'audio':{'data':base64.b64encode(b'{"not":"audio"}xxxxx').decode()}}}):
            self.up.reply=value
            with self.assertRaises(ai.ModelError) as raised:speech.handle({'action':'speak','text':'Hello.'})
            self.assertNotIn('SECRET',str(raised.exception))
    def test_real_mem0_local_index_with_official_embedding_configuration(self):
        cfg=replace(self.cfg,embedding_model='text-embedding-v4',embedding_dims=1024,
                    endpoints={**self.cfg.endpoints,'embedding':(self.base+'/v1','embedding_SECRET')})
        self.up.reply={'data':[{'index':0,'embedding':[1.0]+[0.0]*1023}]}
        row={'id':'synthetic-1','content':'synthetic memory','source_event_ids':['source-1'],'version':1,'knowledge_id':'F2','type':'fact'}
        with patch.object(ai,'settings',return_value=cfg),patch.object(ma,'_root',return_value=self.root/'mem0'),patch.dict(os.environ,{'MYTREE_MEM0_ENABLED':'1'}):
            try:
                result=ma.sync_search('synthetic',[row],'synthetic memory')
                self.assertEqual(result['status'],'ready',result)
                self.assertEqual(result['records'][0]['id'],'synthetic-1')
                path,payload,key=self.up.requests[-1]
                self.assertEqual(path,'/v1/embeddings');self.assertEqual(key,'Bearer embedding_SECRET')
                self.assertEqual(payload['model'],'text-embedding-v4');self.assertEqual(payload['dimensions'],1024)
            finally:ma.close()
    def test_embedding_key_rotation_reuses_live_index_and_uses_new_credential(self):
        cfg=replace(self.cfg,embedding_model='text-embedding-v4',embedding_dims=1024,
                    endpoints={**self.cfg.endpoints,'embedding':(self.base+'/v1','embedding_FIRST')})
        self.up.reply={'data':[{'index':0,'embedding':[1.0]+[0.0]*1023}]}
        with patch.object(ai,'settings',return_value=cfg) as settings,patch.object(ma,'_root',return_value=self.root/'rotate'):
            try:
                first=ma._memory();first.embedding_model.embed('first synthetic')
                changed=replace(cfg,endpoints={**cfg.endpoints,'embedding':(self.base+'/v1','embedding_SECOND')})
                settings.return_value=changed
                second=ma._memory()
                self.assertIs(first,second)
                second.embedding_model.embed('second synthetic')
                self.assertEqual(self.up.requests[-1][2],'Bearer embedding_SECOND')
                self.assertEqual(len(ma._instances),1)
            finally:ma.close()
    def test_logs_never_contain_payload_or_secrets(self):
        ai.complete('tutor',[{'role':'user','content':'PRIVATE_STUDENT_TEXT'}])
        log=(self.root/'usage.jsonl').read_text()
        for secret in ('PRIVATE_STUDENT_TEXT','tutor_SECRET','LEGACY_SECRET'):self.assertNotIn(secret,log)

class ConfigTests(unittest.TestCase):
    def settings(self,values):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,values,clear=True),patch.object(ai,'CONFIG_PATH',Path(d)/'missing'):
            # Restore original function: OfficialTests patches are scoped to each test.
            return ai.settings()
    def test_new_provider_never_inherits_legacy_key(self):
        cfg=self.settings({'MYTREE_API_KEY':'OLD','MYTREE_TUTOR_API_BASE':'https://api.deepseek.com'})
        self.assertEqual(ai.endpoint(cfg,'tutor'),('https://api.deepseek.com',''))
        self.assertEqual(ai.endpoint(cfg,'vision')[1],'OLD')
    def test_blank_role_key_disables_only_that_role(self):
        cfg=self.settings({'MYTREE_API_KEY':'OLD','MYTREE_VISION_API_KEY':''})
        with patch.object(ai,'settings',return_value=cfg):
            cap=ai.capabilities();self.assertFalse(cap['vision']);self.assertTrue(cap['conversation']);self.assertNotIn('OLD',json.dumps(cap))
    def test_invalid_addresses_and_protocols_rejected(self):
        for values in ({'MYTREE_TTS_API_BASE':'http://external.invalid'},{'MYTREE_TUTOR_API_BASE':'https://user:key@api.deepseek.com'},{'MYTREE_ASR_PROTOCOL':'volcano'},{'MYTREE_ENABLE_THINKING':'maybe'},{'MYTREE_EMBEDDING_DIMS':'bad'}):
            with self.assertRaises(ai.ModelError):self.settings(values)
    def test_official_private_preset_keeps_unrelated_settings_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.env.local';p.write_text('MYTREE_API_KEY=OLD\nMYTREE_SMTP_PASSWORD=KEEP\nMYTREE_TUTOR_MODEL=old\n')
            values=configure.profile_values('QWEN_SECRET','https://dashscope.aliyuncs.com/compatible-mode/v1')
            configure.write_private(p,values);self.assertEqual(p.stat().st_mode&0o777,0o600)
            with patch.dict(os.environ,{},clear=True),patch.object(ai,'CONFIG_PATH',p):cfg=ai.settings()
            self.assertEqual(ai.endpoint(cfg,'tutor')[1],'QWEN_SECRET');self.assertIn('MYTREE_SMTP_PASSWORD=KEEP',p.read_text())
            self.assertEqual(cfg.embedding_model,'text-embedding-v4');self.assertEqual(cfg.tts_protocol,'qwen')
    def test_deepseek_preset_separates_keys(self):
        values=configure.profile_values('Q','https://dashscope.aliyuncs.com/compatible-mode/v1','D','deepseek-flash')
        self.assertEqual(values['MYTREE_TUTOR_API_KEY'],'D');self.assertEqual(values['MYTREE_VISION_API_KEY'],'Q')
    def test_embedding_index_spaces_are_isolated_and_legacy_kept(self):
        cfg=ai.Settings();modern=replace(cfg,embedding_model='text-embedding-v4',embedding_dims=1024)
        with patch.object(ma,'_root',return_value=Path('/synthetic/mem0')):
            self.assertEqual(ma.index_root(cfg),Path('/synthetic/mem0'))
            self.assertNotEqual(ma.index_root(modern),ma.index_root(cfg))
            self.assertNotEqual(ma.index_root(modern),ma.index_root(replace(modern,embedding_dims=1536)))
            changed_base=replace(cfg,base='https://another-official.example/v1')
            self.assertNotEqual(ma.index_root(cfg),ma.index_root(changed_base))
            self.assertNotEqual(ma.index_root(changed_base),ma.index_root(replace(changed_base,base='https://third-official.example/v1')))
    def test_embedding_cache_requests_selected_model_and_validates_dimension(self):
        with tempfile.TemporaryDirectory() as d:
            original=SimpleNamespace(config={},client=SimpleNamespace(embeddings=unittest.mock.Mock()))
            original.client.embeddings.create.return_value=SimpleNamespace(data=[SimpleNamespace(index=0,embedding=[1.0,0.0])])
            cache=ma.CachedEmbedding(original,Path(d),'text-embedding-v4',2)
            self.assertEqual(cache.embed('synthetic'),[1.0,0.0]);cache.embed('synthetic')
            original.client.embeddings.create.assert_called_once_with(model='text-embedding-v4',input=['synthetic'],dimensions=2)
            original.client.embeddings.create.return_value=SimpleNamespace(data=[SimpleNamespace(index=0,embedding=[1.0])])
            with self.assertRaises(RuntimeError):cache.embed('different')

if __name__=='__main__':unittest.main(verbosity=2)
