import sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]/"server"))
import importlib.util,tempfile,threading,json,urllib.request,urllib.error,os
from pathlib import Path
s=importlib.util.spec_from_file_location('backend',str(Path(__file__).resolve().parents[1]/'server'/'server.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
 m.DB=d+'/test.sqlite3';m.init();m.register('admin','管理员','test-password-strong',1)
 server=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
 def req(route,data=None,token=''):
  r=urllib.request.Request(base+route,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token});return json.load(urllib.request.urlopen(r))
 req('/api/register',{'username':'zhangsan','name':'张三','password':'test-password-strong'})
 t=req('/api/login',{'username':'zhangsan','password':'test-password-strong'})['token']
 e={'id':'same-event','fields':100,'files':10,'failed':1};req('/api/events',e,t);req('/api/events',e,t)
 try:req('/api/stats',token=t);raise AssertionError('regular user got admin access')
 except urllib.error.HTTPError as ex:assert ex.code==403
 a=req('/api/login',{'username':'admin','password':'test-password-strong'})['token'];rows=req('/api/stats',token=a);assert len(rows)==1 and rows[0]['fields']==100 and rows[0]['name']=='张三'
 server.shutdown();print('PASS: register/login, admin authorization, idempotent event upload, daily statistics')
