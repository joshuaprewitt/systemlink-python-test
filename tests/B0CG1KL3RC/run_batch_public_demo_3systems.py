"""Generate batch test data across 3 systems in a target workspace.

This script creates test-plan work items for each DUT serial, assigns systems
in round-robin across 3 system IDs, then executes the test flow to publish
results.

Usage:
    python run_batch_public_demo_3systems.py --server <URL> --api-key <KEY> \
      --system-id <SYSTEM_1> --system-id <SYSTEM_2> --system-id <SYSTEM_3>
"""

import argparse
import json
import logging
import os
import random
import subprocess
import sys
from collections.abc import Sequence
import urllib.error
import urllib.request

from nisystemlink.clients.assetmanagement import AssetManagementClient
from nisystemlink.clients.assetmanagement.models import QueryAssetsRequest
from nisystemlink.clients.product import ProductClient
from nisystemlink.clients.product.models import CreateProductRequest, QueryProductsRequest
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    CreateWorkItemRequest,
    ResourceDefinition,
    ResourceSelectionDefinition,
    ResourcesDefinition,
    SystemResourceDefinition,
    SystemResourceSelectionDefinition,
)

from config import PRODUCT_CHARACTERISTICS, PROGRAM_NAME, get_configuration
from execution import run_test
from initialization import initialize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Public Demo workspace (provided by user).
WORKSPACE_ID = "35b4522f-8875-43a4-8717-172ff004b275"
DEFAULT_DEMO_PART_NUMBER = "NCR18650GA"
EXPECTED_SYSTEM_COUNT = 3
SYSTEM_QUERY_TAKE = 500
SYSTEMLINK_API_KEY_HEADER = "x-ni-api-key"
DEMO_SERVER_TOKEN = "demo-api"
PARENT_WORKORDER_NAME = "18650 Battery Tests"

# Use 100 DUT serial identifiers and test each DUT twice (200 total results).
SERIALS = [str(n) for n in range(1234, 1334)]
TESTS_PER_DUT = 2

# Temperature profile for generated results.
TEMPS = [-25.0, 0.0, 15.0, 25.0, 35.0, 45.0]

DEFAULT_OPERATOR_POOL = [
    "Alan Turing",
    "Nikola Tesla",
    "Ada Lovelace",
    "Katherine Johnson",
    "Albert Einstein",
]

