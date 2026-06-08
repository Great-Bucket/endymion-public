# Endymion — Calibration Log

Documents the physical setup and findings from calibration runs.
Individual run CSVs live in `logs/` and are committed to git.

---

## D025 — Launch Candidate (2026-05-13)

Best run to date. Supersedes D017 as the launch candidate. Found by systematic
threshold search at the new 87cm platform position — after D022 (40k, too
insensitive), D023 (50k, very bad), D024 (35k, constant false triggers), D025
(38,750) was the goldilocks value. Behaviour matches D017 subjectively.

**Physical setup:**

| Parameter | Value |
|---|---|
| Kinect → chair (front edge, horizontal) | 100 cm |
| Kinect height (stand platform) | 87 cm |
| Kinect height (bottom edge of sensor) | ~90.5 cm |
| Chair seat height from ground | 45 cm |
| Stand | KOOV Projector Stand |
| Viewer seated eye height | ~122 cm |
| Note | Chair height at venue should match — verify before show |

**Settings:**

| Parameter | Value | Notes |
|---|---|---|
| `KINECT_FG_DEPTH_THRESHOLD_MM` | 200 | Unchanged |
| `KINECT_MIN_FG_PIXELS` | 20000 | Unchanged |
| `KINECT_MASK_CHANGE_THRESHOLD` | **38,750** | Tuned for 87cm platform position; noise floor p90=10,255 |
| `MOTION_TRIGGER` | **0.72** | Unchanged from D017 |
| `HOLD_DURATION` | **1.0** | Unchanged from D017 |
| `RECOVERY_DURATION` | **5** | Unchanged from D017 |
| `EMPTY_CAVE_DARK` | **1** | Unchanged from D017 |
| `VIDEO_SPEED` | **0.5** | New — preferred playback rate for the piece |
| `HALF_RES_EFFECTS` | **1** | New — required on Pi for frame rate performance |
| `EFFECTS` | luminosity,vignette,desaturation | Unchanged |

**Threshold search at 87cm platform (2026-05-13):**

| Run | Threshold | Result |
|---|---|---|
| D022 | 40,000 | Too insensitive — small movements missed (glasses removal) |
| D023 | 50,000 | Very bad — even less responsive |
| D024 | 35,000 | Constant false triggers — video stayed dark throughout |
| **D025** | **38,750** | Goldilocks — behaviour matches D017 |

**Note on method:** the correct approach after finding 40k too insensitive and 35k
too strict was to search the interval between them, not to declare the position
unworkable. D025 confirms the 87cm position is viable with the right threshold.

---

## D017 — Previous Launch Candidate (2026-05-12)

Superseded by D025. Retained for reference.

**Physical setup:**

| Parameter | Value |
|---|---|
| Kinect → chair (front edge) | 100 cm |
| Kinect height (stand platform) | 101 cm (corrected from 101.5 — remeasured 2026-05-13) |
| Kinect height (bottom edge of sensor) | 104.5 cm |
| Stand | KOOV Projector Stand |
| Viewer seated eye height | ~122 cm |

**Settings:**

| Parameter | Value | Notes |
|---|---|---|
| `KINECT_FG_DEPTH_THRESHOLD_MM` | 200 | Unchanged from D008 |
| `KINECT_MIN_FG_PIXELS` | 20000 | Unchanged from D008 |
| `KINECT_MASK_CHANGE_THRESHOLD` | **40,000** | Same as D008; trigger at 11,200 with new MOTION_TRIGGER |
| `MOTION_TRIGGER` | **0.72** | Raised from 0.70 — catches more small movements |
| `HOLD_DURATION` | **1.0** | Lowered from ~2.4s — entry feels responsive |
| `RECOVERY_DURATION` | **5** | Lowered from ~8s — brightening not too slow |
| `EMPTY_CAVE_DARK` | **1** | New — cave dark when empty |
| `EFFECTS` | luminosity,vignette,desaturation | Unchanged |

**Behaviour confirmed:**
- Empty cave → dark ✓ (new)
- Entry → dark ✓
- Sitting still → brightens after ~1s hold, ~5s recovery ✓
- Small hand movements within body → triggers ✓
- Torso rock → triggers ✓
- Fast head rotation → triggers ✓
- Leaving → stays dark ✓
- Re-entry with different seat height (+25cm cushions) → still works ✓
- No false triggers from still-sitting ✓

**How we got here from D008:**

