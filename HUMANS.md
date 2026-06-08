# Endymion — Quick Reference

## SSH into Pi
```bash
ssh box1@raspberrypi.local

ethernet:
ssh -o ServerAliveInterval=30 box1@10.0.0.1



cd ~/my-projects/endymion && source venv/bin/activate
```

## Run the app (Pi)
All settings live in `.env`. Normal launch is just:
```bash
python main.py
```
Stand clear for ~1s. Wait for `[Kinect] Background captured.` then sit down.  
Press `B` to recalibrate background (cave must be empty). Press `Q` or `Esc` to quit.

## Common one-off overrides
Pass any of these in front of `python main.py` to override `.env` for that run only:

| Flag | What it does | Example |
|---|---|---|
| `VIDEO_SPEED=0.5` | Play video at half speed (preferred for the piece) | `VIDEO_SPEED=0.5 python main.py` |
| `VIDEO_SPEED=1.0` | Play video at full speed | `VIDEO_SPEED=1.0 python main.py` |
| `VIDEO_SPEED=0.25` | Play video at quarter speed | `VIDEO_SPEED=0.25 python main.py` |
| `DEBUG=1` | Print sensor values to terminal each frame | `DEBUG=1 python main.py` |
| `LOG_FILE=logs/session.csv` | Write per-frame CSV log for analysis | `LOG_FILE=logs/session.csv python main.py` |
| `EFFECTS=none` | Bypass all effects (baseline / framerate test) | `EFFECTS=none python main.py` |
| `HALF_RES_EFFECTS=0` | Run effects at full resolution (slower, for comparison) | `HALF_RES_EFFECTS=0 python main.py` |
| `EMPTY_CAVE_DARK=0` | Empty cave shows bright video instead of dark | `EMPTY_CAVE_DARK=0 python main.py` |
| `FULLSCREEN=0` | Windowed mode (dev only) | `FULLSCREEN=0 python main.py` |
| `KINECT_MASK_CHANGE_THRESHOLD=50000` | Adjust motion sensitivity (higher = less sensitive) | see calibration log |
| `MOTION_TRIGGER=0.72` | Threshold below which motion is detected (0–1) | see calibration log |
| `HOLD_DURATION=1.0` | Seconds frozen at nadir before recovery starts | see calibration log |
| `RECOVERY_DURATION=5` | Seconds to climb back to full brightness | see calibration log |

**Current Pi `.env` settings (D017 + PR #21):**
```
VIDEO_PATH=assets/video/SlowFilm_4endymion_h264_1080p_v1.mp4
VIDEO_SPEED=0.5
SENSOR_TYPE=kinect
FULLSCREEN=1
EFFECTS=luminosity,vignette,desaturation
HALF_RES_EFFECTS=1
KINECT_FG_DEPTH_THRESHOLD_MM=200
KINECT_MIN_FG_PIXELS=20000
KINECT_MASK_CHANGE_THRESHOLD=38750
MOTION_TRIGGER=0.72
HOLD_DURATION=1.0
RECOVERY_DURATION=5
EMPTY_CAVE_DARK=1
DEBUG=0
LOG_FILE=
```

## Fetch log (Mac)
```bash
getlog D021   # saves as logs/D021.csv — use next available run ID
```

## Git workflow
```bash
git checkout main && git pull
git checkout -b branch-name
# make changes, then:
git add . && git commit -m "message"
git push -u origin branch-name
gh pr create --title "..." --body "..."
# merge on GitHub, then: git checkout main && git pull
# on Pi: git pull
```

## Shut down Pi safely
```bash
sudo shutdown now
```
