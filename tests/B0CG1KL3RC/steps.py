"""Reusable step-building infrastructure for SystemLink test applications.

Provides helpers for capturing measurements, evaluating pass/fail status,
reading spec limits, and constructing CreateStepRequest objects. These are
test-agnostic and can be imported by any test module.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Callable

from nisystemlink.clients.testmonitor.models import (
    CreateStepRequest,
    Measurement,
    NamedValue,
    Status,
    StatusType,
    StepData,
)

logger = logging.getLogger(__name__)


def get_spec(specs: dict[str, str], key: str) -> float:
    """Read a numeric limit from resolved specs with a ``spec.`` prefix fallback."""
    candidates = [key, f"spec.{key}"] if not key.startswith("spec.") else [key, key[5:]]
    for source in (specs,):
        for candidate in candidates:
            v = source.get(candidate)
            if v not in (None, ""):
                return float(v)
    raise RuntimeError(f"Missing spec: {key}")


def compare_gele(value: float, low: float, high: float) -> StatusType:
    """GELE comparison: PASSED if low <= value <= high."""
    return StatusType.PASSED if low <= value <= high else StatusType.FAILED


def capture_measurement(
    measure_fn: Callable[..., float],
    *args,
) -> tuple[datetime, float, float]:
    """Call *measure_fn* and return ``(started_at, duration_s, value)``."""
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    value = measure_fn(*args)
    duration = time.monotonic() - t0
    return started_at, duration, value


def build_step(
    result_id: str,
    name: str,
    step_type: str,
    spec_id: str,
    measurement_value: float,
    low_limit: float,
    high_limit: float,
    units: str,
    part_number: str,
    duration: float,
    started_at: datetime,
    inputs: list[NamedValue] | None = None,
    outputs: list[NamedValue] | None = None,
) -> CreateStepRequest:
    """Build a :class:`CreateStepRequest` with limits and measurement metadata."""
    status_type = compare_gele(measurement_value, low_limit, high_limit)
    return CreateStepRequest(
        step_id=spec_id,
        result_id=result_id,
        name=name,
        step_type=step_type,
        status=Status(status_type=status_type),
        total_time_in_seconds=duration,
        started_at=started_at,
        inputs=inputs or [],
        outputs=outputs or [],
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
