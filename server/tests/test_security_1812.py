import hashlib,os,sqlite3,tempfile,time,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,manage
from test_admin_session import AdminSessionTests

class SecurityHttpTests(AdminSessionTests):
 def device(self,number):
  return {'deviceId':f'{number:08x}-1111-4111-8111-111111111111','deviceSecret':f'{number:064x}','osUsername':'测试用户','computer':'TEST-PC'}
 def test_session_hash_expiry_logout_and_password_six(self):
  server.register('six','六位密码','123456')
  with self.assertRaises(ValueError):server.register('five','五位密码','12345')
  body,_=self.request('/api/login',{'username':'six','password':'123456'});token=body['token']
  with server.connect() as c:
   stored=c.execute('SELECT token FROM sessions WHERE user=(SELECT id FROM users WHERE username=?)',('six',)).fetchone()[0]
   self.assertEqual(stored,hashlib.sha256(token.encode()).hexdigest());self.assertNotEqual(stored,token)
  self.request('/api/me',headers={'Authorization':'Bearer '+token})
  self.request('/api/password',{'currentPassword':'123456','newPassword':'12345'},headers={'Authorization':'Bearer '+token},status=400)
  self.request('/api/password',{'currentPassword':'123456','newPassword':'abcdef'},headers={'Authorization':'Bearer '+token})
  self.request('/api/me',headers={'Authorization':'Bearer '+token},status=401)
  self.request('/api/login',{'username':'six','password':'abcdef'})
  self.login();cookie=self.jar._cookies['127.0.0.1']['/api']['cleaner_admin'].value
  with server.connect() as c:self.assertEqual(c.execute('SELECT token FROM sessions WHERE token=?',(hashlib.sha256(cookie.encode()).hexdigest(),)).fetchone()[0],hashlib.sha256(cookie.encode()).hexdigest())
  self.request('/api/admin/logout',{});self.request('/api/admin/session',status=401)
 def test_admin_reset_accepts_six_characters(self):
  self.login()
  with tempfile.TemporaryDirectory() as tmp:
   password=Path(tmp)/'password';password.write_text('abcdef\n',encoding='utf-8')
   manage.reset_admin(password)
  self.request('/api/admin/session',status=401)
  self.request('/api/login',{'username':'admin','password':'abcdef'})
 def test_device_disable_restore_revoke_and_unlimited_enrollment(self):
  first,_=self.request('/api/device/login',self.device(1));token=first['token'];self.login()
  disabled,_=self.request('/api/admin/device-state',{'deviceId':self.device(1)['deviceId'],'action':'disable'});self.assertEqual(disabled['state'],'disabled')
  self.request('/api/events',{'id':'disabled','fields':1,'files':1,'failed':0},headers={'Authorization':'Bearer '+token},status=401)
  self.request('/api/device/login',self.device(1),status=401)
  rows,_=self.request('/api/admin/devices');self.assertEqual(rows[0]['state'],'disabled');self.assertFalse(rows[0]['online'])
  self.request('/api/admin/device-state',{'deviceId':self.device(1)['deviceId'],'action':'restore'})
  second,_=self.request('/api/device/login',self.device(1));self.assertEqual(second['username'],first['username'])
  self.request('/api/admin/device-state',{'deviceId':self.device(1)['deviceId'],'action':'revoke'})
  self.request('/api/admin/device-state',{'deviceId':self.device(1)['deviceId'],'action':'restore'},status=409)
  self.request('/api/device/login',self.device(1),status=401)
  with server.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM devices').fetchone()[0],1)
  server.LIMITS.clear()
  for i in range(2,112):self.request('/api/device/login',self.device(i))
  self.assertFalse(server.LIMITS)
  with server.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM devices').fetchone()[0],111)
   self.assertEqual(c.execute('SELECT count(*) FROM device_enrollments').fetchone()[0],0)

class MigrationTests(unittest.TestCase):
 def test_legacy_tokens_backed_up_migrated_and_rollback_preserves_accounts_sessions(self):
  with tempfile.TemporaryDirectory() as tmp:
   old_db=server.DB;old_env=dict(os.environ)
   try:
    server.DB=str(Path(tmp)/'app.sqlite3');os.environ['ADMIN_PASSWORD']='123456';os.environ['BACKUP_DIR']=str(Path(tmp)/'backups');server.init()
    with server.connect() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',('legacy-token',(c.execute('SELECT id FROM users WHERE username=?',('admin',)).fetchone()[0]),int(time.time())+3600))
    server.init()
    backup=next((Path(tmp)/'backups').glob('before-1812-migration-*.sqlite3'))
    self.assertEqual(backup.stat().st_mode&0o777,0o600)
    with server.connect() as c:
     self.assertEqual(c.execute('SELECT count(*) FROM users WHERE username=?',('admin',)).fetchone()[0],1)
     self.assertEqual(c.execute('SELECT token FROM sessions').fetchone()[0],hashlib.sha256(b'legacy-token').hexdigest())
    with sqlite3.connect(backup) as c:self.assertEqual(c.execute('SELECT token FROM sessions').fetchone()[0],'legacy-token')
    manage.restore_database(backup,True,preserve_sessions=True)
    with server.connect() as c:
     self.assertEqual(c.execute('SELECT token FROM sessions').fetchone()[0],'legacy-token')
     self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)
    server.init()
    with server.connect() as c:self.assertEqual(c.execute('SELECT token FROM sessions').fetchone()[0],hashlib.sha256(b'legacy-token').hexdigest())
   finally:server.DB=old_db;os.environ.clear();os.environ.update(old_env)
