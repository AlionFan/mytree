"""Independent parent/admin entry points and server-side role boundaries."""
import hashlib,json,os,time,unittest
from unittest.mock import patch
import test_auth
from app import auth

class RoleTests(unittest.TestCase):
    setUp=test_auth.AuthTests.setUp
    tearDown=test_auth.AuthTests.tearDown
    req=test_auth.AuthTests.req
    login=test_auth.AuthTests.login
    def config(self):
        salt=b'0123456789abcdef'
        return patch.dict(os.environ,{'MYTREE_ADMIN_USER':'test-admin','MYTREE_ADMIN_SALT':salt.hex(),'MYTREE_ADMIN_HASH':hashlib.scrypt(b'test-password',salt=salt,n=16384,r=8,p=1).hex()})
    def admin(self):
        status,body,headers=self.req('/api/admin/login',{'username':'test-admin','password':'test-password'})
        self.assertEqual(status,200,body)
        return headers['Set-Cookie'].split(';')[0]
    def test_student_and_admin_cannot_impersonate_each_other(self):
        _,student=self.login()
        self.assertEqual(self.req('/api/admin/overview')[0],401)
        self.assertEqual(self.req('/api/admin/overview',cookie=student)[0],403)
        self.assertEqual(self.req('/api/admin/overview',cookie=student,extra={'X-Role':'admin'})[0],403)
        with self.config():
            admin=self.admin()
            self.assertEqual(self.req('/api/admin/overview',cookie=admin)[0],200)
            self.assertEqual(self.req('/api/profile',cookie=admin)[0],401)
    def test_parent_has_separate_empty_state_and_no_unbound_child_data(self):
        _,cookie=self.login()
        self.assertEqual(self.req('/parent',cookie=cookie)[0],200)
        self.assertIn('parent-gate',self.req('/parent',cookie=cookie)[1])
        self.assertNotIn('family-accept',self.req('/parent',cookie=cookie)[1])
        self.assertEqual(self.req('/api/parent/overview?student=other',cookie=cookie)[0],403)
        index=self.req('/',cookie=cookie)[1];self.assertNotIn('data-nav="/parent"',index)
    def test_admin_logout_and_expiry(self):
        with self.config():
            cookie=self.admin();self.assertEqual(self.req('/admin',cookie=cookie)[0],200)
            self.assertEqual(self.req('/api/admin/logout',{},cookie=cookie)[0],200)
            self.assertEqual(self.req('/api/admin/overview',cookie=cookie)[0],401)
            cookie=self.admin()
            with patch('app.auth.time.time',return_value=time.time()+auth.ADMIN_TTL+1):self.assertEqual(self.req('/api/admin/overview',cookie=cookie)[0],401)
    def test_wrong_missing_credentials_and_rate_limit(self):
        with self.config():
            for _ in range(10):self.assertEqual(self.req('/api/admin/login',{'username':'test-admin','password':'wrong'})[0],401)
            self.assertEqual(self.req('/api/admin/login',{'username':'test-admin','password':'test-password'})[0],429)
        with patch.dict(os.environ,{'MYTREE_ADMIN_USER':'','MYTREE_ADMIN_HASH':'','MYTREE_ADMIN_SALT':''}):
            with self.assertRaises(auth.AuthError):auth.admin_login('admin','test','different-ip')
    def test_cross_origin_admin_login_and_logout_denied(self):
        with self.config():
            self.assertEqual(self.req('/api/admin/login',{'username':'test-admin','password':'test-password'},origin='https://other.test')[0],403)
            cookie=self.admin();self.assertEqual(self.req('/api/admin/logout',{},cookie=cookie,origin='null')[0],403)
    def test_overview_has_real_counts_but_no_credentials(self):
        self.login();self.login('other@example.test')
        with self.config():
            cookie=self.admin();status,data,_=self.req('/api/admin/overview',cookie=cookie)
            self.assertEqual(status,200);self.assertEqual(data['account_count'],2);self.assertTrue(data['email_ready'])
            raw=json.dumps(data);self.assertNotIn('test-password',raw);self.assertNotIn('first@example.test',raw);self.assertNotIn('session',raw)
        with patch('app.auth.mail_ready',return_value=False):self.assertFalse(auth.admin_overview()['email_ready'])

if __name__=='__main__':unittest.main(verbosity=2)
