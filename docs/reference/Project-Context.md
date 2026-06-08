# Endymion — Project Context

> Starting-point notes for building the software side of an interactive video installation.
> **Status:** exploratory. Many decisions are still open. Treat this as a brief, not a spec.

---

## What the piece is

*Endymion* is an interactive video installation in which a single viewer enters a small, cave-like space and is bathed in light from a projector. The image on the screen responds to the viewer's presence — but not in a gamified, gesture-controlled way. The viewer's **stillness and attention** are the input. The image evolves in response.

The piece is named after the Greek myth of the sleeper on Mount Latmus, kept eternally with his eyes open and beheld nightly by Selene's descending moonlight. The myth's central scene is a *mutual gaze*: a still mortal and a descending light watching one another.

### Core research question

> How can an interactive video installation enact the mutual gaze at the heart of the Endymion myth — the open-eyed sleeper and the descending moon beholding one another in a cave — by designing a circuit in which a viewer's stillness shapes the projected image, and the projected image, in turn, shapes the viewer?

### Conceptual frame

The piece positions itself against two dominant modes of screen-based encounter: the **spectacle** that demands attention, and the **interface** that demands action. It belongs to a third register — ambient, restrained, attuned to presence rather than performance — which might be called the *receptive-generative* paradox: the viewer is most active when most still.

This register draws on **Joanna Zylinska's notion of nonhuman vision**: the proposition that machines see in ways decoupled from human agency, and that this asymmetry can disrupt the human-centered world. Here the sensor perceives the viewer in ways the viewer cannot return (depth, motion vectors, skeletal pose, heat) — a technological reinscription of Selene's gaze. What unfolds on the scrim is neither cinema nor interface but something between: a form of mutual watching in which seeing and being-seen become inseparable.

*(Full theoretical grounding — Zylinska, the myth, Ars Electronica context — is held in separate research notes.)*

### Design principles (distilled from the concept)

These should constrain technical decisions:

1. **Stillness is the input, not gesture.** Reward presence; do not reward waving, posing, or "playing." A still viewer is the active ingredient. The sensor responds to body-level commitment to stillness — not micro-policing of every glance. Head orientation is freely the viewer's; it is the body that must be present. This distinction is intentional, not a hardware limitation.
2. **Ambient, not interactive in the gaming sense.** No score, no win-state, no clear cause-and-effect that the viewer can game. The viewer should not be sure exactly *what* they are doing to the image.
3. **The circuit is mutual.** The image shapes the viewer just as the viewer shapes the image. The piece should pull the viewer toward stillness, not just respond to it.
4. **Asymmetric perception.** The sensor sees the viewer in ways the viewer cannot return — body heat, motion vectors, depth, skeletal pose. This asymmetry is part of the work, not a bug to hide.
5. **Slow time.** Changes should unfold over seconds and minutes, not frames. No twitchy responsiveness. Think weather, breath, tide.
6. **Loops, not narratives.** Content should be loop-friendly and have no clear beginning/end. The viewer enters and leaves freely.

---

## Physical development setup (home / reference configuration)

**Current position (2026-05-13 — lowered for D021 experimentation):**

| Parameter | Measurement |
|---|---|
| Kinect stand | KOOV Projector Stand |
| Kinect height (stand platform) | 87 cm |
| Kinect height (bottom edge of sensor) | ~90.5 cm |
| Kinect → chair (front edge of chair seat) | 100 cm |
| Viewer seated eye height | ~122 cm (48 in) |
| Status | Uncalibrated — D021 run pending |

**D025 position (home development, 2026-05-13):**

| Parameter | Measurement |
|---|---|
| Kinect height (stand platform) | 87 cm |
| Kinect height (bottom edge of sensor) | ~90.5 cm |
| Kinect → chair (front edge, horizontal) | 100 cm |
| Chair seat height from ground | 45 cm |
| `KINECT_MASK_CHANGE_THRESHOLD` valid at this position | 38,750 |

**Event position (venue, 2026-05-21) ← active:**

| Parameter | Measurement |
|---|---|
| Kinect height (stand platform) | 87 cm |
| Kinect height (bottom edge of sensor) | ~90.5 cm |
| Kinect → chair (front edge, horizontal) | 100 cm |
| Chair seat height from ground | 43 cm |
| `KINECT_MASK_CHANGE_THRESHOLD` | 7500 (calibrated on site, 2026-05-21) |
| p90 still floor at this position | 2,038 (vs ~11,000 at home — gallery cave has much lower IR noise) |

**D017 position (previous launch candidate):**

