# Pi Setup — Operational Reference

Raspberry Pi 5 is the production runtime. This document is the operational
reference for connecting, running, and maintaining the Pi during development
and at the event.

---

## Pi connection

### Over ethernet (preferred — works at any venue, no WiFi needed)

The Pi has a static IP on its ethernet port. The Mac adapter is configured to match.
Plug in the cable and:

```bash
ssh -o ServerAliveInterval=30 box1@10.0.0.1
```

The `-o ServerAliveInterval=30` prevents the connection dropping during idle periods.

> **Known issue (2026-05-21 venue):** `ssh box1@10.0.0.1` gives "Connection refused" even though ping to 10.0.0.1 succeeds. SSH via `raspberrypi.local` works because mDNS resolves to the Pi's IPv6 link-local address on eth0, which SSH accepts. Root cause is likely a firewall zone restriction on the `direct-eth` nmcli profile blocking IPv4 port 22. **Workaround: use `raspberrypi.local` instead of `10.0.0.1` for SSH.** Fix to be investigated post-event.
If you added the entry to `~/.ssh/config` (see below), plain `ssh box1@10.0.0.1` works too.

**`~/.ssh/config` entry (on Mac — keeps connection alive automatically):**
```
Host 10.0.0.1
  User box1
  ServerAliveInterval 30
  ServerAliveCountMax 6
```

**One-time setup (already done — recorded here for reference):**

*On Pi:*
```bash
sudo nmcli connection add type ethernet ifname eth0 con-name "direct-eth" \
  ipv4.method manual ipv4.addresses "10.0.0.1/24" \
  ipv6.method link-local autoconnect yes
sudo nmcli connection up "direct-eth"
```

*On Mac:* System Settings → Network → AX88179A → Details → TCP/IP →
Configure IPv4: **Manually**, IP: `10.0.0.2`, Subnet: `255.255.255.0` → OK → Apply.

This profile persists across Pi reboots (`autoconnect yes`). `10.0.0.1` is always
available as long as the cable is plugged in.

### Over WiFi (fallback — home network or venue WiFi if client isolation is off)

```bash
ssh box1@raspberrypi.local
```

If `.local` fails: `arp -a | grep raspberry` on the Mac to find the current IP.

**Python version on Pi: 3.11.2.** Mac venv should match.

---

## Running the app on the Pi

```bash
# ON PI — standard run (all settings in .env, just:)
python main.py

# Override for a calibration/diagnostic run:
DEBUG=1 LOG_FILE=logs/session.csv python main.py
```

Stand clear of the Kinect for the first ~1 second. Watch for
`[Kinect] Background captured.` before entering the cave.

Press `Q` or `Escape` to quit. Press `B` to recalibrate the background
(see Recalibration section below).

---

## Pi .env (current working config)

```
SENSOR_TYPE=kinect
VIDEO_PATH=assets/video/SlowFilm_4endymion_h264_1080p_v1.mp4
VIDEO_SPEED=0.5
FULLSCREEN=1
EFFECTS=luminosity,vignette,desaturation
HALF_RES_EFFECTS=1
SIGNAL_MODE=penalty
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

These are the **D025 launch-candidate settings** (2026-05-13). Kinect platform
at 87cm. `KINECT_MASK_CHANGE_THRESHOLD=38750` was found by systematic threshold
search at this height. `VIDEO_SPEED=0.5` is the preferred playback rate.
`HALF_RES_EFFECTS=1` is required on the Pi for frame rate performance. Do not
change sensor parameters without running a new calibration session. See
`docs/CALIBRATION-log.md` for the full history.

---

## Log workflow

After each Pi test run, fetch the log to the Mac using `scp`:

```bash
# ON MAC — copy session.csv and save as a named run file:
scp box1@raspberrypi.local:~/my-projects/endymion/logs/session.csv logs/D010.csv
```

D-series = diagnostic runs with all four signals logged.
`logs/session.csv` on the Pi is overwritten each run and is gitignored.

---

## Recalibration (Kinect background model)

The Kinect captures a background depth model of the empty cave at startup.
Any object that moves after calibration becomes foreground and generates false
motion signals.

- **At startup:** auto-calibrates for ~1 second (`KINECT_BG_FRAMES=30`).
  Cave must be empty. Watch for `[Kinect] Background captured.`
- **Press `B` mid-run:** recaptures background. Use between visitors or if
  anything in the scene shifts (chair moved, sensor bumped). Cave must be
  empty during the ~1 second capture.

**Risk:** the chair is not fixed and will move during a 4-hour event. Options:
- Tape/bolt chair to floor. Calibrate once with chair in place.
- Attendant presses `B` to recalibrate between visitors (keyboard must be
  connected to Pi).

---

## Git workflow

**All changes go through a PR — no direct commits to `main`.**
Branch protection is ON on GitHub.

```bash
# Start any piece of work:
git checkout main && git pull
git checkout -b your-branch-name

# After making changes:
git add . && git commit -m "message"
git push -u origin your-branch-name
gh pr create --title "..." --body "..."

