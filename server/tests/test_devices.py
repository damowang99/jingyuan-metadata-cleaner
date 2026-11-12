from test_admin_session import AdminSessionTests
import server
class DeviceTests(AdminSessionTests):
 def profile(self,id='11111111-1111-4111-8111-111111111111',secret='a'*64,computer='DESKTOP-ONE'):
  return {'deviceId':id,'deviceSecret':secret,'osUsername':'Administrator','computer':computer}
 def test_device_enrollment_renewal_and_spoof_rejection(self):
  a,_=self.request('/api/device/login',self.profile());self.assertFalse(a['admin']);self.assertIn('token',a)
  b,_=self.request('/api/device/login',self.profile());self.assertEqual(a['username'],b['username'])
  self.request('/api/device/login',self.profile(secret='b'*64),status=401)
  self.request('/api/stats',headers={'Authorization':'Bearer '+a['token']},status=403)
  self.request('/api/device/login',{'osUsername':'Administrator'},status=400)
  with server.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM devices').fetchone()[0],1)
   self.assertNotEqual(c.execute('SELECT secret FROM devices').fetchone()[0],'a'*64)
 def test_same_os_username_keeps_devices_separate_and_legacy_stats_intact(self):
  a,_=self.request('/api/device/login',self.profile());b,_=self.request('/api/device/login',self.profile(id='22222222-2222-4222-8222-222222222222',secret='b'*64,computer='DESKTOP-TWO'))
  self.assertNotEqual(a['username'],b['username'])
  for token,id in [(a['token'],'one'),(b['token'],'two')]:self.request('/api/events',{'id':id,'fields':2,'files':1,'failed':0},headers={'Authorization':'Bearer '+token})
  self.login();rows,_=self.request('/api/stats');self.assertEqual(len(rows),2);self.assertEqual({r['name'] for r in rows},{'Administrator'});self.assertEqual(len({r['username'] for r in rows}),2)
  self.assertTrue(any('DESKTOP-ONE' in r['username'] for r in rows))
  renamed=self.profile();renamed['osUsername']='设计组张三';self.request('/api/device/login',renamed)
  updated,_=self.request('/api/stats');self.assertEqual({r['name'] for r in updated},{'设计组张三','Administrator'})
  with server.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM devices').fetchone()[0],2)
  with server.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],2)
