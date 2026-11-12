import hashlib,json,plistlib,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from update_helper import apply_update

class MacInstallerTests(unittest.TestCase):
 def fixture(self,root):
  old=root/'installed'/'Metadata Cleaner.app';(old/'Contents').mkdir(parents=True)
  info={'CFBundleIdentifier':'com.cleaner.metadata','CFBundleShortVersionString':'1.2.0'}
  (old/'Contents/Info.plist').write_bytes(plistlib.dumps(info));(old/'Contents/old-marker').write_text('keep previous app')
  archive=root/'update.zip'
  with zipfile.ZipFile(archive,'w') as z:z.writestr('Metadata Cleaner.app/Contents/Info.plist',plistlib.dumps({**info,'CFBundleShortVersionString':'1.2.1'}))
  user=root/'profile';user.mkdir();(user/'history.json').write_text('preserve user history')
  return {'target':str(old),'artifact':str(archive),'size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'version':'1.2.1','bundleId':'com.cleaner.metadata','pid':9999999,'token':'a'*32,'work':str(root/'work'),'userData':str(user),'result':str(user/'update-result.json'),'blocked':str(user/'blocked-update.json')}
 def test_success_preserves_profile(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(Path(t))
   def launch(bundle):
    info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes());self.assertEqual(info['CFBundleShortVersionString'],'1.2.1')
    (Path(c['userData'])/('update-ack-'+c['token']+'.json')).write_text(json.dumps({'token':c['token'],'version':c['version']}))
   self.assertTrue(apply_update(c,opener=launch,waiter=lambda _:None,ack_timeout=1))
   self.assertEqual((Path(c['userData'])/'history.json').read_text(),'preserve user history')
   self.assertEqual(json.loads(Path(c['result']).read_text())['status'],'ok')
 def test_failed_start_rolls_back(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(Path(t));launched=[]
   self.assertFalse(apply_update(c,opener=lambda p:launched.append(plistlib.loads((p/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']),waiter=lambda _:None,ack_timeout=0))
   self.assertEqual(launched,['1.2.1','1.2.0'])
   self.assertTrue((Path(c['target'])/'Contents/old-marker').exists())
   self.assertEqual(json.loads(Path(c['blocked']).read_text())['sha256'],c['sha256'])
 def test_failure_before_replacement_reopens_original(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(Path(t));c['restartOnFailure']=True;Path(c['artifact']).write_bytes(b'corrupted');opened=[];waited=[]
   self.assertFalse(apply_update(c,opener=lambda p:opened.append(p),waiter=lambda pid:waited.append(pid),ack_timeout=0))
   self.assertEqual(opened,[Path(c['target'])]);self.assertEqual(waited,[c['pid']])
 def test_bad_hash_keeps_original(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(Path(t));Path(c['artifact']).write_bytes(b'corrupted')
   self.assertFalse(apply_update(c,opener=lambda _:self.fail('should not launch'),waiter=lambda _:None,ack_timeout=0))
   self.assertTrue((Path(c['target'])/'Contents/old-marker').exists())
if __name__=='__main__':unittest.main()
