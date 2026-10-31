"""Finder entry point for the packaged application."""
from multiprocessing import freeze_support

if __name__ == '__main__':
    freeze_support()
    import sys
    from pathlib import Path
    import threading
    from seeutoken.mac_upgrade import main as complete_upgrade, ensure_user_cleanup

    canonical = Path(sys.executable).parents[2]
    installed = canonical == Path('/Applications/seeUtoken.app')
    if len(sys.argv) == 2 and sys.argv[1] in ('--cleanup-system-apps', '--complete-upgrade'):
        if not installed:
            raise SystemExit('Upgrade cleanup requires the installed /Applications/seeUtoken.app')
        raise SystemExit(complete_upgrade(sys.argv[1], canonical))
    if installed:
        threading.Thread(target=ensure_user_cleanup, args=(canonical,), daemon=True).start()
    from seeutoken.app import main
    main()