| Step | Change | Reason |
|---|---|---|
| D008 → D012 | Distance 137.5cm → 100cm | More pixels per cm of movement; fast head rotation first detected |
| D012 → D014 | Height 73.6cm → 104.5cm (eye level) | Noise floor dropped from ~11,700 to ~8,200; head detection improved |
| D014 → D015 | Added EMPTY_CAVE_DARK=1; threshold 40,000 → 35,000 | Cave dark when empty; threshold too tight, false triggers |
| D015 → D016 | Threshold 35,000 → 40,000; HOLD=1.0; RECOVERY=5 | Eliminated false triggers; entry timing improved |
| D016 → D017 | MOTION_TRIGGER 0.70 → 0.72 | Catches more small movements without false triggers |

---

## Physical Setup (home / development reference)

**Current position (2026-05-13 — pre-D021, uncalibrated):**

| Parameter | Value |
|---|---|
| Kinect → chair (front edge) | 100 cm |
| Kinect height (stand platform) | 87 cm |
| Kinect height (bottom edge of sensor) | ~90.5 cm |
| Stand | KOOV Projector Stand |
| Viewer seated eye height | ~122 cm |
| Status | **Lowered from D017 position for experimentation — pending calibration run D021** |

**D017 position (calibrated, 2026-05-12):**

| Parameter | Value |
|---|---|
| Kinect → chair (front edge) | 100 cm |
| Kinect height (stand platform) | 101 cm |
| Kinect height (bottom edge of sensor) | 104.5 cm |
| Stand | KOOV Projector Stand |
| Viewer seated eye height | ~122 cm |

**D008 position (original, now retired):**

| Parameter | Value |
|---|---|
| Kinect → viewer distance | 137.5 cm (chair front edge) |
| Kinect height from ground | 73.6 cm (bottom edge of Kinect) |
| Viewer eye height (seated) | ~122 cm (48 in) |

Update the "Current position" table whenever hardware moves.

---

## Calibration Run Workflow

```bash
# ON PI — run with explicit params (don't rely on .env for calibration):
SENSOR_TYPE=kinect FULLSCREEN=1 DEBUG=1 \
  EFFECTS=luminosity,vignette,desaturation \
  LOG_FILE=logs/session.csv \
  [parameter overrides] \
  python main.py

# ON MAC — after each run:
getlog D008   # saves as logs/D008.csv (D-series = diagnostic runs with all 4 signals)
```

Stand clear of the Kinect for the first ~1 second (background capture).

---

## Key Findings from E001–E018

### Sensor architecture (E001–E010): frame differencing — abandoned

Runs E001–E010 used a frame-to-frame depth differencing approach on the raw
Kinect depth data. Core finding: this approach was fundamentally unable to
detect lateral (side-to-side) movement. Head turns and body sways that don't
change depth produce no signal. Abandoned in favour of background subtraction.

### Sensor architecture (E011–E018): background subtraction + centroid tracking

Background subtraction correctly isolated the human foreground from the scene.
Key parameter values found:

| Parameter | Working Value | Notes |
|---|---|---|
| `KINECT_FG_DEPTH_THRESHOLD_MM` | **200** | 50 and 100 both caused noise pixels to leak into foreground. 200mm safely above Kinect noise floor at 4ft. |
| `KINECT_MIN_FG_PIXELS` | **20000** | 500 and 5000 too small — noise blobs exceeded threshold. 20000 requires a human-sized foreground blob. |
| `KINECT_BG_FRAMES` | 30 | Works. No reason to change. |

**Centroid tracking proved insufficient.** The centroid is the centre of mass
of the entire foreground silhouette. The torso dominates (60–70% of area), so
arm movements barely shift the centroid. A viewer waving both arms overhead
produced almost no signal change. This is an architectural limitation — no
parameter tuning can fix it.

**Next approach:** foreground mask frame differencing (v3).

---

## Sensor architecture (D-series): foreground mask frame differencing — active

v3 replaced centroid tracking. The algorithm:
1. Builds a background depth model at startup (cave empty).
2. Classifies pixels as foreground when `depth < background - FG_DEPTH_THRESHOLD_MM`.
3. Computes `changed` = number of foreground mask pixels that flipped since last frame.
4. `presence = max(0, 1 − changed / KINECT_MASK_CHANGE_THRESHOLD)`
5. If `presence < MOTION_TRIGGER`, the penalty fires.

**Key discovery: KINECT_MASK_CHANGE_THRESHOLD arithmetic**

