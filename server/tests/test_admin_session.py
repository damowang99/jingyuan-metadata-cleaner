import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class QuietHandler(server.Handler):
    def log_message(self,*_):pass

class AdminSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.previous_db=server.DB;self.environment=dict(os.environ)
        server.DB=str(Path(self.temp.name)/'test.sqlite3')
        os.environ.pop('ADMIN_PASSWORD_FILE',None);os.environ.pop('COOKIE_SECURE',None)
        os.environ['ADMIN_PASSWORD']='admin-test-password';server.LIMITS.clear();server.init()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.http.server_port)
        self.jar=http.cookiejar.CookieJar();self.browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();server.DB=self.previous_db
        os.environ.clear();os.environ.update(self.environment);self.temp.cleanup()
    def request(self,route,data=None,headers=None,opener=None,status=200):
        req=urllib.request.Request(self.base+route,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        try:r=(opener or self.browser).open(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        with r:
            self.assertEqual(r.status,status)
            return json.load(r),r.headers
    def login(self):return self.request('/api/admin/login',{'username':'admin','password':'admin-test-password'})
    def test_refresh_restore_cookie_and_logout_revokes_session(self):
        body,headers=self.login();self.assertNotIn('token',body)
        cookie=headers['Set-Cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertIn('Max-Age=2592000',cookie);self.assertIn('Path=/api',cookie)
        self.assertFalse(list(self.jar)[0].discard)
        # A new page/opener sharing the browser cookie jar can restore without a password.
        new_page=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.assertTrue(self.request('/api/admin/session',opener=new_page)[0]['admin'])
        self.assertEqual(self.request('/api/stats',opener=new_page)[0],[])
        self.request('/api/admin/logout',{})
        self.assertEqual(len(self.jar),0)
        self.request('/api/admin/session',status=401)
        with server.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
    def test_expired_cookie_and_cross_origin_requests(self):
        self.login()
        self.request('/api/admin/logout',{},headers={'Origin':'http://other.example'},status=403)
        self.assertTrue(self.request('/api/admin/session')[0]['admin'])
        self.request('/api/admin/login',{'username':'admin','password':'admin-test-password'},headers={'Origin':'http://other.example'},status=403)
        with server.connect() as c:c.execute('UPDATE sessions SET expires=0')
        self.request('/api/admin/session',status=401);self.assertEqual(len(self.jar),0)
    def test_bearer_logout_revokes_only_selected_session(self):
        first,_=self.request('/api/login',{'username':'admin','password':'admin-test-password'})
        second,_=self.request('/api/login',{'username':'admin','password':'admin-test-password'})
        self.request('/api/admin/logout',{},headers={'Authorization':'Bearer '+first['token']})
        self.request('/api/me',headers={'Authorization':'Bearer '+first['token']},status=401)
        self.request('/api/me',headers={'Authorization':'Bearer '+second['token']})
        with server.connect() as c:
            rows=[row[0] for row in c.execute('SELECT token FROM sessions')]
        self.assertNotIn(first['token'],rows)
        self.assertEqual(len(rows),1)
    def test_desktop_bearer_still_works_and_secure_cookie_option(self):
        body,_=self.request('/api/login',{'username':'admin','password':'admin-test-password'})
        self.assertIn('token',body)
        self.assertEqual(self.request('/api/stats',headers={'Authorization':'Bearer '+body['token']})[0],[])
        self.login();self.request('/api/admin/logout',{})
        self.request('/api/me',headers={'Authorization':'Bearer '+body['token']})
        os.environ['COOKIE_SECURE']='1'
        self.assertIn('Secure',self.login()[1]['Set-Cookie'])
        server.register('worker','Worker','worker-test-password')
        self.request('/api/admin/login',{'username':'worker','password':'worker-test-password'},status=403)

if __name__=='__main__':unittest.main()

class AccountTests(AdminSessionTests):
    def test_change_own_password_without_admin_creation(self):
        self.login()
        self.request('/api/admin/create',{'username':'second'},status=404)
        self.request('/api/password',{'currentPassword':'bad','newPassword':'replacement-password'},status=400)
        self.request('/api/password',{'currentPassword':'admin-test-password','newPassword':'replacement-password'})
        self.request('/api/admin/session',status=401)
        self.request('/api/admin/login',{'username':'admin','password':'admin-test-password'},status=401)
        self.request('/api/admin/login',{'username':'admin','password':'replacement-password'})
