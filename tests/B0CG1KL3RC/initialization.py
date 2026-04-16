"""Test initialization — resolve work item, product, DUT, and system."""

import logging
import platform
from dataclasses import dataclass, field
from pathlib import Path

from nisystemlink.clients.core import HttpConfiguration
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import WorkItem
from nisystemlink.clients.product import ProductClient
from nisystemlink.clients.product.models import (
    CreateProductRequest,
    QueryProductsRequest,
)
from nisystemlink.clients.assetmanagement import AssetManagementClient
from nisystemlink.clients.assetmanagement.models import (
    Asset,
    AssetType,
    CalibrationStatus,
    QueryAssetsRequest,
)

from config import PART_NUMBER, PRODUCT_SPECS, PROGRAM_NAME, get_hostname

logger = logging.getLogger(__name__)


@dataclass
class TestContext:
    """Resolved context needed to execute the test."""

    work_item: WorkItem
    work_item_id: str
    part_number: str
    serial_number: str
    operator: str
    host_name: str
    system_id: str | None
    product_properties: dict[str, str] = field(default_factory=dict)
    work_item_properties: dict[str, str] = field(default_factory=dict)
    dut_asset: Asset | None = None


def _resolve_product(
    product_client: ProductClient,
    part_number: str,
    interactive: bool,
) -> dict[str, str]:
    """Query the product by part number and return its spec properties.

    Creates the product with default specs if it does not exist and we are
    running in interactive mode.
    """
    result = product_client.query_products_paged(
        QueryProductsRequest(
            filter=f'partNumber == "{part_number}"',
            take=1,
        )
    )

    if result.products:
        product = result.products[0]
        logger.info("Found product %s (id=%s)", part_number, product.id)
        return product.properties or {}

    if not interactive:
        raise RuntimeError(
            f"Product {part_number} not found and running in automated mode — "
            "cannot prompt for data sheet. Create the product first."
        )

    logger.warning("Product %s not found — creating with default specs", part_number)
    print(f"\nProduct '{part_number}' does not exist in Test Monitor.")
    print("Creating with default 18650 battery specifications.\n")

    product_client.create_products(
        [
            CreateProductRequest(
                part_number=part_number,
                name="18650 Li-ion Battery Cell",
                family="Battery",
                keywords=["18650", "li-ion", "battery"],
                properties=PRODUCT_SPECS,
            )
        ]
    )
    logger.info("Created product %s", part_number)
    return dict(PRODUCT_SPECS)


def _resolve_dut(
    asset_client: AssetManagementClient,
    work_item: WorkItem,
) -> Asset | None:
    """Resolve the DUT asset assigned to the work item."""
    if not work_item.resources or not work_item.resources.duts:
        logger.info("No DUT resource assigned to work item")
        return None

    selections = work_item.resources.duts.selections or []
    if not selections:
        logger.info("No DUT selections on work item")
        return None

    dut_id = selections[0].id
    if not dut_id:
        return None

    result = asset_client.query_assets(
        QueryAssetsRequest(filter=f'id == "{dut_id}"', take=1)
    )
    if result.assets:
        asset = result.assets[0]
        logger.info(
            "Resolved DUT: %s (serial=%s)", asset.model_name, asset.serial_number
        )
        return asset

    logger.warning("DUT asset %s not found", dut_id)
    return None


def _resolve_system_id(
    work_item: WorkItem,
    is_dev_mode: bool,
) -> str | None:
    """Resolve the system (minion) ID for result and file linking.

    On a managed system (is_dev_mode=False): reads the local minionId from the
    NI SystemLink configuration files on disk.

    In dev mode (is_dev_mode=True): uses the system resource ID assigned to the
    work item, since the developer's machine is not a managed system.
    """
    if not is_dev_mode:
        minion_id = _read_local_minion_id()
        if minion_id:
            logger.info("Using local system minionId: %s", minion_id)
            return minion_id
        logger.warning("Could not read local minionId — falling back to work item")

    # Dev mode or local read failed: use the work item's system resource
    if not work_item.resources or not work_item.resources.systems:
        return None
    selections = work_item.resources.systems.selections or []
    if selections and selections[0].id:
        logger.info("Using work item system resource: %s", selections[0].id)
        return selections[0].id
    return None


