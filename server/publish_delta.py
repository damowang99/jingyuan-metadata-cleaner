"""Optional Windows code package. Full signed ZIP remains the fallback channel."""
import argparse,base64,datetime,hashlib,json,os,subprocess,tempfile,zipfile
from pathlib import Path

def publish_delta(base,new,root,key):
    root=Path(root)
    with zipfile.ZipFile(base) as old,zipfile.ZipFile(new) as latest:
        a=json.loads(old.read('app/update-package.json'));b=json.loads(latest.read('app/update-package.json'))
        if a['appId']!=b['appId'] or b['platform']!='win32' or a['arch']!=b['arch']:raise ValueError('Package identity mismatch')
        if set(a['files'])!=set(b['files']):return None
        changed={name:value for name,value in b['files'].items() if a['files'][name]!=value}
        if not changed or set(changed)-{'Metadata Cleaner.exe','resources/app.asar'}:return None
        marker=dict(b,kind='code',baseVersion=a['version'],files=changed,baseFiles={n:v for n,v in b['files'].items() if n not in changed})
        with tempfile.TemporaryDirectory() as temp:
            package=Path(temp)/'code.zip'
            with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
                for name in changed:
                    data=latest.read('app/'+name)
                    if len(data)!=changed[name]['size'] or hashlib.sha256(data).hexdigest()!=changed[name]['sha256']:raise ValueError('File integrity failed')
                    archive.writestr('app/'+name,data)
                archive.writestr('app/update-package.json',json.dumps(marker))
            digest=hashlib.sha256(package.read_bytes()).hexdigest();name='cleaner-'+b['version']+'-win32-'+b['arch']+'-code-'+digest[:12]+'.zip'
            payload=dict(schema=1,kind='code',baseVersion=a['version'],version=b['version'],platform='win32',arch=b['arch'],url='/downloads/'+name,size=package.stat().st_size,sha256=digest,publishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
            raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode();message=Path(temp)/'payload';message.write_bytes(raw);signature=Path(temp)/'signature'
            subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(key),'-in',str(message),'-out',str(signature)],check=True,capture_output=True)
            envelope=dict(payload=base64.b64encode(raw).decode(),signature=base64.b64encode(signature.read_bytes()).decode())
            destination=root/'artifacts'/name
            if not destination.exists():os.replace(package,destination);os.chmod(destination,0o644)
            manifest=root/'manifests'/('win32-'+b['arch']+'-from-'+a['version']+'.json');pending=manifest.with_suffix('.tmp');pending.write_text(json.dumps(envelope));os.chmod(pending,0o644);os.replace(pending,manifest)
            return payload
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--new',required=True);p.add_argument('--root',default='/opt/metadata-cleaner/releases');p.add_argument('--key',default='/opt/metadata-cleaner/secrets/update-private.pem');a=p.parse_args();print(json.dumps(publish_delta(a.base,a.new,a.root,a.key)))
