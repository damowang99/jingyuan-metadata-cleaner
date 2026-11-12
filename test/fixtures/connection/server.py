# Isolated test backend: two listening sockets, one SQLite database, no production settings.
import os,sys,json,threading,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[3]/'server'
sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('cleaner_fixture_backend',root/'server.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
os.environ.pop('ADMIN_PASSWORD_FILE',None)
os.environ['ADMIN_PASSWORD']='fixture-admin-password'
backend.DB=str(Path(sys.argv[1])/'test.sqlite3');backend.init()
class Quiet(backend.Handler):
 def log_message(self,*_):pass
servers={}
for entry in ['lan','wan']:
 http=backend.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
 threading.Thread(target=http.serve_forever,daemon=True).start();servers[entry]=http
print(json.dumps({entry:http.server_port for entry,http in servers.items()}),flush=True)
try:
 for command in sys.stdin:
  entry=command.strip()
  if entry in servers:
   http=servers.pop(entry);http.shutdown();http.server_close();print(json.dumps({'stopped':entry}),flush=True)
finally:
 for http in servers.values():http.shutdown();http.server_close()
