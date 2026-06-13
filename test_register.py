"""Smoke test: register and unregister alecs_toolbox in Blender background.

Run from repo root:
  blender --background --python test_register.py

Or with full path to Blender 5.1 on Windows.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ADDON_ROOT = Path(__file__).resolve().parent
ADDON_PARENT = ADDON_ROOT.parent

if str(ADDON_PARENT) not in sys.path:
    sys.path.insert(0, str(ADDON_PARENT))


def main() -> int:
    import alecs_toolbox

    print(f"Testing {alecs_toolbox.__name__} from {ADDON_ROOT}")

    try:
        alecs_toolbox.register()
        print("  register() OK")
    except Exception:
        print("  register() FAILED")
        traceback.print_exc()
        return 1

    try:
        alecs_toolbox.unregister()
        print("  unregister() OK")
    except Exception:
        print("  unregister() FAILED")
        traceback.print_exc()
        return 1

    print("OK: alecs_toolbox register/unregister smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
