"""Configuration module for SystemLink connection."""

import os
import socket
import logging

from nisystemlink.clients.core import HttpConfiguration

logger = logging.getLogger(__name__)

PROGRAM_NAME = "18650 Battery Test"
PART_NUMBER = "B0CG1KL3RC"

# 18650 battery product specifications — used as defaults when creating the product.
# Limits are sourced from product properties at runtime (not these constants).
PRODUCT_SPECS = {
    "spec.nominal_voltage": "3.7",
    "spec.nominal_voltage_units": "V",
    "spec.voltage_low_limit": "2.5",
    "spec.voltage_high_limit": "4.2",
    "spec.nominal_capacity_mah": "2500",
    "spec.capacity_low_limit_mah": "2250",
    "spec.capacity_high_limit_mah": "2750",
    "spec.max_charge_voltage": "4.2",
    "spec.max_charge_voltage_units": "V",
    "spec.min_discharge_voltage": "2.5",
    "spec.min_discharge_voltage_units": "V",
    "spec.max_continuous_discharge_current": "5.0",
    "spec.max_continuous_discharge_current_units": "A",
    "spec.internal_resistance_low_limit": "10",
    "spec.internal_resistance_high_limit": "80",
    "spec.internal_resistance_units": "mΩ",
    "spec.weight_low_limit": "40",
    "spec.weight_high_limit": "50",
    "spec.weight_units": "g",
    "spec.operating_temp_low": "-20",
    "spec.operating_temp_high": "60",
    "spec.operating_temp_units": "°C",
}


def get_configuration(
    server: str | None = None,
    api_key: str | None = None,
) -> HttpConfiguration | None:
    """Build HttpConfiguration.

    Priority:
      1. Explicit ``server`` / ``api_key`` args (CLI flags for dev use).
      2. ``SYSTEMLINK_SERVER_URI`` / ``SYSTEMLINK_API_KEY`` env vars.
      3. ``None`` — the SDK auto-discovers credentials on a managed system.
    """
    server = server or os.environ.get("SYSTEMLINK_SERVER_URI")
    api_key = api_key or os.environ.get("SYSTEMLINK_API_KEY")

    if server and api_key:
        logger.info("Using explicit server configuration: %s", server)
        return HttpConfiguration(server_uri=server, api_key=api_key)

    logger.info("No explicit credentials — using SystemLink system credentials")
    return None


def get_hostname() -> str:
    return socket.gethostname()
