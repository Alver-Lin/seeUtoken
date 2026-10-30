"""Windows GUI entry: persistent logs, a single instance and useful startup errors."""
from __future__ import annotations

import ctypes
import logging
from logging.handlers import RotatingFileHandler
import sys

from .storage import settings_path


def smoke_test(report):
    """Exercise the frozen CLR/WebView2/JavaScript bridge on a Windows runner."""
    import json
    import threading
    from pathlib import Path
    import pystray
    import psutil
    import webview
    from . import __version__
    from .app import UI, ASSETS
    from .windows_float import apply_sidebar, hide_from_taskbar, taskbar_hidden

    report = Path(report)
    result = {'ok': False, 'version': __version__}
    for resource in (UI / 'panels' / 'index.html', UI / 'assets' / 'panels.js', ASSETS / 'icon.ico'):
        if not resource.is_file():
            raise RuntimeError(f'Missing bundled resource: {resource.name}')
    window = webview.create_window('seeUtoken build check', html='<html><body>Windows build check</body></html>',
                                   width=300, height=200, frameless=True, hidden=True)
    window.events.before_show += hide_from_taskbar

    def loaded():
        def check():
            try:
                result['javascript'] = window.evaluate_js('6 * 7')
                apply_sidebar(window, 'liquid-light-clear', {
                    'width': 300, 'height': 200,
                    'commands': [['M', 10, 10], ['L', 200, 10],
                                 ['C', 220, 10, 220, 50, 200, 50], ['L', 10, 50], ['Z']],
                })
                result['windowRegion'] = window.native.Region is not None
                result['sidebarTaskbarHidden'] = taskbar_hidden(window)
                result['ok'] = result['javascript'] == 42 and result['windowRegion'] and result['sidebarTaskbarHidden']
            except Exception as exc:
                result['error'] = str(exc)
            finally:
                report.write_text(json.dumps(result), encoding='utf-8')
                window.destroy()
        threading.Thread(target=check, daemon=True).start()

    window.events.loaded += loaded
    try:
        webview.start(gui='edgechromium', private_mode=True, storage_path=str(report.parent / 'webview2'))
    except Exception as exc:
        result['error'] = str(exc)
        report.write_text(json.dumps(result), encoding='utf-8')
    return 0 if result['ok'] else 1


def _acquire_instance():
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, r'Local\seeUtoken.Desktop')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle(handle)
        return None
    return handle


def main():
    from ctypes import wintypes

    folder = settings_path().parent
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / 'seeUtoken.log'
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
        log, maxBytes=2_000_000, backupCount=2, encoding='utf-8')],
        format='%(asctime)s %(levelname)s %(message)s', force=True)
    # PyInstaller --windowed sets these streams to None. Some dependencies print.
    stream = log.open('a', encoding='utf-8', buffering=1)
    previous_streams = sys.stdout, sys.stderr
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    mutex = None
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('seeUtoken.Desktop')
        mutex = _acquire_instance()
        if mutex is None:
            ctypes.windll.user32.MessageBoxW(None, 'seeUtoken 已在运行，请从系统托盘打开主窗口。', 'seeUtoken', 0x40)
            return 0
        from .app import main as app_main
        app_main()
        return 0
    except Exception:
        logging.exception('seeUtoken startup failed')
        ctypes.windll.user32.MessageBoxW(None,
            'seeUtoken 启动失败。请确认已安装 Microsoft Edge WebView2 Runtime 和 .NET Framework 4.8。\n'
            'WebView2 下载：https://developer.microsoft.com/microsoft-edge/webview2/\n\n'
            f'诊断日志：{log}', 'seeUtoken', 0x10)
        return 1
    finally:
        if mutex is not None:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle(mutex)
        sys.stdout, sys.stderr = previous_streams
        stream.close()
