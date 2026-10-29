"""Entry point for the single-file Windows application."""
from multiprocessing import freeze_support

if __name__ == '__main__':
    freeze_support()
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        try:
            from seeutoken.windows_runtime import smoke_test
            result = smoke_test(sys.argv[2])
        except Exception:
            import json
            from pathlib import Path
            import traceback
            Path(sys.argv[2]).write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}), encoding='utf-8')
            result = 1
        raise SystemExit(result)
    from seeutoken.windows_runtime import main
    raise SystemExit(main())