# After merging on GitHub:
git checkout main && git pull
# On Pi: git pull
```

This applies to everything — code changes, doc updates, config changes.
No exceptions. Keeping main clean through PRs makes it easy to pull onto
the Pi and know exactly what's there.

---

## MacBook dev environment

```bash
git clone git@github.com:Great-Bucket/Endymion.git
cd endymion && python3 -m venv venv
source venv/bin/activate && pip install -r requirements.txt
cp env.example .env
```

The large video file is not in the repo. For local dev use the short test clip:
```
VIDEO_PATH=assets/video/20240905_digital-catapult-team.mov
```

---

## Venue calibration procedure

**D008 settings are calibrated to the home development setup. They will not transfer
directly to the gallery without recalibration.** The one parameter that must be
re-measured on site is `KINECT_MASK_CHANGE_THRESHOLD`.

### On-site calibration steps

1. Place Kinect and chair. Aim for **105–120 cm Kinect-to-chair**, Kinect height
   **60–75 cm** from floor (within the known working envelope). Bring the same chair
   if possible — chair height drives where the silhouette sits in the frame.
2. Start a D-series instrumented run with `DEBUG=1 LOG_FILE=logs/session.csv`.
3. Sit still in the chair for 30 seconds. Exit. Stop the run.
4. Fetch the log: `scp box1@raspberrypi.local:~/my-projects/endymion/logs/session.csv logs/D010.csv` (use next available run ID).
5. Find the p90 value of the `changed` column during the still segment.
6. Set `KINECT_MASK_CHANGE_THRESHOLD = 3.5 × p90_still_floor` (rounded to nearest 5,000).
   - Example: p90 still = 11,000 → set threshold to 38,500 → use **40,000**.
   - Example: p90 still = 14,000 (closer placement) → set threshold to **50,000**.
7. Run a verification test with the new threshold. With `EMPTY_CAVE_DARK=1`
   (the default — see `docs/SPEC-empty-cave-dark.md`), confirm:
   empty cave → dark, entry → dark, sustained stillness → brightens after
   `HOLD_DURATION` and climbs over `RECOVERY_DURATION`, moderate movement → dark.
   (Legacy `EMPTY_CAVE_DARK=0` inverts: empty → bright, still → bright, etc.)

### Operating envelope

The algorithm works reliably within these bounds. Outside this range, expect hard failure:

| Parameter | Working range | Failure below | Failure above |
|---|---|---|---|
| Kinect-to-chair distance | 105–180 cm (3.5–6 ft) | Silhouette too large → false occupancy | Silhouette too small → reads always empty |
| Kinect height from floor | 60–120 cm (24–48 in) | Floor enters foreground mask | Looking down too steeply, head exits frame |

**`KINECT_FG_DEPTH_THRESHOLD_MM=200` and `KINECT_MIN_FG_PIXELS=20000` can usually stay
fixed.** Only `KINECT_MASK_CHANGE_THRESHOLD` needs site-specific measurement.

---

## Remaining tasks before the event

Sensor work is complete. D008 settings are locked. The remaining work is
show-prep, not feature development.

- [ ] **Lock D008 config into Pi `.env`** — add `KINECT_MASK_CHANGE_THRESHOLD=40000`
      to the Pi `.env` so it is never accidentally omitted from a run command.

- [ ] **Empty cave dark mode** — implement `EMPTY_CAVE_DARK=1` per
      `docs/SPEC-empty-cave-dark.md`. Video plays dark when no one is present.
      Required for the correct ambient state between visitors. (In progress with CC.)

- [ ] **Autostart on boot** — systemd unit that launches `main.py` after boot.
      Artist is present and can restart manually, but autostart removes the need.

- [ ] **Auto-recalibration when cave is empty** — add logic to auto-recalibrate
      after the cave reads as empty for ≥ 30 consecutive seconds. Chair is taped
      down and artist can press `B` manually, so this is desirable not mandatory.

- [ ] **Empty cave dark mode** — implement `EMPTY_CAVE_DARK=1` per
      `docs/SPEC-empty-cave-dark.md`. Video plays dark when no one is present.
      Required for the correct ambient state between visitors.

- [ ] **Failed-read defence** — a transient `freenect.sync_get_depth` returning
      `None` currently reports `raw=1.0` (still), silently. For a 4-hour unattended
      install, a USB drop looks identical to a perfectly still viewer for the rest
      of the show. Add a consecutive-failed-reads counter that logs to stderr after
      N failures (e.g. 30 = ~1 second at 30fps). Small change, high value.

- [ ] **4-hour soak test** — run unattended on Pi with real Kinect, real projector,
      representative occupancy pattern. Watch for: memory leaks, thermal throttling,
      USB dropouts, HDMI sleep, dropped frames, background drift.

- [ ] **On-site dry run** — test in the actual venue with actual projector throw,
      fabric scrim, and ambient light. Cave lighting during development is
      approximate. Recalibrate `NADIR` on-site; the dark phase reads ~20% brighter
      on the Nebula Mars 3 than on a screen.

- [x] **Video looping** — `VideoPlayer` already seeks to frame 0 on end-of-file.
      Loop is seamless. Verified in code (`src/visual/player.py` lines 88–91).