| Parameter | Measurement |
|---|---|
| Kinect height (stand platform) | 101 cm |
| Kinect height (bottom edge of sensor) | 104.5 cm |
| Kinect → chair (front edge of chair seat) | 100 cm |
| `KINECT_MASK_CHANGE_THRESHOLD` valid at this position | 40,000 |

Any change to Kinect height or distance requires a full recalibration run before
D017 sensor settings are valid again. See `docs/CALIBRATION-log.md` for procedure.

---

## Practical constraints

- **Event date:** ~2 weeks out at time of writing. Hard deadline.
- **Duration:** 4-hour run. Software must run unattended for 4 hours. Crashes mid-show = bad.
- **Space:** 8.3 ft × 3.25 ft enclosed pocket. Dim/dark. One viewer at a time, seated. Display surface is a fabric scrim (or small physical screen — TBD).
- **Network:** Cannot assume reliable WiFi at venue. Build offline-first.

## Operational model (event)

Endymion runs as a **self-serve installation** for the full duration of the event:

- Started once at the beginning of the show, stopped at the end.
- A sign outside the cave reads "one person at a time."
- Visitors enter, sit for as long as they like, and leave on their own. No prompting.
- Gaps between visitors may range from seconds to several minutes.
- The artist is present at the event and can intervene if needed, but is not stationed at the cave. Think "attended but autonomous" — not "Mars orbiter."

**Physical mitigations:**
- Chair is taped to the floor. Sign asks visitors not to move it.
- Artist checks on the setup periodically.
- B-key recalibration available as manual fallback if needed (keyboard connected to Pi).

**Implications for the software:**
- The system must handle the full visitor cycle autonomously: empty → entry → session → exit → empty, repeating for 4 hours without degrading.
- Video loops indefinitely — already implemented (`VideoPlayer` seeks to frame 0 at end of file).
- Video plays dark between visitors (empty cave = dark, once `EMPTY_CAVE_DARK` is implemented) — signals to the next visitor that the space is ready.
- Auto-recalibration is desirable but not mandatory given the chair is fixed and the artist is present.

---

## Hardware inventory

### Already purchased and in hand

| Item | Notes |
|---|---|
| Nebula Mars 3 Air projector | 1080p native, 400 ANSI lumens, HDMI input, ~2.5hr battery (will be plugged in for show) |
| Raspberry Pi 5 (8GB) — CanaKit Starter Kit PRO | 128GB SD, active cooler, 27W PSU, micro-HDMI cables, Turbine Black case |
| KOOV Projector Stand | Adjustable 20–61", tray-style top, 360° rotation/tilt |
| Apeman M7 projector (older, 2018) | ~100 ANSI lumens, 480p, HDMI only. Available as a possible second projector. |

### Possible input sensors (already owned)

| Sensor | Status | Notes |
|---|---|---|
| Kinect v1 (Xbox 360) | **Active — fully integrated on Pi 5** | Depth sensor, background subtraction, sensor tuning in progress |
| Leap Motion Controller | Not pursued | Hand/finger tracking, near-field (~60cm). Leap Motion not well-suited to full-body stillness detection. |
| MacBook M4 webcam | Dev fallback (`SENSOR_TYPE=camera`) | Frame differencing, useful for dev without Pi |

### Auto-shutoff and the Mars 3 Air

The Mars 3 Air will sleep on HDMI inactivity (10 min) and auto-power-off in standby (30 min). For a 4-hour install, **the Pi must keep a continuous HDMI signal alive at all times**, even when "nothing is happening" visually. A black screen is fine; no signal at all is not. Auto-shutoff settings should also be disabled in the projector's menu.

---

## Software landscape (to evaluate, not yet committed)

### Likely development setup

- **Develop on:** MacBook M4 (fast iteration, good debugging)
- **Deploy to:** Raspberry Pi 5 connected to projector via HDMI
- Aim for a stack that runs on both with minimal porting friction.

### Candidate stacks

**Python + OpenCV + pygame / pyglet / moderngl**
- Pros: runs on both Mac and Pi 5, integrates with every sensor, good for camera-based motion detection, easy to wire up
- Cons: real-time video manipulation can be performance-sensitive; shader work requires moderngl or similar
- Likely the default unless something compelling pulls us elsewhere

**openFrameworks (C++)**
- Pros: industry standard for installation art, excellent video and shader support, runs on Pi
- Cons: C++ build cycle slower for quick iteration; steeper if not already familiar

**Processing (Java) or p5.js (browser)**
- Pros: fast prototyping, designed for this kind of work
- Cons: Processing on Pi is workable but not great; p5.js in a browser adds a layer

