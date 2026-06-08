"""
Luminosity signal models for Endymion.

Two models are available:

  PresenceSignal — EMA-based smoother (legacy). The sensor value is
      continuously tracked; luminosity follows presence in real time with
      asymmetric rise/fall windows and a nadir hold period.

  PenaltyRoutine — event-triggered model (preferred). The sensor value is
      used only as a binary trigger. Motion fires a self-contained penalty
      routine that snaps to near-black, holds for a fixed duration, then
      recovers along an ease-in curve. The image has its own gravity — it
      does not follow the viewer moment-to-moment.

      BRIGHT      — full brightness, waiting for first trigger
      FALLING     — fast EMA snap toward nadir
      HOLDING     — frozen at nadir for hold_duration seconds
      RECOVERING  — slow ease-in climb back to full brightness

  Any motion re-detected during FALLING, HOLDING, or RECOVERING resets the
  full hold clock and snaps the value back toward nadir.
"""

from __future__ import annotations

import time

BRIGHT = "BRIGHT"
FALLING = "FALLING"
HOLDING = "HOLDING"
RISING = "RISING"
RECOVERING = "RECOVERING"


def _alpha(window_seconds: float, fps: float) -> float:
    """EMA alpha derived from a desired time-constant in seconds."""
    return 1.0 - pow(0.01, 1.0 / max(window_seconds * fps, 1e-6))


class PresenceSignal:
    """
    Three-phase asymmetric smoother: fall → hold → rise.

    Args:
        fall_window:    Time constant (s) for dropping toward black.
                        Short = sharp fall. Typically 0.3–0.6s.
        hold_duration:  Minimum seconds locked at nadir after last motion
                        before any rise is permitted. Typically 1–3s.
        rise_window:    Time constant (s) for climbing back to brightness.
                        Long = viewer must sustain stillness. Typically 3–6s.
        motion_trigger: Raw value below this is treated as motion.
                        0.7 catches real motion but ignores sensor noise.
        fps:            Expected update rate in Hz.

    Example:
        signal = PresenceSignal(fall_window=0.4, hold_duration=2.0, rise_window=3.0)
        while True:
            raw = sensor.read()
            smoothed = signal.update(raw)
            player.render(smoothed)
    """

    def __init__(
        self,
        fall_window: float = 0.4,
        hold_duration: float = 2.0,
        rise_window: float = 3.0,
        motion_trigger: float = 0.7,
        fps: float = 30.0,
    ) -> None:
        self._alpha_fall = _alpha(fall_window, fps)
        self._alpha_rise = _alpha(rise_window, fps)
        self._hold_duration = hold_duration
        self._motion_trigger = motion_trigger
        self._value: float = 0.0
        self._phase: str = RISING
        # Initialise far in the past so we start in "rising allowed" state.
        self._last_motion_time: float = -float("inf")

    def update(self, raw: float) -> float:
        """
        Process one raw sample and return the smoothed presence value.

        Args:
            raw: Sensor output in [0.0, 1.0].

        Returns:
            Smoothed presence value in [0.0, 1.0].
        """
        now = time.monotonic()

        if raw < self._motion_trigger:
            # Motion detected — fall and reset the hold clock.
            # Applies in any phase, including mid-HOLD (resets the debt).
            self._last_motion_time = now
            self._value = self._alpha_fall * raw + (1.0 - self._alpha_fall) * self._value
            self._phase = FALLING
        elif (now - self._last_motion_time) < self._hold_duration:
            # Hold period — freeze at nadir; no rise permitted yet
            self._phase = HOLDING
        else:
            # Hold elapsed and viewer is still — allow slow rise
            self._value = self._alpha_rise * raw + (1.0 - self._alpha_rise) * self._value
            self._phase = RISING

        return self._value

    @property
    def value(self) -> float:
        """Current smoothed value without updating."""
        return self._value

    @property
    def phase(self) -> str:
        """Current phase: FALLING, HOLDING, or RISING."""
        return self._phase


