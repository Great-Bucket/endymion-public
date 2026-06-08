# Spec: `PresenceSignal` — Three-Phase Presence Smoother

## Context

This spec defines the intended behaviour of the `PresenceSignal` class in `src/utils/signal.py`.

`PresenceSignal` is the core temporal logic of Endymion. It sits between the raw sensor (which reads frame-by-frame motion from the webcam or Kinect) and the visual effects pipeline (which drives luminosity, vignette, ghosting, etc.). Its job is to translate a noisy, instantaneous sensor reading into a smooth, weighted presence value that feels experientially meaningful to the viewer.

The design is deliberately asymmetric and punitive toward movement. This is not a neutral smoother — it encodes the conceptual logic of the piece: **stillness must be earned, and movement carries a real cost.** A viewer who fidgets or glances away does not get to "coast" at partial brightness. The image retreats fully, holds in darkness, and only slowly returns as the viewer re-commits to stillness.

The three-phase model — fall, hold, rise — is the minimum structure needed to express this logic in time. The fall is fast (movement is immediately felt). The hold is unconditional (even becoming still again does not help until the debt is paid). The rise is slow (brightness is a reward for sustained attention, not a reflex).

---

## Purpose

Translate a raw, noisy sensor value (0.0 = full motion, 1.0 = full stillness) into a smooth, asymmetric presence value that drives visual effects. The core design intent: **movement is punished quickly and the penalty lasts long enough that the viewer must commit to genuine, sustained stillness before brightness returns.**

---

## Three Phases

### Phase 1 — FALLING
**Trigger**: raw sensor value drops below `motion_trigger` (default 0.7).

- Apply a fast EMA toward the raw value using `alpha_fall` (derived from `fall_window`, default 0.4 seconds).
- Reset the hold clock to `now`.
- The value drops quickly — not instantly, but within a fraction of a second.

### Phase 2 — HOLDING
**Trigger**: raw is above `motion_trigger` (viewer appears still) but fewer than `hold_duration` seconds (default 2.0s) have elapsed since the last motion event.

- The smoothed value is **completely frozen** — no change whatsoever, neither up nor down.
- This is a hard lockout. The viewer cannot "earn" any brightness during this window no matter how still they are.

**Re-trigger during HOLD**: if new motion is detected while in the hold window:
- The hold clock **resets** — the full `hold_duration` is owed again from the new motion event.
- The value **continues to fall** (applies `alpha_fall` toward the new low raw value) — compounding the penalty. Repeated or sustained motion drives the value progressively lower.

### Phase 3 — RISING
**Trigger**: raw is above `motion_trigger` AND `hold_duration` has fully elapsed since the last motion event.

- Apply a slow EMA toward the raw value using `alpha_rise` (derived from `rise_window`, default 3.0 seconds).
- The value climbs gradually. The viewer must sustain stillness for several seconds to recover full brightness.

---

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `fall_window` | 0.4s | Time constant for descent — how fast the value drops on motion |
| `hold_duration` | 2.0s | Seconds the value is frozen after the last motion event |
| `rise_window` | 3.0s | Time constant for ascent — how slowly brightness recovers |
| `motion_trigger` | 0.7 | Raw value below which motion is considered detected |
| `fps` | 24.0 | Expected update rate, used to compute EMA alpha values. Derived from the video file at runtime — do not hardcode 30. |

---

## State Machine Summary

```
[any state]
    raw < motion_trigger
        → FALLING: apply alpha_fall, reset hold clock

FALLING or HOLDING
    raw >= motion_trigger AND time_since_last_motion < hold_duration
        → HOLDING: freeze value (no update)

HOLDING
    raw < motion_trigger (motion again during hold)
        → FALLING: apply alpha_fall, reset hold clock (full 2s owed again)

HOLDING
    time_since_last_motion >= hold_duration AND raw >= motion_trigger
        → RISING: apply alpha_rise

RISING
    raw < motion_trigger
        → FALLING: apply alpha_fall, reset hold clock
```

---

## Known Issue in Previous Implementation

The version prior to the fix applied `alpha_fall` during the HOLD phase even when the viewer was still. Because `alpha_fall` is fast and `raw` was high (viewer now still), it was actively pulling the value upward — the opposite of intended. The value was "rocketing" toward brightness during what should have been a locked dark period. The fix (`pass` during hold) is correct in concept, but if the hold is not being experienced as long enough in practice, the likely causes are:

1. The fall is not reaching a low enough nadir before freezing (brief motion = shallow drop).
2. The `hold_duration` needs further increase beyond 2.0s.
3. The `motion_trigger` threshold is too high — minor sensor noise is being classified as stillness, cutting the fall short.
