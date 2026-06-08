"""
Sensor backends for Endymion.

Each backend produces a single normalised 'presence' value in [0.0, 1.0]
updated at ~30 Hz.  0.0 = no presence / full motion; 1.0 = still presence.
"""

from .base import BaseSensor

__all__ = ["BaseSensor"]
