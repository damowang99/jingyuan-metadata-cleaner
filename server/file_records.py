"""Per-file metadata and optional previews. All reads require administrator authentication."""
import base64,datetime,json,re,sqlite3

def init(c):
 c.executescript('CREATE TABLE IF NOT EXISTS file_records(user INTEGER NOT NULL,event TEXT NOT NULL,ordinal INTEGER NOT NULL,name TEXT NOT NULL,time TEXT NOT NULL,detected TEXT NOT NULL,status TEXT NOT NULL,error TEXT NOT NULL,fields INTEGER NOT NULL,preview BLOB,PRIMARY KEY(user,event,ordinal)); CREATE INDEX IF NOT EXISTS file_records_event ON file_records(event);')

def text(value,limit):
 if not isinstance(value,str):raise ValueError('无效文件明细')
 return value[:limit]

def upload(c,u,d):
 event=d.get('event');items=d.get('items')
 if not isinstance(event,str) or not 1<=len(event)<=100 or not isinstance(items,list) or not 1<=len(items)<=10:raise ValueError('无效文件明细')
 stored=c.execute('SELECT * FROM events WHERE id=? AND user=?',(event,u['id'])).fetchone()
 if not stored:return {'accepted':False,'reason':'event-not-owned'}
 for item in items:
  if not isinstance(item,dict) or type(item.get('ordinal'))is not int or not 0<=item['ordinal']<=1000000:raise ValueError('无效文件明细')
  name=text(item.get('name',''),255)
  if not name or '/' in name or '\\' in name or any(ord(ch)<32 for ch in name):raise ValueError('只允许文件名')
  fields=item.get('fields',0)
  if type(fields)is not int or not 0<=fields<=10000000:raise ValueError('无效字段数量')
  detected=item.get('detected',[])
  if not isinstance(detected,list) or len(detected)>100:raise ValueError('无效检测结果')
  detected=[{'tag':text(x.get('tag',''),150),'value':text(x.get('value',''),1000)} for x in detected if isinstance(x,dict)]
  preview=None
  if item.get('preview'):
   raw=item['preview']
   if not isinstance(raw,str) or len(raw)>140000:raise ValueError('预览图过大')
   try:preview=base64.b64decode(raw,validate=True)
   except Exception:raise ValueError('无效预览图')
   if not 4<=len(preview)<=100000 or not preview.startswith(b'\xff\xd8\xff') or not preview.endswith(b'\xff\xd9'):raise ValueError('仅支持JPEG预览图')
  # Date grouping follows the original server event date, not the upload/retry date.
  stamp=item.get('time',stored['created'])
  try:
   stamp=datetime.datetime.fromisoformat(text(stamp,64).replace('Z','+00:00'))
   if stamp.tzinfo is None:raise ValueError()
   stamp=stamp.isoformat()
  except (ValueError,TypeError):stamp=stored['created']
  c.execute('INSERT INTO file_records VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user,event,ordinal) DO UPDATE SET preview=COALESCE(file_records.preview,excluded.preview)',(u['id'],event,item['ordinal'],name,stamp,json.dumps(detected,ensure_ascii=False),text(item.get('status',''),80),text(item.get('error',''),1000),fields,preview))
 return {'accepted':True}

def listing(c,user,day,offset):
 if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('日期无效')
 where='f.user=? AND substr(e.created,1,10)=?';args=(user,day)
 total=c.execute('SELECT count(*) FROM file_records f JOIN events e ON e.id=f.event AND e.user=f.user WHERE '+where,args).fetchone()[0]
 rows=c.execute('SELECT f.user,f.event,f.ordinal,f.name,f.time,f.detected,f.status,f.error,f.fields,f.preview IS NOT NULL AS hasPreview FROM file_records f JOIN events e ON e.id=f.event AND e.user=f.user WHERE '+where+' ORDER BY julianday(f.time) DESC,f.event DESC,f.ordinal DESC LIMIT 50 OFFSET ?',(*args,offset)).fetchall()
 return {'total':total,'offset':offset,'limit':50,'rows':[dict(r)|{'detected':json.loads(r['detected']),'hasPreview':bool(r['hasPreview'])} for r in rows]}
