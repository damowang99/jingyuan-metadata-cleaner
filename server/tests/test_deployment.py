import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import manage


class QuietHandler(server.Handler):
    def log_message(self, *_):
        pass


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_database = server.DB
        self.environment = dict(os.environ)
        server.DB = str(self.root / 'data' / 'cleaner.sqlite3')
        self.password_file = self.root / 'password.txt'
        self.password_file.write_text('first-admin-password\n')
        os.environ['ADMIN_PASSWORD_FILE'] = str(self.password_file)
        os.environ['REQUIRE_ADMIN_PASSWORD'] = '1'
        os.environ['BACKUP_DIR'] = str(self.root / 'backups')
        server.LIMITS.clear()
        self.http = None

    def tearDown(self):
        self.stop()
        server.DB = self.old_database
        os.environ.clear()
        os.environ.update(self.environment)
        self.temp.cleanup()

    def start(self):
        server.init()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.http.server_port)

    def stop(self):
        if self.http:
            self.http.shutdown()
            self.http.server_close()
            self.thread.join()
            self.http = None

    def request(self, route, data=None, token='', expected=200):
        request = urllib.request.Request(self.url + route, data=json.dumps(data).encode() if data is not None else None,
                                        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, expected)
            return json.load(response)

    def login(self, username='admin', password='first-admin-password'):
        return self.request('/api/login', {'username': username, 'password': password})['token']

    def test_persistence_backup_restore_and_password_reset(self):
        self.start()
        self.assertEqual(self.request('/api/health')['database'], 'ok')
        self.request('/api/register', {'username': 'worker', 'name': '张三', 'password': 'worker-password'}, expected=201)
        token = self.login('worker', 'worker-password')
        self.request('/api/stats', token=token, expected=403)
        keeper = sqlite3.connect(server.DB)
        try:
            self.assertEqual(keeper.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            keeper.execute('SELECT count(*) FROM users').fetchone()
            def upload(index):
                return self.request('/api/events', {'id': 'event-' + str(index), 'fields': 3, 'files': 1, 'failed': 0}, token)
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(upload, range(12)))
            self.assertTrue(Path(server.DB + '-wal').exists())
            snapshot = manage.backup_database(server.DB, self.root / 'backups' / 'snapshot.sqlite3')
        finally:
            keeper.close()
        admin = self.login()
        self.assertEqual(self.request('/api/stats', token=admin)[0]['fields'], 36)
        with self.assertRaises(FileExistsError):
            manage.backup_database(server.DB, snapshot)
        self.password_file.write_text('second-admin-password\n')
        self.stop()
        self.start()
        self.login()  # Changing the file does not reset the existing account implicitly.
        self.request('/api/login', {'username': 'admin', 'password': 'second-admin-password'}, expected=401)
        manage.reset_admin(self.password_file)
        self.request('/api/stats', token=admin, expected=403)
        self.login(password='second-admin-password')
        self.stop()
        with self.assertRaises(ValueError):
            manage.restore_database(snapshot, False)
        preserved = manage.restore_database(snapshot, True)
        self.assertTrue(preserved.exists())
        self.start()
        restored_admin = self.login()
        self.assertEqual(self.request('/api/stats', token=restored_admin)[0]['fields'], 36)
        self.request('/api/me', token=token, expected=401)
        self.login('worker', 'worker-password')

    def test_admin_secret_required_and_database_health(self):
        os.environ.pop('ADMIN_PASSWORD_FILE')
        os.environ.pop('ADMIN_PASSWORD', None)
        with self.assertRaises(RuntimeError):
            server.init()
        os.environ['ADMIN_PASSWORD_FILE'] = str(self.password_file)
        self.password_file.write_text('short')
        with self.assertRaises(ValueError):
            server.init()
        self.password_file.write_text('valid-admin-password')
        self.start()
        with server.connect() as connection:
            connection.execute('DROP TABLE users')
        self.assertEqual(self.request('/api/health', expected=503)['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
