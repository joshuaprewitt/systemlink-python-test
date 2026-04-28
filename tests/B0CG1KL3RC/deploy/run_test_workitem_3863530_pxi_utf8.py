"""Compatibility wrapper for legacy PYTHONUTF8=1 run command.

Equivalent modern command:
  python ops.py run-test --alias "NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1" --work-item-id 3863530 --cmd-prefix "set PYTHONUTF8=1"
"""

import sys

from ops import main

TARGET = 'NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1'
WORK_ITEM_ID = '3863530'


if __name__ == '__main__':
    sys.argv = [
        sys.argv[0],
        'run-test',
        '--alias',
        TARGET,
        '--work-item-id',
        WORK_ITEM_ID,
        '--cmd-prefix',
        'set PYTHONUTF8=1',
        *sys.argv[1:],
    ]
    raise SystemExit(main())
