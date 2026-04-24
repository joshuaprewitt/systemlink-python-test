"""Compatibility wrapper for legacy state apply command.

Equivalent modern command:
  python ops.py apply-state --state-id 69e23b7aaf1edbfc5fdc4697
"""

import sys

from ops import main

STATE_ID = '69e23b7aaf1edbfc5fdc4697'


if __name__ == '__main__':
    sys.argv = [
        sys.argv[0],
        'apply-state',
        '--state-id',
        STATE_ID,
        *sys.argv[1:],
    ]
    raise SystemExit(main())
