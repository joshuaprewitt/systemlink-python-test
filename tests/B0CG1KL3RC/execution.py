"""Test execution — create result, run steps, upload files, update work item."""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from nisystemlink.clients.core import ApiException, HttpConfiguration
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import (
    CreateResultRequest,
    CreateStepRequest,
    Measurement,
    NamedValue,
    Status,
    StatusType,
    StepData,
    UpdateResultRequest,
)
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    UpdateWorkItemRequest,
    UpdateWorkItemsRequest,
)
from nisystemlink.clients.file import FileClient

from config import PROGRAM_NAME, PRODUCT_SPECS
from initialization import TestContext
from simulator import (
    measure_capacity,
    measure_charge_voltage,
    measure_discharge_cutoff_voltage,
    measure_internal_resistance,
    measure_open_circuit_voltage,
    measure_temperature,
    measure_voltage_under_load,
    measure_weight,
)

logger = logging.getLogger(__name__)


def _get_spec(props: dict[str, str], key: str) -> float:
    """Read a numeric limit from resolved spec limits with fallback defaults."""
    candidates = [key]
    if key.startswith("spec."):
        candidates.append(key[5:])
    else:
        candidates.append(f"spec.{key}")

    value = None
    for source in (props, PRODUCT_SPECS):
        for candidate in candidates:
            candidate_value = source.get(candidate)
            if candidate_value not in (None, ""):
                value = candidate_value
                break
        if value is not None:
            break

    if value is None:
        raise RuntimeError(f"Missing product spec: {key}")
    return float(value)


def _compare(value: float, low: float, high: float) -> StatusType:
    """GELE comparison — pass if low <= value <= high."""
    return StatusType.PASSED if low <= value <= high else StatusType.FAILED


def _build_step(
    result_id: str,
    name: str,
    step_type: str,
    spec_id: str,
    measurement_value: float,
    low_limit: float,
    high_limit: float,
    units: str,
    inputs: list[NamedValue],
    outputs: list[NamedValue],
    part_number: str,
    duration: float,
    started_at: datetime,
) -> CreateStepRequest:
    """Build a CreateStepRequest with full inputs/outputs/limits metadata."""
    status_type = _compare(measurement_value, low_limit, high_limit)
    return CreateStepRequest(
        step_id=spec_id,
        result_id=result_id,
        name=name,
        step_type=step_type,
        status=Status(status_type=status_type),
        total_time_in_seconds=duration,
        started_at=started_at,
        inputs=inputs,
        outputs=outputs,
        data=StepData(
            text=name,
            parameters=[
                Measurement(
                    name=name,
                    status=status_type.value,
                    measurement=str(measurement_value),
                    lowLimit=str(low_limit),
                    highLimit=str(high_limit),
                    units=units,
                    comparisonType="GELE",
                    specId=spec_id,
                )
            ],
        ),
        properties={
            "step.startedAt": started_at.isoformat(),
            "step.duration": str(round(duration, 3)),
            "step.limitSource": f"product:{part_number}",
        },
    )


