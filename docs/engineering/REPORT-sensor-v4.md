# Endymion Sensor — Diagnostic Report and v4 Proposal

**Date:** 2026-05-11  
**Author:** Cursor (Sonnet 4.6)  
**Status:** Ready for review — written for Claude Code second opinion

---

## 1. Target Behaviour

The installation requires the sensor to detect human **movement**, not human **presence**.
The rule is simple: if the viewer moves, the video darkens. If they are still, the video is bright.

"Still" means: no head turns, no weight shifts, no gestures. Gentle breathing is acceptable.
"Moving" means: any deliberate body movement — head rotation, torso rock, arm raise, fidgeting.

When no one is in the cave, the video plays bright (no movement = bright).

---

## 2. Architecture History

### v1 — Raw depth frame differencing (abandoned)
Compared consecutive raw depth frames pixel-by-pixel over the full frame.  
**Failed:** Cannot detect lateral (side-to-side) movement. Rocking left-right at a
constant depth from the sensor produces no signal.

### v2 — Background subtraction + centroid tracking (abandoned)
Background subtraction correctly isolated the human foreground from the scene.
Centroid tracking failed: the torso dominates the centre of mass (~60–70% of
silhouette area), so arm and head movements barely shift the centroid.

### v3 — Background subtraction + foreground mask frame differencing (current, insufficient)
Keep the background model. Replace centroid with a count of how many pixels flipped
state (foreground ↔ background) in the binary foreground mask between frames.

**What worked:**
- Background subtraction correctly identifies the human silhouette.
- Empty-cave detection (`n_fg < KINECT_MIN_FG_PIXELS`) works reliably.
- Entry and exit are detected (large silhouette appearance/disappearance).
- Arms separated wide overhead are detected (dramatic silhouette expansion).

**What failed:**
- Head rotation, torso rocking, arm raises (not separated) — **not detected**.
- Root cause: see Section 3.

---

## 3. Root Cause Analysis

### 3.1 What mask differencing actually measures

`changed = (fg_mask != prev_fg_mask).sum()` counts pixels that **crossed the
foreground/background boundary** between frames. This is a measure of **silhouette
shape change**, not movement.

A movement only registers if it changes the outline of the silhouette:
- Arms separated wide → silhouette expands dramatically → large `changed` ✓
- Entry / exit → silhouette appears / disappears → large `changed` ✓
- Head turn → face rotates, depth at face pixels changes, but the silhouette **outline barely shifts** → small `changed` ✗
- Torso rock left-right → silhouette translates as a unit → pixels enter on one side, exit on the other, but the **net count change is small** → small `changed` ✗

### 3.2 Evidence from calibration logs

**D001** (threshold=50,000): Person in frame for ~350 frames — rotating head, rocking
torso, raising arms, separating arms.

| Inferred `changed` range | % of in-frame frames | Interpretation |
|---|---|---|
| 5,000–9,000 | 23.6% | Still / pausing |
| 10,000–20,000 | 73.3% | All active movement (head, torso, arms raised) |
| 35,000–50,000+ | 1.3% | Arms separated wide |

Head rotation, full torso rocks, and arms raised overhead all generated the **same
changed values (10,000–20,000)** as the still-person noise floor (8,000–10,000).
There is no reliable separation between "still" and "moving head/torso" in this signal.

**D003** (threshold=40,000): Detailed 130-second session with logged action sequence.

Timeline mapped to log:
```
t=0–17s    Outside cave          raw=1.0    smooth=1.0   BRIGHT ✓
t=17s      Entered               raw=0.0    dark (entry motion)
t=17–30s   Settling in chair     raw recovering
t=30–102s  Head rotation, torso rocking, arms raised    raw=0.65–0.77   BRIGHT
t=102s     Arms separated overhead    raw drops → DARK ✓
t=112s     Exited cave           raw=1.0    BRIGHT ✓
```

For **72 consecutive seconds**, the person was deliberately rotating their head,
rocking their torso, and raising their arms — and the video remained fully bright.
The sensor read these movements as "still".

### 3.3 Why the noise floor is so high

The foreground mask has a structural noise floor of ~8,000–10,000 changed pixels per
frame even for a completely motionless person. This comes from:

- **Edge pixels at the silhouette boundary**: the depth transition between a person
  (~1,200 mm) and the background (~3,000 mm) is steep. Small Kinect measurement
  noise (~10–20 mm) at the precise boundary causes individual pixels to flip
  foreground/background on every frame.
- **At 4 ft, a human silhouette spans ~30,000 pixels.** Approximately 900 pixels lie
  on the boundary. Depth noise causes 10–30% of these to flicker per frame:
  900 × 0.15 = ~135 pixels per frame minimum, but in practice the measured floor is
  8,000–10,000 — suggesting the boundary zone is wider or more unstable than expected.

The motion signal for head turns and body rocks adds only ~2,000–5,000 pixels above
this floor. That signal is buried in the noise.

---

## 4. Recommendation: v4 — Depth Change Within Foreground

### 4.1 The core idea

Instead of asking "did the silhouette shape change?", ask:
**"Did the depth values at foreground pixels change between frames?"**

When a viewer turns their head, the face is now presented at an angle — the depth of
face pixels changes by 30–100 mm even though the silhouette outline barely shifts.
When they rock their torso, the chest depth changes even if the lateral silhouette
edge doesn't move much. This signal is invisible to mask differencing but is directly
measured by per-pixel depth comparison.

This is related to v1 (depth frame differencing) but with a critical difference:
**apply it only within the foreground region**. v1 failed because it included background
pixels, which are very noisy. Restricting to foreground pixels eliminates that noise.

### 4.2 Algorithm

**Phase 1 — Background capture:** unchanged from v2/v3.

**Phase 2 — Foreground extraction:** unchanged from v2/v3.
```
valid = (depth > KINECT_MIN_DEPTH) & (depth < KINECT_MAX_DEPTH)
fg_mask = (|depth - background| > KINECT_FG_DEPTH_THRESHOLD_MM) & valid
```
If `n_fg < KINECT_MIN_FG_PIXELS`: cave empty → return `raw=1.0`.

**Phase 3 — Depth change within foreground (replaces mask differencing):**

```
both_fg = fg_mask & prev_fg_mask          # pixels foreground in BOTH frames
depth_diff = |depth[both_fg] - prev_depth[both_fg]|
moved_pixels = (depth_diff > KINECT_DEPTH_NOISE_FLOOR_MM).sum()
presence = max(0.0, 1.0 - moved_pixels / KINECT_FG_MOTION_THRESHOLD)
```

- `moved_pixels = 0` → presence = 1.0 (perfectly still)
- `moved_pixels >= KINECT_FG_MOTION_THRESHOLD` → presence = 0.0 (fully moving)

`KINECT_DEPTH_NOISE_FLOOR_MM` filters out per-pixel measurement noise (the Kinect's
natural depth jitter at 4 ft is ~10–20 mm). Setting this to 30 mm means only genuine
movement registers as a changed pixel.

**What is stored between frames:**  
`self._prev_fg_mask` (as now) **and** `self._prev_depth` (the full depth frame, needed to
compare depth values at the same pixels).

**Edge cases:**
- `prev_fg_mask is None` or `prev_depth is None` (first frame after calibration): store
  both, return `1.0`.
- Cave empty (`n_fg < min_fg_pixels`): reset both `_prev_fg_mask` and `_prev_depth`
  to `None`, return `1.0`.
- `both_fg.sum() == 0` (no pixels foreground in both frames — person just entered):
  store current mask and depth, return `1.0`.

### 4.3 Why this detects what mask differencing misses

| Movement | Mask differencing | Depth-within-fg |
|---|---|---|
| Head turn 30° | face outline barely shifts → ~2,000 extra changed pixels | face pixels change depth 30–100 mm → many pixels above noise floor → detected ✓ |
| Torso rock L-R | silhouette shifts laterally as unit → ~3,000 net boundary change | chest pixels change depth 10–30 mm → detected if above noise floor ✓ |
| Arm extended forward | silhouette barely widens → small mask change | arm pixels change depth 100–500 mm → very clearly detected ✓ |
| Arms separated wide | silhouette expands dramatically → detected ✓ | also detected ✓ |
| Still person | ~8,000–10,000 noise floor → hard to separate from movement | noise floor = pixels changing >30 mm per frame ≈ 100–500 → clear separation ✓ |
| Entry / exit | detected ✓ | detected ✓ |

