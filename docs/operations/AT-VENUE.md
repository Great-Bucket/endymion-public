# Endymion — At-Venue Setup

Everything that needs to happen at the gallery to get the installation running.
Work through this in order. Do not skip the calibration step.

---

## Hardware checklist — bring these

- [ ] Raspberry Pi 5 + power supply (27W USB-C)
- [ ] Kinect v1 (Xbox 360) + power/USB cable
- [ ] KOOV Projector Stand
- [ ] Nebula Mars 3 Air projector + power cable + HDMI cable
- [ ] Micro-HDMI → HDMI cable (Pi to projector)
- [ ] MacBook (for SSH, log analysis, and emergency access)
- [ ] Chair (bring the same chair used during calibration — seat height matters)
- [ ] Tape or floor bolts to fix the chair position
- [ ] USB keyboard (for initial setup and fallback recalibration)

---

## Step 1 — Physical placement

Target geometry:

| Parameter | Target | Acceptable range |
|---|---|---|
| Kinect → front edge of chair | 120 cm | 105–180 cm |
| Kinect height from floor (bottom edge) | 70–75 cm | 60–120 cm |
| Viewer → back wall (behind chair) | > 50 cm | More is better — depth gap must stay > 200mm |

- Mount Kinect on KOOV stand. Aim it at the centre of the seated viewer's torso.
- Tilt the Kinect slightly upward if needed so the full seated silhouette is in frame.
- Fix the chair to the floor with tape or bolts. **The chair must not move after
  calibration.** If it moves, the background model is invalid and the image stays dark.
- Run a short video on the projector (any HDMI output) to confirm throw angle, focus,
  and keystone before touching the Pi.

---

## Step 2 — Pi boot and software check

Power on the Pi. Connect via SSH from the Mac:

**Preferred (static ethernet, most reliable):**
```bash
ssh -o ServerAliveInterval=30 box1@10.0.0.1
```

**Fallback (mDNS, requires same network):**
```bash
ssh box1@raspberrypi.local
```

If both fail:
```bash
arp -a | grep raspberry   # find IP, then ssh box1@<IP>
```

See `HANDOFF-pi-setup.md` for ethernet static-IP setup instructions.

Pull the latest code:
```bash
cd ~/my-projects/endymion
git pull
source venv/bin/activate
```

---

## Step 3 — Projector settings

On the Nebula Mars 3 Air:
- **Disable auto-shutoff** — it will sleep after 10 min of HDMI inactivity and
  power off after 30 min standby. Disable both in the projector's settings menu.
- **Set to plug-in power mode** — do not run on battery for a 4-hour event.
- **Focus and keystone** — set before calibration so the image is final.

The dark phase of the video reads ~20% brighter on the projector than on a monitor.
Tune `NADIR` in the `.env` after the calibration run if the dark level feels wrong.
(`NADIR=0.12` was the home value — may need to go lower at the venue.)

---

## Step 4 — Sensor calibration (mandatory at every new venue)

The D008 home settings will not work unmodified at a new location. The noise floor
changes with distance and room geometry. You must measure it on site.

### 4a. Measure the still noise floor

Run a diagnostic session (cave empty, then you sit still for 30 seconds):

```bash
# ON PI:
source venv/bin/activate
SENSOR_TYPE=kinect FULLSCREEN=0 DEBUG=1 \
  EFFECTS=none \
  LOG_FILE=logs/session.csv \
  python main.py
```

- Stand clear while the background is captured (`[Kinect] Background captured.`).
- Sit in the chair. Sit completely still for 30 seconds. Exit the cave. Stop the run (`Q`).

Fetch the log to the Mac:
```bash
# ON MAC:
getlog D010   # use next available D-series number
```

### 4b. Calculate the new threshold

Open the CSV. Look at the `changed` column during the still-sitting segment.
Find the **p90 value** (the 90th percentile — sort the column, take the value at 90%).

```
KINECT_MASK_CHANGE_THRESHOLD = round(p90_still × 3.5, nearest 5000)
```

