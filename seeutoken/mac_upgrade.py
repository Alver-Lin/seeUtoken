"""Remove obsolete installed bundles and reconcile only this app's user registrations."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import tempfile
import time

APP_ID = 'com.seeutoken.desktop'
LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'


def bundle_info(app):
    try:
        with (Path(app) / 'Contents/Info.plist').open('rb') as stream:
            return plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {}


def version_key(value):
    value = str(value or '')
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}', value):
        return None
    parts = tuple(int(part) for part in value.split('.'))
    return parts + (0,) * (4 - len(parts))


def installed_info(canonical):
    canonical = Path(canonical)
    info = bundle_info(canonical)
    if canonical.is_symlink() or info.get('CFBundleIdentifier') != APP_ID or not version_key(info.get('CFBundleShortVersionString')):
        raise ValueError('A valid installed seeUtoken bundle is required before cleanup')
    return info


def registered_apps(dump):
    """Do not match another application's plist text mentioning seeUtoken."""
    records = []
    for block in re.split(r'\n-{20,}\n', dump):
        if not re.search(r'^identifier:\s+' + re.escape(APP_ID) + r'\s*$', block, re.M):
            continue
        path = re.search(r'^path:\s+(.+?) \(0x[0-9a-fA-F]+\)\s*$', block, re.M)
        version = re.search(r'^version:\s+(\S+)', block, re.M)
        if path and Path(path[1]).is_absolute():
            records.append((Path(path[1]), version_key(version[1]) if version else None))
    return records


def same_bundle(first, second):
    try:
        return first.samefile(second)
    except OSError:
        return first.resolve() == second.resolve()


def _running(executables):
    output = subprocess.check_output(['/bin/ps', '-ww', '-axo', 'pid=,comm='], text=True)
    pids = []
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1] in executables and int(parts[0]) != os.getpid():
            pids.append(int(parts[0]))
    return pids


def stop_old_apps(apps, timeout=20):
    executables = {str(app / 'Contents/MacOS/seeUtoken') for app in apps}
    if not executables:
        return
    for pid in _running(executables):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    while _running(executables):
        if time.monotonic() >= deadline:
            raise RuntimeError('An older seeUtoken copy is still running; it was not removed')
        time.sleep(.2)


def remove_older_installed_copies(directory, canonical):
    """Only standard application directories; never traverse user backups or Trash."""
    canonical, directory = Path(canonical), Path(directory)
    current = version_key(installed_info(canonical)['CFBundleShortVersionString'])
    if not directory.is_dir():
        return []
    candidates = []
    for app in directory.iterdir():
        if app.suffix.lower() != '.app' or app.is_symlink() or not app.is_dir() or same_bundle(app, canonical):
            continue
        info = bundle_info(app)
        version = version_key(info.get('CFBundleShortVersionString'))
        if info.get('CFBundleIdentifier') == APP_ID and version is not None and version < current:
            candidates.append(app)
    stop_old_apps(candidates)
    removed = []
    for app in candidates:
        # Revalidate after shutdown, before removing any bundle.
        info = bundle_info(app)
        version = version_key(info.get('CFBundleShortVersionString'))
        if not app.is_symlink() and not same_bundle(app, canonical) and info.get('CFBundleIdentifier') == APP_ID and version is not None and version < current:
            shutil.rmtree(app)
            removed.append(str(app))
    return removed


def cleanup_user(canonical, home=None):
    canonical, home = Path(canonical), Path(home or Path.home())
    info = installed_info(canonical)
    current = version_key(info['CFBundleShortVersionString'])
    report = {'version': info['CFBundleShortVersionString'], 'application': str(canonical),
              'inode': canonical.stat().st_ino, 'complete': False, 'removedApplications': [],
              'unregisteredCopies': []}
    report['removedApplications'] = remove_older_installed_copies(home / 'Applications', canonical)
    dump = subprocess.check_output([LSREGISTER, '-dump'], text=True)
    for path, registered_version in registered_apps(dump):
        if same_bundle(path, canonical):
            continue
        actual = bundle_info(path)
        if actual:
            version = version_key(actual.get('CFBundleShortVersionString'))
            if actual.get('CFBundleIdentifier') != APP_ID or version is None or version > current:
                continue
            if version < current:
                stop_old_apps([path])
        else:
            if registered_version is not None and registered_version > current:
                continue
            if home / '.Trash' not in path.parents:
                try:
                    live = path.exists()
                except OSError:
                    live = True
                if live:
                    # Do not change unreadable or unrelated live bundles.
                    continue
        # Missing paths, Trash entries, old mounted DMGs and duplicate build
        # bundles must not remain discoverable as additional installed apps.
        subprocess.run([LSREGISTER, '-u', str(path)], capture_output=True, text=True)
        report['unregisteredCopies'].append(str(path))
    subprocess.run([LSREGISTER, '-f', str(canonical)], check=True, capture_output=True, text=True)
    remaining = {str(path) for path, _ in registered_apps(subprocess.check_output([LSREGISTER, '-dump'], text=True))}
    if remaining.intersection(report['unregisteredCopies']):
        raise RuntimeError('Some duplicate registrations remain; cleanup will retry on first launch')
    report['complete'] = True
    destination = home / '.config/seeUtoken/upgrade-state.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False, encoding='utf-8') as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, ensure_ascii=False)
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return report


def ensure_user_cleanup(canonical):
    """Fallback on first launch when installation happened without a GUI user."""
    canonical = Path(canonical)
    try:
        info = installed_info(canonical)
        state_path = Path.home() / '.config/seeUtoken/upgrade-state.json'
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        if (state.get('complete') and state.get('version') == info['CFBundleShortVersionString']
                and state.get('application') == str(canonical) and state.get('inode') == canonical.stat().st_ino):
            return
        cleanup_user(canonical)
    except Exception:
        logging.exception('Unable to finish seeUtoken application registration cleanup')


def main(action, canonical):
    if action == '--cleanup-system-apps':
        removed = remove_older_installed_copies('/Applications', canonical)
        print(json.dumps({'removedApplications': removed}))
    elif action == '--complete-upgrade':
        print(json.dumps(cleanup_user(canonical), ensure_ascii=False))
    else:
        raise ValueError('Unknown upgrade cleanup action')
    return 0
