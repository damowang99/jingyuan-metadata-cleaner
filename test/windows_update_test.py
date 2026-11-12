import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

spec = importlib.util.spec_from_file_location('windows_worker', Path(__file__).resolve().parents[1] / 'desktop' / 'windows-update.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class Parent:
    def __init__(self, alive=False):
        self.running = alive
        self.closed = False
    def alive(self):
        return self.running
    def close(self):
        self.closed = True


class Platform:
    def __init__(self, config, mode='ok', alive=False):
        self.config, self.mode = config, mode
        self.parent_process = Parent(alive)
        self.children, self.launches = [], []
        self.installations = 0

    def parent(self, pid):
        return self.parent_process

    def install(self, artifact, target):
        self.installations += 1
        # A real child mutates opaque application files, simulating installer success/failure.
        script = "from pathlib import Path;import sys;p=Path(sys.argv[1]);(p/'Metadata Cleaner.exe').write_bytes(b'new exe');(p/'resources'/'app.asar').write_bytes(b'new asar');(p/'extra.tmp').write_bytes(b'extra');sys.exit(int(sys.argv[2]))"
        return subprocess.Popen([sys.executable, '-c', script, str(target), '9' if self.mode == 'install-fail' else '0'])

    def launch(self, executable, token):
        version = 'old' if executable.read_bytes() == b'old exe' else self.config['version']
        self.launches.append(version)
        if self.mode == 'startup-fail' and version != 'old':
            child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(23)'])
        else:
            script = "import json,sys,time;from pathlib import Path;p=Path(sys.argv[1])/('update-ack-'+sys.argv[2]+'.json');p.write_text(json.dumps({'version':sys.argv[3],'token':sys.argv[2],'visible':True,'ready':True,'trayReady':True}),encoding='utf-8');time.sleep(30)"
            if self.config.get('background'):script=script.replace("'visible':True","'visible':False")
            if self.mode == 'missing-ready':script=script.replace("'trayReady':True","'trayReady':False")
            if self.mode == 'startup-late-fail' and version != 'old':script=script.replace('time.sleep(30)','time.sleep(0.03);raise SystemExit(42)')
            child = subprocess.Popen([sys.executable, '-c', script, self.config['userData'], token, version])
        self.children.append(child)
        return child

    def stop(self, process):
        process.kill()
        process.wait(timeout=5)

    def cleanup(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


class UpdateWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cleaner-worker-')
        self.root = Path(self.temp.name).resolve() / '测试用户 空格'
        self.root.mkdir()
        self.target = self.root / '安装目录 app'
        (self.target / 'resources').mkdir(parents=True)
        (self.target / 'Metadata Cleaner.exe').write_bytes(b'old exe')
        (self.target / 'resources' / 'app.asar').write_bytes(b'old opaque asar')
        self.task = self.root / 'updates' / 'install-test'
        self.task.mkdir(parents=True)
        artifact = self.task / 'installer.exe'
        artifact.write_bytes(b'verified installer fixture')
        self.config = dict(target=str(self.target), backup=str(self.task / 'backup'),
                           artifact=str(artifact), executable='Metadata Cleaner.exe',
                           sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                           size=artifact.stat().st_size, pid=123, token='unique-test-token',
                           version='1.5.7', userData=str(self.root), result=str(self.root / 'result.json'),
                           blocked=str(self.root / 'blocked.json'), ready=str(self.task / 'ready.json'),
                           cancel=str(self.task / 'cancel'), helperLog=str(self.task / 'helper.log'))
        self.platform = Platform(self.config)

    def tearDown(self):
        self.platform.cleanup()
        self.temp.cleanup()

    def run_worker(self):
        return worker.apply_update(self.config, self.platform, parent_timeout=0.08,
                                   startup_timeout=2, stable_timeout=0.1, interval=0.01)

    def result(self):
        return json.loads(Path(self.config['result']).read_text(encoding='utf-8'))

    def test_actual_filesystem_success_unicode_path_ready_ack_and_cleanup(self):
        self.assertTrue(self.run_worker())
        self.assertEqual(self.result()['status'], 'ok')
        self.assertEqual((self.target / 'resources' / 'app.asar').read_bytes(), b'new asar')
        self.assertFalse(Path(self.config['backup']).exists())
        self.assertFalse(Path(self.config['blocked']).exists())
        ready = json.loads(Path(self.config['ready']).read_text(encoding='utf-8'))
        self.assertEqual(ready, dict(token=self.config['token'], pid=os.getpid()))
        self.assertIn('update completed', Path(self.config['helperLog']).read_text(encoding='utf-8'))
        self.assertTrue(self.platform.parent_process.closed)

    def test_partial_installer_failure_restores_opaque_asar_and_restarts_old(self):
        self.platform.mode = 'install-fail'
        self.assertFalse(self.run_worker())
        self.assertIn('exit code 9', self.result()['error'])
        self.assertEqual((self.target / 'resources' / 'app.asar').read_bytes(), b'old opaque asar')
        self.assertFalse((self.target / 'extra.tmp').exists())
        self.assertEqual(self.platform.launches, ['old'])

    def test_new_app_early_exit_restores_and_restarts_old(self):
        self.platform.mode = 'startup-fail'
        self.assertFalse(self.run_worker())
        self.assertIn('23', self.result()['error'])
        self.assertEqual((self.target / 'Metadata Cleaner.exe').read_bytes(), b'old exe')
        self.assertEqual(self.platform.launches, ['1.5.7', 'old'])

    def test_corrupt_installer_never_signals_ready_or_changes_app(self):
        Path(self.config['artifact']).write_bytes(b'tampered')
        self.assertFalse(self.run_worker())
        self.assertIn('integrity', self.result()['error'])
        self.assertFalse(Path(self.config['ready']).exists())
        self.assertEqual(self.platform.installations, 0)
        self.assertEqual((self.target / 'Metadata Cleaner.exe').read_bytes(), b'old exe')

    def test_cancel_keeps_existing_app_and_never_installs(self):
        Path(self.config['cancel']).write_text('cancel')
        self.platform.parent_process.running = True
        self.assertFalse(self.run_worker())
        self.assertEqual(self.platform.installations, 0)
        self.assertEqual(self.platform.launches, [])
        self.assertFalse(Path(self.config['ready']).exists())

    def test_parent_not_exiting_never_starts_installer(self):
        self.platform.parent_process.running = True
        self.assertFalse(self.run_worker())
        self.assertIn('did not exit', self.result()['error'])
        self.assertEqual(self.platform.installations, 0)
        self.assertEqual(self.platform.launches, [])

    def test_backup_nested_in_app_is_rejected_before_ready(self):
        self.config['backup'] = str(self.target / 'nested-backup')
        self.assertFalse(self.run_worker())
        self.assertIn('outside', self.result()['error'])
        self.assertFalse(Path(self.config['ready']).exists())

    def make_archive(self, version=None, unsafe=None):
        payload = {'Metadata Cleaner.exe': b'new exe', 'resources/app.asar': b'new asar',
                   'resources/bin/windows-python/python.exe': b'python fixture', 'resources/app.asar.unpacked/node_modules/exiftool-vendored.exe/bin/exiftool.exe': b'exiftool fixture'}
        info = dict(schema=1, appId='com.cleaner.metadata', platform='win32', arch='x64',
                    executable='Metadata Cleaner.exe', version=version or self.config['version'],
                    files={name:dict(size=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in payload.items()})
        artifact = self.task / 'package.zip'
        with zipfile.ZipFile(artifact,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in payload.items():archive.writestr('app/'+name,data)
            archive.writestr('app/update-package.json',json.dumps(info))
            if unsafe:archive.writestr(unsafe,b'escape')
        self.config['artifact']=str(artifact)
        self.config['size']=artifact.stat().st_size
        self.config['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()

    def make_code_archive(self):
        self.make_archive()
        artifact=Path(self.config['artifact'])
        with zipfile.ZipFile(artifact) as z: entries={n:z.read(n) for n in z.namelist()}
        info=json.loads(entries['app/update-package.json']);info['kind']='code';info['baseFiles']={}
        for name in list(info['files']):
            if name not in ('Metadata Cleaner.exe','resources/app.asar'):
                file=self.target/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(entries.pop('app/'+name))
                info['baseFiles'][name]=info['files'].pop(name)
        entries['app/update-package.json']=json.dumps(info).encode()
        with zipfile.ZipFile(artifact,'w') as z:
            for name,data in entries.items():z.writestr(name,data)
        self.config['size']=artifact.stat().st_size;self.config['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()

    def test_code_update_never_copies_unchanged_runtime(self):
        self.make_code_archive()
        original=worker.shutil.copy2;copied=[]
        def record(a,b,*args,**kwargs):
            copied.append(str(a));return original(a,b,*args,**kwargs)
        with mock.patch.object(worker.shutil,'copy2',side_effect=record):self.assertTrue(self.run_worker())
        self.assertFalse(any('python.exe' in p or 'exiftool.exe' in p for p in copied))
        self.assertEqual((self.target/'resources/app.asar').read_bytes(),b'new asar')

    def test_code_base_mismatch_keeps_running_app_and_does_not_signal_ready(self):
        self.make_code_archive();(self.target/'resources/bin/windows-python/python.exe').write_bytes(b'changed runtime')
        self.assertFalse(self.run_worker());self.assertIn('BASE_MISMATCH',self.result()['error'])
        self.assertFalse(Path(self.config['ready']).exists());self.assertEqual(self.platform.launches,[])
        self.assertEqual((self.target/'Metadata Cleaner.exe').read_bytes(),b'old exe')

    def test_code_launch_failure_restores_code_and_leaves_runtime(self):
        self.make_code_archive();self.platform.mode='startup-fail'
        self.assertFalse(self.run_worker());self.assertEqual((self.target/'resources/app.asar').read_bytes(),b'old opaque asar')
        self.assertEqual((self.target/'resources/bin/windows-python/python.exe').read_bytes(),b'python fixture')
        self.assertEqual(self.platform.launches,[self.config['version'],'old'])

    def test_zip_updates_current_unicode_directory_without_running_installer(self):
        self.make_archive()
        uninstaller=self.target/'Uninstall Metadata Cleaner.exe'
        uninstaller.write_bytes(b'original uninstall')
        (self.target/'personal-note.txt').write_bytes(b'keep personal file')
        self.assertTrue(self.run_worker())
        self.assertEqual(self.platform.installations,0)
        self.assertEqual((self.target/'Metadata Cleaner.exe').read_bytes(),b'new exe')
        self.assertEqual(uninstaller.read_bytes(),b'original uninstall')
        self.assertEqual((self.target/'personal-note.txt').read_bytes(),b'keep personal file')
        self.assertEqual(self.result()['status'],'ok')

    def test_zip_startup_failure_restores_original_files_and_launches_old_app(self):
        self.make_archive()
        self.platform.mode='startup-fail'
        self.assertFalse(self.run_worker())
        self.assertEqual((self.target/'resources'/'app.asar').read_bytes(),b'old opaque asar')
        self.assertEqual(self.platform.launches,[self.config['version'],'old'])
        self.assertEqual(self.result()['stage'],'wait-for-startup-acknowledgement')

    def test_app_crash_after_acknowledgement_still_rolls_back(self):
        self.make_archive()
        self.platform.mode='startup-late-fail'
        self.assertFalse(self.run_worker())
        self.assertIn('42',self.result()['error'])
        self.assertEqual(self.platform.launches,[self.config['version'],'old'])
        self.assertEqual((self.target/'Metadata Cleaner.exe').read_bytes(),b'old exe')

    def test_archive_missing_windows_exiftool_is_rejected_before_ready(self):
        self.make_archive()
        artifact=Path(self.config['artifact']);missing='resources/app.asar.unpacked/node_modules/exiftool-vendored.exe/bin/exiftool.exe'
        with zipfile.ZipFile(artifact) as archive:entries={name:archive.read(name) for name in archive.namelist()}
        del entries['app/'+missing]
        marker=json.loads(entries['app/update-package.json']);del marker['files'][missing]
        entries['app/update-package.json']=json.dumps(marker).encode()
        with zipfile.ZipFile(artifact,'w') as archive:
            for name,data in entries.items():archive.writestr(name,data)
        self.config['size']=artifact.stat().st_size;self.config['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assertFalse(self.run_worker());self.assertIn('Required application file missing',self.result()['error'])
        self.assertFalse(Path(self.config['ready']).exists());self.assertEqual((self.target/'Metadata Cleaner.exe').read_bytes(),b'old exe')

    def test_zip_path_traversal_is_rejected_before_ready_or_overwrite(self):
        self.make_archive(unsafe='app/../../escaped.exe')
        self.assertFalse(self.run_worker())
        self.assertIn('Unsafe',self.result()['error'])
        self.assertFalse(Path(self.config['ready']).exists())
        self.assertEqual((self.target/'Metadata Cleaner.exe').read_bytes(),b'old exe')

    def test_zip_wrong_version_is_rejected_before_existing_app_changes(self):
        self.make_archive(version='9.9.9')
        self.assertFalse(self.run_worker())
        self.assertIn('identity/version',self.result()['error'])
        self.assertEqual(self.platform.launches,[])

    def test_zip_file_hash_mismatch_is_rejected(self):
        self.make_archive()
        artifact=Path(self.config['artifact'])
        with zipfile.ZipFile(artifact) as source:
            entries={name:source.read(name) for name in source.namelist()}
        entries['app/Metadata Cleaner.exe']=b'wrong exe'
        with zipfile.ZipFile(artifact,'w') as output:
            for name,data in entries.items():output.writestr(name,data)
        self.config['size']=artifact.stat().st_size
        self.config['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assertFalse(self.run_worker())
        self.assertIn('file integrity',self.result()['error'])
        self.assertFalse(Path(self.config['ready']).exists())

    def test_windows_launcher_is_independent_visible_and_clears_node_mode(self):
        class StartupInfo:
            def __init__(self):self.dwFlags=0;self.wShowWindow=0
        constants=dict(STARTUPINFO=StartupInfo,STARTF_USESHOWWINDOW=1,CREATE_NEW_PROCESS_GROUP=512,DETACHED_PROCESS=8)
        with mock.patch.multiple(worker.subprocess,create=True,**constants), mock.patch.object(worker.subprocess,'Popen') as popen, mock.patch.dict(os.environ,{'ELECTRON_RUN_AS_NODE':'1'}):
            worker.WindowsPlatform().launch(self.target/'Metadata Cleaner.exe','test-token')
            args,options=popen.call_args
            self.assertIn('--show-after-update',args[0])
            self.assertNotIn('ELECTRON_RUN_AS_NODE',options['env'])
            self.assertEqual(options['startupinfo'].wShowWindow,1)
            self.assertEqual(options['creationflags'],520)
            self.assertEqual(options['cwd'],str(self.target))

    def test_background_ready_ack_without_visible_window_succeeds(self):
        self.make_archive();self.config['background']=True
        self.assertTrue(self.run_worker());self.assertFalse(self.result()['visible']);self.assertTrue(self.result()['background'])

    def test_background_without_tray_readiness_rolls_back(self):
        self.make_archive();self.config['background']=True;self.platform.mode='missing-ready'
        self.assertFalse(self.run_worker());self.assertEqual((self.target/'resources/app.asar').read_bytes(),b'old opaque asar')
        self.assertEqual(self.platform.launches,[self.config['version'],'old'])

    def test_background_post_ack_crash_rolls_back(self):
        self.make_archive();self.config['background']=True;self.platform.mode='startup-late-fail'
        self.assertFalse(self.run_worker());self.assertIn('42',self.result()['error'])
        self.assertEqual(self.platform.launches,[self.config['version'],'old'])

    def test_background_launcher_passes_hidden_flag_and_preserves_detachment(self):
        class StartupInfo:
            def __init__(self):self.dwFlags=0;self.wShowWindow=1
        constants=dict(STARTUPINFO=StartupInfo,STARTF_USESHOWWINDOW=1,CREATE_NEW_PROCESS_GROUP=512,DETACHED_PROCESS=8)
        with mock.patch.multiple(worker.subprocess,create=True,**constants),mock.patch.object(worker.subprocess,'Popen') as popen:
            worker.WindowsPlatform(background=True).launch(self.target/'Metadata Cleaner.exe','test-token')
            args,options=popen.call_args
            self.assertIn('--background-after-update',args[0]);self.assertNotIn('--show-after-update',args[0]);self.assertEqual(options['startupinfo'].dwFlags & constants['STARTF_USESHOWWINDOW'],0);self.assertEqual(options['creationflags'],520)

    def test_nsis_destination_is_final_and_unquoted_even_with_spaces(self):
        command = worker.installer_command(r'C:\下载 空格\installer.exe', r'C:\应用 程序\净元')
        self.assertTrue(command.endswith(r' /D=C:\应用 程序\净元'))
        self.assertIn('/S /D=', command)


if __name__ == '__main__':
    unittest.main()
