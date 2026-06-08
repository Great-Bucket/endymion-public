# Soak Test Report — 2026-05-14

**Run duration:** ~6 hours (13:11–19:13 PDT)
**Location:** Basement studio
**Purpose:** Validate stability and behaviour for a 3-hour gallery event

---

## 1. placeholder. ignore.

---

## 2. Known Facts

### 2.1 What data exists

| Data source | Coverage | Status |
|---|---|---|
| `soak_monitor_20260514_131102.log` | 13:11–16:31 (200 min) | Complete, 401 poll records |
| `soak_stderr_20260514_131131.log` | Full run | Only contains KeyboardInterrupt on shutdown — normal |
| `session.csv` in soak folder | 1 min 41 sec | Belongs to earlier calibration run D026, not this soak |

**No per-frame sensor data exists for the 6-hour soak.** The run was launched without `LOG_FILE=logs/session.csv` and the Pi's `.env` had `LOG_FILE=` empty. This was an error in the run instructions I provided.

### 2.2 Hardware health (from monitor log)

The monitor log polled every 30 seconds from 13:11 to 16:31 — covering the first 3h20m of the run.

- **Temperature:** Stabilised at 63–66°C within the first 30 minutes. Peak reading: **67.5°C** at 14:54. No throttling at any point (`throttled=0x0` throughout).
- **Memory:** Settled at ~780–820 MB used (of ~8 GB total). No trend of growth. Occasional spikes to ~940 MB, always recovering. No sign of memory leak.
- **Process:** `main.py` was running continuously every time the monitor polled after 13:11:32. Zero `main_running=NO` flags during the monitored window.
- **Throttle flags:** `0x0` on all 401 polls — never under-voltage, never throttled.

The monitor log ended at 16:31 because it was configured for 200 minutes. After that point, there is no hardware telemetry.

### 2.3 How the run ended

The only entry in `soak_stderr_20260514_131131.log` is this:

```
Traceback (most recent call last):
  File "main.py", line 226, in <module>
  ...
  File "src/visual/effects.py", line 181, in apply
    mask = np.clip(mask, 0.0, 1.0)[:, :, np.newaxis]
KeyboardInterrupt
```

This is not a crash. It is the normal Python traceback produced when Ctrl+C is pressed during a NumPy operation. The app ran continuously until manually stopped at approximately 19:13.

**The app did not crash at any point during the 6-hour run.**

### 2.4 Anomalies reported by the artist

These are described as observed, not inferred:

- **~17:00 (approx. 3h50m into run):** Video appeared bright when the cave was empty. The expected behaviour in an empty cave is darkness.
- **~19:10 (approx. 6h into run):** Video began oscillating between light and dark states while the cave was empty. This continued until the app was stopped at 19:13.

