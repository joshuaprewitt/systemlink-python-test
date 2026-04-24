"""Compatibility wrapper for package install.

Prefer using ops.py directly:
  python ops.py install-package --version <VERSION>
"""

import sys

from ops import main


if __name__ == '__main__':
    sys.argv = [sys.argv[0], 'install-package', *sys.argv[1:]]
    raise SystemExit(main())