def run_test(
    configuration: HttpConfiguration | None,
    ctx: TestContext,
) -> str:
    """Execute the battery test, publish results, and return the result ID."""
    tm_client = TestMonitorClient(configuration)
    wi_client = WorkItemClient(configuration)
    file_client = FileClient(configuration)

    specs = ctx.spec_limits
    test_start = datetime.now(timezone.utc)

    # ---- Create RUNNING result ----
    result_resp = tm_client.create_results(
        [
            CreateResultRequest(
                program_name=PROGRAM_NAME,
                status=Status(status_type=StatusType.RUNNING),
                started_at=test_start,
                host_name=ctx.host_name,
                system_id=ctx.system_id,
                operator=ctx.operator,
                part_number=ctx.part_number,
                serial_number=ctx.serial_number,
                properties={"workItemId": ctx.work_item_id},
                keywords=["18650", "battery", "li-ion"],
                workspace=ctx.work_item.workspace,
            )
        ]
    )
    result_id = result_resp.results[0].id
    logger.info("Created result %s (RUNNING)", result_id)

    # ---- Transition work item to IN_PROGRESS ----
    wi_client.update_work_items(
        UpdateWorkItemsRequest(
            work_items=[
                UpdateWorkItemRequest(id=ctx.work_item_id, state="IN_PROGRESS")
            ]
        )
    )
    logger.info("Work item %s → IN_PROGRESS", ctx.work_item_id)

    # ---- Execute test steps ----
    steps: list[CreateStepRequest] = []
    step_statuses: list[StatusType] = []

    # --- Step 1: Open Circuit Voltage ---
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    ocv = measure_open_circuit_voltage()
    duration = time.monotonic() - t0
    step = _build_step(
        result_id=result_id,
        name="Open Circuit Voltage",
        step_type="NumericLimit",
        spec_id="OutputVoltage",
        measurement_value=ocv,
        low_limit=_get_spec(specs, "voltage_low_limit"),
        high_limit=_get_spec(specs, "voltage_high_limit"),
        units="V",
        inputs=[],
        outputs=[NamedValue(name="output.ocv_voltage", value=str(ocv))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 2: Voltage Under Load ---
    load_current = _get_spec(specs, "max_continuous_discharge_current")
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    loaded_v = measure_voltage_under_load(load_current)
    duration = time.monotonic() - t0
    step = _build_step(
        result_id=result_id,
        name="Voltage Under Load",
        step_type="NumericLimit",
        spec_id="OutputVoltageUnderLoad",
        measurement_value=loaded_v,
        low_limit=_get_spec(specs, "min_discharge_voltage"),
        high_limit=_get_spec(specs, "voltage_high_limit"),
        units="V",
        inputs=[
            NamedValue(name="input.load_current", value=f"{load_current} A"),
        ],
        outputs=[NamedValue(name="output.loaded_voltage", value=str(loaded_v))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 3: Internal Resistance ---
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    ir = measure_internal_resistance()
    duration = time.monotonic() - t0
    step = _build_step(
        result_id=result_id,
        name="Internal Resistance",
        step_type="NumericLimit",
        spec_id="InternalResistance",
        measurement_value=ir,
        low_limit=_get_spec(specs, "internal_resistance_low_limit"),
        high_limit=_get_spec(specs, "internal_resistance_high_limit"),
        units="mΩ",
        inputs=[],
        outputs=[NamedValue(name="output.internal_resistance", value=str(ir))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 4: Capacity ---
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    capacity = measure_capacity()
    duration = time.monotonic() - t0
    step = _build_step(
        result_id=result_id,
        name="Cell Capacity",
        step_type="NumericLimit",
        spec_id="Capacity",
        measurement_value=capacity,
        low_limit=_get_spec(specs, "capacity_low_limit_mah"),
        high_limit=_get_spec(specs, "capacity_high_limit_mah"),
        units="mAh",
        inputs=[NamedValue(name="input.charge_rate", value="1.0 A")],
        outputs=[NamedValue(name="output.measured_capacity", value=str(capacity))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 5: Charge Voltage ---
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    charge_v = measure_charge_voltage()
    duration = time.monotonic() - t0
    max_charge = _get_spec(specs, "max_charge_voltage")
    step = _build_step(
        result_id=result_id,
        name="End-of-Charge Voltage",
        step_type="NumericLimit",
        spec_id="EndOfChargeVoltage",
        measurement_value=charge_v,
        low_limit=max_charge - 0.05,
        high_limit=max_charge,
        units="V",
        inputs=[],
        outputs=[NamedValue(name="output.charge_voltage", value=str(charge_v))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 6: Discharge Cutoff Voltage ---
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    cutoff_v = measure_discharge_cutoff_voltage()
    duration = time.monotonic() - t0
    min_discharge = _get_spec(specs, "min_discharge_voltage")
    step = _build_step(
        result_id=result_id,
        name="Discharge Cutoff Voltage",
        step_type="NumericLimit",
        spec_id="DischargeCutoffVoltage",
        measurement_value=cutoff_v,
        low_limit=min_discharge,
        high_limit=min_discharge + 0.2,
        units="V",
        inputs=[],
        outputs=[NamedValue(name="output.cutoff_voltage", value=str(cutoff_v))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 7: Weight ---
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    weight = measure_weight()
    duration = time.monotonic() - t0
    step = _build_step(
        result_id=result_id,
        name="Cell Weight",
        step_type="NumericLimit",
        spec_id="CellWeight",
        measurement_value=weight,
        low_limit=_get_spec(specs, "weight_low_limit"),
        high_limit=_get_spec(specs, "weight_high_limit"),
        units="g",
        inputs=[],
        outputs=[NamedValue(name="output.weight", value=str(weight))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # --- Step 8: Temperature Under Discharge ---
    ambient = float(ctx.work_item_properties.get("ambient_temp_c", "25.0"))
    step_start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    temp = measure_temperature(ambient)
    duration = time.monotonic() - t0
    step = _build_step(
        result_id=result_id,
        name="Temperature Under Discharge",
        step_type="NumericLimit",
        spec_id="TemperatureUnderDischarge",
        measurement_value=temp,
        low_limit=_get_spec(specs, "operating_temp_low"),
        high_limit=_get_spec(specs, "operating_temp_high"),
        units="°C",
        inputs=[NamedValue(name="input.ambient_temp", value=f"{ambient} °C")],
        outputs=[NamedValue(name="output.cell_surface_temp", value=str(temp))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=step_start,
    )
    steps.append(step)
    step_statuses.append(step.status.status_type)

    # ---- Publish steps ----
    tm_client.create_steps(steps)
    logger.info("Published %d test steps", len(steps))

    # ---- Write test log file and upload ----
    total_time = (datetime.now(timezone.utc) - test_start).total_seconds()
    log_path = Path(f"test_log_{result_id}.txt")
    _write_log(log_path, ctx, steps, step_statuses)

    file_ids: list[str] = []
    try:
        file_metadata = {
            "resultId": result_id,
            "workItemId": ctx.work_item_id,
            "minionId": ctx.system_id or "",
            "fileType": "test-log",
        }
        try:
            with open(log_path, "rb") as fp:
                file_id = file_client.upload_file(file=fp, metadata=file_metadata)
        except ApiException as ex:
            # Some server builds reject multipart metadata even though the SDK supports it.
            if "metadata field was specified as a file" not in str(ex):
                raise
            logger.warning("Metadata upload rejected by server, retrying file upload without metadata")
            with open(log_path, "rb") as fp:
                file_id = file_client.upload_file(file=fp)
        file_ids.append(file_id)
        logger.info("Uploaded log file %s", file_id)
    except Exception:
        logger.exception("Failed to upload log file")
    finally:
        log_path.unlink(missing_ok=True)

    # ---- Determine final status ----
    if any(s == StatusType.ERRORED for s in step_statuses):
        final_status = StatusType.ERRORED
    elif any(s == StatusType.FAILED for s in step_statuses):
        final_status = StatusType.FAILED
    else:
        final_status = StatusType.PASSED

    # ---- Update result with final status and file IDs ----
    update_props = {"workItemId": ctx.work_item_id}
    if file_ids:
        update_props["fileIds"] = ",".join(file_ids)

    tm_client.update_results(
        [
            UpdateResultRequest(
                id=result_id,
                status=Status(status_type=final_status),
                total_time_in_seconds=total_time,
                file_ids=file_ids,
                properties=update_props,
            )
        ]
    )
    logger.info(
        "Result %s updated → %s (%.1fs)", result_id, final_status.value, total_time
    )

    # ---- Transition work item ----
    wi_state = "PENDING_APPROVAL"
    wi_client.update_work_items(
        UpdateWorkItemsRequest(
            work_items=[
                UpdateWorkItemRequest(id=ctx.work_item_id, state=wi_state)
            ]
        )
    )
    logger.info("Work item %s → %s", ctx.work_item_id, wi_state)

    return result_id


def _write_log(
    path: Path,
    ctx: TestContext,
    steps: list[CreateStepRequest],
    statuses: list[StatusType],
) -> None:
    """Write a simple text log of the test execution."""

    def _ascii_safe(text: str) -> str:
        return (
            text.replace("—", "-")
            .replace("°", "deg")
            .replace("Ω", "Ohm")
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Test Log - {_ascii_safe(PROGRAM_NAME)}\n")
        f.write(f"Work Item: {ctx.work_item_id}\n")
        f.write(f"Part: {ctx.part_number}  Serial: {ctx.serial_number}\n")
        f.write(f"Operator: {ctx.operator}  Host: {ctx.host_name}\n")
        f.write("-" * 50 + "\n")
        for step, status in zip(steps, statuses):
            params = step.data.parameters if step.data else []
            meas = params[0] if params else None
            units = _ascii_safe(meas.units) if meas and meas.units else ""
            f.write(
                f"  {step.name}: {status.value}"
                f"  measurement={meas.measurement if meas else 'N/A'}"
                f"  [{meas.lowLimit}..{meas.highLimit}] {units}\n"
            )
