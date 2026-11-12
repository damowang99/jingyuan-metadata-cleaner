from test_admin_session import AdminSessionTests
import server,time
class FleetTests(AdminSessionTests):
 def device(self):
  p={'deviceId':'33333333-3333-4333-8333-333333333333','deviceSecret':'c'*64,'osUsername':'测试用户','computer':'TEST-PC'}
  token=self.request('/api/device/login',p)[0]['token'];return p,{'Authorization':'Bearer '+token}
 def test_heartbeat_policy_permissions_offline_and_rename_audit(self):
  p,h=self.device();current,_=self.request('/api/heartbeat',{'version':'1.7.0','policy':1},headers=h);self.assertEqual(current['mode'],'default')
  self.assertIn('Adobe',current['keywords'])
  self.request('/api/admin/devices',headers=h,status=403);self.request('/api/admin/policy',dict(current,watch=False),headers=h,status=403)
  self.login();devices,_=self.request('/api/admin/devices');self.assertTrue(devices[0]['online'])
  changed,_=self.request('/api/admin/policy',dict(current,mode='inspect',watch=False,extensions=['.jpg'],keywords=['StudioX','摄影工具']));self.assertEqual(changed['revision'],2);self.assertEqual(changed['keywords'],['StudioX','摄影工具'])
  self.request('/api/admin/policy',dict(changed,keywords=['']),status=400)
  self.request('/api/admin/policy',dict(changed,keywords=['A','a']),status=400)
  self.request('/api/admin/policy',current,status=409)
  self.assertFalse(self.request('/api/policy',headers=h)[0]['watch'])
  p['osUsername']='新名称';self.request('/api/device/login',p);changes,_=self.request('/api/admin/name-changes');self.assertEqual(changes[0]['old_name'],'测试用户');self.assertEqual(changes[0]['new_name'],'新名称')
  with server.connect() as c:c.execute('UPDATE device_status SET last_seen=?',(time.time()-181,))
  self.assertFalse(self.request('/api/admin/devices')[0][0]['online'])
 def test_report_is_idempotent_and_does_not_store_paths(self):
  p,h=self.device();event={'id':'fleet-report','fields':2,'files':1,'failed':0,'scanned':3,'policyRevision':1,'reason':'手动扫描','file':'/private/file.jpg'}
  accepted,_=self.request('/api/events',event,headers=h);self.assertEqual(accepted,{'ok':True,'accepted':True,'event_id':'fleet-report','duplicate':False})
  duplicate,_=self.request('/api/events',dict(event,fields=999,files=999,scanned=999),headers=h);self.assertEqual(duplicate,{'ok':True,'accepted':True,'event_id':'fleet-report','duplicate':True})
  self.login();rows,_=self.request('/api/admin/reports');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['summary']['scanned'],3);self.assertNotIn('file',rows[0]['summary'])
  stats,_=self.request('/api/stats');self.assertEqual(stats[0]['fields'],2);self.assertEqual(stats[0]['files'],1)
  second=self.request('/api/device/login',{'deviceId':'44444444-4444-4444-8444-444444444444','deviceSecret':'d'*64,'osUsername':'第二人','computer':'PC-2'})[0]
  self.request('/api/events',event,headers={'Authorization':'Bearer '+second['token']},status=409)

 def test_network_authenticated_reporting_and_observed_peer(self):
  p,h=self.device();network=[{'name':'en0','ip':'10.0.0.10','mac':'aa:bb:cc:dd:ee:ff'}]
  self.request('/api/heartbeat',{'version':'1.8.3','network':network},headers=dict(h,**{'X-Forwarded-For':'203.0.113.99'}))
  self.request('/api/events',{'id':'network-event','fields':1,'files':1,'failed':0},headers=h)
  self.login();row=self.request('/api/stats')[0][0];self.assertEqual(row['peer_ip'],'127.0.0.1');self.assertEqual(row['network'],network)
  self.assertEqual(self.request('/api/admin/devices')[0][0]['network'],network)
  self.request('/api/heartbeat',{'version':'1.8.0'},headers=h);self.assertEqual(self.request('/api/stats')[0][0]['network'],network)
  for bad in [{'name':'eth0','ip':'bad','mac':''},{'name':'eth0','ip':'10.0.0.1','mac':'bad'}]:self.request('/api/heartbeat',{'version':'1.8.3','network':[bad]},headers=h,status=400)
  self.assertEqual(self.request('/api/stats')[0][0]['network'],network)
