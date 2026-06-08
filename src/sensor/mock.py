"""
Mock sensor for testing without any physical hardware.

Generates a simulated presence signal that slowly oscillates between
0.0 (moving) and 1.0 (still) using a sine wave, so the full effect
pipeline can be exercised on the Pi before a real sensor is connected.

Usage:
    SENSOR_TYPE=mock python main.py
    SENSOR_TYPE=mock MOCK_PERIOD=20.0 python main.py  # slower cycle
"""

import math
import time

from .base import BaseSensor


class MockSensor(BaseSensor):
    """
    Simulated presence sensor — no hardware required.

    Produces a sine-wave presence signal that completes one full
    cycle every `period` seconds: still → moving → still → ...

    Args:
        period: Seconds for one full oscillation cycle (default 10s).
        offset: Phase offset in seconds (default 0 — starts at mid-point).
    """

    def __init__(self, period: float = 10.0, offset: float = 0.0) -> None:
        self._period = period
        self._offset = offset
        self._start: float = 0.0

    def start(self) -> None:
        self._start = time.monotonic()

    def stop(self) -> None:
        pass

    def read(self) -> float:
        elapsed = time.monotonic() - self._start + self._offset
        # Sine oscillates -1 to 1 — remap to 0.0–1.0
        raw = 0.5 + 0.5 * math.sin(2 * math.pi * elapsed / self._period)
        return float(raw)
