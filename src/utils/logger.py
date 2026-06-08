"""
Session data logger.

When LOG_FILE is set, writes one CSV row per frame containing:
    t        — elapsed seconds since start
    raw      — raw sensor value
    smooth   — smoothed presence value
    <effect> — one column per active effect showing its computed value

Use for short calibration runs (30–60s) to review sensor behaviour
and effect response without relying on subjective real-time observation.

Example CSV output (EFFECTS=luminosity,vignette):
    t,raw,smooth,lum,vig_sigma
    0.033,0.00,0.00,0.05,0.25
    0.066,0.82,0.21,0.24,1.17
    ...
"""

import csv
import time
from pathlib import Path


class SessionLogger:
    """Writes per-frame sensor + effect values to a CSV file."""

    def __init__(
        self,
        path: str,
        effect_names: list[str],
        diagnostic_names: list[str] | None = None,
    ) -> None:
        self._path = Path(path)
        self._effect_names = effect_names
        self._diagnostic_names = list(diagnostic_names or [])
        self._file = None
        self._writer = None
        self._start = None

    def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(
            ["t", "raw", "smooth"] + self._effect_names + self._diagnostic_names
        )
        self._start = time.monotonic()
        print(f"[Logger] Writing session data to {self._path}")

    def log(
        self,
        raw: float,
        smooth: float,
        effect_values: list[float],
        diagnostic_values: list | None = None,
    ) -> None:
        if self._writer is None or self._start is None:
            return
        t = round(time.monotonic() - self._start, 4)
        diag = diagnostic_values or [None] * len(self._diagnostic_names)
        diag_cells = ["" if v is None else round(float(v), 4) for v in diag]
        self._writer.writerow(
            [t, round(raw, 4), round(smooth, 4)]
            + [round(v, 4) for v in effect_values]
            + diag_cells
        )

    def stop(self) -> None:
        if self._file is not None:
            self._file.flush()
            self._file.close()
            print(f"[Logger] Session saved to {self._path}")


class NullLogger:
    """Drop-in replacement when logging is disabled."""

    def start(self) -> None: pass
    def log(
        self,
        raw: float,
        smooth: float,
        effect_values: list[float],
        diagnostic_values: list | None = None,
    ) -> None: pass
    def stop(self) -> None: pass
