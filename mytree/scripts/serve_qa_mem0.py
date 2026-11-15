"""Synthetic authenticated learners; real Mem0/embedding and math workflow."""
import hashlib,json,os,signal,sys,tempfile,time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import auth,cards,store,mem0_adapter
from app.schedule import now
from app.server import Handler
with tempfile.TemporaryDirectory(prefix='mytree-mem0-qa-') as folder:
 with patch.dict(os.environ,{'MYTREE_AUTH_MODE':'email','MYTREE_AUTH_DB':folder+'/auth.db','MYTREE_AUTH_SECRET':'SYNTHETIC_QA_ONLY','MYTREE_COOKIE_SECURE':'0','MYTREE_MEMORY_DB':folder+'/memory.db','MYTREE_MEM0_ENABLED':'1'}),patch('app.profile._PATH',folder+'/profiles.json'):
  users=[]
  for i in range(2):
   owner='qa_mem0_'+str(i);email='mem0_'+str(i)+'@example.test';token=('SYNTHETIC_MEM0_'+str(i)).ljust(43,'x')
   with auth._db() as db:
    db.execute('INSERT INTO users VALUES(?,?,?)',(email,owner,0));db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,time.time()+3600))
   source=cards.study(owner,{'problem':'x^2-9','steps':['(x-3)^2'] if i==0 else ['(x-3)*(x+3)']},'source',strict=False)['output']['wrong_card']
   if i==0:store.update(owner,lambda p:p['reviews']['F2'].update(due=(now()-timedelta(days=1)).isoformat()))
   users.append({'token':token,'source':source['id'],'owner':owner})
  class QAHandler(Handler):
   def do_GET(self):
    # Test-only control channel on loopback. Never part of the production handler.
    if self.path.startswith('/__qa/memory-failure/'):
     self.server.memory_failure=self.path.endswith('/on');return self._json(200,{'ok':True})
    if self.path=='/__qa/answers':
     p=store.read('qa_mem0_0');return self._json(200,{q['id']:{i['id']:i['answer_latex'] for i in q['items'].values()} for q in p['quizzes'].values()})
    if self.path=='/__qa/restart-index':mem0_adapter.close();return self._json(200,{'ok':True})
    return super().do_GET()
   def do_POST(self):
    if getattr(self.server,'memory_failure',False) and self.path in ('/api/memory','/api/review/personalize'):
     with patch('app.mem0_adapter._memory',side_effect=TimeoutError()):return super().do_POST()
    return super().do_POST()
  http=ThreadingHTTPServer(('127.0.0.1',0),QAHandler)
  signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
  print(json.dumps({'base':'http://127.0.0.1:'+str(http.server_address[1]),'users':users}),flush=True)
  try:http.serve_forever()
  finally:mem0_adapter.close()
