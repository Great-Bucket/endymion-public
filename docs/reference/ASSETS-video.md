# Endymion — Video Assets

Tracks the source and export versions of the video used in the installation.
The installation video will always be named a version of **SlowFilm**.

---

## Source: `IF_13_70.mov`

| Property       | Value                                     |
|----------------|-------------------------------------------|
| File           | `IF_13_70.mov`                            |
| Location       | `/Volumes/JUPITER/ReedFilmz/ReedFilmProjects/SlowFilm_IF_2016/` |
| Container      | QuickTime Movie                           |
| Codec          | Apple ProRes 422, Quality: Most (5.00)    |
| Resolution     | 1920 × 1080                               |
| Frame rate     | 23.976 fps (24000/1001) — **not 24.0, not 30** |
| Duration       | ~34 minutes (49,071 frames)               |
| Pixel aspect   | 1.0 (square pixels)                       |
| Color space    | Rec. 709                                  |
| Audio          | None (0 audio tracks)                     |
| Created with   | Adobe Premiere Pro CC 2015.4 (Macintosh)  |

> This is the underlying asset in the Premiere sequence — the uncompressed source master.
> It will not be used in the installation. A trimmed, re-exported version (see below) is the runtime file.
> The Premiere sequence trims the black leader and tail before export.

---

## Installation exports

The source has been trimmed (black leader/tail removed) and exported in three versions.
Files live on the Pi at `~/my-projects/endymion/assets/video/` and on the iMac.

### Produced versions

| File | Size | Bitrate | Duration | Status |
|------|------|---------|----------|--------|
| `SlowFilm_4endymion_h264_1080p_v1.mp4` | 3.87 GB | ~18 Mbps | 33:54 | ✅ Plays on Pi — both soak tests run on this |
| `SlowFilm_4endymion_h264_1080p_v2.mp4` | 509 MB | ~2 Mbps | 33:56 | ✅ Plays on Pi — lower-quality backup |
| `SlowFilm_4endymion_h264_1080p_v3-shorter.mp4` | 3.1 GB | ~15 Mbps avg | 29:52 | ✅ On Pi — **active version** |

**Active:** v3 — set in Pi `.env` as `VIDEO_PATH=assets/video/SlowFilm_4endymion_h264_1080p_v3-shorter.mp4`

> **Bitrate calculation method:** avg bitrate = file size (binary GB × 1,024³ × 8 bits) ÷ duration (seconds). File sizes reported by macOS use binary (1 GB = 1,073,741,824 bytes); bitrate is in decimal Mbps (1 Mbps = 1,000,000 bits/sec). The ~2.4% mismatch per unit step is negligible for these estimates.

> v3 is a re-cut removing less interesting black & green sections (~4 minutes trimmed vs v1/v2).
> v1 retained on Pi as a backup — both soak tests were run on v1.

### Loop specs by version

| Version | Duration | Approx. loops in 4-hour show |
|---------|----------|------------------------------|
| v1 | 33:54 | ~7 |
| v2 | 33:56 | ~7 |
| v3 | 29:52 | ~8 |

### Export settings

| Setting | v1 (as-built) | v2 (as-built) | v3 (as-built) |
|---------|--------------|--------------|--------------|
| Codec | H.264 | H.264 | H.264 |
| Container | `.mp4` | `.mp4` | `.mp4` |
| Resolution | 1920 × 1080 | 1920 × 1080 | 1920 × 1080 |
| Frame rate | 23.976 fps | 23.976 fps | 23.976 fps |
| Bitrate mode | VBR | VBR | VBR, 2-pass |
| Target bitrate | ~18 Mbps | ~2 Mbps | 15 Mbps |
| Max bitrate | — | — | 18 Mbps |
| Key frame distance | — | — | 24 |
| Color space | Rec. 709 | Rec. 709 | Rec. 709 ✅ confirmed via VLC |
| Audio | None | None | None |

Future exports follow the naming convention `SlowFilm_4endymion_<descriptor>.mp4`.
The `VIDEO_PATH` env var points to whichever version is active — no code changes needed to swap.

### Pi testing status

- ✅ v1 plays on Pi at confirmed `23.976 Hz` — fps fix working — used for both soak tests
- ✅ v2 plays on Pi — confirmed as viable lower-quality backup
- ✅ v3 transferred to Pi (2026-05-21) — set as active in `.env`
- ⬜ v3 playback not yet formally tested with full effects stack
- ⬜ Loop-restart seek not yet tested (29:52 mark for v3)

Remaining procedure when ready to do formal performance testing:

1. Transfer v3 to Pi: `scp SlowFilm_4endymion_h264_1080p_v3-shorter.mp4 box1@raspberrypi.local:~/my-projects/endymion/assets/video/`
2. Update `.env`: `VIDEO_PATH=assets/video/SlowFilm_4endymion_h264_1080p_v3-shorter.mp4`
3. Run with full effects: `DEBUG=1 EFFECTS=luminosity,vignette,desaturation python main.py`
4. Watch the fps readout — target is consistent ~23fps
5. If stuttering: enable `HALF_RES_EFFECTS=1` first (see `docs/PERFORMANCE-effects.md`)
6. If still struggling: re-export at 720p and retest

---

## Why frame rate matters: clean math, not running time

The reason to care about frame rate is **processor efficiency and smooth playback**,
not correctness of running time.

The Pi 5 has already shown stuttering under heavier effect combinations. Any
arithmetic the runtime has to do against frame counts (ghosting buffer sizes,
effect period calculations, EMA alpha values) benefits from a clean, predictable
number. The source is 23.976fps (24000/1001). Treat it as **24fps** in all
frame-count formulas:

- 24fps divisors: **1, 2, 3, 4, 6, 8, 12, 24** — all clean integers
- 30fps divisors: 1, 2, 3, 5, 6, 10, 15, 30 — different rhythm, no cleaner
- Mismatched export fps (e.g. re-encoding to 30fps) forces the decoder to
  synthesise or drop frames, adding unnecessary CPU work every single loop tick

The main loop ticks at the video's native fps (read from the file at startup
via `cv2.CAP_PROP_FPS`). Exporting at any other rate would force unnecessary
frame-rate conversion work on the Pi on every frame, every loop.
