import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
import json
import uuid
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class ServerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=server.DB
        self.old_id=server.INSTANCE_ID
        self.env=dict(os.environ)
        os.environ.pop('ADMIN_PASSWORD_FILE',None)
        os.environ.pop('ADMIN_PASSWORD',None)
        os.environ.pop('REQUIRE_ADMIN_PASSWORD',None)
        server.DB=str(Path(self.tmp.name)/'persist.sqlite3')
    def tearDown(self):
        server.DB=self.db
        server.INSTANCE_ID=self.old_id
        os.environ.clear();os.environ.update(self.env)
        self.tmp.cleanup()
    def test_restart_and_sqlite_backup_preserve_instance_and_existing_records(self):
        server.init();identity=server.INSTANCE_ID
        self.assertEqual(str(uuid.UUID(identity)),identity)
        server.register('worker','Worker','worker-test-password')
        server.init()
        self.assertEqual(server.INSTANCE_ID,identity)
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)
            backup=sqlite3.connect(str(Path(self.tmp.name)/'backup.sqlite3'))
            c.backup(backup);backup.close()
        server.DB=str(Path(self.tmp.name)/'backup.sqlite3');server.init()
        self.assertEqual(server.INSTANCE_ID,identity)
        server.DB=str(Path(self.tmp.name)/'other.sqlite3');server.init()
        self.assertNotEqual(server.INSTANCE_ID,identity)
    def test_both_host_aliases_return_same_id_version_and_business_headers(self):
        server.init()
        class Quiet(server.Handler):
            def log_message(self,*_):pass
        http=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        try:
            base='http://127.0.0.1:'+str(http.server_port)
            for host in ['192.168.10.10:8787','203.0.113.10:8787']:
                req=urllib.request.Request(base+'/api/health',headers={'Host':host})
                with urllib.request.urlopen(req) as r:
                    b=json.load(r)
                    self.assertEqual(b['server_instance_id'],server.INSTANCE_ID)
                    self.assertEqual(r.headers['X-Server-Instance-ID'],server.INSTANCE_ID)
                    self.assertEqual(b['api_version'],1)
                    self.assertEqual(b['server_version'],'1.8.17')
                    self.assertEqual(b['database'],'ok')
            try:urllib.request.urlopen(base+'/api/stats')
            except urllib.error.HTTPError as e:
                self.assertEqual(e.headers['X-Server-Instance-ID'],server.INSTANCE_ID)
                self.assertIn(e.status,[401,403]);e.close()
        finally:http.shutdown();http.server_close();worker.join()
