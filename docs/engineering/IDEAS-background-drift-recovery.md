# Idea: Background Drift Recovery

**Status:** Not implemented. Specced here for reference in case background drift
proves to be a problem during the gallery event or a future deployment.

**Decision context:** After the 2026-05-14 soak test, this feature was designed,
discussed, and deliberately deferred. The reasoning: the event is 3 hours, the
artist is present, the failure mode is visible, and a manual restart takes 10
seconds. Adding automated recalibration whose benefit depends on visitor gaps
introduces complexity without guaranteed payoff. If drift becomes a demonstrated
problem in the field, implement this spec.

---

## The Problem It Solves

The Kinect background model is captured once at startup and never updated. If
ambient IR conditions change during a session — sunlight decreasing, gallery
lights being switched on or off, sensor temperature shifts — the stored background
can become mismatched with the empty room's actual depth readings. This produces
phantom foreground: the sensor "sees" the empty cave as occupied.

The consequence is visible: the video stays bright when the cave is empty, or
oscillates between bright and dark with no one present. Full analysis in
`docs/SOAK-TEST-REPORT-20260514.md`.

The fix is simple conceptually: recapture the background when you know the cave
is empty. Between-visitor recalibration does this automatically during the natural
gaps between gallery visitors.

---

## How It Works

**Single trigger — empty-cave idle timer:**

Every sensor frame, if `n_fg < KINECT_MIN_FG_PIXELS` (the cave reads as empty),
increment a running timer. If the cave reads as occupied, reset the timer to zero.
If the timer reaches `KINECT_RECAL_EMPTY_S` seconds of *continuous* empty
readings, call `calibrate()` and reset the timer.

`calibrate()` already exists in `KinectSensor`. It captures 30 depth frames,
computes their pixel-wise mean, and stores the result as `self._background`. It
takes approximately 1–2 seconds and prints `[Kinect] Background captured.`

**In pseudocode:**

```python
# In KinectSensor.__init__:
self._empty_since: float | None = None  # wall-clock time cave first read empty

# In KinectSensor.read(), after the n_fg < min_fg_pixels check:
if n_fg < self._min_fg_pixels:
    now = time.monotonic()
    if self._empty_since is None:
        self._empty_since = now
    elif (now - self._empty_since) >= self._recal_empty_s > 0:
        print(f"[Kinect][INFO] Auto-recal: EMPTY_{self._recal_empty_s}S", flush=True)
        self._calibrate()
        self._empty_since = None
    return empty_default
else:
    self._empty_since = None  # reset on any occupied frame
    # ... rest of read()
```

**Configuration:**

```
# In .env / env.example:
# Seconds of continuous empty-cave reading before auto-recalibrating the background.
# Set to 0 to disable. Only fires when cave is confirmed empty — safe during sessions.
KINECT_RECAL_EMPTY_S=60
```

**Logging:**

Print to stderr with a recognisable prefix so it appears in the soak stderr log:
```
[Kinect][INFO] Auto-recal: EMPTY_60S at t=4523.2
```
No changes to the CSV schema.

---

## Known Limitations

**Does not recover from stuck-occupied drift.**

If phantom foreground has already caused the sensor to read the cave as
permanently occupied, the empty-cave timer never starts and this feature never
fires. This is the more severe failure mode (observed at ~19:10 in the soak test).

For a supervised installation, the artist notices and restarts the app. For a
fully unattended deployment, a separate watchdog (previously called "Trigger B")
would be needed — but that carries its own risk of recalibrating while a real
viewer is present. See `SOAK-TEST-REPORT-20260514.md` Section 4.3 for the
full trade-off discussion.

**Does not help if visitors arrive back-to-back.**

If visitors arrive within `KINECT_RECAL_EMPTY_S` seconds of each other
throughout the event, the timer never completes. In that scenario, this feature
provides no protection. However: continuous occupancy means the sensor is reading
real foreground data, which reduces (but does not eliminate) the phantom foreground
risk. A manual restart during any longer gap between visitors is the fallback.

**Recalibration takes ~1–2 seconds.**

During that window, the main loop blocks. The video freezes briefly. This is
only noticeable if someone is watching the display during an empty period. If the
installation is dark (EMPTY_CAVE_DARK=1), the screen is already dark and the
freeze is imperceptible.

---

## Implementation Notes

- Approximately 15–20 lines in `src/sensor/kinect.py`, all within `read()` and
  `__init__()`.
- `_recal_empty_s` is loaded from `KINECT_RECAL_EMPTY_S` in `config.py`, same
  pattern as other Kinect thresholds. Type: `float`. Default: `60.0`.
  Pass `0` to disable.
- The feature is Kinect-only. Other sensor backends (`camera`, `picamera`,
  `mock`) do not have a background model and should ignore the setting.
- The `_empty_since` timer uses `time.monotonic()`, consistent with the rest of
  the codebase.
- After recalibration, `_prev_fg_mask`, `_prev_depth`, and `_prev_ir` should be
  reset to `None` — `calibrate()` already does this.
- Test: run with `KINECT_RECAL_EMPTY_S=10` in a known-empty room and confirm
  `[Kinect][INFO] Auto-recal` appears in stderr after 10 seconds. Then confirm
  the video behaviour is unchanged after recalibration.

---

## Before Implementing

Read `SOAK-TEST-REPORT-20260514.md` in full, especially Sections 3, 4.3, and 4.4.
The design here reflects decisions made after that report. Do not add Trigger B
(stuck-occupied watchdog) in the same PR without a separate discussion.
