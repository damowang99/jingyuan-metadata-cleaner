"""Windows update worker; runs from a copied embedded Python outside the app directory."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
import stat
from pathlib import PurePosixPath


def write_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def installer_command(artifact, target):
    # NSIS /D= must be last and its value must not be quoted, even with spaces.
    return subprocess.list2cmdline([str(artifact), '/S']) + ' /D=' + str(target)


class WindowsParent:
    def __init__(self, pid):
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.OpenProcess(0x00100000, False, pid)
        if not self.handle:
            error = ctypes.get_last_error()
            if error != 87:
                raise ctypes.WinError(error)

    def alive(self):
        if not self.handle:
            return False
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 258

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class WindowsPlatform:
    def __init__(self, user_data=None, background=False):
        self.background = background
        self.user_data = Path(user_data) if user_data else None

    def parent(self, pid):
        return WindowsParent(pid)

    def install(self, artifact, target):
        return subprocess.Popen(installer_command(artifact, target), executable=str(artifact),
                                creationflags=subprocess.CREATE_NO_WINDOW)

    def stop(self, process):
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=30)

    def launch(self, executable, token):
        environment = dict(os.environ)
        environment.pop('ELECTRON_RUN_AS_NODE', None)
        startup = subprocess.STARTUPINFO()
        if not self.background:
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # Quiet startup is controlled by the app flag, not a forced OS hide state.
        # This leaves later user-initiated window presentation unaffected.
        startup.wShowWindow = 1
        log_stream = (self.user_data / ('update-launch-' + token + '.log')).open('ab') if self.user_data else None
        try:
            return subprocess.Popen([str(executable), '--update-ack=' + token, '--background-after-update' if self.background else '--show-after-update'],
                                    cwd=str(executable.parent), env=environment, stdin=subprocess.DEVNULL,
                                    stdout=log_stream or subprocess.DEVNULL, stderr=log_stream or subprocess.DEVNULL,
                                    close_fds=True, startupinfo=startup,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        finally:
            if log_stream:
                log_stream.close()



def matches(file, expected):
    if not file.is_file() or file.is_symlink() or file.stat().st_size != expected['size']:
        return False
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest() == expected['sha256']


def safe_target(root, name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or any(part in ('.', '..') or ':' in part for part in parts):
        raise RuntimeError('Unsafe update target')
    file = root.joinpath(*parts)
    if any(parent.is_symlink() for parent in [file, *file.parents] if parent != root.parent):
        raise RuntimeError('Symbolic link in update target')
    return file


def extract_package(artifact, stage, config):
    seen = set()
    with zipfile.ZipFile(artifact) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or sum(info.file_size for info in entries) > 2 * 1024**3:
            raise RuntimeError('Update archive is too large')
        for info in entries:
            name = info.filename
            parts = PurePosixPath(name).parts
            reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {'COM' + str(i) for i in range(1, 10)} | {'LPT' + str(i) for i in range(1, 10)}
            if not parts or parts[0] != 'app' or name.startswith('/') or '\\' in name or any(part in ('.', '..') or ':' in part or part.endswith(('.', ' ')) or part.split('.')[0].upper() in reserved for part in parts):
                raise RuntimeError('Unsafe archive path: ' + name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise RuntimeError('Archive symbolic links are not allowed')
            key = name.rstrip('/').casefold()
            if key in seen:
                raise RuntimeError('Duplicate archive path: ' + name)
            seen.add(key)
            destination = stage.joinpath(*parts[1:])
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open('xb') as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
    marker = stage / 'update-package.json'
    if marker.stat().st_size > 2 * 1024 * 1024:
        raise RuntimeError('Package manifest is too large')
    info = json.loads(marker.read_text(encoding='utf-8'))
    if info.get('appId') != 'com.cleaner.metadata' or info.get('version') != config['version'] or info.get('arch') != config.get('arch', 'x64') or info.get('platform') != 'win32':
        raise RuntimeError('Update package identity/version mismatch')
    executable = info.get('executable', '')
    if not executable or '/' in executable or '\\' in executable or ':' in executable or not executable.lower().endswith('.exe'):
        raise RuntimeError('Invalid package executable')
    files = info.get('files')
    if not isinstance(files, dict):
        raise RuntimeError('Missing package file manifest')
    actual = {file.relative_to(stage).as_posix() for file in stage.rglob('*') if file.is_file()} - {'update-package.json'}
    if actual != set(files):
        raise RuntimeError('Package file list mismatch')
    for name, expected in files.items():
        file = stage / name
        digest = hashlib.sha256()
        with file.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        if file.stat().st_size != expected['size'] or digest.hexdigest() != expected['sha256']:
            raise RuntimeError('Package file integrity failed: ' + name)
    base = info.get('baseFiles', {})
    if info.get('kind') == 'code':
        if set(files) - {executable, 'resources/app.asar'} or not base:
            raise RuntimeError('Invalid code-only package')
        for name, expected in base.items():
            if not matches(safe_target(Path(config['target']), name), expected):
                raise RuntimeError('BASE_MISMATCH: ' + name)
    elif base:
        raise RuntimeError('Unexpected base manifest')
    for required in (executable, 'resources/app.asar', 'resources/bin/windows-python/python.exe', 'resources/app.asar.unpacked/node_modules/exiftool-vendored.exe/bin/exiftool.exe'):
        if required not in files and required not in base:
            raise RuntimeError('Required application file missing: ' + required)
    return executable


def restore_app(backup, target, preserve=(), remove_extras=True):
    # Mirror opaque files with OS calls, never Electron's ASAR virtual filesystem.
    target.mkdir(parents=True, exist_ok=True)
    for source in backup.iterdir():
        destination = target / source.name
        if source.is_dir() and not source.is_symlink():
            restore_app(source, destination, remove_extras=remove_extras)
        else:
            shutil.copy2(source, destination)
    for item in target.iterdir():
        if remove_extras and item.name not in preserve and not (backup / item.name).exists():
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()


def apply_update(config, platform, parent_timeout=90, install_timeout=600, startup_timeout=120, stable_timeout=3, interval=0.25):
    target, backup = Path(config['target']), Path(config['backup'])
    artifact = Path(config['artifact'])
    executable = target / config['executable']
    ack = Path(config['userData']) / ('update-ack-' + config['token'] + '.json')
    log_path = Path(config['helperLog'])
    parent = installer = new_process = None
    backup_complete = install_started = False
    staged = None
    changes = None
    created = []
    new_executable = executable
    stage = 'validate-artifact'

    def log(message):
        # Write directly as well as to redirected stderr: no dependence on console encoding.
        with log_path.open('a', encoding='utf-8') as stream:
            stream.write(time.strftime('%Y-%m-%dT%H:%M:%S') + ' ' + message + '\n')
            stream.flush()

    def cancelled():
        if Path(config['cancel']).exists():
            raise RuntimeError('Update cancelled; existing application remains running')

    try:
        log('Embedded Python worker started: ' + sys.version.split()[0])
        cancelled()
        digest = hashlib.sha256()
        with artifact.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if artifact.stat().st_size != config['size'] or digest.hexdigest() != config['sha256']:
            raise RuntimeError('Update integrity check failed')
        stage = 'validate-existing-application'
        if not executable.is_file() or not (target / 'resources' / 'app.asar').is_file():
            raise RuntimeError('Previous application is incomplete')
        resolved_target, resolved_backup = target.resolve(), backup.resolve()
        if resolved_backup == resolved_target or resolved_target in resolved_backup.parents or resolved_backup in resolved_target.parents:
            raise RuntimeError('Backup must be outside application directory')
        probe = target / ('.cleaner-write-' + config['token'])
        try:
            with probe.open('xb') as stream:
                stream.write(b'write-check')
        finally:
            probe.unlink(missing_ok=True)
        stage = 'open-parent-process'
        if artifact.suffix.lower() == '.zip':
            stage = 'extract-and-verify-package'
            staged = backup.parent / 'staged-app'
            log('Extracting and verifying Windows application files')
            new_name = extract_package(artifact, staged, config)
            new_executable = target / new_name
        parent = platform.parent(config['pid'])
        cancelled()
        stage = 'signal-ready'
        write_json(config['ready'], {'token': config['token'], 'pid': os.getpid()})
        stage = 'wait-for-previous-application'
        log('Helper ready; waiting for previous application to exit')
        deadline = time.monotonic() + parent_timeout
        while parent.alive():
            cancelled()
            if time.monotonic() > deadline:
                raise RuntimeError('Previous application did not exit')
            time.sleep(interval)
        cancelled()
        stage = 'backup-application'
        log('Backing up changed application files only' if staged else 'Backing up previous application')
        if staged:
            info = json.loads((staged / 'update-package.json').read_text(encoding='utf-8'))
            # Check again after the old process exits, before making any changes.
            for name, expected in info.get('baseFiles', {}).items():
                if not matches(safe_target(target, name), expected): raise RuntimeError('BASE_MISMATCH: ' + name)
            changes = [name for name, expected in info['files'].items() if not matches(safe_target(target, name), expected)]
            backup.mkdir()
            for name in changes:
                source = safe_target(target, name)
                if source.exists():
                    destination = backup / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                else: created.append(name)
            log('Changed files: ' + str(len(changes)))
        else:
            shutil.copytree(target, backup)
        backup_complete = True
        if staged:
            stage = 'apply-verified-files'
            log('Updating verified files in the existing application directory: ' + str(target))
            install_started = True
            for name in changes:
                destination = safe_target(target, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged / name, destination)
        else:
            stage = 'run-installer'
            log('Installer path: ' + str(artifact) + '; exists=' + str(artifact.is_file()))
            log('Install target: ' + str(target))
            log('Running silent installer')
            install_started = True
            installer = platform.install(artifact, target)
            try:
                code = installer.wait(timeout=install_timeout)
            except subprocess.TimeoutExpired:
                installer.kill()
                installer.wait(timeout=30)
                raise RuntimeError('Installer timed out')
            if code != 0:
                raise RuntimeError('Installer failed: exit code ' + str(code))
        stage = 'launch-new-application'
        log('Executable path: ' + str(new_executable) + '; exists=' + str(new_executable.is_file()))
        if not new_executable.is_file():
            raise RuntimeError('Updated executable is missing: ' + str(new_executable))
        log('Starting new application')
        new_process = platform.launch(new_executable, config['token'])
        stage = 'wait-for-startup-acknowledgement'
        deadline = time.monotonic() + startup_timeout
        confirmed_at = None
        while time.monotonic() < deadline:
            if ack.exists():
                try:
                    response = json.loads(ack.read_text(encoding='utf-8-sig'))
                except (ValueError, OSError):
                    response = {}
                if response.get('version') == config['version'] and response.get('token') == config['token'] and ((response.get('ready') is True and response.get('trayReady') is True) if config.get('background') else response.get('visible') is True):
                    if new_process.poll() is not None:
                        raise RuntimeError('New application exited after startup acknowledgement: ' + str(new_process.poll()))
                    if confirmed_at is None:
                        confirmed_at = time.monotonic()
                    if time.monotonic() - confirmed_at < stable_timeout:
                        if new_process.poll() is not None:
                            raise RuntimeError('New application exited after startup acknowledgement: ' + str(new_process.poll()))
                        time.sleep(interval)
                        continue
                    write_json(config['result'], {'status': 'ok', 'version': config['version'], 'visible': response.get('visible',False), 'background':bool(config.get('background')), 'pid': new_process.pid, 'log': str(log_path)})
                    log('New version ready and process stable; update completed')
                    ack.unlink(missing_ok=True)
                    try:
                        shutil.rmtree(backup)
                    except OSError as error:
                        log('Backup retained: ' + str(error))
                    return True
            code = new_process.poll()
            if code is not None:
                raise RuntimeError('New application exited before startup acknowledgement: ' + str(code))
            time.sleep(interval)
        raise RuntimeError('New application did not confirm startup')
    except Exception as error:
        reason = str(error)
        log('Update failed at ' + stage + ': ' + reason)
        log(traceback.format_exc())
        if new_process and new_process.poll() is None:
            try:
                platform.stop(new_process)
            except Exception as stop_error:
                log('Stopping failed application: ' + str(stop_error))
        restored = not install_started
        if install_started and backup_complete:
            try:
                log('Restoring previous application')
                restore_app(backup, target, remove_extras=not bool(staged))
                for name in created: safe_target(target, name).unlink(missing_ok=True)
                restored = True
            except Exception as rollback_error:
                reason += '; restore failed: ' + str(rollback_error)
                log(reason)
        write_json(config['blocked'], {'version': config['version'], 'sha256': config['sha256'], 'engine': 'python-v1'})
        write_json(config['result'], {'status': 'failed', 'version': config['version'], 'error': reason, 'stage': stage, 'winerror': getattr(error, 'winerror', None), 'filename': getattr(error, 'filename', None), 'log': str(log_path)})
        if restored and parent and not parent.alive():
            try:
                platform.launch(executable, config['token'])
                log('Previous application restarted')
            except Exception as launch_error:
                log('Restart failed: ' + str(launch_error))
        return False
    finally:
        if parent:
            parent.close()


def main(config_path):
    config = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    if os.name != 'nt':
        raise RuntimeError('This worker requires Windows')
    return apply_update(config, WindowsPlatform(config['userData'], background=bool(config.get('background'))))


if __name__ == '__main__':
    try:
        sys.exit(0 if main(sys.argv[1]) else 1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
