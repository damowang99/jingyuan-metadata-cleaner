"""Count distinct device-local path fingerprints per server event date."""
import re

def init(c):
 c.executescript('CREATE TABLE IF NOT EXISTS scanned_files(user INTEGER NOT NULL,day TEXT NOT NULL,identity TEXT NOT NULL,PRIMARY KEY(user,day,identity));CREATE TABLE IF NOT EXISTS scan_batches(event TEXT PRIMARY KEY,user INTEGER NOT NULL,day TEXT NOT NULL);CREATE INDEX IF NOT EXISTS scan_batches_day ON scan_batches(user,day);')
def upload(c,u,d):
 event=d.get('event');files=d.get('files');final=d.get('final',False)
 if not isinstance(event,str) or not 1<=len(event)<=100 or not isinstance(files,list) or len(files)>500 or type(final)is not bool or any(not isinstance(x,str) or not re.fullmatch(r'[a-f0-9]{64}',x) for x in files):raise ValueError('扫描明细无效')
 record=c.execute('SELECT created FROM events WHERE id=? AND user=?',(event,u['id'])).fetchone()
 if not record:return {'accepted':False}
 day=record['created'][:10]
 c.executemany('INSERT OR IGNORE INTO scanned_files VALUES(?,?,?)',[(u['id'],day,x) for x in files])
 if final:c.execute('INSERT OR IGNORE INTO scan_batches VALUES(?,?,?)',(event,u['id'],day))
 return {'accepted':True}
