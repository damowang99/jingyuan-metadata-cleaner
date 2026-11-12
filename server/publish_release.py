"""Publish an immutable artifact, then atomically switch its signed release manifest."""
import argparse,base64,datetime,hashlib,json,os,plistlib,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path

def publish(artifact,version,platform,arch,root,key):
    artifact=Path(artifact).resolve();root=Path(root);key=Path(key)
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or platform not in ('darwin','win32') or arch not in ('arm64','x64'):raise ValueError('无效版本或平台')
    suffix='.zip' if platform=='darwin' or artifact.suffix.lower()=='.zip' else '.exe'
    if artifact.suffix.lower()!=suffix:raise ValueError('安装包类型不匹配')
    if platform=='darwin':
        with zipfile.ZipFile(artifact) as archive:
            info=plistlib.loads(archive.read('Metadata Cleaner.app/Contents/Info.plist'))
            if info.get('CFBundleIdentifier')!='com.cleaner.metadata' or info.get('CFBundleShortVersionString')!=version:raise ValueError('Mac应用身份或版本不匹配')
    if platform=='win32' and suffix=='.zip':
        with zipfile.ZipFile(artifact) as archive:
            info=json.loads(archive.read('app/update-package.json'))
            if info.get('appId')!='com.cleaner.metadata' or info.get('version')!=version or info.get('arch')!=arch:raise ValueError('Windows archive identity/version mismatch')
            for required in ['Metadata Cleaner.exe','resources/app.asar','resources/bin/windows-python/python.exe','resources/app.asar.unpacked/node_modules/exiftool-vendored.exe/bin/exiftool.exe']:
                if required not in info.get('files',{}) or 'app/'+required not in archive.namelist():raise ValueError('Windows package missing required component: '+required)
    size=artifact.stat().st_size
    if not 1024<=size<=1024**3:raise ValueError('安装包大小无效')
    h=hashlib.sha256()
    with artifact.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):h.update(chunk)
    digest=h.hexdigest();name='cleaner-'+version+'-'+platform+'-'+arch+'-'+digest[:12]+suffix
    (root/'artifacts').mkdir(parents=True,exist_ok=True);(root/'manifests').mkdir(exist_ok=True)
    manifest=root/'manifests'/(platform+'-'+arch+('-zip' if platform=='win32' and suffix=='.zip' else '')+'.json')
    if manifest.exists():
        old=json.loads(base64.b64decode(json.loads(manifest.read_text())['payload']))
        if tuple(map(int,version.split('.')))<tuple(map(int,old['version'].split('.'))):raise ValueError('禁止发布比当前通道更旧的版本')
        if old['version']==version and old['sha256']!=digest:raise ValueError('同一版本号不可发布不同内容，请递增版本号')
    payload={'schema':1,'version':version,'platform':platform,'arch':arch,'url':'/downloads/'+name,'size':size,'sha256':digest,'publishedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    with tempfile.TemporaryDirectory() as temp:
        message=Path(temp)/'payload';message.write_bytes(raw);signature=Path(temp)/'signature'
        subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(key),'-in',str(message),'-out',str(signature)],check=True,capture_output=True)
        envelope={'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(signature.read_bytes()).decode()}
    destination=root/'artifacts'/name
    if not destination.exists():
        temp=destination.with_suffix(destination.suffix+'.upload');shutil.copyfile(artifact,temp);os.chmod(temp,0o644);temp.replace(destination)
    temp=manifest.with_suffix('.tmp');temp.write_text(json.dumps(envelope),encoding='utf-8');os.chmod(temp,0o644);temp.replace(manifest)
    if platform=='win32' and suffix=='.zip':
        from publish_delta import publish_delta
        for previous in (root/'artifacts').glob('cleaner-*-win32-'+arch+'-*.zip'):
            if previous==destination or '-code-' in previous.name:continue
            try:
                with zipfile.ZipFile(previous) as z:base=json.loads(z.read('app/update-package.json'))['version']
                if tuple(map(int,base.split('.'))) < (1,6,7) or tuple(map(int,base.split('.'))) >= tuple(map(int,version.split('.'))):continue
                publish_delta(previous,destination,root,key)
            except Exception as error:
                # Optional optimization never prevents the full update channel from working.
                print('Code package skipped: '+str(error),file=__import__('sys').stderr)
    return payload

def main():
    p=argparse.ArgumentParser();p.add_argument('--artifact',required=True);p.add_argument('--version',required=True);p.add_argument('--platform',required=True);p.add_argument('--arch',required=True);p.add_argument('--root',default='/opt/metadata-cleaner/releases');p.add_argument('--key',default='/opt/metadata-cleaner/secrets/update-private.pem');args=p.parse_args()
    print(json.dumps(publish(args.artifact,args.version,args.platform,args.arch,args.root,args.key),ensure_ascii=False))
if __name__=='__main__':main()
