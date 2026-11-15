"""Isolated email-session QA; synthetic profiles only, no real email or models."""
import json,os,signal,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,auth,profile,agent,cards,store
from app.server import Handler
from serve_qa_phase_b import FakeModel
from PIL import Image,ImageDraw
with tempfile.TemporaryDirectory(prefix='mytree-product-qa-') as folder:
 root=Path(folder)
 image=Image.new('RGB',(600,400),'white');ImageDraw.Draw(image).text((40,70),'Factor: x^2 - 9\nWork: (x - 3)^2',fill='black');image.save(root/'synthetic.png')
 with patch.dict(os.environ,{'MYTREE_AUTH_MODE':'email','MYTREE_AUTH_DB':folder+'/auth.db','MYTREE_AUTH_SECRET':'SYNTHETIC_QA_ONLY','MYTREE_COOKIE_SECURE':'0'}),patch('app.profile._PATH',folder+'/profiles.json'),patch('app.ai.USAGE_PATH',root/'usage.jsonl'):
  users=[]
  for i in range(3):
   email=['learner@example.test','parent@example.test','stranger@example.test'][i];token=('SYNTHETIC_SESSION_'+str(i)).ljust(43,'x')
   with auth._db() as db:
    db.execute('INSERT INTO users VALUES(?,?,?)',(email,'qa_product_'+str(i),0))
    import hashlib,time
    db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,time.time()+3600))
   users.append({'email':email,'token':token})
  # Build one genuine synthetic unlock through the production qualification gates.
  source=cards.study('qa_product_0',{'problem':'x^2-9','steps':['(x-3)^2']},'qa-guide-source',strict=False)['output']['wrong_card']
  sequence=0
  def call(operation,params):
   global sequence
   sequence+=1
   result,status=agent.handle({'schema_version':'1.0','request_id':'qa_guide_'+str(sequence),'operation':operation,'client':{'type':'web','name':'test','version':'1'},'subject':{'profile_id':'qa_product_0'},'input':params})
   if status!=200:raise ValueError(result)
   return result['output']
  group=call('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[source['id']]})
  for item in store.read('qa_product_0')['quizzes'][group['quiz_id']]['items'].values():call('quiz.answer',{'quiz_id':group['quiz_id'],'exercise_id':item['id'],'answer':item['answer_latex']})
  unlocked=call('card.unlock',{'quiz_id':group['quiz_id']})
  card=next(iter(store.read('qa_product_0')['knowledge_cards'].values()))
  call('tree.move',{'action':'move','method':'menu','expected_revision':0,'card_id':card['id'],'parent_id':None,'position':{'x':48,'y':36}})
  fake=ThreadingHTTPServer(('127.0.0.1',0),FakeModel);threading.Thread(target=fake.serve_forever,daemon=True).start()
  cfg=ai.Settings('http://127.0.0.1:'+str(fake.server_address[1])+'/v1','QA_ONLY','gpt-6.1-sol','gpt-6.1-sol',5,'low')
  http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
  with patch('app.ai.settings',return_value=cfg):
   print(json.dumps({'base':'http://127.0.0.1:'+str(http.server_address[1]),'image':str(root/'synthetic.png'),'users':users}),flush=True)
   http.serve_forever()
