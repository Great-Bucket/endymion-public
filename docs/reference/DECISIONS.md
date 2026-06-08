# Endymion — Decisions

Records the key design and technical decisions made during development.

---

## 1. Which sensor?

**Decision:** Kinect v1 (Xbox 360). Two units owned.

- Full Python integration confirmed working on Pi 5.
- Camera (MacBook webcam) retained as dev fallback via `SENSOR_TYPE=camera`.
- Leap Motion not pursued — Kinect depth data better suited to detecting
  stillness vs presence in a fixed space.

---

## 2. Video architecture?

**Decision:** Architecture A — single video loop, parameter-modulated.

`SlowFilm_4endymion_h264_1080p_v1.mp4` is the active exhibition file (3.87 GB, ~15 Mbps). Effects pipeline
(luminosity, vignette, desaturation) driven by the presence signal. Running on
Pi at 23.976fps. v1 is preferred over v2 due to perceptibly better image quality.
Both soak tests (2026-05-14, 2026-05-19) were run on v1.

Revisit if a second video loop becomes compelling during tuning.

---

## 3. What does the sensor measure?

**Status:** v3 is the launch candidate (D008 settings). Head rotation is a confirmed
unresolvable gap in depth + IR sensing. Decision pending on whether to add RGB face
detection (see Paths A/B/C in CALIBRATION-log.md).

### Full algorithm history

- **v1 (abandoned):** Raw depth frame differencing over the full frame.
  Failed — cannot detect lateral movement, high background noise.

- **v2 (abandoned):** Background subtraction + centroid tracking.
  Centroid dominated by torso mass; arm and head movements produce no signal.

