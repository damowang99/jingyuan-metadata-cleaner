import os, sqlite3, json, secrets, hashlib, hmac, time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
import release_api
import device_auth
import fleet
import file_records
import scan_inventory
import threading
import uuid
import ssl
from http.cookies import SimpleCookie, CookieError
from contextlib import contextmanager
LIMITS={};LIMIT_LOCK=threading.Lock()
API_VERSION=1
SERVER_VERSION='1.8.17'
INSTANCE_ID=''
DB=os.environ.get('DATABASE','cleaner.sqlite3')
WEB=Path(__file__).parent/'web'
def token_hash(token):return hashlib.sha256(token.encode('utf-8')).hexdigest()
def backup_before_migration():
 path=Path(DB)
 if not path.is_file():return None
 with sqlite3.connect(DB) as c:
  tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if 'devices' not in tables:return None
  legacy='sessions' in tables and any(not (len(r[0])==64 and all(x in '0123456789abcdef' for x in r[0])) for r in c.execute('SELECT token FROM sessions'))
  needed=legacy or 'device_controls' not in tables or 'device_enrollments' not in tables
 if not needed:return None
 from manage import backup_database,backup_path
 return backup_database(DB,backup_path('before-1812-migration'))
@contextmanager
def connect():
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row
 try:
  with c:yield c
 finally:c.close()
