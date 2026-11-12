"""Unprivileged Mac update installer. It runs from a private copy outside the app."""
import hashlib,json,os,plistlib,shutil,subprocess,sys,time,uuid,zipfile,signal
from pathlib import Path

def write_json(path,body):
    path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(body),encoding='utf-8');os.chmod(temp,0o600);temp.replace(path)

def wait_exit(pid,timeout=90):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:os.kill(pid,0)
        except ProcessLookupError:return
        time.sleep(.2)
    raise RuntimeError('旧客户端未退出，未替换应用')

def apply_update(config,opener=None,waiter=wait_exit,ack_timeout=120):
    target=Path(config['target']);artifact=Path(config['artifact']);work=Path(config['work']);work.mkdir(parents=True,exist_ok=True)
    backup=target.with_name('.metadata-cleaner-previous-'+uuid.uuid4().hex+'.app');incoming=target.with_name('.metadata-cleaner-incoming-'+uuid.uuid4().hex+'.app');moved=False
    ack=Path(config['userData'])/('update-ack-'+config['token']+'.json')
    if opener is None:
        def opener(bundle):subprocess.run(['/usr/bin/open','-n','-a',str(bundle),'--args','--update-ack='+config['token']],check=True)
    try:
        h=hashlib.sha256()
        with artifact.open('rb') as file:
            for chunk in iter(lambda:file.read(1024*1024),b''):h.update(chunk)
        if artifact.stat().st_size!=config['size'] or h.hexdigest()!=config['sha256']:raise RuntimeError('更新文件校验失败')
        with zipfile.ZipFile(artifact) as archive:
            for entry in archive.infolist():
                path=Path(entry.filename)
                if path.is_absolute() or '..' in path.parts:raise RuntimeError('更新包路径无效')
            if sum(e.file_size for e in archive.infolist())>3*1024**3:raise RuntimeError('解压大小超限')
        stage=work/'unpacked';stage.mkdir()
        subprocess.run(['/usr/bin/ditto','-x','-k',str(artifact),str(stage)],check=True)
        source=stage/'Metadata Cleaner.app'
        with (source/'Contents/Info.plist').open('rb') as f:info=plistlib.load(f)
        if info.get('CFBundleIdentifier')!=config['bundleId'] or info.get('CFBundleShortVersionString')!=config['version']:raise RuntimeError('应用身份或版本不匹配')
        with (target/'Contents/Info.plist').open('rb') as f:old_info=plistlib.load(f)
        if old_info.get('CFBundleIdentifier')!=config['bundleId']:raise RuntimeError('目标不是净元应用')
        shutil.copytree(source,incoming,symlinks=True)
        waiter(config['pid'])
        target.rename(backup);moved=True;incoming.rename(target)
        opener(target)
        deadline=time.monotonic()+ack_timeout
        while time.monotonic()<deadline:
            try:
                result=json.loads(ack.read_text())
                if result.get('version')==config['version'] and result.get('token')==config['token']:break
            except (OSError,ValueError):pass
            time.sleep(.25)
        else:raise RuntimeError('新版本未确认启动，恢复旧版')
        write_json(config['result'],{'status':'ok','version':config['version']});ack.unlink(missing_ok=True);shutil.rmtree(backup);shutil.rmtree(stage);return True
    except Exception as error:
        if moved:
            try:
                launched=json.loads((Path(config['userData'])/('update-start-'+config['token']+'.json')).read_text())
                if launched.get('token')==config['token']:
                    os.kill(int(launched['pid']),signal.SIGTERM)
                    time.sleep(1)
            except (OSError,ValueError,KeyError):pass
            if target.exists():target.rename(work/('failed-app-'+uuid.uuid4().hex+'.app'))
            if backup.exists():backup.rename(target)
        write_json(config['blocked'],{'version':config['version'],'sha256':config['sha256']})
        write_json(config['result'],{'status':'failed','version':config['version'],'error':str(error)})
        if moved or config.get('restartOnFailure'):
            try:
                if not moved:waiter(config['pid'])
                opener(target)
            except Exception:pass
        return False
    finally:
        if incoming.exists():shutil.rmtree(incoming,ignore_errors=True)

def main(config_path):
    config=json.loads(Path(config_path).read_text());config['restartOnFailure']=True;config['work']=str(Path(config_path).parent/'work')
    raise SystemExit(0 if apply_update(config) else 1)
