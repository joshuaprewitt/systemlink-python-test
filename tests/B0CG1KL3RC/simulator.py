"""Simulated battery measurements for 18650 cell testing.

Generates realistic measurement values with configurable noise. Replace this
module with real instrument drivers for production use.
"""

import random


def _noisy(nominal: float, pct_noise: float = 0.02) -> float:
    """Return *nominal* ± *pct_noise* percent random variation."""
    delta = nominal * pct_noise
    return round(nominal + random.uniform(-delta, delta), 4)


def measure_open_circuit_voltage() -> float:
    """Simulate OCV measurement of a charged 18650 cell (V)."""
    return _noisy(3.7, 0.03)


def measure_voltage_under_load(load_current_a: float) -> float:
    """Simulate terminal voltage under *load_current_a* amps (V).

    Models a ~50 mΩ internal resistance voltage drop.
    """
    ocv = 3.7
    ir_drop = load_current_a * 0.050
    return _noisy(ocv - ir_drop, 0.02)


def measure_internal_resistance() -> float:
    """Simulate AC internal resistance measurement (mΩ)."""
    return _noisy(45.0, 0.15)


def measure_capacity(charge_rate_a: float = 1.0) -> float:
    """Simulate a charge/discharge capacity measurement (mAh)."""
    return _noisy(2500.0, 0.05)


def measure_charge_voltage() -> float:
    """Simulate end-of-charge voltage (V)."""
    return _noisy(4.18, 0.005)


def measure_discharge_cutoff_voltage() -> float:
    """Simulate end-of-discharge cutoff voltage (V)."""
    return _noisy(2.55, 0.02)


def measure_weight() -> float:
    """Simulate cell weight measurement (g)."""
    return _noisy(46.0, 0.03)


def measure_temperature(ambient_c: float = 25.0) -> float:
    """Simulate cell surface temperature during discharge (°C)."""
    return _noisy(ambient_c + 8.0, 0.10)
