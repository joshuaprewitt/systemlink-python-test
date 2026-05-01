"""Simulated battery measurements for 18650 cell testing.

Generates realistic measurement values with configurable noise. Replace this
module with real instrument drivers for production use.

All measurement functions accept an optional ``temp_c`` (ambient temperature in
°C). Li-ion cells degrade significantly below 0°C: internal resistance rises,
capacity drops, and voltage limits shift — producing out-of-spec results at
extreme cold. Valid range: -25 to 60°C.
"""

import random


def _noisy(nominal: float, pct_noise: float = 0.02) -> float:
    """Return *nominal* ± *pct_noise* percent random variation."""
    delta = nominal * pct_noise
    return round(nominal + random.uniform(-delta, delta), 4)


def measure_open_circuit_voltage(temp_c: float = 25.0) -> float:
    """Simulate OCV of a charged 18650 cell (V).

    OCV drops slightly at cold temperatures (~3 mV/°C below 0°C).
    """
    cold_drop = max(0.0, -temp_c) * 0.003
    return _noisy(3.7 - cold_drop, 0.03)


def measure_voltage_under_load(load_current_a: float, temp_c: float = 25.0) -> float:
    """Simulate terminal voltage under *load_current_a* amps (V).

    DC internal resistance (nominally higher than AC IR) follows an
    Arrhenius-like exponential: doubles roughly every 30°C below 25°C.
    Nominal DC IR: 50 mΩ at 25°C; ~89 mΩ at 0°C; ~159 mΩ at −25°C.
    """
    cold_delta = max(0.0, 25.0 - temp_c)
    ir_mohm = 50.0 * (2.0 ** (cold_delta / 30.0))
    ir_drop = load_current_a * ir_mohm / 1000.0
    return _noisy(3.7 - ir_drop, 0.02)


def measure_internal_resistance(temp_c: float = 25.0) -> float:
    """Simulate AC internal resistance (mΩ).

    Arrhenius-like exponential model: resistance roughly doubles every 30°C
    below 25°C. At 0°C ~80 mΩ (at the high limit); at −25°C ~143 mΩ, well
    above it. A modest +0.5%/°C increase applies above 45°C.
    """
    cold_delta = max(0.0, 25.0 - temp_c)
    cold_factor = 2.0 ** (cold_delta / 30.0)
    heat_factor = 1.0 + max(0.0, temp_c - 45.0) * 0.005
    return _noisy(45.0 * cold_factor * heat_factor, 0.15)


def measure_capacity(temp_c: float = 25.0) -> float:
    """Simulate charge/discharge capacity (mAh).

    Piecewise model reflecting measured Li-ion behaviour:
    - 0–35°C: full rated capacity.
    - Above 35°C: 0.4%/°C loss; at 60°C ~2250 mAh (at the low limit).
    - 0°C to −10°C: 1.2%/°C loss (gentle derating near freezing);
      at −10°C ~2200 mAh, just below the 2250 mAh low limit.
    - Below −10°C: 2.5%/°C additional loss; at −25°C ~1260 mAh (~50%).
    """
    if temp_c >= 35.0:
        derating_factor = 1.0 - (temp_c - 35.0) * 0.004
    elif temp_c >= 0.0:
        derating_factor = 1.0
    elif temp_c >= -10.0:
        derating_factor = 1.0 + temp_c * 0.012  # temp_c is negative
    else:
        derating_factor = 0.88 + (temp_c + 10.0) * 0.025  # (temp_c + 10) is negative
    nominal = 2500.0 * max(0.3, derating_factor)
    return _noisy(nominal, 0.05)


def measure_charge_voltage(temp_c: float = 25.0) -> float:
    """Simulate end-of-charge voltage (V).

    BMS reduces charge target at cold (~3 mV/°C below 0°C). At -25°C the
    measured voltage (~4.10 V) falls below the lower limit (max_charge − 0.05).
    """
    cold_drop = max(0.0, -temp_c) * 0.003
    return _noisy(4.18 - cold_drop, 0.005)


def measure_discharge_cutoff_voltage(temp_c: float = 25.0) -> float:
    """Simulate end-of-discharge cutoff voltage (V).

    Voltage sags more at cold; battery hits cutoff at a higher voltage
    (+8 mV/°C below 0°C). At -25°C (~2.75 V) exceeds the 2.70 V high limit.
    """
    cold_rise = max(0.0, -temp_c) * 0.008
    return _noisy(2.55 + cold_rise, 0.02)


def measure_weight() -> float:
    """Simulate cell weight measurement (g). Not temperature-dependent."""
    return _noisy(46.0, 0.03)


def measure_temperature(ambient_c: float = 25.0) -> float:
    """Simulate cell surface temperature during discharge (°C).

    Self-heating adds ~8°C above ambient. At ambient ≥ 52°C the surface
    temperature exceeds the 60°C high limit.
    """
    return _noisy(ambient_c + 8.0, 0.10)

