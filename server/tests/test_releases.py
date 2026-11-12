import json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,release_api
class Quiet(server.Handler):
 def log_message(self,*_):pass
class ReleasesTests(unittest.TestCase):
 def test_manifest_download_and_path_rejection(self):
  with tempfile.TemporaryDirectory() as folder:
   previous=release_api.ROOT;release_api.ROOT=Path(folder)
   (release_api.ROOT/'manifests').mkdir();(release_api.ROOT/'artifacts').mkdir()
   envelope={'payload':'test','signature':'test'}
   (release_api.ROOT/'manifests/darwin-arm64.json').write_text(json.dumps(envelope))
   (release_api.ROOT/'artifacts/client.zip').write_bytes(b'zip package')
   (release_api.ROOT/'artifacts/link.zip').symlink_to(release_api.ROOT/'manifests/darwin-arm64.json')
   http=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(http.server_port)
   try:
    with urllib.request.urlopen(base+'/api/updates/darwin/arm64') as r:self.assertEqual(json.load(r),envelope);self.assertEqual(r.headers['Cache-Control'],'no-store')
    with urllib.request.urlopen(base+'/downloads/client.zip') as r:self.assertEqual(r.read(),b'zip package');self.assertEqual(r.headers['Content-Length'],'11')
    for route in ['/downloads/link.zip','/downloads/../secrets/key','/downloads/%2e%2e','/api/updates/linux/x64','/api/updates/win32/x64']:
     with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+route)
     self.assertEqual(error.exception.code,404)
   finally:http.shutdown();http.server_close();thread.join();release_api.ROOT=previous
 def test_windows_zip_channel_is_separate_from_legacy_installer(self):
  with tempfile.TemporaryDirectory() as folder:
   previous=release_api.ROOT;release_api.ROOT=Path(folder);(release_api.ROOT/'manifests').mkdir()
   legacy={'payload':'legacy','signature':'old'};modern={'payload':'zip','signature':'new'}
   (release_api.ROOT/'manifests/win32-x64.json').write_text(json.dumps(legacy))
   (release_api.ROOT/'manifests/win32-x64-zip.json').write_text(json.dumps(modern))
   http=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(http.server_port)
   try:
    with urllib.request.urlopen(base+'/api/updates/win32/x64') as response:self.assertEqual(json.load(response),legacy)
    with urllib.request.urlopen(base+'/api/updates/win32/x64?format=zip') as response:self.assertEqual(json.load(response),modern)
   finally:http.shutdown();http.server_close();thread.join();release_api.ROOT=previous
if __name__=='__main__':unittest.main()