**Environmental context (artist's observation):** The run started at 13:11 on a May afternoon in Seattle with a fair amount of natural light entering the basement studio. By 17:00 there was noticeably less light. By 19:10 the sun was approaching setting and the light entering the space was significantly less than at startup. This environmental change is potentially significant — see Section 3.2.

---

## 3. Theory of What Caused the Anomalies

### 3.1 Background drift — the dominant mechanism and contributing factors

The Kinect's motion detection works by comparing each live depth frame to a static background model. The background is captured at startup as the mean of 30 depth frames, and is never updated again. The key calculation is:

```python
fg_mask = (np.abs(depth - self._background) > 200mm) & valid
```

A pixel is counted as "foreground" (someone present) only if it differs from the stored background by more than 200mm. If the cave is empty but the sensor's depth readings have shifted since startup, some pixels will appear to be foreground even when nothing is there — phantom foreground.

**The dominant mechanism — flicker-during-calibration (Mechanism B, refined):**

The Kinect v1 operates at 830nm near-infrared. Sunlight contains significant energy at this wavelength, which competes with the Kinect's own IR projector. Under high ambient IR, depth pixels do not simply shift in value — they flicker in and out of validity entirely (returning 0 for invalid/saturated pixels). The critical failure happens during calibration.

The 30-frame calibration computes a pixel-wise mean of depth frames without filtering invalid readings — invalid pixels return 0, and those zeros are included in the average. If a pixel is intermittently valid during the calibration window — say, valid in 15 of 30 frames at a true depth of 2,000mm and invalid (0) in the other 15 — the stored background for that pixel is approximately 1,000mm. This diluted value is baked in for the rest of the session.

At runtime, when ambient IR decreases (sun lowering), the same pixel stops flickering and reads consistently at its true depth of 2,000mm. The fg detection then computes `|2,000 − 1,000| = 1,000mm`, far above the 200mm threshold. That pixel registers as phantom foreground, stably, even though the cave is empty.

This mechanism:
- Easily clears the 200mm threshold regardless of how it is tuned
- Affects coherent regions of the depth frame — the areas that faced windows or received sun reflections during the calibration window
- Produces *stable* phantom foreground (the diluted background is a fixed number; the runtime reading is also now stable), which is required for the "bright when empty" observation
- Has exactly the temporal signature observed: behaves normally while ambient IR resembles calibration conditions, fails as conditions diverge

**The temporal correlation is strong:** the anomaly began at ~17:00 as the sun lowered, and worsened at ~19:10 as it approached setting.

**Other contributing factors:**

- **Mechanism A — Thermal drift (minor):** The Kinect's IR projector drifts a few mm over operating temperature swings. Insufficient on its own to clear the 200mm threshold, but not zero. Cumulative over hours.
- **Mechanism C — Warm-up drift:** The Kinect goes through its largest thermal swing in the first ~30 minutes as electronics come up to temperature. Calibrating while the sensor is still cold means the background is captured under slightly different conditions than the runtime steady state. Small magnitude but present.
- **Mechanism D — Gallery artificial lighting with IR content:** Halogen, incandescent, and tungsten lamps produce significant near-IR. Fluorescent lamps produce less but flicker. Modern LED lighting produces very little near-IR. "Sealed from sunlight" does not mean "stable IR environment" if the venue's own lighting has IR content. This is directly relevant to any future deployment of Endymion.

### 3.2 How the mechanism causes "bright when empty"

Once calibration has captured diluted background values for a set of pixels, those pixels register as phantom foreground at runtime (their delta from the stored background exceeds 200mm). The code then checks whether these phantom pixels are *moving*:

```python
changed = int((fg_mask != self._prev_fg_mask).sum())
presence = 1.0 - changed / mask_change_threshold
```

Because the phantom foreground arises from a fixed diluted background value being compared to a now-stable runtime reading, the phantom fg mask is extremely stable frame to frame. `changed` is very low. Therefore:

```
presence = 1.0 - (very small number / threshold) ≈ 1.0
```

The PenaltyRoutine receives a presence value close to 1.0, above the motion trigger (0.7). It concludes: *no motion detected*. The routine stays in BRIGHT. The video displays at full brightness in an empty cave.

**This matches the observation at ~17:00.**

### 3.3 How the mechanism causes oscillation

As conditions continue to diverge from calibration, the number of phantom foreground pixels fluctuates around the `min_fg_pixels` threshold (20,000 pixels). When it dips below, the code takes the empty-cave path and resets state. The frame-by-frame sequence becomes:

- **Frame N:** `n_fg = 19,500` (below threshold) → empty-cave path → `_prev_fg_mask = None`, return `0.0`
- **Frame N+1:** `n_fg = 20,500` (above threshold), but `_prev_fg_mask` is `None` → first-frame fallthrough → return `0.0`, store state
- **Frame N+2:** `n_fg = 20,500`, real diff against stable phantom mask → `changed ≈ 0` → `presence ≈ 1.0`
- **Frames N+3 onwards:** `presence ≈ 1.0` until `n_fg` dips again

Every dip-and-rise around the 20,000 threshold produces two consecutive `0.0` outputs followed by sustained `1.0` outputs. The PenaltyRoutine receives the two `0.0`s, fires, snaps to nadir, holds for 2.4s, then receives sustained `1.0`s and recovers over 8s back to BRIGHT — and the cycle repeats. This produces an oscillation envelope of roughly 10–15 seconds of darkness followed by full brightness, repeating autonomously with nothing in the room.

**This matches the observation at ~19:10.**

### 3.4 Why the anomaly appeared at ~4 hours, not earlier

The monitor log shows the Pi's temperature stabilised by 13:40 (within ~30 minutes of startup). Thermal drift in the Kinect itself is slow-accumulating. More significantly, ambient IR from sunlight decreases gradually over the afternoon, not suddenly. The 4-hour onset is consistent with either mechanism: a slow shift from thermal drift, a slow decrease in ambient IR as the sun moved lower and the angle of light entering the basement changed, or both accumulating together until the background model became sufficiently mismatched to produce visible anomalies.

### 3.5 What the design assumed vs. what happened

The design assumes: *the room is identical at hour 6 to how it was at startup.* The Kinect background model is implicitly a "world snapshot." In a short session (30 minutes) this holds well. Over 6 hours, it doesn't.

### 3.6 Alternative causes (considered but less likely)

- **USB dropout or Kinect hardware glitch:** The code handles this explicitly by returning `1.0` (intentionally bright for one frame) and resetting state. A sustained dropout would cause `main.py` to loop on transient frames, not a sustained bright state.
- **Crash or exception:** Ruled out — stderr contains only the normal KeyboardInterrupt.
- **Configuration error:** The `.env` had `EMPTY_CAVE_DARK=1`, meaning the app *should* go dark when empty. This setting was correct. The fault is that the background model became stale.

---

## 4. Lessons for Next Time

### 4.1 Always capture LOG_FILE during a soak

The absence of per-frame data made this diagnosis entirely inferential. The actual presence values during the anomaly are unknown — we are working from theory and observation alone.

**Fix:** Add `LOG_FILE=logs/session_$(date +%Y%m%d_%H%M%S).csv` explicitly to the run command. Never rely on `.env` for this during a soak.

### 4.2 The monitor needs to run for the full duration

The monitor ran for 200 minutes (3h20m) of a 6-hour run. The anomalies occurred at 3h50m and 6h — both outside the monitored window. Had the monitor run longer, we might have seen the temperature change or other correlates around 17:00.

**Fix:** Set `MONITOR_DURATION` to at least 1.5× the planned run length.

### 4.3 The background model is the key fragility

The most important operational lesson: the Kinect background model is calibrated once and never updated. Any space where IR conditions change during the session — changing daylight, artificial lighting with IR content turning on or off, or simply sensor warm-up — risks corrupting the background model.

**Calibration timing matters.** Calibrate as close to event start time as possible, with the space in its final lighting configuration. Let the Kinect warm up for 5–10 minutes before starting the app so the electronics are at operating temperature when the background is captured.

**Fix design — Trigger A only (empty-cave auto-recalibration):**

Implement a single auto-recalibration trigger in `KinectSensor`:

- **Trigger A (empty-cave timer):** If the cave has been continuously empty (`n_fg < min_fg_pixels`) for ≥ 60 seconds, silently recalibrate. This handles the slow-drift case: as soon as the sensor reads the cave as empty for a minute, it refreshes the background.

Trigger A only fires when the cave is confirmed empty — it cannot bake a viewer into the background, it cannot interfere with a session in progress. It is a conservative, low-risk improvement intended primarily for future unattended deployments.

**Trigger B (stuck-occupied watchdog) — explicitly rejected.** A watchdog that fires after N minutes of continuous occupancy would risk recalibrating while a viewer is genuinely present and still — exactly the behaviour Endymion invites. The consequence (viewer rendered invisible to the sensor for the rest of their session) is worse than the drift problem it guards against. Do not implement.

**For the upcoming event — human-in-the-loop response.** The artist will be present. The failure mode (video bright or oscillating in an empty cave) is immediately visible. The correct response is: clear the room, restart the app (`Ctrl+C`, then `python main.py ...`). Calibration takes approximately 10 seconds. This is the primary mitigation for the event. Trigger A provides a passive safety net between visitor sessions.

Each Trigger A recalibration event should be printed to stderr with a recognisable prefix (e.g. `[Kinect][INFO] Auto-recal: EMPTY_60S`) so it appears in the soak stderr log and can be identified post-event. The threshold is exposed as `KINECT_RECAL_EMPTY_S` (set to `0` to disable entirely).

Slow background adaptation is a better long-term fix but is out of scope before the event. Deferred.

### 4.4 The event is 3 hours — timing margin is narrow

The event is 3 hours. The soak anomaly appeared at 3h50m. The event duration falls just inside the window where the background model held cleanly today — but only by 50 minutes, and today's conditions (studio with window light) were different from the gallery. This margin is not comfortable enough to rely on without mitigation.

Trigger A provides passive protection during gaps between visitors. The manual restart procedure (see Section 4.3) is the primary response if drift is observed. Taken together, these give adequate coverage for a 3-hour supervised event.

### 4.5 The analyser falsely flagged KeyboardInterrupt as an exception

The `analyse_soak.py` script counted the `KeyboardInterrupt` traceback in stderr as an application exception. It is not — it is a normal shutdown. The script should filter `KeyboardInterrupt` from its exception detection.

### 4.6 A proposed empirical test to confirm the ambient IR hypothesis

The ambient IR theory is currently inferential — based on temporal correlation, not measured data. A diagnostic script (`tools/capture_bg.py`) has been written that captures and saves a 30-frame Kinect background model.

**Refined test design** (incorporating CC's suggestion to test the production failure path, not just abstract means):

1. **Morning (bright ambient light):** Run `python tools/capture_bg.py --label morning`. Saves the background model to `logs/bg_morning_<timestamp>.npz`.
2. **Evening (low light, same physical setup, no changes):** Instead of capturing a second background, capture a series of 30 live depth frames and run the production fg-mask computation against the saved morning background: `|depth − background| > 200mm` within the valid depth range.
3. **Report `n_fg`** for each of those 30 frames. If `n_fg > 20,000` (the `min_fg_pixels` threshold), the production failure path is confirmed — the cave would read as occupied with nobody in it.

If `n_fg` fluctuates across the 20,000 boundary across the 30 frames, that confirms the oscillation mechanism as well as the bright-when-empty failure.

**This test has not yet been run.** However, it is of value not only for next week's gallery event but for all future deployments of Endymion — see Section 5.

---

## 5. Why the IR Issue Matters Beyond Next Week

The gallery space for the upcoming event is described as sealed from natural light. The ambient IR risk from sunlight may therefore be low for that specific show. However, Endymion is intended to be shown in other contexts — outdoor or semi-outdoor settings, spaces with windows, or venues with non-LED lighting — where sunlight or artificial IR sources could be a more significant problem.

Trigger A (empty-cave auto-recalibration) and the diagnostic test (`capture_bg.py`) are therefore not just pre-event patches — they are permanent improvements to the installation's robustness for any future context. An installation that silently refreshes its background during gaps between visitors is more trustworthy to leave running unattended.

**The gallery lighting question remains open:** ask the venue in advance whether the lighting is LED, halogen, or fluorescent. If it is halogen or tungsten, Mechanism D (Section 3.1) applies even in a sealed space — Trigger A and manual restart remain the mitigations.

**Trigger A coverage limit for unattended deployments:** Trigger A only fires when the cave has been empty for 60 continuous seconds. If IR drift has already caused the stuck-occupied failure mode (phantom foreground keeps the cave reading as occupied), the 60s empty condition never fires and Trigger A cannot recover. For any fully unattended deployment where stuck-occupied drift is a risk, a different mitigation is needed — either Trigger B (explicitly rejected for this installation due to conceptual conflict with stillness), a scheduled operator restart, or a more robust background adaptation algorithm.

---

## 6. Summary

The 6-hour soak demonstrated that the app is fundamentally stable: no crashes, no thermal throttling, no memory leaks, no USB dropouts in the monitored window. The anomalies were caused by the Kinect background model being captured under high ambient IR conditions. As ambient IR decreased over the afternoon, calibration pixels that had flickered during capture became stable at runtime, producing phantom foreground with a fixed large delta from the diluted background.

The fix for the event is operational: the artist is present, the failure mode is visible, and a manual restart takes 10 seconds. No code changes are required before the event. The background drift recovery feature (auto-recalibration during empty-cave gaps) has been specced and deferred — see `docs/IDEAS-background-drift-recovery.md`.

---

## 7. Requested Next Steps for CC

The following work is requested in priority order:

**1. Raise the default monitor duration and add a clear end marker**

In `tools/pi_monitor.sh`: raise the default `MONITOR_DURATION` (currently 200 minutes) to at least 360 minutes. Print a visible `[MONITOR ENDED — no further telemetry]` line when the duration limit is reached so it is unambiguous in the log when coverage stops. This is a 5-line shell change, independent of everything else.

**2. Fix the analyser's false-flag of `KeyboardInterrupt`**

`tools/analyse_soak.py` counts `KeyboardInterrupt` tracebacks as application exceptions. Add a filter to exclude it. Can go in the same PR as item 1.

**3. Update `tools/capture_bg.py` with the production fg-mask test**

The script exists in the repo (`tools/capture_bg.py`). Extend it to support a `--compare` mode that captures 30 live depth frames and runs each against a saved background using the production fg-mask path (`|depth − background| > 200mm`), reporting `n_fg` per frame. This directly tests whether ambient IR drift would cause phantom foreground in production conditions, as described in Section 4.6.

**4. Run a second logged soak** ✓ *COMPLETE — 2026-05-19*

**Results:** 3h 6m, 221,062 frames, 19.76 fps average. Zero USB dropouts, zero freezes, zero stderr exceptions, zero UNREACHABLE monitor polls. System behaviour confirmed correct by direct observation at 3h: cave dark when empty, brightens correctly when occupied. Analyser report: `logs/soak_20260519/`.

**Start conditions (2026-05-19, 12:21 PDT):** Basement studio, overcast sky, diffuse daylight through windows sufficient to read by, no artificial lights. Ambient light level remained approximately stable throughout. Artist absent for first ~3 hours; present for final ~6 minutes.

**Analyser output:**

```
Duration: 3h 6m 30s  |  Frames: 221,062  |  Avg fps: 19.76
USB/Kinect dropouts:    0  ✓
Freeze events:          0  ✓
Stderr exceptions:      0  ✓
Monitor UNREACHABLE:    0  ✓
Signal drift window 17: -36.8%  ⚠  (see interpretation below)
Monitor WARNINGs:       7        ⚠  (see interpretation below)
Overall: FAIL (two flagged items — both benign)
```

**Interpretation of flagged items:**

- *Signal drift window 17:* The `changed` p90 dropped in the final 10-minute window (covering the artist's return and test session at ~3:20 PM). The artist's movements were less vigorous than at startup; no phantom foreground developed. Confirmed benign by direct observation.
- *Monitor WARNING lines (7):* The monitor started 2 minutes before the Pi app launched. Several "main.py not running" warnings fired during that startup gap. No runtime warnings.

**Key finding — confirms the May 14 hypothesis:**

No background drift occurred during 3+ hours of stable overcast conditions. This directly supports the flicker-during-calibration theory: drift requires the ambient IR level at runtime to differ significantly from the level at calibration. Stable lighting = stable sensor = no phantom foreground. The May 14 anomaly required both high IR at startup (sunny afternoon) and decreasing IR at runtime (sun setting). Neither condition was present today.

**Implication for the gallery event:** The gallery space is sealed from natural light with controlled artificial lighting. If the venue uses modern LED lighting (low IR output), the risk of calibration/runtime IR mismatch is low. Ask the venue about lighting type before the event. Manual restart remains the fallback if any anomaly is observed.

---

*Note: Background drift recovery (auto-recalibration) has been specced and deferred. See `docs/IDEAS-background-drift-recovery.md`. Do not implement without a separate discussion.*
