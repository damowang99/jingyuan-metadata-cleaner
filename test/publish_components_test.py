import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('publisher',Path(__file__).resolve().parents[1]/'server'/'publish_release.py');publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
class PublishComponentTests(unittest.TestCase):
 def test_signer_rejects_missing_windows_exiftool_before_key_access(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);artifact=root/'client.zip';names=['Metadata Cleaner.exe','resources/app.asar','resources/bin/windows-python/python.exe']
   info=dict(appId='com.cleaner.metadata',version='1.6.4',arch='x64',files={name:{} for name in names})
   with zipfile.ZipFile(artifact,'w') as archive:
    archive.writestr('app/update-package.json',json.dumps(info))
    for name in names:archive.writestr('app/'+name,b'fixture')
   with self.assertRaisesRegex(ValueError,'required component.*exiftool'):
    publisher.publish(artifact,'1.6.4','win32','x64',root/'releases',root/'nonexistent-private-key.pem')
if __name__=='__main__':unittest.main()
