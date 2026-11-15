"""本地假上游验证协议、图片确认边界和讲解质检；不调用真实付费模型。"""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,profile
from app.pipeline import diagnose
from test_all import _req,_serve


def sample_image(width=240,height=180):
    from PIL import Image
    out=io.BytesIO();Image.new('RGB',(width,height),'white').save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()


class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append({'body':body,'authorization':self.headers['Authorization'],'path':self.path})
        status,result=self.server.replies.pop(0)
        self.send_response(status);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps(result).encode())


class AITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        self.upstream.requests=[];self.upstream.replies=[]
        threading.Thread(target=self.upstream.serve_forever,daemon=True).start()
        self.cfg=ai.Settings('http://127.0.0.1:'+str(self.upstream.server_address[1])+'/v1','TEST_SECRET','kimi-k3.1-pro','gpt-6.1-sol',5,'low')
        self.patches=[patch('app.ai.settings',return_value=self.cfg),patch('app.ai.USAGE_PATH',Path(self.temp.name)/'usage.jsonl'),patch('app.profile._PATH',self.temp.name+'/profiles.json')]
        for p in self.patches:p.start()
        self.httpd,self.base=_serve()
        self.analysis=diagnose('x^2-9',['(x-3)^2'])['analysis']

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.upstream.shutdown();self.upstream.server_close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def reply(self,result,status=200):
        data={'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)},'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
        self.upstream.replies.append((status,data if status==200 else result))

    def test_diagram_role_is_independent_of_vision_and_text_tutor(self):
        for operation,expected in [('diagram','glm-5.3-flash'),('vision','kimi-k3.1-pro'),('tutor','gpt-6.1-sol')]:
            self.reply({'ok':True})
            result,meta=ai.complete(operation,[{'role':'user','content':'synthetic role check'}])
            self.assertEqual(self.upstream.requests[-1]['body']['model'],expected)
            self.assertEqual(meta['model'],expected)
        self.assertEqual(ai.capabilities()['diagram_model'],'glm-5.3-flash')

    def test_photo_transcription_requires_confirmation_and_does_not_grade(self):
        self.reply({'problem':'x^2-9','steps':['(x-3)^2'],'supported':True,'multiple_questions':False,'warnings':[],'uncertain_lines':[]})
        status,raw=_req(self.base,'POST','/api/recognize',{'student':'photo_test','image_data':sample_image(1900,1000)})
        self.assertEqual(status,200,raw)
        result=json.loads(raw)
        self.assertTrue(result['needs_confirmation'])
        self.assertEqual(result['steps'],['(x-3)^2'])  # 学生错误必须原样保留。
        self.assertEqual(profile.get('photo_test')['history'],0)
        request=self.upstream.requests[0]
        self.assertEqual(request['path'],'/v1/chat/completions')
        self.assertEqual(request['authorization'],'Bearer TEST_SECRET')
        self.assertIn('max_tokens',request['body'])
        self.assertEqual(request['body']['model'],'kimi-k3.1-pro')
        self.assertEqual(request['body']['temperature'],0)
        self.assertNotIn('reasoning_effort',request['body'])
        self.assertEqual(request['body']['response_format'],{'type':'json_object'})
        image=request['body']['messages'][1]['content'][1]['image_url']['url']
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(image.split(',')[1]))) as uploaded:
            self.assertEqual(uploaded.width,1600)
        usage=Path(self.temp.name,'usage.jsonl').read_text()
        self.assertNotIn('TEST_SECRET',usage);self.assertNotIn('base64',usage);self.assertNotIn('x^2',usage)

    def test_image_input_rejects_urls_invalid_bytes_and_tiny_images(self):
        for data in ('https://private.invalid/picture.png','data:image/png;base64,AA==',sample_image(10,10)):
            with self.assertRaises(ValueError):ai.prepare_image(data)
        self.assertFalse(self.upstream.requests)

    def test_unclear_ocr_and_multiple_questions_are_not_silently_corrected(self):
        self.reply({'problem':'x^2-?','steps':[],'supported':True,'multiple_questions':True,'warnings':['题干看不清'],'uncertain_lines':[]})
        result=ai.recognize(sample_image())
        self.assertEqual(result['problem'],'x^2-?');self.assertIn(0,result['uncertain_lines']);self.assertTrue(result['multiple_questions'])

    def test_tutor_uses_saved_diagnosis_and_validated_equation(self):
        event=profile.record('owner',self.analysis,'x^2-9')
        self.reply({'reply':'面积没有变化，只是重新拼成了长方形。你能把每一块对应回去吗？','equations':[{'left':'x^2-9','right':'(x-3)(x+3)'}]})
        status,raw=_req(self.base,'POST','/api/chat',{'student':'owner','diagnosis_id':event['id'],'question':'讲完整思路','level':3,'analysis':{'target':'fake'}})
        self.assertEqual(status,200,raw)
        result=json.loads(raw);self.assertFalse(result['fallback']);self.assertEqual(len(result['equations']),1)
        request=self.upstream.requests[0]['body'];self.assertIn('max_completion_tokens',request);self.assertNotIn('max_tokens',request)
        self.assertNotIn('fake',json.dumps(request));self.assertEqual(request['model'],'gpt-6.1-sol')
        context=json.loads(request['messages'][1]['content'].split('：',1)[1])
        self.assertEqual(context['visual'],'difference_of_squares')
        self.assertTrue(any('正方形' in label for label in context['visual_labels']))
        status,_=_req(self.base,'POST','/api/chat',{'student':'other','diagnosis_id':event['id'],'question':'讲解','level':3})
        self.assertEqual(status,400);self.assertEqual(len(self.upstream.requests),1)

    def test_low_hint_answer_leaks_and_bad_math_fall_back_honestly(self):
        for result in [
            {'reply':'最终就是 (x+3)(x-3)。','equations':[]},
            {'reply':'这个式子直接相等。','equations':[{'left':'x^2-9','right':'(x-3)^2'}]},
            {'reply':'答案见等式。','equations':[{'left':'x^2-9','right':'(x+3)(x-3)'}]},
            {'reply':'x^2-9=(x-3)(x+3)','equations':[]},
        ]:
            self.reply(result)
            output=ai.tutor(self.analysis,'告诉我答案',1)
            self.assertTrue(output['fallback']);self.assertEqual(output['source'],'checked_hint');self.assertEqual(output['reply'],self.analysis['hints'][0])

    def test_upstream_auth_errors_are_sanitized(self):
        self.reply({'error':'TEST_SECRET should never be forwarded'},401)
        with self.assertRaises(ai.ModelError) as caught:ai.recognize(sample_image())
        self.assertEqual(caught.exception.code,'MODEL_AUTH_ERROR');self.assertNotIn('TEST_SECRET',str(caught.exception))
        self.assertNotIn('TEST_SECRET',Path(self.temp.name,'usage.jsonl').read_text())

    def test_malformed_model_output_does_not_crash_service(self):
        self.reply({'problem':'x','steps':'not an array'})
        with self.assertRaises(ai.ModelError):ai.recognize(sample_image())

    def test_public_capabilities_never_include_credentials(self):
        status,raw=_req(self.base,'GET','/api/capabilities')
        self.assertEqual(status,200);self.assertNotIn(b'TEST_SECRET',raw)
        self.assertTrue(json.loads(raw)['vision'])
        self.assertNotIn('TEST_SECRET',repr(self.cfg))
        self.assertEqual(_req(self.base,'GET','/.env.local')[0],404)

if __name__=='__main__':unittest.main(verbosity=2)
