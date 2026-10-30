"""Gracefully close verified, same-user app instances before the installer copies files."""
from __future__ import annotations

import ctypes
from pathlib import Path, PureWindowsPath
import re

APP_EXECUTABLE = re.compile(r'seeutoken(?:-v\d+\.\d+\.\d+)?\.exe', re.IGNORECASE)


def executable_identity(executable):
    """Read version resources; a filename alone is insufficient to select a process."""
    from ctypes import wintypes

    version = ctypes.WinDLL('version', use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR,
                                     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT))
    version.VerQueryValueW.restype = wintypes.BOOL
    size = version.GetFileVersionInfoSizeW(str(executable), None)
    if not size:
        return {}
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(executable), 0, size, buffer):
        return {}
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not version.VerQueryValueW(buffer, r'\VarFileInfo\Translation', ctypes.byref(pointer), ctypes.byref(length)) or length.value < 4:
        return {}
    translation = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort))
    prefix = f'\\StringFileInfo\\{translation[0]:04x}{translation[1]:04x}\\'
    result = {}
    for key in ('ProductName', 'FileDescription'):
        if version.VerQueryValueW(buffer, prefix + key, ctypes.byref(pointer), ctypes.byref(length)) and length.value:
            result[key] = ctypes.wstring_at(pointer.value, length.value - 1)
    return result


def close_windows(pids):
    from ctypes import wintypes

    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user.EnumWindows.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    @callback_type
    def close(handle, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value in pids:
            user.PostMessageW(handle, 0x0010, 0, 0)  # WM_CLOSE uses the app's normal shutdown.
        return True

    if not user.EnumWindows(close, 0):
        raise ctypes.WinError(ctypes.get_last_error())


def prepare_upgrade(process_api=None, identity=None, close=None, timeout=20):
    if process_api is None:
        import psutil as process_api
    identity = identity or executable_identity
    close = close or close_windows
    current = process_api.Process()
    username = current.username().casefold()
    excluded = {current.pid, *(parent.pid for parent in current.parents())}
    candidates = []
    for process in process_api.process_iter(['pid', 'exe', 'username']):
        data = process.info
        executable = data.get('exe') or ''
        if (data['pid'] in excluded or (data.get('username') or '').casefold() != username
                or not APP_EXECUTABLE.fullmatch(PureWindowsPath(executable).name)):
            continue
        try:
            info = identity(executable)
            if info.get('ProductName') == 'seeUtoken' and info.get('FileDescription') == 'seeUtoken AI usage monitor':
                candidates.append(process)
        except OSError:
            continue
    if candidates:
        close({process.pid for process in candidates})
        _, alive = process_api.wait_procs(candidates, timeout=timeout)
        if alive:
            raise RuntimeError('Please quit seeUtoken before upgrading. The existing installation is unchanged.')
    return {'ok': True, 'closedProcesses': len(candidates)}


def main(report):
    import json

    try:
        result = prepare_upgrade()
    except Exception as exc:
        result = {'ok': False, 'error': str(exc)}
    Path(report).write_text(json.dumps(result), encoding='utf-8')
    return 0 if result['ok'] else 1
