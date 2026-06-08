# Effects Pipeline — Performance Notes

## Context

The effects pipeline runs per-frame in the main loop alongside video decode and sensor read. On the development iMac this is fine for most combinations, but on the Raspberry Pi 5 (the intended event hardware) frame budget will be tight. This document captures known bottlenecks and candidate optimisations, to be revisited when Pi testing begins.

Target: **1080p at 23.976fps** (the source frame rate) on the Pi 5. Fallback: **720p at 23.976fps** if needed.

---

## Effect Cost Ranking — measured on Pi 5 at 1080p (`luminosity,vignette,desaturation`)

Per `EFFECTS_PROFILE=1` average over 100 frames, viewer out of frame so pipeline runs at full cost:

| Effect | Pi cost (1080p) | % of total | Why |
|---|---|---|---|
| Vignette | ~96 ms | 69 % | Per-pixel `np.exp` over 2M pixels + full-frame float multiply |
| Luminosity | ~35 ms | 25 % | `frame * brightness` allocates a 6.2M-element float64 array (~50 MB), casts back to uint8 |
| Desaturation | ~8 ms | 6 % | Two OpenCV cvtColor calls + `addWeighted`. OpenCV is fast on Pi here. |
| **Total** | **~140 ms** | — | 3.3× over the 41.7 ms budget at 24 fps |

**This is inverted from the pre-measurement assumption** that desaturation would dominate. Luminosity and vignette — both pure numpy — are hit hardest by ARM memory bandwidth; OpenCV's C implementation of cvtColor is comparatively cheap.

After `HALF_RES_EFFECTS=1` (see §1 below): total drops to ~34 ms, comfortably inside budget.

**Active stack for the piece**: `luminosity, vignette, desaturation`. Ghosting and blur are deprioritised.

---

## Candidate Optimisations

### 1. Half-resolution effect processing — **IMPLEMENTED**

Apply the entire effect pipeline at 960×540 (half width/height = quarter pixel count), then scale back up to display resolution before blitting. The single highest-leverage change — it quarters the work for every effect simultaneously.

Wired via `HALF_RES_EFFECTS=1` env var. See `src/visual/player.py` and `docs/SPEC-effects-performance.md` §4.

**Pi result:** total pipeline cost 140 ms → ~34 ms (4.1×). Visually crisp at projection throw; the upscale artifact is not visible at viewing distance.

---

### 2. Desaturation — replace double conversion with channel blend — **INVESTIGATED AND REJECTED**

The original recommendation was to replace `RGB→GRAY→RGB` + `cv2.addWeighted` with a single numpy weighted average:

```python
# Luminance-weighted grayscale in one pass (no intermediate conversion):
gray_value = (0.299 * frame[:,:,0] + 0.587 * frame[:,:,1] + 0.114 * frame[:,:,2])
gray_rgb = np.stack([gray_value, gray_value, gray_value], axis=2)
result = (gray_rgb * (1 - presence) + frame * presence).astype(np.uint8)
```

The premise was that removing two full-frame OpenCV calls would be a free win. **Direct benchmarking refutes this.** Mac at half-res (540×960), 200 frames each, warmed:

```
cv2 cvtColor x2 + addWeighted  :  0.47 ms / frame
numpy weighted blend (Rec. 601):  3.35 ms / frame   (~7× slower)
```

The cv2 path runs as a SIMD-optimised C pass over uint8; the numpy path promotes the frame to float64 (~50 MB at 1080p) and runs several full-frame multiplies through Python's array-op overhead — the same shape of cost that makes luminosity and vignette expensive on the Pi. Output is bit-equivalent (±1 LSB at extremes) so there is no quality difference either.

**Keep the cv2 path. Do not implement the numpy replacement.** See `docs/SPEC-effects-performance.md` §2 for the full investigation.

---

### 3. Vignette — gaussian_mask caching — **IMPLEMENTED**

The distance array (`_dist`) was already cached per frame size. The `gaussian_mask` itself, however, was being recomputed every frame even when `sigma` was unchanged. Now cached on `(shape, sigma)` and invalidated when either changes. See `VignetteEffect` in `src/visual/effects.py`.

**Cache hits** during the HOLDING phase (smoothed pinned to nadir → sigma constant for the full hold window). Cache *misses* during FALLING / RECOVERING where sigma changes every frame. The bright bypass (§3 of SPEC-effects-performance) covers the BRIGHT phase entirely.

**Mac measurement (540×960 frames):** ~1.4 ms/frame saved when sigma is constant. The Pi vignette cost is dominated by the full-frame multiply (~96 ms), not the `np.exp`, so this is a small but free win — not a structural fix. The remaining heavy lifting is done by half-resolution processing (§1).

The original note about precomputing to float32/float16 is unaddressed; could halve memory bandwidth for the multiply if needed later.

---

### 4. Ghosting — reduce buffer size (if ghosting is re-introduced)

Ghosting is currently deprioritised. If brought back:

- Reduce `buffer_size` from 8 to 3–4 frames. Visually still produces the temporal echo; computationally half the work.
- Alternatively, blend at half resolution (see point 1) and upscale before compositing.

---

### 5. Luminosity — *not* optimal on Pi (~25 % of total)

Originally marked "negligible" on the assumption that a scalar multiply is essentially free. Pi profiling refuted this: `np.clip(frame * brightness, 0, 255).astype(np.uint8)` allocates a float64 array of ~50 MB per frame at 1080p, casts it back to uint8 — pure memory bandwidth. ARM memory subsystem is the bottleneck, not the arithmetic.

The half-resolution path (§1) brings this within budget by quartering the pixel count. A further optimisation would be to do the multiply directly on uint8 with `cv2.convertScaleAbs(frame, alpha=brightness)` — single C-level pass, no float intermediate. Not implemented yet.

---

## Pi 5 Testing Checklist — historical (kept for reference)

The order below was the pre-measurement plan. Pi testing has since shown that the dominant cost is **memory bandwidth from full-frame numpy operations**, not OpenCV calls. The practical setting on the Pi is `HALF_RES_EFFECTS=1` plus the bright bypass — see `docs/SPEC-effects-performance.md` for the implemented optimisations.

Original order (kept for any future hardware re-evaluation):

1. Baseline: video playback only (`EFFECTS=none`) — confirms Pi can decode the video at 23.976fps
2. Add luminosity — note frame rate change (actually ~25 % of pipeline cost on Pi at full res)
3. Add vignette — note frame rate change (actually ~69 % of pipeline cost on Pi)
4. Add desaturation — note frame rate change (only ~6 % of pipeline cost on Pi)
5. Enable `HALF_RES_EFFECTS=1` — 4× speedup, brings total to ~34 ms / inside budget
6. If still struggling: 720p video transcode, or move pipeline to GLSL fragment shader (below)

---

## Notes on GPU / Shader Path

All current effects run on the CPU via NumPy/OpenCV. A future optimisation path — if CPU effects prove insufficient — is to move the pipeline to a GLSL fragment shader via `moderngl`. This was listed as an optional dependency in `requirements.txt` from the outset. The Pi 5's GPU can handle simple per-pixel shaders easily and would offload the CPU entirely.

This is a significant rewrite and should only be considered if CPU optimisations are insufficient.
