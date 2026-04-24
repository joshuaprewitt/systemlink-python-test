"""Test execution: create result, run steps, upload files, and update work item."""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from nisystemlink.clients.core import ApiException, HttpConfiguration
from nisystemlink.clients.file import FileClient
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
from nisystemlink.clients.work_item.models import UpdateWorkItemRequest, UpdateWorkItemsRequest

from config import PRODUCT_SPECS, PROGRAM_NAME
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


def _get_spec(specs: dict[str, str], key: str) -> float:
    """Read a numeric limit from resolved limits with PRODUCT_SPECS fallback."""
    candidates = [key]
    if key.startswith("spec."):
        candidates.append(key[5:])
    else:
        candidates.append(f"spec.{key}")

    value = None
    for source in (specs, PRODUCT_SPECS):
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
    """GELE comparison: pass if low <= value <= high."""
    return StatusType.PASSED if low <= value <= high else StatusType.FAILED


def _capture_measurement(
    measure_fn: Callable[..., float],
    *args,
) -> tuple[datetime, float, float]:
    """Measure a value and return (started_at, duration, value)."""
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    value = measure_fn(*args)
    duration = time.monotonic() - t0
    return started_at, duration, value


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
    """Build a CreateStepRequest with limits and measurement metadata."""
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


def _build_open_circuit_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    started_at, duration, measured = _capture_measurement(measure_open_circuit_voltage)
    return _build_step(
        result_id=result_id,
        name="Open Circuit Voltage",
        step_type="NumericLimit",
        spec_id="OutputVoltage",
        measurement_value=measured,
        low_limit=_get_spec(specs, "voltage_low_limit"),
        high_limit=_get_spec(specs, "voltage_high_limit"),
        units="V",
        inputs=[],
        outputs=[NamedValue(name="output.ocv_voltage", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_under_load_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    load_current = _get_spec(specs, "max_continuous_discharge_current")
    started_at, duration, measured = _capture_measurement(measure_voltage_under_load, load_current)
    return _build_step(
        result_id=result_id,
        name="Voltage Under Load",
        step_type="NumericLimit",
        spec_id="OutputVoltageUnderLoad",
        measurement_value=measured,
        low_limit=_get_spec(specs, "min_discharge_voltage"),
        high_limit=_get_spec(specs, "voltage_high_limit"),
        units="V",
        inputs=[NamedValue(name="input.load_current", value=f"{load_current} A")],
        outputs=[NamedValue(name="output.loaded_voltage", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_internal_resistance_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    started_at, duration, measured = _capture_measurement(measure_internal_resistance)
    return _build_step(
        result_id=result_id,
        name="Internal Resistance",
        step_type="NumericLimit",
        spec_id="InternalResistance",
        measurement_value=measured,
        low_limit=_get_spec(specs, "internal_resistance_low_limit"),
        high_limit=_get_spec(specs, "internal_resistance_high_limit"),
        units="mΩ",
        inputs=[],
        outputs=[NamedValue(name="output.internal_resistance", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_capacity_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    started_at, duration, measured = _capture_measurement(measure_capacity)
    return _build_step(
        result_id=result_id,
        name="Cell Capacity",
        step_type="NumericLimit",
        spec_id="Capacity",
        measurement_value=measured,
        low_limit=_get_spec(specs, "capacity_low_limit_mah"),
        high_limit=_get_spec(specs, "capacity_high_limit_mah"),
        units="mAh",
        inputs=[NamedValue(name="input.charge_rate", value="1.0 A")],
        outputs=[NamedValue(name="output.measured_capacity", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_charge_voltage_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    max_charge = _get_spec(specs, "max_charge_voltage")
    started_at, duration, measured = _capture_measurement(measure_charge_voltage)
    return _build_step(
        result_id=result_id,
        name="End-of-Charge Voltage",
        step_type="NumericLimit",
        spec_id="EndOfChargeVoltage",
        measurement_value=measured,
        low_limit=max_charge - 0.05,
        high_limit=max_charge,
        units="V",
        inputs=[],
        outputs=[NamedValue(name="output.charge_voltage", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_discharge_cutoff_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    min_discharge = _get_spec(specs, "min_discharge_voltage")
    started_at, duration, measured = _capture_measurement(measure_discharge_cutoff_voltage)
    return _build_step(
        result_id=result_id,
        name="Discharge Cutoff Voltage",
        step_type="NumericLimit",
        spec_id="DischargeCutoffVoltage",
        measurement_value=measured,
        low_limit=min_discharge,
        high_limit=min_discharge + 0.2,
        units="V",
        inputs=[],
        outputs=[NamedValue(name="output.cutoff_voltage", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_weight_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    started_at, duration, measured = _capture_measurement(measure_weight)
    return _build_step(
        result_id=result_id,
        name="Cell Weight",
        step_type="NumericLimit",
        spec_id="CellWeight",
        measurement_value=measured,
        low_limit=_get_spec(specs, "weight_low_limit"),
        high_limit=_get_spec(specs, "weight_high_limit"),
        units="g",
        inputs=[],
        outputs=[NamedValue(name="output.weight", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _build_temperature_step(result_id: str, ctx: TestContext, specs: dict[str, str]) -> CreateStepRequest:
    ambient = float(ctx.work_item_properties.get("ambient_temp_c", "25.0"))
    started_at, duration, measured = _capture_measurement(measure_temperature, ambient)
    return _build_step(
        result_id=result_id,
        name="Temperature Under Discharge",
        step_type="NumericLimit",
        spec_id="TemperatureUnderDischarge",
        measurement_value=measured,
        low_limit=_get_spec(specs, "operating_temp_low"),
        high_limit=_get_spec(specs, "operating_temp_high"),
        units="°C",
        inputs=[NamedValue(name="input.ambient_temp", value=f"{ambient} °C")],
        outputs=[NamedValue(name="output.cell_surface_temp", value=str(measured))],
        part_number=ctx.part_number,
        duration=duration,
        started_at=started_at,
    )


def _create_running_result(tm_client: TestMonitorClient, ctx: TestContext, started_at: datetime) -> str:
    response = tm_client.create_results(
        [
            CreateResultRequest(
                program_name=PROGRAM_NAME,
                status=Status(status_type=StatusType.RUNNING),
                started_at=started_at,
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
    result_id = response.results[0].id
    logger.info("Created result %s (RUNNING)", result_id)
    return result_id


def _update_work_item_state(wi_client: WorkItemClient, work_item_id: str, state: str) -> None:
    wi_client.update_work_items(
        UpdateWorkItemsRequest(
            work_items=[UpdateWorkItemRequest(id=work_item_id, state=state)]
        )
    )
    logger.info("Work item %s -> %s", work_item_id, state)


def _collect_steps(result_id: str, ctx: TestContext, specs: dict[str, str]) -> tuple[list[CreateStepRequest], list[StatusType]]:
    builders = [
        _build_open_circuit_step,
        _build_under_load_step,
        _build_internal_resistance_step,
        _build_capacity_step,
        _build_charge_voltage_step,
        _build_discharge_cutoff_step,
        _build_weight_step,
        _build_temperature_step,
    ]

    steps: list[CreateStepRequest] = []
    statuses: list[StatusType] = []
    for builder in builders:
        step = builder(result_id, ctx, specs)
        steps.append(step)
        statuses.append(step.status.status_type)

    return steps, statuses


def _upload_result_log(
    file_client: FileClient,
    result_id: str,
    ctx: TestContext,
    steps: list[CreateStepRequest],
    statuses: list[StatusType],
) -> list[str]:
    log_path = Path(f"test_log_{result_id}.txt")
    _write_log(log_path, ctx, steps, statuses)

    file_ids: list[str] = []
    try:
        metadata = {
            "resultId": result_id,
            "workItemId": ctx.work_item_id,
            "minionId": ctx.system_id or "",
            "fileType": "test-log",
        }
        try:
            with open(log_path, "rb") as fp:
                file_id = file_client.upload_file(file=fp, metadata=metadata)
        except ApiException as ex:
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

    return file_ids


def _determine_final_status(statuses: list[StatusType]) -> StatusType:
    if any(status == StatusType.ERRORED for status in statuses):
        return StatusType.ERRORED
    if any(status == StatusType.FAILED for status in statuses):
        return StatusType.FAILED
    return StatusType.PASSED


def run_test(configuration: HttpConfiguration | None, ctx: TestContext) -> str:
    """Execute the battery test, publish results, and return the result ID."""
    tm_client = TestMonitorClient(configuration)
    wi_client = WorkItemClient(configuration)
    file_client = FileClient(configuration)

    test_start = datetime.now(timezone.utc)
    specs = ctx.spec_limits

    result_id = _create_running_result(tm_client, ctx, test_start)
    _update_work_item_state(wi_client, ctx.work_item_id, "IN_PROGRESS")

    steps, statuses = _collect_steps(result_id, ctx, specs)
    tm_client.create_steps(steps)
    logger.info("Published %d test steps", len(steps))

    total_time = (datetime.now(timezone.utc) - test_start).total_seconds()
    file_ids = _upload_result_log(file_client, result_id, ctx, steps, statuses)
    final_status = _determine_final_status(statuses)

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
    logger.info("Result %s updated -> %s (%.1fs)", result_id, final_status.value, total_time)

    _update_work_item_state(wi_client, ctx.work_item_id, "PENDING_APPROVAL")
    return result_id


def _write_log(
    path: Path,
    ctx: TestContext,
    steps: list[CreateStepRequest],
    statuses: list[StatusType],
) -> None:
    """Write a simple text log of the test execution."""

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"Test Log - {PROGRAM_NAME}\n")
        handle.write(f"Work Item: {ctx.work_item_id}\n")
        handle.write(f"Part: {ctx.part_number}  Serial: {ctx.serial_number}\n")
        handle.write(f"Operator: {ctx.operator}  Host: {ctx.host_name}\n")
        handle.write("-" * 50 + "\n")
        for step, status in zip(steps, statuses):
            parameters = step.data.parameters if step.data else []
            measurement = parameters[0] if parameters else None
            handle.write(
                f"  {step.name}: {status.value}"
                f"  measurement={measurement.measurement if measurement else 'N/A'}"
                f"  [{measurement.lowLimit}..{measurement.highLimit}] {measurement.units if measurement else ''}\n"
            )
