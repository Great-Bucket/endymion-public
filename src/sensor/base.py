"""Abstract base class for all sensor backends."""

from abc import ABC, abstractmethod


class BaseSensor(ABC):
    """
    Common interface every sensor backend must implement.

    Subclasses produce a single normalised 'presence' value:
        0.0 — no presence, or viewer is moving
        1.0 — viewer is present and still

    The value should update at approximately 30 Hz and be smoothed
    externally via utils.signal before being passed to the visual layer.
    """

    @abstractmethod
    def start(self) -> None:
        """Open the sensor hardware / connection."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Release the sensor hardware / connection."""
        ...

    @abstractmethod
    def read(self) -> float:
        """
        Return the current raw presence value in [0.0, 1.0].

        Called once per frame. Must not block for more than ~10 ms.
        """
        ...

    def __enter__(self) -> "BaseSensor":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()
