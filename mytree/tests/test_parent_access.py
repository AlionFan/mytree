"""Same-account parent mode: purpose OTP, password, session and migration boundaries."""
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_auth
from app import auth, family, parent_access


class ParentAccessTests(unittest.TestCase):
    setUp=test_auth.AuthTests.setUp
    tearDown=test_auth.AuthTests.tearDown
    req=test_auth.AuthTests.req
    login=test_auth.AuthTests.login

    def code(self,account,cookie,purpose='parent_setup'):
        sent={}
        with patch('app.parent_access._send_code',side_effect=lambda email,code,purpose:sent.update(code=code,email=email,purpose=purpose)):
            parent_access.request_code(account,cookie,purpose,'test-parent-ip')
        return sent['code']

    def setup_parent(self,account,cookie,password='Parent-example-2026'):
        code=self.code(account,cookie)
        data,header=parent_access.handle(account,cookie,'setup',{'password':password,'confirm_password':password,'code':code},'test-parent-ip')
        return cookie+'; '+header.split(';',1)[0],data

    def test_setup_own_profile_and_lock_keeps_base_login(self):
        account,base=self.login();header,data=self.setup_parent(account,base)
        self.assertTrue(parent_access.status(account,header)['unlocked'])
        self.assertFalse(parent_access.status(account,base)['unlocked'])
        with patch('app.family.profile.get',return_value={'practice_correct':3,'tree':[{'lit':True}],'reviews':[],'recent':[]}):
            self.assertEqual(family.overview(account,header)['profile']['practice_correct'],3)
        parent_access.lock(account,header)
        with self.assertRaises(auth.AuthError):family.overview(account,header)
        self.assertEqual(auth.session(base)['profile_id'],account['profile_id'])
        with auth._db() as db:
            row=db.execute('SELECT * FROM parent_passwords').fetchone()
            self.assertNotIn('Parent-example-2026',str(dict(row)))
            self.assertFalse(db.execute('SELECT * FROM parent_codes').fetchall())
        self.assertIn('HttpOnly',parent_access.cookie('x'*43));self.assertIn('SameSite=Strict',parent_access.cookie('x'*43))

    def test_wrong_purpose_login_code_reuse_and_cross_account(self):
        a,ac=self.login('a@example.test','a');b,bc=self.login('b@example.test','b')
        auth.request_code(a['email'],'login-again');login_code=self.sent[a['email']]
        for account,cookie,code in [(a,ac,login_code),(b,bc,self.code(a,ac))]:
            with self.assertRaises(auth.AuthError):parent_access.handle(account,cookie,'setup',{'password':'Password-123','confirm_password':'Password-123','code':code},'try-purpose')
        # A valid setup OTP cannot be consumed as a reset OTP.
        code=self.code(b,bc)
        with self.assertRaises(auth.AuthError):parent_access.handle(b,bc,'reset',{'password':'Password-123','confirm_password':'Password-123','code':code},'try-purpose')
        header,_=parent_access.handle(b,bc,'setup',{'password':'Password-123','confirm_password':'Password-123','code':code},'try-purpose')
        with self.assertRaises(auth.AuthError):parent_access.handle(b,bc,'setup',{'password':'Password-123','confirm_password':'Password-123','code':code},'try-purpose')

    def test_expiry_logout_and_cross_base_session(self):
        a,base=self.login();header,data=self.setup_parent(a,base)
        _,base2=self.login(a['email'],'other-browser')
        parent_cookie=header.split('; ',1)[1]
        self.assertFalse(parent_access.status(a,base2+'; '+parent_cookie)['unlocked'])
        with patch('app.parent_access.time.time',return_value=data['expires_at']+1):self.assertFalse(parent_access.status(a,header)['unlocked'])
        auth.logout(base)
        with self.assertRaises(auth.AuthError):parent_access.status(a,header)

    def test_reset_revokes_all_parent_sessions_and_old_password(self):
        a,base=self.login();header,_=self.setup_parent(a,base)
        code=self.code(a,base,'parent_reset')
        result,new_cookie=parent_access.handle(a,base,'reset',{'password':'New-parent-123','confirm_password':'New-parent-123','code':code},'reset-ip')
        self.assertFalse(parent_access.status(a,header)['unlocked'])
        with self.assertRaises(auth.AuthError):parent_access.handle(a,base,'unlock',{'password':'Parent-example-2026'},'unlock-ip')
        _,cookie=parent_access.handle(a,base,'unlock',{'password':'New-parent-123'},'unlock-ip')
        self.assertTrue(parent_access.status(a,base+'; '+cookie.split(';',1)[0])['unlocked'])

    def test_password_failures_cooldown_and_success_not_counted(self):
        a,base=self.login();self.setup_parent(a,base)
        for _ in range(5):
            with self.assertRaises(auth.AuthError) as e:parent_access.handle(a,base,'unlock',{'password':'Wrong-Password'},'fail-ip')
            self.assertEqual(e.exception.code,'PARENT_PASSWORD_INVALID')
        with self.assertRaises(auth.AuthError) as e:parent_access.handle(a,base,'unlock',{'password':'Parent-example-2026'},'fail-ip')
        self.assertEqual(e.exception.status,429)
        with patch('app.parent_access.time.time',return_value=time.time()+601):
            for _ in range(6):parent_access.handle(a,base,'unlock',{'password':'Parent-example-2026'},'fail-ip')

    def test_setup_concurrent_has_one_winner(self):
        a,base=self.login();code=self.code(a,base)
        def run(_):
            try:parent_access.handle(a,base,'setup',{'password':'Concurrent-123','confirm_password':'Concurrent-123','code':code},'race-ip');return True
            except auth.AuthError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sorted(pool.map(run,range(2))),[False,True])

    def test_expired_wrong_codes_attempts_and_send_failure(self):
        a,base=self.login();code=self.code(a,base)
        with patch('app.parent_access.time.time',return_value=time.time()+601):
            with self.assertRaises(auth.AuthError):parent_access.handle(a,base,'setup',{'password':'Password-123','confirm_password':'Password-123','code':code},'expiry-ip')
        with auth._db() as db:db.execute('DELETE FROM parent_codes')
        with patch('app.parent_access._send_code',side_effect=auth.AuthError('发送失败','MAIL_SEND_FAILED',503)):
            with self.assertRaises(auth.AuthError):parent_access.request_code(a,base,'parent_setup','failure-ip')
        with auth._db() as db:self.assertFalse(db.execute('SELECT * FROM parent_codes').fetchall())

    def test_old_relations_cannot_authorize(self):
        a,base=self.login();b,bc=self.login('other@example.test','other')
        with auth._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS family_links(child TEXT,parent TEXT,created REAL)')
            db.execute('INSERT INTO family_links VALUES(?,?,?)',(b['email'],a['email'],0))
        with self.assertRaises(auth.AuthError) as e:family.overview(a,base)
        self.assertEqual(e.exception.code,'PARENT_LOCKED')
        for action in ('invite','accept','revoke'):
            with self.assertRaises(auth.AuthError) as e:parent_access.handle(a,base,action,{},'legacy-ip')
            self.assertEqual(e.exception.status,410)
        with auth._db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM family_links').fetchone()[0],1)
        from app import store
        store.update(a['profile_id'],lambda p:p.update(practice_correct=3))
        store.update(b['profile_id'],lambda p:p.update(practice_correct=7))
        header,_=self.setup_parent(a,base)
        self.assertEqual(family.overview(a,header)['profile']['practice_correct'],3)

    def test_http_gate_cookie_refresh_and_origin(self):
        a,base=self.login();sent={}
        self.assertEqual(self.req('/api/parent/status')[0],401)
        self.assertEqual(self.req('/api/parent/overview',cookie=base)[0],403)
        with patch('app.parent_access._send_code',side_effect=lambda email,code,purpose:sent.update(code=code)):
            self.assertEqual(self.req('/api/parent/send-code',{'purpose':'parent_setup'},cookie=base,origin='https://foreign.test')[0],403)
            self.assertEqual(self.req('/api/parent/send-code',{'purpose':'parent_setup'},cookie=base)[0],200)
        status,data,headers=self.req('/api/parent/setup',{'password':'Password-123','confirm_password':'Password-123','code':sent['code']},cookie=base)
        self.assertEqual(status,200,data);parent=base+'; '+headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.req('/api/parent/overview?student=other',cookie=parent)[0],200)
        self.assertEqual(self.req('/parent',cookie=parent)[0],200)
        self.assertEqual(self.req('/api/parent/overview',cookie=parent)[0],403)
        self.assertEqual(self.req('/api/profile',cookie=base)[0],200)
        self.assertEqual(self.req('/api/parent/invite',{'email':'other@example.test'},cookie=base)[0],410)

    def test_http_other_cookie_and_reset_password_format(self):
        a,base=self.login();header,_=self.setup_parent(a,base)
        b,bc=self.login('other@example.test','other')
        self.assertEqual(self.req('/api/parent/overview',cookie=bc+'; '+header.split('; ',1)[1])[0],403)
        for password in ('short','x'*129):
            self.assertEqual(self.req('/api/parent/unlock',{'password':password},cookie=base)[0],400)
        self.assertEqual(self.req('/api/parent/unlock',{'password':'Parent-example-2026','profile_id':b['profile_id']},cookie=base)[0],400)

    def test_parent_mail_template_has_explicit_purpose(self):
        captured=[]
        class SMTP:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def login(self,*args):pass
            def send_message(self,message):captured.append(message);return {}
        config={'host':'smtp.example.test','port':465,'from':'sender@example.test','user':'FAKE_USER','password':'FAKE_TEST_ONLY'}
        with patch('app.auth.smtp_settings',return_value=config),patch('app.auth.mail_ready',return_value=True),patch('app.auth.smtplib.SMTP_SSL',return_value=SMTP()):
            parent_access._send_code('family@example.test','123456','parent_reset')
        self.assertIn('重置家长密码',captured[0]['Subject'])
        for part in (captured[0].get_body(preferencelist=('plain',)),captured[0].get_body(preferencelist=('html',))):
            text=part.get_content();self.assertIn('仅用于当前账号重置家长密码',text);self.assertNotIn('首次验证后将创建账号',text)

    def test_setup_and_legacy_disable_do_not_reassign_learning_data(self):
        from app import store,profile
        from pathlib import Path
        a,base=self.login();store.update(a['profile_id'],lambda p:p.update(practice_correct=9,lit=['F2']))
        before=Path(profile._PATH).read_bytes();header,_=self.setup_parent(a,base)
        data=family.overview(a,header)
        self.assertEqual(data['profile']['practice_correct'],9)
        self.assertEqual(Path(profile._PATH).read_bytes(),before)
