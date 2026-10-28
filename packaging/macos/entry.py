"""Finder entry point for the packaged application."""
from multiprocessing import freeze_support

if __name__ == '__main__':
    freeze_support()
    from seeutoken.app import main
    main()
