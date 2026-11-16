"""FR-018: durable OTP, sessions, authorization and HTTP boundary tests."""
import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import auth, profile
from test_all import _serve


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'MYTREE_AUTH_MODE':'email','MYTREE_AUTH_DB':self.temp.name+'/auth.sqlite3','MYTREE_AUTH_SECRET':'TEST_ONLY_RANDOM_SECRET','MYTREE_COOKIE_SECURE':'0','MYTREE_TRUST_PROXY':'0','MYTREE_PUBLIC_ORIGIN':'','MYTREE_SMTP_CONFIG':self.temp.name+'/no-smtp'})
        self.env.start()
        self.profile=patch.object(profile,'_PATH',self.temp.name+'/profiles.json');self.profile.start()
        self.ready=patch('app.auth.mail_ready',return_value=True);self.ready.start()
        self.sent={}
        self.send=patch('app.auth.send_code',side_effect=lambda email,code:self.sent.__setitem__(email,code));self.send.start()
        self.http,self.base=_serve()
    def tearDown(self):
        self.http.shutdown();self.http.server_close()
        self.send.stop();self.ready.stop();self.profile.stop();self.env.stop();self.temp.cleanup()
    def req(self,path,body=None,cookie='',origin=None,extra=None):
        headers={'Content-Type':'application/json','Origin':self.base if origin is None else origin,'Cookie':cookie,**(extra or {})}
        req=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:r=urllib.request.build_opener(NoRedirect).open(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        with r:
            raw=r.read()
            try:data=json.loads(raw)
            except (ValueError,UnicodeError):data=raw.decode()
            return r.status,data,r.headers
    def login(self,email='first@example.test',ip='127.0.0.1'):
        auth.request_code(email,ip)
        account,token=auth.verify_code(email,self.sent[email],ip)
        return account,auth.COOKIE+'='+token
    def test_unlogged_redirects_no_basic_challenge_and_old_basic_refused(self):
        for path in ('/tree','/parent','/plan','/explore'):
            status,_,h=self.req(path);self.assertEqual(status,303);self.assertEqual(h['Location'],'/login?next=%2Fparent' if path=='/parent' else '/login');self.assertIsNone(h['WWW-Authenticate'])
        status,_,h=self.req('/api/profile',extra={'Authorization':'Basic dHJlZTpvbGQ='});self.assertEqual(status,401);self.assertIsNone(h['WWW-Authenticate'])
        for path in ('/','/welcome','/home.css','/home.js','/signup','/login','/login.js','/login.css','/favicon.svg','/_ready'):
            self.assertEqual(self.req(path)[0],200)
        self.assertEqual(self.req('/api/speech',{'action':'speak'})[0],401)
        self.assertEqual(self.req('/api/knowledge/learn',{'action':'open','card_id':'card'})[0],401)
    def test_public_home_preserves_signed_in_desk_and_private_assets(self):
        status,body,_=self.req('/')
        self.assertEqual(status,200);self.assertIn('id="home-main"',body)
        self.assertNotIn('id="app"',body)
        for path in ('/app.js','/focus-ui.js','/learning-ui.js','/style.css','/api/agent','/api/profile'):
            self.assertEqual(self.req(path)[0],401)
        _,cookie=self.login()
        status,body,_=self.req('/',cookie=cookie)
        self.assertEqual(status,200);self.assertIn('id="app"',body)
        self.assertNotIn('id="home-main"',body)

    def test_register_me_and_relogin_reuse_same_profile(self):
        status,result,_=self.req('/api/auth/code',{'email':'First@Example.test'});self.assertEqual(status,200);self.assertNotIn(self.sent['first@example.test'],json.dumps(result))
        status,user,h=self.req('/api/auth/verify',{'email':'first@example.test','code':self.sent['first@example.test']});self.assertEqual(status,200);self.assertTrue(user['created'])
        self.assertIn('HttpOnly',h['Set-Cookie']);self.assertIn('SameSite=Strict',h['Set-Cookie']);cookie=h['Set-Cookie'].split(';')[0]
        status,me,_=self.req('/api/auth/me',cookie=cookie);self.assertEqual(status,200);self.assertEqual(me['user']['profile_id'],user['profile_id'])
        self.assertEqual(self.req('/api/auth/verify',{'email':'first@example.test','code':self.sent['first@example.test']})[0],400)
        with patch('app.auth.time.time',return_value=auth.time.time()+61):
            next_user,_=self.login()
        self.assertFalse(next_user['created']);self.assertEqual(next_user['profile_id'],user['profile_id'])
    def test_wrong_code_attempts_persist_and_limit(self):
        auth.request_code('first@example.test','ip')
        wrong='000000' if self.sent['first@example.test']!='000000' else '000001'
        for _ in range(5):
            with self.assertRaises(auth.AuthError):auth.verify_code('first@example.test',wrong,'ip')
        with self.assertRaises(auth.AuthError):auth.verify_code('first@example.test',self.sent['first@example.test'],'ip')
        with auth._db() as c:self.assertEqual(c.execute('SELECT attempts FROM codes').fetchone()[0],5)
    def test_expired_code_and_old_code_after_resend(self):
        auth.request_code('first@example.test','ip');old=self.sent['first@example.test'];now=auth.time.time()
        with patch('app.auth.time.time',return_value=now+601):
            with self.assertRaises(auth.AuthError):auth.verify_code('first@example.test',old,'ip')
            with patch('app.auth.secrets.randbelow',return_value=(int(old)+1)%1000000):auth.request_code('first@example.test','ip')
            with self.assertRaises(auth.AuthError):auth.verify_code('first@example.test',old,'ip')
            self.assertTrue(auth.verify_code('first@example.test',self.sent['first@example.test'],'ip')[0]['created'])
    def test_email_and_ip_send_limits(self):
        auth.request_code('first@example.test','ip')
        with self.assertRaises(auth.AuthError) as e:auth.request_code('first@example.test','ip')
        self.assertEqual(e.exception.status,429)
        for i in range(19):auth.request_code(f'user{i}@example.test','ip')
        with self.assertRaises(auth.AuthError) as e:auth.request_code('next@example.test','ip')
        self.assertEqual(e.exception.status,429)
    def test_global_send_limit(self):
        with auth._db() as c:c.executemany('INSERT INTO rates VALUES (?,?)',[('all-send',auth.time.time())]*100)
        with self.assertRaises(auth.AuthError) as e:auth.request_code('first@example.test','ip')
        self.assertEqual(e.exception.status,429)
    def test_email_daily_send_limit(self):
        with auth._db() as c:c.executemany('INSERT INTO rates VALUES (?,?)',[(auth._digest('email:first@example.test'),auth.time.time())]*10)
        with self.assertRaises(auth.AuthError) as e:auth.request_code('first@example.test','ip')
        self.assertEqual(e.exception.status,429)
    def test_verify_ip_limit_persists_even_without_code(self):
        for _ in range(60):
            with self.assertRaises(auth.AuthError):auth.verify_code('first@example.test','123456','ip')
        with self.assertRaises(auth.AuthError) as e:auth.verify_code('first@example.test','123456','ip')
        self.assertEqual(e.exception.status,429)
    def test_failed_mail_does_not_leave_usable_code(self):
        with patch('app.auth.send_code',side_effect=auth.AuthError('发送失败','MAIL_SEND_FAILED',503)):
            self.assertEqual(self.req('/api/auth/code',{'email':'first@example.test'})[0],503)
        with auth._db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM codes').fetchone()[0],0)
    def test_unconfigured_mail_fails_closed(self):
        with patch('app.auth.mail_ready',return_value=False):
            status,data,_=self.req('/api/auth/code',{'email':'first@example.test'});self.assertEqual(status,503);self.assertEqual(data['code'],'MAIL_UNAVAILABLE')
        self.assertFalse(self.sent)
    def test_logout_and_expired_cookie(self):
        _,cookie=self.login();self.assertEqual(self.req('/api/auth/me',cookie=cookie)[0],200)
        self.assertEqual(self.req('/api/auth/logout',{},cookie=cookie)[0],200)
        self.assertEqual(self.req('/api/auth/me',cookie=cookie)[0],401)
        with patch('app.auth.time.time',return_value=auth.time.time()+61):_,cookie=self.login()
        with patch('app.auth.time.time',return_value=auth.time.time()+auth.SESSION_TTL+62):self.assertEqual(self.req('/api/auth/me',cookie=cookie)[0],401)
    def test_other_account_cannot_select_profile_or_subject(self):
        a,ca=self.login();b,cb=self.login('second@example.test')
        with profile._lock:
            data=profile._load();profile._student(data,a['profile_id'])['history']=17;profile._save(data)
        self.assertEqual(self.req('/api/profile?student='+a['profile_id'],cookie=cb)[1]['history'],0)
        self.assertEqual(self.req('/api/profile?student='+b['profile_id'],cookie=ca)[1]['history'],17)
        with patch('app.server.agent.handle',return_value=({'ok':True},200)) as handle:
            self.req('/api/agent',{'subject':{'profile_id':a['profile_id']}},cookie=cb)
            body=handle.call_args.args[0];self.assertEqual(body['subject']['profile_id'],b['profile_id']);self.assertNotIn('student',body)
        with patch('app.server.profile.set_availability',return_value={}) as write:
            self.req('/api/availability',{'student':a['profile_id'],'availability':{}},cookie=cb)
            self.assertEqual(write.call_args.args[0],b['profile_id'])
    def test_authenticated_real_agent_and_cross_account_sources(self):
        from app import cards,store
        a,ca=self.login();b,cb=self.login('second@example.test')
        card=cards.study(a['profile_id'],{'problem':'x^2-9','steps':['(x-3)^2']},'source',strict=False)['output']['wrong_card']
        def envelope(operation,input,target):
            return {'schema_version':'1.0','request_id':'real-'+operation,'operation':operation,'client':{'type':'web','name':'test'},'subject':{'profile_id':target},'input':input}
        request=envelope('card.list',{'type':'wrong','limit':10},a['profile_id'])
        status,result,_=self.req('/api/agent',request,cookie=ca)
        self.assertEqual(status,200,result);self.assertEqual(result['output']['items'][0]['id'],card['id'])
        for operation in ('review.today','tree.get'):
            status,result,_=self.req('/api/agent',envelope(operation,{},a['profile_id']),cookie=ca)
            self.assertEqual(status,200,result)
        status,result,_=self.req('/api/agent',envelope('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[card['id']]},a['profile_id']),cookie=ca)
        self.assertEqual(status,422,result);self.assertEqual(result['error']['code'],'UNSUPPORTED')
        status,result,_=self.req('/api/agent',request,cookie=cb)
        self.assertEqual(status,200,result);self.assertFalse(result['output']['items'])
        request=envelope('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':[card['id']]},a['profile_id'])
        status,result,_=self.req('/api/agent',request,cookie=cb)
        self.assertEqual(status,422,result);self.assertFalse(store.read(b['profile_id'])['quizzes'])
        status,result,_=self.req('/api/hint',{'diagnosis_id':card['diagnosis_id'],'level':1},cookie=ca)
        self.assertEqual(status,200,result)
        status,result,_=self.req('/api/hint',{'diagnosis_id':card['diagnosis_id'],'level':1},cookie=cb)
        self.assertNotEqual(status,200,result);self.assertFalse(store.read(b['profile_id'])['hint_views'])
        # Even a malicious extra top-level student remains a contract error.
        request=envelope('card.list',{'type':'wrong','limit':10},a['profile_id']);request['student']=a['profile_id']
        self.assertEqual(self.req('/api/agent',request,cookie=ca)[0],400)
    def test_cross_origin_rejected_even_before_login(self):
        for path,body in (('/api/auth/code',{'email':'first@example.test'}),('/api/auth/verify',{'email':'first@example.test','code':'123456'}),('/api/auth/logout',{}),('/api/availability',{})):
            self.assertEqual(self.req(path,body,origin='https://attacker.test')[0],403)
            self.assertEqual(self.req(path,body,origin='null')[0],403)
    def test_otp_is_consumed_atomically(self):
        auth.request_code('first@example.test','ip');code=self.sent['first@example.test']
        def verify(_):
            try:return auth.verify_code('first@example.test',code,'ip')[0]['created']
            except auth.AuthError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted([str(x) for x in pool.map(verify,range(2))]),['None','True'])
    def test_secrets_not_stored_as_plaintext_and_secure_cookie(self):
        user,cookie=self.login();token=cookie.split('=')[1]
        with auth._db() as c:
            session=c.execute('SELECT digest FROM sessions').fetchone()[0];self.assertNotEqual(session,token)
        self.assertEqual(os.stat(auth._path()).st_mode&0o777,0o600)
        with patch.dict(os.environ,{'MYTREE_COOKIE_SECURE':'1'}):self.assertIn('; Secure',auth.cookie_header())
    def test_invalid_email_code_cookie_inputs(self):
        for email in ('x','x@example.test\r\nBcc: other@example.test','a..b@example.test',123):
            self.assertEqual(self.req('/api/auth/code',{'email':email})[0],400)
        for code in ('12345','１２３４５６',123456):
            self.assertEqual(self.req('/api/auth/verify',{'email':'first@example.test','code':code})[0],400)
        for cookie in ('mytree_session=???','x=y','mytree_session='+('x'*10000)):
            self.assertIsNone(auth.session(cookie))
    def test_smtp_ssl_and_no_sensitive_error_details(self):
        with patch('app.auth.smtp_settings',return_value={'host':'smtp.qq.com','port':465,'user':'sender@example.test','password':'PRIVATE_TEST_SMTP','from':'sender@example.test'}),patch('app.auth.smtplib.SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            # Use real sender, bypassing this fixture's code capture.
            self.send.stop()
            try:auth.send_code('recipient@example.test','123456')
            finally:self.send.start()
            self.assertEqual(smtp.call_args.args,('smtp.qq.com',465));self.assertIsNotNone(smtp.call_args.kwargs['context'])
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0];self.assertEqual(message['To'],'recipient@example.test')

if __name__=='__main__':unittest.main(verbosity=2)
