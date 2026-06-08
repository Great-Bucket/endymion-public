"""
Camera-based motion detection sensor backend.

Uses frame differencing via OpenCV to produce a presence/stillness value.
Good for development on the MacBook M4 webcam before dedicated hardware
is wired up.

Presence value:
    High motion delta  → value near 0.0 (viewer is moving)
    Low motion delta   → value near 1.0 (viewer is still)
    No frames / error  → 0.0
"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseSensor


class CameraSensor(BaseSensor):
    """Frame-differencing presence detector using any OpenCV-compatible camera."""

    def __init__(
        self,
        device_index: int = 0,
        motion_threshold: float = 5.0,
        noise_floor: float = 1.0,
    ) -> None:
        """
        Args:
            device_index: OpenCV camera index (0 = default/built-in webcam).
            motion_threshold: Mean pixel diff *above the noise floor* that
                registers as fully moving. Tune experimentally.
            noise_floor: Baseline sensor noise — the mean diff you observe
                when the camera is completely covered and nothing is moving.
                Subtract this before computing presence so true stillness = 1.0.
                Typical values: 0.5–2.0 depending on the camera.
        """
        self._device_index = device_index
        self._motion_threshold = motion_threshold
        self._noise_floor = noise_floor
        self._cap: cv2.VideoCapture | None = None
        self._prev_gray: np.ndarray | None = None

    def start(self) -> None:
        # Use AVFoundation backend explicitly on macOS to avoid Continuity Camera
        # (iPhone) being selected over the built-in FaceTime webcam.
        self._cap = cv2.VideoCapture(self._device_index, cv2.CAP_AVFOUNDATION)
        if not self._cap.isOpened():
            # Fall back to default backend if AVFoundation isn't available (e.g. Pi)
            self._cap = cv2.VideoCapture(self._device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera at index {self._device_index}")
        self._prev_gray = None

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def read(self) -> float:
        if self._cap is None:
            return 0.0

        ret, frame = self._cap.read()
        if not ret:
            return 0.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            return 0.0

        diff = cv2.absdiff(gray, self._prev_gray).astype(np.float32)
        self._prev_gray = gray

        motion = float(diff.mean())
        # Subtract baseline sensor noise so true stillness maps to 1.0
        adjusted = max(0.0, motion - self._noise_floor)
        presence = max(0.0, 1.0 - adjusted / self._motion_threshold)
        return min(1.0, presence)
