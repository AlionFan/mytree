"""Private fake audio/vision service for explorer browser tests; zero paid calls."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io,json,signal,sys,tempfile,threading,wave
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai
from app.server import Handler,MyTreeHTTPServer

class Fake(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  raw=self.rfile.read(int(self.headers['Content-Length']))
  if self.path.endswith('/transcriptions'):result=json.dumps({'text':'What color is the notebook?'}).encode();mime='application/json'
  elif self.path.endswith('/speech'):
   out=io.BytesIO()
   with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*16000*8)
   result=out.getvalue();mime='audio/wav'
  else:
   body=json.loads(raw);prompt=body['messages'][-1]['content'][0]['text'];question='Question: ' in prompt
   previous=prompt.split('Previous description: ',1)[1].split('\n',1)[0]
   value={'description':'It looks green. The notebook has a rectangular shape.' if question else 'I can see a green notebook. A blue circle is beside it.','changed':True}
   if previous and not question:value={'description':'','changed':False}
   result=json.dumps({'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}]}).encode();mime='application/json'
  self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(result)

def main():
 with tempfile.TemporaryDirectory(prefix='mytree-explorer-qa-') as folder:
  fake=ThreadingHTTPServer(('127.0.0.1',0),Fake);threading.Thread(target=fake.serve_forever,daemon=True).start();http=MyTreeHTTPServer(('127.0.0.1',0),Handler)
  cfg=ai.Settings('http://127.0.0.1:'+str(fake.server_address[1])+'/v1','TEST_SECRET','gpt-6.1-sol','gpt-6.1-sol',5,'low')
  signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
  try:
   with patch('app.ai.settings',return_value=cfg),patch('app.ai.USAGE_PATH',Path(folder)/'usage.jsonl'),patch('app.profile._PATH',folder+'/profiles.json'):
    print(json.dumps({'base':'http://127.0.0.1:'+str(http.server_address[1]),'profile':folder+'/profiles.json'}),flush=True);http.serve_forever()
  except KeyboardInterrupt:pass
  finally:http.server_close();fake.shutdown();fake.server_close()
if __name__=='__main__':main()
