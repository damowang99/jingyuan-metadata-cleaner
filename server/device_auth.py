"""Device enrollment with a per-installation secret; OS names are display labels only."""
import hashlib,hmac,re,secrets,time
import fleet

def login(connect,data,peer_ip=''):
 device_id=data.get('deviceId','');secret=data.get('deviceSecret','');name=data.get('osUsername','');computer=data.get('computer','')
 if not isinstance(device_id,str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',device_id):raise ValueError('Invalid device identity')
 if not isinstance(secret,str) or not re.fullmatch(r'[a-f0-9]{64}',secret):raise ValueError('Invalid device credential')
 if not isinstance(name,str) or not name.strip() or len(name)>80 or not isinstance(computer,str) or not computer.strip() or len(computer)>120:raise ValueError('Invalid device label')
 digest=hashlib.sha256(secret.encode()).hexdigest()
 with connect() as c:
  device=c.execute('SELECT * FROM devices WHERE id=?',(device_id,)).fetchone()
  if device and not hmac.compare_digest(device['secret'],digest):return None
  if device:
   control=c.execute('SELECT state FROM device_controls WHERE device_id=?',(device_id,)).fetchone()
   if control and control['state']!='active':return None
   user=device['user'];old=c.execute('SELECT name FROM users WHERE id=?',(user,)).fetchone()[0]
   if old!=name:c.execute('INSERT INTO name_changes(user,old_name,new_name,created) VALUES(?,?,?,?)',(user,old,name,fleet.now()))
   c.execute('UPDATE users SET name=? WHERE id=?',(name,user));c.execute('UPDATE devices SET computer=? WHERE id=?',(computer,device_id))
  else:
   # Enrollment creates ordinary desktop users and never changes an existing admin.
   username='device-'+device_id;salt=secrets.token_hex(16)
   cur=c.execute('INSERT INTO users(username,name,salt,password,admin) VALUES(?,?,?,?,0)',(username,name,salt,secrets.token_hex(32)))
   user=cur.lastrowid;c.execute('INSERT INTO devices(id,user,secret,computer) VALUES(?,?,?,?)',(device_id,user,digest,computer))
  # Retain recent tokens so an in-flight desktop request can finish after renewal.
  c.execute('DELETE FROM sessions WHERE user=? AND expires<?',(user,time.time()))
  token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,int(time.time())+30*86400))
 return {'token':token,'name':name,'username':'device-'+device_id,'computer':computer,'admin':False}