def _read_local_minion_id() -> str | None:
    """Read the local minionId from NI SystemLink configuration files.

    Checks the standard locations used by NI SystemLink managed systems:
    - Windows: C:/ProgramData/National Instruments/salt/conf/minion_id
    - Linux: /etc/salt/minion_id
    """
    if platform.system() == "Windows":
        config_path = Path(
            "C:/ProgramData/National Instruments/salt/conf/minion_id"
        )
    else:
        config_path = Path("/etc/salt/minion_id")

    if not config_path.exists():
        return None

    try:
        minion_id = config_path.read_text().strip()
        if minion_id:
            return minion_id
    except Exception:
        logger.debug("Failed to read minionId from %s", config_path, exc_info=True)

    return None


def _check_fixture_calibration(
    asset_client: AssetManagementClient,
    work_item: WorkItem,
) -> None:
    """Warn if any assigned fixture is past calibration due date."""
    if not work_item.resources or not work_item.resources.fixtures:
        return
    selections = work_item.resources.fixtures.selections or []
    for sel in selections:
        if not sel.id:
            continue
        result = asset_client.query_assets(
            QueryAssetsRequest(filter=f'id == "{sel.id}"', take=1)
        )
        if not result.assets:
            continue
        fixture = result.assets[0]
        if fixture.calibration_status == CalibrationStatus.PAST_RECOMMENDED_DUE_DATE:
            logger.warning(
                "Fixture %s (%s) is PAST calibration due date!",
                fixture.name or fixture.model_name,
                sel.id,
            )


def initialize(
    configuration: HttpConfiguration | None,
    work_item_id: str,
    interactive: bool = False,
) -> TestContext:
    """Resolve all test context from a work item ID.

    Args:
        configuration: SystemLink connection, or ``None`` for system creds.
        work_item_id: The work item to load.
        interactive: If ``True``, allow operator prompts (e.g. product creation).

    Returns:
        A populated :class:`TestContext`.

    Raises:
        RuntimeError: If required parameters cannot be resolved.
    """
    wi_client = WorkItemClient(configuration)
    product_client = ProductClient(configuration)
    asset_client = AssetManagementClient(configuration)

    # --- Work item ---
    logger.info("Fetching work item %s", work_item_id)
    work_item = wi_client.get_work_item(work_item_id)

    part_number = work_item.part_number or PART_NUMBER
    operator = work_item.assigned_to or "unassigned"
    host_name = get_hostname()
    is_dev_mode = configuration is not None
    system_id = _resolve_system_id(work_item, is_dev_mode)

    # --- Product specs ---
    product_props = _resolve_product(product_client, part_number, interactive)

    # --- DUT ---
    dut_asset = _resolve_dut(asset_client, work_item)
    serial_number = (
        dut_asset.serial_number
        if dut_asset and dut_asset.serial_number
        else work_item.properties.get("serialNumber", "UNKNOWN")
        if work_item.properties
        else "UNKNOWN"
    )

    # --- Fixture calibration check ---
    _check_fixture_calibration(asset_client, work_item)

    # --- Work item properties ---
    wi_props = work_item.properties or {}

    ctx = TestContext(
        work_item=work_item,
        work_item_id=work_item_id,
        part_number=part_number,
        serial_number=serial_number,
        operator=operator,
        host_name=host_name,
        system_id=system_id,
        product_properties=product_props,
        work_item_properties=wi_props,
        dut_asset=dut_asset,
    )

    if interactive:
        _print_summary(ctx)
        resp = input("\nProceed with test execution? [Y/n] ").strip().lower()
        if resp and resp != "y":
            raise RuntimeError("Operator aborted test execution")

    return ctx


def _print_summary(ctx: TestContext) -> None:
    """Display resolved parameters for operator confirmation."""
    print("\n" + "=" * 60)
    print("  TEST INITIALIZATION SUMMARY")
    print("=" * 60)
    print(f"  Program:       {PROGRAM_NAME}")
    print(f"  Work Item:     {ctx.work_item_id}")
    print(f"  Part Number:   {ctx.part_number}")
    print(f"  Serial Number: {ctx.serial_number}")
    print(f"  Operator:      {ctx.operator}")
    print(f"  Host:          {ctx.host_name}")
    print(f"  System ID:     {ctx.system_id or 'N/A'}")
    if ctx.dut_asset:
        print(f"  DUT Model:     {ctx.dut_asset.model_name}")
    print(f"  Specs loaded:  {len(ctx.product_properties)} properties")
    print("=" * 60)
