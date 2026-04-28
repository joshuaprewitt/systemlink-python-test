"""Configuration module for SystemLink connection."""

import os
import socket
import logging

from nisystemlink.clients.core import HttpConfiguration

logger = logging.getLogger(__name__)

PROGRAM_NAME = "18650 Battery Test"
PART_NUMBER = "B0CG1KL3RC"

# Product characteristics belong on the product record.
PRODUCT_CHARACTERISTICS = {
    "cell_type": "Cylindrical",
    "nom_volt": "3.7",
    "Capacity": "3600",
    "Symbol": "Battery Cell",
    "(NewField_468e015f-0)": "45",
    "(NewField_4f156673-f)": "18x65",
}

# 18650 battery test limits used as local fallbacks.
# Primary limits should come from Specification API records linked to the product.
PRODUCT_SPECS = {
    "voltage_low_limit": "2.5",
    "voltage_high_limit": "4.2",
    "capacity_low_limit_mah": "2250",
    "capacity_high_limit_mah": "2750",
    "max_charge_voltage": "4.2",
    "min_discharge_voltage": "2.5",
    "max_continuous_discharge_current": "5.0",
    "internal_resistance_low_limit": "10",
    "internal_resistance_high_limit": "80",
    "weight_low_limit": "40",
    "weight_high_limit": "50",
    "operating_temp_low": "-20",
    "operating_temp_high": "60",
}

# Maps runtime limit keys to linked spec IDs and the limit field to read.
SPEC_LIMIT_BINDINGS = {
    "voltage_low_limit": ("OutputVoltage", "min"),
    "voltage_high_limit": ("OutputVoltage", "max"),
    "max_continuous_discharge_current": ("MaxContinuousDischargeCurrent", "max"),
    "min_discharge_voltage": ("DischargeCutoffVoltage", "min"),
    "internal_resistance_low_limit": ("InternalResistance", "min"),
    "internal_resistance_high_limit": ("InternalResistance", "max"),
    "capacity_low_limit_mah": ("Capacity", "min"),
    "capacity_high_limit_mah": ("Capacity", "max"),
    "max_charge_voltage": ("EndOfChargeVoltage", "max"),
    "weight_low_limit": ("CellWeight", "min"),
    "weight_high_limit": ("CellWeight", "max"),
    "operating_temp_low": ("TemperatureUnderDischarge", "min"),
    "operating_temp_high": ("TemperatureUnderDischarge", "max"),
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
