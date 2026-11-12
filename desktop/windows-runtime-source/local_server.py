import os,sys,json,secrets
from pathlib import Path
if len(sys.argv)>1 and sys.argv[1]=='--apply-update':
 from update_helper import main
 main(sys.argv[2])
 raise SystemExit(0)
folder=Path(sys.argv[1]);folder.mkdir(parents=True,exist_ok=True)
os.environ['DATABASE']=str(folder/'local-cleaner.sqlite3')
credentials_file=folder/'local-admin.json'
if credentials_file.exists():
 credentials=json.loads(credentials_file.read_text(encoding='utf-8'))
else:
 if Path(os.environ['DATABASE']).exists():raise RuntimeError('本机后台管理员凭据文件缺失，请检查应用数据目录')
 credentials={'username':'admin','password':secrets.token_urlsafe(18)}
 credentials_file.write_text(json.dumps(credentials),encoding='utf-8')
os.environ['ADMIN_PASSWORD']=credentials['password']
import server
server.init()
server.ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('CLEANER_LOCAL_PORT','8787'))),server.Handler).serve_forever()
