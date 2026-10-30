"""Packaging values shared by both platforms; the Python version is authoritative."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
module = ast.parse((ROOT / 'seeutoken' / '__init__.py').read_text())
VERSION = next(ast.literal_eval(node.value) for node in module.body
               if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))
VERSION_PARTS = tuple(int(part) for part in VERSION.split('.'))
assert len(VERSION_PARTS) == 3 and all(0 <= part <= 65535 for part in VERSION_PARTS)
APP_ID = 'com.seeutoken.desktop'

if __name__ == '__main__':
    print(VERSION)