| p90 still floor | Set threshold to |
|---|---|
| ~10,000 (same as home) | 35,000–40,000 |
| ~12,000 | 42,000 → use **45,000** |
| ~14,000 (Kinect closer) | 49,000 → use **50,000** |
| ~8,000 (Kinect further) | 28,000 → use **30,000** |

### 4c. Update the Pi .env

```bash
# ON PI:
nano ~/my-projects/endymion/.env
```

Set `KINECT_MASK_CHANGE_THRESHOLD` to the value from 4b.
Leave all other sensor parameters unchanged.

### 4d. Verification run

Run a quick verification (2–3 minutes):

```bash
SENSOR_TYPE=kinect FULLSCREEN=1 DEBUG=1 \
  EFFECTS=luminosity,vignette,desaturation \
  LOG_FILE=logs/session.csv \
  python main.py
```

Confirm (assumes `EMPTY_CAVE_DARK=1`, the default):
- [ ] Cave empty at startup → video is **dark** during *and* after calibration
- [ ] You enter → video stays dark
- [ ] You sit completely still → after `HOLD_DURATION` seconds video begins to
      brighten, climbing to full over `RECOVERY_DURATION`
- [ ] You rock torso or extend arm → video goes dark
- [ ] You leave → video stays dark (cave empty)

If the video never brightens after sustained stillness: threshold is still too
low — the still-noise floor is firing the penalty continuously. Increase
`KINECT_MASK_CHANGE_THRESHOLD` by 10 000 and retest.
If small body shifts don't darken the video: threshold is too high — decrease
by 10 000 and retest.

> Legacy bright-on-empty mode: set `EMPTY_CAVE_DARK=0` in `.env`. In that mode
> the checklist inverts (empty → bright, still viewer → bright, movement → dark,
> leave → returns to bright). Kept for rollback; not the production setting.

---

## Step 5 — Production run

Once calibration passes, update `.env` for the show:

```
DEBUG=0
LOG_FILE=
FULLSCREEN=1
```

The app starts automatically at boot via the systemd service. To start, stop, or restart it manually:

```bash
# ON PI:
systemctl --user start endymion      # start
systemctl --user stop endymion       # stop
systemctl --user restart endymion    # restart (recalibrates — cave must be empty)
journalctl --user -u endymion -f     # watch live logs
```

The app runs unattended from here. The Pi must stay powered and the HDMI cable connected.

**Between visitors or after a lighting change:** restart with cave empty so it recalibrates a clean background:
```bash
systemctl --user restart endymion
```
Stay out of the cave for ~2 seconds after restart.

**B-key recalibration:** if a keyboard is connected, press `B` with cave empty to recalibrate
the background without restarting the app.

---

## Step 6 — Failure recovery

| Symptom | Cause | Fix |
|---|---|---|
| Video stays dark permanently with viewer in chair | Chair moved after calibration, or threshold too low (still-floor firing penalty continuously) | Press `B` with cave empty to recalibrate; if persistent, raise `KINECT_MASK_CHANGE_THRESHOLD` |
| Video stays bright with cave empty | `EMPTY_CAVE_DARK=0` in `.env` (legacy mode), or PenaltyRoutine not firing | Confirm `EMPTY_CAVE_DARK=1` in `.env`; check Kinect is producing depth data |
| Video stays bright with viewer present, no response to movement | Kinect not recognised, or threshold too high | Check Kinect USB; check stderr output |
| Projector goes to sleep | Auto-shutoff not disabled | Wake projector; disable sleep in projector settings |
| App crashes / no video | Pi error | SSH in, check logs, restart `python main.py` |
| SSH fails | Pi not on same network, or mDNS not resolving | Try IP directly: `arp -a | grep raspberry` |

---

## Known limitations

- **Head rotation is not detected.** The sensor responds to body-level movement —
  weight shifts, torso rocking, arm gestures, entry, exit. A viewer who sits still
  but moves only their head will not trigger the penalty. This is an accepted design
  position, not a bug.
- **No network at venue** — the Pi must have the latest code pulled before arriving.
  Run `git pull` at home on the day of the event.