**TouchDesigner**
- Pros: the de facto tool for installation video, beautiful results fast
- Cons: paid, not really a Cursor/code workflow, doesn't run on Pi (Mac only at the show)

**Recommendation as a starting bet:** Python on both Mac and Pi 5. Use OpenCV for camera input, dedicated SDK if going with Leap or Kinect, and either pygame (simple) or moderngl + GLSL shaders (for richer real-time visual effects). If shaders feel like too much, pre-render video variants and crossfade/blend between them based on input.

### Video playback fallback

If real-time generation proves too ambitious in the timeline, a viable simpler architecture: **pre-render multiple video loops** and have the software crossfade or blend between them based on sensor input. This keeps the runtime code simple (a video player + a mixer) and pushes complexity into pre-production. Pi Video Looper 2 is loop-only and won't do this directly; we'd need a custom player (OpenCV VideoCapture or VLC bindings can do it).

---

## Possible architectures

### Architecture A — single video, parameter-modulated

```
[sensor] → [stillness/presence value] → [shader parameters / playback speed / opacity]
                                              ↓
                                         [single video loop on screen]
```

Simplest. One video, but its rendering is modulated — speed, brightness, blur, color, glitch, etc. — by what the sensor reads.

### Architecture B — two videos blended

```
[sensor] → [blend coefficient]
                    ↓
[video A] ──────► [mixer] ──────► [output]
[video B] ──────►        
```

Two pre-rendered loops crossfade based on input. Simple to implement, very effective if the two videos contrast well (e.g., one bright/active, one dark/still).

### Architecture C — generative

```
[sensor] → [parameters] → [shader / generative algorithm] → [output]
```

No source video at all; the image is generated in real time from sensor data. Highest ceiling, highest risk.

### Architecture D — sensor-driven shader on top of source video

```
[sensor] → [shader uniforms]
                    ↓
[video loop] ──► [GPU shader] ──► [output]
```

Best of both: stable source video + real-time GPU effects driven by sensor. Probably the sweet spot if shader work is in scope.

---

## Open decisions

1. **Which sensor?** ✅ Kinect v1 (Xbox 360). Two units owned and working on Pi 5.
2. **One video or two?** ✅ Single loop — `SlowFilm_4endymion_h264_1080p_v2.mp4`.
3. **What does the sensor measure?** In progress — see `docs/DECISIONS.md` and `docs/SPEC-kinect-v2.md`.
4. **What does the image do in response?** Working stack: luminosity + vignette + desaturation. Revisit after sensor is dialled in.
5. **Runtime: Pi only, or Mac at the show?** ✅ Raspberry Pi 5.
6. **Single projector or two?** TBD. Single Nebula Mars 3 Air for now.

---

## Website

The public-facing webpage for this installation:

**https://www.reedobeirne.com/endymion-revisited/**

---

## Existing assets

- **Leap Motion hackathon code** (~2 months old). Should be the first thing reviewed for what's already working. Likely a fast path to a working sensor input.
- **Multiple physical movie screens** owned. Need to find one small enough to fit the pocket, or use a fabric scrim instead.

---

## Remaining milestones

1. ✅ Pi 5 booting, video playing fullscreen at 23.976fps
2. ✅ Effects pipeline (luminosity, vignette, desaturation) running on Pi
3. ✅ Kinect v1 integrated — background subtraction, foreground extraction working
4. ⬜ **Sensor tuning** — implement mask differencing (`docs/SPEC-kinect-v2.md`) and dial in sensitivity
5. ⬜ **Projector calibration** — tune NADIR on actual projector surface (reads ~20% brighter than screens)
6. ⬜ **Performance check** — verify ~24fps with full effects stack on Pi
7. ⬜ **4-hour soak test** — unattended run, check for crashes/thermal/HDMI dropout
8. ⬜ **Autostart on boot** — Pi launches app on power-up, no keyboard needed at venue
9. ⬜ **On-site dry run** — test in the actual cave space if possible

---

## What this doc is not

- Not a finalized spec. Many decisions deliberately left open.
- Not a research summary. Theoretical grounding (Zylinska, the myth, etc.) is held in separate notes.
- Not a hardware build guide. Assumes the Pi 5 kit is assembled per CanaKit instructions.

The goal of bringing this into Cursor is to have a coding companion that understands *why* the piece is the way it is, so when proposing implementations it can reach for ones that match the design principles above — quiet, slow, mutual, asymmetric — rather than defaulting to gamified, twitchy, gesture-driven patterns.