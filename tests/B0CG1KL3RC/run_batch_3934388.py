"""Batch runner: 10 DUTs (serial 1234–1243) across multiple temperatures.

Creates one work item per DUT under test plan 3934388, then runs the full
battery test for each, publishing results to SystemLink.

Usage:
    python run_batch_3934388.py --server <URL> --api-key <KEY>

Environment variables SYSTEMLINK_SERVER_URI / SYSTEMLINK_API_KEY are also
accepted as an alternative to CLI flags.
"""

import argparse
import logging
import sys

from nisystemlink.clients.assetmanagement import AssetManagementClient
from nisystemlink.clients.assetmanagement.models import QueryAssetsRequest
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    CreateWorkItemRequest,
    ResourceDefinition,
    ResourceSelectionDefinition,
    ResourcesDefinition,
)

from config import PART_NUMBER, PROGRAM_NAME, get_configuration
from execution import run_test
from initialization import initialize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TEST_PLAN_ID = "3934388"

# 10 DUTs: serial 1234 – 1243
SERIALS = [str(n) for n in range(1234, 1244)]

# Temperature assigned to each DUT (round-robin across the 6 test conditions).
# Results in: -25, 0, 15, 25, 35, 45, -25, 0, 15, 25 °C
_TEMPS = [-25, 0, 15, 25, 35, 45]
DUT_TEMPS = [_TEMPS[i % len(_TEMPS)] for i in range(len(SERIALS))]


def _resolve_dut_ids(
    asset_client: AssetManagementClient,
    serials: list[str],
    part_number: str,
) -> dict[str, str]:
    """Return {serial: asset_id} for DUT assets matching *part_number*.

    Filters by ``modelName == part_number`` (exact) and the serial numbers
    in *serials*. Logs a warning for any serial with no match.
    """
    serial_filter = " || ".join(f'serialNumber == "{s}"' for s in serials)
    result = asset_client.query_assets(
        QueryAssetsRequest(
            filter=f'modelName == "{part_number}" && ({serial_filter})',
            take=len(serials) + 10,
        )
    )

    mapping: dict[str, str] = {}
    for asset in result.assets:
        if asset.serial_number and asset.id:
            mapping[asset.serial_number] = asset.id
            logger.info(
                "Resolved DUT: serial=%s -> asset_id=%s (%s)",
                asset.serial_number, asset.id, asset.name,
            )

    for serial in serials:
        if serial not in mapping:
            logger.warning("No DUT asset found for serial=%s (part=%s)", serial, part_number)

    return mapping


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{PROGRAM_NAME} — batch run (test plan {TEST_PLAN_ID})"
    )
    parser.add_argument("--server", help="SystemLink server URI. For dev use.")
    parser.add_argument("--api-key", help="SystemLink API key. For dev use.")
    return parser.parse_args()


def _create_work_items(
    wi_client: WorkItemClient,
    workspace: str | None,
    dut_ids: dict[str, str],
) -> list[tuple[str, str, float]]:
    """Create one work item per DUT and return [(work_item_id, serial, temp_c), ...]."""
    requests = [
        CreateWorkItemRequest(
            name=f"18650 Battery Test — SN {serial} @ {temp:+.0f}°C",
            type="testplan",
            state="DEFINED",
            parent_id=TEST_PLAN_ID,
            part_number=PART_NUMBER,
            test_program=PROGRAM_NAME,
            workspace=workspace,
            workflow_id="422815",
            resources=ResourcesDefinition(
                duts=ResourceDefinition(
                    selections=[
                        ResourceSelectionDefinition(id=dut_ids[serial])
                    ] if serial in dut_ids else [],
                )
            ),
            properties={
                "serialNumber": serial,
                "ambient_temp_c": str(float(temp)),
                "test_profile": "standard",
                "charge_rate_a": "1.0",
            },
        )
        for serial, temp in zip(SERIALS, DUT_TEMPS)
    ]

    response = wi_client.create_work_items(requests)

    created = []
    for item in response.created_work_items or []:
        # Find matching serial via properties
        serial = (item.properties or {}).get("serialNumber", "UNKNOWN")
        temp = float((item.properties or {}).get("ambient_temp_c", "25"))
        created.append((item.id, serial, temp))
        logger.info("Created work item %s  serial=%s  temp=%.0f°C", item.id, serial, temp)

    for err in response.failed_work_items or []:
        logger.error("Failed to create work item: %s", err)

    return created


def _get_plan_workspace(wi_client: WorkItemClient) -> str | None:
    """Return the workspace of the test plan so new work items inherit it."""
    try:
        plan = wi_client.get_work_item(TEST_PLAN_ID)
        return plan.workspace
    except Exception:
        logger.warning("Could not fetch test plan %s — workspace will be omitted", TEST_PLAN_ID)
        return None


def main() -> int:
    args = _parse_args()
    configuration = get_configuration(server=args.server, api_key=args.api_key)

    wi_client = WorkItemClient(configuration)

    logger.info("Fetching workspace from test plan %s", TEST_PLAN_ID)
    workspace = _get_plan_workspace(wi_client)

    asset_client = AssetManagementClient(configuration)
    logger.info("Resolving DUT assets for part number %s", PART_NUMBER)
    dut_ids = _resolve_dut_ids(asset_client, SERIALS, PART_NUMBER)

    logger.info("Creating %d work items under test plan %s", len(SERIALS), TEST_PLAN_ID)
    dut_items = _create_work_items(wi_client, workspace, dut_ids)

    if not dut_items:
        logger.error("No work items were created — aborting")
        return 1

    results: list[tuple[str, str, float, str | None]] = []  # (serial, wi_id, temp, result_id|None)
    for wi_id, serial, temp_c in dut_items:
        logger.info(
            "=== Running test: serial=%s  temp=%.0f°C  work_item=%s ===",
            serial, temp_c, wi_id,
        )
        result_id = None
        try:
            ctx = initialize(configuration, wi_id, interactive=False)
            result_id = run_test(configuration, ctx)
            logger.info("Finished serial=%s -> result %s", serial, result_id)
        except Exception:
            logger.exception("Test failed for serial=%s (work_item=%s)", serial, wi_id)
        results.append((serial, wi_id, temp_c, result_id))

    # --- Summary ---
    print("\n" + "=" * 60)
    print(f"Batch complete — test plan {TEST_PLAN_ID}")
    print("=" * 60)
    passed = sum(1 for *_, r in results if r is not None)
    print(f"{'Serial':<12} {'Temp (°C)':<12} {'Work Item':<20} {'Result ID'}")
    print("-" * 60)
    for serial, wi_id, temp_c, result_id in results:
        status = result_id if result_id else "FAILED (see logs)"
        print(f"{serial:<12} {temp_c:<12.0f} {wi_id:<20} {status}")
    print("-" * 60)
    print(f"{passed}/{len(results)} tests completed successfully")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
