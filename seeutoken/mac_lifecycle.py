"""Integrate Dock reopen and Quit with pywebview's shared AppKit loop."""

from __future__ import annotations

_delegate_class = None


def install_app_delegate(on_reopen, on_quit):
    """Call on the AppKit thread after pywebview has created its windows."""
    from webview.platforms.cocoa import BrowserView

    global _delegate_class
    if _delegate_class is None:
        class SeeUtokenAppDelegate(BrowserView.AppDelegate):
            def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
                # The floating sidebar counts as a visible window, even when
                # the main window is minimized. Always restore the main one.
                self.on_reopen()
                return False

            def applicationShouldTerminate_(self, app):
                # Let pywebview close every window before stopping its loop.
                self.on_quit()
                return 0  # NSTerminateCancel

        _delegate_class = SeeUtokenAppDelegate

    delegate = _delegate_class.alloc().init()
    delegate.on_reopen = on_reopen
    delegate.on_quit = on_quit
    # New pywebview windows (including login) reuse this delegate.
    BrowserView._shared_app_delegate = delegate
    BrowserView.app.setDelegate_(delegate)
    return delegate