RunMatrixRow = tuple[str, str, float]
CreatedWorkItem = tuple[str, str, str, float]
ResultRow = tuple[str, str, str, float, str, str | None]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            f"{PROGRAM_NAME} batch generator for 3 systems in workspace {WORKSPACE_ID}"
        )
    )
    parser.add_argument("--server", help="SystemLink server URI.")
    parser.add_argument("--api-key", help="SystemLink API key.")
    parser.add_argument(
        "--workspace-id",
        default=WORKSPACE_ID,
        help=f"Workspace ID for generated data. Default: {WORKSPACE_ID}",
    )
    parser.add_argument(
        "--part-number",
        default=DEFAULT_DEMO_PART_NUMBER,
        help=(
            "Part number used for generated work items/results. "
            f"Default: {DEFAULT_DEMO_PART_NUMBER}"
        ),
    )
    parser.add_argument(
        "--system-id",
        dest="system_ids",
        action="append",
        required=True,
        help="System resource ID. Provide exactly 3 via repeated --system-id flags.",
    )
    parser.add_argument(
        "--operator",
        dest="operators",
        action="append",
        default=None,
        help=(
            "Operator pool used for random per-result assignment. "
            "Repeat to provide multiple operators."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible operator assignment.",
    )
    parser.add_argument(
        "--allow-non-demo-server",
        action="store_true",
        help="Allow execution against a non-demo server URI.",
    )
    return parser.parse_args()


def _assert_demo_server(server_uri: str, allow_non_demo: bool) -> None:
    uri = (server_uri or "").lower()
    if allow_non_demo:
        return
    if DEMO_SERVER_TOKEN not in uri:
        raise RuntimeError(
            "This script is restricted to demo server usage. "
            "Use a demo-api server URI or pass --allow-non-demo-server."
        )


def _require_unique_system_ids(system_ids: Sequence[str]) -> list[str]:
    unique_system_ids = list(dict.fromkeys(system_ids))
    if len(unique_system_ids) != EXPECTED_SYSTEM_COUNT:
        raise RuntimeError(
            f"Provide exactly {EXPECTED_SYSTEM_COUNT} unique --system-id values."
        )
    return unique_system_ids


def _extract_api_key(configuration) -> str:
    api_keys = getattr(configuration, "api_keys", {}) or {}
    if not isinstance(api_keys, dict):
        return ""
    return str(api_keys.get(SYSTEMLINK_API_KEY_HEADER, "") or "")


def _query_systems_via_api(server_uri: str, api_key: str) -> list[dict]:
    url = f"{server_uri}/nisysmgmt/v1/query-systems"
    body = json.dumps({"take": SYSTEM_QUERY_TAKE}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header(SYSTEMLINK_API_KEY_HEADER, api_key)

    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        return []

    systems = payload.get("data", [])
    return systems if isinstance(systems, list) else []


def _query_systems_via_slcli(workspace_id: str) -> list[dict]:
    completed = subprocess.run(
        [
            "slcli",
            "system",
            "list",
            "-f",
            "json",
            "-w",
            workspace_id,
            "-t",
            str(SYSTEM_QUERY_TAKE),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    return payload if isinstance(payload, list) else []


def _build_system_display_map(systems: list[dict]) -> dict[str, str]:
    display_by_id: dict[str, str] = {}
    for system in systems:
        if not isinstance(system, dict):
            continue

        system_id = str(system.get("id", "") or "")
        if not system_id:
            continue

        alias = str(system.get("alias", "") or "").strip()
        hostname = str(system.get("hostname", system.get("host", "")) or "").strip()
        display_by_id[system_id] = alias or hostname or system_id
    return display_by_id


def _resolve_system_display_names(
    configuration,
    system_ids: list[str],
    workspace_id: str,
) -> dict[str, str]:
    """Resolve user-friendly system names for the provided system IDs."""
    server_uri = str(getattr(configuration, "server_uri", "") or "").rstrip("/")
    api_key = _extract_api_key(configuration)
    if not server_uri or not api_key:
        logger.warning("Missing server/api key configuration; using system IDs in names.")
        return {system_id: system_id for system_id in system_ids}

    try:
        systems = _query_systems_via_api(server_uri, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        logger.warning(
            "Direct systems API lookup failed (%s); trying slcli fallback.",
            exc,
        )
        try:
            systems = _query_systems_via_slcli(workspace_id)
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
            logger.exception("slcli fallback failed; using system IDs in names.")
            return {system_id: system_id for system_id in system_ids}

    display_by_id = _build_system_display_map(systems)

    resolved: dict[str, str] = {}
    for system_id in system_ids:
        resolved[system_id] = display_by_id.get(system_id, system_id)

    missing = [system_id for system_id in system_ids if resolved[system_id] == system_id]
    if missing:
        logger.warning(
            "Could not resolve alias/hostname for %d system(s); using ID fallback: %s",
            len(missing),
            ", ".join(missing),
        )

    return resolved


def _resolve_dut_ids(
    asset_client: AssetManagementClient,
    serials: list[str],
    part_number: str,
) -> dict[str, str]:
    serial_filter = " || ".join(f'serialNumber == "{s}"' for s in serials)
    result = asset_client.query_assets(
        QueryAssetsRequest(
            filter=f'modelName == "{part_number}" && ({serial_filter})',
            take=len(serials) + 20,
        )
    )

    mapping: dict[str, str] = {}
    for asset in result.assets:
        if asset.serial_number and asset.id:
            mapping[asset.serial_number] = asset.id

    missing = [s for s in serials if s not in mapping]
    if missing:
        logger.warning(
            "Missing DUT assets for %d serial(s); runs continue using serial properties only: %s",
            len(missing),
            ", ".join(missing),
        )
    return mapping


def _ensure_product_exists(
    product_client: ProductClient,
    part_number: str,
    workspace_id: str,
) -> None:
    query = product_client.query_products_paged(
        QueryProductsRequest(
            filter=f'partNumber == "{part_number}"',
            take=50,
        )
    )

    for product in query.products or []:
        if product.workspace == workspace_id:
            logger.info("Product %s already exists in workspace %s", part_number, workspace_id)
            return

    logger.info("Creating product %s in workspace %s", part_number, workspace_id)

    full_request = CreateProductRequest(
        part_number=part_number,
        name="18650 Li-ion Battery Cell",
        family="Battery",
        keywords=["18650", "li-ion", "battery"],
        properties=PRODUCT_CHARACTERISTICS,
        workspace=workspace_id,
    )
    response = product_client.create_products([full_request])
    created = getattr(response, "created_products", None)
    if created is None:
        created = getattr(response, "products", None)
    if created:
        return

    failed = getattr(response, "failed_products", None)
    if failed is None:
        failed = getattr(response, "failed", None)
    logger.warning(
        "Full product create failed for %s in workspace %s; retrying minimal payload. failed=%s",
        part_number,
        workspace_id,
        failed,
    )

    minimal_request = CreateProductRequest(
        part_number=part_number,
        name="18650 Li-ion Battery Cell",
        family="Battery",
        workspace=workspace_id,
    )
    retry = product_client.create_products([minimal_request])
    retry_created = getattr(retry, "created_products", None)
    if retry_created is None:
        retry_created = getattr(retry, "products", None)
    if retry_created:
        return

    retry_failed = getattr(retry, "failed_products", None)
    if retry_failed is None:
        retry_failed = getattr(retry, "failed", None)
    raise RuntimeError(
        f"Failed to create product {part_number} in workspace {workspace_id}. "
        f"full_failed={failed} minimal_failed={retry_failed}"
    )


def _create_parent_workorder(
    wi_client: WorkItemClient,
    workspace_id: str,
    part_number: str,
) -> str:
    response = wi_client.create_work_items(
        [
            CreateWorkItemRequest(
                name=PARENT_WORKORDER_NAME,
                type="workorder",
                state="DEFINED",
                part_number=part_number,
                workspace=workspace_id,
            )
        ]
    )
    if not response.created_work_items:
        raise RuntimeError(f"Failed to create parent workorder: {response.failed_work_items}")
    return response.created_work_items[0].id


def _build_run_matrix(
    serials: list[str],
    system_ids: list[str],
    tests_per_dut: int,
) -> list[RunMatrixRow]:
    matrix: list[RunMatrixRow] = []
    expanded_serials = serials * tests_per_dut
    temp_index_by_system: dict[str, int] = {system_id: 0 for system_id in system_ids}
    for index, serial in enumerate(expanded_serials):
        system_id = system_ids[index % len(system_ids)]
        temp_index = temp_index_by_system[system_id]
        temp_c = TEMPS[temp_index % len(TEMPS)]
        temp_index_by_system[system_id] = temp_index + 1
        matrix.append((serial, system_id, temp_c))
    return matrix


def _build_operator_sequence(
    run_count: int,
    operators: list[str],
    seed: int | None,
) -> list[str]:
    cleaned = [name.strip() for name in operators if name and name.strip()]
    pool = list(dict.fromkeys(cleaned))
    if not pool:
        raise RuntimeError("Operator pool is empty.")

    rng = random.Random(seed)
    sequence: list[str] = []
    while len(sequence) < run_count:
        shuffled = pool[:]
        rng.shuffle(shuffled)
        sequence.extend(shuffled)
    return sequence[:run_count]


def _create_work_items(
    wi_client: WorkItemClient,
    parent_workorder_id: str,
    workspace_id: str,
    part_number: str,
    dut_ids: dict[str, str],
    run_matrix: list[RunMatrixRow],
    system_display_names: dict[str, str],
) -> list[CreatedWorkItem]:
    requests: list[CreateWorkItemRequest] = []

    for serial, system_id, temp_c in run_matrix:
        system_display_name = system_display_names.get(system_id, system_id)
        requests.append(
            CreateWorkItemRequest(
                name=f"18650 Demo Batch SN {serial} on {system_display_name}",
                type="testplan",
                state="DEFINED",
                parent_id=parent_workorder_id,
                part_number=part_number,
                test_program=PROGRAM_NAME,
                workspace=workspace_id,
                resources=ResourcesDefinition(
                    duts=ResourceDefinition(
                        selections=[ResourceSelectionDefinition(id=dut_ids[serial])]
                        if serial in dut_ids
                        else [],
                    ),
                    systems=SystemResourceDefinition(
                        selections=[SystemResourceSelectionDefinition(id=system_id)],
                    ),
                ),
                properties={
                    "serialNumber": serial,
                    "ambient_temp_c": str(temp_c),
                    "test_profile": "public_demo_3_system",
                    "charge_rate_a": "1.0",
                },
            )
        )

    response = wi_client.create_work_items(requests)

    created_map: dict[tuple[str, str, float], str] = {}
    for item in response.created_work_items or []:
        props = item.properties or {}
        system_selections = (
            item.resources.systems.selections
            if item.resources and item.resources.systems and item.resources.systems.selections
            else []
        )
        key = (
            props.get("serialNumber", ""),
            (system_selections[0].id if system_selections else ""),
            float(props.get("ambient_temp_c", "25")),
        )
        created_map[key] = item.id

    for err in response.failed_work_items or []:
        logger.error("Failed to create work item: %s", err)

    created: list[CreatedWorkItem] = []
    for serial, system_id, temp_c in run_matrix:
        wi_id = created_map.get((serial, system_id, float(temp_c)))
        if wi_id:
            created.append((wi_id, serial, system_id, temp_c))
            logger.info(
                "Created work item %s serial=%s system=%s temp=%.0fC",
                wi_id,
                serial,
                system_id,
                temp_c,
            )

    return created


def _scale_for_system(system_id: str, primary_system_id: str) -> str:
    # Primary system is intentionally biased +15% for Internal Resistance.
    return "1.15" if system_id == primary_system_id else "1.0"


def _execute_runs(
    configuration,
    created: list[CreatedWorkItem],
    operator_sequence: list[str],
    primary_system_id: str,
) -> list[ResultRow]:
    results: list[ResultRow] = []
    for (wi_id, serial, system_id, temp_c), operator in zip(created, operator_sequence):
        os.environ["SYSTEMLINK_TEST_OPERATOR"] = operator
        os.environ["SYSTEMLINK_INTERNAL_RESISTANCE_SCALE"] = _scale_for_system(
            system_id,
            primary_system_id,
        )

        result_id = None
        try:
            ctx = initialize(configuration, wi_id, interactive=False)
            result_id = run_test(configuration, ctx)
        except Exception:
            logger.exception(
                "Run failed for work item %s serial=%s system=%s",
                wi_id,
                serial,
                system_id,
            )

        results.append((wi_id, serial, system_id, temp_c, operator, result_id))

    return results


def _print_summary(
    parent_workorder_id: str,
    workspace_id: str,
    results: list[ResultRow],
) -> int:
    print("\n" + "=" * 92)
    print(
        f"Public Demo 3-system batch complete. parent={parent_workorder_id} "
        f"workspace={workspace_id}"
    )
    print("=" * 92)
    print(f"{'Work Item':<14} {'Serial':<8} {'System':<40} {'TempC':<6} {'Operator':<18} {'Result ID'}")
    print("-" * 92)
    for wi_id, serial, system_id, temp_c, operator, result_id in results:
        print(
            f"{wi_id:<14} {serial:<8} {system_id[:40]:<40} {temp_c:<6.0f} {operator[:18]:<18} "
            f"{result_id or 'FAILED'}"
        )
    print("-" * 92)
    passed = sum(1 for *_, result_id in results if result_id)
    print(f"{passed}/{len(results)} runs completed successfully")
    return passed


def main() -> int:
    args = _parse_args()
    configuration = get_configuration(server=args.server, api_key=args.api_key)

    _assert_demo_server(str(configuration.server_uri), args.allow_non_demo_server)

    unique_system_ids = _require_unique_system_ids(args.system_ids)

    primary_system_id = unique_system_ids[0]

    operators = args.operators or DEFAULT_OPERATOR_POOL

    wi_client = WorkItemClient(configuration)
    product_client = ProductClient(configuration)
    asset_client = AssetManagementClient(configuration)

    _ensure_product_exists(product_client, args.part_number, args.workspace_id)

    parent_workorder_id = _create_parent_workorder(
        wi_client,
        args.workspace_id,
        args.part_number,
    )
    logger.info("Created parent workorder %s", parent_workorder_id)

    dut_ids = _resolve_dut_ids(asset_client, SERIALS, args.part_number)
    system_display_names = _resolve_system_display_names(
        configuration,
        unique_system_ids,
        args.workspace_id,
    )

    run_matrix = _build_run_matrix(SERIALS, unique_system_ids, TESTS_PER_DUT)
    created = _create_work_items(
        wi_client,
        parent_workorder_id,
        args.workspace_id,
        args.part_number,
        dut_ids,
        run_matrix,
        system_display_names,
    )

    if not created:
        logger.error("No work items were created; aborting.")
        return 1

    operator_sequence = _build_operator_sequence(
        run_count=len(created),
        operators=operators,
        seed=args.seed,
    )

    results = _execute_runs(
        configuration,
        created,
        operator_sequence,
        primary_system_id,
    )

    passed = _print_summary(
        parent_workorder_id,
        args.workspace_id,
        results,
    )

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
