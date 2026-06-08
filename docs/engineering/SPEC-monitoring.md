# Spec: Soak Test Monitoring System

**Status:** Approved — implemented in this PR.
**Context:** Endymion is a **3-hour** unattended gallery installation. (Note: `docs/Project-Context.md` says "4-hour run" — that's stale; the event is 3 hours. Update that doc next time it's edited.) A 3+ hour soak test is required before the event. If something goes wrong during the test or the event itself, we need post-hoc diagnostic data to understand what happened and whether it was noticeable to a viewer.

---

## Goals

1. Capture enough data to diagnose any failure mode after the fact.
2. Add zero meaningful load to the Pi — all monitoring compute runs on the Mac.
3. Require no code changes to `main.py` or the core app — monitoring wraps the existing system from outside.
4. Be resilient to ordinary 3-hour-unattended Mac-side flakiness (Mac sleep, SSH hiccup, lost network).
5. Be simple enough to start and stop with a single command each.

---

## Run Timeline

The full operational sequence from setup through archive. **This is the test plan**; everything else in the spec is reference material.

| Step | Where | What |
|---|---|---|
| 1. Pre-flight | Mac | Verify ≥1 GB free on Mac and Pi (`df -h` each). Confirm Pi `.env` is set as intended (`HALF_RES_EFFECTS=1`, `LOG_FILE=logs/session.csv`, `EMPTY_CAVE_DARK=1`). |
| 2. Smoke-test monitor | Mac | `./tools/pi_monitor.sh 2` — confirm a 2-minute log appears in `logs/` with at least four poll lines. Optional: run analyser against an existing CSV. |
| 3. Start monitor | Mac | `caffeinate -i ./tools/pi_monitor.sh 200 &` — runs in background for 3h20m (3-hour test + 20-minute buffer), with the Mac prevented from sleeping. Note the log path it prints. |
| 4. Start app on Pi | Pi (SSH) | `cd ~/my-projects/endymion && source venv/bin/activate && python main.py 2>logs/soak_stderr_$(date +%Y%m%d_%H%M%S).log` (note the stderr log filename). |
| 5. Check-ins | Mac | At T+60min and T+120min: glance at terminal to confirm `main.py` still running; `grep WARNING logs/soak_monitor_*.log` for any alerts since last check. No need to verify the projector or sit in the chair (see §Human check-in protocol). |
| 6. End run | Pi (SSH) | Ctrl+C the `main.py` process. The monitor on the Mac stops automatically at its duration limit. |
| 7. Archive | Mac | `./tools/pi_monitor.sh` writes a final line on exit; then run the archive step (see §Teardown). |
| 8. Analyse | Mac | `python tools/analyse_soak.py logs/soak_<date>/session.csv logs/soak_<date>/soak_stderr_*.log logs/soak_<date>/soak_monitor_*.log` — read the report, apply pass/fail criteria. |

---

## Architecture

Two components, both running on the Mac:

- **Component 1 — `tools/pi_monitor.sh`** polls the Pi over SSH every 30 s during the run. Mac-side only; Pi is read-only.
- **Component 2 — `tools/analyse_soak.py`** runs on the Mac after the run, against the session CSV (plus optional Pi stderr log and monitor log).

No app code is touched. No code runs on the Pi other than the existing `main.py`.

---

## Component 1 — Pi health poller (`tools/pi_monitor.sh`)

### Canonical invocation
```bash
caffeinate -i ./tools/pi_monitor.sh 200
```

- `caffeinate -i` prevents Mac sleep / idle while the script runs. **Required.** Without it, a lid-close mid-test stops the monitor.
- `200` = duration in minutes (default 200 = 3 h 20 min, covering the 3-hour test plus buffer).

### What it polls

A single SSH session per poll runs four commands and parses the combined output on the Mac side:

| Command | Field captured |
|---|---|
| `vcgencmd measure_temp` | CPU temperature in °C |
| `vcgencmd get_throttled` | Throttle flag (hex) |
| `free -m` | "Available" memory in MB (field 7), reported as `mem_free` for spec compatibility |
| `pgrep -f "python.*main\.py"` | Whether `main.py` is running |

### SSH options (all required)

```
-o ConnectTimeout=5         # fail fast on hung connections
-o ServerAliveInterval=10   # detect dead connections during the command
-o BatchMode=yes            # never prompt for a password — fail instead
```

### Output format

One line per successful poll (tab-separated):
```
2026-05-14T12:00:00-07:00	temp=52.1C	throttled=0x0	mem_used=312MB	mem_free=3700MB	main_running=YES
```

One line on poll failure (network error, SSH timeout, Pi down):
```
2026-05-14T12:00:30-07:00	UNREACHABLE
```

One additional WARNING line per active alert (right after the data line that produced it):
```
2026-05-14T12:00:00-07:00	WARNING	temp 82.3C >= 80C
2026-05-14T12:00:00-07:00	WARNING	throttle active (0x50005)
```

### Alert conditions

- Temperature ≥ 80 °C (Pi 5 soft-throttles at 80, hard-throttles at 85)
- Throttle flag low 4 bits non-zero (`vcgencmd get_throttled & 0xF != 0` — currently-active throttling)
- `mem_free < 200 MB`
- `main_running != YES`

Note: `0x50000` (high bits set, low bits zero) means *previously* throttled but not currently. **Not** an alert — informational only.

### Persistence guarantees

- **Never exit the loop on a single poll failure.** Log `UNREACHABLE`, sleep, continue.
- **Flush each log line immediately.** Implemented via per-line `printf … >> file` (shell append-and-close flushes on each invocation).
- **Pass `caffeinate -i` from outside** to prevent Mac sleep. Without it, the script will die when the lid closes.

### Output file

`logs/soak_monitor_YYYYMMDD_HHMMSS.log`, created at start. Path is echoed to stdout so the caller can capture it.

---

## Component 2 — Session CSV analyser (`tools/analyse_soak.py`)

### Usage
```bash
python tools/analyse_soak.py <session.csv> [stderr.log] [monitor.log]
```

- `<session.csv>` — required. The per-frame CSV produced by `SessionLogger`.
- `[stderr.log]` — optional. The Pi-side stderr capture (`Exception`, `Traceback`, `[Kinect][WARN]` lines).
- `[monitor.log]` — optional. The Mac-side monitor log produced by `pi_monitor.sh`. Provides peak temperature + monitor warning count for the summary.

### Stdlib only

Uses `csv`, `statistics`, `re`, `sys`, `os`. No `numpy`, no `pandas`, no venv required. Tested with Python 3.8+.

### Checks performed

1. **USB / Kinect dropout detection** — runs of consecutive frames where `raw == 1.0` AND the diagnostic `changed` cell is empty for more than **10 seconds**. Under `EMPTY_CAVE_DARK=1` this combination is uniquely diagnostic of `freenect.sync_get_depth()` returning `None` (the depth-failure early-return path in `kinect.py` deliberately keeps `raw=1.0` to avoid snapping a live image to nadir on a single dropped frame; sustained for >10s means the Kinect is gone). The bright bypass in `player.py` will trip because `raw=1.0`, so the **viewer would see the video go bright** — opposite of the original failure-mode table.

2. **Signal drift** — split the in-frame portion into 10-minute windows. Compute the **p90 of `changed`** in each window. Flag any window whose p90 deviates by more than **25 %** from the **first window's p90** (the baseline). 25 % was chosen as a placeholder; once D-series data gives a measured normal variance, replace this with `μ ± 3σ`. Note: this metric is only meaningful if the cave occupancy pattern is roughly consistent across windows. For an empty-cave soak with `EMPTY_CAVE_DARK=1`, `changed` is empty most of the time (sensor returns `raw=0.0` from the empty-cave early return). The check is most useful for sessions that include viewer activity.

