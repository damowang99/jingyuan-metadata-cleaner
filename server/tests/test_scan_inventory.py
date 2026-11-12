from test_admin_session import AdminSessionTests
import server
class ScanInventoryTests(AdminSessionTests):
 def device(self,key='a'):
  return {'Authorization':'Bearer '+self.request('/api/device/login',{'deviceId':key*8+'-1111-4111-8111-'+'1'*12,'deviceSecret':key*64,'osUsername':'测试用户','computer':'TEST-PC'})[0]['token']}
 def event(self,h,id):self.request('/api/events',{'id':id,'files':0,'fields':0,'failed':0,'scanned':3},headers=h)
 def test_unique_across_batches_and_retries_not_counts(self):
  h=self.device();self.event(h,'first');self.event(h,'second');self.login();self.assertIsNone(self.request('/api/stats')[0][0]['uniqueScanned'])
  for event,files in [('first',['a'*64,'b'*64]),('first',['a'*64,'b'*64]),('second',['b'*64,'c'*64])]:self.request('/api/scanned-files',{'event':event,'files':files,'final':True},headers=h)
  row=self.request('/api/stats')[0][0];self.assertEqual(row['uniqueScanned'],3);self.assertEqual(row['files'],0)
  self.request('/api/scanned-files',{'event':'second','files':['/private/path'],'final':True},headers=h,status=400)
  other=self.device('b');self.assertFalse(self.request('/api/scanned-files',{'event':'first','files':['d'*64],'final':True},headers=other)[0]['accepted'])
  self.event(other,'other-device');self.request('/api/scanned-files',{'event':'other-device','files':['a'*64],'final':True},headers=other)
  rows=self.request('/api/stats')[0];self.assertEqual(sorted(r['uniqueScanned'] for r in rows),[1,3])
 def test_day_follows_event_not_upload_and_empty_scan_is_zero(self):
  h=self.device();self.event(h,'older')
  with server.connect() as c:c.execute("UPDATE events SET created='2026-01-01T12:00:00+08:00' WHERE id='older'")
  self.request('/api/scanned-files',{'event':'older','files':['a'*64],'final':True},headers=h)
  self.event(h,'today');self.request('/api/scanned-files',{'event':'today','files':[],'final':True},headers=h);self.login();rows=self.request('/api/stats')[0];self.assertEqual(rows[0]['uniqueScanned'],0);self.assertEqual(rows[1]['day'],'2026-01-01');self.assertEqual(rows[1]['uniqueScanned'],1)