def init():
 global INSTANCE_ID
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 backup_before_migration()
 with connect() as c:
  c.execute('PRAGMA journal_mode=WAL')
  c.executescript('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,name TEXT,salt TEXT,password TEXT,admin INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user INTEGER,expires INTEGER); CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,user INTEGER,created TEXT,fields INTEGER,files INTEGER,failed INTEGER); CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,user INTEGER UNIQUE,secret TEXT NOT NULL,computer TEXT NOT NULL);')
  c.executescript("CREATE TABLE IF NOT EXISTS device_controls(device_id TEXT PRIMARY KEY,state TEXT NOT NULL CHECK(state IN ('active','disabled','revoked')),changed TEXT NOT NULL,admin INTEGER); CREATE TABLE IF NOT EXISTS device_enrollments(device_id TEXT PRIMARY KEY,peer_ip TEXT NOT NULL,created REAL NOT NULL); CREATE INDEX IF NOT EXISTS idx_device_enrollments_ip_created ON device_enrollments(peer_ip,created);")
  for (token,) in c.execute('SELECT token FROM sessions').fetchall():
   if len(token)!=64 or any(x not in '0123456789abcdef' for x in token):c.execute('UPDATE sessions SET token=? WHERE token=?',(token_hash(token),token))
  c.execute('DELETE FROM sessions WHERE expires<=?',(time.time(),))
  fleet.init(c)
  file_records.init(c)
  scan_inventory.init(c)
  c.execute('CREATE TABLE IF NOT EXISTS server_info(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  c.execute('INSERT OR IGNORE INTO server_info VALUES(?,?)',('server_instance_id',str(uuid.uuid4())))
  INSTANCE_ID=c.execute('SELECT value FROM server_info WHERE key=?',('server_instance_id',)).fetchone()[0]
 password=os.environ.get('ADMIN_PASSWORD','')
 if os.environ.get('ADMIN_PASSWORD_FILE'):
  password=Path(os.environ['ADMIN_PASSWORD_FILE']).read_text(encoding='utf-8').rstrip('\r\n')
 if password:register('admin','管理员',password,1)
 elif os.environ.get('REQUIRE_ADMIN_PASSWORD')=='1':
  with connect() as c:
   if not c.execute('SELECT 1 FROM users WHERE admin=1').fetchone():raise RuntimeError('首次启动必须提供管理员密码文件')
def register(username,name,password,admin=0):
 if not isinstance(username,str) or not username.strip() or len(username)>80 or not isinstance(name,str) or not name.strip() or len(name)>80 or not isinstance(password,str) or len(password)<6 or len(password)>256: raise ValueError('账号、姓名必填；密码需要6至256位')
 salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
 with connect() as c:
  if admin:
   existing=c.execute('SELECT admin FROM users WHERE username=?',(username,)).fetchone()
   if existing:
    if not existing['admin']:raise RuntimeError('admin账号已存在但不是管理员，请先处理账号冲突')
    return
  c.execute('INSERT INTO users(username,name,salt,password,admin) VALUES(?,?,?,?,?)',(username,name,salt,digest,admin))
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kw):super().__init__(*args,directory=str(WEB),**kw)
 def setup(self):
  self.request.settimeout(20)
  super().setup()
 def reply(self,status,data,cookie=None):
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
  if cookie is not None:self.send_header('Set-Cookie',cookie)
  self.end_headers();self.wfile.write(body)
 def cookie_token(self):
  try:
   cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
   return cookie['cleaner_admin'].value if 'cleaner_admin' in cookie else ''
  except CookieError:return ''
 def session_cookie(self,token='',clear=False,persistent=True):
  cookie=SimpleCookie();cookie['cleaner_admin']=token
  item=cookie['cleaner_admin'];item['httponly']=True;item['samesite']='Strict';item['path']='/api';item['max-age']=0 if clear else 30*86400
  if not persistent and not clear:del item['max-age']
  if os.environ.get('COOKIE_SECURE')=='1' or isinstance(self.connection,ssl.SSLSocket):item['secure']=True
  return item.OutputString()
 def same_origin(self):
  origin=self.headers.get('Origin')
  if origin:
   parsed=urlparse(origin)
   return parsed.scheme in ['http','https'] and parsed.netloc==self.headers.get('Host')
  return self.headers.get('Sec-Fetch-Site')!='cross-site'
 def user(self):
  token=self.headers.get('Authorization','').removeprefix('Bearer ') or self.cookie_token()
  if not token:return None
  with connect() as c:return c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user LEFT JOIN devices d ON d.user=u.id LEFT JOIN device_controls dc ON dc.device_id=d.id WHERE s.token=? AND s.expires>? AND (d.id IS NULL OR COALESCE(dc.state,'active')='active')",(token_hash(token),time.time())).fetchone()
 def end_headers(self):
  if INSTANCE_ID:self.send_header('X-Server-Instance-ID',INSTANCE_ID)
  route=urlparse(getattr(self,'path','')).path
  if not route.startswith(('/api/','/downloads/')):
   if route.endswith(('.css','.js')):self.send_header('Cache-Control','no-cache')
   elif route.endswith(('.html','/')):self.send_header('Cache-Control','no-store')
  super().end_headers()
 def do_GET(self):
  if release_api.serve(self,urlparse(self.path).path):return
  if urlparse(self.path).path=='/api/health':
   try:
    with connect() as c:c.execute('SELECT id FROM users LIMIT 1').fetchone()
    return self.reply(200,{'service':'metadata-cleaner','status':'ok','database':'ok','api_version':API_VERSION,'server_version':SERVER_VERSION,'server_instance_id':INSTANCE_ID})
   except sqlite3.Error:return self.reply(503,{'service':'metadata-cleaner','status':'unavailable'})
  if urlparse(self.path).path=='/api/admin/session':
   u=self.user()
   if not u or not u['admin']:return self.reply(401,{'error':'Admin login required'},cookie=self.session_cookie(clear=True))
   return self.reply(200,{'name':u['name'],'username':u['username'],'admin':True})
  if urlparse(self.path).path=='/api/me':
   u=self.user()
   if not u:return self.reply(401,{'error':'登录已过期'})
   return self.reply(200,{'name':u['name'],'username':u['username']})
  if urlparse(self.path).path in ['/api/policy','/api/admin/devices','/api/admin/reports','/api/admin/name-changes']:
   u=self.user()
   if not u:return self.reply(401,{'error':'需要登录'})
   try:
    with connect() as c:return self.reply(200,fleet.get(c,urlparse(self.path).path,u))
   except PermissionError:return self.reply(403,{'error':'需要管理员权限'})
  if urlparse(self.path).path in ['/api/admin/file-records','/api/admin/file-preview']:
   u=self.user()
   if not u or not u['admin']:return self.reply(403,{'error':'需要管理员登录'})
   try:
    q=parse_qs(urlparse(self.path).query);user=int(q.get('user',[''])[0])
    with connect() as c:
     if urlparse(self.path).path=='/api/admin/file-records':
      offset=max(0,int(q.get('offset',['0'])[0]));return self.reply(200,file_records.listing(c,user,q.get('day',[''])[0],offset))
     event=q.get('event',[''])[0];ordinal=int(q.get('ordinal',[''])[0])
     row=c.execute('SELECT preview FROM file_records WHERE user=? AND event=? AND ordinal=?',(user,event,ordinal)).fetchone()
     if not row or row['preview'] is None:return self.reply(404,{'error':'没有可用预览'})
     self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(row['preview'])));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(row['preview']);return
   except (ValueError,TypeError):return self.reply(400,{'error':'文件明细查询参数无效'})
  if urlparse(self.path).path=='/api/stats':
   u=self.user()
   if not u or not u['admin']:return self.reply(403,{'error':'需要管理员登录'})
   with connect() as c:
    rows=c.execute("SELECT u.id userId,CASE WHEN d.id IS NOT NULL THEN d.computer || ' · ' || substr(d.id,1,8) ELSE u.username END username,u.name,n.peer_ip,n.interfaces,n.updated networkUpdated,substr(e.created,1,10) day,sum(e.fields) fields,sum(e.files) files,sum(e.failed) failed,CASE WHEN EXISTS(SELECT 1 FROM scan_batches b WHERE b.user=u.id AND b.day=substr(e.created,1,10)) THEN (SELECT count(*) FROM scanned_files f WHERE f.user=u.id AND f.day=substr(e.created,1,10)) ELSE NULL END uniqueScanned FROM events e JOIN users u ON u.id=e.user LEFT JOIN devices d ON d.user=u.id LEFT JOIN device_network n ON n.user=u.id GROUP BY u.id,day ORDER BY day DESC,u.id").fetchall()
   return self.reply(200,[dict(r)|{'network':json.loads(r['interfaces'] or '[]')} for r in rows])
  if self.path.startswith('/api/'):return self.reply(404,{'error':'接口不存在'})
  super().do_GET()
 def do_POST(self):
  try:
   n=int(self.headers.get('Content-Length','0'))
   if n<0 or n>(1500000 if urlparse(self.path).path=='/api/file-records' else 65536):return self.reply(413,{'error':'请求过大'})
   d=json.loads(self.rfile.read(n));route=urlparse(self.path).path
   if not isinstance(d,dict):raise ValueError('无效请求')
   if (route.startswith('/api/admin/') or route=='/api/password') and not self.same_origin():return self.reply(403,{'error':'Cross-origin request rejected'})
   if route=='/api/admin/logout':
    with connect() as c:c.execute('DELETE FROM sessions WHERE token IN (?,?)',(token_hash(self.headers.get('Authorization','').removeprefix('Bearer ')),token_hash(self.cookie_token())))
    return self.reply(200,{'ok':True},cookie=self.session_cookie(clear=True))
   if route in ['/api/login','/api/admin/login','/api/register']:

    with LIMIT_LOCK:
     now=time.time();ip=self.client_address[0];attempts=[t for t in LIMITS.get(ip,[]) if now-t<60];LIMITS[ip]=attempts
     if len(attempts)>=20:return self.reply(429,{'error':'请求频繁，请稍后重试'})
     attempts.append(now)
   if route=='/api/device/login':
    result=device_auth.login(connect,d,self.client_address[0])
    return self.reply(200,result) if result else self.reply(401,{'error':'Device credential rejected'})
   if route=='/api/register':register(d.get('username'),d.get('name'),d.get('password'));return self.reply(201,{'ok':True})
   if route in ['/api/login','/api/admin/login']:
    with connect() as c:
     u=c.execute('SELECT * FROM users WHERE username=?',(d.get('username'),)).fetchone()
     if not u or not hmac.compare_digest(u['password'],hashlib.pbkdf2_hmac('sha256',str(d.get('password','')).encode(),u['salt'].encode(),600000).hex()):return self.reply(401,{'error':'账号或密码错误'})
     if route=='/api/admin/login' and not u['admin']:return self.reply(403,{'error':'Admin login required'})
     t=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(t),u['id'],int(time.time())+30*86400))
    if route=='/api/admin/login':return self.reply(200,{'name':u['name'],'admin':True},cookie=self.session_cookie(t,persistent=d.get('remember',True) is True))
    return self.reply(200,{'token':t,'name':u['name'],'admin':bool(u['admin'])})
   u=self.user()
   if not u:return self.reply(401,{'error':'请重新登录'})
   if route in ['/api/heartbeat','/api/events','/api/file-records']:
    with connect() as c:fleet.network(c,u,self.client_address[0],d.get('network') if route=='/api/heartbeat' else None)
   if route in ['/api/heartbeat','/api/admin/policy','/api/admin/device-state']:
    try:
     with connect() as c:return self.reply(200,fleet.post(c,route,u,d))
    except PermissionError:return self.reply(403,{'error':'需要管理员权限'})
    except RuntimeError as e:return self.reply(409,{'error':str(e)})
   if route=='/api/password':
    with connect() as c:
     current=c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone()
     if not hmac.compare_digest(current['password'],hashlib.pbkdf2_hmac('sha256',str(d.get('currentPassword','')).encode(),current['salt'].encode(),600000).hex()):return self.reply(400,{'error':'Current password is incorrect'})
     password=d.get('newPassword')
     if not isinstance(password,str) or not 6<=len(password)<=256:raise ValueError('Invalid password')
     salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
     c.execute('UPDATE users SET salt=?,password=? WHERE id=?',(salt,digest,u['id']))
     c.execute('DELETE FROM sessions WHERE user=?',(u['id'],))
    return self.reply(200,{'ok':True},cookie=self.session_cookie(clear=True))
   if route=='/api/scanned-files':
    with connect() as c:return self.reply(200,scan_inventory.upload(c,u,d))
   if route=='/api/file-records':
    with connect() as c:return self.reply(200,file_records.upload(c,u,d))
   if route=='/api/events':
    if not isinstance(d.get('id'),str) or len(d['id'])>100:raise ValueError('无效记录')
    for k in ['fields','files','failed']:
     if type(d.get(k)) is not int or not 0<=d[k]<=10000000:raise ValueError('无效计数')
    # Use server time in Asia/Shanghai, never trust client date or identity.
    import datetime
    date=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    with connect() as c:
     inserted=c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)',(d['id'],u['id'],date,d['fields'],d['files'],d['failed'])).rowcount==1
     stored=c.execute('SELECT * FROM events WHERE id=?',(d['id'],)).fetchone()
     if stored['user']!=u['id']:return self.reply(409,{'accepted':False,'error':'记录 ID 已被其他设备使用'})
     fleet.report(c,stored['user'],dict(d,fields=stored['fields'],files=stored['files'],failed=stored['failed']))
    return self.reply(200,{'ok':True,'accepted':True,'event_id':d['id'],'duplicate':not inserted})
   self.reply(404,{'error':'接口不存在'})
  except sqlite3.OperationalError:self.reply(503,{'error':'数据库暂时忙，请稍后重试'})
  except sqlite3.IntegrityError:self.reply(409,{'error':'账号已存在'})
  except (ValueError,TypeError,KeyError):self.reply(400,{'error':'策略无效：请选择有效规则，并填写受支持的文件扩展名' if locals().get('route')=='/api/admin/policy' else '请求内容无效，密码至少6位'})
if __name__=='__main__':
 init();ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8787'))),Handler).serve_forever()
