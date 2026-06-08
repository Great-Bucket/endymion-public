# Spec: Effects Pipeline Performance

**Status:** Implemented (§1, §3, §4, §5 plus a bypass-ramp addition). §2 investigated and rejected — the proposed numpy replacement is measurably *slower* than the current cv2 path on the actual hardware. See §2 below.

**Outcome:** Pi total pipeline cost was 140 ms/frame at 1080p full-res (running at ~7fps). Half-res (§4) drops this to ~34 ms — inside the 41.7 ms budget. Bright bypass (§3) eliminates the pipeline entirely during the BRIGHT phase, with a 2-second ramp (added after Pi testing) softening the dark→bright frame-rate transition. Vignette mask caching (§5) saves the per-pixel `np.exp` during HOLD phase when sigma is constant.

**PR:** `feat/effects-performance`.

**Related:** `docs/PERFORMANCE-effects.md` (pre-existing bottleneck analysis and candidate
optimisations — this spec extends it with a concrete implementation priority order and corrects
earlier mistakes from the first draft).

---

## Problem statement

The app plays `SlowFilm_4endymion_h264_1080p_v1.mp4` (15,201 kb/s, 1920×1080, 23.98fps).
The Pi 5 cannot decode this file AND run the full effects pipeline within the 41.7ms frame
budget. The result is dropped frames and stuttery video.

Without effects (`EFFECTS=none`), the video plays smoothly. With effects
(`luminosity,vignette,desaturation`), frame rate drops noticeably. This isolates the bottleneck
to the effects pipeline, not decode alone.

**Key observation:** The viewer confirmed that when the video is at full brightness (`smooth=1.0`
— viewer sitting still), no effects are visible. This means the pipeline is running every frame
at full cost and producing zero visible output. That CPU is needed for decode.

---

## What the effects pipeline actually does at `smooth=1.0`

Traced through the real code (`src/visual/effects.py`):

**LuminosityEffect.apply():**
```
brightness = 0.05 + 0.95 * (1.0 ** 0.6) = 1.0
np.clip(frame * 1.0, 0, 255).astype(np.uint8)
```
Result: identity. Cost: allocates a float64 array (~50MB at 1920×1080×3), then casts back.
Wasted memory bandwidth on every frame.

**VignetteEffect.apply():**
```
mask = 1 - intensity * (1.0 - 1.0) * (...) = 1.0 everywhere
np.clip(frame * 1.0, 0, 255).astype(np.uint8)
```
Result: identity. Cost: gaussian_mask is recomputed every frame even at constant sigma, then a
full-frame multiply with a mask of all-ones.

**DesaturationEffect.apply():**
```
cv2.cvtColor(frame, RGB2GRAY)    # full-frame conversion
cv2.cvtColor(gray, GRAY2RGB)     # second full-frame conversion
cv2.addWeighted(gray_rgb, 0.0, frame, 1.0, 0)
```
Result: identity (0.0 weight on grayscale). Cost: two full-frame OpenCV colour space conversions
plus addWeighted, regardless of smooth value. **Almost certainly the dominant cost of the three.**

---

## Implementation plan (priority order)

### 1. Profile first — 15 minutes of work — **DONE**

Wrap each `effect.apply()` call in `time.perf_counter_ns()` and log the delta, averaged over
100 frames. This confirms which effect accounts for most of the budget. Likely split:
desaturation ~50–70%, vignette ~20–30%, luminosity ~5%. Numbers drive priority.

**Implemented:** `src/visual/effects.py` — `EFFECTS_PROFILE=1` env var enables one-line stderr summary every 100 frames. Opt-in; zero overhead when off.

**Measured on Pi (1080p full-res, viewer out of frame so pipeline runs at full cost):**
```
luminosity ≈ 35 ms (25%)   vignette ≈ 96 ms (69%)   desaturation ≈ 8 ms (6%)   | total ≈ 140 ms
```
This **inverted the spec's hypothesis** (desaturation was predicted dominant; vignette is actually dominant) and re-ordered §2 to lowest priority.

---

### 2. Fix desaturation — replace double cvtColor with numpy channel blend — **INVESTIGATED AND REJECTED**

