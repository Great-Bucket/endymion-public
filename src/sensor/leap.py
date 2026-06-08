"""
Leap Motion sensor backend.

Requires the Ultraleap Gemini tracking service and the leapc-cffi Python
bindings.  See docs/SETUP.md for installation instructions.

Starting point: review hackathon code from ~2 months ago and migrate the
working Leap polling logic into the read() method below.
"""

from .base import BaseSensor


class LeapSensor(BaseSensor):
    """
    Reads hand/presence data from a connected Leap Motion controller.

    Presence is derived from hand stability — a still hand close to the
    sensor reads near 1.0; no hands or rapid movement reads near 0.0.
    """

    def __init__(self, smoothing_window: float = 3.0) -> None:
        self._smoothing_window = smoothing_window
        self._connection = None  # leapc_cffi connection object

    def start(self) -> None:
        # TODO: initialise leapc_cffi connection
        # from leapc_cffi import leapc
        # self._connection = leapc.create_connection()
        raise NotImplementedError("Wire up leapc_cffi — see hackathon code")

    def stop(self) -> None:
        if self._connection is not None:
            # TODO: self._connection.close()
            self._connection = None

    def read(self) -> float:
        # TODO: poll latest frame, derive stillness value
        # hands = self._connection.get_last_frame().hands
        # ...
        raise NotImplementedError("Wire up leapc_cffi — see hackathon code")
