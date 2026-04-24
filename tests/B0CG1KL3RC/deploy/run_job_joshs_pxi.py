"""Compatibility wrapper for legacy Josh's PXI state apply command.

Equivalent modern command:
  python ops.py apply-state --alias "Josh's PXI" --state-id 69e23b7aaf1edbfc5fdc4697
"""

import sys

from ops import main

STATE_ID = '69e23b7aaf1edbfc5fdc4697'
TARGET_ALIAS = "Josh's PXI"


if __name__ == '__main__':
    sys.argv = [
        sys.argv[0],
        'apply-state',
        '--alias',
        TARGET_ALIAS,
        '--state-id',
        STATE_ID,
        *sys.argv[1:],
    ]
    raise SystemExit(main())