For `presence` to clear `MOTION_TRIGGER=0.7` (i.e., video stays bright), `changed` must be
≤ `0.3 × KINECT_MASK_CHANGE_THRESHOLD`. The confirmed noise floor while sitting still is
**~9,500–11,500 changed pixels**. This means the threshold must be at least **~38,000** to
prevent the still noise floor from triggering the penalty.

| Run | `KINECT_MASK_CHANGE_THRESHOLD` | Breakpoint | Outcome |
|---|---|---|---|
| D001–D004 | 40,000 | 12,000 | Reasonably functional; missed slow head turns |
| D005 | (same) | 12,000 | Baseline |
| D006 | 1,000 | 300 | Pinned dark entire session — threshold 10× below noise floor |
| D007 | 50,000 | 15,000 | Working: still=bright, fast movement=dark. Speed-sensitive. |

**Key discovery: velocity detection**

The v3 mask differencing measures frame-to-frame change — it is fundamentally a
**velocity detector**, not a displacement detector. Slow movements (even large ones)
produce little mask change between consecutive frames and go undetected. Fast movements
produce large frame-to-frame changes and trigger the penalty. This applies even to
movements within the torso silhouette (confirmed D007): slow reach toward screen = no
trigger; fast reach toward screen = triggers. Breathing is slow enough to never trigger.

This behaviour is acceptable for the installation (fidgeting is fast; settling in is
slow), but the algorithm cannot detect someone slowly turning their head over several
seconds.

**D008 — Launch Candidate (threshold=40,000)**

Best run to date. Settings:

| Parameter | Value |
|---|---|
| `KINECT_FG_DEPTH_THRESHOLD_MM` | 200 |
| `KINECT_MIN_FG_PIXELS` | 20000 |
| `KINECT_MASK_CHANGE_THRESHOLD` | **40,000** |
| `MOTION_TRIGGER` | 0.7 |
| `EFFECTS` | luminosity,vignette,desaturation |

Behaviour confirmed:
- Empty cave → bright ✓
- Entry → dark ✓
- Sitting still → bright ✓
- Moderate torso rock → triggers ✓
- Extended arm → triggers ✓
- Fast reach within torso → triggers ✓
- Slow reach within torso → does NOT trigger (acceptable — breathing-level)
- Head rotation (any direction, any speed) → does NOT trigger ✗

**Known limitation:** Head rotation is invisible to v3 mask differencing. Head detection
requires a different signal. See D009 findings below.

---

## D009 — Head Rotation Diagnostic (DEFINITIVE)

**Purpose:** Confirm whether any logged signal detects head rotation.

**Sequence:** ~30s still → yaw L/R → pause → pitch U/D → pause → hold-right → hold-left
→ still → U/D → fast U/D → full 180° head circle → still → exit.

**Statistical result (5-second window analysis by Claude Code):**

| Segment | What was happening | `changed` p50/p90/p99 | `moved_ir_pixels` p50/p90/p99 |
|---|---|---|---|
| t=10–30s | Sitting still | 10,177 / 16,022 / 43,833 | 1,576 / 6,086 / 31,257 |
| t=30–140s | All head rotations | **10,023 / 10,723 / 11,192** | **1,509 / 1,641 / 1,735** |
| t=140–145s | Exit | 35,918 / 52,266 | 22,541 / 27,243 |

**The p99 of the head-rotation period sits below the p90 of the still period.**
This is not a threshold problem. Head rotation is invisible to all four signals.

**Why each signal fails:**

- **v3 `changed`:** The head is a roughly symmetric oval from the Kinect's viewpoint.
  90° rotation changes the silhouette outline by ~5–10 pixels per side — less than 5%
  of the ~10,000-pixel noise floor from depth jitter at the head/wall boundary.

- **v4 `moved_pixels` / `mean_abs_ddepth`:** Head rotation moves the face through
  angles, not distances. The depth change at prominent features (nose, chin) is
  30–60mm — within or at the `KINECT_DEPTH_NOISE_FLOOR_MM=30` threshold.

- **v5 `moved_ir_pixels`:** The Kinect's IR emitter projects a **fixed** dot pattern
  in world coordinates — dots do NOT travel with the face. Skin is approximately
  Lambertian (diffuse), so rotating it under a fixed illumination source produces
  nearly identical pixel intensity regardless of angle. This is a physical limitation
  of structured-light sensing of smooth diffuse surfaces. The IR optical flow proposal
  (SPEC-kinect-v5-ir-optical-flow.md) was based on a mistaken assumption that dots
  were anchored to the subject — they are not. That spec is now invalidated.