**Originally projected as the biggest CPU win.** Pi profile showed it is actually the smallest of the three effects (6%, ~8 ms / frame at 1080p full-res via the existing cv2 path).

**The proposed numpy replacement** was implemented locally and benchmarked against the current cv2 path before committing. On Mac at half-res (540×960, 200 frames each, warmed):

```
cv2 cvtColor x2 + addWeighted  :  0.47 ms / frame
numpy weighted blend (Rec. 601):  3.35 ms / frame
delta                          : +2.88 ms / frame  (~7× slower)
```

**Why the recommendation was wrong.** OpenCV's `cvtColor` and `addWeighted` are SIMD-optimised C passes over uint8 data — single-pass, no intermediate float arrays. The numpy replacement promotes to float64 (a ~50 MB allocation at 1080p) and runs several full-frame multiplies through Python's array-op overhead. Same shape of cost as luminosity and vignette, which were already known to be expensive specifically *because* of float64 numpy allocations. On Pi the gap is expected to widen, not close, because ARM memory bandwidth penalises the numpy path more heavily than the cv2 path.

**Decision:** keep the cv2 path. Output was verified bit-equivalent (±1 LSB; cvtColor rounds, .astype truncates), so the change had no quality benefit either. Removed from scope.

`docs/PERFORMANCE-effects.md` §2 has been updated to match this finding.

Replace:
```python
gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
result = cv2.addWeighted(gray_rgb, blend, frame, 1 - blend, 0)
```

With:
```python
gray_value = 0.299 * frame[:,:,0] + 0.587 * frame[:,:,1] + 0.114 * frame[:,:,2]
gray_rgb = np.stack([gray_value, gray_value, gray_value], axis=2)
result = (gray_rgb * (1 - presence) + frame * presence).astype(np.uint8)
```

Eliminates two full-frame OpenCV conversion calls per frame. Applies across all phases (bright
and dark). Visually identical.

---

### 3. Bright bypass at `smooth >= 0.9999` — **DONE**

**Implemented:** `src/visual/player.py` — `_BRIGHT = 0.9999` module-level constant; `render()` skips the pipeline (and the half-res round-trip) when `presence >= _BRIGHT`, going straight from source frame to display.

**Addition: bypass ramp.** Pi testing surfaced a perceptible 14→24 fps jump at the moment `smooth` crosses 0.9999. Added a 2-second linear ramp on every bypass-entry that decays a deliberate per-frame sleep from ~34 ms (matching dark-phase pacing) to 0 ms. The frame rate now eases up rather than stepping. Two new module-level constants: `_BYPASS_RAMP_DURATION = 2.0` and `_BYPASS_RAMP_INITIAL_SLEEP_S = 0.034`. State: `self._bypass_entry_time`, reset whenever `smooth` drops back below `_BRIGHT`.

**When smooth is exactly at full brightness, skip the pipeline call entirely.**

```python
_BRIGHT = 0.9999  # module-level constant in player.py — not an env var

def render(self, presence: float) -> None:
    ret, frame = self._cap.read()
    ...
    if smooth < _BRIGHT:
        frame = pipeline.apply(frame, smooth)
    # else: raw frame used directly — pipeline not called
    surface = frame_to_surface(frame)
    display.blit(surface, (0, 0))
```

**Why 0.9999, not 0.98:**
At `smooth=0.98` the effects are noticeably active — vignette darkens corners by ~6%, luminosity
is 1.1% below full, desaturation mixes in 2% grey. Bypassing at 0.98 creates a visible jump
every time smooth crosses that value during recovery. The exact identity point is 1.0 only.
`>= 0.9999` catches the sustained BRIGHT phase without triggering during recovery.

**When smooth reaches 1.0:** `PenaltyRoutine` sets `_value = 1.0` and enters BRIGHT phase,
where it stays until the next motion event. This is precisely the long still period where
frame rate problems are most noticeable and where bypass is cleanest to apply.

**Visual impact:** None. At `smooth=1.0`, pipeline output is identical to the raw frame.

**Do not add `BRIGHT_THRESHOLD` as an env var.** This value should never be tuned. A
module-level constant is the right scope.

