import json,time,datetime,ipaddress,re
EXTENSIONS=['.gif','.jpg','.jpeg','.tif','.tiff','.png','.webp','.psd','.psb','.pdf','.ai','.eps','.xmp','.dng','.heic','.heif','.avif','.jp2','.jxl','.svg','.indd','.ps']
DEFAULT_KEYWORDS=['Adobe','Photoshop','Illustrator','Acrobat','InDesign','Lightroom','Premiere','After Effects','Audition','InCopy','Dreamweaver','Fireworks','FreeHand','GoLive','PageMaker','Distiller','Creative Cloud','Creative Suite','Camera Raw','ImageReady','Animate','Captivate','Substance','Bridge','XD']
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def init(c):
 c.execute("CREATE TABLE IF NOT EXISTS device_network(user INTEGER PRIMARY KEY,peer_ip TEXT NOT NULL,interfaces TEXT NOT NULL,updated TEXT NOT NULL)")
 c.executescript('CREATE TABLE IF NOT EXISTS device_status(user INTEGER PRIMARY KEY,last_seen REAL,version TEXT,policy INTEGER); CREATE TABLE IF NOT EXISTS name_changes(id INTEGER PRIMARY KEY,user INTEGER,old_name TEXT,new_name TEXT,created TEXT); CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,user INTEGER,created TEXT,body TEXT); CREATE TABLE IF NOT EXISTS policies(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT,updated TEXT,admin INTEGER);')
 c.execute('INSERT OR IGNORE INTO policies VALUES(1,1,?,?,NULL)',(json.dumps({'mode':'default','extensions':EXTENSIONS,'watch':True}),now()))
 for row in c.execute('SELECT e.* FROM events e LEFT JOIN reports r ON r.id=e.id WHERE r.id IS NULL').fetchall():
  body={k:row[k] for k in ['fields','files','failed']};body['reason']='历史统计（无扫描明细）';c.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?,?)',(row['id'],row['user'],row['created'],json.dumps(body)))
def policy(c):
 r=c.execute('SELECT * FROM policies WHERE id=1').fetchone();body=json.loads(r['body']);body.setdefault('keywords',DEFAULT_KEYWORDS);body.setdefault('sourceMode','all');return {**body,'revision':r['revision'],'updated':r['updated']}
def get(c,route,u):
 if route=='/api/policy':return policy(c)
 if not u['admin']:raise PermissionError()
 if route=='/api/admin/devices':return [dict(r)|{'network':json.loads(r['interfaces'] or '[]'),'online':bool(r['state']=='active' and r['last_seen'] and time.time()-r['last_seen']<=180)} for r in c.execute("SELECT d.id,u.name,d.computer,s.last_seen,s.version,s.policy,n.peer_ip,n.interfaces,n.updated AS networkUpdated,COALESCE(dc.state,'active') AS state FROM devices d JOIN users u ON u.id=d.user LEFT JOIN device_status s ON s.user=u.id LEFT JOIN device_network n ON n.user=u.id LEFT JOIN device_controls dc ON dc.device_id=d.id ORDER BY s.last_seen DESC")]
 if route=='/api/admin/name-changes':return [dict(r) for r in c.execute('SELECT n.id,u.name,d.computer,n.old_name,n.new_name,n.created FROM name_changes n JOIN users u ON u.id=n.user LEFT JOIN devices d ON d.user=n.user ORDER BY n.id DESC LIMIT 1000')]
 if route=='/api/admin/reports':return [dict(r)|{'summary':json.loads(r['body'])} for r in c.execute('SELECT r.*,u.name,d.computer FROM reports r JOIN users u ON u.id=r.user LEFT JOIN devices d ON d.user=r.user ORDER BY julianday(r.created) DESC LIMIT 1000')]
 raise ValueError('Unknown route')
