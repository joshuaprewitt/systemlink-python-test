"""Move all B0CG1KL3RD work items and test results to the
'NI Connect 2026 - SystemLink Hands On' workspace.

Queries every accessible workspace for work items whose partNumber is
B0CG1KL3RD and test results whose part_number is B0CG1KL3RD, then
updates any that are not already in the target workspace.

Usage:
    python migrate_workspace_B0CG1KL3RD.py --server <URL> --api-key <KEY>
"""

import argparse
import logging
import sys

from nisystemlink.clients.core import HttpConfiguration
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import (
    QueryResultsRequest,
    UpdateResultRequest,
)
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    QueryWorkItemsRequest,
    UpdateWorkItemRequest,
    UpdateWorkItemsRequest,
)

from config import get_configuration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PART_NUMBER = "B0CG1KL3RD"
TARGET_WORKSPACE = "26f50ba0-f249-4aaf-99b3-96b7a5afd75c"  # NI Connect 2026 - SystemLink Hands On


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Migrate all {PART_NUMBER} data to the NI Connect 2026 - SystemLink Hands On workspace"
    )
    parser.add_argument("--server", help="SystemLink server URI. For dev use.")
    parser.add_argument("--api-key", help="SystemLink API key. For dev use.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be changed without making any updates.",
    )
    return parser.parse_args()


def migrate_work_items(wi_client: WorkItemClient, dry_run: bool) -> int:
    """Find and move all B0CG1KL3RD work items not in the target workspace."""
    logger.info("Querying work items for part number %s ...", PART_NUMBER)

    # Page through all work items matching the part number
    wrong = []
    continuation_token = None
    take = 200
    while True:
        response = wi_client.query_work_items(
            QueryWorkItemsRequest(
                filter=f'partNumber == "{PART_NUMBER}"',
                take=take,
                continuation_token=continuation_token,
            )
        )
        items = response.work_items or []
        for item in items:
            if item.workspace != TARGET_WORKSPACE:
                wrong.append(item)
        continuation_token = response.continuation_token
        if not continuation_token:
            break

    logger.info(
        "Found %d work item(s) for %s not in target workspace", len(wrong), PART_NUMBER
    )
    if not wrong:
        return 0

    for item in wrong:
        logger.info(
            "  Work item %s  workspace=%s  name=%s",
            item.id, item.workspace, item.name,
        )

    if dry_run:
        logger.info("[DRY RUN] Would update %d work items", len(wrong))
        return 0

    # Batch update workspace — chunk to 100 to be safe
    requests = [
        UpdateWorkItemRequest(id=item.id, workspace=TARGET_WORKSPACE)
        for item in wrong
    ]
    updated = 0
    for chunk_start in range(0, len(requests), 100):
        chunk = requests[chunk_start:chunk_start + 100]
        resp = wi_client.update_work_items(UpdateWorkItemsRequest(work_items=chunk))
        succeeded = len(resp.updated_work_items or [])
        failed = resp.failed_work_items or []
        updated += succeeded
        for f in failed:
            logger.error("Failed to update work item: %s", f)

    logger.info("Updated %d/%d work items -> target workspace", updated, len(wrong))
    return len(wrong) - updated  # return number of failures


def migrate_results(tm_client: TestMonitorClient, dry_run: bool) -> int:
    """Find and move all B0CG1KL3RD test results not in the target workspace."""
    logger.info("Querying test results for part number %s ...", PART_NUMBER)

    wrong = []
    continuation_token = None
    while True:
        response = tm_client.query_results(
            QueryResultsRequest(
                filter=f'partNumber == "{PART_NUMBER}"',
                take=500,
                continuation_token=continuation_token,
            )
        )
        results = response.results or []
        for r in results:
            if r.workspace != TARGET_WORKSPACE:
                wrong.append(r)
        continuation_token = response.continuation_token
        if not continuation_token:
            break

    logger.info(
        "Found %d result(s) for %s not in target workspace", len(wrong), PART_NUMBER
    )
    if not wrong:
        return 0

    for r in wrong:
        logger.info(
            "  Result %s  workspace=%s  serial=%s",
            r.id, r.workspace, r.serial_number,
        )

    if dry_run:
        logger.info("[DRY RUN] Would update %d results", len(wrong))
        return 0

    # Batch update workspace — chunk to 100 to be safe
    # update_results(results: List[UpdateResultRequest], replace: bool)
    requests = [
        UpdateResultRequest(id=r.id, workspace=TARGET_WORKSPACE)
        for r in wrong
    ]
    updated = 0
    for chunk_start in range(0, len(requests), 100):
        chunk = requests[chunk_start:chunk_start + 100]
        resp = tm_client.update_results(chunk)
        succeeded = len(resp.results or [])
        failed = resp.failed or []
        updated += succeeded
        for f in failed:
            logger.error("Failed to update result: %s", f)

    logger.info("Updated %d/%d results -> target workspace", updated, len(wrong))
    return len(wrong) - updated


def main() -> int:
    args = _parse_args()
    configuration = get_configuration(server=args.server, api_key=args.api_key)

    wi_client = WorkItemClient(configuration)
    tm_client = TestMonitorClient(configuration)

    if args.dry_run:
        logger.info("=== DRY RUN — no changes will be made ===")

    wi_failures = migrate_work_items(wi_client, args.dry_run)
    result_failures = migrate_results(tm_client, args.dry_run)

    print("\n" + "=" * 60)
    print(f"Migration complete for {PART_NUMBER}")
    print(f"  Target workspace: NI Connect 2026 - SystemLink Hands On ({TARGET_WORKSPACE})")
    if wi_failures or result_failures:
        print(f"  Work item failures : {wi_failures}")
        print(f"  Result failures    : {result_failures}")
        return 1
    else:
        print("  All data is now in the target workspace.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