**Conclusion:** depth + IR via libfreenect has been exhausted as a route to head
rotation detection on Kinect v1. No amount of algorithm tuning changes this.

---

## D010 — Ratio-Based Threshold Test (FAILED — reverted)

**Purpose:** Test `changed / n_fg` ratio threshold as a scale-invariant alternative
to the absolute `KINECT_MASK_CHANGE_THRESHOLD`.

**Settings:** `KINECT_MASK_CHANGE_RATIO=1.17`, `MOTION_TRIGGER=0.7` (equivalent to
triggering when ratio > 0.35).

**Result:** Much worse than D008. Vigorous arm-waving over head and to the side
produced `raw ≈ 0.75` — above the 0.7 trigger, so no penalty fired. Only reaching
directly toward the camera triggered darkness. Reverted via PR #17.

**Why it failed:** When an arm extends sideways, both `changed` and `n_fg` grow
together — new foreground area appears AND its boundary pixels change. The ratio stays
flat, so the trigger doesn't fire. The absolute threshold works because arm extension
adds a large *absolute* `changed` count regardless of `n_fg`.

Root cause: `changed` scales with silhouette perimeter (≈ √area), not area. Dividing
by `n_fg` (area) systematically makes large body movements appear proportionally
smaller. Do not retry.

**D008 restored as launch candidate. Git: PR #16 (feat) then PR #17 (revert).**

---

## Head Rotation: Paths Forward

Three options exist. The choice is a design question, not a technical one.

### Path A — CHOSEN. D008 is the launch candidate.

**RGB diagnostic run 2026-05-12, dark room, projector as sole light source.**
All 10 frames were essentially black — only the Kinect's own indicator LED and the
distant projector screen were visible. No person, no face, no usable image content.
The projector faces the screen, not the viewer; it provides almost no return
illumination for the RGB camera at the viewer's position.

**Path B is closed.** RGB face detection cannot work under installation lighting
conditions. No further RGB experiments are warranted.

### Path B — CLOSED (RGB requires light the cave does not provide)

Ruled out by the 2026-05-12 diagnostic. Kinect v1 RGB is unusable in darkness.

### Path C — Pi NoIR Camera + IR LEDs (new hardware, deferred)

The IR camera (already owned, never installed) with IR illumination would see facial
features regardless of ambient light. This remains an option for a future iteration
if head rotation detection becomes a hard requirement. Not needed for launch.

---

## Lighting Conditions Key

| Code | Description |
|---|---|
| L-DAY-BRIGHT | Daytime, bright exterior light, no direct sun into room |
| L-DAY-OVERCAST | Daytime, overcast |
| L-DUSK | Transitional — fading exterior light |
| L-DARK | Evening/night, no exterior light |
| L-DARK-AMBIENT | Evening, some ambient interior lighting |

---

## Open Risk: Chair Movement During Event

The background calibration model is captured at startup with the cave empty.
If the chair moves after calibration, it becomes persistent foreground and
generates false motion signals for the rest of the session.

For a 4-hour event, the chair will inevitably shift between visitors.

**Mitigations:**
- Tape or bolt the chair to the floor. Calibrate once with chair in place.
- Attendant presses `B` to recalibrate between visitors (keyboard connected to Pi).
- The B-key recalibration is already implemented and takes ~1 second.

---

## Parameter Reference

| Parameter | What it controls | Notes |
|---|---|---|
| `KINECT_FG_DEPTH_THRESHOLD_MM` | Depth diff (mm) to classify a pixel as foreground | **200** — confirmed working at 137.5cm |
| `KINECT_MIN_FG_PIXELS` | Min foreground pixels to consider cave occupied | **20000** — confirmed working |
| `KINECT_MASK_CHANGE_THRESHOLD` | Pixel flip count that maps to presence=0 | **40000** — D008 launch value; set to ~3.5× noise floor |
| `KINECT_BG_FRAMES` | Frames averaged for background model | 30 (~1s at 30fps) |
| `MOTION_TRIGGER` | Presence threshold below which penalty fires | **0.7** — D008 value; higher = more sensitive |
| `NADIR` | Luminosity floor during penalty | 0–1; 0.12 = ghost image visible |
| `HOLD_DURATION` | Seconds frozen at nadir after last motion | seconds |
| `RECOVERY_DURATION` | Seconds to climb back to full brightness | seconds |
| `RECOVERY_CURVE` | Power curve for recovery shape | >1 = lingers in darkness |
