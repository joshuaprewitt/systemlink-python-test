"""Batch runner: 5 DUTs × 4 temperatures = 20 runs for product B0CG1KL3RD.

Creates one work item per (DUT, temperature) combination under a given test plan,
then runs the full battery test for each, publishing results to SystemLink.

Usage:
    python run_batch_B0CG1KL3RD.py --test-plan-id <ID> --server <URL> --api-key <KEY>

Environment variables SYSTEMLINK_SERVER_URI / SYSTEMLINK_API_KEY are also
accepted as an alternative to CLI flags.
"""

import argparse
import json
import logging
import ssl
import sys
import urllib.request

from nisystemlink.clients.assetmanagement import AssetManagementClient
from nisystemlink.clients.assetmanagement.models import QueryAssetsRequest
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    CreateWorkItemRequest,
    ResourceDefinition,
    ResourceSelectionDefinition,
    ResourcesDefinition,
)

from config import PROGRAM_NAME, get_configuration
from execution import run_test
from initialization import initialize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PART_NUMBER_RD = "B0CG1KL3RD"

# Target workspace — "NI Connect 2026 - SystemLink Hands On"
WORKSPACE_ID = "26f50ba0-f249-4aaf-99b3-96b7a5afd75c"

# 5 DUTs for the new product variant.
SERIALS = [str(n) for n in range(2001, 2006)]

# 4 temperature conditions — each DUT is tested at all 4, giving 20 total runs.
TEMPERATURES = [-25.0, 0.0, 25.0, 45.0]

# Cartesian product: (serial, temp_c) for every combination.
RUN_MATRIX: list[tuple[str, float]] = [
    (serial, temp)
    for serial in SERIALS
    for temp in TEMPERATURES
]


def _resolve_dut_ids(
    asset_client: AssetManagementClient,
    serials: list[str],
    part_number: str,
) -> dict[str, str]:
    """Return {serial: asset_id} for DUT assets matching *part_number*.

    Logs a warning for any serial with no matching asset.
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
        description=f"{PROGRAM_NAME} — 20-run batch for {PART_NUMBER_RD}"
    )
    parser.add_argument(
        "--work-order-id",
        default=None,
        help="SystemLink work order ID to attach test plans to. "
             "If omitted, a new work order is created automatically.",
    )
    parser.add_argument("--server", help="SystemLink server URI. For dev use.")
    parser.add_argument("--api-key", help="SystemLink API key. For dev use.")
    return parser.parse_args()


def _create_work_order(server: str, api_key: str) -> str:
    """Create a new top-level work order for PART_NUMBER_RD via niworkorder REST API."""
    url = f"{server.rstrip('/')}/niworkorder/v1/workorders"
    body = json.dumps({
        "workOrders": [{
            "name": f"18650 Battery Test \u2014 {PART_NUMBER_RD} Batch Run",
            "type": "TEST_REQUEST",
            "state": "NEW",
            "workspace": WORKSPACE_ID,
        }]
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("x-ni-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "nisystemlink-python/1.0")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"Failed to create work order — HTTP {exc.code}: {body_text}"
        ) from exc

    created = data.get("createdWorkOrders") or []
    if not created:
        failed = data.get("failedWorkOrders") or []
        raise RuntimeError(f"Failed to create work order: {failed}")
    work_order_id = created[0]["id"]
    logger.info("Created work order %s for part number %s", work_order_id, PART_NUMBER_RD)
    return work_order_id


def _get_plan_workspace(wi_client: WorkItemClient, test_plan_id: str) -> str | None:
    """Return the workspace of the test plan so new work items inherit it."""
    try:
        plan = wi_client.get_work_item(test_plan_id)
        return plan.workspace
    except Exception:
        logger.warning(
            "Could not fetch test plan %s — workspace will be omitted", test_plan_id
        )
        return None


def _create_work_items(
    wi_client: WorkItemClient,
    test_plan_id: str,
    workspace: str | None,
    dut_ids: dict[str, str],
) -> list[tuple[str, str, float]]:
    """Create one work item per (DUT, temperature) and return [(wi_id, serial, temp_c), ...]."""
    requests = [
        CreateWorkItemRequest(
            name=f"18650 Battery Test — {PART_NUMBER_RD} SN {serial} @ {temp:+.0f}°C",
            type="testplan",
            state="DEFINED",
            parent_id=test_plan_id,
            part_number=PART_NUMBER_RD,
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
        for serial, temp in RUN_MATRIX
    ]

    response = wi_client.create_work_items(requests)

    created = []
    for item in response.created_work_items or []:
        serial = (item.properties or {}).get("serialNumber", "UNKNOWN")
        temp = float((item.properties or {}).get("ambient_temp_c", "25"))
        created.append((item.id, serial, temp))
        logger.info(
            "Created work item %s  serial=%s  temp=%.0f°C", item.id, serial, temp
        )

    for err in response.failed_work_items or []:
        logger.error("Failed to create work item: %s", err)

    return created


def main() -> int:
    args = _parse_args()
    configuration = get_configuration(server=args.server, api_key=args.api_key)

    wi_client = WorkItemClient(configuration)

    work_order_id = args.work_order_id
    if work_order_id is None:
        logger.info("No work order ID provided — creating a new work order")
        server_url = str(configuration.server_uri).rstrip("/")
        _api_key = (configuration.api_keys or {}).get("x-ni-api-key", "")
        work_order_id = _create_work_order(server=server_url, api_key=_api_key)

    workspace = WORKSPACE_ID
    logger.info("Using workspace: %s (NI Connect 2026 - SystemLink Hands On)", workspace)

    asset_client = AssetManagementClient(configuration)
    logger.info("Resolving DUT assets for part number %s", PART_NUMBER_RD)
    dut_ids = _resolve_dut_ids(asset_client, SERIALS, PART_NUMBER_RD)

    logger.info(
        "Creating %d work items (%d DUTs × %d temps) under work order %s",
        len(RUN_MATRIX), len(SERIALS), len(TEMPERATURES), work_order_id,
    )
    dut_items = _create_work_items(wi_client, work_order_id, workspace, dut_ids)

    if not dut_items:
        logger.error("No work items were created — aborting")
        return 1

    results: list[tuple[str, str, float, str | None]] = []
    for wi_id, serial, temp_c in dut_items:
        logger.info(
            "=== Running test: serial=%s  temp=%.0f°C  work_item=%s ===",
            serial, temp_c, wi_id,
        )
        result_id = None
        try:
            ctx = initialize(configuration, wi_id, interactive=False)
            result_id = run_test(configuration, ctx)
            logger.info("Finished serial=%s  temp=%.0f°C -> result %s", serial, temp_c, result_id)
        except Exception:
            logger.exception(
                "Test failed for serial=%s  temp=%.0f°C (work_item=%s)",
                serial, temp_c, wi_id,
            )
        results.append((serial, wi_id, temp_c, result_id))

    # --- Summary ---
    print("\n" + "=" * 68)
    print(f"Batch complete — {PART_NUMBER_RD}  ({len(RUN_MATRIX)} runs)  work order: {work_order_id}")
    print("=" * 68)
    passed = sum(1 for *_, r in results if r is not None)
    print(f"{'Serial':<10} {'Temp (°C)':<12} {'Work Item':<24} {'Result ID'}")
    print("-" * 68)
    for serial, wi_id, temp_c, result_id in results:
        status = result_id if result_id else "FAILED (see logs)"
        print(f"{serial:<10} {temp_c:<12.0f} {wi_id:<24} {status}")
    print("-" * 68)
    print(f"{passed}/{len(results)} tests completed successfully")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