- **v3 (LAUNCH CANDIDATE — D008 settings):** Background subtraction + foreground
  mask frame differencing. Counts pixels that flipped foreground/background state
  between consecutive frames. Inherently a **velocity detector** — slow movements
  produce little frame-to-frame change.
  - **Works:** Entry/exit, arm separation, large/fast torso shifts, arm extensions.
  - **Does not trigger:** Slow deliberate movements (acceptable — breathing won't fire).
  - **Confirmed undetectable:** Head rotation in any direction at any speed.

- **v4 (instrumented, confirmed inadequate):** Depth-within-foreground change.
  `moved_pixels` and `mean_abs_ddepth` logged as diagnostics. Head rotation
  keeps the face at approximately the same depth → below noise floor.

- **v5 IR simple-diff (instrumented, confirmed inadequate):** `moved_ir_pixels`
  computed from frame-to-frame IR intensity change. Based on mistaken assumption
  that the Kinect's IR structured-light dots travel with the face — they do not.
  The dots are projected in world coordinates from a fixed emitter. Skin is
  approximately Lambertian; rotating it under fixed illumination produces near-
  identical IR intensity. Confirmed by D009 statistical analysis.

  **The SPEC-kinect-v5-ir-optical-flow.md proposal is invalidated by D009.** IR
  optical flow (Farneback) would be downstream of the same per-pixel IR values and
  would show the same null result. Do not implement.

### Threshold experiment: ratio-based vs absolute (D010, 2026-05-12) — FAILED, REVERTED

**Tried:** Replace `changed > KINECT_MASK_CHANGE_THRESHOLD` (absolute pixel count) with
`changed / n_fg > 0.3 × KINECT_MASK_CHANGE_RATIO` (ratio). Appealing in theory because
a ratio is scale-invariant — the same value should work regardless of viewer body size
or Kinect distance. Implemented as PR #16, tested in D010, reverted in PR #17.

**What happened:** Vigorous arm-waving produced `raw ≈ 0.75`, never crossing the
`MOTION_TRIGGER=0.7` firing line. Only reaching directly toward the camera triggered
the penalty. The piece was far less sensitive than D008.

**Why it failed:** When a viewer extends an arm sideways, both `changed` and `n_fg`
increase together — the arm creates new foreground pixels AND new boundary pixels. The
ratio stays nearly flat, so the trigger never fires for the class of movements we most
want to detect. The absolute threshold works precisely because arm extension adds a
large *absolute* changed count regardless of n_fg.

The deeper issue: `changed` scales with silhouette *perimeter* (≈ √area), not area.
Dividing by `n_fg` (area) makes large movements look proportionally smaller than small
ones. The ratio approach is wrong for this physics.

**Conclusion:** Do not retry ratio-based thresholding. The absolute threshold
(`KINECT_MASK_CHANGE_THRESHOLD=40000`) is the correct formulation for this algorithm.

### Why head rotation is undetectable with depth + IR (confirmed D009)

D009 was a clean 130-second head-only motion diagnostic. Statistical analysis across
5-second windows showed the head-rotation segment was **flatter than the opening
stillness segment** in all four signals. The p99 of 110 seconds of continuous head
rotation (1,735 IR pixels) was below the p90 of the still period. This is a physical
hardware limitation, not a tuning problem. See CALIBRATION-log.md for full numbers.

### What would detect head rotation

- **Kinect RGB camera** (existing hardware): Facial features translate visibly in
  RGB during rotation. Works only when cave is lit (during playback, not penalty).
  Run RGB diagnostic first before any implementation.
- **Pi NoIR Camera + IR LEDs** (owned, not yet installed): Works in darkness.
  Adds hardware complexity.
- **Skeleton tracking**: Requires Microsoft Kinect SDK (Windows only) — not viable
  on Pi.

---

## 4. What does the image do in response?

**Decision:** TBD — needs experimentation in the actual space.

Current working stack: luminosity + vignette + desaturation driven by the
PenaltyRoutine. Feel is good. Revisit after sensor is dialled in.

### 4a. Empty-cave default — SETTLED

**Decision:** Empty cave reads as **dark**, not bright (`EMPTY_CAVE_DARK=1`,
the new default).

Stillness is the active condition that earns the image, rather than the passive
default. When no one is present, the projected image is dark — the correct
ambient state between visitors and a signal to the next viewer that the space
is ready. Entry by itself does not earn brightness; only sustained stillness
does. See `docs/SPEC-empty-cave-dark.md` for the spec and the four return sites
this affects. Legacy `EMPTY_CAVE_DARK=0` (empty → bright) is kept for rollback.

---

## 5. Runtime target?

**Decision:** Raspberry Pi 5. Confirmed running at 23.976fps with full effects
pipeline. MacBook used for dev only.

---

## 6. Single projector or two?

**Decision:** TBD. Single Nebula Mars 3 Air for now. Apeman M7 (480p) available
as ambient fill if the concept calls for it.

---

## 7. Alternative hardware / sensor paths investigated

Researched 2026-05-11. None selected yet. Documented here for reference if
the Kinect IR optical flow approach is insufficient.

### MSI GS63VR Stealth Pro 4K (owned)
- CPU: Intel Core i7-7700HQ | GPU: NVIDIA GTX 1060 6GB | RAM: 16GB
- Can run **Microsoft Kinect SDK 1.8** (Windows-only) which provides 20
  skeleton joints including head position. This would solve head-turn detection.
- Two deployment options:
  - **A) Laptop as co-processor:** Kinect → USB → MSI Laptop (skeleton tracking)
    → WiFi → Pi (video). Kinect MUST be physically connected to the laptop
    (raw USB data cannot be forwarded over WiFi). Two-device setup, more failure
    points.
  - **B) Laptop replaces Pi entirely:** Kinect + Endymion app all on laptop →
    HDMI → projector. One device, but fan noise in the cave is a real concern for
    a meditative installation.
- **Status:** Not yet pursued. Available as fallback if IR optical flow fails.

### Azure Kinect DK
- Microsoft's successor to Kinect v1. Uses Time-of-Flight depth, 12MP RGB, IMU.
- Body Tracking SDK provides 32 joints. Orbbec's **Femto Bolt** is the
  Microsoft-endorsed replacement (same SDK compatibility).
