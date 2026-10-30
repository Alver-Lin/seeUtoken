"""Real installer migration/reinstall test. Only run on a disposable GitHub Windows runner."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import winreg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from seeutoken.windows_upgrade import executable_identity
VERSION = runpy.run_path(str(ROOT / 'packaging' / 'metadata.py'))['VERSION']
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\com.seeutoken.desktop_is1'


def wait_for(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.1)
    raise RuntimeError('Timed out waiting for the test application')


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Installer integration tests require a disposable GitHub Actions runner')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
    installer = ROOT / 'dist' / f'seeUtoken-V{VERSION}.exe'
    expected_hash = hashlib.sha256((ROOT / 'build/windows/app/seeUtoken.exe').read_bytes()).digest()
    with tempfile.TemporaryDirectory(prefix='seeutoken-upgrade-') as folder:
        folder = Path(folder)
        target = folder / 'installed'
        target.mkdir()
        data = folder / 'user-data' / 'seeUtoken'
        data.mkdir(parents=True)
        settings = data / 'settings.json'
        cache = data / 'usage_cache.json'
        settings.write_text(json.dumps({'upgrade-test': 'keep-settings'}))
        cache.write_text(json.dumps({'upgrade-test': 'keep-usage'}))
        before = settings.read_bytes(), cache.read_bytes()
        env = {**os.environ, 'APPDATA': str(data.parent)}
        ready = folder / 'ready'
        source = folder / 'Legacy.cs'
        source.write_text('''using System;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
[assembly: AssemblyProduct("seeUtoken")]
[assembly: AssemblyDescription("seeUtoken AI usage monitor")]
[assembly: AssemblyTitle("seeUtoken AI usage monitor")]
[assembly: AssemblyFileVersion("1.0.1.0")]
class Legacy {
  [STAThread] static void Main(string[] args) {
    using (var mutex = new Mutex(false, @"Local\\seeUtoken.Desktop")) {
      var form = new Form();
      form.Text = "seeUtoken upgrade test";
      form.Shown += delegate { File.WriteAllText(args[0], "ready"); };
      Application.Run(form);
    }
  }
}''')
        binary = target / 'seeUtoken.exe'
        subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64',
                        '/reference:System.Windows.Forms.dll', '/out:' + str(binary), str(source)], check=True)
        assert executable_identity(binary) == {
            'ProductName': 'seeUtoken', 'FileDescription': 'seeUtoken AI usage monitor',
        }, 'Legacy fixture must have the same version resources as v1.0.1'
        legacy = target / 'seeUtoken-V1.0.1.exe'
        shutil.copyfile(binary, legacy)
        processes = []
        def install():
            log = folder / 'installer.log'
            try:
                subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                                '/DIR=' + str(target), '/LOG=' + str(log)],
                               check=True, timeout=180, env=env)
            except Exception:
                if log.exists():
                    print(log.read_text(encoding='utf-8-sig', errors='replace'), flush=True)
                raise
            assert hashlib.sha256(binary.read_bytes()).digest() == expected_hash
            assert (settings.read_bytes(), cache.read_bytes()) == before
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
                assert winreg.QueryValueEx(key, 'DisplayVersion')[0] == VERSION
                assert Path(winreg.QueryValueEx(key, 'InstallLocation')[0]) == target
        try:
            # A portable 1.0.1 in Downloads is also closed, but is not deleted.
            portable = folder / 'Downloads' / 'seeUtoken-V1.0.1.exe'
            portable.parent.mkdir()
            shutil.copyfile(binary, portable)
            for index, exe in enumerate((binary, portable)):
                flag = ready.with_name('ready-' + str(index))
                processes.append(subprocess.Popen([str(exe), str(flag)], env=env))
                wait_for(flag.exists)
            install()
            for process in processes:
                process.wait(timeout=10)
            assert not legacy.exists(), 'Managed version-named executable was left behind'
            assert portable.exists(), 'A file outside the installation was deleted'
            # Reinstalling the same version must replace the payload as well.
            binary.write_bytes(b'replace this stale same-version payload')
            install()
            shortcut = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/seeUtoken.lnk'
            assert shortcut.is_file(), 'Stable Start Menu shortcut missing'
            print('PASS: running 1.0.1 -> 1.0.2, portable migration, same-version replacement, registry, shortcuts, user data')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            uninstaller = target / 'unins000.exe'
            if uninstaller.exists():
                subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                               env=env, check=True, timeout=120)
                wait_for(lambda: not binary.exists())
                assert (settings.read_bytes(), cache.read_bytes()) == before


if __name__ == '__main__':
    main()
