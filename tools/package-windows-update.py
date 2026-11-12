from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib,json,shutil
project=Path(__file__).resolve().parents[1]
version=json.loads((project/'desktop/package.json').read_text(encoding='utf-8'))['version']
dist=project/'desktop/dist'
root=dist/'win-unpacked'
files={}
for file in sorted(root.rglob('*')):
 if not file.is_file():continue
 if file.is_symlink():raise RuntimeError('Symlinks not supported')
 digest=hashlib.sha256()
 with file.open('rb') as source:
  for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
 files[file.relative_to(root).as_posix()]={'size':file.stat().st_size,'sha256':digest.hexdigest()}
assert any(name.endswith('exiftool-vendored.exe/bin/exiftool.exe') for name in files),'Missing Windows ExifTool'
marker=dict(schema=1,appId='com.cleaner.metadata',version=version,platform='win32',arch='x64',executable='Metadata Cleaner.exe',files=files)
with ZipFile(dist/f'Metadata-Cleaner-{version}-win-x64-update.zip','w',ZIP_DEFLATED,compresslevel=9) as archive:
 for name in files:archive.write(root/name,'app/'+name)
 archive.writestr('app/update-package.json',json.dumps(marker,ensure_ascii=False))
