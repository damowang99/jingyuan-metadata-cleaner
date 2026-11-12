import json,os,re,shutil
from pathlib import Path
from urllib.parse import parse_qs,urlparse
ROOT=Path(os.environ.get('RELEASE_ROOT','/releases'))

def serve(handler,route):
    match=re.fullmatch(r'/api/updates/(darwin|win32)/(arm64|x64)',route)
    if match:
        channel='-zip' if match[1]=='win32' and parse_qs(urlparse(getattr(handler,'path',route)).query).get('format')==['zip'] else ''
        file=ROOT/'manifests'/(match[1]+'-'+match[2]+channel+'.json')
        base=parse_qs(urlparse(getattr(handler,'path',route)).query).get('base',[''])[0]
        if channel=='-zip' and re.fullmatch(r'\d+\.\d+\.\d+',base):
            candidate=ROOT/'manifests'/('win32-'+match[2]+'-from-'+base+'.json')
            try:
                import base64
                full=json.loads(base64.b64decode(json.loads(file.read_text())['payload']))
                delta=json.loads(base64.b64decode(json.loads(candidate.read_text())['payload']))
                if delta['version']==full['version'] and delta.get('baseVersion')==base:file=candidate
            except (OSError,ValueError,KeyError):pass
        try:
            if file.stat().st_size>24000:raise ValueError('manifest too large')
            envelope=json.loads(file.read_text(encoding='utf-8'))
        except FileNotFoundError:handler.reply(404,{'error':'尚未发布该平台版本'});return True
        except (OSError,ValueError):handler.reply(503,{'error':'版本清单不可用'});return True
        handler.reply(200,envelope);return True
    if route.startswith('/downloads/'):
        name=route[len('/downloads/'):]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.(exe|zip)',name):handler.reply(404,{'error':'更新包不存在'});return True
        file=ROOT/'artifacts'/name
        try:
            if file.is_symlink():raise FileNotFoundError()
            stream=file.open('rb')
        except OSError:handler.reply(404,{'error':'更新包不存在'});return True
        with stream:
            handler.send_response(200);handler.send_header('Content-Type','application/octet-stream');handler.send_header('Content-Length',str(os.fstat(stream.fileno()).st_size));handler.send_header('Content-Disposition','attachment; filename="'+name+'"');handler.send_header('Cache-Control','public, max-age=31536000, immutable');handler.end_headers();shutil.copyfileobj(stream,handler.wfile,64*1024)
        return True
    return False