### 4.4 Parameters

| Parameter | Proposed default | Unit | Notes |
|---|---|---|---|
| `KINECT_DEPTH_NOISE_FLOOR_MM` | 30 | mm | Depth change at a pixel that counts as "moved". Above Kinect's natural noise (~15–20 mm at 4 ft). |
| `KINECT_FG_MOTION_THRESHOLD` | 1500 | pixels | Number of moved pixels that = "fully moving". Start here; tune up if too strict. |

Replace `KINECT_MASK_CHANGE_THRESHOLD` with these two parameters.

Retained from v3 (confirmed, do not change):

| Parameter | Confirmed value |
|---|---|
| `KINECT_FG_DEPTH_THRESHOLD_MM` | 200 |
| `KINECT_MIN_FG_PIXELS` | 20,000 |
| `KINECT_BG_FRAMES` | 30 |

### 4.5 Implementation scope

Files that change:
- `src/sensor/kinect.py` — replace mask differencing logic with depth-within-fg
- `src/utils/config.py` — remove `kinect_mask_change_threshold`, add `kinect_depth_noise_floor_mm` and `kinect_fg_motion_threshold`
- `main.py` — update `build_sensor()` parameter names
- `env.example` — replace env var documentation

Files that do NOT change:
- `src/visual/player.py`
- `src/visual/effects.py`
- `src/utils/signal.py`
- `src/sensor/base.py`, `camera.py`, `mock.py`
- Background capture pipeline, B-key recalibration, logging system

### 4.6 Risk and open question

**Breathing:** the chest moves 10–20 mm per breath at 4 ft. With `KINECT_DEPTH_NOISE_FLOOR_MM=30`,
a 10–20 mm chest movement will NOT register (below the floor). A deep breath might
reach 25–30 mm. Starting at 30 mm should be safe; raise to 35 mm if breathing triggers.

**Chair movement:** same risk as v2/v3. Chair moves after calibration → persistent
foreground → false motion when the silhouette shape shifts. Mitigation: B-key
recalibration between visitors, or bolt/tape the chair.

**`both_fg` coverage:** if the person is actively moving (entry, large arm gesture), the
`both_fg` intersection of current and previous mask may be small. In this case,
`moved_pixels` is naturally high (the entering/leaving pixels), which is correct —
large movement = low presence.

---

## 5. What to Keep, What to Replace

| Component | Status |
|---|---|
| Background model capture | **Keep** — working correctly |
| B-key recalibration | **Keep** — already implemented |
| `n_fg < KINECT_MIN_FG_PIXELS` empty-cave detection | **Keep** — confirmed working |
| `KINECT_FG_DEPTH_THRESHOLD_MM=200` | **Keep** — confirmed correct at 4 ft |
| `KINECT_MIN_FG_PIXELS=20000` | **Keep** — confirmed correct |
| Mask shape comparison (`fg_mask != prev_fg_mask`) | **Replace** with depth-within-fg |
| `KINECT_MASK_CHANGE_THRESHOLD` | **Replace** with `KINECT_DEPTH_NOISE_FLOOR_MM` + `KINECT_FG_MOTION_THRESHOLD` |

---

## 6. Starting Parameters for First v4 Test

```bash
# ON PI — stand clear for ~1s at startup:
source venv/bin/activate
SENSOR_TYPE=kinect FULLSCREEN=1 DEBUG=1 \
  EFFECTS=luminosity,vignette,desaturation \
  KINECT_FG_DEPTH_THRESHOLD_MM=200 \
  KINECT_MIN_FG_PIXELS=20000 \
  KINECT_DEPTH_NOISE_FLOOR_MM=30 \
  KINECT_FG_MOTION_THRESHOLD=1500 \
  MOTION_TRIGGER=0.7 \
  LOG_FILE=logs/session.csv \
  python main.py
```

**If too strict** (breathing triggers): raise `KINECT_DEPTH_NOISE_FLOOR_MM` to 35–40.  
**If too forgiving** (head turns don't trigger): lower `KINECT_FG_MOTION_THRESHOLD` to 1000, or lower `KINECT_DEPTH_NOISE_FLOOR_MM` to 25.