def post(c,route,u,d):
 if route=='/api/admin/device-state':
  if not u['admin']:raise PermissionError()
  device_id=d.get('deviceId');action=d.get('action')
  if not isinstance(device_id,str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',device_id) or action not in ['disable','restore','revoke']:raise ValueError()
  device=c.execute('SELECT user FROM devices WHERE id=?',(device_id,)).fetchone()
  if not device:raise ValueError()
  row=c.execute('SELECT state FROM device_controls WHERE device_id=?',(device_id,)).fetchone();old=row['state'] if row else 'active'
  if old=='revoked' or action=='restore' and old!='disabled':raise RuntimeError('设备状态不允许此操作')
  state={'disable':'disabled','restore':'active','revoke':'revoked'}[action]
  c.execute('INSERT INTO device_controls VALUES(?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET state=excluded.state,changed=excluded.changed,admin=excluded.admin',(device_id,state,now(),u['id']))
  if state!='active':c.execute('DELETE FROM sessions WHERE user=?',(device['user'],))
  return {'ok':True,'state':state}
 if route=='/api/heartbeat':
  version=d.get('version','');revision=d.get('policy',0)
  if not isinstance(version,str) or len(version)>40 or type(revision)is not int:raise ValueError()
  c.execute('INSERT OR REPLACE INTO device_status VALUES(?,?,?,?)',(u['id'],time.time(),version,revision));return policy(c)
 if route=='/api/admin/policy':
  if not u['admin']:raise PermissionError()
  keywords=d.get('keywords');source_mode=d.get('sourceMode','all')
  valid_keywords=isinstance(keywords,list) and 1<=len(keywords)<=40 and all(isinstance(x,str) and x.strip() and len(x.strip())<=80 and not any(ord(c)<32 for c in x) for x in keywords)
  if source_mode not in ['all','keywords'] or source_mode=='keywords' and not valid_keywords or d.get('mode') not in ['default','adobe','inspect'] or type(d.get('watch'))is not bool or not isinstance(d.get('extensions'),list) or not d['extensions'] or any(x not in EXTENSIONS for x in d['extensions']):raise ValueError()
  if not isinstance(keywords,list):keywords=DEFAULT_KEYWORDS
  keywords=list(dict.fromkeys(x.strip() for x in keywords if isinstance(x,str) and x.strip()))
  if source_mode=='keywords' and (not keywords or len(keywords)!=len(set(x.casefold() for x in keywords))):raise ValueError()
  if d.get('revision')!=policy(c)['revision']:raise RuntimeError('策略已被其他管理员修改，请刷新后再保存')
  body={k:d[k] for k in ['mode','watch','extensions']};body['keywords']=keywords;body['sourceMode']=source_mode;c.execute('UPDATE policies SET revision=revision+1,body=?,updated=?,admin=? WHERE id=1',(json.dumps(body),now(),u['id']));return policy(c)
 raise ValueError()
def report(c,user,data):
 # Reports contain counts and task metadata only; paths and file contents stay on the device.
 body={k:data[k] for k in ['fields','files','failed']}
 for k in ['scanned','skipped','matched','durationMs','policyRevision']:
  v=data.get(k,0)
  if type(v)is int and 0<=v<=10**12:body[k]=v
 body['reason']=str(data.get('reason','客户端清理'))[:80]
 c.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?,?)',(data['id'],user,now(),json.dumps(body)))

def network(c,u,peer,payload=None):
 if u['admin']:return
 peer=str(ipaddress.ip_address(peer));interfaces=None
 if payload is not None:
  if not isinstance(payload,list) or len(payload)>16:raise ValueError('网卡信息无效')
  interfaces=[]
  for item in payload:
   if not isinstance(item,dict):raise ValueError('网卡信息无效')
   name=item.get('name','');ip=item.get('ip','');mac=item.get('mac','')
   if not isinstance(name,str) or len(name)>80 or not isinstance(ip,str) or len(ip)>64 or not isinstance(mac,str) or len(mac)>17:raise ValueError('网卡信息无效')
   address=ipaddress.ip_address(ip)
   if address.is_loopback or address.is_unspecified:continue
   mac=mac.lower()
   if mac and not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',mac):raise ValueError('MAC地址无效')
   interfaces.append({'name':name,'ip':str(address),'mac':'' if mac=='00:00:00:00:00:00' else mac})
  interfaces=json.dumps(interfaces,ensure_ascii=False)
 if interfaces is None:
  previous=c.execute('SELECT interfaces FROM device_network WHERE user=?',(u['id'],)).fetchone();interfaces=previous['interfaces'] if previous else '[]'
 c.execute('INSERT OR REPLACE INTO device_network VALUES(?,?,?,?)',(u['id'],peer,interfaces,now()))