3. **False-trigger rate** — `% frames where raw < MOTION_TRIGGER`. The `MOTION_TRIGGER` value is read from `.env` (in the project root, parsed with stdlib), falling back to `0.7` if absent. **Interpretation depends on `EMPTY_CAVE_DARK` mode:**
   - `EMPTY_CAVE_DARK=0` (legacy bright-on-empty): an empty-cave soak should produce <5 % low-raw frames; higher = noise floor has risen above trigger.
   - `EMPTY_CAVE_DARK=1` (current default): an empty-cave soak produces 100 % low-raw frames by design (`raw=0.0` always when empty). Metric is meaningless. The complementary metric to watch is **% frames where `changed` is non-empty** — the cave reading as occupied during an expected-empty soak. Reported separately as "spurious-occupancy rate."

4. **Frame rate** — average fps from `t`-column deltas. Flag any sustained period (≥30 s) where fps < 10.

5. **Gap (freeze) detection** — any single `dt > 1.0 s` in the `t` column is a **freeze event**, distinct from low fps. Report timestamp + gap duration. A 1.5-second freeze and a 1.5-second period of 15fps look different to a viewer — the freeze is a stutter / hang.

6. **Stderr scan** (if path provided) — count occurrences of `Exception`, `Traceback`, `Error`, `[Kinect][WARN]`. Show up to the first 10 unique stderr lines containing those tokens.

7. **Monitor summary** (if path provided) — peak temperature, total WARNING line count, number of UNREACHABLE polls.

### Output

Plain text report to stdout. Sections:

```
=== Session summary ===
File: logs/session.csv
Duration: 184m 12s
Frames: 217,840
Average fps: 19.7

=== USB/Kinect dropout ===
0 dropout events.

=== Signal drift ===
Baseline p90 (window 0): 11,200
Window p90 deviations: ...

=== False-trigger / occupancy ===
% frames raw < 0.7: 100.0% (expected under EMPTY_CAVE_DARK=1)
% frames changed != empty: 0.3%

=== Frame rate ===
Avg fps: 19.7. Low-fps periods (≥30s of <10fps): 0.

=== Gap detection ===
0 freeze events (dt > 1.0s).

=== Stderr scan ===
0 Exception/Traceback hits.
2 [Kinect][WARN] lines (shown below).

=== Monitor summary ===
Peak temperature: 67.4°C. 0 WARNING lines. 1 UNREACHABLE poll.
```

---

## Pass / fail criteria

The soak test **passes** if all of the following hold:

| Check | Pass condition |
|---|---|
| Monitor warnings | 0 `WARNING` lines in `soak_monitor_*.log` |
| USB dropouts | 0 detected by analyser |
| Signal drift | All window p90s within ±25 % of baseline (or replaced metric once measured) |
| Freeze events | 0 `dt > 1.0 s` gaps |
| Stderr exceptions | 0 `Exception` / `Traceback` lines |
| Frame rate | No ≥30 s sustained period with fps < 10 |

`UNREACHABLE` polls are **not** automatic failures (transient SSH / mDNS hiccups happen). Investigate if more than ~3 in a 3-hour run.

---

## Teardown / archiving

After the run, run these from the Mac in order:

```bash
# 1. Determine the session subdirectory
SOAK_DIR="logs/soak_$(date +%Y%m%d)"
mkdir -p "$SOAK_DIR"

# 2. Sync the session CSV and stderr log from the Pi.
# Note: the `getlog` alias takes a D-series run ID; soak tests have no
# D-series ID, so use scp directly here.
scp box1@raspberrypi.local:'~/my-projects/endymion/logs/session.csv' "$SOAK_DIR/session.csv"
scp box1@raspberrypi.local:'~/my-projects/endymion/logs/soak_stderr_*.log' "$SOAK_DIR/"

# 3. Move the monitor log into the same subdirectory
mv logs/soak_monitor_*.log "$SOAK_DIR/"

# 4. Run analysis against the archived files
python tools/analyse_soak.py "$SOAK_DIR"/session.csv "$SOAK_DIR"/soak_stderr_*.log "$SOAK_DIR"/soak_monitor_*.log > "$SOAK_DIR/report.txt"

# 5. Read the report
cat "$SOAK_DIR/report.txt"
```

