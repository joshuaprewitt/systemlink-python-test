"""Battery 18650 Test — SystemLink-integrated test application.

Usage:
    # Automated mode (for remote execution from SystemLink):
    python main.py --work-item-id <WORK_ITEM_ID>

    # Interactive mode (prompts for work item ID and confirmation):
    python main.py

    # Developer mode (non-managed system, pass slcli credentials):
    python main.py --work-item-id <ID> --server <URL> --api-key <KEY>
"""

import argparse
import logging
import sys

from config import PROGRAM_NAME, get_configuration
from initialization import initialize
from execution import run_test

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"{PROGRAM_NAME} — 18650 Battery Cell Test (SystemLink-integrated)",
    )
    parser.add_argument(
        "--work-item-id",
        help="SystemLink work item ID. If omitted, prompts interactively.",
    )
    parser.add_argument(
        "--server",
        help="SystemLink server URI (e.g. https://myserver.com). For dev use.",
    )
    parser.add_argument(
        "--api-key",
        help="SystemLink API key. For dev use.",
    )
    args = parser.parse_args()

    interactive = args.work_item_id is None
    work_item_id = args.work_item_id

    if interactive:
        work_item_id = input("Enter Work Item ID: ").strip()
        if not work_item_id:
            logger.error("No work item ID provided")
            return 1

    configuration = get_configuration(server=args.server, api_key=args.api_key)

    try:
        logger.info("Initializing test for work item %s", work_item_id)
        ctx = initialize(configuration, work_item_id, interactive=interactive)

        logger.info("Starting test execution")
        result_id = run_test(configuration, ctx)

        logger.info("Test complete — result ID: %s", result_id)
        print(f"\nResult: {result_id}")
        return 0

    except Exception:
        logger.exception("Test execution failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
