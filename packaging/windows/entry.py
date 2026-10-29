"""Entry point for the single-file Windows application."""
from multiprocessing import freeze_support

if __name__ == '__main__':
    freeze_support()
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from seeutoken.windows_runtime import smoke_test
        raise SystemExit(smoke_test(sys.argv[2]))
    from seeutoken.windows_runtime import main
    raise SystemExit(main())
