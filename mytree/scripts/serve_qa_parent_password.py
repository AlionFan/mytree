"""Local-only purpose OTP oracle and isolated synthetic accounts; never shipped."""
import hashlib,json,os,signal,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,os.environ.get('MYTREE_APP_ROOT',str(Path(__file__).resolve().parents[1])))
from app import auth,parent_access,store
from app.server import Handler,MyTreeHTTPServer
codes={}
class QA(Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/__qa/parent-code':
            account=auth.session(self.headers.get('Cookie'))
            if not account:return self._json(401,{'error':'test session required'})
            return self._json(200,{'code':codes.get((account['email'],parse_qs(u.query).get('purpose',[''])[0]))})
        return super().do_GET()
with tempfile.TemporaryDirectory(prefix='mytree-parent-qa-') as folder:
 with patch.dict(os.environ,{'MYTREE_AUTH_MODE':'email','MYTREE_AUTH_DB':folder+'/auth.db','MYTREE_AUTH_SECRET':'SYNTHETIC_ONLY','MYTREE_COOKIE_SECURE':'0','MYTREE_PUBLIC_ORIGIN':''}),patch('app.profile._PATH',folder+'/profiles.json'),patch('app.parent_access._send_code',side_effect=lambda email,code,purpose:codes.__setitem__((email,purpose),code)):
  users=[]
  for i in range(2):
   email=['family-a@example.test','family-b@example.test'][i];token=('PARENT_SYNTHETIC_'+str(i)).ljust(43,'x');pid='qa_parent_'+str(i)
   with auth._db() as db:
    db.execute('INSERT INTO users VALUES(?,?,?)',(email,pid,0));db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,time.time()+3600))
   store.update(pid,lambda p,i=i:p.update(practice_correct=3 if i==0 else 7,lit=['F2']))
   users.append({'email':email,'token':token})
  with auth._db() as db:
   db.execute('CREATE TABLE IF NOT EXISTS family_links(child TEXT,parent TEXT,created REAL)');db.execute('INSERT INTO family_links VALUES(?,?,?)',(users[0]['email'],users[1]['email'],0))
  server=MyTreeHTTPServer(('127.0.0.1',0),QA);signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));print(json.dumps({'base':'http://127.0.0.1:'+str(server.server_address[1]),'users':users}),flush=True);server.serve_forever()
