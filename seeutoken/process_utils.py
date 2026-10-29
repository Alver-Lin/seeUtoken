"""Subprocess defaults for background helpers in the Windows GUI application."""
import subprocess
import sys


def background_process_options():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
