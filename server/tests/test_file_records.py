from test_admin_session import AdminSessionTests
import server,base64
class FileRecordTests(AdminSessionTests):
 def device(self,key='a'):
  return {'Authorization':'Bearer '+self.request('/api/device/login',{'deviceId':key*8+'-1111-4111-8111-'+'1'*12,'deviceSecret':key*64,'osUsername':'测试用户','computer':'TEST-PC'})[0]['token']}
 def event(self,h,event='files-event'):
  self.request('/api/events',{'id':event,'fields':2,'files':1,'failed':0},headers=h)
 def item(self):return {'ordinal':0,'name':'sample.jpg','time':'2026-11-09T01:00:00Z','fields':2,'status':'已清除','detected':[{'tag':'XMP-xmp:CreatorTool','value':'Adobe Photoshop'}],'preview':base64.b64encode(b'\xff\xd8\xff\xe0test\xff\xd9').decode()}
 def test_owner_scope_admin_reads_idempotence_and_date(self):
  h=self.device();self.event(h);other=self.device('b');item=self.item()
  self.assertFalse(self.request('/api/file-records',{'event':'files-event','items':[item]},headers=other)[0]['accepted'])
  self.request('/api/file-records',{'event':'files-event','items':[item]},headers=h)
  self.request('/api/file-records',{'event':'files-event','items':[item]},headers=h)
  self.request('/api/admin/file-records?user=1&day=2026-11-09',headers=h,status=403)
  self.login();stats,_=self.request('/api/stats');user=stats[0]['userId'];day=stats[0]['day']
  response,_=self.request('/api/admin/file-records?user='+str(user)+'&day='+day)
  self.assertEqual(response['total'],1);row=response['rows'][0];self.assertTrue(row['hasPreview']);self.assertEqual(row['name'],'sample.jpg');self.assertNotIn('preview',row)
  import urllib.request
  url='/api/admin/file-preview?user='+str(user)+'&event=files-event&ordinal=0'
  with self.browser.open(self.base+url) as r:self.assertEqual(r.headers['Content-Type'],'image/jpeg');self.assertEqual(r.read(),base64.b64decode(item['preview']))
  self.request('/api/admin/file-records?user='+str(user)+'&day=invalid',status=400)
  self.jar.clear();self.request(url,status=403)
 def test_validation_and_history_independent_persistence(self):
  h=self.device();self.event(h)
  for replacement in [{'name':'/private/image.jpg'},{'name':'C:\\secret.jpg'},{'preview':'not-base64'},{'preview':base64.b64encode(b'<svg/>').decode()},{'fields':-1}]:
   self.request('/api/file-records',{'event':'files-event','items':[dict(self.item(),**replacement)]},headers=h,status=400)
  self.request('/api/file-records',{'event':'files-event','items':[self.item()]},headers=h)
  with server.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM file_records').fetchone()[0],1)
   self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],1)
   self.assertEqual(c.execute('SELECT sum(fields) FROM events').fetchone()[0],2)

 def test_frontend_cache_headers(self):
  for route,expected in [('/index.html','no-store'),('/style.css','no-cache'),('/file-records.js','no-cache'),('/api/health','no-store')]:
   with self.browser.open(self.base+route) as r:self.assertEqual(r.headers['Cache-Control'],expected)
