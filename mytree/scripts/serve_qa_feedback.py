"""Temporary synthetic 11-card / 10-question UI fixtures, zero paid calls."""
import io,json,os,signal,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,cards,profile,store
from app.server import Handler,MyTreeHTTPServer
from PIL import Image,ImageDraw
class Fake(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));items=[]
  for i in range(1,11):
   problem=fr'分解因式：\(x^2-{i*i}\)。'
   items.append({'problem':problem,'problem_latex':f'x^2-{i*i}','steps':[],'question_type':'factor','topic_id':'F2','supported':True,'printed_number':str(i),'region':[0,(i-1)/10,1,.1],'problem_complete':True,'diagram_complete':True,'answer_presence':'absent','association_status':'clear','association_evidence':'每题题号对应独立印刷题干，没有学生作答。','uncertain_lines':[],'warnings':[],'alternatives':[],'diagram_description':'','fragments':[{'role':'problem','script_kind':'printed','text':problem,'region':[0,(i-1)/10,1,.1]}]})
  result={'items':items,'unassigned_fragments':[],'overflow':False,'warnings':[]}
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps({'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]}).encode())
with tempfile.TemporaryDirectory(prefix='mytree-feedback-') as folder:
 with patch('app.profile._PATH',folder+'/profiles.json'),patch('app.ai.USAGE_PATH',Path(folder)/'usage.jsonl'),patch.dict(os.environ,{'MYTREE_MEMORY_DB':folder+'/memory.db'}):
  for i in range(1,12):
   card=cards.study('demo',{'problem':f'x^2-{i*i}','steps':[f'(x-{i})^2']},f'fixture{i}',strict=False)['output']['wrong_card']
   store.update('demo',lambda v:v['wrong_cards'][card['id']].update(problem=(r'若式子 \(\frac{1}{\sqrt{x-1}}\) 在实数范围内有意义，则x的取值范围是____。' if i==1 else r'一段较长的原题条件，面积与周长需要结合相似关系说明，题卡应自然换行且公式不能与下一张题卡叠在一起。\(a^2-4ab+4b^2=(a-2b)^2\)。')))
  im=Image.new('RGB',(1600,2400),'white');d=ImageDraw.Draw(im)
  for i in range(1,11):d.text((100,200*i),f'{i}. Factor: x^2 - {i*i}',fill='black')
  image=folder+'/page.png';im.save(image)
  fake=ThreadingHTTPServer(('127.0.0.1',0),Fake);threading.Thread(target=fake.serve_forever,daemon=True).start();cfg=ai.Settings('http://127.0.0.1:'+str(fake.server_address[1])+'/v1','SYNTHETIC','gpt-6.1-sol','gpt-6.1-sol',5)
  http=MyTreeHTTPServer(('127.0.0.1',0),Handler);signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
  with patch('app.ai.settings',return_value=cfg):
   print(json.dumps({'base':'http://127.0.0.1:'+str(http.server_address[1]),'image':image}),flush=True);http.serve_forever()