- **Limitation:** Body Tracking SDK requires x86-64 + NVIDIA CUDA GPU. Does NOT
  run on Raspberry Pi (ARM). Same Windows/x86 constraint as Kinect SDK 1.8.
- **Discontinued** (October 2023). Available as old stock only.
- **Status:** Not purchased. Not pursued unless MSI laptop path is chosen.

### Orbbec cameras (Astra 2, Femto Bolt, Gemini series)
- Orbbec is the primary manufacturer of Kinect-class depth cameras in 2026.
- **Femto Bolt:** Azure Kinect DK replacement, endorsed by Microsoft. Full body
  tracking via Azure Kinect SDK wrapper — but again requires x86-64/CUDA for
  body tracking.
- **Astra 2:** Structured light, 1600×1200 @ 30fps depth, USB-C. Good sensor
  specs but OrbbecSDK minimum requirements are "Ubuntu 20.04/22.04+, quad-core
  2.9GHz+, 8GB RAM" — targeting x86-64, NOT Raspberry Pi.
- **Bottom line:** Orbbec's raw depth/IR streams would likely work on Pi
  (similar to libfreenect for Kinect v1), but skeleton tracking middleware is
  not officially supported on ARM.
- **Status:** Not purchased. Not pursued.

### Pi Camera v3 NoIR + IR LED boards (OWNED — not yet tested)
- **Arducam 8MP IMX219 RPi-CAM-V2 NoIR:** Raspberry Pi camera without IR
  filter — can see 850nm IR light that is invisible to humans.
- **DORHEA 2× 3W 850nm IR LED boards:** Self-contained IR illuminators.
  Plug into mains, flood the scene with invisible IR light.
- Together these create a "night vision" setup: person is illuminated in IR,
  camera sees them clearly, human sees nothing.
- **Potential path:** Run MediaPipe Pose on the IR image → 33 body landmarks
  including nose, ears, shoulders → head turns are geometrically measurable.
- **Known risks:**
  - MediaPipe is trained on visible-light RGB images. IR images differ in
    texture/contrast. Landmark detection may be unreliable on IR without
    retraining.
  - IR LED coverage in the cave must be verified (shadows, projector reflections).
  - Adds new hardware and a new library dependency close to the event.
- **Should test AFTER Kinect IR optical flow**, since that requires no new
  hardware and uses the already-working Kinect infrastructure.
- **Status:** Hardware owned, unopened. Bookmarked for experiment #2.

---

## Decision log

| Date | Decision | Chosen |
|---|---|---|
| 2026-05-09 | Runtime target | Raspberry Pi 5 |
| 2026-05-09 | Video architecture | Architecture A — single loop |
| 2026-05-09 | Active video file | `SlowFilm_4endymion_h264_1080p_v2.mp4` (superseded) |
| 2026-05-20 | Active video file | `SlowFilm_4endymion_h264_1080p_v1.mp4` — v1 chosen for exhibition (better quality) |
| 2026-05-09 | Sensor hardware | Kinect v1 (Xbox 360) — two units owned |
| 2026-05-10 | Sensor algorithm v1 | Raw depth frame differencing — abandoned |
| 2026-05-10 | Sensor algorithm v2 | Background subtraction + centroid — abandoned |
| 2026-05-11 | Sensor algorithm v3 | Background subtraction + mask differencing — implemented, partially working |
| 2026-05-11 | Sensor algorithm v4 candidate | Depth-within-foreground — instrumented, also fails head turns |
| 2026-05-11 | Next sensor experiment | Kinect IR optical flow — NOT YET TESTED |
| 2026-05-11 | Alternative hardware | Investigated MSI laptop, Azure Kinect, Orbbec, Pi Camera — none selected |
| 2026-05-12 | Empty-cave default | Dark — `EMPTY_CAVE_DARK=1`. Stillness earns the image. See `docs/SPEC-empty-cave-dark.md` |
