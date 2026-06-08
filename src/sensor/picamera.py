"""
Raspberry Pi NoIR Camera sensor backend.

Uses picamera2 (Pi 5 camera library) to read frames from the CSI-connected
Pi Camera Module NoIR and applies the same frame-differencing logic as
CameraSensor. Works in darkness when paired with an IR illuminator.

Prerequisites on the Pi:
    sudo apt install python3-picamera2
    sudo raspi-config  →  Interface Options → Camera → Enable

Status: STUB — implement when the Pi Camera Module arrives.
"""

from .base import BaseSensor


class PiCameraSensor(BaseSensor):
    """
    Frame-differencing presence detector using the Pi Camera Module (CSI).

    Functionally identical to CameraSensor but uses picamera2 instead of
    OpenCV's VideoCapture, which is required for the CSI camera on Pi 5.

    Args:
        motion_threshold: Mean pixel diff that registers as fully moving.
        noise_floor: Baseline noise to subtract before computing presence.
        resolution: Capture resolution as (width, height). Smaller = faster.
    """

    def __init__(
        self,
        motion_threshold: float = 5.0,
        noise_floor: float = 1.0,
        resolution: tuple[int, int] = (640, 480),
    ) -> None:
        self._motion_threshold = motion_threshold
        self._noise_floor = noise_floor
        self._resolution = resolution
        self._camera = None
        self._prev_gray = None

    def start(self) -> None:
        # TODO: initialise picamera2
        # from picamera2 import Picamera2
        # self._camera = Picamera2()
        # self._camera.configure(self._camera.create_preview_configuration(
        #     main={"size": self._resolution, "format": "RGB888"}
        # ))
        # self._camera.start()
        raise NotImplementedError(
            "PiCameraSensor is not yet implemented. "
            "Install picamera2, enable the camera interface, and complete "
            "this class when the Pi Camera Module arrives."
        )

    def stop(self) -> None:
        # TODO: self._camera.stop()
        pass

    def read(self) -> float:
        # TODO: capture frame, convert to grayscale, frame-diff, return presence
        return 0.0