---

### 4. Half-resolution effect processing — **DONE** (priority reordered to first after profile)

**Implemented:** `src/visual/player.py` runs the effects pipeline at `(width/2, height/2)` and upscales with `cv2.INTER_LINEAR` before blitting. Wired via `HALF_RES_EFFECTS=1` env var through `Config`.

**Pi result:** total pipeline cost 140 ms → ~34 ms (4.1× speedup). Visually crisp at projection throw — no softening visible. The single highest-leverage change.

**Spec's listed surface (effects.py, player.py, env.example) was extended to include `src/utils/config.py` and `main.py` to route `HALF_RES_EFFECTS` through `Config` consistently with every other env var. Reading env directly in `player.py` would have kept the literal surface but broken project convention.**

**Already documented in `PERFORMANCE-effects.md` §1.**

Apply effects at 960×540 (quarter pixel count), then upscale before blitting:

```python
small = cv2.resize(frame, (960, 540))
small = pipeline.apply(small, presence)
frame = cv2.resize(small, (1920, 1080), interpolation=cv2.INTER_LINEAR)
```

This quarters the numpy work for every effect simultaneously. Human vision at projection
distances does not reliably detect the upscale artifact. Effective during the dark/penalty
phase where smooth < 0.9999 and effects are running.

Wire with `HALF_RES_EFFECTS=1` env var as noted in `PERFORMANCE-effects.md`.

---

### 5. Cache vignette gaussian_mask when sigma is unchanged (minor) — **DONE**

**Implemented:** `src/visual/effects.py` — `VignetteEffect` now caches `_gaussian_mask` keyed on `(shape, sigma)`. Invalidated on shape change (inside `_get_dist`) or when `sigma` changes between frames. Cache hits exactly during the HOLDING phase (smoothed pinned to nadir → sigma constant).

**Mac measurement (200 frames, 540×960):** ~1.4 ms/frame saved when sigma is constant. Modest win, but real and free. Output verified bit-identical to non-cached implementation.

The gaussian_mask is recomputed every frame even when sigma hasn't changed (e.g., during any
sustained phase). Cache it as a class attribute and invalidate only when sigma changes. Small
win, free to implement alongside other vignette work.

---

## What was removed from the first draft

**Option C (frame caching when smooth is unchanged) — removed.** This was structurally broken:
`VideoPlayer.render()` calls `self._cap.read()` every tick, advancing the video by one frame.
The input frame changes every tick regardless of smooth value. Caching the last rendered surface
would freeze the video to a still image. Do not implement.

**BRIGHT_THRESHOLD as env var — removed.** The only meaningful bypass point is presence==1.0.
Making this configurable adds operational surface (`.env`, docs, Pi sync) with no practical
benefit.

---

## Implementation surface area

| File | Change |
|---|---|
| `src/visual/effects.py` | Fix desaturation (§2); cache vignette gaussian_mask (§5) |
| `src/visual/player.py` | Add bright bypass at `_BRIGHT = 0.9999` (§3); conditionally apply half-res (§4) |
| `env.example` | Add `HALF_RES_EFFECTS=0` with comment (§4) |
| `.env` (Pi) | Set `HALF_RES_EFFECTS=1` if needed after testing |

---

## Testing sequence

1. **Baseline:** run with v1 and `EFFECTS=none` — confirm smooth playback. This is the
   performance ceiling.
2. **After §2 (desaturation fix):** run full effects. Expect measurable framerate improvement
   in both bright and dark phases.
3. **After §3 (bright bypass):** sit still until BRIGHT phase. Confirm video plays at baseline
   frame rate. Move. Confirm effects engage correctly as smooth drops. Sit still again. Confirm
   smooth transition back to bypass at recovery completion.
4. **No visible discontinuity** should be detectable at the bright/effects boundary. If a pop
   is visible, the `_BRIGHT` constant needs reviewing (should not happen at 0.9999).
5. **After §4 (half-res effects):** run in dark phase. Confirm frame rate improves. At
   projection distances, confirm no visible softening from the upscale.

Do not re-encode the video. The goal is to make v1 play well on the Pi, not to compromise
source quality.
