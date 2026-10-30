"""Run the finished EXE in an isolated user-data directory and verify a real WebView."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
exe = ROOT / 'dist' / 'seeUtoken-V1.0.2.exe'
with exe.open('rb') as stream:
    assert stream.read(2) == b'MZ', 'The artifact is not a Windows executable'
    stream.seek(0x3C)
    pe_offset = struct.unpack('<I', stream.read(4))[0]
    stream.seek(pe_offset)
    assert stream.read(4) == b'PE\x00\x00', 'Invalid PE header'
    assert struct.unpack('<H', stream.read(2))[0] == 0x8664, 'Expected a Windows x64 EXE'
with tempfile.TemporaryDirectory(prefix='seeutoken-smoke-') as folder:
    report = Path(folder) / 'report.json'
    env = {**os.environ, 'APPDATA': folder, 'LOCALAPPDATA': folder,
           'CODEX_HOME': str(Path(folder) / 'codex')}
    process = subprocess.Popen([str(exe), '--smoke-test', str(report)], env=env)
    try:
        code = process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False, capture_output=True)
        raise RuntimeError('Frozen WebView2 application did not finish its startup check')
    result = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
    assert code == 0 and result.get('ok'), f'Frozen startup check failed: code={code}, report={result}'
    print(json.dumps(result, ensure_ascii=False))
