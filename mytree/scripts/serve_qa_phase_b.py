"""Isolated browser QA service: fake model, synthetic image, temporary profile.

The test-only oracle exists only in this Handler subclass, never in the app.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import signal
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,profile
from app.server import Handler
from PIL import Image,ImageDraw


class FakeModel(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if body['model']!='gpt-6.1-sol':raise ValueError('Unexpected QA model')
        result={'problem':r'分解因式：\(x^2-9\)。','problem_latex':'x^2-9','steps':[r'\((x-3)^2\)'],
            'question_type':'factor','topic_id':'F2','supported':True,'multiple_questions':False,'warnings':[],'uncertain_lines':[]}
        if '本次是整页识别' in json.dumps(body,ensure_ascii=False):
            result={'items':[{**result,'printed_number':'1','region':[0,0,1,1],
                 'problem_complete':True,'diagram_complete':True,'answer_presence':'present','association_status':'clear','association_evidence':'明确题号、笔迹连续且仅属于本题。',
                 'fragments':[{'role':'problem','script_kind':'printed','text':result['problem'],'region':[0,0,1,0.4]},
                              {'role':'student_work','script_kind':'handwritten','text':result['steps'][0],'region':[0,0.4,1,0.5]}]}],
                    'overflow':False,'unassigned_fragments':[],'warnings':[]}
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]}).encode())


class QAHandler(Handler):
    def do_GET(self):
        if self.path.startswith('/__qa/answers?'):
            args=parse_qs(urlparse(self.path).query)
            value=profile._student(profile._load(),args['student'][0]);quiz=value['quizzes'][args['quiz'][0]]
            return self._json(200,{key:item['answer_latex'] for key,item in quiz['items'].items()})
        return super().do_GET()


def main():
    with tempfile.TemporaryDirectory(prefix='mytree-b-ui-') as directory:
        root=Path(directory)
        image=Image.new('RGB',(600,300),'white');ImageDraw.Draw(image).text((40,70),'Factor: x^2 - 9\nWork: (x - 3)^2',fill='black');image.save(root/'synthetic.png')
        fake=ThreadingHTTPServer(('127.0.0.1',0),FakeModel)
        threading.Thread(target=fake.serve_forever,daemon=True).start()
        cfg=ai.Settings('http://127.0.0.1:'+str(fake.server_address[1])+'/v1','SYNTHETIC_TEST_KEY','gpt-6.1-sol','gpt-6.1-sol',5,'low')
        http=ThreadingHTTPServer(('127.0.0.1',0),QAHandler)
        signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
        try:
            with patch('app.ai.settings',return_value=cfg),patch('app.ai.USAGE_PATH',root/'usage.jsonl'),patch('app.profile._PATH',str(root/'profiles.json')):
                print(json.dumps({'base':'http://127.0.0.1:'+str(http.server_address[1]),'profile':str(root/'profiles.json'),'image':str(root/'synthetic.png')}),flush=True)
                http.serve_forever()
        except KeyboardInterrupt:pass
        finally:
            http.server_close();fake.shutdown();fake.server_close()


if __name__=='__main__':main()