class PenaltyRoutine:
    """
    Event-triggered luminosity penalty.

    The sensor is used only as a binary trigger. Once motion is detected
    the routine runs its own internal clock — the image has its own gravity
    and does not follow the viewer moment-to-moment.

    Args:
        motion_trigger:    Raw value below which motion is detected (0–1).
        nadir:             Target luminosity at the bottom of the penalty.
                           0.02 = nearly black, a ghost of the image.
        fall_window:       EMA time constant (s) for the snap to nadir.
                           Short = sharp drop. 0.3s is nearly instant.
        hold_duration:     Seconds frozen at nadir after last motion.
                           Recovery cannot begin until this elapses.
        recovery_duration: Total time (s) to climb from nadir to full
                           brightness once hold has elapsed.
        recovery_curve:    Power exponent for the recovery curve.
                           > 1.0 = ease-in: lingers in darkness, then
                           accelerates toward brightness. 2.5 spends
                           ~70% of recovery time below half-brightness.
        fps:               Expected update rate in Hz.
    """

    def __init__(
        self,
        motion_trigger: float = 0.7,
        nadir: float = 0.02,
        fall_window: float = 0.3,
        hold_duration: float = 3.0,
        recovery_duration: float = 8.0,
        recovery_curve: float = 2.5,
        fps: float = 30.0,
    ) -> None:
        self._motion_trigger = motion_trigger
        self._nadir = nadir
        self._alpha_fall = _alpha(fall_window, fps)
        self._hold_duration = hold_duration
        self._recovery_duration = recovery_duration
        self._recovery_curve = recovery_curve

        self._value: float = 1.0
        self._phase: str = BRIGHT
        self._triggered: bool = False
        self._last_motion: float = 0.0
        self._recovery_started: float | None = None

    def update(self, raw: float) -> float:
        """
        Process one raw sensor sample and return the current luminosity value.

        Args:
            raw: Sensor output in [0.0, 1.0]. Only its relation to
                 motion_trigger matters — the magnitude is not tracked.

        Returns:
            Luminosity value in [nadir, 1.0].
        """
        now = time.monotonic()

        if raw < self._motion_trigger:
            # Motion detected — snap toward nadir and reset the hold clock.
            # Fires from any phase; mid-recovery re-triggers a full penalty.
            self._triggered = True
            self._last_motion = now
            self._recovery_started = None
            self._value = self._alpha_fall * self._nadir + (1.0 - self._alpha_fall) * self._value
            self._phase = FALLING

        elif not self._triggered:
            # Penalty has never fired — stay at full brightness.
            self._value = 1.0
            self._phase = BRIGHT

        else:
            time_since_motion = now - self._last_motion

            if time_since_motion < self._hold_duration:
                # Within the hold window.
                if self._value > self._nadir + 0.005:
                    # Still falling toward nadir.
                    self._value = self._alpha_fall * self._nadir + (1.0 - self._alpha_fall) * self._value
                    self._phase = FALLING
                else:
                    # At nadir — lock until hold elapses.
                    self._value = self._nadir
                    self._phase = HOLDING

            else:
                # Hold has elapsed — begin recovery.
                if self._recovery_started is None:
                    self._recovery_started = now

                elapsed = now - self._recovery_started
                t = min(elapsed / self._recovery_duration, 1.0)
                # Ease-in curve: slow out of darkness, faster near brightness.
                curved_t = t ** self._recovery_curve
                self._value = self._nadir + (1.0 - self._nadir) * curved_t

                if t >= 1.0:
                    self._value = 1.0
                    self._phase = BRIGHT
                else:
                    self._phase = RECOVERING

        return self._value

    @property
    def value(self) -> float:
        """Current luminosity value without updating."""
        return self._value

    @property
    def phase(self) -> str:
        """Current phase: BRIGHT, FALLING, HOLDING, or RECOVERING."""
        return self._phase