Result: `logs/soak_<date>/` contains `session.csv`, `soak_stderr_*.log`, `soak_monitor_*.log`, and `report.txt`. Tag the directory with a note (success / failure mode / circumstances) before moving on.

---

## Human check-in protocol

At T+60min and T+120min, two things only:

1. Glance at the SSH terminal — is `main.py` still running? (If yes, no further action; if no, see Failure recovery in `docs/AT-VENUE.md`.)
2. `grep WARNING logs/soak_monitor_*.log` — any new alerts since last check?

**Removed from this protocol** (compared to the original spec):
- ~~Sit in the chair to verify the sensor still responds~~ — contaminates the empty-cave baseline that drift detection relies on.
- ~~Verify the projector is displaying~~ — the projector runs continuously and is not a concern.

---

## Appendix A — Failure modes and viewer impact

Updated for the `EMPTY_CAVE_DARK=1` world (default since PR #19).

| Failure mode | Likely viewer experience | Detectable how |
|---|---|---|
| App crash | Frozen frame, then black after some seconds (depends on projector behaviour) | Process no longer running on Pi (`main_running=NO`) |
| Kinect / USB dropout | `freenect.sync_get_depth()` returns `None` → `raw=1.0` sustained → bright bypass engages → **video goes bright, stays bright** while the dropout persists. The opposite of the legacy bright-on-empty era. | `raw=1.0` sustained AND `changed` empty for >10s, detected by the analyser |
| Thermal throttling | Video stutters, fps drops | Pi CPU temp ≥80°C; `vcgencmd get_throttled` low-bits non-zero |
| Memory leak | Gradual fps degradation, eventual crash | `mem_free` declining over time in monitor log |
| HDMI sleep | Projector goes dark *despite* HDMI signal being alive (Pi keeps producing frames) | Not detectable from the Pi side. Mitigation: projector auto-sleep disabled in firmware before the run. |
| Signal drift | Sensitivity shifting over time (e.g. background drift after thermal expansion) | `changed` p90 per-window comparison in analyser |
| Video decode failure | Frozen frame, possibly stuck on a corrupted frame | Exception in Pi stderr log; `dt > 1.0s` gap in CSV |

---

## What this does NOT cover

- **HDMI sleep at the projector end.** Cannot be detected from the Pi. The projector's own auto-sleep firmware setting must be disabled before the run (per `docs/AT-VENUE.md`).
- **Visual quality degradation** (e.g. half-res upscale becoming visible due to projector throw change). Human observation only — but that's a setup-time concern, not a soak-time concern.
- **Network failure between Mac and Pi.** Logged as `UNREACHABLE`; no automatic recovery beyond "next poll tries again."
- **Pi's own filesystem space.** Worth pre-checking with `ssh ... 'df -h /'` before the run (Step 1 of the Run Timeline).
- **Real-time alerts.** The monitor writes WARNING lines to disk; nothing pages a human. For unattended overnight tests, consider piping WARNING lines to `osascript -e 'display notification ...'` or similar — left as a future addition.

---

## Implementation surface area

| File | Status |
|---|---|
| `tools/pi_monitor.sh` | New — Mac-side bash poller |
| `tools/analyse_soak.py` | New — stdlib-only post-run analyser |
| `docs/SPEC-monitoring.md` | This document (revised) |

No changes to `main.py`, `src/`, `env.example`, or any existing app code.
